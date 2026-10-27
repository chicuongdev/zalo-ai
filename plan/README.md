# Kế hoạch Zalo AI Challenge 2026 — DataMate

> Thư mục này chứa toàn bộ kế hoạch **trước khi** triển khai code. Mọi thay đổi hướng đi lớn cần cập nhật ở đây trước.
> Nguồn đề bài: [../subject/](../subject/)

## Tóm tắt 1 trang

**Bài toán:** Xây AI agent trả lời câu hỏi tiếng Việt đời thường (có dấu / không dấu / viết tắt) trực tiếp trên dữ liệu bảng (CSV, XLSX, SQLite) của các hộ kinh doanh nhỏ Việt Nam. Mỗi câu trả về một đáp án có kiểu (`number`, `percent`, `string`, `date`, `boolean`, `list`, `table`), hoặc `unanswerable` khi dữ liệu không đủ, hoặc `abstain` khi agent chọn không trả lời.

**Chấm điểm:** khớp tuyệt đối, không partial credit, metric Penalized Accuracy `PA = (#đúng − #sai) / N` (đúng +1, abstain 0, sai −1) ⇒ chỉ trả lời khi P(đúng) > 0.5; **chính xác + biết lúc nào nên im lặng** quan trọng ngang nhau.

**Ràng buộc then chốt:** chỉ dùng **model open-source** (public trước 01/10/2026, tổng ≤ 15B tham số lúc inference), chạy **offline** trong Docker trên 2× RTX 5090, ~500 câu trong ≤ 6h, kết quả **tái lập** (chênh PA ≤ 0.03).

**Hướng giải:** Agent "LLM open-source sinh code pandas/SQL → thực thi trong sandbox → tự sửa lỗi → kiểm chứng → abstain nếu không chắc", được bao quanh bởi các lớp **xác định** (loader/profiler dữ liệu, thư viện helper cho thời gian/Tết/xếp hạng/doanh thu, formatter đúng luật chấm). Sau khi có baseline, **fine-tune LoRA** model trên dữ liệu tổng hợp + trajectories đúng từ train.

## Mục lục

| # | File | Nội dung |
|---|---|---|
| 1 | [01_phan_tich_de_bai.md](01_phan_tich_de_bai.md) | Phân tích đề, luật chấm, ràng buộc và hệ quả thiết kế |
| 2 | [02_kien_truc.md](02_kien_truc.md) | Kiến trúc pipeline agent, module, cấu trúc repo |
| 3 | [03_lua_chon_model.md](03_lua_chon_model.md) | Chọn model open-source, ngân sách 15B, serving, benchmark |
| 4 | [04_du_lieu_va_eda.md](04_du_lieu_va_eda.md) | Phân tích dữ liệu train, chia dev/hold-out, taxonomy câu hỏi |
| 5 | [05_lo_trinh_trien_khai.md](05_lo_trinh_trien_khai.md) | Lộ trình G0–G5, task, Definition of Done |
| 6 | [06_danh_gia_va_abstain.md](06_danh_gia_va_abstain.md) | Evaluator local, phân tích lỗi, chiến lược abstain/unanswerable |
| 7 | [07_fine_tuning.md](07_fine_tuning.md) | Dữ liệu tổng hợp, SFT LoRA, RL với reward thực thi |
| 8 | [08_trien_khai_docker.md](08_trien_khai_docker.md) | Docker, predict.sh, time budget, determinism |
| 9 | [09_rui_ro_va_cau_hoi.md](09_rui_ro_va_cau_hoi.md) | Rủi ro, phương án giảm, câu hỏi mở |

## Timeline tổng (tương đối, điều chỉnh khi biết deadline)

```
Tuần 1      G0  Chuẩn bị: lấy data, EDA, chốt môi trường GPU dev, benchmark nhanh model
Tuần 1–2    G1  Evaluator local + loader/profiler + baseline end-to-end  → nộp public lần 1
Tuần 2–4    G2  Helper library, prompt, few-shot, phân tích lỗi theo nhóm → nộp public định kỳ
Tuần 4–5    G3  Abstain policy, self-consistency, phát hiện unanswerable
Tuần 4–7    G4  Fine-tune LoRA (song song G3), so sánh với base model
Tuần cuối   G5  Đóng gói Docker, đo thời gian, kiểm thử tái lập, freeze & nộp
```

## Quy ước trạng thái task

Trong các file kế hoạch, mỗi task đánh dấu: `[ ]` chưa làm · `[~]` đang làm · `[x]` xong · `[-]` bỏ (ghi lý do).

## Hiện trạng (2026-10-26)

- Workspace mới chỉ có `subject/` (4 file mô tả đề). **Chưa có dữ liệu train/public.**
- Công thức PA đã được bổ sung vào `02.evaluation.json`: đúng +1, abstain 0, sai −1.
- Máy local không có GPU NVIDIA → cần môi trường GPU riêng để phát triển.
