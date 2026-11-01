# Benchmark LLM parser

Thiết lập chung:
- Kaggle 2×T4 16GB, fp16, không thinking, greedy.
- 6 ví dụ few-shot lấy từ split `fit` (shop khác).
- Đo trên split `dev`. Script: `scripts/eval_llm_parser.py`, notebook `notebooks/kaggle_llm_benchmark.ipynb`.

| Ngày | Model | Backend | n | JSON hợp lệ | Intent đúng | PA llm | PA rule | PA agree | PA llm_else_rule | s/câu | Ghi chú |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 01/11 | Qwen3.5-9B | vLLM nightly, TP2, `--text-only --max-num-seqs 16 --enforce-eager --max-model-len 4096` | 50 | 100% | 100% | 1.000 | 1.000 | 1.000 | 1.000 | 1.44 | Nạp model 518s. FA2 không có trên T4, vLLM tự chuyển sang cách tính khác |
| 01/11 | Qwen3.5-9B | transformers 4-bit | 50 | 100% | 100% | 1.000 | 1.000 | 1.000 | 1.000 | 5.44 | Thiếu `flash-linear-attention` / `causal_conv1d` nên chạy bản PyTorch thuần (chậm) |

Lưu ý:
- 50 câu đầu của dev đều dễ: parser luật cũng đúng hết, nên chưa phân biệt được LLM với parser luật.
- Cần chạy đủ 513 câu dev và 512 câu holdout.

Lịch sử lỗi môi trường:
1. Cài vLLM nightly kéo về torch CUDA 13.0, lệch với torchaudio của Kaggle (CUDA 12.8). Sửa: gỡ torchaudio.
2. Hết bộ nhớ ở GPU 1 với cấu hình mặc định. Sửa: `--text-only` (bỏ phần profiling ảnh), `--max-num-seqs 16`, `--enforce-eager`, `--max-model-len 4096`.
