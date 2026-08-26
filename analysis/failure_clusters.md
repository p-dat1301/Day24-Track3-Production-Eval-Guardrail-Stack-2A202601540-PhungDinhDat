# Failure Cluster Analysis, Phase A

**Sinh viên:** Chưa cung cấp
**Ngày:** Chưa ghi nhận
**Trạng thái:** PENDING, chưa có `reports/ragas_50q.json`. Không suy ra score từ ground truth hoặc test set.

---

## 1. Aggregate RAGAS Scores theo Distribution

| Metric | factual | multi_hop | adversarial |
|---|---:|---:|---:|
| faithfulness | PENDING | PENDING | PENDING |
| answer_relevancy | PENDING | PENDING | PENDING |
| context_precision | PENDING | PENDING | PENDING |
| context_recall | PENDING | PENDING | PENDING |
| **avg_score** | **PENDING** | **PENDING** | **PENDING** |

**Cách điền:** lấy trực tiếp từ `per_distribution`. `count` phải lần lượt là 20, 20 và 10. Không thay PENDING bằng target threshold.

---

## 2. Bottom 10 Questions

Nguồn duy nhất: `reports/ragas_50q.json`, key `bottom_10`. Danh sách phải sort tăng dần theo `avg_score`.

| Rank | Question ID | Distribution | Question | avg_score | worst_metric | Diagnosis | Suggested fix |
|---:|---:|---|---|---:|---|---|---|
| 1 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| 2 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| 3 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| 4 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| 5 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| 6 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| 7 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| 8 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| 9 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| 10 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |

**Diagnosis map:** `faithfulness` = hallucinating; `answer_relevancy` = answer không khớp câu hỏi; `context_precision` = nhiều chunk không liên quan; `context_recall` = thiếu chunk liên quan. Suggested fix phải lấy từ `failure_clusters` hoặc ghi rõ bằng chứng câu hỏi và context.

---

## 3. Failure Cluster Matrix

Mỗi ô = số câu có `worst_metric` bằng row và `distribution` bằng column. Nguồn: `failure_clusters.matrix` trong report.

| worst_metric | factual | multi_hop | adversarial | Total |
|---|---:|---:|---:|---:|
| faithfulness | PENDING | PENDING | PENDING | PENDING |
| answer_relevancy | PENDING | PENDING | PENDING | PENDING |
| context_precision | PENDING | PENDING | PENDING | PENDING |
| context_recall | PENDING | PENDING | PENDING | PENDING |
| **Total** | **PENDING** | **PENDING** | **PENDING** | **50** |

**Kiểm tra:** tổng matrix phải bằng 50, nếu phase chạy đủ 50 kết quả. Tie metric cần theo quy tắc của phase, không tự đếm lại bằng mắt.

---

## 4. Dominant Failure Analysis

**Dominant distribution:** PENDING
**Dominant metric:** PENDING

**Bằng chứng cần ghi:** distribution hoặc metric có count lớn nhất trong matrix. Nếu có hòa, ghi rõ hòa và dùng avg score để ưu tiên điều tra. Không gọi một cluster là dominant khi chưa có JSON.

> Chưa thể kết luận nguyên nhân khi Phase A chưa chạy. Sau khi có report, đối chiếu bottom 10 với question, answer và contexts. Với factual, kiểm tra version policy và câu trả lời trực tiếp. Với multi_hop, kiểm tra đủ chunk và phép tính. Với adversarial, kiểm tra phủ định và xung đột v2023, v2024. Chỉ gán nguyên nhân khi có evidence từ case cụ thể.

---

## 5. Suggested Fixes

| Metric yếu | Root cause cần xác nhận | Suggested fix sau khi có evidence |
|---|---|---|
| faithfulness | Answer có claim không nằm trong context | Ép answer chỉ dùng evidence, thêm citation hoặc giảm temperature; thêm regression case |
| context_recall | Relevant policy chunk không xuất hiện | Điều chỉnh chunking, query expansion hoặc thêm BM25; kiểm tra metadata version |
| context_precision | Retrieval trả nhiều chunk không liên quan | Tăng reranking quality, metadata filter và threshold retrieval |
| answer_relevancy | Answer bỏ sót intent hoặc trả lan man | Chỉnh prompt theo question type, yêu cầu trả đúng trường thông tin cần hỏi |

Các đề xuất là remediation hypotheses, không phải kết quả đo. Mỗi fix cần được xác nhận bằng test case trước và sau.

---

## 6. Nhận xét về Adversarial Distribution

**So sánh score:** adversarial PENDING, factual PENDING, multi_hop PENDING.

**Version conflicts:** PENDING. Kiểm tra các case hỏi policy cũ, đặc biệt ngày phép và VPN, rồi đối chiếu answer với policy hiện hành trong ground truth.

**Bottom 10 thuộc adversarial:** PENDING. Liệt kê question ID từ `bottom_10`, không suy đoán từ nhãn distribution.

> Test set offline xác nhận có 10 adversarial cases, gồm bẫy version conflict và phủ định. Chưa có bằng chứng pipeline bị nhầm cho đến khi `reports/ragas_50q.json` được tạo. Kết luận cuối phải nêu score chênh lệch và case cụ thể.

---

## Input và cách tái tạo

```text
Input: answers_50q.json + test_set_50q.json
Command: python src/phase_a_ragas.py
Output: reports/ragas_50q.json
```

Nếu RAGAS dependency hoặc Day 18 evaluator không sẵn sàng, report phải ghi rõ offline fallback. Offline lexical score không được mô tả như live RAGAS measurement.
