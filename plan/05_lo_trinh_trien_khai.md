# 05 — Lộ trình triển khai

Mỗi giai đoạn có **Definition of Done (DoD)**. Không chuyển giai đoạn khi DoD chưa đạt (trừ khi ghi rõ lý do).

## G0 — Chuẩn bị (tuần 1)

- [ ] Lấy dữ liệu train/public; xin Docker guideline. (Công thức PA đã có: +1 / 0 / −1.)
- [ ] Chốt môi trường GPU dev (thuê/lab), cài vLLM + CUDA ≥ 12.8.
- [ ] EDA theo [04](04_du_lieu_va_eda.md), viết `plan/eda_findings.md`.
- [ ] Chia train-fit / dev / holdout theo business.
- [ ] Tải weights các model ứng viên ([03](03_lua_chon_model.md)), xác minh params/licence/ngày release.

**DoD:** có data, có taxonomy câu hỏi, có danh sách split, chạy được vLLM với ≥ 1 model ứng viên.

## G1 — Baseline end-to-end (tuần 1–2)

- [ ] `datamate/scoring.py` + `scripts/evaluate.py`: cài đúng luật chấm (normalize string, alias, list theo vị trí, table như tập, type phải khớp) + PA = (correct − wrong)/N. Unit test với các ví dụ trong đề.
- [ ] `loader.py`: đọc CSV/XLSX (mọi sheet)/SQLite → DataFrame + DuckDB.
- [ ] `profiler.py`: schema card gọn.
- [ ] `agent.py` tối giản: 1 prompt (rulebook + README + schema card + câu hỏi) → code → thực thi → formatter.
- [ ] `executor.py`: subprocess + timeout; `formatter.py`.
- [ ] `runner.py`: ghi submission + log tăng dần.
- [ ] Benchmark model nhanh trên dev (2–3 model).
- [ ] **Nộp public leaderboard lần 1.**

**DoD:** chạy hết train dev và public test không crash; có số PA dev & public đầu tiên.

## G2 — Tăng độ chính xác (tuần 2–4)

Vòng lặp: chạy dev → evaluator dump lỗi → gom nhóm lỗi → sửa nhóm lớn nhất → lặp.

- [ ] Helper library ([02 §4](02_kien_truc.md)): thời gian, Tết, valid_orders, revenue, giá vốn theo lô, rank tie-break, pct_change, find_entity — có unit test lấy từ rulebook.
- [ ] Normalizer câu hỏi (viết tắt, không dấu) + entity index.
- [ ] Few-shot động: lấy k câu train-fit giống nhất (BM25) kèm code lời giải đúng.
- [ ] Self-repair: traceback / kết quả rỗng → sửa ≤ 2–3 vòng.
- [ ] Profiler nâng cao: nhận diện cột tiền/ngày bẩn, cột trạng thái, khoá join.
- [ ] Thử phương án SQL (DuckDB) và model text-to-SQL; so với pandas.
- [ ] Chốt combo model ([03 §3](03_lua_chon_model.md)).

**DoD:** accuracy dev tăng ổn định qua mỗi vòng; mỗi nhóm lỗi lớn có ghi nhận nguyên nhân; holdout không tụt xa dev (≤ 5 điểm).

## G3 — Abstain & unanswerable (tuần 4–5)

- [ ] Tín hiệu tin cậy + self-consistency ([06](06_danh_gia_va_abstain.md)).
- [ ] Bộ phát hiện unanswerable (Planner + kiểm tra schema).
- [ ] Tune ngưỡng tin cậy để tối đa PA (+1/0/−1) trên dev; kiểm tra trên holdout.

**DoD:** PA dev có abstain > PA dev khi không bao giờ abstain (cải thiện giữ được trên holdout); chính sách abstain tổng quát (không phụ thuộc business).

## G4 — Fine-tune (tuần 4–7, song song G3)

- [ ] Generator dữ liệu tổng hợp + sinh trajectories ([07](07_fine_tuning.md)).
- [ ] SFT LoRA trên base đã chọn; so A/B với base trên dev + holdout.
- [ ] (Tuỳ) RL với reward thực thi.

**DoD:** model fine-tune tốt hơn base trên **holdout** (không chỉ dev), không vượt 15B, chạy được trên vLLM.

## G5 — Đóng gói & thi (tuần cuối trước deadline nộp solution)

- [ ] Dockerfile + predict.sh theo guideline BTC ([08](08_trien_khai_docker.md)).
- [ ] Chạy `--network none`, `/data` read-only, đo thời gian trên toàn bộ public (~1000 câu) → suy ra 500 câu private.
- [ ] Chạy 2 lần → |ΔPA| ≪ 0.03.
- [ ] README: mô tả, model + params + licence, cách chạy.
- [ ] Freeze, nộp image; chạy private test bằng **chính image đó**, nộp submission.

**DoD:** image chạy sạch trên máy mới; thời gian private ước tính ≤ 50% budget 6h; tái lập.

## Nhịp làm việc

- Nộp public leaderboard sau mỗi cải tiến lớn (theo giới hạn số lần nộp/ngày), ghi lại bảng điểm theo phiên bản trong `plan/changelog.md`.
- Mỗi thay đổi đánh giá trên dev + holdout trước khi nộp public — không tune theo public leaderboard (dễ overfit, và public cũng không được dùng để train).
