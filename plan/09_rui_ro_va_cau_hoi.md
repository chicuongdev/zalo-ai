# 09 — Rủi ro & câu hỏi mở

## 1. Rủi ro và phương án giảm

| Rủi ro | Mức | Phương án |
|---|---|---|
| Câu sai bị trừ −1 (PA +1/0/−1) — trả lời bừa làm điểm âm | Cao | Abstain khi P(đúng) ≤ 0.5; hiệu chỉnh độ tin cậy trên dev, kiểm tra holdout |
| Private có **ngành mới**, schema lạ | Cao | Profiler/loader tổng quát; holdout theo ngành khác; dữ liệu tổng hợp đa ngành; không hard-code tên cột |
| README trống / sơ sài | Trung bình | Profiler tự suy luận ngữ nghĩa cột; đánh giá riêng trên business có README kém |
| Rulebook private khác train | Trung bình | Luôn đọc rulebook runtime; helper tham số hoá; test với rulebook đã chỉnh sửa giả lập |
| Vượt giờ 6h khi re-run | Cao | Ghi tăng dần, watchdog, mục tiêu ≤ 50% budget |
| Không tái lập (|ΔPA| > 0.03) → loại | Cao | Greedy + seed, worker cố định, kiểm thử 2 lần, log đầy đủ |
| Vượt 15B (quên tính embedder/vision encoder/adapter) | Cao | Bảng params trong README, kiểm trước khi nộp, hỏi BTC về LoRA |
| Model open-source yếu tiếng Việt không dấu | Trung bình | Normalizer + benchmark câu không dấu riêng; fine-tune trên paraphrase |
| vLLM/Blackwell không tương thích | Trung bình | Dùng đúng base image BTC sớm; có phương án fallback (transformers/SGLang) |
| Code sinh ra treo/ăn RAM | Trung bình | Sandbox timeout + giới hạn bộ nhớ |
| Overfit public leaderboard | Thấp–TB | Quyết định dựa trên dev/holdout |
| Không có GPU dev local | Cao (tiến độ) | Thuê GPU sớm; dev logic trên model nhỏ, xác nhận trên model lớn |

## 2. Câu hỏi mở

Cần user trả lời:
1. **Deadline** các vòng (nộp solution, private test) — để chốt timeline cụ thể.
2. **Tài nguyên GPU** dùng để phát triển/fine-tune (loại GPU, số lượng, VRAM, thời gian sử dụng).
3. Số thành viên trong đội & phân công (ví dụ: 1 người data/helper, 1 người LLM/prompt, 1 người fine-tune/Docker).
4. Đã có / khi nào có dữ liệu train & public test?

Cần hỏi BTC / forum:
1. **Docker guideline** & base image.
2. Cách tính tham số khi dùng **LoRA adapter** / nhiều adapter trên một base.
3. Giới hạn số lần nộp public mỗi ngày.
4. Máy chấm có giống hệt cấu hình công bố không (để ước lượng thời gian chính xác hơn).
