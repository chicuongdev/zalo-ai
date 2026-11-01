# Kết quả EDA bộ train (2026-11-01)

Nguồn: `train.zip` → giải nén vào `data/train/` (không commit). Script EDA tạm nằm ngoài repo; sẽ chuyển thành `scripts/eda.py` khi bắt đầu code.

## 1. Câu hỏi & đáp án

- 3.000 câu, 30 business (25 business × ~118 câu, 6 business × 40 câu). `as_of_date` từ 2025-01-15 đến 2026-09-20; một business có thể có nhiều `as_of_date` khác nhau.
- Phân bố type:

| number | percent | list | date | string | unanswerable | boolean | table |
|---|---|---|---|---|---|---|---|
| 1884 (62.8%) | 578 (19.3%) | 193 (6.4%) | 145 (4.8%) | 88 (2.9%) | 70 (2.3%) | 23 (0.8%) | 19 (0.6%) |

- `alias`: 94% câu không có alias; câu có tên đối tượng thì alias chứa **mã** (`SP0076`, `KH0098`) và các cách viết khác (`"Từ Hải Thanh 0359470831"`, `"Le An Duc"`). Với list/table, alias là **list theo từng vị trí** (`[['KH0098'], ['KH0078'], …]`).
- **Câu hỏi được sinh từ template** (khoảng 40–60 ý định), sau đó diễn đạt lại kiểu văn nói: không dấu, gõ sai Telex (`tieenf`, `thangs`, `nhieeuf`, `cuwar hangf`), teencode (`dthu`, `bn`, `bnhiu`, `hnay`, `hqua`, `z`, `ha`), tiếng Anh xen (`total`, `bill`, `best seller`, `order`).
- Phân cụm thô theo từ khoá (số lượng gần đúng):
  - Doanh thu theo kỳ/mặt hàng/nhóm/hình thức thanh toán/kênh/ca/size: ~500.
  - Tồn kho, hết hàng, hàng ế: ~450.
  - % tăng trưởng so kỳ trước/cùng kỳ: ~150.
  - Đơn huỷ (đếm, tỉ lệ): ~250.
  - Số đơn, số đơn vượt ngưỡng tiền: ~135.
  - Ngày/tháng cao nhất: ~140.
  - Giá bán một ngày: ~100.
  - Hiệu ứng tăng giá: ~80.
  - Top mặt hàng / top khách: ~160.
  - Tỉ trọng nhóm: ~75.
  - Giá trị trung bình một đơn: ~70.
  - Công nợ (tổng, top bảng, tuổi nợ, nợ thêm/trả nợ): ~130.
  - Nhập hàng (tổng, giá nhập bình quân): ~80.
  - Ngành: thuốc kê đơn, hoạt chất, hạn dùng, size M/L, đợt giao.
  - Ít gặp: lãi gộp, lãi ròng, nhân viên giỏi nhất, xu hướng tăng liên tục (boolean).
- **Unanswerable (70 câu) có 3 nguồn**:
  1. **Thông tin shop không ghi**: giới tính khách, địa chỉ/đường, đánh giá nhân viên ("có lễ phép không"), giá vốn khi không có cột giá vốn, công nợ khi không có dữ liệu thanh toán, tồn kho khi không có file tồn, hình thức thanh toán, kênh bán, nhóm khách, mã khách…
  2. **Kỳ nằm hoàn toàn ngoài khoảng dữ liệu**, ví dụ hỏi tháng 1/2025 khi dữ liệu bắt đầu từ 02/2025.
  3. **Phép tính cần dữ liệu không có**, ví dụ % thay đổi so với tháng trước khi tháng trước nằm ngoài dữ liệu.

  ⇒ Unanswerable được quyết định bởi **"shop có ghi loại thông tin này không" + "kỳ có nằm trong dữ liệu không"** — hoàn toàn kiểm tra được bằng máy.

## 2. Rulebook train (`data/train/rulebook.md`)

Rất chi tiết, 10 mục: (1) đơn & doanh thu, (2) thời gian, (3) xếp hạng, (4) công nợ, (5) kho/nhập/giá vốn, (6) luật theo ngành (cà phê, nhà thuốc, VLXD), (7) không trả lời được, (8) cách ghi trong file, (9) format đáp án & chấm điểm, (10) từ ngữ. Một số điểm then chốt **khác trực giác**:

- Đơn có trả hàng (kể cả một phần) → bỏ **cả đơn** khỏi doanh thu và số đơn; đơn đang giao vẫn tính.
- Kỳ của đơn theo **ngày đặt**; bản ghi sau `as_of_date` coi như chưa xảy ra, **trừ** trạng thái huỷ/trả.
- "Tháng này so với tháng trước" = cùng số ngày; "tuần trước" = cả tuần T2–CN; "N ngày gần nhất" gồm hôm nay; "trên N" không gồm N.
- Tết năm Y = 23 tháng Chạp (âm Y−1) → hết mùng 10 tháng Giêng (âm Y), tra `calendar.csv` (cột: `date, weekday, lunar_day, lunar_month, lunar_year, lunar_leap, holiday`, 1.461 ngày từ 2024-01-01).
- Bán chạy = số lượng **quy về đơn vị cơ bản**; "Phí phục vụ" không phải mặt hàng nhưng vẫn tính doanh thu.
- Khách: shop có mã thì theo mã; không có mã thì theo **tên**, chỉ khác cách viết là cùng khách; khách lẻ không tính.
- Lãi gộp dùng **giá vốn ghi trên dòng bán**; giá vốn bình quân gia quyền theo lô chỉ khi được hỏi.
- Bằng nhau → theo **mã** tăng dần (không có mã thì theo tên).
- Format: tiền là số nguyên VND; trung bình tiền làm tròn về đồng (nửa đồng làm tròn lên); % và trung bình khác làm tròn 2 chữ số; tồn theo đơn vị lớn là list `[nguyên, lẻ]`; nhiều số → list theo thứ tự câu hỏi.

⚠️ Private dùng rulebook riêng (có thể khác) → hệ thống phải **so sánh rulebook runtime với rulebook train** và xử lý phần khác (xem [thiet_ke/03](thiet_ke/03_tang_ngu_nghia_va_intent.md)).

## 3. Dữ liệu business

- 30 business, mỗi business 1–17 file; định dạng **CSV, XLSX, SQLite**. Ngành quan sát được: tạp hoá, cà phê/trà sữa, nhà hàng/quán nhậu, nhà thuốc, vật liệu xây dựng, cửa hàng gas/nước.
- **7 "kiểu nguồn"** lặp lại (cùng ý nghĩa, khác tên cột/cách ghi):

| Kiểu | Ví dụ | Đặc điểm |
|---|---|---|
| A. File phẳng CSV một dòng = một dòng hàng | biz_101, 114, 125 | Tên cột tuỳ ý (`Nội dung`, `Thanh tien`, `Quy ra ĐV lẻ`), quy đổi đơn vị nằm trong README |
| B. Sổ tay Excel một sheet | biz_107, 113, 126 | Ngày là serial Excel, `"1 hộp"` lẫn số, không có mã đơn |
| C. Sổ tay Excel mỗi tháng một sheet | biz_105, 117 | Header 2 tầng (`Hàng | Tiền | Đơn`), tiền `"1tr440"`, `"16,56tr"`, ngày `"1/1"` (năm lấy từ tên sheet), `"2 thg 1 2025"` |
| D. Phần mềm bán hàng: sổ chi tiết bán hàng | biz_112, 115, 116, 118, 130 | Dòng tiêu đề "SỔ CHI TIẾT BÁN HÀNG", số `"25,000.0000"`, nhiều file/sheet theo tháng |
| E. Phần mềm bán hàng: nhiều danh sách | biz_102–104, 106, 108, 109, 119–122, 128 | Hoá đơn, chi tiết, khách, SP, nhập, lô, tồn, sổ quỹ; có khi gộp nhiều sheet trong một file |
| F. CSV nhiều bảng nối bằng mã | biz_111, 127, 129 | `don_hang`, `chi_tiet_don`, `thanh_toan`, `khach_hang`, `san_pham` với tên cột lộn xộn |
| G. SQLite POS chuẩn hoá | biz_123 (17 bảng) | Đầy đủ nhất: thẻ kho, lô, lịch sử giá, trả hàng, thuốc |
| (H) Nhiều nguồn trộn | biz_124 | File phần mềm + sổ tay chi phí/nhập hàng + CSV tồn kho |

- Kích thước: vài trăm đến ~145k dòng/bảng; file xlsx tới ~5MB (cần reader nhanh).
- "Bẩn" quan sát được:
  - Tiền viết nhiều kiểu: `"38,000"`, `"55.000đ"`, `"25,000.0000"`, `"1tr440"`, `"9tr960"`, `"1,84tr"`, số âm cho dòng trả.
  - Ngày viết nhiều kiểu: `dd/mm/yyyy`, serial Excel, `datetime`, `"1/1"`, `"1 thg 1 2025"`.
  - Số lượng có kèm đơn vị: `"2 thùng"`.
  - Trạng thái nhiều cách viết: `Đã hoàn thành / ok / xong / đã lấy / Thành công / Hoàn thành / Đã giao / Đổi trả / Đặt hàng (Đã duyệt)…`.
  - Khách lẻ ghi `"lẻ"`, `"kl"`, `"Khách lẻ"`.
  - Tên SP khác hoa/thường giữa file (`PANADOL EXTRA HỘP…` vs `Panadol Extra hộp…`).
  - Tên khách kèm số điện thoại.
  - Ô trống ở các dòng sau của một đơn (fill-down, rulebook §8); dòng trùng do lỗi xuất (§8).
  - Tên file bị mojibake khi giải nén zip (`Danh s├ích h├áng h├│a.xlsx`).
- README: 17–191 dòng; luôn có danh sách file, mô tả cột và **"Dữ liệu có đến hết dd/mm/yyyy"**; nhiều README chứa **bảng quy đổi đơn vị dạng text** (`Coca Cola 330ml: 1 thùng = 24 lon`) và quy ước riêng (trả hàng ghi số âm, tồn cuối là tồn tại ngày cuối dữ liệu…).

## 4. Hệ quả thiết kế (quyết định)

1. Tách **nạp & chuẩn hoá dữ liệu** (mỗi business một lần) khỏi **trả lời câu hỏi** (mỗi câu): đưa 7+ kiểu nguồn về **một mô hình dữ liệu chuẩn**.
2. Rulebook rất cụ thể và đáp án do oracle xác định ⇒ **cài đặt rulebook thành thư viện ngữ nghĩa xác định** (semantic layer). Không để LLM tự diễn giải lại từng luật cho mỗi câu.
3. Câu hỏi theo template ⇒ LLM làm **bộ phân tích câu hỏi → kế hoạch truy vấn có cấu trúc** (intent + slot), thay vì sinh code tự do cho mọi câu. Sinh code chỉ là **đường dự phòng** cho intent lạ (ngành mới ở private).
4. Unanswerable = **manifest năng lực** của shop (shop có ghi thông tin gì, khoảng ngày dữ liệu) so với **yêu cầu** của intent.
