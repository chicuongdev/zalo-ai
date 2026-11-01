# Kế hoạch Zalo AI Challenge 2026 — DataMate

> Thư mục này chứa toàn bộ kế hoạch **trước khi** triển khai code. Mọi thay đổi hướng đi lớn cần cập nhật ở đây trước.
> Nguồn đề bài: [../subject/](../subject/)

## Tóm tắt 1 trang

**Bài toán:** Xây AI agent trả lời câu hỏi tiếng Việt đời thường (có dấu / không dấu / viết tắt) trực tiếp trên dữ liệu bảng (CSV, XLSX, SQLite) của các hộ kinh doanh nhỏ Việt Nam. Mỗi câu trả về một đáp án có kiểu (`number`, `percent`, `string`, `date`, `boolean`, `list`, `table`), hoặc `unanswerable` khi dữ liệu không đủ, hoặc `abstain` khi agent chọn không trả lời.

**Chấm điểm:** khớp tuyệt đối, không partial credit, metric Penalized Accuracy `PA = (#đúng − #sai) / N` (đúng +1, abstain 0, sai −1) ⇒ chỉ trả lời khi P(đúng) > 0.5; **chính xác + biết lúc nào nên im lặng** quan trọng ngang nhau.

**Ràng buộc then chốt:** chỉ dùng **model open-source** (public trước 01/10/2026, tổng ≤ 15B tham số lúc inference), chạy **offline** trong Docker trên 2× RTX 5090, ~500 câu trong ≤ 6h, kết quả **tái lập** (chênh PA ≤ 0.03).

**Hướng giải** (đã chốt sau EDA, chi tiết ở [thiet_ke/](thiet_ke/00_tong_quan.md)):

- **Pha A**: đưa dữ liệu thô của mỗi shop về một **mô hình dữ liệu chuẩn** (DuckDB) kèm **manifest năng lực**.
- **Pha B**: LLM open-source **phân tích câu hỏi thành kế hoạch truy vấn có cấu trúc** (intent + tham số). Một **thư viện ngữ nghĩa xác định** cài đặt rulebook sẽ tính đáp án.
- Câu ngoài catalog hoặc luật bị đổi đi **đường dự phòng**: LLM sinh code trên mô hình chuẩn.
- **Kiểm chứng** rồi chỉ trả lời khi P(đúng) > 0.5.
- **Fine-tune LoRA** parser trên "plan vàng" (plan đã kiểm chứng bằng đáp án train).

## Mục lục

| # | File | Nội dung |
|---|---|---|
| 1 | [01_phan_tich_de_bai.md](01_phan_tich_de_bai.md) | Phân tích đề, luật chấm, ràng buộc và hệ quả thiết kế |
| 2 | [02_kien_truc.md](02_kien_truc.md) | Tóm tắt kiến trúc và lý do chọn |
| 2a | [thiet_ke/](thiet_ke/00_tong_quan.md) | **Thiết kế hệ thống chi tiết** (10 file): mô hình dữ liệu, Pha A, thư viện ngữ nghĩa, hiểu câu hỏi, thực thi, runtime, ví dụ trọn luồng, hợp đồng module, kiểm thử |
| 2b | [eda_findings.md](eda_findings.md) | Kết quả EDA bộ train |
| 3 | [03_lua_chon_model.md](03_lua_chon_model.md) | Chọn model open-source, ngân sách 15B, serving, benchmark |
| 4 | [04_du_lieu_va_eda.md](04_du_lieu_va_eda.md) | Phân tích dữ liệu train, chia dev/hold-out, taxonomy câu hỏi |
| 5 | [05_lo_trinh_trien_khai.md](05_lo_trinh_trien_khai.md) | Lộ trình G0–G5, task, Definition of Done |
| 6 | [06_danh_gia_va_abstain.md](06_danh_gia_va_abstain.md) | Evaluator local, phân tích lỗi, chiến lược abstain/unanswerable |
| 7 | [07_fine_tuning.md](07_fine_tuning.md) | Dữ liệu tổng hợp, SFT LoRA, RL với reward thực thi |
| 8 | [08_trien_khai_docker.md](08_trien_khai_docker.md) | Docker, predict.sh, time budget, determinism |
| 9 | [09_rui_ro_va_cau_hoi.md](09_rui_ro_va_cau_hoi.md) | Rủi ro, phương án giảm, câu hỏi mở |

## Mốc chính thức của cuộc thi (GMT+7, tra cứu ngày 2026-11-01)

| Mốc | Thời gian |
|---|---|
| Mở cuộc thi | 26/10/2026 |
| **Hạn nộp solution** (Docker: code train + test + model) | **16/11/2026 23:59** |
| Công bố private test | 20/11/2026 09:00 |
| Hạn nộp kết quả private | 23/11/2026 23:59 |
| Công bố 2 đội vào chung kết mỗi bảng | 02/12/2026 |
| Công bố kết quả cuối | 12/12/2026 |

Nguồn: [challenge.zalo.ai](https://challenge.zalo.ai/) (theo kết quả tìm kiếm; trang render bằng JS, cần mở bằng trình duyệt để xem đủ), [Znews](https://znews.vn/zalo-ai-challenge-2026-khoi-tranh-voi-hai-bai-toan-ve-ai-tac-nhan-post1692123.html). Giải: tổng 12.000 USD; vô địch 3.500 USD, nhì 2.500 USD. Nên chốt thành viên đội trước hạn solution ít nhất một tuần.

⇒ Từ 01/11 còn **15 ngày** đến hạn solution. Lộ trình bên dưới đã được nén theo ngày ([05](05_lo_trinh_trien_khai.md)).

## Các giai đoạn

```
G0  Chuẩn bị: data, EDA, thiết kế                                    (xong phần lớn)
G1  Nền móng xác định: chấm điểm, parser giá trị, Pha A → CDM 30 shop  (không cần GPU)
G2  Thư viện ngữ nghĩa + tái tạo oracle bằng plan vàng                 (không cần GPU)
G3  Hiểu câu hỏi bằng LLM, end-to-end → nộp public lần 1               (cần GPU)
G4  Đường dự phòng, rulebook diff, hiệu chỉnh abstain
G5  Fine-tune LoRA parser (song song G4)
G6  Docker, đo thời gian, tái lập, freeze & nộp
```

## Quy ước trạng thái task

Trong các file kế hoạch, mỗi task đánh dấu: `[ ]` chưa làm · `[~]` đang làm · `[x]` xong · `[-]` bỏ (ghi lý do).

## Hiện trạng (2026-11-01)

- Đã có dữ liệu train (`train.zip`, 30 shop, 3.000 câu); EDA xong; thiết kế chi tiết xong. Chưa có public test.
- Công thức PA đã được bổ sung vào `02.evaluation.json`: đúng +1, abstain 0, sai −1.
- Máy local không có GPU NVIDIA → cần môi trường GPU riêng để phát triển.
