# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.json`.

## 1. Thông tin học viên

- **Họ và tên:**
- **MSSV:**
- **Lớp:** K4-L3A
- **Repository URL:**
- **Commit SHA cuối:**
- **Challenge ID:**
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602955`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | `evidence/02-log-validator.txt` |
| Dashboard validator | `evidence/03-dashboard-validator.txt` |
| Structured log | `evidence/04-structured-log.txt` |
| PII redaction | `evidence/05-pii-redaction.txt` |
| Trace list | [Ảnh](evidence/06-trace-list.png), [API](evidence/06-trace-list.json) |
| Trace waterfall | [Ảnh](evidence/07-trace-waterfall.png), [API](evidence/07-trace-waterfall.json) |
| Trace metadata | [Generation usage](evidence/08-trace-metadata.png), [Correlation ID](evidence/08-correlation-id.png), [API](evidence/08-trace-metadata.json) |
| Prompt versions | [Ảnh](evidence/09-prompt-versions.png), [API](evidence/09-prompt-versions.json) |
| Prompt rollback | [Production v2](evidence/10-production-v2.png), [Sau rollback v1](evidence/10-prompt-rollback.png), [API](evidence/10-prompt-rollback.json) |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | [Ảnh](evidence/12-incident-metric.png), [Số liệu](evidence/12-incident-metric.json) |
| Incident log | [Ảnh](evidence/13-incident-log.png), [Log](evidence/13-incident-log.txt) |
| Incident trace | [Ảnh Langfuse](evidence/14-incident-trace.png), [API](evidence/14-incident-trace.json) |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 50/100 trên 42 dòng log đã lưu | 100/100 trên 93 dòng, 39 correlation ID | 20 dòng cũ thiếu trường CP1 đã được tách khỏi log trước khi đo lại |
| `validate_dashboard.py` | Chưa có runtime dashboard | 6/6 panel | Có runtime HTML và ảnh chụp sáu panel |
| `pytest` | Chưa chạy baseline | 5 bài test PII CP1 đạt | Chạy `tests/test_pii.py` |
| Số traces hợp lệ | Chỉ có root observation | 12 traces / 36 observations | Mỗi trace có AGENT → RETRIEVER + GENERATION |
| Số PII leak | 0 | 0 | Validator không phát hiện PII trong log |
| Latency P95 / TTFT P95 | | 786 ms / 55 ms | Snapshot rolling 60 phút, 22 requests |
| Retrieval success rate | | 100% | 22 requests trong snapshot; error rate 0% |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** Middleware giữ `x-request-id` hợp lệ theo dạng `req-<8-hex>`; nếu thiếu hoặc sai định dạng thì sinh ID mới. ID được bind vào structlog context, trả trong response header `x-request-id`, cùng thời gian xử lý ở `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** `user_id_hash` (SHA-256 rút gọn, không ghi raw user ID), `session_id`, `feature`, `model` và `env` được bind trước event `request_received`.
- **Cách bảo đảm PII được scrub trước khi ghi:** Processor chạy sau khi format exception và trước JSONL writer/JSON renderer; scrub đệ quy mọi chuỗi trong event, payload và metadata. Pattern che email, số điện thoại Việt Nam, CCCD 12 số và số thẻ 13–19 số.
- **Cách kiểm chứng kết quả:** `tests/test_pii.py` đạt 5/5; log validator đạt 100/100, với 0 trường bắt buộc thiếu, 10 correlation ID và 0 PII leak. TestClient xác nhận ID hợp lệ được giữ nguyên, ID sai định dạng được thay bằng ID hợp lệ, và response có hai header yêu cầu. Evidence: `evidence/02-log-validator.txt`, `evidence/04-structured-log.txt`, `evidence/05-pii-redaction.txt`.

## 5. Tracing và prompt versioning

- **Nguồn traces:** Workload tự chạy trong project gắn với keys cá nhân trong `.env`, session `cp2-7cc64389c7`; API Langfuse V2 trả 12 traces và 36 observations. Xem `evidence/06-trace-list.json`.
- **Cấu trúc:** Root `lab-agent-run` (AGENT), hai child `retrieval` (RETRIEVER) và `llm-generation` (GENERATION). Parent IDs được đối chiếu khi export. Generation gắn managed prompt, model, input/output tokens và chi phí USD; root không capture raw input/output. Các child chỉ ghi số ký tự, số tài liệu và metadata prompt.
- **Nối log:** `metadata.correlation_id` trên root trùng `correlation_id` trong JSONL; session ID và user hash cũng được truyền. Export đối chiếu đủ 12 IDs với logs.
- **Prompt:** `day13-chat`; v1 có label `baseline`, v2 có label `candidate`. Hai label được chạy cùng input: `Explain monitoring metrics and the request investigation flow.`
- **Baseline v1:** trace `5049f5af2f7837e84fbb2c3df7341afe`, correlation `req-3fffedd5`.
- **Candidate v2:** trace `28f879cf72dc084a3a329f355007dfc2`, correlation `req-a483043a`.
- **Promote:** `production` chuyển từ v1 sang v2; trace `6bc0575df6a149ff4c6a1a2808f04cea`, correlation `req-b70c7878`, được Langfuse liên kết prompt v2.
- **Rollback:** Chuyển `production` về v1; trace đầu sau rollback `203b9de5790c9cac4de87d808a4f7c6f`, correlation `req-7882d44d`. API xác nhận hiện tại `baseline=1`, `candidate=2`, `production=1`. Đặt cache TTL 0 để đổi label có hiệu lực ngay trong bài lab.
- **Evidence:** `evidence/07-trace-waterfall.json`, `evidence/08-trace-metadata.json`, `evidence/09-prompt-versions.json`, `evidence/10-prompt-rollback.json` là dữ liệu API thật. Đã lưu ảnh UI 06, 07, 09 và trạng thái sau rollback 10. Mục 08 gồm ảnh generation usage (model, prompt name/version/label, token/cost) và ảnh Log View bổ sung correlation ID `req-e7abd347`; root observation `b88149ad` khớp trace waterfall/API evidence. Đã lưu ảnh trace production v2 trước rollback ở `evidence/10-production-v2.png`.
- **Giới hạn:** LLM và retrieval dùng mock của starter; traces được ingest thật vào Langfuse. Token/cost là số liệu mô phỏng và ước tính, không phải hóa đơn provider.

## 6. Dashboard, SLO và alerts

- **Runtime:** `.venv/bin/python scripts/dashboard.py`, mở `http://127.0.0.1:8765`. Đọc `data/logs.jsonl`, rolling 60 phút, refresh 30 giây. Snapshot và ảnh: `evidence/11-dashboard-overview.html`, `evidence/11-dashboard-overview.png`.
- **Sáu panel:** latency P50/P95/P99 + TTFT P95 (ms); traffic tổng và theo phút; error rate + breakdown + retrieval success (%); cost tổng và theo phút (USD); input/output tokens; mean quality proxy (0–1). Mỗi panel có threshold và đơn vị. Validator: `evidence/03-dashboard-validator.txt`, đạt 6/6.
- **Snapshot:** 22 requests, P95 786 ms, TTFT P95 55 ms, error rate 0%, retrieval success 100%, cost $0.047190, 900 input + 2966 output tokens, quality trung bình 0.836.
- **SLO:** 99.5% requests thành công trong ≤3000 ms, cửa sổ rolling 28 ngày. Ngưỡng 3 giây dành dư địa so với workload lab hiện tại dưới 1 giây và phát hiện request chậm ảnh hưởng trải nghiệm; cần đánh giá lại với traffic thực.
- **Error budget:** 100% − 99.5% = 0.5%; với N requests cho phép N × 0.005 requests xấu, ví dụ 5/1000. Request lỗi hoặc thành công nhưng >3000 ms đều tiêu budget. Snapshot 60 phút không chứng minh đạt SLO 28 ngày.
- **Alerts:** P95 >3000 ms trong 5 phút (warning); error rate >2% trong 5 phút (critical); retrieval success <90% trong 5 phút (warning). Owner `llmops-oncall`, Slack channel `#day13-llmops-alerts`; ba runbook ở `docs/alerts.md#alert-1`, `#alert-2`, `#alert-3`. Đây là cấu hình lab; chưa triển khai alert engine hoặc tích hợp gửi Slack.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`, cohort K4/L3A, seed `1311`. Dùng nguyên file chính thức được cấp tại `config/challenge.json`, không thay đổi query/seed/incident. File được gitignore và không đưa vào evidence.
- **Cách chạy:** App có tracing chạy riêng ở cổng 8001 vì app cũ trên 8000 không bật tracing. Dùng `BASE_URL=http://127.0.0.1:8001 .venv/bin/python scripts/load_test.py --challenge --concurrency 5` cho cả baseline, incident và recovery. Inject bằng `scripts/inject_incident.py`, khắc phục bằng cùng lệnh thêm `--disable`.
- **Khoảng thời gian UTC:** baseline 09:47:24.780–09:47:28.251; incident 09:47:28.372–09:47:43.825; recovery 09:47:43.968–09:47:46.924 ngày 29/09/2026. Theo giờ Việt Nam: cộng 7 giờ, khoảng 16:47. Chi tiết ở `evidence/cp3-phases.json`.
- **Triệu chứng từ metrics:** Feature `monitoring`, 5 requests mỗi giai đoạn. P95 latency xử lý: baseline **1458 ms**, incident **3372 ms**, recovery **853 ms**. Trong incident **5/5 requests >2000 ms** (ngưỡng challenge); baseline và recovery 0/5. TTFT P95 54→55→55 ms, HTTP errors 0%, retrieval success 100%. Không thể dùng tỷ lệ thành công để kết luận retrieval không bị chậm. Evidence: `evidence/12-incident-metric.png` và `.json`.
- **Log line/correlation ID:** `response_sent` tại **2026-09-29T09:47:40.795693Z**, `correlation_id=req-a7eae60b`, `session_id=k4-l3a-challenge-s03`, `feature=monitoring`, `latency_ms=3372`, `ttft_ms=54`, `tool_name=retrieval`, `tool_success=true`. Log request_received/response_sent thật được trích trong `evidence/13-incident-log.txt` và ảnh `.png`.
- **Trace/span liên quan:** Trace **`ec779bdefc94672332ed8fc77ee6260b`** có cùng correlation ID. Root `lab-agent-run` **3373 ms**; retrieval **2506 ms**; generation **157 ms**. Retrieval chiếm khoảng **74.3%** thời lượng root; phần còn lại gồm fetch managed prompt và overhead, không quy toàn bộ thời gian cho retrieval. Nguồn: Langfuse V2 observations API; `evidence/14-incident-trace.json`. Truy cập [trace cá nhân](https://cloud.langfuse.com/project/cmumd4c8t1zpdad0cke1owi6g/traces/ec779bdefc94672332ed8fc77ee6260b).
- **Root cause:** Challenge bật `STATE['rag_slow']`. Trong `app/mock_rag.py`, `retrieve()` thực hiện `time.sleep(2.5)` trước tra cứu corpus. Trace retrieval đo khoảng 2.5 giây, generation vẫn khoảng 0.157 giây và TTFT ổn định. Đây là độ trễ retrieval được inject, không phải lỗi generation hay thiếu tài liệu.
- **Fix action đã thực hiện:** Tắt `rag_slow` qua endpoint disable bằng `scripts/inject_incident.py --disable`, giữ nguyên file challenge, rồi chạy lại cùng queries/seed/concurrency. Recovery P95 **853 ms**, 0/5 requests vượt ngưỡng; spans retrieval sau recovery được API ghi 0 ms ở độ phân giải millisecond. Evidence control/workload của ba giai đoạn nằm trong `evidence/cp3-*-control.txt`, `evidence/cp3-*-workload.txt`.
- **Preventive measure đề xuất:** Theo dõi latency riêng cho retrieval, bổ sung timeout/fallback cho truy xuất và phân tích P95 theo feature. Thêm phép đo thời gian toàn request, gồm queue wait, vì app hiện gọi thao tác đồng bộ trong async route; chuyển tác vụ blocking sang thread pool hoặc client async trước triển khai thực. Gắn correlation/session IDs để drill down từ metric tới log và trace. Các cải tiến production này chưa được triển khai trong bài mô phỏng.
- **Phân biệt số đo:** Client HTTP latency khi concurrency 5 khoảng 15.34 giây trong incident, cao hơn agent latency ~3 giây vì blocking và queue wait. Metrics JSONL đo từ đầu `agent.run`, không gồm toàn bộ thời gian chờ ở HTTP. TTFT chỉ đo trong generation, không gồm retrieval trước đó. `/metrics` là tích lũy toàn process nên P95 sau recovery vẫn chứa các request incident; recovery 853 ms tính riêng từ log trong đúng khoảng recovery, không xóa log lỗi.
- **Giới hạn:** Incident chỉ kéo dài khoảng 15 giây, không chứng minh alert duration 5 phút đã kích hoạt hoặc đạt SLO rolling 28 ngày. Tạo **15 traces / 45 observations** thật cho ba giai đoạn. Ảnh UI Langfuse `evidence/14-incident-trace.png` hiển thị đúng project, trace ID, correlation ID `req-a7eae60b`, root 3.37 s, retrieval 2.51 s và generation 157 ms; khớp API evidence ở độ làm tròn của UI.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
- **Một lỗi/blocker đã gặp:** API trace legacy trả 410 cho organization mới.
- **Cách tìm nguyên nhân và xử lý:** Dùng observations API V2 với filter session/time và chọn field groups metadata/io/model/usage/prompt.
- **Cách hiểu luồng Metrics → Logs → Traces:**
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
- **Điều quan trọng nhất đã học:**
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** CP2 có API evidence, ảnh dashboard và ảnh UI 06/07/09/10 sau rollback; mục 08 có thêm ảnh correlation ID; đã có ảnh production v2 trước rollback trong thư mục evidence. CP3 đã chạy challenge chính thức, xác định retrieval chậm, kiểm chứng recovery và lưu đủ evidence 12–14.

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
