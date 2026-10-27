# 08 — Đóng gói Docker & vận hành

## 1. Yêu cầu image

- Source code (huấn luyện + inference), **weights model** (đã quantize/merge LoRA), `predict.sh`, README.
- `predict.sh`: đọc test set từ `/data` (read-only), ghi `/result/submission.jsonl`.
- Log mỗi câu tại `/result/logs/` — tối thiểu: id, đáp án cuối, thời gian xử lý; thêm: câu chuẩn hoá, plan, code sinh ra, output thực thi, số vòng sửa, điểm tin cậy.
- Chạy với **networking disabled** → không `pip install`, không tải model lúc chạy; đặt `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`.
- Base image theo **Docker guideline của BTC** (chưa có); CUDA ≥ 12.8, PyTorch + vLLM build hỗ trợ Blackwell (sm_120).

## 2. Luồng `predict.sh`

```
1. Khởi động vLLM (1 bản/GPU nếu FP8 data-parallel, hoặc TP=2), chờ sẵn sàng
2. Đọc /data/questions.jsonl, rulebook.md, calendar.csv
3. Với mỗi business: load + profile dữ liệu (cache trong RAM, 512GB dư)
4. Xử lý câu song song (N worker, N cố định), mỗi câu xong → append submission + ghi log + flush
5. Watchdog thời gian: còn ít thời gian → chuyển chế độ nhanh (bỏ self-consistency), sát giờ → ghi abstain cho câu còn lại
6. Ghi đủ mọi id (câu chưa xử lý = abstain) trước khi thoát
```

## 3. Ngân sách thời gian

- 6h = 21.600s cho ~500 câu, **kể cả load model** → ~43s/câu nếu tuần tự; với chạy song song thực tế dư nhiều.
- Mục tiêu nội bộ: private test xong trong **≤ 50% budget** (phòng máy BTC chậm hơn, số câu nhiều hơn).
- Đo trên public (~1000 câu) trên phần cứng gần nhất có thể; ghi thời gian từng bước vào log để tối ưu.
- Thời gian là tiêu chí phá hoà điểm → nhanh hơn cũng có lợi.

## 4. Determinism & tái lập (Rule 8: |ΔPA| ≤ 0.03)

- Greedy decoding (temperature 0), seed cố định cho mọi sampling (kể cả self-consistency dùng seed riêng theo hash nội dung câu hỏi, **không** theo id).
- Thứ tự xử lý và số worker cố định; kết quả mỗi câu không phụ thuộc câu khác.
- vLLM có thể không batch-invariant (kết quả thay đổi nhẹ theo batch) → thử chế độ batch-invariant nếu phiên bản vLLM hỗ trợ, hoặc đo độ lệch thực tế giữa các lần chạy; abstain có ngưỡng giúp giảm dao động.
- Sandbox: timeout cố định, không phụ thuộc thời gian thực hay random.
- Kiểm thử: chạy image 2 lần trên public, so từng đáp án; |ΔPA| phải ≪ 0.03.

## 5. Checklist trước khi nộp

- [ ] `docker run --gpus all --network none -v <test>:/data:ro -v <out>:/result <image>` chạy sạch trên máy mới.
- [ ] submission.jsonl hợp lệ JSON, đủ id, type hợp lệ.
- [ ] Logs đủ trường.
- [ ] Tổng params các model ≤ 15B, khai báo trong README (tên, nguồn HF, licence, params).
- [ ] Không có logic theo business_id/question id (grep code).
- [ ] Không dùng dữ liệu public/private test trong training/few-shot.
- [ ] Thời gian và tái lập đã đo.
