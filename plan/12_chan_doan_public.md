# 12 — Chẩn đoán: vì sao public sai nhiều (PA 0,189 → 0,26)

## Hiện tượng
- Train/dev/holdout: policy `safe` gần như 0 câu sai.
- Public: khoảng 133–203 câu sai trên 527–595 câu đã trả lời (độ chính xác chỉ khoảng 66–75%).
- Khoảng cách này quá lớn để do parser hiểu sai câu hỏi: parser đã đạt 97–99% trên các shop chưa từng thấy (dev/holdout).
  Giả thuyết: **dữ liệu public có cách ghi sổ mà Pha A (đọc dữ liệu) chưa từng gặp**, nên thư viện tính đúng công thức
  nhưng trên một bảng bị đọc sai. Một bảng đọc sai làm sai **mọi** câu của shop đó, kể cả khi LLM và luật đồng thuận
  (đồng thuận không giúp gì khi dữ liệu sai).

## Cách kiểm chứng (không dùng leaderboard)
Với mỗi shop, đối chiếu đầu ra của thư viện với một phép tính độc lập viết trực tiếp từ file gốc theo README
(số đơn, số đơn trả hoặc huỷ, doanh thu theo tháng).

## Nguyên nhân gốc đã tìm thấy (đều là lỗi Pha A)
| # | Shop | Cách ghi sổ | Hậu quả trước khi sửa | Luật sửa (tổng quát) |
|---|---|---|---|---|
| A | dev_011 | STT, khách, bớt, khách trả chỉ ghi ở **dòng đầu** mỗi đơn | mỗi dòng thành một đơn (6043 thay vì 3819 đơn): số đơn, khách, trả hàng đều sai | cột "STT" để trống đúng ở các dòng mà cột cấp đơn cũng trống ⇒ là mã đơn (`_is_group_key`) |
| B | dev_014 | STT **lặp lại** ở mọi dòng, mỗi tháng một sheet, tên khách viết khác nhau trong cùng đơn | 10282 "đơn" thay vì 6334 | cột lặp thành cụm liên tiếp và có ít nhất một cột cấp đơn không đổi trong cụm ⇒ mã đơn |
| C | dev_011, 013, 014 | trạng thái đơn ghi ở **Ghi chú** (luật mới của rulebook public) | đơn trả hoặc huỷ vẫn được tính vào doanh thu | `status_from_note`: chỉ nhận từ ngữ huỷ, trả, đang giao rõ ràng; không nhắc gì thì là hoàn thành; "trả góp/trả trước/trả nợ" không phải trả hàng |
| D | dev_013 | sổ **nhập hàng** bị đọc thành sổ bán | tiền nhập cộng vào doanh thu | bảng có cột nhà cung cấp không thể là bảng bán (và ngược lại với cột khách) |
| E | dev_013 | cột TT có mô tả README dài hơn mẫu | thiếu thành tiền | khớp mô tả README theo tiền tố (cụm ≥ 3 từ) |
| F | dev_013 | dòng "Voucher", "Dùng n điểm", "Phí ship" nằm trong sổ bán | voucher bị trừ và phí ship bị cộng vào doanh thu (rulebook §1 cấm cả hai) | dòng điều chỉnh không có số lượng ⇒ chuyển thành giảm giá hoặc phí giao của đơn |
| G | dev_002 | topping ghi chung ô với món (luật mới) | 1095 dòng thành mặt hàng lạ; số lượng theo món và theo topping sai | tách khi món và topping đều là hàng đã biết và topping có tiền trong ngoặc |

Đã kiểm chứng khớp số liệu độc lập: dev_011 (số đơn theo tháng 263/282, 29 đơn trả) và dev_014 (393/398 đơn theo tháng, 68 đơn trả).

## Việc còn lại
- dev_004: "Hàng theo bó, 1 bó = 10 cây" ghi bằng văn xuôi trong README; cần kiểm tra bộ đọc quy đổi.
- dev_011/014: sheet "Ghi tắt" (tên viết tắt sang tên đầy đủ và loại hàng) chưa được đọc, nên câu hỏi theo mặt hàng hoặc loại máy sẽ hỏng.
- dev_003 (không có ngày đơn), dev_012 (sửa xe): đang bỏ trống hết. Không gây sai, nhưng mất điểm.
- Thêm vào validator một tín hiệu "nghi đọc sai": tỉ lệ đơn chỉ có một dòng và có cột cấp đơn bị trống, bảng bán có cột nhà cung cấp…
  Khi gặp tín hiệu này ở private test thì bỏ trống cả shop thay vì trả lời sai.
