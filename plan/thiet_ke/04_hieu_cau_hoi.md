# 04 — Hiểu câu hỏi: Normalizer, Parser, Entity Linker, Period Resolver

```
question ─▶ [B1] Normalizer ─▶ {q_fixed, q_noaccent, regex_hints}
                                   │
                                   ▼
            [B2] Question Parser (LLM, guided JSON) ──▶ QueryPlan (thô: còn chứa "cụm tên", "biểu thức kỳ")
                                   │
                 ┌─────────────────┴──────────────────┐
                 ▼                                    ▼
          [B3] Entity Linker                   [B4] Period Resolver
          cụm tên → id thực thể                biểu thức kỳ → [from, to] cụ thể
                 └─────────────────┬──────────────────┘
                                   ▼
                          ResolvedPlan  ──▶ [B5] Answerability ──▶ [B6]/[B7]
```

## B1 — Normalizer (xác định, không LLM)

1. NFC, lowercase bản phụ, chuẩn khoảng trắng.
2. **Sửa lỗi gõ Telex** khi một từ có ký tự dấu thừa ở cuối và bản sửa nằm trong từ điển tiếng Việt: `tieenf→tiền`, `thangs→tháng`, `nhieeuf→nhiều`, `cuwar hangf→cửa hàng`, `ddown→đơn`, `hoom→hôm`, `vaayj→vậy`. Sửa trên từ không có trong từ điển và không phải tên thực thể.
3. **Mở rộng teencode** bằng bảng từ (xây từ train): `dthu→doanh thu`, `bn/bnhiu/bnhiêu/nhiêu→bao nhiêu`, `hnay→hôm nay`, `hqua/bữa qua→hôm qua`, `dc/đc→được`, `ko/k/hông/hok→không`, `sp→sản phẩm`, `th trc/thang trc→tháng trước`, `tm→tiền mặt`, `ck→chuyển khoản`, `j→gì`, `z/ha/nhỉ/đó/ạ` (bỏ), `total→tổng`, `bill/order→đơn`, `best seller→bán chạy nhất`.
4. Sinh `q_noaccent` (bỏ dấu, đ→d) dùng cho regex và tra thực thể.
5. **Regex hints** (độc lập với LLM, dùng để kiểm chéo): ngày `dd/mm/yyyy`, `tháng M/YYYY`, `tháng M năm YYYY`, `quý Q`, `N ngày gần nhất`, số tiền `9.600.000 đồng`, `top K`/`K mặt hàng`, ngưỡng `từ N trở lên / ít nhất N / ≥ N / quá N`.

## B2 — Question Parser (LLM)

- Model: model chính (Qwen3-14B hoặc bản fine-tune LoRA của nó), **guided decoding theo JSON schema** (vLLM `guided_json` / xgrammar) ⇒ đầu ra luôn parse được, intent luôn thuộc catalog.
- Chế độ: không bật thinking (nhanh, ổn định). Chỉ bật thinking cho lần gọi lại khi kiểm chéo thất bại.
- Prompt (dùng prefix caching: phần tĩnh giống nhau cho mọi câu của một shop):
  1. Mô tả nhiệm vụ + **catalog intent** (tên, mô tả một dòng, slots, ví dụ).
  2. Tóm tắt rulebook §2 (cách nói thời gian) + §9 (thứ tự nhiều số).
  3. **Ngữ cảnh shop**: ngành, các năng lực có/không, enums (nhóm hàng, kênh, phương thức TT, nhóm khách), đơn vị cơ bản phổ biến.
  4. **Few-shot động**: 6–8 câu train **giống nhất** (BM25 trên `q_noaccent`) cùng QueryPlan đã kiểm chứng.
  5. Câu hỏi đã chuẩn hoá + câu gốc + `as_of_date`.

### Schema `QueryPlan` (rút gọn)

```json
{
  "intent": "revenue_change_pct",
  "outputs": [                                  // ≥1; nhiều phần tử → đáp án list theo thứ tự câu hỏi
    {"metric": "revenue",
     "period": {"kind": "this_month_to_date"},
     "compare": {"kind": "prev_month_same_days"},
     "filters": {"product": null, "group": null, "size": null, "payment_method": null,
                 "channel": null, "customer_group": null, "shift": null, "rx": null, "ingredient": null},
     "k": null, "rank_metric": null, "threshold": null, "unit": null}
  ],
  "entities": [{"kind": "product", "mention": "nuoc suoi lavie 1.5L"}],
  "answer_type": "percent",
  "requires": ["order_lines"],                   // gợi ý thêm cho B5
  "unsupported_attribute": null                  // ví dụ "customer_gender", "customer_address", "staff_attitude"
}
```

**Biểu thức kỳ** (`period.kind`) — LLM chỉ **gắn nhãn**, không tự tính ngày:
`day{date}` · `today` · `yesterday` · `this_week` · `last_week` · `this_month_to_date` · `prev_month_same_days` · `month{m, y?}` · `quarter{q, y?}` · `year{y}` · `ytd` · `range{from, to}` · `last_n_days{n}` · `as_of_end_of{date|today}` · `tet{y}` · `before_tet{y}` · `n_days_from{date, n}` · `n_days_before{date, n}` · `months_ending_at{m, y, count}` · `prev_period` (kỳ liền trước của kỳ chính) · `same_period_last_year`.

### Kiểm chéo parser (tín hiệu tin cậy)

- Ngày/tháng/số trong QueryPlan phải khớp `regex_hints` (ví dụ câu có "tháng 3/2026" mà plan lại là tháng 4 → sai).
- Intent phù hợp với `answer_type` và từ khoá (ví dụ "%" ↔ percent).
- Lệch → gọi lại một lần với thinking + thông báo lệch → vẫn lệch thì hạ độ tin cậy mạnh.

## B3 — Entity Linker

1. Ứng viên: tra `entity_index` theo `norm`, `norm_noaccent`, token-set ratio (rapidfuzz), khớp mã trực tiếp (`SP0042`). Lấy top 5.
2. Quyết định:
   - Điểm cao nhất ≥ 95 và cách ứng viên thứ hai ≥ 8 → chọn luôn.
   - Ngược lại → LLM chọn trong top 5 (guided enum, có thêm lựa chọn "không có").
3. "Không có" hoặc điểm quá thấp → **thực thể không tồn tại**. Từ đó: nếu câu hỏi về một mặt hàng/khách cụ thể → nhiều khả năng unanswerable, nhưng chỉ kết luận khi điểm đủ chắc; còn lại abstain.
4. Ghi `link_margin` vào tín hiệu tin cậy.

## B4 — Period Resolver (xác định, cài rulebook §2)

Đầu vào: biểu thức kỳ + `as_of_date` + `RuleConfig` + Calendar. Đầu ra: `[from, to]` (ngày, đóng hai đầu) hoặc danh sách khoảng.

| Biểu thức | Luật |
|---|---|
| `this_week` | thứ Hai của tuần chứa hôm nay → hết hôm nay |
| `last_week` | cả tuần liền trước, T2 → CN |
| `this_month_to_date` | ngày 1 → hết hôm nay |
| `prev_month_same_days` | ngày 1 → ngày trùng số hôm nay của tháng trước; không có ngày đó → hết tháng trước |
| `month{m}` không năm | năm nay nếu không sau hôm nay, ngược lại năm trước |
| `last_n_days{n}` | n ngày kể cả hôm nay |
| `tet{y}` | 23/12 âm (năm âm y−1) → hết 10/1 âm (năm âm y) |
| `as_of_end_of{d}` | trạng thái lúc hết ngày d, mọi phát sinh từ đầu dữ liệu |
| `n_days_from{d, n}` / `n_days_before{d, n}` | [d, d+n−1] / [d−n, d−1] |

Sau khi giải: cắt với `[data_start, min(data_end, as_of)]`. Kỳ **hoàn toàn ngoài** dữ liệu → `out_of_range=true` (B5 quyết định unanswerable). Kỳ chỉ có một phần trong dữ liệu → tính trên phần có (§7).
