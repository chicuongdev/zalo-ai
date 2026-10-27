# 07 — Fine-tuning model open-source

Mục tiêu: model open-source quen với **API helper của ta, kiểu dữ liệu bẩn của hộ kinh doanh VN, câu hỏi văn nói không dấu, và format đáp án** → ít lỗi code, đúng định nghĩa nghiệp vụ hơn. Chỉ bắt đầu khi baseline G2 đã ổn định (để biết lỗi nào cần fine-tune giải).

Rule 6: chỉ dùng **train + dữ liệu tự sinh + dataset/model public**. **Không** dùng câu hỏi/dữ liệu public test hay private test.

## 1. Nguồn dữ liệu huấn luyện

### 1.1 Trajectories từ train (rejection sampling)
- Chạy agent (model lớn nhất có thể, nhiều lần sample với temperature > 0) trên business `train-fit`.
- Giữ các trajectory có đáp án **đúng** theo evaluator → cặp (prompt, plan, code).
- Với câu unanswerable: giữ trajectory kết luận đúng + lý do.
- Không dùng `dev`/`holdout` để giữ đánh giá sạch (có thể thêm vào ở lần train cuối cùng).

### 1.2 Dữ liệu tổng hợp (tăng độ phủ, đặc biệt **ngành mới**)
- **Generator business giả** (`scripts/make_synthetic.py`): nhiều ngành (cả ngành không có trong train: tiệm vàng, spa, cửa hàng điện thoại, nông sản, thú cưng, in ấn…), 12–30 tháng, mùa vụ (Tết theo calendar, cuối tuần, ngày lương), đơn huỷ/trả, voucher, VAT, ship, lô nhập giá khác nhau.
- **Làm bẩn** có kiểm soát: tên cột tiếng Việt/không dấu/tiếng Anh, tiền dạng "1.250.000đ"/"1,25tr", ngày nhiều định dạng, tên SP nhiều cách viết, nhiều sheet/file, README đầy đủ/sơ sài/trống.
- **Template câu hỏi** theo taxonomy ([04](04_du_lieu_va_eda.md)), viết lại thành văn nói/không dấu/viết tắt (dùng LLM open-source để paraphrase).
- **Đáp án tính bằng code chuẩn** (oracle viết tay, áp dụng rulebook) → đáp án đúng chắc chắn; sinh cả câu unanswerable có chủ đích (bỏ cột giá vốn, hỏi ngoài khoảng thời gian…).
- Có thể dùng thêm dataset text-to-SQL public (BIRD/Spider train, SynSQL) một phần nhỏ để giữ năng lực SQL.

## 2. SFT với LoRA

- Base: model thắng benchmark ([03](03_lua_chon_model.md)), vd Qwen3-14B / Qwen3-8B / Qwen2.5-Coder.
- Công cụ: **Unsloth** hoặc **TRL + PEFT**; QLoRA nếu GPU dev hạn chế.
- Cấu hình khởi điểm: LoRA r = 16–64, alpha = 2r, lr 1e-4 → 2e-4, 1–3 epoch, context 8–16k (schema card dài), loss chỉ trên phần trả lời.
- Trộn: ~60% trajectories train, ~40% tổng hợp; giữ một phần dữ liệu chat tổng quát nếu thấy model "quên" tiếng Việt/reasoning.
- Merge LoRA vào base (hoặc dùng multi-LoRA trên vLLM) → kiểm tra tổng params không đổi.

## 3. RL với reward thực thi (tuỳ chọn, nếu còn thời gian & GPU)

- **GRPO** (TRL/verl): sinh nhiều lời giải cho mỗi câu, thực thi, reward **đúng bằng metric**: +1 nếu đúng theo evaluator, −1 nếu sai, 0 nếu abstain → model học **biết khi nào không chắc**, tối ưu trực tiếp PA.
- Dữ liệu: câu tổng hợp + train-fit (có đáp án để tính reward).
- Chi phí cao — chỉ làm khi SFT đã có lợi rõ.

## 4. Đánh giá

- So base vs SFT vs SFT+RL trên **dev và holdout** với cùng pipeline.
- Chú ý overfit: nếu tăng trên dev nhưng không tăng trên holdout (ngành khác) → giảm tỷ lệ dữ liệu train thật, tăng tổng hợp đa ngành.

## 5. Tài nguyên ước tính

| Việc | GPU | Thời gian ước tính |
|---|---|---|
| Sinh trajectories (vLLM, ~3000 câu × vài sample) | 1× 24–80GB | vài giờ |
| SFT LoRA 8B | 1× 24GB (QLoRA) / 1× 48–80GB | vài giờ |
| SFT LoRA 14B | 1× 48–80GB | vài giờ đến 1 ngày |
| GRPO 8B–14B | 2–4× 80GB | 1–3 ngày |
