# 04 — Dữ liệu & EDA

Làm ngay khi có dữ liệu train. Kết quả EDA ghi vào `plan/eda_findings.md` (tạo khi làm).

## 1. Lấy dữ liệu

- [ ] Tải train + public test về `data/train/`, `data/public/` (không commit vào git).
- [ ] Kiểm tra cấu trúc đúng như mô tả (data/<biz>/, rulebook.md, calendar.csv, questions.jsonl, answers.jsonl).
- [ ] Theo dõi forum/BTC: Docker guideline, cập nhật rulebook.

## 2. Phân tích câu hỏi (train `questions.jsonl` + `answers.jsonl`)

- [ ] Phân bố **type** đáp án; tỷ lệ **unanswerable** (quyết định chiến lược abstain).
- [ ] Phân bố câu có dấu / không dấu / viết tắt; độ dài câu.
- [ ] Cụm thời gian xuất hiện ("tuần rồi", "tháng trước", "quý 3", "Tết", "cùng kỳ"…) + tần suất.
- [ ] Ý định nghiệp vụ: doanh thu, số lượng, lợi nhuận/giá vốn, tồn kho, công nợ, khách hàng, nhân viên, chi nhánh, so sánh %, xu hướng, ngày cao điểm…
- [ ] Câu ranking: top-k, "…nhất", tiêu chí ngầm định (→ mặc định rulebook).
- [ ] Mẫu `alias` trong answers (tên + mã) → xác nhận chiến lược trả mã.
- [ ] Câu unanswerable: **vì sao** không trả lời được (thiếu cột, ngoài khoảng thời gian, thực thể không tồn tại, câu mơ hồ) → danh sách quy tắc phát hiện.

**Đầu ra:** taxonomy câu hỏi (~15–30 nhóm), mỗi nhóm: số lượng, ví dụ, helper cần, mức khó.

## 3. Phân tích dữ liệu business

- [ ] Liệt kê file/bảng/sheet mỗi business; số dòng; khoảng thời gian.
- [ ] Mẫu schema lặp lại giữa các ngành (orders, order_lines, products, purchases/lots, customers, debts, staff, branches…) và các biến thể tên cột (tiếng Việt / tiếng Anh / không dấu / viết tắt).
- [ ] Mức "bẩn": định dạng tiền ("1.250.000đ", "1,25tr", "1250k"), ngày (dd/mm/yyyy, serial Excel, text), tên SP nhiều cách viết, dòng tổng/ghi chú lẫn trong bảng, header không ở dòng 1, ô gộp, giá trị thiếu, trùng lặp.
- [ ] Cách biểu diễn trạng thái đơn (huỷ, trả hàng, trả một phần), voucher, VAT, phí ship.
- [ ] Chất lượng README: phân loại đầy đủ / sơ sài / trống — đo xem agent có phụ thuộc README không.
- [ ] `rulebook.md` train: đọc kỹ toàn bộ, liệt kê mọi định nghĩa → test case cho helper.
- [ ] `calendar.csv`: cấu trúc cột, phạm vi năm, cách tra Tết.

## 4. Chia dữ liệu phát triển

Chia **theo business**, không theo câu hỏi (để mô phỏng business/ngành chưa thấy ở private test):

| Tập | Business | Dùng cho |
|---|---|---|
| `train-fit` | ~20 | Few-shot pool, dữ liệu fine-tune, phát triển helper |
| `dev` | ~5 | Tune prompt/ngưỡng abstain, benchmark model |
| `holdout` | ~5, ưu tiên **ngành khác** với train-fit | Chỉ đánh giá cuối mỗi giai đoạn, không tune trên đó |

Ghi danh sách business mỗi tập vào `plan/eda_findings.md` và giữ cố định.

## 5. Baseline "không LLM" để hiểu độ khó

- [ ] Đo % câu mà một bộ template + helper đơn giản giải được (vd "doanh thu tháng X") → biết phần nào cần LLM thực sự.
- [ ] Chạy evaluator với submission toàn `abstain` (PA = 0) và toàn `unanswerable` để kiểm tra evaluator.
