# 11 — Khi nào hệ thống hiểu sai, và cách xử lý tổng quát (không thêm case thủ công)

## 0. Vấn đề

Parser luật đạt 100% trên train nhưng chỉ phủ 44,7% trên public trước khi sửa tay. Sau khi chuẩn hoá cách viết tháng thì lên 72,5%. Kiểu cải thiện này (nhìn câu lỗi → thêm regex) **không tổng quát được**: private sẽ có ngành mới, khái niệm mới, cách viết mới.

Nguy hiểm hơn cả "không trả lời" là **trả lời tự tin nhưng sai** (−1 điểm). Số đo trên public:
- 241/1.000 câu chứa từ chưa từng gặp ở train (ngoài tên hàng/khách của shop).
- Parser luật **vẫn trả lời 165 câu** trong số đó. Không có đáp án nên chưa biết đúng hay sai, nhưng đây là vùng rủi ro cao nhất.

Nguyên tắc: hệ thống phải **biết khi nào mình không hiểu**. Mọi tầng phải trả về được "không chắc", và chỉ trả lời khi P(đúng) > 0,5.

## 1. Phân loại lỗi theo tầng

| # | Tầng | Kiểu lỗi | Ví dụ thật | Mức nguy hiểm | Tín hiệu phát hiện được (không cần đáp án) |
|---|---|---|---|---|---|
| A1 | Pha A — nhận bảng | Bố cục sổ mới (báo cáo tổng hợp, báo cáo ca, sổ sửa xe) không ra được bảng chuẩn | dev_003 không có ngày đơn; dev_012 sổ sửa xe | Cao: kéo theo unanswerable sai | validator thấp, bảng `extra_*`, cột không ánh xạ |
| A2 | Pha A — ánh xạ cột | Cột lạ bị gán **nhầm** trường (nguy hiểm hơn bỏ trống) | "Mô tả" bị coi là tên hàng (đã gặp ở train) | Rất cao: sai âm thầm | margin điểm giữa ứng viên #1 và #2 thấp; kiểm kiểu giá trị; bất biến (Σ dòng ≈ tổng đơn) |
| A3 | Pha A — giá trị | Định dạng tiền/ngày mới | `332,5972tr` | Trung bình | tỉ lệ parse < 0,99 |
| A4 | Pha A — ngữ nghĩa | Thông tin **có trong file** nhưng CDM không có chỗ chứa (trả góp, thu máy cũ, thẻ thành viên, sổ nợ riêng) ⇒ manifest báo "không ghi" ⇒ **unanswerable sai** | dev_014 `SoNo.xlsx`, dev_008 | Rất cao | có file/sheet/cột chưa dùng; README nhắc tới khái niệm |
| B1 | Hiểu câu — bề mặt | Viết tắt, teencode, Telex, gõ đảo chữ, từ địa phương, cách viết ngày | `Th7/2026`, `dh`, `kua`, `wan`, `ngày mô`, `nhta` | Trung bình: thường dẫn tới bỏ trống | tỉ lệ từ lạ; parser luật không ra kỳ |
| B2 | Hiểu câu — **khái niệm lạ** | Câu hỏi khái niệm không có trong catalog; parser **ép** về intent gần nhất | "khách sộp nhất" bị hiểu thành khách mua nhiều tiền nhất; "giờ cao điểm"; "lượt xe" | **Rất cao: sai tự tin** | từ lạ; thuật ngữ in đậm trong rulebook mới; intent không giải thích hết các từ chính |
| B3 | Hiểu câu — luật đổi | Cùng tên khái niệm nhưng rulebook runtime định nghĩa khác train | doanh thu kỳ đặt loại đơn trả sau kỳ | Cao | diff rulebook theo từng dòng |
| B4 | Gắn thực thể | Tên hàng/khách viết lạ, viết thiếu, trùng gần nhau; khớp mờ chọn nhầm | "trà" (nhóm) với "Trà vải" (hàng) | Cao | điểm khớp thấp, hai ứng viên sát nhau, khớp được nhiều loại thực thể |
| B5 | Slot | Sai đơn vị, k, ngưỡng >/≥, kỳ so sánh, thứ tự nhiều số | "từ N trở lên" | Trung bình | parser luật và LLM khác nhau ở slot |
| C1 | Thực thi | Kỳ có một phần dữ liệu; kết quả rỗng hoặc 0 thay vì unanswerable | | Trung bình | kết quả rỗng, chia cho 0, kỳ bị cắt mạnh |
| C2 | Định dạng | Sai type (list hay string, cột bảng) | | Trung bình | type của intent khác type mà câu hỏi gợi ý |

## 2. Giải pháp tổng quát

### G1. "Không biết" là một đầu ra hợp lệ ở mọi tầng
- Schema LLM thêm intent `other`. Hiện tại guided decoding **ép** LLM chọn trong catalog, nên khái niệm lạ bị ép vào intent sai (B2).
- Parser luật chỉ trả lời khi có **bằng chứng dương**:
  - Mỗi plan ghi lại các từ khoá đã kích hoạt nó.
  - Câu còn **từ nội dung chưa được giải thích** (không thuộc từ điển train, tên thực thể của shop, hay từ đệm) ⇒ độ tin cậy thấp.
  - Bỏ mặc định "không khớp gì thì là doanh thu".
- Manifest phân biệt ba trạng thái: **không có** / **có** / **có thể có nhưng chưa đọc được** (A4). Chỉ kết luận unanswerable khi không còn bảng/cột chưa dùng nào có thể chứa thông tin đó; ngược lại thì abstain hoặc đi đường dự phòng.

### G2. Kiểm chứng ngược (back-translation)
- Từ plan sinh lại một **câu hỏi chuẩn** bằng template cố định, ví dụ "Khách nào có doanh thu cao nhất tháng 8/2025?".
- LLM trả lời có/không: "Câu gốc và câu chuẩn có hỏi cùng một điều không?"
- Bắt được B2 (khách sộp ≠ khách mua nhiều tiền nhất), B4, B5 mà không cần biết trước khái niệm mới.
- Rẻ: một lượt sinh ngắn mỗi câu.

### G3. Nhiều lời giải độc lập + đồng thuận
- Hiện có parser luật và LLM, kết hợp kiểu `agree`.
- Thêm các lời giải độc lập khác: LLM với bộ few-shot khác, hoặc LLM trên câu đã chuẩn hoá.
- Thực thi tất cả. Đáp án trùng nhau ⇒ tin cậy cao; khác nhau ⇒ abstain hoặc chọn theo hiệu chỉnh.
- Đây là cơ chế chống sai tổng quát nhất, không phụ thuộc kiểu lỗi.

### G4. Rulebook là dữ liệu đầu vào, không phải hằng số
- Tách bảng luật thành các dòng (thuật ngữ in đậm ở cột trái → định nghĩa).
- So với rulebook train:
  - Dòng **không đổi**: thư viện dùng được.
  - Dòng **đổi** hoặc **mới**: lập **glossary runtime**. Câu hỏi nhắc tới thuật ngữ trong glossary mới đi đường dự phòng G5 (prompt kèm nguyên văn định nghĩa), hoặc abstain.
- Bắt được B2 và B3 mà không cần viết intent cho từng khái niệm.

### G5. Đường dự phòng: LLM sinh code (B7)
- Cho câu `other` hoặc thuật ngữ mới.
- Đầu vào prompt: schema CDM, các bảng `extra_*` (gồm cả bảng chưa ánh xạ), README, định nghĩa rulebook liên quan, và helper đã kiểm chứng (`valid_orders`, `revenue_of`, kỳ thời gian…).
- Chạy code trong sandbox, sinh 2 lời giải độc lập. Hai lời giải ra cùng đáp án mới nộp, khác nhau thì abstain.

### G6. Gắn thực thể có biên an toàn
- Lấy top-k ứng viên kèm điểm. Điểm #1 thấp hoặc sát #2 ⇒ LLM chọn trong top-k, có lựa chọn "không có".
- Một chuỗi khớp được nhiều loại thực thể (nhóm và hàng) ⇒ giữ cả hai plan, kiểm chứng bằng G2/G3.

### G7. Chuẩn hoá bề mặt có quy luật, không theo từng từ
- Biến đổi ký tự theo quy luật teencode: k↔c, w↔qu, j↔gi, z↔d/v, gõ đảo 2 ký tự liền nhau.
- Chỉ nhận biến thể khi kết quả rơi vào **từ điển** (train + rulebook + README + tên thực thể). Mở rộng `telex_fix` đã có.
- LLM vẫn nhận câu gốc. Bước này chỉ giúp parser luật, BM25 và gắn thực thể.

### G8. Hiệu chỉnh quyết định (B8)
- Đặc trưng cho mỗi câu:
  - đồng thuận parser luật / LLM,
  - kết quả kiểm chứng ngược,
  - số từ lạ,
  - margin gắn thực thể,
  - độ tin cậy manifest/validator của miền,
  - nhóm intent.
- Ước lượng P(đúng) trên dev/holdout (và các tập stress ở mục 3). Chỉ nộp khi > 0,5.

## 3. Đo khả năng tổng quát (thay cho nhìn câu public rồi sửa tay)

| Tập đo | Cách tạo | Đo gì |
|---|---|---|
| Leave-industry-out | Bỏ hẳn một ngành (vd nhà thuốc) khỏi few-shot và từ điển; chạy trên các shop ngành đó | khái niệm và tên lạ (B2, B4) |
| Paraphrase stress | Dùng LLM viết lại câu train theo phong cách public (viết tắt, k/c, w/qu, địa phương, đổi trật tự); đáp án giữ nguyên | bề mặt (B1) |
| Concept-swap | Câu train đổi khái niệm có định nghĩa khác (sộp, trung thành, ưa chuộng…) mà đáp án đã biết là **khác** đáp án intent gần nhất | hệ thống phải abstain, không được trả lời intent gần nhất (B2) |
| Rulebook giả lập | Sửa vài dòng rulebook train (vd ca sáng 07:00–12:59); tính lại đáp án | B3 |
| Public leaderboard | Nộp định kỳ | số thật, chỉ dùng để tìm *loại* lỗi |

Số đo chính: **PA** (không chỉ accuracy) và **tỉ lệ sai trên câu đã trả lời**. Mục tiêu: tỉ lệ sai < 5% trên mọi tập stress.

## 4. Thứ tự làm đề xuất

| Bước | Việc | Lỗi giảm được | Công |
|---|---|---|---|
| 1 | G1: `other` trong schema LLM; bỏ mặc định "doanh thu"; độ tin cậy theo từ chưa giải thích; manifest 3 trạng thái | B2, A4 | nhỏ |
| 2 | `predict.py` + kết hợp kiểu `agree`, nộp public lần đầu | đo thật | nhỏ |
| 3 | G4: phân tích rulebook ⇒ glossary runtime ⇒ đánh dấu câu dùng thuật ngữ mới/đổi | B2, B3 | vừa |
| 4 | G2: kiểm chứng ngược | B2, B4, B5 | vừa |
| 5 | Tập stress mục 3 (paraphrase, concept-swap, leave-industry-out) ⇒ hiệu chỉnh G8 | đo | vừa |
| 6 | G5: LLM sinh code cho câu `other` / thuật ngữ mới, kèm đồng thuận 2 lời giải | tăng phủ an toàn | lớn |
| 7 | Pha A tổng quát: bảng chưa ánh xạ vẫn giữ (`extra_*`) và mô tả cho G5; LLM hỗ trợ ánh xạ cột khi margin thấp | A1, A2, A4 | vừa–lớn |
| 8 | G7 chuẩn hoá ký tự có quy luật; G6 gắn thực thể top-k | B1, B4 | nhỏ |

## 5. Tiến độ (03/11)

| Việc | Trạng thái | Kết quả |
|---|---|---|
| Manifest 3 trạng thái (`validate.unread_data`, `maybe_records`, `intents.absent`) | xong | Public: unanswerable 137 → 49 (các câu còn bảng/cột chưa đọc được giờ bỏ trống). Train 70/70 unanswerable vẫn đúng |
| Mở rộng schema: trường cấp đơn trong sổ bán phẳng (kênh, nhân viên, nhóm khách, khách trả, còn nợ, phí ship, giảm giá HĐ, nhóm hàng…) | xong | dev_007/008 đọc được nhân viên, kênh, nhóm khách. Train 3000/3000, doanh thu 144/144 |
| Bỏ mặc định "doanh thu" của parser luật | xong | 87 câu public không khớp từ khoá nào: giờ không có plan |
| LLM được chọn `other` (+ ví dụ trong system prompt) | xong | chưa đo trên GPU |
| Rulebook analyzer (`datamate/rules/analyzer.py`): băm từng dòng, glossary thuật ngữ mới/đổi, khớp cụm từ có dấu, cụm quen thuộc ở train được mở rộng | xong | Public: 32 thuật ngữ, 51 câu bị gắn cờ. Train: 1 câu gắn cờ nhầm |
| Độ lạ (`qa/novelty.py`, từ điển `configs/vocab_seen.txt`) | xong | |
| Quyết định (`qa/decide.py`) + formatter + `datamate/pipeline.py` + `scripts/predict.py` | xong | Train (chỉ parser luật): PA 0,980. Public (chỉ parser luật): trả lời 595, bỏ trống 405 |
| Notebook Kaggle: cell dự đoán public có LLM | xong | chờ chạy |
| **Nộp public lần 1** (chỉ parser luật, 595 câu trả lời) | 03/11 | **PA 0,189** ⇒ khoảng 392 đúng / 203 sai: **34% câu trả lời sai**. Kiểm tay: thư viện tính đúng (doanh thu dev_001 khớp từng đồng); lỗi nằm ở hiểu câu |
| Kiểm tra plan ↔ câu hỏi (`qa/consistency.py`): mọi con số được dùng; "nhóm" phải có bộ lọc; dạng câu hỏi ↔ type; kỳ trạng thái với đại lượng theo kỳ; thực thể có trong câu; **mọi từ được giải thích** (từ vựng theo intent, học từ train, `configs/intent_vocab.json`) | xong | Báo nhầm: 2/3000 (số) + 2,2% dev/holdout (từ vựng, học trên `fit`). Train: sai 30 → 12, PA 0,980 → 0,985 |
| Nhóm khách / kênh không có trong shop ⇒ bỏ trống (không trả 0, không unanswerable) | xong | |
| Public sau các lớp trên (chỉ parser luật) | 03/11 | trả lời 522, bỏ trống 478 — chờ nộp lần 2 để đo |
| Kiểm chứng ngược (G2), tập stress (mục 3), LLM sinh code (G5), Pha A dev_003/012 | chưa | |

Không làm: thêm regex hay intent theo từng câu public. Intent mới chỉ thêm khi khái niệm có **định nghĩa trong rulebook** và xuất hiện trong nhiều shop. Mọi intent mới vẫn phải qua G2/G3.
