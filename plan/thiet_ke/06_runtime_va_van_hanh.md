# 06 — Runtime: tiến trình, song song, cache, log, thời gian, tái lập

## 1. Tiến trình trong container

```
predict.sh
 └─ python -m datamate.main --data /data --out /result
     ├─ [P0] khởi động LLM service (subprocess vLLM, OpenAI-compatible, localhost)
     │      GPU0 + GPU1: 1 replica / GPU (FP8) — hoặc TP=2 nếu BF16 không vừa 1 GPU
     ├─ [P1] RulebookAnalyzer + Calendar (CPU, trong lúc vLLM đang load)
     ├─ [P2] Pha A: ProcessPool (CPU, ~8 process) — mỗi business 1 task
     │      gọi LLM qua HTTP cho Schema Mapper; xong shop nào → đẩy shop đó vào hàng đợi "sẵn sàng"
     ├─ [P3] Pha B: asyncio worker pool (~32 câu đồng thời)
     │      lấy câu của các shop đã sẵn sàng; B1–B6/B8–B9 chạy trong process chính
     │      (DuckDB read-only theo shop); B7 chạy subprocess sandbox
     └─ [P4] Writer: append submission.jsonl + log từng câu, flush + fsync sau mỗi câu
```

- Pha A và Pha B **chồng lên nhau**: shop nào nạp xong thì trả lời câu của shop đó ngay. LLM được dùng xen kẽ bởi cả hai pha.
- vLLM gom batch các request đồng thời → tận dụng GPU. Prefix caching cho phần prompt tĩnh theo shop.
- Mặc định **không** cần GPU cho Pha A, trừ các lần gọi LLM ánh xạ cột.

## 2. Cache & trạng thái

| Cache | Phạm vi | Ghi chú |
|---|---|---|
| `ShopStore` (DuckDB file + manifest + entity index) | `/tmp/work/<biz>/` | Dựng một lần mỗi lần chạy; khi dev có thể dùng lại giữa các lần chạy (khoá theo hash file) |
| Kết quả hàm ngữ nghĩa | bộ nhớ, `(biz, intent, slots)` | Nhiều câu hỏi lại cùng thứ |
| Prompt prefix | vLLM | Tự động |
| Few-shot index (BM25) | đóng gói sẵn từ train | Chỉ chứa câu **train** (Rule 6) |

## 3. Log (`/result/logs/<qid>.json`, một file một câu + `run.jsonl` tổng)

```json
{"id": "q_…", "business_id": "biz_…", "question": "…", "as_of_date": "…",
 "normalized": "…", "plan": {…}, "plan_retries": 0,
 "entities": [{"mention": "…", "id": "SP0042", "score": 97, "margin": 21}],
 "periods": [{"expr": {…}, "from": "…", "to": "…", "clipped": false}],
 "answerability": {"status": "answerable", "rule": null},
 "path": "semantic|fallback", "fallback_code": "…", "exec_output": "…",
 "raw_value": …, "signals": {…}, "p_correct": 0.93, "decision": "answer",
 "final": {"type": "number", "answer": 48250000},
 "timing_ms": {"normalize": 2, "parse": 820, "exec": 35, "total": 900}}
```

Đủ trường bắt buộc (id, đáp án cuối, thời gian), cộng toàn bộ đường đi để giải trình với BTC (Rule 8).

## 4. Ngân sách thời gian (6h cho ~500 câu, gồm load model)

| Bước | Ước tính | Ghi chú |
|---|---|---|
| Load vLLM + model 14B FP8 | 2–5 phút | Song song với P1, P2 |
| Pha A | 10–20 shop × 0.5–3 phút / 8 process | ≈ 5–10 phút |
| Pha B đường chính | ~1–3 s/câu × 500 / 32 đồng thời | vài phút |
| Pha B dự phòng (giả sử 20% câu) | ~20–40 s/câu | ≈ 10–20 phút |
| **Tổng ước tính** | **< 1 giờ** | Dư rất nhiều so với 6h → có thể dùng thêm self-consistency |

**Watchdog**: theo dõi thời gian còn lại.

- Còn < 60 phút → tắt self-consistency.
- Còn < 20 phút → tắt đường dự phòng (câu cần dự phòng → abstain).
- Còn < 5 phút → ghi abstain cho mọi câu còn lại rồi thoát.

## 5. Tái lập (|ΔPA| ≤ 0.03)

- LLM: `temperature=0`, `seed` cố định. Self-consistency dùng seed suy từ **hash nội dung câu hỏi** (không theo id).
- vLLM: bật chế độ batch-invariant nếu phiên bản hỗ trợ; nếu không, đo độ dao động giữa hai lần chạy. Phần lớn đáp án đi qua đường xác định nên dao động nhỏ.
- Không phụ thuộc thứ tự hoàn thành: mỗi câu độc lập; thứ tự dòng trong submission không ảnh hưởng chấm.
- Pha A xác định hoàn toàn trừ các lần gọi LLM ánh xạ (greedy + guided JSON).
- Kiểm thử: chạy image hai lần trên public, so từng đáp án.

## 6. Lỗi & phục hồi

| Lỗi | Xử lý |
|---|---|
| Một file không đọc được | Bỏ file đó, ghi vào manifest; miền liên quan `confidence` thấp |
| Pha A của một shop lỗi | Câu của shop đó → đường dự phòng trên bảng thô đã parse (A3) → vẫn lỗi thì abstain |
| vLLM chết | Khởi động lại một lần; trong lúc chờ, các câu có thể trả lời bằng regex-only parser (nếu tin cậy cao) |
| Exception bất kỳ ở một câu | Bắt tại worker → abstain câu đó, log traceback; không bao giờ làm chết toàn bộ |
