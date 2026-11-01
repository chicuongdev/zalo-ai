# 09 — Chiến lược kiểm thử & đo lường từng tầng

Mục tiêu: biết **lỗi nằm ở tầng nào**. Nhờ kiến trúc tách tầng, phần lớn công việc (Pha A, thư viện ngữ nghĩa, period, formatter) **không cần GPU** và phát triển được ngay trên máy local.

## 1. Bộ dữ liệu kiểm chứng: "QueryPlan vàng" cho train

Ý tưởng then chốt: một QueryPlan được coi là **đúng** nếu thực thi nó cho ra **đúng đáp án train**. Ta có 3.000 đáp án nên có thể sinh và kiểm chứng plan tự động:

1. `scripts/label_plans.py`: với mỗi câu train, sinh plan ứng viên. Có ba nguồn:
   - Parser regex/template, vì câu hỏi theo template nên phủ được phần lớn.
   - LLM lớn nhất có thể dùng khi dev. Vì đây chỉ là bước tạo nhãn, không chạy lúc inference, nên có thể dùng model tốt hơn hoặc gọi nhiều lần.
   - Sửa tay cho phần còn lại.
2. Thực thi plan → so đáp án bằng `scoring.py`.
   - **Khớp** ⇒ plan vàng.
   - **Không khớp** ⇒ lỗi ở plan **hoặc** ở thư viện ngữ nghĩa/Pha A, cần xem tay.
3. Kết quả gồm:
   - Bộ (câu → plan vàng) để đo parser.
   - Danh sách lỗi thư viện ngữ nghĩa cần sửa.
   - **Dữ liệu SFT** cho parser ([../07_fine_tuning.md](../07_fine_tuning.md)).

## 2. Kiểm thử theo tầng

| Tầng | Cách kiểm | Chỉ số | Mục tiêu |
|---|---|---|---|
| A3 Parsers | Unit test với các mẫu bẩn thu từ EDA | Pass 100% | 100% |
| A1–A6 Pha A | Mọi shop train dựng được; validator | Điểm validator | ≥ 0.99 mọi shop |
| Pha A tổng quát | **Leave-one-out theo kiểu nguồn**: bỏ từ điển đồng nghĩa của shop đang thử → còn ánh xạ đúng không (mô phỏng shop lạ) | % cột ánh xạ đúng | ≥ 95% |
| B4 Period | Unit test từng dòng rulebook §2 (+ mép tháng, năm nhuận, tuần qua năm, Tết) | Pass | 100% |
| S Thư viện ngữ nghĩa | **Tái tạo oracle**: chạy plan vàng | Accuracy trên câu answerable | ≥ 98% |
| B5 Answerability | Trên 70 câu unanswerable train + toàn bộ câu answerable | Precision / recall unanswerable | P ≥ 0.95, R ≥ 0.8 |
| B1+B2 Parser | So với plan vàng trên business dev/holdout | Exact-match intent, slot accuracy | Intent ≥ 97%, plan ≥ 92% |
| B3 Entity | So id thực thể trong plan vàng | Accuracy | ≥ 98% |
| B7 Dự phòng | Ép một phần câu train đi đường dự phòng (giả lập intent lạ) | Accuracy / abstain | Đo để hiệu chỉnh ngưỡng |
| B8 Quyết định | Đường PA theo ngưỡng trên dev | PA | Tối đa |
| B9 Formatter | Round-trip qua `scoring.py` với đáp án train | Pass | 100% |
| End-to-end | `scripts/evaluate.py` trên dev/holdout | PA, accuracy, % abstain | Theo dõi mỗi phiên bản |

## 3. Chia dữ liệu

- Theo **business**, cố định từ đầu:
  - `fit` (~20 shop): xây từ điển, few-shot, SFT.
  - `dev` (~5): tune ngưỡng, prompt.
  - `holdout` (~5): đánh giá cuối giai đoạn. Chọn sao cho có **kiểu nguồn** và **ngành** khác `fit`, ví dụ giữ riêng một shop SQLite, một sổ tay nhiều sheet, một nhà hàng.
- Danh sách lưu trong `plan/eda_findings.md` khi chốt.

## 4. Phát triển không cần GPU

| Việc | Cần GPU? |
|---|---|
| Pha A (trừ ánh xạ LLM — tạm dùng từ điển cho train) | Không |
| Thư viện ngữ nghĩa + tái tạo oracle bằng plan vàng | Không |
| Period, answerability, formatter, scoring | Không |
| Parser regex/template (baseline + dùng để kiểm chéo) | Không |
| Parser LLM, entity LLM, dự phòng, benchmark model | **Có** (≥ 24GB cho 14B FP8/AWQ; dev nhanh với 4B/8B) |

⇒ Có thể bắt đầu ngay G1 trên máy local; GPU chỉ cần từ khi làm parser LLM.

## 5. Theo dõi phiên bản

Mỗi lần chạy đánh giá ghi một dòng vào `plan/changelog.md`: phiên bản code, model, PA dev/holdout theo tầng, % abstain, thời gian. Không tune theo public leaderboard.
