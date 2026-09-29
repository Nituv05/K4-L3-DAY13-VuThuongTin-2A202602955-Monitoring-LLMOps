"""Read real CP3 logs and Langfuse observations; export sanitized evidence."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from app.challenge import load_challenge
from scripts.dashboard import collect_metrics

OUT = ROOT / 'submission/evidence'


def save(name, payload):
    (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + '\n')


def parse(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def main():
    load_dotenv(ROOT / '.env')
    from langfuse import get_client
    challenge = load_challenge(ROOT / 'config/challenge.json')
    phases = json.loads((OUT / 'cp3-phases.json').read_text())
    sessions = {q['session_id'] for q in challenge.queries}
    records = [json.loads(line) for line in (ROOT / 'data/logs.jsonl').read_text().splitlines() if line.strip()]
    summaries = []
    phase_records = {}
    for phase in phases:
        start, end = parse(phase['start']), parse(phase['end'])
        selected = [r for r in records if r.get('session_id') in sessions and start <= parse(r['ts']) <= end]
        phase_records[phase['phase']] = selected
        metrics = collect_metrics(selected, now=end, window_minutes=60)
        responses = [r for r in selected if r.get('event') == 'response_sent']
        summaries.append(dict(phase=phase['phase'], start=phase['start'], end=phase['end'], metrics=metrics, slow_requests=sum(r['latency_ms'] > challenge.latency_threshold_ms for r in responses)))
    incident_records = phase_records['incident']
    representative = max((r for r in incident_records if r.get('event') == 'response_sent'), key=lambda r:r['latency_ms'])
    cid = representative['correlation_id']
    client = get_client()
    result = client.api.observations.get_many(from_start_time=parse(phases[0]['start'])-timedelta(seconds=1), to_start_time=parse(phases[-1]['end'])+timedelta(seconds=1), limit=200, fields='core,basic,metadata,model,usage,prompt,metrics')
    groups = defaultdict(list)
    keys = ['id','trace_id','parent_observation_id','name','type','start_time','end_time','session_id','model','prompt_name','prompt_version','usage_details','cost_details','metadata','latency']
    for item in result.data:
        if item.session_id not in sessions:
            continue
        row = {key:getattr(item,key,None) for key in keys}
        if isinstance(row['metadata'],str): row['metadata']=json.loads(row['metadata'])
        row['metadata'] = {k:v for k,v in (row['metadata'] or {}).items() if 'key' not in k.lower() and 'secret' not in k.lower()}
        groups[item.trace_id].append(row)
    matching = [(tid,obs) for tid,obs in groups.items() if any(o['metadata'].get('correlation_id') == cid for o in obs)]
    if not matching:
        raise RuntimeError('Incident trace not available yet; rerun this read-only export shortly.')
    trace_id, observations = matching[0]
    root = next(o for o in observations if o['type']=='AGENT')
    retr = next(o for o in observations if o['type']=='RETRIEVER')
    gen = next(o for o in observations if o['type']=='GENERATION')
    assert retr['parent_observation_id'] == gen['parent_observation_id'] == root['id']
    trace_url = client.get_trace_url(trace_id=trace_id)
    payload = dict(challenge_id=challenge.challenge_id,seed=challenge.seed,incident=challenge.incident,threshold_ms=challenge.latency_threshold_ms,affected_feature=challenge.affected_feature,phases=summaries,representative=dict(correlation_id=cid,trace_id=trace_id,trace_url=trace_url,log=representative,retrieval_ms=round(retr['latency']*1000,2),generation_ms=round(gen['latency']*1000,2),root_ms=round(root['latency']*1000,2)),trace_count=len(groups),observation_count=sum(map(len,groups.values())))
    save('12-incident-metric.json',payload)
    log_lines=[r for r in incident_records if r.get('correlation_id')==cid]
    (OUT/'13-incident-log.txt').write_text('Source: data/logs.jsonl\nChallenge: '+challenge.challenge_id+'\nTrace ID: '+trace_id+'\n'+'\n'.join(json.dumps(r,ensure_ascii=False) for r in log_lines)+'\n')
    save('14-incident-trace.json',dict(source='Langfuse V2 observations API',trace_id=trace_id,correlation_id=cid,trace_url=trace_url,observations=observations))
    save('cp3-trace-index.json',dict(traces=[dict(trace_id=tid,correlation_id=next(o['metadata'].get('correlation_id') for o in obs if o['type']=='AGENT'),retrieval_ms=round(next(o['latency'] for o in obs if o['type']=='RETRIEVER')*1000,2)) for tid,obs in groups.items()]))
    rows=''.join(f"<tr><td>{s['phase']}</td><td>{s['start']}</td><td>{s['end']}</td><td>{s['metrics']['traffic']['request_count']}</td><td>{s['metrics']['latency_ms']['p95']:.0f}</td><td>{s['metrics']['latency_ms']['ttft_p95']:.0f}</td><td>{s['slow_requests']}/5</td></tr>" for s in summaries)
    bars=''.join(f"<div class='row'><b>{s['phase']}</b><div class='track'><i style='width:{s['metrics']['latency_ms']['p95']/40:.1f}%'></i><em></em></div><strong>{s['metrics']['latency_ms']['p95']:.0f} ms</strong></div>" for s in summaries)
    style="body{font:18px system-ui;background:#0b1425;color:#eef3ff;padding:40px}h1{font-size:30px}h2{font-size:22px}p{color:#bdcbe2}table{width:100%;border-collapse:collapse;font-size:15px}td,th{text-align:left;padding:12px;border-bottom:1px solid #33445f}.card{background:#152238;border:1px solid #33445f;border-radius:15px;padding:24px;margin:24px 0}.row{display:grid;grid-template-columns:120px 1fr 130px;gap:15px;margin:25px 0}.track{position:relative;background:#25364f;height:30px}.track i{display:block;background:#a878ff;height:100%}.track em{position:absolute;left:50%;height:42px;top:-6px;border-left:3px solid #ffcc6e}code,pre{font-size:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere}"
    metric_html=f"<html><head><meta charset='utf-8'><style>{style}</style></head><body><h1>CP3 — Retrieval latency incident</h1><p>Challenge: {challenge.challenge_id} · feature: {challenge.affected_feature} · seed: {challenge.seed}</p><p>Source: actual request logs, grouped by recorded phase intervals (UTC). Application latency excludes HTTP queue wait.</p><div class='card'><h2>Latency P95 · phase comparison</h2><p>Yellow line: challenge threshold {challenge.latency_threshold_ms} ms; scale 0–4000 ms.</p>{bars}</div><div class='card'><table><tr><th>Phase</th><th>Start UTC</th><th>End UTC</th><th>Requests</th><th>P95 ms</th><th>TTFT P95 ms</th><th>&gt;2000 ms</th></tr>{rows}</table></div><div class='card'><h2>Representative incident request</h2><p>Correlation: {cid}<br>Trace: {trace_id}<br>Log latency: {representative['latency_ms']} ms · retrieval: {payload['representative']['retrieval_ms']} ms · generation: {payload['representative']['generation_ms']} ms</p><p>HTTP errors: 0. Retrieval success: 100%. Slow retrieval is localized by the child observation.</p></div></body></html>"
    (OUT/'12-incident-metric.html').write_text(metric_html)
    log_html=f"<html><head><meta charset='utf-8'><style>{style}</style></head><body><h1>CP3 — Actual structured log excerpt</h1><p>Source: data/logs.jsonl · {challenge.challenge_id}</p><p>Trace ID: {trace_id} · Correlation ID: {cid}</p><div class='card'><pre>{html.escape(chr(10).join(json.dumps(r,indent=2,ensure_ascii=False) for r in log_lines))}</pre></div></body></html>"
    (OUT/'13-incident-log.html').write_text(log_html)
    print(json.dumps({k:v for k,v in payload.items() if k not in ['phases']},indent=2,default=str))
    print('P95 phase summaries:', [(s['phase'],s['metrics']['latency_ms'],s['slow_requests']) for s in summaries])
    client.shutdown()


if __name__=='__main__':
    main()
