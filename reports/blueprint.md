# CI/CD Blueprint: RAG Eval và Guardrail Stack

**Sinh viên:** Chưa cung cấp
**Ngày:** Chưa ghi nhận
**Trạng thái số liệu:** PENDING, chờ `reports/ragas_50q.json`, `reports/judge_results.json` và `reports/guard_results.json` được tạo bởi phase tương ứng.

---

## Guard Stack Architecture

```text
User Input
    |
    v
[Presidio PII Scan]
    | block: VN_CCCD, VN_PHONE, EMAIL
    | action: HTTP 400, không chuyển input vào RAG
    v
[NeMo Input Rail]
    | block: off-topic, jailbreak, prompt injection
    | action: từ chối an toàn, không gọi RAG
    v
[RAG Pipeline]
    | M1 Chunk -> M2 Search -> M3 Rerank -> answer model
    v
[NeMo Output Rail]
    | flag: PII hoặc sensitive content trong response
    | action: thay bằng safe response
    v
User Response
```

**Ranh giới tin cậy:** Input chỉ được coi là hợp lệ sau PII scan và input rail. Output rail kiểm tra lần cuối trước khi trả response. Mọi quyết định block hoặc replace cần được ghi log bằng loại rail, rule, request id và latency, không ghi raw PII.

---

## Latency Budget

Số liệu dưới đây là **budget thiết kế**, không phải measurement. Giá trị thực tế phải lấy từ `reports/guard_results.json` và đối chiếu với `measure_p95_latency()`.

| Layer | P50 (ms) | P95 (ms) | P99 (ms) | Budget |
|---|---:|---:|---:|---:|
| Presidio PII | PENDING | PENDING | PENDING | <10 ms |
| NeMo Input Rail | PENDING | PENDING | PENDING | <300 ms |
| RAG Pipeline | PENDING | PENDING | PENDING | <2000 ms |
| NeMo Output Rail | PENDING | PENDING | PENDING | <300 ms |
| **Total Guard** | PENDING | **PENDING** | PENDING | **<500 ms** |

**Budget OK:** PENDING, chỉ kết luận sau live measurement.

**Cách kết luận:** Total Guard đạt nếu P95 total <500 ms. Nếu vượt, xác định layer có P95 lớn nhất trong report. Tối ưu theo evidence, ví dụ giảm payload hoặc cache PII cho Presidio, giảm network round trip cho NeMo, hoặc tối ưu retrieval và rerank cho RAG. Không dùng giá trị ước lượng thay cho measurement.

---

## CI/CD Gates

Các gate chạy trước merge. Tên lệnh là contract của lab, còn threshold phải được version-control cùng workflow.

```yaml
- name: RAGAS Quality Gate
  run: python src/phase_a_ragas.py
  env:
    MIN_FAITHFULNESS: 0.75
    MIN_AVG_SCORE: 0.65

- name: Guardrail Gate
  run: pytest tests/test_phase_c.py -k "test_adversarial_suite_pass_rate"
  # Pass tối thiểu 15/20, tương đương 75%

- name: Latency Gate
  run: python -c "from src.phase_c_guard import measure_p95_latency; ..."
  # P95 total phải < 500 ms
```

**Gate evidence cần lưu:** exit code, commit SHA, test set version, model/config version, report JSON và timestamp. Không merge nếu report thiếu trường bắt buộc hoặc dùng fallback mà không gắn nhãn offline.

---

## Monitoring Dashboard, production

| Metric | Alert threshold | Action |
|---|---|---|
| RAGAS faithfulness, daily sample | <0.70 | Triage sample, kiểm tra grounding và page on-call nếu lỗi xác nhận |
| Adversarial block rate | <80% | Review attack patterns, thêm regression case |
| Guard P95 latency | >600 ms | Trace layer chậm nhất, scale hoặc tối ưu sau khi có trace |
| PII detected count | Spike >10/hour | Security review, kiểm tra rule drift, không đưa raw PII vào dashboard |
| Report freshness | Quá một chu kỳ đánh giá | Chặn publish dashboard, chạy lại phase |

Threshold trên là **policy target**, không phải kết quả của lab. Dashboard phải phân biệt `offline_fallback` và `live_model`.

---

## Kết quả thực tế từ Lab

| Chỉ số | Kết quả | Nguồn và trạng thái |
|---|---:|---|
| RAGAS avg_score, 50 câu | PENDING | `reports/ragas_50q.json`, chưa có |
| Worst metric | PENDING | `per_distribution` hoặc `bottom_10`, chưa có |
| Dominant failure distribution | PENDING | `failure_clusters`, chưa có |
| Cohen's kappa | PENDING | `reports/judge_results.json`, chưa có |
| Adversarial pass rate | PENDING / 20 | `reports/guard_results.json`, chưa có |
| Guard P95 latency | PENDING ms | `measure_p95_latency()`, chưa có |

**Offline facts đã xác nhận:** test set định nghĩa 20 factual, 20 multi-hop và 10 adversarial. Human labels có 10 câu, gồm 5 label đúng và 5 label sai theo file nhãn. Đây không phải measurement của model hoặc guard.

---

## Nhận xét và Cải tiến

Hiện chưa có report JSON nên chưa thể kết luận chất lượng, bias hoặc latency thực tế. Sau khi phase chạy xong, failure cluster sẽ quyết định ưu tiên giữa retrieval, reranking và prompt grounding. Production cần giữ version policy, model, prompt và test set cùng report để kết quả tái lập được. Guard phải fail closed ở input độc hại, redact log, và có regression test cho từng rule đã từng block sai hoặc bỏ sót.

---

## Quy trình điền report

1. Chạy Phase A, kiểm tra `total_questions`, ba distribution và `bottom_10`.
2. Chạy Phase B, điền pairwise, swap consistency, kappa và verbosity từ JSON.
3. Chạy Phase C, điền pass rate và latency từ report, không dùng target budget làm số đo.
4. Chạy `python check_lab.py` và `pytest tests/ -q`.
5. Nếu input còn thiếu, giữ `PENDING` và ghi rõ file hoặc lệnh cần tạo input.
