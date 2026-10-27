# 01 — Phân tích đề bài

## 1. Input / Output

**Mỗi câu hỏi** (`questions.jsonl`):

```json
{"id": "q_06de33fa21cc", "business_id": "biz_118", "question": "sp bán dc nhiều nhất tuần rồi là gì", "as_of_date": "2026-03-04"}
```

- `question`: tiếng Việt đời thường — có dấu, **không dấu** ("thang nay hang nao ban cham nhat"), viết tắt ("sp", "dc", "ko"), văn nói.
- `as_of_date`: mốc "hôm nay" để hiểu "tháng này", "tuần rồi", "cùng kỳ năm ngoái".

**Gói dữ liệu mỗi split:**

```
<split>/
├── data/<business_id>/   *.csv | *.xlsx | *.sqlite  + README.md
├── rulebook.md           định nghĩa mặc định (khác nhau giữa các split!)
├── calendar.csv          lịch âm–dương (Tết)
├── questions.jsonl
└── answers.jsonl         chỉ có ở train (kèm "alias")
```

- Mỗi business: 12–30 tháng hoạt động, có mùa vụ (Tết, Trung thu, lễ, ngày lương, cuối tuần), vài trăm → ~300.000 dòng.
- README chất lượng thất thường: có khi đủ data dictionary, có khi vài ghi chú, có khi gần như trống.
- Ngành: tạp hoá, cà phê/trà sữa, nhà hàng, nhà thuốc, vật liệu xây dựng, sửa xe máy, mẹ & bé… **Private test có ngành mới.**

**Output** (`submission.jsonl`, mỗi dòng một object):

```json
{"id": "q_01234", "type": "string", "answer": "Sting dâu 330ml"}
{"id": "q_01235", "type": "number", "answer": 48250000}
{"id": "q_01236", "type": "percent", "answer": -12.45}
{"id": "q_01237", "type": "date", "answer": "2026-08-15"}
{"id": "q_01238", "type": "boolean", "answer": true}
{"id": "q_01239", "type": "list", "answer": ["Cà phê sữa", "Bạc xỉu", "Trà đào"]}
{"id": "q_01240", "type": "table", "answer": {"columns": ["khach_hang", "so_tien_no"], "rows": [["Chị Lan", 3200000], ["Anh Tú", 1500000]]}}
{"id": "q_01241", "type": "unanswerable", "reason": "Dữ liệu không có giá vốn nên không tính được lợi nhuận"}
{"id": "q_01242", "type": "abstain"}
```

Câu thiếu trong file = abstain. `reason` tuỳ chọn.

## 2. Luật chấm từng kiểu & hệ quả thiết kế

Mỗi câu: **correct / wrong / abstain**. Đúng khi **type trùng reference** VÀ giá trị khớp. Không partial credit.

| Type | Luật khớp | Hệ quả cho formatter / agent |
|---|---|---|
| `number` | Khớp tuyệt đối; reference là số nguyên (VND, đếm, số lượng) hoặc làm tròn 2 chữ số | Tiền/đếm → int; còn lại `round(x, 2)`. Tránh lỗi float (`48250000.0000001`) |
| `percent` | Khớp sau làm tròn 2 chữ số, **đúng dấu** | Trả theo đơn vị % (−12.45, không phải −0.1245). Tăng trưởng = (mới − cũ)/cũ × 100 |
| `string` | NFC → lowercase → ký tự không phải chữ/số/khoảng trắng thành space → gộp space. **Giữ dấu.** Reference chấp nhận mọi cách viết có trong data + **mã** | Trả đúng tên như trong data, hoặc trả **mã** (vd `SP0042`) khi có — an toàn nhất. Không tự bỏ dấu, không "làm đẹp" tên |
| `date` | `yyyy-mm-dd`; câu hỏi về tháng → `yyyy-mm` | Formatter phải biết câu hỏi hỏi ngày hay tháng |
| `boolean` | `true`/`false` | JSON bool, không phải chuỗi |
| `list` | Có thứ tự, so từng vị trí; phần tử theo luật string/number | Sắp xếp theo tiêu chí câu hỏi (hoặc mặc định rulebook), **giảm dần**, hoà → **mã tăng dần**; ít hơn k ứng viên → trả hết |
| `table` | Cột khớp theo tên chuẩn hoá, không khớp thì theo vị trí; hàng so như **tập hợp** | Thứ tự cột phải hợp lý (khoá trước, giá trị sau); thứ tự hàng không quan trọng |
| `unanswerable` | Đúng khi và chỉ khi reference unanswerable | Trả lời bất kỳ cho câu unanswerable = **sai** |
| `abstain` | Luôn tính abstain | Lối thoát an toàn khi không chắc |

**Ranking:** loại bỏ trường hợp hoà ở biên k (hoặc ở hạng 1 với câu "…nhất") khỏi test → nếu agent thấy hoà ở biên thì nhiều khả năng **đang tính sai** (tín hiệu để kiểm tra lại / abstain). "Over valid orders only" ⇒ chỉ tính trên đơn hợp lệ (loại đơn huỷ/trả theo rulebook).

## 3. Metric — Penalized Accuracy (PA)

Công thức chính thức (đã cập nhật trong `subject/02.evaluation.json`):

$$PA = \frac{1}{N}\sum_{i=1}^{N} s_i,\qquad s_i = \begin{cases} +1 & \text{đúng} \\ 0 & \text{abstain (hoặc thiếu)} \\ -1 & \text{sai} \end{cases}$$

tức là `PA = (#correct − #wrong) / N`, nằm trong [−1, 1].

- Mọi câu cùng trọng số. Trả lời bất kỳ cho câu unanswerable = sai (−1). Hoà điểm → so tổng thời gian inference trong lần re-run, rồi thời điểm nộp.
- **Hệ quả 1 — ngưỡng trả lời:** kỳ vọng điểm khi trả lời = p·(+1) + (1−p)·(−1) = 2p − 1 ⇒ **chỉ trả lời khi P(đúng) > 0.5**, ngược lại abstain (0 điểm) có lợi hơn.
- **Hệ quả 2 — sai rất đắt:** một câu sai xoá điểm của một câu đúng. Ví dụ: accuracy 70% mà không bao giờ abstain → PA = 0.70 − 0.30 = **0.40**; nếu abstain đúng chỗ 20% câu khó (trong đó phần lớn sẽ sai) và giữ 65% đúng, 15% sai → PA = **0.50**.
- **Hệ quả 3 — unanswerable:** trả `unanswerable` sai chỗ cũng là −1 → bộ phát hiện unanswerable cũng phải qua ngưỡng tin cậy; khi phân vân giữa "có đáp án" và "unanswerable", abstain là lựa chọn an toàn.
- **Hệ quả 4 — quá giờ:** câu chưa ghi = abstain (0), không bị trừ → ghi tăng dần là đủ an toàn.
- Mốc tham chiếu: submission toàn abstain → PA = 0.

## 4. Quy tắc nghiệp vụ mặc định (rulebook train — ví dụ)

- **Doanh thu** = tổng tiền dòng sau giảm giá **cấp dòng** (voucher cấp đơn **không** trừ), **không** VAT, **không** phí ship, **loại** đơn huỷ và đơn có bất kỳ món bị trả.
- "**Bán chạy**" = theo **số lượng**.
- **Tuần** = Thứ Hai → Chủ Nhật.
- "**Tháng này**" = từ đầu tháng chứa as_of_date đến **hết** as_of_date.
- **Giá vốn mặc định** = bình quân gia quyền giá nhập theo lô.
- **Cửa sổ Tết** = 23 tháng Chạp → mùng 10 tháng Giêng (âm lịch, tra `calendar.csv`).

⚠️ Rulebook **có thể khác giữa các split** ⇒ agent phải **đọc rulebook của split đang chạy** lúc runtime, đưa vào prompt; helper phải tham số hoá (không hard-code định nghĩa doanh thu/tuần).

## 5. Splits

| Split | Business | Câu hỏi | Đáp án |
|---|---|---|---|
| Training | 30 | ~3.000 | Có (+ alias) |
| Public test | 10–20 | ~1.000 | Ẩn, chấm public leaderboard |
| Private test | 10–20 | ~500 | Ẩn, có **ngành mới** |

## 6. Ràng buộc kỹ thuật (Rules)

| # | Ràng buộc | Hệ quả |
|---|---|---|
| R2 | Model **open-source**, weights public trước **01/10/2026**, licence cho phép; **tổng ≤ 15B tham số** của mọi model dùng lúc inference (LLM, embedding, reranker, classifier; MoE tính đủ). Quantize tự do, fine-tune tự do. Khai báo trong README | Chọn model kỹ, tính cả embedder (xem [03](03_lua_chon_model.md)) |
| R3 | Offline hoàn toàn, không API, không mạng | Weights đóng gói trong image; không `pip install`/download lúc chạy |
| R4 | Không human-in-the-loop, **cấm hard-code** đáp án hoặc logic theo id câu hỏi/business | Mọi logic phải tổng quát theo nội dung dữ liệu & câu hỏi |
| R5 | Được sinh & chạy code; `/data` read-only | Sandbox ghi vào `/tmp` |
| R6 | Chỉ dùng train + dữ liệu tự sinh + public datasets; **cấm** train trên public/private test | Không đưa câu hỏi public test vào few-shot/fine-tune |
| R7 | 2× RTX 5090 (2×32GB), 512GB RAM; private test ≤ **6h** kể cả load model; CUDA ≥ 12.8 | Ngân sách ~43s/câu nếu tuần tự — chạy song song để có dư |
| R8 | Điểm cuối = re-run của BTC; **|PA upload − PA re-run| ≤ 0.03**; quá giờ → phần chưa ghi = abstain | Determinism, ghi submission **tăng dần**, log đủ để giải trình |

## 7. Những điểm khó dự kiến

1. **Hiểu câu hỏi văn nói không dấu** → chuẩn hoá trước khi lập kế hoạch.
2. **Dữ liệu bẩn**: định dạng tiền ("1.250.000đ", "1,25tr"), ngày nhiều kiểu, tên SP nhiều cách viết, nhiều file/sheet cần join.
3. **Ngữ nghĩa nghiệp vụ**: doanh thu vs voucher/VAT/ship/hàng trả, giá vốn theo lô, công nợ.
4. **Thời gian tương đối & âm lịch**: "tuần rồi", "cùng kỳ năm ngoái", "Tết năm nay".
5. **Unanswerable**: câu hỏi hợp lý nhưng data không có cột cần (vd không có giá vốn → không tính lợi nhuận), ngoài khoảng thời gian dữ liệu.
6. **Ngành mới ở private test** → không được overfit schema train.
