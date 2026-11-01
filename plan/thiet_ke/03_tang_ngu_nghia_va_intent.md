# 03 — Tầng ngữ nghĩa (Semantic Library), catalog intent & rulebook

## 1. Nguyên tắc

- Mỗi luật rulebook được cài đúng **một lần**, trong một hàm, có docstring trích **mục rulebook** (§1…§10) và unit test.
- Hàm nhận `ShopStore` + tham số đã giải (khoảng ngày cụ thể, id thực thể); trả **giá trị thô** (số/ngày/list/bảng). Không format.
- Tham số luật nằm trong `RuleConfig` (mặc định = rulebook train) để rulebook private khác ở các điểm "tham số hoá được" thì không phải sửa code.

## 2. Primitive (dùng chung bởi mọi intent)

```python
valid_orders(store, period, cfg)        # §1: không huỷ, không trả (kể cả trả một phần); đang giao vẫn tính; theo ngày đặt
all_orders(store, period)               # §1 tỉ lệ huỷ: mọi trạng thái
order_revenue(store, orders, cfg)       # Σ line_amount (sau giảm dòng), không trừ giảm giá đơn, không VAT, không ship
lines_of(store, orders, filters)        # filters: product, group, size, rx, ingredient, unit_base…
is_item(line)                           # §3: loại "Phí phục vụ" khỏi xếp hạng/đếm, vẫn tính doanh thu
customer_key(store)                     # §3: theo mã nếu có, không thì theo tên chuẩn hoá; khách lẻ loại
rank(df, by, id_col, k, cfg)            # giảm dần, hoà theo mã tăng dần (không mã → theo tên), < k → trả hết
debt_at(store, date, cfg)               # §4: đơn không huỷ (đơn trả vẫn tính), loại COD & sàn; phần chưa trả của grand_total
stock_at(store, product, date)          # §5: nguồn ưu tiên (1) thẻ kho, (2) lô: nhập lô − bán lô + trả lô,
                                        #     (3) snapshot tồn cuối dựng ngược bằng nhập/bán sau ngày; không có → unanswerable
avg_purchase_price(store, product, month, unit) # §5: bình quân theo số lượng nhập, bỏ phiếu huỷ
price_on(store, product, date, unit)    # §5: đơn giá trên dòng bán trước chiết khấu, cho 1 đv cơ bản, gồm cả đơn huỷ/trả
gross_profit(store, period, filters)    # §5: doanh thu − Σ qty × giá vốn ghi trên dòng bán
pct_change(new, old) / diff(new, old)   # §1: so kỳ trước, giảm ra số âm; chênh lệch = kỳ hỏi − kỳ so
as_of_cutoff(store, as_of)              # bản ghi sau as_of coi như chưa xảy ra (trừ trạng thái huỷ/trả)
```

## 3. Catalog intent (bản đầu từ EDA — sẽ chốt bằng gán nhãn có kiểm chứng, xem [09](09_chien_luoc_kiem_thu.md))

Mỗi intent có: **slots**, **type đáp án**, **yêu cầu năng lực** (để B5 quyết định unanswerable), **mục rulebook**.

| # | Intent | Slots chính | Type | Yêu cầu manifest | Rulebook |
|---|---|---|---|---|---|
| 1 | `revenue` | period, filters{product, group, size, rx, ingredient, payment_method, channel, customer_group, shift, staff} | number | order_lines (+ cột filter tương ứng) | §1, §2, §6 |
| 2 | `revenue_series` | periods[] | list | | §1 |
| 3 | `revenue_change_pct` | period, compare_period | percent | | §1, §2 |
| 4 | `revenue_diff` | period, compare_period | number | | §1 |
| 5 | `revenue_share` | filter, period | percent | cột filter | §1 (mẫu = cả shop, gồm vãng lai) |
| 6 | `revenue_multi` | period, filters[] (nhiều nhóm/hình thức) | list | | §1, §9 (thứ tự theo câu) |
| 7 | `order_count` | period, filters, amount_threshold{op, value} | number | | §1, §2 ("từ N trở lên" gồm N) |
| 8 | `cancel_count` | period | number | status | §1 |
| 9 | `cancel_rate` | period | percent | status | §1 |
| 10 | `avg_order_value` | period | number | | §3 (làm tròn đồng, nửa lên) |
| 11 | `best_day` / `best_month` | period hoặc months[], metric | date | | §9 (yyyy-mm cho tháng) |
| 12 | `days_meeting_threshold` | period, threshold | number | | §2 |
| 13 | `trend_increasing` | months[] | boolean | | §1 |
| 14 | `top_items` / `best_item` | period, k, metric{qty_base, revenue, gross_profit}, filters | list / string | (gross_profit → line_cost) | §3, §5 |
| 15 | `item_qty` | product, period, unit | number | | §3, §10 |
| 16 | `qty_by_base_unit` | unit, period | number | | §3 ("cộng mọi mặt hàng tính theo lon") |
| 17 | `items_in_n_orders` | period, n, op | number | | §2 |
| 18 | `unsold_items` | period | number / list | | §5 (đã từng bán trước kỳ) |
| 19 | `price_on_day` | product, date, unit | number | | §5 |
| 20 | `price_increase_effect` | product, date, n_days, unit | percent | price_history | §5 |
| 21 | `top_customers` / `best_customer` | period, k, metric{revenue, orders} | list / string | customers | §3 |
| 22 | `customer_count` | period, condition{min_orders, …} | number | | §3 |
| 23 | `best_staff` | period | string | staff | §3 |
| 24 | `debt_total` | as_of_date, filters{age_gt} | number | payments/debt | §4 |
| 25 | `debtor_count` | as_of_date | number | | §4 |
| 26 | `top_debtors` | as_of_date, k | table | | §4, §9 |
| 27 | `debt_aging_buckets` | as_of_date, buckets[] | list | | §4 |
| 28 | `debt_new_and_paid` | period, customer? | list / number | | §4 |
| 29 | `stock_qty` | product, as_of_date, unit | number | stock_* | §2, §5 |
| 30 | `stock_big_unit` | product, as_of_date | list `[nguyên, lẻ]` | stock + conversions | §5 |
| 31 | `stock_value` | as_of_date | number | stock + catalog_cost | §5 |
| 32 | `out_of_stock_items` | date | number / list | stock | §5 |
| 33 | `purchase_total` | period, supplier? | number | purchases | §5 |
| 34 | `top_supplier` | period | string | purchases | §5 |
| 35 | `avg_purchase_price` | product, month, unit | number | purchase_lines | §5 |
| 36 | `purchase_minus_sales` | product, period | number | | §5 |
| 37 | `gross_profit` | period, filters | number | line_cost | §5 |
| 38 | `net_profit` | month | number | line_cost + expenses | §5 |
| 39 | `rx_share` / revenue theo kê đơn | period | percent / number | prescription | §6 Nhà thuốc |
| 40 | `expiring_lots` | n_days, metric{list, value} | list / number | lots + expiry | §6 Nhà thuốc |
| 41 | `nearest_expiry_lot` | product, date | date | lots | §6 Nhà thuốc |
| 42 | `size_qty` | size, period | number | | §6 Cà phê |
| 43 | `delivery_trips` | month | number | deliveries | §6 VLXD |
| 44 | `shift_revenue` / so ca | period, shift | number / percent | order_ts | §2 |
| 45 | `tet_*` | Tết năm Y, so với trước Tết | number / percent | | §2 |
| 99 | `other` | (câu ngoài catalog) | — | — | → đường dự phòng B7 |

Câu nhiều số (ví dụ "nợ thêm bao nhiêu và trả được bao nhiêu") → QueryPlan có `outputs[]` theo **đúng thứ tự câu hỏi**, đáp án là list (§9).

## 4. `RuleConfig` & xử lý rulebook private khác train

```python
@dataclass(frozen=True)
class RuleConfig:
    week_start: int = 0                       # thứ Hai
    exclude_partial_return_orders: bool = True
    count_delivering_as_sale: bool = True
    this_month_compare_same_days: bool = True
    last_n_days_includes_today: bool = True
    shift_morning: tuple = ("06:00", "13:59"); shift_afternoon: tuple = ("14:00", "21:59")
    tet_window: tuple = ((12, 23), (1, 10))   # 23 tháng Chạp → mùng 10 tháng Giêng
    best_seller_metric: str = "qty_base"
    tie_break: str = "code_asc"
    money_round: str = "half_up"; pct_decimals: int = 2
    cod_is_cash: bool = False
    walk_in_belongs_to_group: bool = False
    gross_profit_cost_source: str = "line_cost"
    ...
```

**Rulebook Analyzer [R]** khi khởi động:

1. Tách rulebook runtime thành các mục/dòng bảng; so với bản train đóng gói sẵn trong image (diff theo từng dòng luật).
2. **Giống hệt** → dùng `RuleConfig` mặc định (trường hợp phổ biến nhất).
3. **Khác ở dòng ánh xạ được tham số** (ví dụ ca sáng 07:00–12:59) → LLM đọc dòng mới + trường `RuleConfig` liên quan → đề xuất giá trị mới (guided JSON) → kiểm tra tính hợp lệ → áp dụng.
4. **Khác ở dòng không tham số hoá được** hoặc **có mục mới** (ví dụ ngành mới ở §6) → ghi `changed_sections`. Mọi intent tham chiếu các mục đó được **chuyển sang đường dự phòng B7**, kèm nguyên văn mục rulebook mới trong prompt.
5. Rulebook luôn được đưa (rút gọn theo mục liên quan) vào prompt của B7.

## 5. Calendar [C]

- Nạp `calendar.csv` → bảng `date ↔ (lunar_day, lunar_month, lunar_year, leap)`.
- `tet_window(Y)`: tìm ngày dương của (23, tháng 12, năm âm Y−1, không nhuận) và (10, tháng 1, năm âm Y) → khoảng đóng.
- `before_tet(Y)`: cùng số ngày ngay trước 23 tháng Chạp.
