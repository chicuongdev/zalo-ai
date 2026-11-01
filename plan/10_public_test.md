# 10 — Public test (01/11/2026): phân tích & kế hoạch

## 1. Dữ liệu

- `public_test.zip` được giải nén vào `data/public_test/`: 1.000 câu, 14 shop (`dev_001`…`dev_014`), `rulebook.md`, `calendar.csv` (giống train). Không có đáp án.
- Chỉ đo được độ phủ (`scripts/coverage_public.py`). Điểm thật phải lấy từ leaderboard public.

## 2. Rulebook public khác train

| Loại | Nội dung mới |
|---|---|
| Sửa luật cũ | Đơn trả hàng sau kỳ (kể cả sau hôm nay) vẫn bị loại khỏi doanh thu kỳ đặt; "chưa giao" thuộc nhóm hỏi số còn lại; giao nhiều đợt tính đến hết hôm nay |
| Khái niệm mới | khách trung thành nhất (nhiều ngày mua nhất), khách sộp nhất (TB/đơn cao nhất, ≥3 đơn), khách hay đổi ý (nhiều đơn huỷ), mặt hàng được ưa chuộng nhất (nhiều đơn nhất), nhân viên/thợ chăm chỉ nhất (nhiều ngày làm), ngày đắt khách (nhiều đơn), giờ cao điểm (khung 1 giờ, type number), nhà cung cấp chính (nhiều phiếu nhập), trung bình mỗi ngày thứ X, báo cáo tiền mặt theo ca |
| Ghi chép | topping ghi chung ô với món là 2 mặt hàng; sổ không có cột trạng thái: trạng thái nằm ở Ghi chú |
| Ngành mới | **Mẹ và bé** (voucher, điểm, ship; size bỉm/số sữa theo danh mục; thành viên mới), **Sửa xe** (lượt xe/phiếu, việc trong ô "Làm gì", dòng xe, biển số, thợ, bảo hành, khách quen), **Điện thoại** (thu máy cũ, trả góp = ghi nợ, bảo hành theo quý, dòng máy/hãng) |
| Bỏ khỏi rulebook | giá nhập bình quân, tồn theo đơn vị lớn, giá bán ngày D (không có câu hỏi loại này). Luật vẫn giữ trong code |

⇒ Private sẽ tiếp tục có ngành và khái niệm mới. Cần đường dự phòng (LLM sinh code, B7) và abstain cẩn thận, không thể chỉ dựa vào catalog intent cố định.

## 3. Hiện trạng trên public (parser luật + thư viện, chưa có LLM)

| Giai đoạn | Có đáp án | Unanswerable | Bỏ trống |
|---|---|---|---|
| Ban đầu | 447 | 99 | 454 (392 do không đọc được kỳ: `Th7/2026`, `T4/2026`, `05/2026`, `8-2025`, `th 5/26`; từ địa phương `mô` = nào, `ni` = này) |
| Sau khi chuẩn hoá kỳ + từ địa phương | **725** | 137 | 138 |

Train vẫn 3000/3000 sau thay đổi.

**Pha A, validator báo lỗi:**
- `dev_003`: không có ngày đơn. Bán hàng tổng hợp + báo cáo ca + phiếu thu.
- `dev_012`: tiệm sửa xe, cấu trúc mới (sổ sửa xe, danh sách thợ).
- `dev_005`: 72% dòng bán không gắn được mặt hàng.
- `dev_010`: 2% đơn thiếu ngày.

**Rủi ro bị trừ điểm:**
- Parser luật mặc định về `revenue` khi không khớp intent nào, nên câu hỏi thuộc khái niệm mới có thể bị trả lời sai.
- 137 câu unanswerable cần kiểm lại. Ví dụ `dev_008`/`dev_014` có sổ nợ riêng (`SoNo.xlsx`) nhưng manifest báo không có `payments`.

## 4. Kế hoạch (đề xuất thứ tự)

1. **An toàn trước:**
   - Chỉ trả lời `revenue` khi câu có từ khoá doanh thu.
   - Câu khớp từ khoá khái niệm mới mà chưa có intent: abstain.
   - Rà các câu unanswerable theo từng shop.
2. **`scripts/predict.py`** (lõi của Docker):
   - Đầu vào: `questions.jsonl` không đáp án. Chạy Pha A, rule parser, LLM, kết hợp (`agree` / `llm_else_rule`) và formatter.
   - Đầu ra: ghi dần `submission.jsonl`, kèm log.
   - Notebook Kaggle chạy public để có **lượt nộp public đầu tiên**.
3. **Pha A** cho `dev_003`, `dev_012`, `dev_005`, `dev_010`: tổng quát hoá cho các dạng sổ mới, không viết riêng theo từng shop.
4. **Intent mới** theo rulebook public (mục 2), ưu tiên theo số câu public cần.
5. **Rulebook analyzer**: khi rulebook runtime khác train, đánh dấu mục thay đổi để intent liên quan đi đường dự phòng hoặc abstain.
6. **Đường dự phòng B7** (LLM sinh code pandas trên CDM) cho câu ngoài catalog.

**Nguyên tắc:** không tune theo public leaderboard (plan/05). Public chỉ dùng để tìm loại lỗi tổng quát. Không hard-code theo `business_id` hay theo câu cụ thể.
