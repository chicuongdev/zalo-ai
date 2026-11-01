# 05 — Lộ trình triển khai

## Lịch theo ngày (hạn solution 16/11 23:59, private 20–23/11)

| Ngày | Việc chính | Đầu ra cuối ngày |
|---|---|---|
| **01–02/11** | Hoàn tất G0 (gitignore, chia fit/dev/holdout, lấy public test, thuê GPU). G1: `scoring.py` + `evaluate.py`, `parsers.py` + test | Đáp án train tự chấm đúng 100%; parser giá trị pass mọi mẫu EDA |
| **02–05/11** | G1: readers, detect, mapper (từ điển + luật), builder, validator; `calendar.py`, `periods.py` | CDM cho 30/30 shop, validator ≥ 0.99 |
| **04–08/11** | G2: primitives + intent theo tần suất; `label_plans.py` (parser regex/template); vòng lặp tái tạo oracle; answerability; formatter | Tái tạo oracle ≥ 95% (mục tiêu 98%) |
| **06–10/11** | G3 (cần GPU từ 06/11): vLLM + Qwen3-14B, normalizer, parser LLM, entity linker, pipeline, Writer/log. **Nộp public lần 1 khoảng 09/11** | Chạy end-to-end trên dev + public |
| **10–13/11** | G4: ngưỡng abstain (hiệu chỉnh trên dev), rulebook diff tối thiểu, fallback code agent bản gọn. G5 (nếu kịp): SFT LoRA parser trên plan vàng | PA dev tốt nhất; nộp public |
| **12–15/11** | G6: Dockerfile, `predict.sh`, chạy `--network none`, đo thời gian, chạy 2 lần kiểm tái lập, README | Image hoàn chỉnh |
| **15/11** | **Freeze code.** Chỉ sửa lỗi chặn | |
| **16/11** | **Nộp Docker** (trước 23:59, nên nộp sớm từ chiều) | |
| 20–23/11 | Chạy image đã freeze trên private, nộp `submission.jsonl` | |

**Cắt bớt so với kế hoạch đầy đủ do thời gian:**
- Bỏ RL (GRPO).
- Bỏ generator business tổng hợp.
- SFT parser chỉ làm nếu G3 xong đúng hạn.
- Đường dự phòng ở mức gọn: một lời giải + một vòng sửa, chỉ dùng khi còn thời gian.
- **Ưu tiên tuyệt đối: Pha A + thư viện ngữ nghĩa + parser.** Ba phần này quyết định phần lớn điểm.

**Đường găng:** CDM 30 shop (05/11) → tái tạo oracle (08/11) → parser LLM (10/11) → Docker (15/11). Nếu trễ một mốc, cắt tiếp G4/G5 chứ không lùi Docker.

Lộ trình đi theo các **tầng** của thiết kế ([thiet_ke/](thiet_ke/00_tong_quan.md)). Thứ tự được chọn để:

1. Phần **không cần GPU** làm trước, ngay trên máy local.
2. Mỗi giai đoạn có số đo riêng ([thiet_ke/09](thiet_ke/09_chien_luoc_kiem_thu.md)).

Mỗi giai đoạn có **DoD**. Không chuyển giai đoạn khi DoD chưa đạt, trừ khi ghi rõ lý do.

## G0 — Chuẩn bị

- [x] Lấy dữ liệu train (`train.zip` → `data/train/`).
- [x] EDA → [eda_findings.md](eda_findings.md).
- [x] Thiết kế hệ thống chi tiết → [thiet_ke/](thiet_ke/00_tong_quan.md).
- [x] Thêm `data/` vào `.gitignore`.
- [x] Chốt chia `fit / dev / holdout` theo business → [configs/splits.json](../configs/splits.json). Holdout gồm SQLite POS (123), nhiều nguồn trộn (124), sổ tay nhiều sheet (117), sổ tay nhà hàng (126), CSV nhiều bảng (129).
- [ ] Chốt môi trường GPU dev; tải và xác minh weights model ứng viên ([03](03_lua_chon_model.md)).
- [ ] Docker guideline từ BTC.

## G1 — Nền móng xác định (không cần GPU)

- [x] `datamate/scoring.py` + `scripts/evaluate.py` (luật chấm chính thức, PA). Unit test bằng ví dụ đề + round-trip toàn bộ `answers.jsonl` (đáp án chuẩn phải tự chấm là đúng 100%).
- [x] `ingest/parsers.py` (A3): tiền, số lượng+đơn vị, ngày, bool, mã. Unit test với mọi mẫu bẩn trong EDA.
- [x] `ingest/readers.py` + `detect.py` (A1–A2): đọc mọi file train, nhận diện header, gộp sheet theo tháng, bỏ dòng tổng/ghi chú (so khớp **giữ dấu** để không xoá nhầm họ "Tống", hàng "Công tắc").
- [x] `ingest/readme.py`: mô tả cột, ngày cuối dữ liệu, bảng quy đổi dạng text, quy ước.
- [x] `ingest/schema.py` + `mapper.py` (A4, tầng mô tả README → từ điển tên cột → fuzzy, có kiểm kiểu giá trị): 30/30 shop phân loại bảng & ánh xạ cột đúng khi rà tay.
- [x] `ingest/normalize.py` + `builder.py` (A5): CDM cho **30/30 shop**. Kiểm tra sớm: **doanh thu tháng/quý khớp 144/144 câu train**.
- [x] `ingest/cache.py`: cache Pha A (30 shop: 3,6 phút lần đầu, 5 giây khi có cache).
- [x] `validate.py` (A6) + manifest năng lực (`scripts/validate_shops.py`): 9 kiểm tra; **30/30 shop ≥ 0.9998**. Manifest gồm ~50 capability, `stock_source` (ledger/lots/snapshot), enums (kênh, hình thức thanh toán, nhóm hàng, đơn vị…). Manifest tính lại khi nạp cache, nên sửa validator không phải dựng lại Pha A.
- [x] `calendar.py`, `qa/periods.py` (B4) + unit test từng dòng rulebook §2 (`tests/test_periods.py`). Thêm kiểu kỳ `month_list`, `month_range`, `last_month`, `this/last_quarter`, `week_of`.

**DoD:** 30/30 shop dựng CDM, validator ≥ 0.99; tests period & parser pass 100%.

## G2 — Thư viện ngữ nghĩa & tái tạo oracle (không cần GPU)

- [x] `semantic/store.py` + `intents.py` (bán hàng, đơn, mặt hàng, khách) + `intents_ops.py` (công nợ, nhập, tồn/lô/hạn dùng, lãi, đợt giao, nhân viên): **~65 intent**. Dùng pandas trực tiếp thay DuckDB (bảng ≤ 200k dòng); DuckDB chỉ cần cho đường dự phòng sinh code.
- [x] `qa/normalize.py` (B1, bản đầu: Telex, teencode, từ vựng `configs/vocab.txt` học từ câu train) + `qa/rule_parser.py` (parser từ khoá sinh nhiều plan ứng viên; dùng để gán nhãn và làm kiểm chéo cho LLM).
- [x] `scripts/label_plans.py` + `scripts/show_misses.py`: plan ứng viên → thực thi → so đáp án → `out/gold_plans.jsonl` + `out/label_misses.jsonl` + `out/rule_parser_submission.jsonl`. Tiến độ tái tạo: 69,1% → 89,0% → 93,3% → 98,6% → **100% (3000/3000)**.
- [x] Sửa thư viện/Pha A theo danh sách lệch. Lỗi Pha A tìm được nhờ vòng này: tên hàng không dấu trên dòng bán không khớp danh mục (sửa `ProductIndex`, §8); kỳ hạn dùng ở tương lai bị cắt theo ngày dữ liệu; tên khách kèm số điện thoại.
- **Số đo phụ:** nếu nộp luôn plan đầu tiên của parser luật thì PA = 0,980 (train), 0,981 (dev), 0,977 (holdout). **Lưu ý:** parser luật được chỉnh khi đã nhìn câu hỏi của cả 30 shop, nên PA dev/holdout của parser luật là lạc quan. Riêng thư viện thì đã kiểm bằng đáp án, không bị ảnh hưởng.
- [ ] `qa/answerability.py` (B5) + kiểm trên 70 câu unanswerable.
- [ ] `qa/formatter.py` (B9).

**DoD:** tái tạo oracle ≥ 98% câu answerable train; answerability P ≥ 0.95, R ≥ 0.8; formatter round-trip 100%.

## G3 — Hiểu câu hỏi bằng LLM (cần GPU)

- [x] `llm.py` (vLLM + transformers dự phòng, greedy, tắt thinking), `qa/llm_parser.py` (catalog, ngữ cảnh shop, few-shot BM25, gắn thực thể bằng rapidfuzz), `scripts/eval_llm_parser.py` (5 cách kết hợp với parser luật; backend `gold` để thử không cần GPU), `scripts/make_kaggle_bundle.py`, `notebooks/kaggle_llm_benchmark.ipynb`.
- [ ] Chạy benchmark trên Kaggle: Qwen3.5-9B, Qwen3-14B-AWQ, Qwen3-8B, Qwen3.5-4B → `plan/benchmarks.md`, chốt model.
- [ ] `qa/normalize.py` (B1): bảng teencode/Telex từ train.
- [ ] `qa/parser.py` (B2): prompt + catalog + ngữ cảnh shop + few-shot BM25 + guided JSON; kiểm chéo regex.
- [ ] `qa/entities.py` (B3).
- [ ] `ingest/mapper.py` tầng LLM + kiểm thử leave-one-out kiểu nguồn.
- [ ] `qa/pipeline.py` + `main.py` + Writer/log → **chạy end-to-end trên train dev**.
- [ ] Chạy public test → **nộp public lần 1**.

**DoD:** intent exact-match ≥ 97%, plan ≥ 92% trên dev & holdout; end-to-end chạy hết public không crash.

## G4 — Dự phòng & quyết định

- [ ] `qa/fallback.py` (B7) + sandbox; thử bằng cách ép các intent đã biết đi đường dự phòng.
- [ ] `rules/analyzer.py` (R): diff rulebook, cập nhật `RuleConfig`, gắn `changed_sections`. Test bằng rulebook train **đã sửa giả lập**.
- [ ] `qa/decide.py` (B8): tín hiệu, hiệu chỉnh `p_correct` theo nhóm intent trên dev, chọn ngưỡng tối đa PA.

**DoD:** PA dev có abstain > PA khi không abstain; holdout giữ được cải thiện.

## G5 — Fine-tune (song song G4)

- [ ] SFT LoRA cho parser trên (câu → plan vàng) + paraphrase tổng hợp ([07](07_fine_tuning.md)).
- [ ] (Tuỳ) SFT cho đường dự phòng; RL với reward +1/0/−1.

**DoD:** bản fine-tune tốt hơn base trên **holdout**; tổng params ≤ 15B.

## G6 — Đóng gói & thi

- [ ] Dockerfile + `predict.sh` theo guideline BTC ([08](08_trien_khai_docker.md)).
- [ ] `--network none`, `/data` read-only; đo thời gian trên public; watchdog.
- [ ] Chạy 2 lần → |ΔPA| ≪ 0.03.
- [ ] README: model + params + licence.
- [ ] Freeze, nộp image; chạy private bằng chính image đó.

**DoD:** image chạy sạch trên máy mới; thời gian ước tính ≤ 50% budget; tái lập.

## Nhịp làm việc

- Mỗi phiên bản ghi số đo theo tầng vào `plan/changelog.md`.
- Không tune theo public leaderboard. Không dùng public/private để train.
