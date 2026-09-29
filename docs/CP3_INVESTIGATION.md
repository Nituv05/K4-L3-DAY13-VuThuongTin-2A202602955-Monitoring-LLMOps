# CP3 — Điều tra challenge chính thức

Challenge `day13-k4-l3a-monitoring-llmops-v1` được chạy nguyên queries và seed 1311 từ file Lab Coach. File challenge được gitignore, không commit/push.

## Chạy lại workload (sẽ tạo logs/traces mới)

```sh
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --env-file .env
```

Trong terminal khác:

```sh
BASE_URL=http://127.0.0.1:8001 .venv/bin/python scripts/load_test.py --challenge --concurrency 5
BASE_URL=http://127.0.0.1:8001 .venv/bin/python scripts/inject_incident.py
BASE_URL=http://127.0.0.1:8001 .venv/bin/python scripts/load_test.py --challenge --concurrency 5
BASE_URL=http://127.0.0.1:8001 .venv/bin/python scripts/inject_incident.py --disable
BASE_URL=http://127.0.0.1:8001 .venv/bin/python scripts/load_test.py --challenge --concurrency 5
```

Không chạy lại nếu chỉ cần xem evidence đã có. Script export bên dưới dùng ranh giới thời gian đã lưu cho lần điều tra gốc:

```sh
.venv/bin/python scripts/export_cp3_evidence.py
```

## Kết quả đã đo

| Giai đoạn | Requests | P95 agent latency | TTFT P95 | Vượt 2000 ms |
|---|---:|---:|---:|---:|
| Baseline | 5 | 1458 ms | 54 ms | 0/5 |
| Incident | 5 | 3372 ms | 55 ms | 5/5 |
| Recovery | 5 | 853 ms | 55 ms | 0/5 |

Request đại diện `req-a7eae60b`, trace `ec779bdefc94672332ed8fc77ee6260b`: retrieval 2506 ms, generation 157 ms, root 3373 ms. Tắt `rag_slow` đã khôi phục latency. Raw HTTP latency lớn hơn agent latency do blocking/queue wait; P95 tích lũy process vẫn chứa request incident sau recovery.

## Evidence

Xem `submission/REPORT.md` mục 7 và `submission/evidence/12-incident-metric.*`, `13-incident-log.*`, `14-incident-trace.json`. Ảnh UI Langfuse mục 14 cần thể hiện trace ID, project và span retrieval chậm; API JSON là bằng chứng bổ trợ.
