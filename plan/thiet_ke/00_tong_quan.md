# 00 — Tổng quan thiết kế hệ thống

> Bộ tài liệu này trả lời: **hệ thống gồm những thành phần nào, chúng kết hợp ra sao, dữ liệu chảy thế nào, và mỗi thành phần có đầu vào/đầu ra gì.** Mọi quyết định đều dựa trên EDA thật ([../eda_findings.md](../eda_findings.md)).

## 1. Ý tưởng cốt lõi

Đáp án chuẩn do một **oracle xác định** tính từ dữ liệu theo rulebook. Câu hỏi được sinh từ khoảng 40–60 template rồi diễn đạt lại kiểu văn nói. Vì vậy hệ thống tốt nhất là **tái tạo oracle**:

```
   dữ liệu thô lộn xộn ──(1) chuẩn hoá──▶ mô hình dữ liệu chuẩn (giống nhau cho mọi shop)
   rulebook ─────────────(2) cài đặt──▶ thư viện ngữ nghĩa xác định (hàm doanh thu, công nợ, tồn…)
   câu hỏi văn nói ──────(3) LLM hiểu──▶ kế hoạch truy vấn có cấu trúc (intent + tham số)
                         (4) thực thi xác định ──▶ (5) kiểm chứng ──▶ (6) đáp án đúng format / abstain
```

LLM open-source chỉ làm những việc **cần hiểu ngôn ngữ**:

- Ánh xạ cột thô sang trường chuẩn (mỗi shop một lần).
- Phân tích câu hỏi thành kế hoạch truy vấn.
- Sinh code cho câu hỏi ngoài catalog (đường dự phòng).

**Mọi con số đều do code xác định tính.**

## 2. Hai pha chạy

| Pha | Chạy khi nào | Đơn vị | Làm gì | Thời gian dự kiến |
|---|---|---|---|---|
| **Pha A — Xây "kho tri thức" mỗi shop** | Đầu phiên chạy, trước khi trả lời | Mỗi `business_id` một lần | Đọc file → nhận diện bảng → parse giá trị → ánh xạ cột (heuristic + LLM) → mô hình chuẩn trong DuckDB → kiểm tra hợp lệ → manifest năng lực + chỉ mục thực thể | 0.5–3 phút/shop, chạy song song |
| **Pha B — Trả lời câu hỏi** | Sau khi shop của câu hỏi xong Pha A | Mỗi câu | Chuẩn hoá câu → LLM phân tích thành QueryPlan → liên kết thực thể → giải kỳ thời gian → kiểm tra trả lời được → thực thi hàm ngữ nghĩa (hoặc sinh code dự phòng) → kiểm chứng → định dạng → ghi | 2–15 giây/câu, chạy song song |

Cả hai pha dùng chung **một server LLM** (vLLM) và một thư viện ngữ nghĩa.

## 3. Sơ đồ thành phần

```
┌──────────────────────────────────────── predict.sh / main.py (Orchestrator) ─────────────────────────────────────────┐
│                                                                                                                      │
│  /data/rulebook.md ──▶ [R] Rulebook Analyzer ──▶ RuleConfig + danh sách mục rulebook bị thay đổi so với bản train    │
│  /data/calendar.csv ─▶ [C] Calendar ──────────▶ tra âm–dương, cửa sổ Tết                                             │
│                                                                                                                      │
│  ── PHA A (mỗi business, process pool CPU) ────────────────────────────────────────────────────────────────────────  │
│  /data/data/<biz>/ ─▶ [A1] File Reader ─▶ [A2] Table Detector ─▶ [A3] Value Parsers ─▶ [A4] Schema Mapper (LLM) ─┐   │
│                                                                                                                │   │
│        ┌───────────────────────────────────────────────────────────────────────────────────────────────────────┘   │
│        ▼                                                                                                           │
│  [A5] Canonical Builder ─▶ [A6] Validator ─▶ ShopStore = { DuckDB chuẩn, Manifest năng lực, Entity Index }        │
│                                                                                                                      │
│  ── PHA B (mỗi câu, async worker pool) ────────────────────────────────────────────────────────────────────────────  │
│  question ─▶ [B1] Normalizer ─▶ [B2] Question Parser (LLM, JSON schema) ─▶ QueryPlan                                 │
│                                    │                                         │                                       │
│                                    │                    ┌────────────────────┼────────────────────┐                  │
│                                    │                    ▼                    ▼                    ▼                  │
│                                    │          [B3] Entity Linker    [B4] Period Resolver   [B5] Answerability       │
│                                    │                    └────────────────────┼────────────────────┘                  │
│                                    ▼                                         ▼                                       │
│                         (intent ngoài catalog / mục          [B6] Plan Executor ──▶ Semantic Library [S]             │
│                          rulebook bị đổi)                                    │                                       │
│                                    └──────────▶ [B7] Fallback Code Agent (LLM + sandbox) ─┐                         │
│                                                                              ▼              ▼                        │
│                                                                    [B8] Verifier & Decision ─▶ [B9] Formatter        │
│                                                                                                 │                    │
│                                                     /result/submission.jsonl ◀── [B10] Writer ◀─┘ ──▶ /result/logs/   │
│                                                                                                                      │
│  [L] LLM Service (vLLM, 2× RTX 5090) ◀── dùng bởi A4, B2, B3 (khi mơ hồ), B7                                         │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## 4. Vai trò từng thành phần (tóm tắt — chi tiết ở các file sau)

| Mã | Thành phần | Đầu vào → Đầu ra | Dùng LLM? | Tài liệu |
|---|---|---|---|---|
| R | Rulebook Analyzer | rulebook.md → `RuleConfig`, `changed_sections` | Có (chỉ khi rulebook khác train) | [03](03_tang_ngu_nghia_va_intent.md) |
| C | Calendar | calendar.csv → hàm âm/dương | Không | [03](03_tang_ngu_nghia_va_intent.md) |
| A1–A3 | Reader, Table Detector, Parsers | file → bảng logic đã parse kiểu | Không | [02](02_nap_va_chuan_hoa_du_lieu.md) |
| A4 | Schema Mapper | bảng logic + README → `MappingSpec` | Có (heuristic trước, LLM khi chưa chắc) | [02](02_nap_va_chuan_hoa_du_lieu.md) |
| A5–A6 | Builder, Validator | MappingSpec → DuckDB chuẩn + manifest + báo cáo kiểm tra | Không | [01](01_mo_hinh_du_lieu_chuan.md), [02](02_nap_va_chuan_hoa_du_lieu.md) |
| S | Semantic Library | hàm Python cài rulebook trên mô hình chuẩn | Không | [03](03_tang_ngu_nghia_va_intent.md) |
| B1 | Normalizer | câu thô → câu sửa Telex/teencode + bản không dấu | Không | [04](04_hieu_cau_hoi.md) |
| B2 | Question Parser | câu + ngữ cảnh shop → `QueryPlan` (JSON) | **Có** (guided JSON) | [04](04_hieu_cau_hoi.md) |
| B3 | Entity Linker | cụm tên trong câu → mã thực thể | Fuzzy + LLM khi mơ hồ | [04](04_hieu_cau_hoi.md) |
| B4 | Period Resolver | biểu thức kỳ → khoảng ngày cụ thể | Không | [04](04_hieu_cau_hoi.md) |
| B5 | Answerability | QueryPlan + manifest → trả lời được / unanswerable | Không | [05](05_thuc_thi_kiem_chung_tra_loi.md) |
| B6 | Plan Executor | QueryPlan đã giải → giá trị thô | Không | [05](05_thuc_thi_kiem_chung_tra_loi.md) |
| B7 | Fallback Code Agent | câu + schema chuẩn + rulebook → code → giá trị | **Có** | [05](05_thuc_thi_kiem_chung_tra_loi.md) |
| B8 | Verifier & Decision | giá trị + tín hiệu → trả lời / abstain | Không (classifier nhỏ) | [05](05_thuc_thi_kiem_chung_tra_loi.md) |
| B9–B10 | Formatter, Writer | giá trị + type → dòng JSONL + log | Không | [05](05_thuc_thi_kiem_chung_tra_loi.md), [06](06_runtime_va_van_hanh.md) |
| L | LLM Service | prompt → text/JSON | — | [06](06_runtime_va_van_hanh.md), [../03_lua_chon_model.md](../03_lua_chon_model.md) |

## 5. Vì sao chọn kiến trúc này (so với "LLM sinh code cho mọi câu")

| Tiêu chí | Sinh code tự do mỗi câu | **Chuẩn hoá + thư viện ngữ nghĩa + parser** |
|---|---|---|
| Độ chính xác với luật tinh vi (bỏ cả đơn có trả một phần, cùng số ngày tháng trước, tie-break mã…) | LLM 14B dễ quên luật → sai âm thầm | Luật cài một lần, test kỹ, đúng mọi lần |
| Dữ liệu bẩn (tiền `1tr440`, header 2 tầng, mỗi tháng một sheet) | Phải xử lý lại ở mỗi câu → dễ sai | Xử lý một lần ở Pha A, có kiểm tra |
| Phát hiện unanswerable | Khó, LLM hay "bịa" | So manifest năng lực với yêu cầu intent, gần như xác định |
| Tốc độ (6h/500 câu, xếp hạng phụ theo thời gian) | Nhiều vòng sinh/sửa code | Một lần gọi LLM ngắn mỗi câu |
| Tái lập (Rule 8) | Code sinh ra dao động | Phần xác định chiếm phần lớn |
| Câu hỏi/ngành mới ở private | Tổng quát hơn | **Cần đường dự phòng** sinh code (B7) |

⇒ Kết hợp cả hai: đường chính **xác định** cho intent đã biết; đường dự phòng **sinh code trên mô hình chuẩn** cho phần còn lại.

## 6. Danh sách tài liệu thiết kế

| File | Nội dung |
|---|---|
| [01_mo_hinh_du_lieu_chuan.md](01_mo_hinh_du_lieu_chuan.md) | Mô hình dữ liệu chuẩn (bảng, trường, ngữ nghĩa), manifest năng lực |
| [02_nap_va_chuan_hoa_du_lieu.md](02_nap_va_chuan_hoa_du_lieu.md) | Pha A chi tiết: đọc file, nhận diện bảng, parser giá trị, ánh xạ cột, kiểm tra |
| [03_tang_ngu_nghia_va_intent.md](03_tang_ngu_nghia_va_intent.md) | Thư viện ngữ nghĩa, catalog intent, RuleConfig, xử lý rulebook khác |
| [04_hieu_cau_hoi.md](04_hieu_cau_hoi.md) | Normalizer, QueryPlan schema, parser LLM, entity linking, period resolver |
| [05_thuc_thi_kiem_chung_tra_loi.md](05_thuc_thi_kiem_chung_tra_loi.md) | Executor, answerability, fallback code agent, verifier, formatter |
| [06_runtime_va_van_hanh.md](06_runtime_va_van_hanh.md) | Tiến trình, song song, cache, log, time budget, determinism |
| [07_luong_vi_du.md](07_luong_vi_du.md) | Đi trọn luồng với câu hỏi thật từ train |
| [08_hop_dong_module_va_repo.md](08_hop_dong_module_va_repo.md) | Kiểu dữ liệu giữa các module, cấu trúc repo, cấu hình |
| [09_chien_luoc_kiem_thu.md](09_chien_luoc_kiem_thu.md) | Kiểm thử từng tầng, bộ đo, cách phát triển không cần GPU |
