# 02 — Kiến trúc (tóm tắt)

> Bản chi tiết: thư mục [thiet_ke/](thiet_ke/00_tong_quan.md). File này chỉ tóm tắt.
> Phiên bản trước đề xuất "LLM sinh code pandas cho mọi câu". Sau EDA dữ liệu thật ([eda_findings.md](eda_findings.md)), kiến trúc đổi sang **chuẩn hoá dữ liệu + thư viện ngữ nghĩa xác định + LLM phân tích câu hỏi**, giữ sinh code làm đường dự phòng.

## Ba lý do thay đổi

1. **Đáp án do oracle xác định theo rulebook rất chi tiết.** Có nhiều luật tinh vi: bỏ cả đơn trả một phần, "tháng này" so cùng số ngày, tie-break theo mã, giá vốn ghi trên dòng bán… Cài luật một lần trong code và test kỹ thì đáng tin hơn để LLM 14B tự nhớ luật ở mỗi câu.
2. **Dữ liệu thô rất đa dạng** (7+ kiểu nguồn, tiền `1tr440`, header 2 tầng, mỗi tháng một sheet). Xử lý **một lần mỗi shop** về mô hình chuẩn sẽ ít lỗi hơn xử lý lại ở mỗi câu.
3. **Câu hỏi sinh từ ~40–60 template** ⇒ việc khó của LLM là **hiểu câu văn nói** để chọn intent và trích tham số. Việc này hợp với model 14B và fine-tune được.

## Luồng

```
PHA A (mỗi shop):  file thô → đọc → tìm bảng → parse giá trị → ánh xạ cột (từ điển + LLM) → mô hình chuẩn (DuckDB)
                    → kiểm tra → manifest năng lực + chỉ mục thực thể

PHA B (mỗi câu):   câu → chuẩn hoá (Telex/teencode) → LLM → QueryPlan (intent + slot, JSON)
                    → liên kết thực thể → giải kỳ thời gian → kiểm tra trả lời được (manifest)
                    → thực thi hàm ngữ nghĩa  ──(intent lạ / luật đổi)──▶  LLM sinh code trên mô hình chuẩn (sandbox)
                    → kiểm chứng + quyết định (p > 0.5?) → định dạng → ghi submission + log
```

## Thành phần & tài liệu

| Thành phần | Tài liệu |
|---|---|
| Mô hình dữ liệu chuẩn, manifest | [thiet_ke/01](thiet_ke/01_mo_hinh_du_lieu_chuan.md) |
| Pha A: nạp & chuẩn hoá | [thiet_ke/02](thiet_ke/02_nap_va_chuan_hoa_du_lieu.md) |
| Thư viện ngữ nghĩa, catalog intent, rulebook | [thiet_ke/03](thiet_ke/03_tang_ngu_nghia_va_intent.md) |
| Hiểu câu hỏi | [thiet_ke/04](thiet_ke/04_hieu_cau_hoi.md) |
| Thực thi, dự phòng, kiểm chứng, định dạng | [thiet_ke/05](thiet_ke/05_thuc_thi_kiem_chung_tra_loi.md) |
| Runtime, song song, log, thời gian, tái lập | [thiet_ke/06](thiet_ke/06_runtime_va_van_hanh.md) |
| Ví dụ trọn luồng | [thiet_ke/07](thiet_ke/07_luong_vi_du.md) |
| Hợp đồng module, cấu trúc repo | [thiet_ke/08](thiet_ke/08_hop_dong_module_va_repo.md) |
| Kiểm thử từng tầng | [thiet_ke/09](thiet_ke/09_chien_luoc_kiem_thu.md) |
