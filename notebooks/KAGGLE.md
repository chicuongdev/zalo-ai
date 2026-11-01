# Chạy benchmark LLM trên Kaggle

## 0. Tài khoản (một lần)
- Đăng nhập kaggle.com → avatar → **Settings** → **Phone verification**. Chưa xác minh số điện thoại thì không bật được GPU và Internet.
- Quota GPU khoảng 30 giờ/tuần, mỗi phiên tối đa 12 giờ. Xem ở Settings → Quotas.

## 1. Chuẩn bị file trên máy
```
python scripts/label_plans.py          # nếu chưa có out/gold_plans.jsonl
python scripts/make_kaggle_bundle.py   # tạo dist/datamate_code.zip (~0.2 MB)
```
Có hai file để tải lên: `dist/datamate_code.zip` và `train.zip` (~128 MB).

## 2. Tạo 2 dataset PRIVATE
kaggle.com → **Datasets** → **+ New Dataset**:

| Tên dataset | File | Visibility |
|---|---|---|
| `datamate-train` | `train.zip` | **Private** |
| `datamate-code` | `dist/datamate_code.zip` | **Private** |

Kaggle tự giải nén file zip, notebook xử lý được cả hai trường hợp (giải nén hoặc không). Khi sửa code: chạy lại bước 1, mở dataset `datamate-code` → **New Version** → tải zip mới lên.

## 3. Tạo notebook
- **Code** → **+ New Notebook** → menu **File → Import Notebook** → chọn `notebooks/kaggle_llm_benchmark.ipynb`.
- Cột phải → **Add Input** → tab *Your Work / Datasets* → thêm `datamate-train` và `datamate-code`.
- Cột phải → **Session options**: **Accelerator = GPU T4 x2**, **Internet = On**, Persistence = Files (tuỳ chọn).
- (Tuỳ chọn) **Add-ons → Secrets** → thêm `HF_TOKEN` (token đọc từ huggingface.co/settings/tokens). Model Qwen là public nên thường không cần.

## 4. Chạy
1. Cell cấu hình: `RUN = "qwen3.5-9b"`, `LIMIT = 50` (thử nhanh), `SPLIT = "dev"`.
2. Chạy lần lượt từng cell bằng Shift+Enter:

| Cell | Việc | Thời gian ước tính |
|---|---|---|
| copy code + data | chép code, liên kết dữ liệu | vài giây |
| cài thư viện | cài vLLM, transformers | 5–10 phút |
| kiểm tra | pytest + chạy plan vàng; **phải thấy `llm PA=1.0000`** | 1–2 phút |
| tải model | khoảng 19 GB cho 9B, lưu vào /tmp | 3–8 phút |
| benchmark vLLM | in `report.txt` | 50 câu: vài phút; 513 câu: 20–60 phút |
| dự phòng transformers | chỉ chạy khi vLLM lỗi | chậm |
| phân tích lỗi | in các câu LLM trả lời sai | vài giây |

3. Chạy được với 50 câu thì đặt `LIMIT = 0` và chạy lại cell benchmark (không cần cài hay tải model lại).
4. Đổi model: **Run → Restart session**, sửa `RUN` (ví dụ `qwen3-14b-awq`), chạy lại từ đầu.

## 5. Lấy kết quả
- Kết quả nằm trong `/kaggle/working/results/<run>/report.txt` và `rows.jsonl`, xem ở panel **Output** bên phải và tải về.
- Muốn giữ lại sau khi tắt phiên: **Save Version → Quick Save**.
- Gửi lại: nội dung `report.txt` và output cell phân tích lỗi.

## 6. Lỗi hay gặp
| Triệu chứng | Cách xử lý |
|---|---|
| `CUDA out of memory` | thêm `--gpu-mem 0.85` hoặc `--max-model-len 6144` vào `extra` của model |
| vLLM báo không hỗ trợ kiến trúc / GPU (compute capability 7.5) | dùng cell dự phòng transformers, hoặc chọn `qwen3-14b-awq` / `qwen3-8b` |
| `bfloat16 is not supported` | kiểm tra đã có `--dtype half` |
| `PyTorch and TorchAudio were compiled with different CUDA versions` | `!pip uninstall -y torchaudio` rồi chạy lại cell benchmark (cell cài thư viện mới đã tự làm bước này) |
| Cell kiểm tra in `GPU visible: False` | Driver Kaggle cũ hơn CUDA của torch mà vLLM kéo về. Gửi lại output cell kiểm tra |
| Lỗi torch khác sau khi cài vLLM | Restart session, chạy lại từ cell cài thư viện; gửi lại log |
| Hết đĩa | model phải nằm ở `/tmp/models` (đĩa `/kaggle/working` chỉ khoảng 20 GB) |
