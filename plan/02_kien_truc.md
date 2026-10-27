# 02 — Kiến trúc agent

## 1. Nguyên tắc

1. **LLM làm phần "hiểu", code làm phần "tính".** LLM không bao giờ tự tính số; mọi con số đến từ code pandas/SQL được thực thi.
2. **Logic khó & dễ sai viết sẵn thành helper xác định** (thời gian, Tết, xếp hạng, doanh thu theo rulebook, chuẩn hoá tên) — LLM chỉ gọi.
3. **Tổng quát theo dữ liệu**: không có nhánh nào phụ thuộc business_id/ngành cụ thể; schema được suy ra lúc runtime.
4. **Mỗi bước có log** (prompt, code, output, thời gian) để debug và để giải trình với BTC (Rule 8).
5. **Biết dừng**: có tín hiệu tin cậy → abstain khi không chắc.

## 2. Pipeline

```
                ┌────────────────────── mỗi business (cache) ──────────────────────┐
 data/<biz>/ ──▶│ [1] Loader ──▶ [2] Profiler ──▶ schema card + entity index        │
 rulebook.md ──▶│ [3] Rulebook parser ──▶ rule card (định nghĩa mặc định)           │
 calendar.csv ─▶│ [4] Calendar helper (âm–dương, cửa sổ Tết)                        │
                └───────────────────────────────────────────────────────────────────┘
                                         │
 question + as_of_date                   ▼
   └─▶ [5] Normalizer (khôi phục dấu, mở rộng viết tắt, trích thực thể/thời gian)
   └─▶ [6] Context builder (schema card + rule card + README rút gọn + few-shot)
   └─▶ [7] Planner LLM  → {answer_type, answerable?, tables/cột cần, định nghĩa áp dụng, kỳ thời gian}
   └─▶ [8] Coder LLM    → code Python (pandas/duckdb + helper) gán biến `answer`
   └─▶ [9] Sandbox executor (subprocess, timeout, chỉ ghi /tmp)
            └─ lỗi / kết quả bất thường → traceback quay lại [8] (≤ 2–3 vòng)
   └─▶ [10] Verifier   (type khớp? NaN/rỗng? dấu %? hoà ở biên ranking? self-consistency)
   └─▶ [11] Decision   (trả lời / unanswerable / abstain theo ngưỡng tin cậy)
   └─▶ [12] Formatter  (làm tròn, ISO date / yyyy-mm, list, table, ưu tiên tên đúng như data/mã)
   └─▶ [13] Runner     ghi 1 dòng submission.jsonl + 1 log /result/logs/<id>.json NGAY sau mỗi câu
```

## 3. Mô tả module

| # | Module | Vào → Ra | Ghi chú |
|---|---|---|---|
| 1 | **Loader** | thư mục business → `dict[name, DataFrame]` + DuckDB connection | CSV: dò encoding (utf-8-sig, cp1258…), delimiter, header lệch. XLSX: **mọi sheet**, header không ở dòng 1, ô gộp. SQLite: mọi bảng/view. Đăng ký tất cả vào DuckDB để LLM có thể viết SQL |
| 2 | **Profiler** | DataFrames → *schema card* (text gọn) | Mỗi cột: kiểu suy luận (ngày/tiền/số/phân loại/văn bản), % null, giá trị mẫu, min/max, cardinality; ứng viên khoá join; khoảng thời gian dữ liệu; cột trạng thái (huỷ/trả), cột mã/tên SP. Cắt gọn để vừa context |
| 2b | **Entity index** | các cột tên (SP, khách, chi nhánh, NCC) → index | Tra mờ có dấu/không dấu (rapidfuzz), map tên ↔ mã ↔ các cách viết |
| 3 | **Rulebook parser** | rulebook.md → rule card | Đưa nguyên văn (rút gọn) vào prompt; trích tham số chính (định nghĩa tuần, doanh thu, Tết…) cho helper khi nhận diện được, mặc định theo văn bản |
| 4 | **Calendar helper** | calendar.csv → hàm | `lunar_to_solar`, `tet_window(year)`, `tet_day(year)` |
| 5 | **Normalizer** | câu hỏi thô → câu chuẩn + slot | Từ điển viết tắt (sp, dc, ko, đt, tr, k…), khôi phục dấu bằng LLM; trích cụm thời gian & thực thể, khớp với entity index |
| 6 | **Context builder** | → prompt | Few-shot chọn bằng BM25/embedder nhỏ trên câu hỏi **train** |
| 7 | **Planner** | → JSON kế hoạch | Có thể gộp với Coder nếu dùng 1 model (thử cả hai) |
| 8 | **Coder** | → code | Môi trường có sẵn `tables`, `duckdb`, `helpers`, `AS_OF` |
| 9 | **Executor** | code → kết quả/traceback | Subprocess riêng, giới hạn thời gian (vd 30s) & RAM; DataFrame đã load giữ trong worker dài hạn để khỏi load lại |
| 10 | **Verifier** | kết quả → điểm tin cậy | Xem [06](06_danh_gia_va_abstain.md) |
| 12 | **Formatter** | kết quả + type → JSON đúng luật | Không bao giờ để LLM tự format số |
| 13 | **Runner** | questions.jsonl → submission | Nhóm theo business, chạy song song nhiều câu (vLLM batching), quản lý time budget |

## 4. Thư viện helper dự kiến (`helpers`)

```python
# thời gian
period("tuần rồi", as_of)           -> (start, end)     # tuần T2–CN, tháng này đến hết as_of…
same_period_last_year(start, end)   -> (start, end)
tet_window(year)                    -> (start, end)     # 23 Chạp → mùng 10 theo calendar.csv
# nghiệp vụ (tham số hoá theo rule card)
valid_orders(df, rules)             -> df               # loại huỷ / có hàng trả
revenue(lines, rules)               -> Series/float     # sau giảm giá dòng, không VAT/ship/voucher
weighted_avg_cost(purchases, item)  -> float            # bình quân gia quyền theo lô
# xếp hạng & thực thể
rank(df, by, code_col, k, asc=False)-> list             # tie-break mã tăng dần, <k → trả hết
find_entity(text, kind)             -> code, canonical name
pct_change(new, old)                -> float (đơn vị %)
```

Danh sách thật sẽ chốt sau EDA ([04](04_du_lieu_va_eda.md)) — chỉ viết helper cho những mẫu xuất hiện nhiều trong train.

## 5. Cấu trúc repo dự kiến

```
zaloai/
├── subject/                 # đề bài (giữ nguyên)
├── plan/                    # kế hoạch (thư mục này)
├── data/                    # train/, public/ (không commit)
├── datamate/
│   ├── loader.py  profiler.py  entities.py  calendar.py  rulebook.py
│   ├── helpers.py           # API cho code sinh ra
│   ├── normalizer.py  prompts/  llm.py (client vLLM)
│   ├── agent.py             # orchestration [5]→[12]
│   ├── executor.py  verifier.py  formatter.py
│   ├── scoring.py           # luật chấm (dùng chung evaluator + verifier)
│   └── runner.py
├── scripts/  evaluate.py  eda.py  bench_models.py  make_synthetic.py
├── training/                # SFT/RL config & script
├── tests/
├── Dockerfile  predict.sh  requirements.txt  README.md
```

## 6. Phương án đối chứng (thử trong G1–G2)

- **A. Code pandas** (mặc định) — linh hoạt với dữ liệu bẩn.
- **B. SQL qua DuckDB** — model text-to-SQL chuyên dụng mạnh ở đây; dễ kiểm chứng.
- **C. Kết hợp**: Coder được chọn pandas hoặc SQL; self-consistency giữa 2 lời giải A & B (hai cách tính khác nhau cùng ra một số ⇒ tin cậy cao).
