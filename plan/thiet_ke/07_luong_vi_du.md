# 07 — Đi trọn luồng với câu hỏi thật (train)

Các ví dụ dưới đây lấy từ `data/train`. Đáp án chuẩn ghi ở cuối mỗi ví dụ để đối chiếu.

---

## Ví dụ 1 — Doanh thu so cùng kỳ, văn nói không dấu

`biz_118`, as_of `2025-10-08`: **"e dthu tu dau thang nay den het hnay hon hay kem cung ky thang trc bn phan tram"** → chuẩn: `percent -17.39`

| Bước | Kết quả |
|---|---|
| Pha A (đã chạy) | biz_118 = "sổ chi tiết bán hàng" (kiểu D) + giao hàng + công nợ theo hạn. CDM: `orders`, `order_lines`, `products`, `deliveries`, `debt_terms`. Manifest: `data_end=2026-09-10`, … |
| B1 Normalizer | `dthu→doanh thu`, `hnay→hôm nay`, `thang trc→tháng trước`, `bn→bao nhiêu`, `e` (bỏ) → "doanh thu từ đầu tháng này đến hết hôm nay hơn hay kém cùng kỳ tháng trước bao nhiêu phần trăm" |
| B2 Parser | `intent=revenue_change_pct`, `period={this_month_to_date}`, `compare={prev_month_same_days}`, `answer_type=percent` |
| B4 Period | Kỳ: 2025-10-01 → 2025-10-08. So: 2025-09-01 → 2025-09-08 (cùng số ngày, §2) |
| B5 | Cả hai kỳ nằm trong dữ liệu → answerable |
| B6 | `revenue(valid_orders(kỳ))` vs `revenue(valid_orders(so))` → `pct_change` |
| B8 | Đường chính, parser khớp regex (không có số), p≈0.9 → trả lời |
| B9 | `round(…, 2)` → `{"type": "percent", "answer": -17.39}` |

---

## Ví dụ 2 — Unanswerable vì shop không ghi thông tin

`biz_109`: **"cho hỏi trong tháng 12/2025, khách nữ chiếm bao nhiu % doanh thu"** → chuẩn: unanswerable

| Bước | Kết quả |
|---|---|
| B2 | `intent=revenue_share`, filter `{customer_gender: "nữ"}`, `unsupported_attribute="customer_gender"` |
| B5 | Manifest `customer_gender=false` (bảng khách của biz_109 không có cột giới tính) → **unanswerable** (rule 1) |
| B8 | Rule chắc chắn + manifest chắc chắn → p cao → nộp |
| B9 | `{"type": "unanswerable", "reason": "Dữ liệu không ghi giới tính khách"}` |

Đối chứng: biz_108 có cột `Giới tính` trong `DanhSachKhachHang` → cùng câu hỏi sẽ **answerable**.

---

## Ví dụ 3 — Unanswerable vì kỳ ngoài dữ liệu

`biz_106` (dữ liệu từ 02/2025): **"tổng dthu tháng 1 năm 2025 là bao nhiu"** → chuẩn: unanswerable

B2: `revenue`, `month{1, 2025}`. B4: [2025-01-01, 2025-01-31] nằm hoàn toàn trước `data_start=2025-02-01` → `out_of_range`. B5 → unanswerable (rule 3). **Không trả 0** (§7).

---

## Ví dụ 4 — Top mặt hàng, quy đổi đơn vị, xếp hạng

`biz_115`: **"liệt kê 5 mặt hangf chạy nhất thangs 2/2025"** → chuẩn: `list ["Gạch ống 8x8x18 Tuynel", "Ngói Đồng Nai 22 viên/m2", "Xi măng Hà Tiên PCB40 bao 50kg", "Xi măng INSEE Power-S bao 50kg", "Thép Pomina D10 cây 11.7m"]`

| Bước | Kết quả |
|---|---|
| B1 | `hangf→hàng`, `thangs→tháng` |
| B2 | `intent=top_items`, `k=5`, `rank_metric=qty_base` (mặc định "bán chạy" §3), `period=month{2, 2025}` |
| B6 | `lines_of(valid_orders)` → loại "Phí phục vụ" → Σ `qty_base` theo `product_id` → `rank(k=5, tie=code_asc)` |
| B8 | Kiểm tra hạng 5 và hạng 6 **không hoà** (nếu hoà → nghi sai, hạ tin cậy) |
| B9 | List `display_name` theo thứ tự |

---

## Ví dụ 5 — Tồn kho theo đơn vị lớn

`biz_121`, as_of `2026-09-20`: **"Xem giúp hết hôm nay trong kho còn bao nhiêu hộp Clorpheniramin 4mg DHG hộp 10 vỉ x 20 viên nguyên và bao nhiêu vỉ lẻ?"** → chuẩn: `list [16, 1]`

- **B3:** liên kết "Clorpheniramin 4mg DHG hộp 10 vỉ x 20 viên" → `SP…`.
- **B2:** `stock_big_unit`, `as_of_end_of{today}`.
- **Quy đổi:** theo `DanhSachQuyDoi` của shop, mặt hàng này có đơn vị cơ bản là **vỉ**, 1 hộp = 10 vỉ. Khớp §5: phần lẻ tính bằng đơn vị cơ bản.
- **Nguồn tồn:** biz_121 **không có file tồn kho**. Tồn được dựng từ **lô**: Σ số lượng nhập theo lô (`DonNhapHang_ChiTiet`) − Σ bán theo lô (`DonHang_Lo`) + Σ trả theo lô, tính đến hết 2026-09-20.
- **B6:** `divmod(tồn_vỉ, 10)` → `[nguyên, lẻ]`. Đáp án chuẩn `[16, 1]` tương ứng tồn 161 vỉ. Con số này sẽ được kiểm lại khi cài, như một test của bước tái tạo oracle.

> Bài học từ ví dụ này: `stock_at` phải hỗ trợ **ba nguồn tồn** theo thứ tự ưu tiên: (1) thẻ kho, (2) tồn theo lô (nhập lô − bán lô + trả lô), (3) snapshot tồn cuối dựng ngược bằng nhập/bán sau ngày hỏi. Manifest ghi shop dùng nguồn nào. Không nguồn nào có → unanswerable (ví dụ biz_130 "tồn kho Bia Tiger lon cuối ngày hôm nay" → unanswerable).

---

## Ví dụ 6 — Câu ngoài catalog (đường dự phòng)

Giả định ở private: **"tháng 5/2026 khu vực sân có bao nhiêu lượt khách"** (shop nhà hàng có `DanhSachHoaDonPhongBan`).

B2: không khớp intent nào → `intent=other`. B7: prompt chứa CDM (gồm bảng `dining`: order_id, table, area, guests), primitive `valid_orders`, rulebook §1–§2 → code:

```python
o = valid_orders(store, period("2026-05-01", "2026-05-31"))
answer = int(store.sql("select sum(guests) from dining where area = 'sân' and order_id in (select order_id from o)").fetchone()[0])
answer_type = "number"
```

Chạy hai lời giải → khớp → p≈0.6 (đường dự phòng) → trả lời nếu vượt ngưỡng đã hiệu chỉnh; không khớp → abstain.

---

## Ví dụ 7 — Rulebook private khác

Giả sử rulebook private đổi "ca sáng 06:00–13:59" thành "07:00–12:59". [R] phát hiện khác ở §2 dòng "Ca sáng, ca chiều" → dòng này ánh xạ được tham số → LLM đề xuất `shift_morning=("07:00","12:59")` → kiểm tra hợp lệ → `RuleConfig` mới. Câu về ca vẫn đi đường chính, kết quả theo luật mới.

Nếu rulebook private thêm "§6 Spa: một liệu trình nhiều buổi tính doanh thu theo buổi" → `changed_sections=["§6 Spa"]` → câu hỏi về shop spa dùng đường dự phòng với nguyên văn mục này trong prompt.
