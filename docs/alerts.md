# Alert runbook — Day 13 Monitoring & LLMOps

Ba alert dưới đây gửi tới Slack `#day13-llmops-alerts`. Khi nhận alert, ghi lại UTC start/end, dashboard time range và correlation ID đại diện trước khi thay đổi hệ thống.

## Alert 1 — User-facing latency is above the SLO

- **Severity / duration:** Warning, P95 latency trên 3.000 ms liên tục 5 phút.
- **Ảnh hưởng:** Người dùng phải chờ lâu hoặc request hết thời gian chờ.
- **Kiểm tra:**
  1. Mở panel latency, đối chiếu P50/P95/P99 và TTFT P95 trong cùng 60 phút.
  2. Lọc `response_sent` theo khoảng thời gian, chọn request có latency cao và lấy `correlation_id`.
  3. Mở trace cùng ID, so thời lượng span `retrieval` với `llm-generation`.
- **Mitigation:** Giảm tải bằng cách giới hạn concurrency; nếu generation tăng sau lần đổi prompt gần nhất, rollback label `production` về version ổn định. Nếu retrieval chiếm thời gian, chuyển tạm sang câu trả lời fallback và kiểm tra nguồn dữ liệu.
- **Phục hồi khi:** P95 dưới 3.000 ms liên tục 10 phút và không còn nhóm request chậm mới.
- **Owner:** `llmops-oncall`.

## Alert 2 — Chat request error rate is elevated

- **Severity / duration:** Critical, error rate trên 2% liên tục 5 phút.
- **Ảnh hưởng:** Một phần request không trả được câu trả lời thành công.
- **Kiểm tra:**
  1. Đọc error rate và breakdown theo `error_type` trên panel errors.
  2. Lọc `request_failed` trong log, kiểm tra `tool_success` và ghi correlation ID.
  3. Mở trace cùng ID để xác định observation nào kết thúc ở trạng thái lỗi.
- **Mitigation:** Rollback thay đổi vừa phát hành nếu lỗi bắt đầu sau release; nếu retrieval lỗi, bật fallback answer; nếu lỗi tập trung ở generation, giới hạn request mới và khôi phục cấu hình/model hoạt động gần nhất.
- **Phục hồi khi:** Error rate dưới 2% liên tục 10 phút và request mới có `response_sent`.
- **Owner:** `llmops-oncall`.

## Alert 3 — Retrieval success is below the guardrail

- **Severity / duration:** Warning, retrieval success dưới 90% liên tục 5 phút.
- **Ảnh hưởng:** Câu trả lời có thể thiếu ngữ cảnh hoặc phải dùng fallback.
- **Kiểm tra:**
  1. Mở panel errors và xem retrieval success cùng error breakdown.
  2. Lọc log `request_failed` có `tool_name=retrieval` và `tool_success=false`.
  3. Mở trace theo correlation ID để kiểm tra span `retrieval` và thời điểm lỗi.
- **Mitigation:** Chuyển tạm sang câu trả lời fallback có thông báo thiếu dữ liệu; kiểm tra trạng thái nguồn/vector index và khôi phục kết nối hoặc index gần nhất đã biết hoạt động.
- **Phục hồi khi:** Retrieval success từ 90% trở lên liên tục 10 phút và lỗi mới không còn tăng.
- **Owner:** `llmops-oncall`.
