# 03 — Lựa chọn model open-source

## Cập nhật 01/11/2026 — ứng viên sau khi khảo sát model mới (tới 09/2026)

| Vai trò | Model | Tham số (HF) | Phát hành / licence | Ghi chú |
|---|---|---|---|---|
| **Chính** | **Qwen/Qwen3.5-9B** | ~10B (gồm vision encoder) | 02–03/2026, Apache-2.0 | Bám chỉ dẫn tốt hơn Qwen3-30B (số do Alibaba công bố). Tắt thinking bằng `enable_thinking=False`. Kiến trúc lai Gated DeltaNet, trang model yêu cầu vLLM nightly ⇒ **rủi ro môi trường** |
| Dự phòng | Qwen/Qwen3-14B (AWQ khi chạy trên Kaggle) | 14.8B | 04/2025, Apache-2.0 | vLLM hỗ trợ ổn định. Gần trần 15B: không còn chỗ cho model phụ |
| Nhẹ / thử nhanh | Qwen/Qwen3.5-4B, Qwen/Qwen3-8B | ~4–5B / 8.2B | | Dùng để thử pipeline, hoặc nếu bị giới hạn thời gian chạy |

**Bị loại vì vượt 15B tổng** (MoE tính đủ experts): Qwen3.6-27B, Qwen3.6-35B-A3B, Gemma 4 bản 26B MoE và 31B, gpt-oss-20b.

**Vì sao 9B là đủ:** LLM chỉ gắn nhãn câu hỏi thành QueryPlan. Mọi phép tính do thư viện ngữ nghĩa làm, và thư viện tái tạo 3000/3000 đáp án train. Parser luật đã cho PA ≈ 0,98 trên train. LLM cần bổ sung cho các cách hỏi mới ở private.

**Không cần fine-tune mới chạy được:** chạy zero-shot kèm few-shot. Prompt gồm catalog intent, ngữ cảnh shop (manifest, enum, tên thực thể khớp) và 6 plan vàng gần nhất lấy bằng BM25 **từ shop khác**. Fine-tune LoRA (G5) chỉ làm khi số đo dev cho thấy cần.

**Benchmark trên Kaggle** (`notebooks/kaggle_llm_benchmark.ipynb`, `scripts/eval_llm_parser.py`):
- Môi trường: 2×T4 16GB, không có bf16, nên dùng `dtype=half`. 9B chạy fp16 với tensor-parallel 2; 14B dùng bản AWQ.
- Đo trên dev (513 câu): tỉ lệ JSON hợp lệ, tỉ lệ intent đúng so với plan vàng, PA của 5 cách kết hợp (`rule`, `llm`, `agree`, `llm_else_rule`, `rule_else_llm`), thời gian/câu.
- **Luật chốt:** model có PA cao nhất ở cách kết hợp tốt nhất. Thời gian phải ≤ 20 giây/câu trên T4 (5090 nhanh hơn nhiều). Nếu Qwen3.5 không chạy được trên vLLM bản release ổn định thì chọn Qwen3-14B.
- Kết quả ghi vào `plan/benchmarks.md`.
- Docker cuối cùng vẫn phải chạy thử trên RTX 5090 thuê (FP8/BF16) trước khi nộp.

## 0. LLM làm gì trong kiến trúc đã chốt ([thiet_ke/](thiet_ke/00_tong_quan.md))

| Vai trò | Tần suất | Yêu cầu chính | Chế độ |
|---|---|---|---|
| **Parser câu hỏi** (B2): câu văn nói → QueryPlan JSON | Mỗi câu (quan trọng nhất) | Hiểu tiếng Việt không dấu/teencode, bám schema JSON | Guided JSON, không thinking, có thể fine-tune LoRA |
| Chọn thực thể khi mơ hồ (B3) | Một phần câu | Nhanh | Guided enum |
| Ánh xạ cột / giá trị (A4) | Vài lần mỗi shop | Đọc README + header + mẫu | Guided JSON, có thể bật thinking |
| Đọc rulebook khác train (R) | Một lần mỗi lần chạy | Hiểu luật | Thinking |
| **Sinh code dự phòng** (B7) | Câu ngoài catalog | Code pandas/DuckDB tốt | Text, có thể thinking |

⇒ Một model đa năng 14B (Qwen3-14B) phủ mọi vai trò. Benchmark ưu tiên **độ chính xác parse trên plan vàng** ([thiet_ke/09](thiet_ke/09_chien_luoc_kiem_thu.md)), sau đó mới tới chất lượng sinh code. Model text-to-SQL chuyên dụng giảm vai trò: chỉ còn là ứng viên cho đường dự phòng.

## 1. Luật áp dụng (Rule 2)

- Weights **public trước 01/10/2026**, licence cho phép sử dụng (Apache-2.0, MIT, Qwen licence, Gemma terms… — đọc kỹ từng cái).
- **Tổng tham số ≤ 15B** cộng **tất cả** model dùng lúc inference: LLM + embedding + reranker + classifier, dù load cùng lúc hay lần lượt. MoE tính **toàn bộ** experts.
- Quantize tự do (FP8, AWQ, GPTQ, GGUF), fine-tune tự do. Khai báo model trong README.

⚠️ Bẫy ngân sách: một model 14.8B + embedder bge-m3 (0.57B) = **15.37B → vi phạm**. Model đa phương thức (vd Gemma-3-12B) có thể có vision encoder được tính vào tổng.
⚠️ Bị loại do tổng tham số: Qwen3-30B-A3B (~30.5B), Qwen3-Coder-30B-A3B, gpt-oss-20b (~21B), các model 32B.

## 2. Danh sách ứng viên

> Số tham số là xấp xỉ theo hiểu biết hiện tại — **bắt buộc xác minh trên Hugging Face** (config/safetensors, ngày release, licence) trước khi chốt. Đồng thời **quét HF các model mới hơn** (phát hành tới 09/2026) cùng tầm ≤14B, đặc biệt dòng Qwen/Gemma/Phi/DeepSeek/Mistral và các model text-to-SQL mới.

### 2.1 LLM tổng quát (reasoning + code + tiếng Việt)

| Model | ~Params | Điểm mạnh | Lưu ý |
|---|---|---|---|
| **Qwen3-14B** | 14.8B | Reasoning (thinking mode), code tốt, đa ngôn ngữ gồm tiếng Việt, hỗ trợ vLLM tốt | Gần chạm trần 15B → không còn chỗ cho embedder |
| **Qwen3-8B** | 8.2B | Cân bằng tốt tốc độ/chất lượng | Còn ~6.8B cho model phụ |
| **Qwen3-4B-Instruct-2507 / Thinking-2507** | 4.0B | Rất mạnh so với kích thước, context dài | Hợp làm router/normalizer/verifier |
| Phi-4 / Phi-4-reasoning | 14.7B | Reasoning toán/logic mạnh | Tiếng Việt yếu hơn Qwen — cần kiểm |
| Gemma-3-12B-it | ~12.2B | Đa ngôn ngữ tốt | Tính cả vision encoder; tool/code kém Qwen |
| DeepSeek-R1-Distill-Qwen-14B | 14.8B | Reasoning dài | Chậm, dễ lan man, tiếng Việt trung bình |

### 2.2 Model code

| Model | ~Params | Ghi chú |
|---|---|---|
| **Qwen2.5-Coder-14B-Instruct** | 14.7B | Code pandas/SQL rất tốt, không có thinking mode |
| Qwen2.5-Coder-7B-Instruct | 7.6B | Bản nhẹ, base tốt để fine-tune |

### 2.3 Model text-to-SQL chuyên dụng (cho phương án SQL/DuckDB)

| Model | ~Params | Ghi chú |
|---|---|---|
| **OmniSQL-7B / 14B** | 7.6B / 14.7B | Fine-tune từ Qwen2.5-Coder trên dữ liệu SQL tổng hợp lớn |
| XiYanSQL-QwenCoder-7B / 14B | 7.6B / 14.7B | SOTA BIRD/Spider ở tầm này (tại thời điểm phát hành) |
| Arctic-Text2SQL-R1-7B / 14B | 7.6B / 14.7B | Huấn luyện bằng RL với reward thực thi |

Hạn chế: chủ yếu huấn luyện trên câu hỏi tiếng Anh và schema sạch → cần Normalizer/Planner tiếng Việt phía trước, hoặc fine-tune lại.

### 2.4 Tiếng Việt chuyên biệt (tham khảo, dùng cho normalizer nếu cần)

Vistral-7B-Chat, SeaLLMs-v3-7B, Arcee-VyLinh (~3B). Thường **không** cần nếu Qwen3 xử lý tốt câu không dấu — kiểm trong benchmark.

### 2.5 Embedding / retrieval (cho few-shot, khớp thực thể)

| Lựa chọn | ~Params | Ghi chú |
|---|---|---|
| **BM25 / rapidfuzz** | 0 | Không tốn ngân sách — ưu tiên dùng trước |
| multilingual-e5-small | ~0.12B | Nhẹ, đủ cho chọn few-shot |
| bge-m3 | ~0.57B | Mạnh hơn, đắt ngân sách |

## 3. Các combo đề xuất (tổng ≤ 15B)

| Combo | Thành phần | Tổng | Khi nào chọn |
|---|---|---|---|
| **A — Một model mạnh** | Qwen3-14B (planner + coder + verifier, đổi vai bằng prompt) + BM25 | ~14.8B | Mặc định để bắt đầu; đơn giản, mạnh nhất về reasoning |
| **B — Chia vai** | Qwen3-8B (coder) + Qwen3-4B-2507 (normalizer/planner/verifier) + e5-small | ~12.3B | Nếu cần nhanh hơn hoặc verifier độc lập giúp abstain tốt hơn |
| **C — Code chuyên dụng** | Qwen2.5-Coder-14B *hoặc* OmniSQL/XiYan-14B + BM25 | ~14.7B | Nếu benchmark cho thấy code/SQL quan trọng hơn reasoning |
| **D — Fine-tune** | Base của combo thắng + **LoRA** từ [07](07_fine_tuning.md) | như base | Giai đoạn G4 |

Mẹo: nhiều LoRA trên **cùng một base** (vLLM multi-LoRA) cho các vai khác nhau — base chỉ tính một lần, adapter rất nhỏ. **Cần hỏi BTC xác nhận** cách tính tham số adapter.

## 4. Kế hoạch benchmark (G0–G1)

1. Chọn **dev set ~300 câu** từ business train hold-out ([04](04_du_lieu_va_eda.md)), phân tầng theo type.
2. Cùng pipeline, cùng prompt, chỉ đổi model: Qwen3-14B (thinking on/off), Qwen3-8B, Qwen2.5-Coder-14B, OmniSQL-14B (chế độ SQL), Phi-4, + model mới tìm được.
3. Đo: accuracy, PA (+1/0/−1), tỷ lệ code chạy lỗi, latency trung bình/câu, tokens sinh ra, VRAM.
4. Bảng kết quả lưu vào `plan/benchmarks.md` (tạo khi chạy). Chốt combo theo PA dev, ràng buộc thời gian là điều kiện cần.

## 5. Serving

- **vLLM** (OpenAI-compatible server hoặc offline `LLM` API), build hỗ trợ **Blackwell / CUDA ≥ 12.8**.
- 2× RTX 5090 (32GB mỗi card):
  - 14B BF16 ~30GB weights → chạy **tensor-parallel = 2**, hoặc **FP8** (~15GB) → **1 bản / GPU, data-parallel** (thông lượng cao hơn, đơn giản hơn). Ưu tiên FP8 + DP nếu FP8 không giảm chất lượng trên dev.
  - Prefix caching bật: schema card + rule card giống nhau cho mọi câu cùng business → tiết kiệm lớn.
- Decoding: greedy (temperature 0), seed cố định, `max_tokens` giới hạn; thinking mode giới hạn ngân sách token.
- Môi trường dev: không có GPU local → cần GPU thuê/lab (≥ 24GB cho 8B BF16 hoặc 14B FP8/AWQ). Có thể dev trên model 4B/8B quantized rồi xác nhận trên 14B.
