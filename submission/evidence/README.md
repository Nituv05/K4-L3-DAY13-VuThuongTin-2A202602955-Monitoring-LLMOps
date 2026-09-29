# Evidence cá nhân

Đặt ảnh hoặc output text dùng để chấm vào thư mục này. Danh sách đầy đủ xem tại [docs/SUBMISSION.md](../../docs/SUBMISSION.md).

Tên file gợi ý:

```text
01-pytest.png
02-log-validator.png
03-dashboard-validator.png
04-structured-log.png
05-pii-redaction.png
06-trace-list.png
07-trace-waterfall.png
08-trace-metadata.png
09-prompt-versions.png
10-prompt-rollback.png
11-dashboard-overview.png
12-incident-metric.png
13-incident-log.png
14-incident-trace.png
```

Có thể dùng `.txt` cho output của tests/validators. Có thể tách dashboard thành nhiều ảnh nếu một ảnh không đọc rõ.

Ảnh `04`, `05`, `13` lấy từ terminal hoặc `data/logs.jsonl`. Ảnh `06`–`10`, `14` lấy từ project Langfuse cá nhân `day13-k4-l3a-<MSSV>` và nên nhìn thấy tên project. Không mở/chụp trang API Keys.

Từ `submission/REPORT.md`, dẫn ảnh bằng đường dẫn tương đối:

```markdown
![Trace waterfall](evidence/07-trace-waterfall.png)
```

Không commit secret, API key, PII thô hoặc evidence của học viên/lớp khác.

## CP2 đã xuất

- 03-dashboard-validator.txt: kết quả 6/6.
- 06–10 (*.json): dữ liệu thật từ Langfuse V2 API; chứa trace IDs, span tree, metadata và prompt versions/rollback.
- 11-dashboard-overview.html / .png: snapshot runtime đọc logs JSONL.
- Chạy `.venv/bin/python scripts/export_langfuse_evidence.py` để đọc lại evidence, không đổi prompt labels.
- Bổ sung ảnh UI Langfuse 06–10 từ project cá nhân theo rubric. Filter session `cp2-7cc64389c7`; trace IDs được liệt kê trong 06-trace-list.json. Không chụp API Keys.

## CP3

- 12-incident-metric.png/.html/.json: so sánh metrics baseline/incident/recovery từ log thật trong từng khoảng UTC.
- 13-incident-log.png/.html/.txt: trích log thật của correlation ID đại diện.
- 14-incident-trace.json: observations thật từ Langfuse V2 API, đã loại metadata chứa key/secret.
- cp3-phases.json: ranh giới thời gian và snapshots /metrics tích lũy.
- cp3-*-workload.txt: output chạy query chính thức với concurrency 5.
- cp3-*-control.txt: enable/disable incident.
- scripts/export_cp3_evidence.py đọc lại evidence từ logs và API, không inject hoặc đổi challenge.
