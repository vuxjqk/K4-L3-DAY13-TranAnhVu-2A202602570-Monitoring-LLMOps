# Khung thiết kế Observability

Dùng khung này trước khi triển khai, sau đó chuyển kết quả cuối sang `submission/REPORT.md`.

## Người dùng và luồng chính

- Ai gửi request? Client gọi `POST /chat` với `user_id`, `session_id`, `feature`, `message` (trong lab là `scripts/load_test.py`).
- Request đi qua những thành phần nào? `CorrelationIdMiddleware` → endpoint `/chat` (FastAPI) → `LabAgent.run` → retrieval (`mock_rag.retrieve`) → resolve prompt từ Langfuse (`day13-chat`, theo label) → LLM (`FakeLLM.generate`) → response.
- Correlation ID được tạo và truyền ở đâu? Tạo/nhận trong middleware (`x-request-id`, format `req-<8-hex>`), bind vào structlog contextvars, lưu ở `request.state`, truyền sang agent và vào trace metadata qua `propagate_attributes`; trả lại client qua header `x-request-id`.

## Tín hiệu quan sát

| Thành phần | Log cần có | Metric cần có | Span cần có |
|---|---|---|---|
| API | `request_received`, `response_sent`, `request_failed` với `correlation_id`, `user_id_hash`, `session_id`, `feature`, `model`, `env`, `trace_id` | traffic (req/phút), error rate %, latency P50/P95/P99 | root `lab-agent-run` (agent) |
| Retrieval | `tool_name=retrieval`, `tool_success`, `error_type` khi lỗi | retrieval success %, `retrieval_ms` | `retrieval` (retriever), metadata `retrieval_ms`, level ERROR khi lỗi |
| LLM | `ttft_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `quality_score` | TTFT P95, tokens in/out, cost theo phút và tổng, quality mean | `llm-generate` (generation) với model, prompt version, usage, cost |

## SLO và alert

| SLI | Mục tiêu | Cửa sổ đo | Alert |
|---|---:|---|---|
| Latency P95 | 99.5% request thành công trong ≤ 3000 ms | 28 ngày | `HighLatencyP95` P2: P95 > 3000 ms trong 5m |
| Error rate | ≤ 2%, retrieval success ≥ 90% | 28 ngày | `HighErrorRateOrRetrievalFailure` P1: error > 2% hoặc retrieval < 90% trong 5m |
| Cost | ≤ 2.5 USD/ngày | 1 ngày | `CostPerRequestSpike` P3: > 0.004 USD/request hoặc dự phóng > 2.5 USD/ngày trong 15m |
| Quality | mean `quality_score` ≥ 0.75 | 60 phút | theo dõi trên dashboard (guardrail, chưa đặt alert riêng) |

## Rủi ro dữ liệu

- PII có thể xuất hiện ở đâu? Trong `message` người dùng gửi (email, số điện thoại, CCCD, thẻ, hộ chiếu), do đó cả prompt đã compile và câu trả lời; `user_id` cũng là định danh.
- Dữ liệu nào được phép ghi vào log? Chỉ preview đã scrub (`summarize_text`), `user_id_hash` thay cho `user_id`, và các số đo (latency, token, cost). Trace chỉ nhận preview đã scrub, không nhận raw prompt/output.
- Redaction diễn ra trước bước nào? Processor `scrub_event` chạy trước `JsonlFileProcessor` (ghi file) và `JSONRenderer`; preview gửi Langfuse đã qua `scrub_text` trước khi rời ứng dụng.
