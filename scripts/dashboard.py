from __future__ import annotations

import argparse
import html
import json
import math
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from statistics import mean
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "dashboard.yaml"
DEFAULT_SLO_PATH = REPO_ROOT / "config" / "slo.yaml"


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _percentile(values: list[float], p: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil((p / 100) * len(ordered)) - 1)
    return float(ordered[index])


def load_records(path: Path, *, now: datetime, window_minutes: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    cutoff = now - timedelta(minutes=window_minutes)
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        timestamp = _parse_timestamp(record.get("ts"))
        if timestamp is not None and cutoff <= timestamp <= now:
            records.append(record)
    return records


def collect_metrics(
    records: list[dict[str, Any]], *, now: datetime, window_minutes: int
) -> dict[str, Any]:
    requests = [record for record in records if record.get("event") == "request_received"]
    responses = [record for record in records if record.get("event") == "response_sent"]
    failures = [record for record in records if record.get("event") == "request_failed"]
    latency = [float(record["latency_ms"]) for record in responses if isinstance(record.get("latency_ms"), (int, float))]
    ttft = [float(record["ttft_ms"]) for record in responses if isinstance(record.get("ttft_ms"), (int, float))]
    costs = [float(record["cost_usd"]) for record in responses if isinstance(record.get("cost_usd"), (int, float))]
    tokens_in = sum(int(record.get("tokens_in") or 0) for record in responses)
    tokens_out = sum(int(record.get("tokens_out") or 0) for record in responses)
    qualities = [float(record["quality_score"]) for record in responses if isinstance(record.get("quality_score"), (int, float))]

    retrieval_events = [record for record in records if isinstance(record.get("tool_success"), bool)]
    retrieval_successes = sum(record["tool_success"] is True for record in retrieval_events)
    retrieval_success_rate = (
        100 * retrieval_successes / len(retrieval_events) if retrieval_events else None
    )
    error_rate = 100 * len(failures) / len(requests) if requests else 0.0
    error_breakdown = Counter(
        str(record.get("error_type") or "UnknownError") for record in failures
    )

    minute_start = now.replace(second=0, microsecond=0) - timedelta(minutes=window_minutes - 1)
    traffic_by_minute: Counter[str] = Counter()
    cost_by_minute: Counter[str] = Counter()
    for record in records:
        timestamp = _parse_timestamp(record.get("ts"))
        if timestamp is None:
            continue
        bucket = timestamp.replace(second=0, microsecond=0).isoformat()
        if record.get("event") == "request_received":
            traffic_by_minute[bucket] += 1
        if record.get("event") == "response_sent" and isinstance(record.get("cost_usd"), (int, float)):
            cost_by_minute[bucket] += float(record["cost_usd"])

    minute_buckets = [
        (minute_start + timedelta(minutes=index)).isoformat()
        for index in range(window_minutes)
    ]

    return {
        "generated_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "window_minutes": window_minutes,
        "record_count": len(records),
        "latency_ms": {
            "p50": _percentile(latency, 50),
            "p95": _percentile(latency, 95),
            "p99": _percentile(latency, 99),
            "ttft_p95": _percentile(ttft, 95),
        },
        "traffic": {
            "request_count": len(requests),
            "per_minute": len(requests) / window_minutes if window_minutes else 0,
            "series": [traffic_by_minute[bucket] for bucket in minute_buckets],
        },
        "errors": {
            "failure_count": len(failures),
            "error_rate_pct": error_rate,
            "breakdown": dict(error_breakdown),
            "retrieval_success_pct": retrieval_success_rate,
            "retrieval_attempts": len(retrieval_events),
        },
        "cost": {
            "total_usd": sum(costs),
            "series": [cost_by_minute[bucket] for bucket in minute_buckets],
        },
        "tokens": {"input": tokens_in, "output": tokens_out, "total": tokens_in + tokens_out},
        "quality": {"mean": mean(qualities) if qualities else None, "sample_count": len(qualities)},
    }


def _fmt(value: float | int | None, decimals: int = 1) -> str:
    return "—" if value is None else f"{value:,.{decimals}f}"


def _threshold(panel: dict[str, Any]) -> str:
    item = panel["threshold"]
    symbol = "≤" if item["operator"] == "lte" else "≥"
    unit = panel.get("unit", "")
    aggregation = str(item["aggregation"]).replace("_", " ")
    return f"Threshold: {aggregation} {symbol} {item['value']:,} {unit}"


def _bars(values: list[float | int], *, color: str, unit: str) -> str:
    max_value = max((float(value) for value in values), default=0.0)
    if max_value <= 0:
        max_value = 1.0
    bars = []
    for index, value in enumerate(values):
        height = max(2, round(float(value) / max_value * 100)) if value else 2
        bars.append(
            f'<span title="Minute {index + 1}: {value} {html.escape(unit)}" '
            f'class="bar" style="height:{height}%;background:{color}"></span>'
        )
    return '<div class="chart" aria-label="minute-by-minute chart">' + "".join(bars) + "</div>"


def render_dashboard(
    metrics: dict[str, Any],
    dashboard_config: dict[str, Any],
    slo_config: dict[str, Any],
) -> str:
    dashboard = dashboard_config["dashboard"]
    panels = {panel["id"]: panel for panel in dashboard["panels"]}
    latency = metrics["latency_ms"]
    errors = metrics["errors"]
    traffic = metrics["traffic"]
    cost = metrics["cost"]
    tokens = metrics["tokens"]
    quality = metrics["quality"]
    slo = slo_config["primary_slo"]
    retrieval_threshold = slo_config["guardrails"]["retrieval_success_rate_pct_min"]

    error_items = "".join(
        f"<li>{html.escape(name)}: {count}</li>"
        for name, count in sorted(errors["breakdown"].items())
    ) or "<li>No failures in this window</li>"

    panel_html = [
        f'''<section class="panel"><h2>{html.escape(panels["latency"]["title"])}</h2>
        <p class="threshold">{_threshold(panels["latency"])}</p>
        <div class="metric-grid four">
          <div><small>P50</small><strong>{_fmt(latency["p50"])} ms</strong></div>
          <div><small>P95</small><strong>{_fmt(latency["p95"])} ms</strong></div>
          <div><small>P99</small><strong>{_fmt(latency["p99"])} ms</strong></div>
          <div><small>TTFT P95</small><strong>{_fmt(latency["ttft_p95"])} ms</strong></div>
        </div><div class="latency-bars">'''
        + "".join(
            f'<div class="latency-row"><span>{label}</span><span class="track"><i style="width:{min(100, (value or 0) / max(panels["latency"]["threshold"]["value"], 1) * 100):.1f}%"></i></span><b>{_fmt(value)} ms</b></div>'
            for label, value in (("P50", latency["p50"]), ("P95", latency["p95"]), ("P99", latency["p99"]), ("TTFT P95", latency["ttft_p95"]))
        )
        + "</div></section>",
        f'''<section class="panel"><h2>{html.escape(panels["traffic"]["title"])}</h2>
        <p class="threshold">{_threshold(panels["traffic"])}</p>
        <div class="hero">{traffic["request_count"]}<small>requests / {metrics["window_minutes"]} min</small></div>
        <p class="submetric">{_fmt(traffic["per_minute"], 2)} requests/min</p>
        {_bars(traffic["series"], color="#4f8cff", unit="requests")}</section>''',
        f'''<section class="panel"><h2>{html.escape(panels["errors"]["title"])}</h2>
        <p class="threshold">{_threshold(panels["errors"])} · retrieval success ≥ {retrieval_threshold}%</p>
        <div class="metric-grid two">
          <div><small>Error rate</small><strong>{_fmt(errors["error_rate_pct"])}%</strong></div>
          <div><small>Retrieval success</small><strong>{_fmt(errors["retrieval_success_pct"])}%</strong></div>
        </div><p class="submetric">{errors["failure_count"]} failed / {traffic["request_count"]} requests</p>
        <ul class="breakdown">{error_items}</ul></section>''',
        f'''<section class="panel"><h2>{html.escape(panels["cost"]["title"])}</h2>
        <p class="threshold">{_threshold(panels["cost"])}</p>
        <div class="hero">${cost["total_usd"]:.6f}<small>USD total / last hour</small></div>
        {_bars(cost["series"], color="#b16cff", unit="USD")}</section>''',
        f'''<section class="panel"><h2>{html.escape(panels["tokens"]["title"])}</h2>
        <p class="threshold">{_threshold(panels["tokens"])}</p>
        <div class="metric-grid two">
          <div><small>Input</small><strong>{tokens["input"]:,} tokens</strong></div>
          <div><small>Output</small><strong>{tokens["output"]:,} tokens</strong></div>
        </div><p class="submetric">{tokens["total"]:,} total tokens</p>
        <div class="token-track"><i style="width:{(100 * tokens["input"] / tokens["total"] if tokens["total"] else 0):.1f}%"></i></div>
        <small class="legend">Input / Output</small></section>''',
        f'''<section class="panel"><h2>{html.escape(panels["quality"]["title"])}</h2>
        <p class="threshold">{_threshold(panels["quality"])}</p>
        <div class="hero">{_fmt(quality["mean"], 3)}<small>score, range 0–1</small></div>
        <p class="submetric">{quality["sample_count"]} response samples</p>
        <div class="quality-track"><i style="width:{min(100, max(0, (quality["mean"] or 0) * 100)):.1f}%"></i><b style="left:{panels["quality"]["threshold"]["value"] * 100:.1f}%"></b></div>
        <small class="legend">SLO threshold at {panels["quality"]["threshold"]["value"]}</small></section>''',
    ]

    refresh = int(dashboard["refresh_seconds"])
    generated = html.escape(metrics["generated_at"])
    title = html.escape(dashboard["title"])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="{refresh}"><title>{title}</title>
<style>
:root{{color-scheme:dark;--bg:#0a1020;--panel:#121c31;--line:#26354f;--muted:#9aaac3;--text:#edf3ff;}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(ellipse at top,#17294a,var(--bg) 55%);color:var(--text);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:28px}}
header{{max-width:1440px;margin:0 auto 22px;display:flex;justify-content:space-between;align-items:end;gap:18px}}h1{{margin:0;font-size:25px}}header p{{margin:5px 0 0;color:var(--muted)}}.stamp{{text-align:right;color:var(--muted);font-size:12px}}
.grid{{max-width:1440px;margin:auto;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}}.panel{{background:linear-gradient(150deg,#17233a,#10192b);border:1px solid var(--line);border-radius:14px;padding:18px;min-height:235px;box-shadow:0 12px 30px #0003}}
h2{{font-size:15px;letter-spacing:.01em;margin:0 0 8px}}.threshold,.legend{{font-size:11px;color:var(--muted)}}.threshold{{margin:0 0 18px}}.metric-grid{{display:grid;gap:10px}}.metric-grid.four{{grid-template-columns:repeat(4,1fr)}}.metric-grid.two{{grid-template-columns:repeat(2,1fr)}}.metric-grid div{{background:#0b1425;border:1px solid #24344f;border-radius:9px;padding:10px 9px;min-width:0}}small{{display:block;color:var(--muted);font-size:11px}}strong{{display:block;margin-top:4px;font-size:17px;white-space:nowrap}}.hero{{font-size:31px;font-weight:700;letter-spacing:-.04em}}.hero small{{font-size:11px;font-weight:400;letter-spacing:0;margin-top:1px}}.submetric{{margin:8px 0 12px;color:#c0cce0}}.chart{{height:46px;display:flex;align-items:end;gap:2px;margin-top:16px;border-bottom:1px solid #3a4a65}}.bar{{flex:1;min-width:2px;border-radius:3px 3px 0 0;opacity:.9}}.latency-bars{{margin-top:15px;display:grid;gap:7px}}.latency-row{{display:grid;grid-template-columns:55px 1fr 82px;gap:8px;align-items:center;color:var(--muted);font-size:11px}}.latency-row b{{font-size:11px;color:var(--text);text-align:right}}.track,.token-track,.quality-track{{height:7px;background:#26354f;border-radius:99px;position:relative;overflow:hidden}}.track i,.token-track i,.quality-track i{{display:block;height:100%;background:#4f8cff;border-radius:99px}}.breakdown{{padding-left:17px;margin:10px 0;color:#d4deee;font-size:12px}}.token-track{{margin:15px 0 7px}}.token-track i{{background:linear-gradient(90deg,#37c9a6,#b16cff)}}.quality-track{{margin:23px 0 8px;overflow:visible}}.quality-track i{{background:#38c98e}}.quality-track b{{position:absolute;width:2px;height:15px;background:#ffcc6e;top:-4px}}@media(max-width:1050px){{.grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}@media(max-width:680px){{body{{padding:16px}}header{{display:block}}.stamp{{text-align:left;margin-top:12px}}.grid{{grid-template-columns:1fr}}.metric-grid.four{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body>
<header><div><h1>{title}</h1><p>Operational view · rolling {metrics["window_minutes"]} minutes · refresh every {refresh}s</p></div><div class="stamp">Updated {generated} UTC<br>{metrics["record_count"]} log records in window</div></header>
<main class="grid">{"".join(panel_html)}</main>
</body></html>'''


def _read_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected a YAML object in {path}")
    return loaded


class DashboardHandler(BaseHTTPRequestHandler):
    log_path = DEFAULT_LOG_PATH
    dashboard_config = _read_yaml(DEFAULT_CONFIG_PATH)
    slo_config = _read_yaml(DEFAULT_SLO_PATH)

    def do_GET(self) -> None:
        now = datetime.now(timezone.utc)
        window = int(self.dashboard_config["dashboard"]["time_range_minutes"])
        records = load_records(self.log_path, now=now, window_minutes=window)
        payload = collect_metrics(records, now=now, window_minutes=window)
        if self.path == "/api/metrics":
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        elif self.path in ("/", "/index.html"):
            body = render_dashboard(payload, self.dashboard_config, self.slo_config).encode("utf-8")
            content_type = "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the six-panel JSONL dashboard")
    parser.add_argument("--logs", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--slo", type=Path, default=DEFAULT_SLO_PATH)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--output", type=Path, help="Write a static HTML snapshot instead of serving")
    args = parser.parse_args()

    dashboard_config = _read_yaml(args.config)
    slo_config = _read_yaml(args.slo)
    now = datetime.now(timezone.utc)
    window = int(dashboard_config["dashboard"]["time_range_minutes"])
    records = load_records(args.logs, now=now, window_minutes=window)
    metrics = collect_metrics(records, now=now, window_minutes=window)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render_dashboard(metrics, dashboard_config, slo_config), encoding="utf-8")
        print(f"Wrote dashboard snapshot: {args.output}")
        return

    DashboardHandler.log_path = args.logs
    DashboardHandler.dashboard_config = dashboard_config
    DashboardHandler.slo_config = slo_config
    server = HTTPServer((args.host, args.port), DashboardHandler)
    print(f"Dashboard listening at http://{args.host}:{args.port} (window {window}m)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Dashboard stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
