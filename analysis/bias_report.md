# LLM Judge Bias Report, Phase B

**Sinh viên:** Chưa cung cấp
**Ngày:** Chưa ghi nhận
**Judge model:** PENDING, lấy từ `reports/judge_results.json` hoặc config khi chạy
**Trạng thái:** PENDING, chưa có judge report. Không dựng winner, kappa hoặc bias rate từ human labels alone.

---

## 1. Pairwise Judge Results

Nguồn: output của `pairwise_judge()` trong `reports/judge_results.json`. Cần tối thiểu 5 cặp thật, reasoning không rỗng, winner chỉ thuộc `A`, `B`, `tie`.

| # | Question ID hoặc tóm tắt | Winner | Score A | Score B | Reasoning tóm tắt | Nguồn |
|---:|---|---|---:|---:|---|---|
| 1 | PENDING | PENDING | PENDING | PENDING | PENDING | judge report |
| 2 | PENDING | PENDING | PENDING | PENDING | PENDING | judge report |
| 3 | PENDING | PENDING | PENDING | PENDING | PENDING | judge report |
| 4 | PENDING | PENDING | PENDING | PENDING | PENDING | judge report |
| 5 | PENDING | PENDING | PENDING | PENDING | PENDING | judge report |

---

## 2. Swap-and-Average Results

`winner_pass2` phải được chuyển về không gian answer gốc. Ví dụ pass 2 đánh answer B trong thứ tự swapped thì winner gốc là A.

| # | Pass 1 Winner | Pass 2 Winner, space gốc | Final | Position Consistent? |
|---:|---|---|---|---|
| 1 | PENDING | PENDING | PENDING | PENDING |
| 2 | PENDING | PENDING | PENDING | PENDING |
| 3 | PENDING | PENDING | PENDING | PENDING |
| 4 | PENDING | PENDING | PENDING | PENDING |
| 5 | PENDING | PENDING | PENDING | PENDING |

**Position bias rate:** PENDING% = số case `position_consistent = false` / tổng judge results. Đây là rate instability, không phải tỷ lệ A hoặc B thắng.

**Cách đọc:** rate >30% là cảnh báo cần giữ swap-and-average và review judge prompt/model. Tie sau hai pass là kết quả hợp lệ, không tự đổi thành winner.

---

## 3. Cohen's kappa Analysis

**Human labels:** `human_labels_10q.json`, 10 câu, 5 label=1 và 5 label=0, theo file hiện tại.
**Judge labels:** PENDING, cần chạy judge trên đúng 10 question ID: 1, 5, 12, 21, 23, 29, 33, 41, 46, 50.

| Question ID | Human Label | Judge Label | Agree? |
|---:|---:|---:|---|
| 1 | 1 | PENDING | PENDING |
| 5 | 0 | PENDING | PENDING |
| 12 | 1 | PENDING | PENDING |
| 21 | 1 | PENDING | PENDING |
| 23 | 1 | PENDING | PENDING |
| 29 | 0 | PENDING | PENDING |
| 33 | 1 | PENDING | PENDING |
| 41 | 0 | PENDING | PENDING |
| 46 | 1 | PENDING | PENDING |
| 50 | 0 | PENDING | PENDING |

**Cohen's kappa:** PENDING
**Interpretation:** PENDING, chờ kappa. Quy ước diễn giải: poor <0, slight 0 đến 0.20, fair 0.21 đến 0.40, moderate 0.41 đến 0.60, substantial 0.61 đến 0.80, almost perfect 0.81 đến 1.00.

Kappa cần tính từ hai vector label độc lập. Không dùng reasoning hoặc score làm judge label nếu phase chưa định nghĩa rule chuyển đổi.

---

## 4. Verbosity Bias

Chỉ tính trên case `final_winner` là A hoặc B. Tie bị loại khỏi mẫu decisive.

- A thắng và A dài hơn B: PENDING / PENDING cases
- B thắng và B dài hơn A: PENDING / PENDING cases
- **Verbosity bias rate:** PENDING%

**Công thức:** `(A thắng, A dài hơn B + B thắng, B dài hơn A) / tổng decisive cases`.

**Kết luận:** PENDING. Nếu rate cao, judge có thể ưu tiên độ dài thay vì correctness, gây phạt answer ngắn nhưng đúng và tăng chi phí token. Cần xem cùng score, reasoning và correctness, không kết luận từ length alone.

---

## 5. Nhận xét chung

Chưa có judge report nên chưa thể nói kappa vượt 0.6 hoặc position bias vượt 30%. Human labels đã có sẵn, nhưng không thay thế kết quả judge. Sau khi chạy, dùng swap-and-average để giảm ảnh hưởng thứ tự, rồi kiểm tra các tie và case disagreement bằng người đánh giá. Production nên dùng judge như tín hiệu hỗ trợ, version-control model và rubric, sample lại các case rủi ro, và không dùng một điểm LLM duy nhất làm quyết định an toàn.

---

## Input và cách tái tạo

```text
Input: answers hoặc answer pairs + human_labels_10q.json
Command: python src/phase_b_judge.py
Output: reports/judge_results.json
```

Nếu chạy offline fallback, ghi rõ trong report. Fallback lexical không được trình bày như đánh giá live bằng GPT.
