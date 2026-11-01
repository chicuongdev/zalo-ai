# 02 — Pha A: Nạp & chuẩn hoá dữ liệu

Đầu vào: `/data/data/<biz>/` (read-only) + `README.md`. Đầu ra: `ShopStore` = DuckDB chuẩn (`/tmp/work/<biz>.duckdb`) + `manifest.json` + `entity_index.pkl` + `ingest_report.json`.

```
[A1] File Reader ─▶ [A2] Table Detector ─▶ [A3] Value Parsers ─▶ [A4] Schema Mapper ─▶ [A5] Canonical Builder ─▶ [A6] Validator
     RawSheet[]         LogicalTable[]          TypedTable[]          MappingSpec             CDM (DuckDB)           Manifest
```

## A1 — File Reader

- Liệt kê file; **sửa tên file mojibake** (thử `name.encode('cp437').decode('utf-8')`).
- CSV: dò encoding (`utf-8-sig` → `utf-8` → `cp1258`), dò dấu phân cách; đọc mọi cột dạng **text** (không để pandas tự đoán kiểu).
- XLSX: đọc **mọi sheet** bằng `python-calamine` (nhanh hơn openpyxl nhiều lần với file 5MB). Giữ giá trị gốc: số, datetime, text.
- SQLite: mở `mode=ro`, đọc mọi bảng.
- Đầu ra `RawSheet{file, sheet, cells: list[list], n_rows}`.

## A2 — Table Detector

Mỗi `RawSheet` có thể có dòng tiêu đề ("DANH SÁCH HÓA ĐƠN", "SỔ CHI TIẾT BÁN HÀNG"), dòng "Kỳ báo cáo…", dòng trống, header 2 tầng (`Hàng | Tiền | Đơn` rồi mới đến header thật), dòng tổng ở cuối.

1. **Tìm dòng header**: trong 15 dòng đầu, chọn dòng có điểm cao nhất theo: tỉ lệ ô là text ngắn không trống; ≥ 3 ô; các dòng ngay dưới có kiểu dữ liệu nhất quán theo cột; khớp từ vựng header đã biết (từ điển xây từ train).
2. Header nhiều tầng: nếu dòng trên header có ít ô và phủ nhóm cột → ghép làm tiền tố (giữ lại để LLM hiểu ngữ cảnh), không dùng làm header chính.
3. Loại dòng cuối kiểu "Tổng cộng", dòng trống.
4. **Gộp bảng cùng cấu trúc**: các sheet/file có **cùng tập header** (thứ tự có thể khác) và cùng "họ" tên file (`SoBanHang_1`, `SoBanHang_2026`, `DanhSachHoaDonChiTiet_1/_2`, sheet `T01_2025`…) → một `LogicalTable`, thêm cột `__sheet`, `__file` và `__sheet_period` (tháng/năm parse từ tên sheet: `T01_2025`, `04.2025`, `Thang 02 2025`, `Tháng 01-2025`, `T02-2025`).
5. File nhiều sheet khác cấu trúc (`DuLieuBanHang.xlsx`, `Bao_cao_ban_hang.xlsx`) → mỗi sheet một bảng logic, tên bảng = tên sheet.

## A3 — Value Parsers (thư viện thuần Python, unit test dày)

Chạy theo **từng cột**: thử các parser, chọn parser parse được ≥ 98% giá trị không trống, ghi lại tỉ lệ lỗi.

| Parser | Ví dụ đầu vào → giá trị |
|---|---|
| `money` | `"38,000"`→38000 · `"55.000đ"`→55000 · `"25,000.0000"`→25000 · `"1tr440"`→1440000 · `"9tr960"`→9960000 · `"16,56tr"`→16560000 · `"1,84tr"`→1840000 · `"-53.500đ"`→−53500 · `"1250k"`→1250000 · số thực Excel |
| `qty_unit` | `"2 thùng"`→(2,"thùng") · `"1 cây"`→(1,"cây") · `3`→(3,None) |
| `date` | `"01/02/2025"` (dd/mm) · serial `45717` · `datetime` · `"1 thg 1 2025"` · `"2 thg 1 2025"` · `"1/1"` + năm từ `__sheet_period` (rulebook §8: ngày không ghi năm → năm của sheet) |
| `datetime` / `time` | `datetime(…)`, `"06:13"` |
| `bool` | `TRUE/FALSE/1/0/"Có"/"x"` |
| `code` | `^[A-Z]{1,4}\d{3,}$` (SP0001, KH0001, ORD000001, PN00001) |
| `text` | NFC, strip |

Dấu `.`/`,` mơ hồ ("1.500" là 1500 hay 1,5): quyết định **theo cả cột** (tập giá trị có dạng `x.xxx` ba chữ số sau dấu → nghìn); kiểm tra chéo `qty × unit_price ≈ line_amount`.

## A4 — Schema Mapper

Mục tiêu: `MappingSpec` = mỗi `LogicalTable` thuộc **bảng CDM nào**; mỗi cột → **trường CDM nào** (hoặc bỏ / `extra`); các **giá trị liệt kê** (trạng thái, phương thức TT, kênh) → enum chuẩn; thông tin rút từ README (quy đổi đơn vị dạng text, ngày cuối dữ liệu, quy ước trả hàng số âm, tồn cuối là tồn ngày nào…).

**Ba tầng, rẻ trước đắt sau:**

1. **Từ điển đồng nghĩa** (xây từ 30 shop train, mở rộng bằng biến thể không dấu): `Thành tiền / Thanh tien / T.Tiền / Amount / Trị giá / Tiền bán / thanh_tien / Tổng` → `line_amount`… Dùng điểm khớp trên tên cột (đã bỏ dấu) + kiểu dữ liệu + mô tả trong README ("**Trị giá**: thành tiền sau giảm" → `line_amount`).
2. **Luật cấu trúc**: bảng có `order_id` lặp + tên SP + số lượng → `order_lines`; một dòng một mã đơn + tổng tiền → `orders`; bảng phẳng chứa cả thông tin đơn lẫn dòng hàng → tách thành `orders` + `order_lines` (fill-down §8, đơn lấy trạng thái/khách ở dòng đầu nhóm).
3. **LLM** (Qwen3-14B, guided JSON) cho cột/bảng còn mơ hồ hoặc điểm khớp thấp. Prompt gồm: phần README liên quan, header, 8 dòng mẫu đã parse, thống kê cột, danh sách trường CDM (có mô tả). Đầu ra theo JSON schema `MappingSpec`. **Mỗi shop một vài lần gọi** → không đáng kể về thời gian.
   - Ánh xạ **giá trị trạng thái** (ví dụ `{"đã lấy","Đổi trả","huỷ"}` → completed/returned/cancelled) và **phương thức TT/kênh** cũng qua LLM, có từ điển ưu tiên.
   - Bảng quy đổi trong README (`- Coca Cola 330ml: 1 thùng = 24 lon`) → regex trước, LLM nếu regex không phủ.

Mọi quyết định đều được ghi vào `ingest_report.json` (cột nào → trường nào, bởi tầng nào, độ tin cậy) để debug.

## A5 — Canonical Builder

1. Áp mapping, parse kiểu, ghi các bảng CDM vào DuckDB.
2. **Fill-down** các trường cấp đơn trong bảng phẳng (§8).
3. **Bỏ dòng trùng hoàn toàn trong cùng một đơn** (§8). Bảng không theo đơn: giữ nguyên.
4. Tính `has_return` (trạng thái trả, dòng âm, có phiếu `returns`, `qty_return_base > 0`), chuẩn `status`.
5. `qty_base`: dùng cột quy đổi có sẵn; nếu không → `qty × factor(product, unit)`; đơn vị không có quy đổi = cơ bản.
6. Sinh `products` khi shop không có danh mục (từ tên trên dòng bán); hợp nhất biến thể tên (khác hoa/thường) về một `product_id`, lưu `name_variants`.
7. `stock_snapshot` + ngày áp dụng (README: "Tồn cuối là tồn cuối ngày cuối có dữ liệu"); nếu có thẻ kho → `stock_ledger`.
8. `is_service_fee`, `size`, `is_made_to_order` (danh mục `Loại hàng hóa`, nhóm hàng đồ uống/món ăn + không có phiếu nhập… → LLM xác nhận một lần/shop).
9. Bảng không ánh xạ được → `extra_<tên>`.

## A6 — Validator

Kiểm tra bất biến, mỗi kiểm tra cho điểm 0–1, ghi vào manifest:

| Kiểm tra | Ý nghĩa nếu hỏng |
|---|---|
| Σ `line_amount` theo đơn ≈ `goods_total` (khi có cả hai) | Ánh xạ sai cột tiền / parse sai dấu nghìn |
| `qty × unit_price − line_discount ≈ line_amount` | Sai cột |
| `qty_base / qty` ∈ hệ số quy đổi đã biết | Sai quy đổi |
| Mọi `status_raw` đã ánh xạ; mỗi đơn đúng 1 trạng thái | Thiếu ánh xạ trạng thái |
| `order_date` ∈ [data_start, data_end]; ngày cuối khớp README | Sai parse ngày (dd/mm vs mm/dd) |
| Σ payments theo đơn ≤ grand_total (+ sai số) | Sai bảng thanh toán |
| Tồn không âm khi dựng ngược từ snapshot | Sai chiều tồn |

Điểm thấp → thử lại tầng LLM với gợi ý lỗi (tối đa 2 lần) → vẫn thấp thì đánh dấu miền đó `confidence` thấp. Từ đó các câu hỏi dùng miền này sẽ được abstain nhiều hơn.

## Kết quả mong muốn trên train (tiêu chí xong Pha A)

- 30/30 shop dựng CDM thành công, mọi kiểm tra ≥ 0.99.
- **Tái tạo oracle**: chạy thư viện ngữ nghĩa với QueryPlan đúng ([09](09_chien_luoc_kiem_thu.md)) cho ≥ 98% câu train trả lời được.
- Thời gian Pha A ≤ 3 phút/shop lớn nhất.
