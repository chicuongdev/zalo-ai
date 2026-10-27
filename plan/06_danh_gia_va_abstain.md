# 06 — Đánh giá, abstain & unanswerable

## 1. Evaluator local

Cài **đúng từng chữ** luật trong `subject/02.evaluation.json`:

- Type pred ≠ type reference → sai. Reference `answer: null` ⇒ type `unanswerable`.
- `string`: NFC → lowercase → ký tự không phải chữ/số/khoảng trắng → space → gộp space; so với reference **và mọi alias**.
- `number`: khớp tuyệt đối; `percent`: khớp sau round 2.
- `date`: chuỗi khớp tuyệt đối.
- `list`: cùng độ dài, so từng vị trí (phần tử: luật number nếu reference là số, ngược lại luật string).
- `table`: cột theo tên chuẩn hoá (không khớp → theo vị trí), hàng so như **multiset**.
- `abstain`/thiếu → abstain.
- PA = (correct − wrong) / N (đúng +1, abstain 0, sai −1 — công thức chính thức). Báo cáo thêm accuracy, tỷ lệ abstain, và **PA nếu không abstain câu nào** để đo giá trị của abstain policy.

**Báo cáo:** tổng; theo type; theo business; theo nhóm taxonomy; dump từng câu (pred, ref, code, output) để phân tích lỗi.

**Unit test evaluator** bằng các ví dụ trong đề (Sting dâu 330ml ↔ sp0042, −12.45, "2025-09", table khách nợ…).

## 2. Phân loại lỗi (dùng trong vòng lặp G2)

| Nhóm | Ví dụ |
|---|---|
| Hiểu sai câu hỏi | nhầm "bán chạy" theo tiền thay vì số lượng |
| Sai kỳ thời gian | tuần CN–T7, "tháng này" tính cả tháng |
| Sai định nghĩa nghiệp vụ | trừ voucher đơn, không loại đơn có hàng trả |
| Sai join/lọc | thiếu sheet, trùng dòng, dòng tổng |
| Sai thực thể | khớp nhầm tên SP gần giống |
| Sai format | tỷ lệ 0.12 thay vì 12.45, date thay vì yyyy-mm, type sai |
| Sai unanswerable | trả số cho câu không trả lời được, hoặc ngược lại |
| Lỗi thực thi | code crash / timeout |

## 3. Tín hiệu tin cậy

| Tín hiệu | Ý nghĩa |
|---|---|
| Code chạy lỗi sau hết số vòng sửa | → abstain |
| Kết quả NaN / rỗng / 0 bất thường | nghi sai lọc/join |
| Type kết quả ≠ type Planner dự kiến | mâu thuẫn nội bộ |
| **Hoà ở biên ranking** (k hoặc hạng 1) | test đã loại các câu như vậy ⇒ nhiều khả năng ta tính sai |
| **Self-consistency**: 2–3 lời giải độc lập (prompt khác / pandas vs SQL / có-không few-shot) | cùng kết quả ⇒ tin cậy cao; lệch ⇒ abstain hoặc chọn đa số |
| Logprob / tự đánh giá của verifier | tham khảo, cần hiệu chỉnh |
| Số vòng self-repair cần dùng | càng nhiều càng kém tin cậy |

Kết hợp thành điểm tin cậy (luật đơn giản trước, sau đó có thể hồi quy logistic nhỏ train trên dev — đây là classifier rất nhỏ, không phải model neural lớn).

**Quyết định:** điểm kỳ vọng khi trả lời = 2p − 1 ⇒ trả lời nếu P(đúng) ước tính **> 0.5**, ngược lại abstain. Vì ước lượng p thường lệch, ngưỡng thực tế trên điểm tin cậy được tune để **tối đa PA trên dev** (vẽ đường PA theo ngưỡng), rồi kiểm tra trên holdout.

**Hiệu chỉnh (calibration):** gom câu dev theo mức tin cậy, đo accuracy thực tế từng mức → chỉ những mức có accuracy > 50% mới được trả lời. Làm riêng theo type đáp án và nhóm câu hỏi nếu dữ liệu đủ (vd câu ranking top-k dễ sai hơn câu đếm).

## 4. Phát hiện unanswerable

Planner trả về `answerable` + lý do, sau đó kiểm tra xác định:

- Câu cần khái niệm (giá vốn, lợi nhuận, tồn kho, công nợ, nhân viên…) nhưng **không có cột/bảng tương ứng** trong schema card.
- Kỳ thời gian hỏi **nằm ngoài** khoảng dữ liệu (vd hỏi năm 2024 khi data bắt đầu 2025).
- Thực thể hỏi **không tồn tại** trong entity index (sau tra mờ).
- Rulebook có quy định riêng về trường hợp không trả lời.

Học từ các câu unanswerable trong train (nhóm theo nguyên nhân, [04 §2](04_du_lieu_va_eda.md)). Cẩn thận: unanswerable sai cũng bị tính sai như mọi câu khác → cũng áp ngưỡng tin cậy.

## 5. Determinism trong đánh giá

Tất cả số liệu dev phải lặp lại được: greedy decoding, seed cố định, cùng thứ tự câu. Chạy dev 2 lần định kỳ để đo độ dao động (tiền đề cho Rule 8).
