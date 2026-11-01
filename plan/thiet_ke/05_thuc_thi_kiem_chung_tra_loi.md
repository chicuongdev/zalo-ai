# 05 — Answerability, thực thi, dự phòng, kiểm chứng, định dạng

## B5 — Answerability (xác định)

Đầu vào: `ResolvedPlan` + `Manifest`. Đầu ra: `answerable | unanswerable(reason) | uncertain`.

Quy tắc (theo thứ tự):

1. `unsupported_attribute` ≠ null (giới tính khách, địa chỉ, thái độ nhân viên…) **và** manifest xác nhận shop không có trường đó → `unanswerable`.
2. Intent yêu cầu năng lực shop không có (bảng [03 §3](03_tang_ngu_nghia_va_intent.md), ví dụ `stock_value` cần `catalog_cost`; `debt_*` cần `payments` hoặc `debt_recorded`; `customer_group` filter cần cột nhóm khách) → `unanswerable`.
3. Mọi kỳ cần thiết (kể cả `compare_period`) nằm **hoàn toàn ngoài** `[data_start, data_end]` → `unanswerable`. Ví dụ "% thay đổi tháng 4/2025 so với tháng liền trước" khi dữ liệu bắt đầu 04/2025.
4. Filter theo giá trị enum không tồn tại ở shop (kênh "zalo oa" khi shop không ghi kênh) → `unanswerable`. Nếu shop có trường kênh nhưng không có giá trị đó → **0**, không phải unanswerable (§7: "không có dữ liệu khác với bằng 0").
5. Miền dữ liệu liên quan có `confidence` thấp, hoặc thực thể không liên kết được nhưng chưa chắc là không tồn tại → `uncertain` (đi tiếp, nhưng hạ tin cậy).

`unanswerable` cũng có điểm tin cậy (rule nào kích hoạt, độ chắc của manifest) → qua B8 như mọi đáp án khác.

## B6 — Plan Executor (xác định)

- Tra `INTENT_REGISTRY[intent]` → hàm thư viện ngữ nghĩa; truyền slots đã giải; với `outputs[]` nhiều phần tử → gọi từng cái, ghép list theo thứ tự.
- DuckDB connection **read-only** dùng chung theo shop; kết quả cache theo `(biz, intent, slots)` (nhiều câu train hỏi lại cùng một thứ).
- Ngoại lệ trong hàm → chuyển B7 (nếu còn thời gian) hoặc abstain.

## B7 — Fallback Code Agent (LLM + sandbox)

Kích hoạt khi: `intent = other`; intent dùng mục rulebook bị đổi (`changed_sections`); B6 lỗi; hoặc kiểm chéo parser thất bại hai lần.

- Prompt:
  - Schema CDM của shop (chỉ các bảng có), kèm 3 dòng mẫu mỗi bảng.
  - Danh sách primitive của thư viện ngữ nghĩa (chữ ký + docstring), để code **gọi primitive** thay vì tự cài lại luật.
  - Các mục rulebook liên quan (nguyên văn).
  - `as_of_date`.
  - Yêu cầu: gán biến `answer` và `answer_type`.
- Sandbox: subprocess riêng, `timeout=30s`, giới hạn RAM, chỉ ghi `/tmp/sandbox/<qid>`. Sandbox mở DuckDB chuẩn ở chế độ read-only.
- Sửa lỗi ≤ 2 vòng (traceback → LLM).
- **Self-consistency**: hai lời giải với hai prompt/seed khác nhau → khớp nhau thì tin cậy trung bình; lệch thì abstain.
- Đường dự phòng luôn mang **tin cậy thấp hơn** đường chính; ngưỡng riêng được hiệu chỉnh trên dev.

## B8 — Verifier & Decision

### Tín hiệu

| Nhóm | Tín hiệu |
|---|---|
| Parser | Logprob intent; khớp `regex_hints`; có phải gọi lại không |
| Thực thể | `link_margin`; LLM phải chọn hay khớp chắc |
| Dữ liệu | `confidence` của miền (từ Validator); kỳ bị cắt một phần |
| Kết quả | Rỗng / NaN / 0 bất thường; **hoà ở biên top-k / hạng 1** (test loại các câu như vậy ⇒ nghi sai); type khớp `answer_type` |
| Đường đi | Chính (B6) hay dự phòng (B7); số vòng sửa; self-consistency |

### Quyết định

- Kết hợp các tín hiệu thành `p_correct`. Bản đầu dùng luật thủ công; sau đó dùng logistic regression **hiệu chỉnh trên dev theo từng intent/nhóm intent**.
- PA = (đúng − sai)/N ⇒ trả lời khi `p_correct > 0.5`; ngưỡng thực tế chọn để **tối đa PA trên dev**, kiểm tra trên holdout.
- Ghi `p_correct` và từng tín hiệu vào log.

## B9 — Formatter (cài rulebook §9)

| Type | Quy tắc |
|---|---|
| number | Tiền: `int`, làm tròn về đồng (nửa đồng lên). Trung bình tiền cũng là tiền. Số đếm: `int`. Còn lại: `round(x, 2)`. Bỏ `.0` thừa (dùng `int` khi là số nguyên) |
| percent | `round(x, 2)`, đơn vị % (12.4, không phải 0.124) |
| date | `YYYY-MM-DD`; intent theo tháng (`best_month`) → `YYYY-MM` |
| boolean | JSON `true/false` |
| string | Tên **đúng cách viết chính trong dữ liệu** (`display_name`). Chuỗi đã khớp tên, nên không cần trả mã. Tên khách kèm SĐT như trong file cũng được nhận |
| list | Mảng JSON (một phần tử vẫn là mảng); tồn theo đơn vị lớn `[nguyên, lẻ]`; thứ tự theo câu hỏi / luật xếp hạng |
| table | `{"columns": [tên đối tượng, số đo… theo thứ tự câu hỏi], "rows": …}`; tên cột theo mẫu train (`khach_hang`, `so_tien_no`) |
| unanswerable | `{"type": "unanswerable", "reason": "<chuỗi>"}` |
| abstain | `{"type": "abstain"}` |

Formatter kiểm tra lại bằng chính `datamate/scoring.py` (round-trip): đáp án phải hợp lệ theo luật chấm của chính type đó.
