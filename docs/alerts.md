# Alert và Runbook

Mỗi alert dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ. Quy trình chung: **Metrics → Logs → Traces**. Dashboard: `python scripts/build_dashboard.py` → `data/dashboard.html`.

## Alert 1

- Tên: `HighLatencyP95`
- Severity: P2
- Duration: 5m
- Kênh thông báo: Slack `#day13-llmops-alerts`
- SLI/SLO liên quan: `fast_successful_requests` (99.5% request thành công trong ≤ 3000 ms, cửa sổ 28 ngày)
- Điều kiện và thời gian duy trì: P95 `latency_ms` của `response_sent` > 3000 ms liên tục 5 phút.
- Ảnh hưởng tới người dùng: câu trả lời chậm, client có thể timeout; mỗi request > 3000 ms tiêu error budget.
- Ba bước kiểm tra đầu tiên:
  1. Panel **Latency**: P95/P99 tăng từ lúc nào; TTFT P95 có tăng theo không (TTFT ổn định → chậm trước bước LLM).
  2. Lọc log chậm: `event == "response_sent" and latency_ms > 3000`, lấy `correlation_id` và `trace_id`.
  3. Mở trace trên Langfuse, so sánh thời lượng span `retrieval` với `llm-generate` (metadata `retrieval_ms`, `ttft_ms`).
- Mitigation tạm thời: nếu span `retrieval` chậm → giảm top-k/timeout retrieval, bật cache hoặc trả fallback answer; nếu `llm-generate` chậm → chuyển model nhỏ hơn hoặc rollback prompt label `production` về version trước.
- Owner: llmops-oncall (Trần Anh Vũ)

## Alert 2

- Tên: `HighErrorRateOrRetrievalFailure`
- Severity: P1
- Duration: 5m
- Kênh thông báo: Slack `#day13-llmops-critical`
- SLI/SLO liên quan: `fast_successful_requests`; guardrail `error_rate_pct_max: 2`, `retrieval_success_rate_pct_min: 90`
- Điều kiện và thời gian duy trì: error rate > 2% hoặc retrieval success < 90% liên tục 5 phút.
- Ảnh hưởng tới người dùng: request trả HTTP 500, người dùng không nhận được câu trả lời; burn error budget nhanh nhất.
- Ba bước kiểm tra đầu tiên:
  1. Panel **Errors**: xem `error_type` breakdown và đường retrieval success.
  2. Lọc log `event == "request_failed"`, đọc `error_type`, `tool_name`, `payload.detail`, lấy `correlation_id`.
  3. Mở trace cùng `correlation_id`: span `retrieval` có level `ERROR` và `status_message` hay lỗi ở `llm-generate`.
- Mitigation tạm thời: retrieval lỗi (ví dụ `Vector store timeout`) → failover sang index dự phòng hoặc trả câu trả lời fallback không dùng RAG; lỗi sau khi deploy/đổi prompt → rollback deploy hoặc label `production`.
- Owner: llmops-oncall (Trần Anh Vũ)

## Alert 3

- Tên: `CostPerRequestSpike`
- Severity: P3
- Duration: 15m
- Kênh thông báo: Slack `#day13-llmops-alerts`
- SLI/SLO liên quan: guardrail `daily_cost_usd_max: 2.5`
- Điều kiện và thời gian duy trì: cost trung bình mỗi request > 0.004 USD (≈ 2× baseline 0.00196 USD) hoặc cost dự phóng theo ngày > 2.5 USD, duy trì 15 phút.
- Ảnh hưởng tới người dùng: không lỗi trực tiếp nhưng vượt ngân sách, câu trả lời thường dài bất thường (chậm hơn, khó đọc).
- Ba bước kiểm tra đầu tiên:
  1. Panel **Cost** và **Tokens**: cost tăng do `tokens_out` hay `tokens_in`; traffic có tăng tương ứng không.
  2. Lọc log `response_sent` có `tokens_out` cao nhất, kiểm tra `feature`, `model`, lấy `correlation_id`.
  3. Mở trace: generation `llm-generate` xem usage/cost và prompt version được link (có vừa promote prompt mới không).
- Mitigation tạm thời: đặt `max_tokens` cho generation, rollback prompt `production` về version trước, hoặc route feature tốn kém sang model rẻ hơn.
- Owner: llmops-oncall (Trần Anh Vũ)
