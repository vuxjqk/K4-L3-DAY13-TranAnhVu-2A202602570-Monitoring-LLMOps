# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Trần Anh Vũ
- **MSSV:** 2A202602570
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/vuxjqk/K4-L3-DAY13-TranAnhVu-2A202602570-Monitoring-LLMOps
- **Commit SHA cuối:** `031219ca57b7762aa941443f1bb106569f7a0e36` (commit chứa toàn bộ source và evidence; commit ngay sau chỉ ghi SHA này vào report. SHA nộp LMS là HEAD trên `main` sau khi push)
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602570`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn | Ghi chú |
|---|---|---|
| Baseline log validator | [evidence/00-baseline-validate-logs.txt](evidence/00-baseline-validate-logs.txt) | CP0, trước khi sửa code |
| Pytest cuối | [evidence/01-pytest.txt](evidence/01-pytest.txt) | 31 passed |
| Log validator | [evidence/02-log-validator.txt](evidence/02-log-validator.txt) | 100/100 |
| Dashboard validator | [evidence/03-dashboard-validator.txt](evidence/03-dashboard-validator.txt) | 6/6 panel |
| Structured log | [evidence/04-structured-log.jsonl](evidence/04-structured-log.jsonl) | log `req-8e311a56` |
| PII redaction | [evidence/05-pii-redaction.txt](evidence/05-pii-redaction.txt) | input PII giả → log đã che email/điện thoại/CCCD/thẻ |
| Trace list | [evidence/06-trace-list.png](evidence/06-trace-list.png) | Langfuse, project cá nhân |
| Trace waterfall | [evidence/07-trace-waterfall.png](evidence/07-trace-waterfall.png) | trace `c4805a73ae932e8e191f1e040efb8322` |
| Trace metadata | [evidence/08a-trace-metadata.png](evidence/08a-trace-metadata.png), [evidence/08b-trace-metadata.png](evidence/08b-trace-metadata.png) | 08a: root metadata (correlation_id, prompt name/label/version); 08b: generation (model, Prompt day13-chat v2, 138 tokens, $0.001542). Dòng public key do SDK tự thêm đã được che |
| Prompt versions | [evidence/09-prompt-versions.png](evidence/09-prompt-versions.png) | `day13-chat` v1/v2 |
| Prompt rollback | [evidence/10a-prompt-promote.png](evidence/10a-prompt-promote.png), [evidence/10b-prompt-rollback.png](evidence/10b-prompt-rollback.png) | 10a: `production` ở v2 sau promote; 10b: `production` về v1 sau rollback |
| Dashboard runtime | [evidence/11-dashboard-overview.png](evidence/11-dashboard-overview.png) | 6 panel, gồm practice `rag_slow` |
| Incident metric | [evidence/12-incident-metric.png](evidence/12-incident-metric.png) | dashboard sau challenge |
| Incident log | [evidence/13-incident-log.jsonl](evidence/13-incident-log.jsonl) | 5 request `monitoring` |
| Incident trace | [evidence/14-incident-trace.txt](evidence/14-incident-trace.txt), [evidence/14-incident-trace.png](evidence/14-incident-trace.png) | trace `e8bdcbad5eb1fa2c365cd19efe0020c2`: span `retrieval` 2.50 s / 2.66 s, `correlation_id=req-8e311a56` |
| Incident recovery | [evidence/15-incident-recovery.txt](evidence/15-incident-recovery.txt) | sau khi tắt incident |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 (thiếu correlation ID + enrichment) | 100/100 | 184 record, 85 correlation ID duy nhất, 0 record thiếu field |
| `validate_dashboard.py` | HỢP LỆ: 6/6 panel | HỢP LỆ: 6/6 panel | Dashboard runtime dựng bằng `scripts/build_dashboard.py` |
| `pytest` | 22 passed | 31 passed | Thêm test PII (CCCD, thẻ, passport) và test correlation/enrichment |
| Số traces hợp lệ | root observation, không có child | 70 trace ID trong log (root + retrieval + generation) | Mỗi trace có `correlation_id` trong metadata |
| Số PII leak | 0 (message preview đã qua `summarize_text`) | 0 | Scrubber chạy trên mọi field trước khi ghi file |
| Latency P95 / TTFT P95 | 7359 ms ở request đầu tiên của CP0 (cold start), chưa có percentile | Bình thường: P95 1487 ms / TTFT P95 50 ms; khi có `rag_slow`: P95 2656 ms / TTFT P95 51 ms | rag_slow đẩy P95 từ ~1.5 s lên ~2.6 s |
| Retrieval success rate | chưa đo | 100% | Không bật `tool_fail`; challenge là `rag_slow` (chậm chứ không lỗi) |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `CorrelationIdMiddleware` gọi `clear_contextvars()` đầu mỗi request, nhận `x-request-id` nếu đúng format `req-<8-hex>` (ngược lại sinh mới bằng `uuid4`), `bind_contextvars(correlation_id=...)`, lưu vào `request.state` để truyền sang agent/trace metadata, và trả lại qua header `x-request-id` cùng `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** `ts`, `level`, `service`, `event`, `correlation_id`, `user_id_hash` (SHA-256 rút gọn, không ghi user_id thô), `session_id`, `feature`, `model`, `env`; log `response_sent` thêm `latency_ms`, `ttft_ms`, `tokens_in/out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`.
- **Cách bảo đảm PII được scrub trước khi ghi:** processor `scrub_event` được đăng ký sau `merge_contextvars`/`TimeStamper` và trước `JsonlFileProcessor`/`JSONRenderer`; nó duyệt đệ quy mọi field (kể cả payload lồng nhau). Pattern gồm email, thẻ thanh toán, CCCD 12 số, điện thoại VN (0/+84, có dấu cách/chấm/gạch) và hộ chiếu VN; thẻ được xử lý trước CCCD/điện thoại để tránh match một phần.
- **Cách kiểm chứng kết quả:** lưu baseline, đổi tên log cũ thành `data/logs.baseline.jsonl`, khởi động lại API, chạy `load_test.py` + một request chứa email/điện thoại → `validate_logs.py` đạt 100/100; `evidence/05-pii-redaction.txt` gửi input PII giả đủ 4 loại và cho thấy log ghi `[REDACTED_EMAIL]`, `[REDACTED_PHONE_VN]`, `[REDACTED_CCCD]`, `[REDACTED_CREDIT_CARD]`; grep giá trị thô trong `data/logs.jsonl` ra 0; test tự động nằm trong `tests/test_pii.py` và `tests/test_correlation_logging.py`.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** key trong `.env` thuộc project `day13-k4-l3a-2A202602570`; mỗi dòng log `response_sent` ghi `trace_id` do SDK trả về, và truy vấn `GET /api/public/v2/observations?traceId=...` bằng key của project trả đúng observation có cùng `correlation_id`.
- **Cấu trúc root/retrieval/generation observations:** `lab-agent-run` (agent, root) → `retrieval` (retriever, output `doc_count`, metadata `retrieval_ms`, level ERROR khi retrieval lỗi) và `llm-generate` (generation, `model=claude-sonnet-4-5`, link prompt managed, `usage_details` input/output, `cost_details` input/output, metadata `ttft_ms`). Input/output chỉ gửi preview đã scrub PII, không gửi raw prompt.
- **Cách nối trace với log:** `correlation_id` được đưa vào trace metadata qua `propagate_attributes` (xuất hiện trên mọi observation); ngược lại log `response_sent` có field `trace_id`. Từ log lấy `trace_id` mở thẳng trace, hoặc lọc trace theo metadata `correlation_id`.
- **Prompt name:** `day13-chat` (tạo bằng `scripts/manage_prompts.py create`)
- **Version/label baseline:** version 1, labels `baseline`, `production` — template gốc (Feature/Docs/Question).
- **Version/label candidate:** version 2, label `candidate` — thêm dòng yêu cầu trả lời tối đa 3 câu ngắn, chỉ dùng docs.
- **Trace ID của mỗi version:** cùng input `What is your refund policy?`:
  - `baseline` (v1): `req-0000b011` → trace `c2567cf1575eee9ea6e5e3bf1daa2de5` (tokens_in 28)
  - `candidate` (v2): `req-0000c012` → trace `c4805a73ae932e8e191f1e040efb8322` (tokens_in 44, generation link `day13-chat` v2)
  - `production` sau promote (v2): `req-0000d013` → trace `553939a3341ec4c99e9fae4eb900fccf` (tokens_in 44)
  - `production` sau rollback (v1): `req-0000e014` → trace `ee7a872e296bb97e6bbe48197c823590` (tokens_in 28)
- **Cách promote và rollback `production`:** `python scripts/manage_prompts.py promote` gọi `update_prompt(version=2, new_labels=["production"])` (Langfuse tự gỡ label khỏi v1); `rollback` gán lại `production` cho version mang label `baseline` (v1). App không cần deploy lại vì đọc prompt theo label (cache TTL 60 s). tokens_in đổi 28 → 44 → 28 chứng minh prompt thực sự đổi.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** `python scripts/build_dashboard.py [--watch]` đọc `data/logs.jsonl` + `config/dashboard.yaml`, sinh `data/dashboard.html` (time range 60 phút, auto refresh 30 s) với 6 panel: Latency (P50/P95/P99 + TTFT P95, threshold 3000 ms), Traffic (count, req/phút), Errors (error rate %, breakdown `error_type`, retrieval success %), Cost (theo phút + tổng), Tokens (in/out), Quality (mean ≥ 0.75). Ảnh: `evidence/11-dashboard-overview.png`. Kiểm tra runtime với `rag_slow`: P95 tăng từ ~1.5 s lên ~2.6 s; request chậm nhất `req-e5fd2d1b` (2656 ms) → trace `883bdf0d859d437f84ed50dd1731f935`.
- **SLO và lý do chọn:** `fast_successful_requests`: 99.5% request trả `response_sent` với `latency_ms ≤ 3000` trong cửa sổ 28 ngày. Traffic bình thường P99 ≈ 1.5 s nên 3000 ms là ngưỡng gấp đôi, ít báo động giả; 99.5% thay vì 99.9% vì phụ thuộc RAG/LLM ngoài có tail latency lớn (chi tiết trong `config/slo.yaml`).
- **Cách tính error budget:** budget = 1 − 99.5% = 0.5% số request trong 28 ngày (ví dụ 10 000 request → tối đa 50 request lỗi hoặc > 3000 ms), tương đương 0.5% × 28 × 24 h = 3.36 giờ hỏng hoàn toàn. Burn rate = tỉ lệ request xấu trong cửa sổ / 0.005.
- **Ba alert và runbook tương ứng:** (1) `HighLatencyP95` P2 — P95 > 3000 ms trong 5m; (2) `HighErrorRateOrRetrievalFailure` P1 — error rate > 2% hoặc retrieval success < 90% trong 5m; (3) `CostPerRequestSpike` P3 — cost/request > 0.004 USD hoặc cost dự phóng/ngày > 2.5 USD trong 15m. Tất cả gửi Slack (`#day13-llmops-alerts` / `#day13-llmops-critical`), owner `llmops-oncall`, runbook ở `docs/alerts.md#alert-1..3`.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (cohort K4, seed 1311, `affected_feature=monitoring`, `latency_threshold_ms=2000`)
- **Khoảng thời gian điều tra:** 2026-09-29 08:29:04Z → 08:29:19Z (15:29:04 → 15:29:19 UTC+7). Mốc so sánh: traffic bình thường ngay trước đó (08:28–08:29Z) và lần chạy lại sau khi xử lý (08:30:31Z).
- **Triệu chứng từ metrics:** panel Latency tăng vọt: 5/5 request `feature=monitoring` có `latency_ms` 2655–2656 ms (P50 = P95 = P99 = 2656 ms, vượt ngưỡng challenge 2000 ms), trong khi ngay trước đó P95 là 156 ms. **TTFT P95 không đổi (50 → 51 ms)**, error rate 0%, retrieval success 100%, tokens/cost không đổi (`tokens_out` TB 112 → 124, cost TB 0.00178 → 0.00196 USD). Vậy phần chậm nằm trước khi LLM sinh token đầu, không phải lỗi hay cost. Phía client mỗi request mất khoảng 13.3 s vì request bị xếp hàng (xem Root cause).
- **Log line và correlation ID liên quan:** `evidence/13-incident-log.jsonl`, ví dụ:
  ```json
  {"event": "response_sent", "correlation_id": "req-8e311a56", "trace_id": "e8bdcbad5eb1fa2c365cd19efe0020c2", "feature": "monitoring", "session_id": "k4-l3a-challenge-s04", "latency_ms": 2656, "ttft_ms": 51, "tool_name": "retrieval", "tool_success": true}
  ```
  Các correlation ID khác: `req-c8907cb9`, `req-224c182b`, `req-616e1d71`, `req-6ac752cc`.
- **Trace ID và span gây ảnh hưởng:** trace `e8bdcbad5eb1fa2c365cd19efe0020c2` (`correlation_id=req-8e311a56`): `lab-agent-run` 2657 ms = **`retrieval` (retriever) 2503 ms, metadata `retrieval_ms=2500`** + `llm-generate` 153 ms (bắt đầu ở +2504 ms, `ttft_ms=51`, prompt v1). Trace bình thường `e80ff986975d12e8cdccc868328cf87e` (`req-fd21af12`): `retrieval` 0 ms, `llm-generate` 155 ms, cùng prompt v1. Span retrieval chiếm khoảng 94% latency, generation và prompt không đổi (`evidence/14-incident-trace.txt`).
- **Root cause:** bước RAG retrieval bị chậm (incident `rag_slow`: vector store/retriever thêm khoảng 2.5 s mỗi lần gọi). Metric, log và trace cùng chỉ về một chỗ: latency tăng nhưng TTFT, token, cost và prompt version không đổi, và span `retrieval` chiếm phần thời gian tăng thêm. Có thêm một yếu tố khuếch đại: endpoint `async def chat` gọi `agent.run` đồng bộ (blocking) nên chặn event loop. 5 request đồng thời bị xử lý tuần tự (response cách nhau khoảng 2.66 s), nên phía client thấy khoảng 13.3 s dù `latency_ms` mỗi request chỉ 2.66 s.
- **Fix action:** tắt nguồn gây chậm (`python scripts/inject_incident.py --disable`, tương ứng khôi phục hoặc failover vector store). Kiểm chứng: chạy lại đúng 5 query challenge thì `latency_ms` = 154 ms, 0/5 request vượt 2000 ms (`evidence/15-incident-recovery.txt`, ví dụ `req-3e109800` → trace `d0b64a600e1c66af90ce0ddd653739c9`).
- **Preventive measure:** (1) đặt timeout cho retrieval (ví dụ 800 ms) kèm fallback trả lời không dùng RAG, và đánh dấu span `retrieval` level WARNING khi timeout; (2) chạy phần agent blocking trong threadpool (`run_in_threadpool`) hoặc chuyển sang retriever async để một request chậm không chặn các request khác; (3) alert `HighLatencyP95` (P95 > 3000 ms/5m), thêm alert riêng cho `retrieval_ms` P95 > 1000 ms theo feature để bắt sớm trước khi vi phạm SLO; (4) theo dõi TTFT cùng latency để phân biệt nhanh chậm ở trước LLM (RAG) hay ở LLM.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** chỉ gửi preview đã scrub PII (`summarize_text`) làm input/output của observation thay vì raw prompt, và ghi ngược `trace_id` vào log `response_sent`. Prompt đã compile chứa nguyên văn câu hỏi của người dùng nên có thể lộ PII lên Langfuse; token/cost vẫn đầy đủ nhờ `usage_details`/`cost_details`. Ghi `trace_id` vào log giúp đi từ log sang trace chỉ bằng một ID (đã dùng ngay ở CP3).
- **Một lỗi/blocker đã gặp:** (1) Khi so sánh prompt v1/v2, cả 4 request có `tokens_in` = 28, nghĩa là label không có tác dụng. (2) API `GET /api/public/traces/{id}` trả HTTP 410 `LEGACY_API_UNAVAILABLE_FOR_NEW_ORGANIZATION`.
- **Cách tìm nguyên nhân và xử lý:** (1) Log uvicorn báo lỗi bind port 8000 do server `--reload` từ CP0 vẫn chạy, nên request đi vào server cũ đang dùng label `production`. Tôi chạy server thử nghiệm ở port 8001 riêng cho từng label; `tokens_in` đổi 28 → 44 → 44 → 28 đúng với v1/v2/promote/rollback. (2) Chuyển sang `GET /api/public/v2/observations?traceId=...`, API này trả đủ cây observation, duration và metadata.
- **Cách hiểu luồng Metrics → Logs → Traces:** metric (dashboard) cho biết *có vấn đề gì và từ lúc nào*: ở CP3 là P95 tăng lên 2656 ms trong khi TTFT, error và cost không đổi. Log cho biết *request nào bị ảnh hưởng*: lọc `latency_ms > 2000` ra `req-8e311a56` kèm `trace_id`. Trace cho biết *bước nào gây ra*: span `retrieval` 2503 ms trên tổng 2657 ms. Metric bao quát nhưng không chi tiết, trace chi tiết nhưng không biết nên mở cái nào; `correlation_id`/`trace_id` là cầu nối giữa hai tầng.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** prompt là "code" thay đổi được mà không cần deploy, nên mỗi trace phải ghi version để biết thay đổi hành vi đến từ đâu. Rollback bằng label giúp khôi phục trong vài giây (đã làm: `production` v2 → v1). Token/cost là tín hiệu riêng của LLM: prompt v2 tăng `tokens_in` 28 → 44 (+57%), phải thấy được trước khi promote. SLO và error budget quyết định khi nào được thử thay đổi và khi nào phải dừng lại để ưu tiên ổn định.
- **Điều quan trọng nhất đã học:** một kết luận incident chỉ đáng tin khi ba tín hiệu khớp nhau. Nhìn riêng latency sẽ dễ đoán do LLM chậm, nhưng TTFT không đổi cùng span `retrieval` chiếm 94% thời gian chứng minh nguyên nhân nằm ở RAG. Ngoài ra, latency đo trong server (2.66 s) có thể khác xa trải nghiệm client (13.3 s) nếu có hàng đợi.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** dashboard là HTML tĩnh sinh từ log (không phải Grafana); alert mới được định nghĩa trong YAML, chưa nối Slack thật; chưa sửa code để chạy `agent.run` trong threadpool và chưa thêm timeout cho retrieval (đang là preventive measure đề xuất); `quality_score` chỉ là heuristic.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [x] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
