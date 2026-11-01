# 01 — Mô hình dữ liệu chuẩn (Canonical Data Model — CDM)

Mọi shop, dù nguồn là CSV phẳng, sổ tay Excel hay SQLite POS, đều được đưa về **cùng một tập bảng** trong DuckDB. Thư viện ngữ nghĩa ([03](03_tang_ngu_nghia_va_intent.md)) chỉ làm việc trên CDM. Bảng hoặc trường nào shop không có thì **để trống và ghi vào manifest**. Không suy ra từ cột khác (rulebook §7).

## 1. Quy ước chung

- Tiền: `BIGINT` VND (giá trị lẻ như `25,000.0000` → 25000; giá vốn lẻ giữ `DOUBLE`).
- Ngày: `DATE`; thời điểm: `TIMESTAMP`; có cả hai khi nguồn có giờ.
- Văn bản gốc luôn được giữ (`*_raw`) để trả lời đúng **cách viết trong dữ liệu**.
- Mỗi dòng có `src` (file#sheet#row) để truy vết trong log.
- Mã: nếu shop có mã (SP0001, KH0001, ORD000001) dùng nguyên; nếu không, sinh mã tổng hợp `@P:<tên chuẩn hoá>` (vẫn đảm bảo tie-break "không có mã thì theo tên").

## 2. Bảng lõi

### `orders` — một dòng một đơn
| Trường | Kiểu | Ý nghĩa / quy tắc |
|---|---|---|
| order_id | TEXT | Mã đơn; sổ tay không có mã → sinh theo nhóm dòng (ngày + khách + vị trí) |
| order_date | DATE | **Ngày đặt** (rulebook §1: kỳ theo ngày đặt) |
| order_ts | TIMESTAMP? | Giờ tạo đơn (dùng cho ca sáng/chiều) |
| status | ENUM | `completed / cancelled / returned / delivering` (đúng 4 trạng thái, §8) |
| status_raw | TEXT | Giá trị gốc |
| has_return | BOOL | Có dòng trả / phiếu trả / số lượng âm / trạng thái trả → `true` |
| customer_id | TEXT? | Mã khách; null = khách lẻ |
| customer_name_raw | TEXT? | Tên ghi trên đơn |
| is_walk_in | BOOL | Khách lẻ (`lẻ`, `kl`, `Khách lẻ`, trống ở shop có mã) |
| payment_method | ENUM? | `cash / transfer / cod / ewallet / card / debt / other` + `payment_method_raw` |
| channel | TEXT? | Kênh bán (`store`, `zalo oa`, điện thoại, sàn…) + `channel_is_marketplace` |
| staff_id, branch_id, shift_id | TEXT? | |
| goods_total | BIGINT? | Tổng tiền hàng (trước giảm giá đơn) |
| order_discount | BIGINT? | Giảm giá cả đơn / voucher |
| shipping_fee, vat | BIGINT? | |
| grand_total | BIGINT? | Khách phải trả cả đơn (đã trừ giảm giá đơn, gồm phí giao) — dùng cho công nợ |
| paid_recorded, debt_recorded | BIGINT? | "Khách đã trả", "Còn nợ" ghi trên đơn |
| note | TEXT? | |

### `order_lines` — một dòng một dòng hàng
| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| order_id, line_no | | |
| product_id | TEXT | Liên kết `products` |
| product_name_raw | TEXT | |
| unit | TEXT | Đơn vị của dòng |
| qty | DOUBLE | Số lượng theo đơn vị dòng (âm = dòng trả) |
| qty_base | DOUBLE | Quy về đơn vị cơ bản (từ cột có sẵn hoặc `qty × factor`) |
| unit_price | BIGINT | Đơn giá dòng (trước chiết khấu) |
| line_discount | BIGINT | |
| line_amount | BIGINT | Thành tiền sau giảm giá dòng — **cơ sở của doanh thu** |
| cost_per_sale_unit | DOUBLE? | "Giá vốn ghi trên dòng bán" (lãi gộp §5) |
| is_service_fee | BOOL | Dòng "Phí phục vụ" — không phải mặt hàng (§3) |

### `products`
| Trường | Ý nghĩa |
|---|---|
| product_id, name (cách viết chính), name_variants[] | Mọi cách viết gặp trong dữ liệu (để alias / liên kết) |
| group | Nhóm hàng (đúng tên, không gộp §3) |
| base_unit | Đơn vị cơ bản |
| list_price, cost_price | Giá bán/giá vốn trong danh mục (giá trị tồn kho §5 dùng `cost_price`) |
| is_prescription, active_ingredient | Nhà thuốc |
| is_made_to_order | Món pha chế/chế biến tại chỗ (loại khỏi "hết hàng" §5) |
| size | `M`/`L` nếu tên kết thúc `(M)`/`(L)` (luật cà phê) |

### Bảng phụ (có thì nạp)
| Bảng | Trường chính | Dùng cho |
|---|---|---|
| `unit_conversions` | product_id, unit, factor_to_base | Quy đổi; đơn vị không có dòng = cơ bản, hệ số 1 (§10) |
| `customers` | customer_id, name, phone, group, gender?, address? | Nhóm khách, công nợ, unanswerable (giới tính/địa chỉ) |
| `payments` | payment_id, order_id, paid_ts, amount, method | Công nợ, trả nợ, nợ thêm |
| `returns` | return_id, order_id, return_ts, refund | Trạng thái trả |
| `purchases` | receipt_id, receipt_date, supplier_id, status, note, total | Tiền nhập, NCC, nhập đầu kỳ |
| `purchase_lines` | receipt_id, product_id, unit, qty, unit_cost, amount, lot_id?, expiry? | Giá nhập bình quân, nhập trừ bán |
| `lots` | lot_id, product_id, receipt_id, expiry, qty_in_base, unit_cost_base | Hạn dùng, giá vốn theo lô |
| `line_lots` | order_id, line_no, lot_id, qty_base, qty_return_base | Tồn theo lô |
| `stock_ledger` | product_id, ts, qty_delta_base, balance_after, doc_type, doc_id | Tồn tại thời điểm (thẻ kho) |
| `stock_snapshot` | product_id, as_of (= ngày cuối dữ liệu), qty_base | Tồn khi chỉ có "tồn cuối" |
| `price_history` | product_id, effective_date, price_base, old_price | Giá bán ngày D, hiệu ứng tăng giá |
| `expenses` | date, category, amount, note | Lãi ròng |
| `deliveries` | order_id, trip_no, date, product_id, qty, vehicle, driver | Đợt giao (VLXD) |
| `debt_terms` | order_id, days_allowed, due_date | Hạn nợ |
| `dining` | order_id, table, area, guests | Nhà hàng (bàn/khu vực) |
| `staff`, `branches`, `suppliers`, `shifts` | | |
| `extra_*` | bảng không ánh xạ được | Giữ nguyên cho đường dự phòng sinh code |

## 3. `ShopMeta` & Manifest năng lực

Sinh ở cuối Pha A, là căn cứ cho kiểm tra trả lời được (B5) và cho prompt của parser.

```json
{
  "business_id": "biz_105",
  "industry_guess": "cafe",
  "data_start": "2025-02-01",
  "data_end": "2026-06-24",              // từ README "Dữ liệu có đến hết", đối chiếu max(order_date)
  "has_customer_codes": false,           // quyết định cách xác định khách (§3)
  "capabilities": {
    "order_lines": true, "order_ts": true, "customers_table": false, "customer_group": false,
    "customer_gender": false, "customer_address": false, "payment_method": false, "channel": false,
    "payments": false, "debt": false, "line_cost": false, "catalog_cost": false,
    "purchases": true, "lots": false, "expiry": false, "stock_snapshot": true, "stock_ledger": false,
    "stock_source": "snapshot",          // "ledger" | "lots" | "snapshot" | null (không tính được tồn)
    "price_history": true, "unit_conversions": true, "expenses": false, "staff": false,
    "deliveries": false, "prescription": false, "active_ingredient": false, "product_group": false
  },
  "enums": {"payment_method": [], "channel": [], "customer_group": [], "product_group": []},
  "validation": {"lines_sum_vs_order_total": "n/a", "qty_base_consistency": 0.999, "status_mapped": 1.0},
  "confidence": {"orders": 0.98, "stock": 0.9}
}
```

- `enums` cho parser biết shop có những giá trị nào (ví dụ kênh bán `zalo oa`, nhóm `thân thiết`). Nhờ vậy câu "khách nhóm thân thiết" ở shop không có nhóm khách → unanswerable.
- `confidence` thấp ở một miền (ví dụ ánh xạ cột kho không chắc) sẽ hạ độ tin cậy của mọi câu dùng miền đó ([05](05_thuc_thi_kiem_chung_tra_loi.md)).

## 4. Chỉ mục thực thể (Entity Index)

Cho mỗi loại thực thể (product, customer, product_group, supplier, staff, active_ingredient, payment_method, channel):

- `id`, `display_name` (cách viết chính), `variants[]`.
- Khoá tra: `norm` (NFC + lowercase + bỏ dấu câu, theo luật chấm), `norm_noaccent` (bỏ dấu, đ→d), token set.
- Khách ở shop không có mã: gộp các tên **chỉ khác cách viết** (khác hoa/thường, dấu, khoảng trắng, hậu tố số điện thoại) thành một khách; tên khác chữ hoặc khác số là hai khách (§3).
