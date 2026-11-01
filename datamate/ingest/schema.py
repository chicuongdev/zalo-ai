"""Table kinds of the canonical data model and the vocabulary used to recognise them (plan/thiet_ke/01, 02 §A4).

Each kind lists its fields. For every field:
  h    header synonyms (compared after `norm_header`)
  d    README column descriptions (compared after `norm_header`); the README vocabulary is fixed across shops
  w    weight when scoring a table against a kind (distinctive fields weigh more)
`need` lists groups of fields; a table can be of that kind only if every group has at least one mapped field.

Synonyms were collected from the 30 train shops; unseen spellings fall back to fuzzy matching and later the LLM tier.
"""
from __future__ import annotations

import re

from .parsers import strip_accents


def norm_header(s: str) -> str:
    """'T.Tiền' -> 't tien'; 'MaHoaDon' -> 'ma hoa don'; 'Đơn vị (tính)' -> 'don vi tinh'."""
    s = re.sub(r"(?<=[a-zà-ỹđ])(?=[A-ZÀ-ỸĐ])", " ", str(s))          # camelCase split
    s = re.sub(r"(?<=[A-ZĐ])(?=[A-ZĐ][a-zà-ỹđ])", " ", s)              # 'SLQuy' -> 'SL Quy'
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def F(h=(), d=(), w=1.0):
    return {"h": [norm_header(x) for x in h], "d": [norm_header(x) for x in d], "w": w}


# ------------------------------------------------------------------ shared field vocab
ORDER_ID = F(["Mã đơn hàng", "Mã hóa đơn", "Ma don", "Mã GD", "Mã bill", "Mã chứng từ", "Mã giao dịch", "Mã phiếu",
              "Số phiếu", "Số CT", "Số HĐ", "Order ID", "So hoa don", "MaHoaDon", "Mã đơn", "Mã HĐ"], ["mã đơn"], 3)
PRODUCT_ID = F(["Mã hàng", "Mã HH", "Mã SKU", "ID SP", "Mã sp", "ma_sp", "Mã món", "Mã sản phẩm", "MaHangHoa", "Ma hang",
                "Mã hàng hóa", "Mã mặt hàng", "Mã hàng bán", "Mã sản phẩm bán", "SKU"], ["mã hàng"], 2)
PRODUCT_NAME = F(["Tên hàng", "Hàng", "Mặt hàng", "Nội dung", "Product", "Sản phẩm", "Ten hang", "Tên SP", "Tên sản phẩm",
                  "Tên món", "Món", "Chi tiết hàng", "Hàng bán", "Hàng hóa", "Tên mặt hàng", "Tên hàng hóa", "TenHang",
                  "ten_hang"], ["tên hàng", "tên", "tên hàng (file chỉ có mặt hàng có đơn vị lớn)"], 2)
UNIT = F(["Đơn vị tính", "DVT", "ĐVT", "DonVi", "Unit", "dvt", "ĐV tính", "Đơn vị (tính)", "Đ.vị", "DonViTinh", "Đơn vị"],
         ["đơn vị tính"], 1)
QTY = F(["Số lượng", "SL", "S.L", "SL bán", "Sluong", "SoLuong", "Số lượng bán", "Số lượng hàng", "Slg", "so_luong",
         "Số lượng sản phẩm"], ["số lượng"], 2)
QTY_BASE = F(["Số lượng quy đổi", "Quy ra ĐV lẻ", "SL lẻ", "SL quy đổi", "Số lượng lẻ", "SL cơ bản", "SLQuyDoi",
              "SL quy ra lẻ"], ["số lượng đã đổi ra đơn vị cơ bản"], 1.5)
UNIT_PRICE = F(["Đơn giá", "Giá", "Giá bán", "Giá lẻ", "Giá 1 đv", "Giá đơn vị", "Price", "Giá sản phẩm", "Giá niêm yết",
                "don_gia", "GiaDonVi", "Đơn giá (đ)", "Đơn giá bán", "Giá bán lẻ"], ["đơn giá"], 1)
LINE_DISCOUNT = F(["Giảm giá", "Khuyến mãi", "Chiết khấu", "ChietKhau"], ["giảm giá"], 0.5)
LINE_AMOUNT = F(["Thành tiền", "Thanh tien", "T.Tiền", "Amount", "Trị giá", "Tiền bán", "Tiền", "Tổng tiền", "thanh_tien",
                 "TriGia", "Thành tiền (đ)", "Tổng"], ["thành tiền sau giảm"], 2)
SALE_COST = F(["Giá vốn", "Giá vốn lúc bán", "GiaVonLucBan"], ["giá vốn"], 1)
ORDER_DATE = F(["Ngày", "Ngày bán", "Ngày giao dịch", "Ngày lập", "Ngày mua", "Ngày tháng", "Ngày đặt hàng", "NgayBan",
                "ngay_ban", "Thời gian", "NgayLap"], ["ngày bán"], 2)
ORDER_TS = F(["Giờ", "Thời gian tạo", "Giờ tạo đơn", "ThoiGianLap"],
             ["thời điểm đặt đơn (ngày giờ)", "giờ đặt đơn (dòng trả hàng: lúc trả)"], 1)
STATUS = F(["Trạng thái", "Kết quả", "Status", "Trạng thái xử lý", "Trạng thái đơn", "Trạng thái đơn hàng", "Tình trạng",
            "Ghi chú TT", "Xử lý", "TinhTrang", "Tình trạng đơn", "trang_thai"], ["trạng thái đơn"], 1.5)
CUSTOMER_NAME = F(["Khách", "Khách hàng", "Tên khách", "Tên khách hàng", "Đối tác", "Bên mua", "TenKH", "Tên KH",
                   "Khách hàng (tên)"], ["tên khách (Khách lẻ nếu không lưu)"], 1)
CUSTOMER_ID = F(["Mã KH", "Mã khách hàng", "Customer ID", "Mã khách mua", "Số KH", "ma_kh", "Mã KH mua", "MaKhachHang"],
                ["mã khách (trống nếu khách lẻ)", "mã khách"], 1)
NOTE = F(["Ghi chú", "Ghi chu", "Diễn giải", "Nội dung", "DienGiai", "Mô tả"], ["ghi chú"], 0.2)

KINDS: dict[str, dict] = {
    # one row per sale line, order-level fields repeated (or filled down) on every line
    "sales_flat": {
        "fields": {
            "order_id": ORDER_ID, "order_date": ORDER_DATE, "order_ts": ORDER_TS, "status": STATUS,
            "customer_name": CUSTOMER_NAME, "customer_id": CUSTOMER_ID,
            "product_id": PRODUCT_ID, "product_name": PRODUCT_NAME, "unit": UNIT, "qty": QTY, "qty_base": QTY_BASE,
            "unit_price": UNIT_PRICE, "line_discount": LINE_DISCOUNT, "line_amount": LINE_AMOUNT, "sale_cost": SALE_COST,
            "note": NOTE,
        },
        "need": [["order_date"], ["product_id", "product_name"], ["qty", "qty_base"], ["line_amount", "unit_price"]],
    },
    "order_lines": {
        "fields": {
            "order_id": ORDER_ID, "line_no": F(["STT", "Thứ tự", "TT dòng", "No.", "SoThuTu"], ["số thứ tự dòng trong đơn"], 1),
            "product_id": PRODUCT_ID, "product_name": PRODUCT_NAME, "unit": UNIT, "qty": QTY, "qty_base": QTY_BASE,
            "unit_price": UNIT_PRICE, "line_discount": LINE_DISCOUNT, "line_amount": LINE_AMOUNT, "sale_cost": SALE_COST,
        },
        "need": [["order_id"], ["product_id", "product_name"], ["qty", "qty_base"], ["line_amount", "unit_price"]],
    },
    "orders": {
        "fields": {
            "order_id": ORDER_ID, "order_date": ORDER_DATE, "order_ts": ORDER_TS, "status": STATUS,
            "customer_name": CUSTOMER_NAME, "customer_id": CUSTOMER_ID,
            "goods_total": F(["Tổng tiền hàng", "Tien hang", "Tiền hàng trước giảm", "TongTienHang"],
                             ["tổng tiền hàng của đơn (cộng thành tiền các dòng), trước giảm giá của đơn",
                              "tiền hàng của đơn: cộng thành tiền các mặt hàng, trước giảm giá của đơn, chưa gồm phí giao"], 2),
            "order_discount": F(["Giảm giá", "CK", "ChietKhau", "Chiết khấu"], ["giảm giá"], 0.5),
            "shipping_fee": F(["Phí giao hàng", "PhiVanChuyen", "Phí vận chuyển", "Phí ship"], [], 0.5),
            "vat": F(["Thuế GTGT", "ThueGTGT", "VAT", "Thuế"], [], 0.5),
            "grand_total": F(["Tổng sau giảm giá", "Tổng bill", "Tổng đơn", "Phải thu", "TongTien", "Tong tien",
                              "TongThanhToan", "Tổng thanh toán"],
                             ["tổng tiền đơn", "số khách phải trả cho cả đơn (đã tính giảm giá của đơn và phí giao)"], 2),
            "paid": F(["Khách đã trả", "Da tra", "Khách trả", "Thanh toán", "Đã thu", "KhachDaTra"], ["đã thanh toán"], 1),
            "debt": F(["Còn nợ", "Còn lại", "Dư nợ", "Chưa trả", "ConPhaiThu"],
                      ["còn nợ", "số khách còn nợ của đơn (đơn huỷ: 0)"], 1),
            "payment_method": F(["Phương thức thanh toán", "Phương thức TT", "Hình thức thanh toán", "Trả bằng",
                                 "PhuongThucTT"],
                                ["hình thức thanh toán của đơn: cash tiền mặt, transfer chuyển khoản, ewallet ví điện tử, "
                                 "cod giao hàng thu tiền, debt ghi nợ", "hình thức thanh toán"], 1),
            "channel": F(["Kênh bán", "Bán qua", "Loại bán", "Nguồn đơn", "KenhBanHang"], ["kênh bán"], 1),
            "staff_id": F(["Người bán", "Mã NV bán", "MaNhanVien"], ["mã nhân viên bán"], 1),
            "branch_id": F(["MaChiNhanh", "Chi nhánh"], [], 0.5),
            "shift_id": F(["MaCaLam", "Ca làm"], [], 0.5),
            "promo_id": F(["MaKhuyenMai"], [], 0.3),
            "note": NOTE,
        },
        "need": [["order_id"], ["order_date", "order_ts"], ["goods_total", "grand_total", "paid", "status"]],
    },
    "products": {
        "fields": {
            "product_id": PRODUCT_ID,
            "product_name": F(PRODUCT_NAME["h"] + ["TenGoi"], ["tên", "tên hàng"], 2),
            "group": F(["Nhóm hàng", "Nhóm hàng hóa", "Nhóm hàng(3 Cấp)", "Danh mục", "Loại sản phẩm", "Nhom hang", "Phân loại",
                        "DanhMuc"], ["nhóm hàng"], 1.5),
            "base_unit": F(["Đơn vị tính", "ĐVT", "Đơn vị", "Đơn vị cơ bản", "DonViCoSo"], ["đơn vị cơ bản"], 1),
            "list_price": F(["Giá bán", "Giá", "Giá hiện tại", "Giá niêm yết", "GiaBanLe"], ["giá bán hiện tại"], 1),
            "cost_price": F(["Giá vốn", "Giá vốn hiện tại", "GiaVonHang"], ["giá vốn"], 1),
            "item_type": F(["Loại hàng hóa", "loai_hang_hoa"], [], 0.5),
            "vat_rate": F(["TyLeThue"], [], 0.2),
        },
        "need": [["product_name"], ["group", "base_unit", "list_price", "cost_price"]],
    },
    "customers": {
        "fields": {
            "customer_id": F(CUSTOMER_ID["h"] + ["Mã khách lẻ/sỉ"], ["mã khách"], 2),
            "customer_name": F(["Tên khách hàng", "Tên KH", "ten_kh", "KH", "Khách hàng (tên)", "Khách lẻ/sỉ", "TenGoi"],
                               ["tên"], 2),
            "phone": F(["Điện thoại", "Số điện thoại", "Di động", "Phone", "SoDienThoai"], ["số điện thoại"], 1.5),
            "customer_group": F(["Nhóm khách hàng", "Nhóm", "Hạng", "LoaiKhachHang"], ["nhóm khách"], 1),
            "address": F(["Địa chỉ", "Addr", "DiaChiLienHe"], ["địa chỉ"], 1),
            "gender": F(["Giới tính", "NamNu"], [], 1),
            "birthday": F(["Ngày sinh", "Sinh nhật", "ngay_sinh"], [], 0.5),
            "customer_type": F(["Loại hình khách", "Đối tượng KH", "loai_hinh_kh"], [], 0.3),
        },
        "need": [["customer_name"], ["phone", "customer_group", "address", "birthday"]],
    },
    "unit_conversions": {
        "fields": {
            "product_id": F(PRODUCT_ID["h"] + ["Mã sp"], ["mã hàng"], 1),
            "product_name": F(PRODUCT_NAME["h"], ["tên hàng (file chỉ có mặt hàng có đơn vị lớn)", "tên hàng"], 1),
            "big_unit": F(["Đơn vị quy đổi", "ĐV lớn", "ĐV nhập", "Đơn vị", "ĐVT", "DonViTinh"], ["đơn vị lớn (thùng, hộp, tấn...)"], 1),
            "factor": F(["Tỉ lệ quy đổi", "Hệ số", "Hệ số QĐ", "Quy đổi", "Bằng", "HeSoQuyDoi"],
                        ["hệ số: số đơn vị cơ bản trong 1 đơn vị lớn"], 3),
            "base_unit": F(["Đơn vị cơ bản", "ĐV nhỏ", "Đơn vị gốc", "ĐV gốc"], ["đơn vị cơ bản"], 1),
            "big_unit_price": F(["Giá bán", "Giá bán theo đơn vị quy đổi", "GiaDonVi"], [], 0.3),
        },
        "need": [["factor"], ["product_id", "product_name"], ["big_unit"]],
    },
    "payments": {
        "fields": {
            "payment_id": F(["Mã phiếu", "Mã phiếu thu", "Phiếu thu", "Mã GD", "MaPhieuThu", "Mã giao dịch"], ["mã phiếu thu"], 1),
            "order_id": F(["Mã hóa đơn", "Số HĐ", "Mã bill", "Số CT", "Mã giao dịch", "Mã GD", "MaHoaDon", "Mã đơn hàng"], ["mã đơn"], 2),
            "pay_ts": F(["Thời gian", "Thời gian thu", "Ngày thu", "Thời điểm", "NgayGioThu"], ["thời điểm thu"], 1.5),
            "amount": F(["Giá trị", "Tiền", "Số tiền thu", "SoTienThu", "Số tiền"], ["số tiền"], 2),
            "method": F(["Phương thức thanh toán", "Phương thức", "PTTT", "HTTT", "PhuongThuc"], ["hình thức thanh toán"], 1),
            "note": NOTE,
        },
        "need": [["order_id"], ["amount"], ["pay_ts"]],
    },
    "purchases": {
        "fields": {
            "receipt_id": F(["Mã nhập hàng", "Mã đơn nhập", "Số phiếu", "MaPhieuNhap", "Mã phiếu nhập"], ["mã phiếu nhập"], 3),
            "receipt_date": F(["Thời gian", "Ngày nhập", "NgayNhapKho"], ["ngày nhập"], 1.5),
            "supplier_id": F(["Mã NCC", "Mã nhà cung cấp", "MaNhaCungCap"], ["mã nhà cung cấp"], 1.5),
            "supplier_name": F(["Nhà cung cấp"], ["nhà cung cấp"], 1),
            "total": F(["Cần trả NCC", "TongGiaTriNhap", "Tổng tiền"], ["tổng tiền phiếu nhập"], 1),
            "status": F(["Trạng thái", "TinhTrang"], ["trạng thái phiếu nhập"], 0.5),
            "branch_id": F(["MaChiNhanh"], [], 0.2),
            "note": F(["Ghi chú", "Ghi chu", "DienGiai", "Nội dung"], ["ghi chú"], 0.3),
        },
        "need": [["receipt_id"], ["receipt_date"]],
    },
    # purchase lines, optionally flat (receipt date / supplier repeated: hand-kept "sổ nhập hàng")
    "purchase_lines": {
        "fields": {
            "receipt_id": F(["Mã nhập hàng", "Mã đơn nhập", "Số phiếu", "MaPhieuNhap"], ["mã phiếu nhập"], 3),
            "line_no": F(["STT", "SoThuTu"], ["số thứ tự dòng trong phiếu nhập"], 0.3),
            "receipt_date": F(["Ngày nhập", "Thời gian"], ["ngày nhập"], 0.5),
            "supplier_name": F(["Nhà cung cấp"], ["nhà cung cấp"], 0.5),
            "product_id": F(PRODUCT_ID["h"], ["mã hàng"], 1),
            "product_name": F(["Tên mặt hàng", "Product", "Tên hàng"], ["tên hàng"], 1),
            "unit": F(["ĐVT", "ĐVT nhập", "DonViTinh", "Đơn vị"], ["đơn vị nhập"], 0.5),
            "qty": F(["Số lượng", "SL nhập", "SL", "Số lượng nhập"], ["số lượng nhập"], 1.5),
            "unit_cost": F(["Đơn giá", "Giá nhập", "DonGiaNhap"], ["giá nhập một đơn vị (theo đơn vị nhập của dòng)"], 2),
            "amount": F(["Thành tiền"], ["tiền nhập của cả dòng"], 1),
            "lot_id": F(["Lô", "Mã lô", "MaLo"], ["số lô"], 0.5),
            "expiry": F(["Hạn sử dụng", "HSD", "HanSuDung"], ["hạn sử dụng"], 0.5),
            "note": F(["Ghi chú", "Ghi chu", "Nội dung", "Mô tả"], ["ghi chú"], 0.3),
        },
        "need": [["receipt_id"], ["product_id", "product_name"], ["qty"], ["unit_cost", "amount"]],
    },
    "lots": {
        "fields": {
            "receipt_id": F(["Mã nhập hàng", "Mã phiếu nhập", "Mã đơn nhập", "MaPhieuNhap"], ["mã phiếu nhập"], 0.5),
            "product_id": F(PRODUCT_ID["h"], ["mã hàng"], 1),
            "lot_id": F(["Lô", "Mã lô", "MaLo"], ["số lô"], 2),
            "expiry": F(["Hạn sử dụng", "HSD", "HanSuDung"], ["hạn sử dụng"], 2),
            "qty_in_base": F(["Số lượng (ĐVT cơ bản)", "SL nhập (ĐVT cơ bản)", "Số lượng nhập", "SLNhapQuyDoi"],
                             ["số lượng nhập (đơn vị cơ bản)"], 2),
            "unit_cost_base": F(["DonGiaNhap"], [], 0.5),
        },
        "need": [["lot_id"], ["expiry"], ["qty_in_base"], ["product_id"]],
    },
    "line_lots": {
        "fields": {
            "order_id": F(["Mã hóa đơn", "Mã đơn hàng", "MaHoaDon"], ["mã đơn"], 2),
            "line_no": F(["STT", "No.", "SoThuTu"], ["số thứ tự dòng trong đơn"], 0.5),
            "lot_id": F(["Lô", "Mã lô", "MaLo"], ["số lô"], 2),
            "qty_base": F(["Số lượng (ĐVT cơ bản)", "Số lượng", "SL quy ra lẻ", "SLQuyDoi"],
                          ["số lượng bán lấy từ lô (đơn vị cơ bản)"], 1.5),
            "qty_return_base": F(["Số lượng trả (ĐVT cơ bản)", "Số lượng trả", "SL trả (ĐVT cơ bản)", "SLTraQuyDoi"],
                                 ["số lượng khách trả lại (đơn vị cơ bản); lớn hơn 0: đơn đó có trả hàng"], 2),
        },
        "need": [["order_id"], ["lot_id"], ["qty_base"]],
    },
    "stock_snapshot": {
        "fields": {
            "product_id": F(PRODUCT_ID["h"], ["mã hàng"], 1),
            "product_name": F(["Tên hàng", "Hàng hóa", "Product"], ["tên hàng"], 1),
            "unit": F(["ĐVT", "Đơn vị tính", "Đơn vị"], ["đơn vị cơ bản", "đơn vị tính"], 0.5),
            "stock_qty": F(["Tồn cuối", "Tồn cuối kỳ", "Tồn thực", "Ton kho", "Tồn kho"], ["tồn kho (đơn vị cơ bản)"], 3),
        },
        "need": [["stock_qty"], ["product_id", "product_name"]],
    },
    "stock_ledger": {
        "fields": {
            "entry_id": F(["MaGiaoDichKho"], [], 0.5),
            "product_id": F(["MaHangHoa", "Mã hàng"], ["mã hàng"], 1),
            "ts": F(["NgayGioPhatSinh", "Thời gian"], [], 1),
            "entry_type": F(["LoaiGiaoDich"], [], 1),
            "qty_delta_base": F(["SLQuyDoi"], [], 1),
            "doc_type": F(["KieuChungTu"], [], 1),
            "doc_id": F(["MaChungTu"], [], 1),
            "balance_after": F(["TonCuoi"], [], 3),
            "branch_id": F(["MaChiNhanh"], [], 0.2),
        },
        "need": [["balance_after"], ["product_id"], ["ts"]],
    },
    "price_history": {
        "fields": {
            "product_id": F(["Mã sản phẩm", "MaHangHoa", "Mã hàng"], ["mã hàng"], 1),
            "product_name": F(["ten_hang", "TenHang", "Sản phẩm", "Tên hàng"], ["tên hàng"], 1),
            "effective_date": F(["Ngày áp dụng", "NgayApDung"], ["ngày bắt đầu áp dụng giá"], 3),
            "new_price": F(["Giá mới", "GiaBanLe"], ["giá bán áp dụng từ ngày đó (đơn vị cơ bản)"], 2),
            "old_price": F(["Giá cũ"], ["giá trước lần đổi (trống ở dòng đầu mỗi mặt hàng)"], 1),
        },
        "need": [["effective_date"], ["new_price"], ["product_id", "product_name"]],
    },
    "deliveries": {
        "fields": {
            "delivery_date": F(["Ngày giao hàng", "Ngày chở"], ["ngày giao"], 2),
            "order_id": F(["Mã đơn hàng", "Mã bill"], ["mã đơn"], 1),
            "trip_no": F(["Lần giao", "Lượt giao"], ["đợt giao (1, 2, 3)"], 3),
            "product_name": F(["Tên hàng hóa", "Tên hàng"], ["tên hàng"], 0.5),
            "unit": F(["Đơn vị tính", "ĐV gốc"], ["đơn vị tính", "đơn vị cơ bản"], 0.3),
            "qty_base": F(["Số lượng giao", "SL thực giao"], ["số lượng đã đổi ra đơn vị cơ bản"], 1),
            "vehicle": F(["Biển số xe"], ["biển số xe"], 1),
            "driver": F(["Người giao hàng", "Người chở"], ["tài xế"], 1),
        },
        "need": [["trip_no"], ["order_id"], ["delivery_date"]],
    },
    "debt_terms": {
        "fields": {
            "order_id": F(["Mã đơn hàng", "So hoa don", "Mã hóa đơn"], ["mã đơn"], 1),
            "days_allowed": F(["Số ngày được nợ", "Hạn nợ (ngày)"], ["số ngày được nợ"], 3),
            "due_date": F(["Hạn thanh toán", "Han tra"], ["hạn thanh toán"], 2),
        },
        "need": [["order_id"], ["days_allowed", "due_date"]],
    },
    "expenses": {
        "fields": {
            "expense_date": F(["Ngày chi", "Ngày"], [], 2),
            "category": F(["Mục", "Khoản chi", "Loại chi"], [], 2),
            "amount": F(["So tien", "Số tiền", "Tiền"], [], 2),
            "note": F(["Ghi chú"], [], 0.3),
        },
        "need": [["expense_date"], ["amount"], ["category"]],
    },
    "dining": {
        "fields": {
            "order_id": F(["Mã hóa đơn", "Mã đơn hàng"], ["mã đơn"], 1),
            "table_id": F(["Phòng/Bàn", "Bàn"], ["bàn"], 3),
            "area": F(["Khu vực"], ["khu vực của bàn"], 1),
            "guests": F(["Số khách"], ["số khách của đơn"], 1),
        },
        "need": [["order_id"], ["table_id"]],
    },
    "drugs": {
        "fields": {
            "product_id": F(["Mã hàng", "Mã SKU", "Mã HH", "MaHangHoa"], ["mã hàng"], 1),
            "ingredient": F(["Hoạt chất", "ThanhPhanChinh"], ["hoạt chất (trống với thực phẩm chức năng, vật tư)"], 3),
            "is_rx": F(["Thuốc kê đơn", "Kê đơn", "BanTheoDon"], ["thuốc kê đơn"], 3),
        },
        "need": [["product_id"], ["ingredient", "is_rx"]],
    },
    "returns": {
        "fields": {
            "return_id": F(["MaPhieuTra", "Mã phiếu trả"], [], 3),
            "order_id": F(["MaHoaDon", "Mã hóa đơn"], ["mã đơn"], 1),
            "return_ts": F(["NgayGioTra", "Thời gian trả"], [], 1),
            "reason": F(["NguyenNhan", "Lý do"], [], 0.5),
            "refund": F(["TienHoanTra", "Tiền hoàn trả"], [], 1),
            "refund_method": F(["CachHoanTien"], [], 0.3),
        },
        "need": [["return_id"], ["order_id"]],
    },
    "staff": {
        "fields": {
            "staff_id": F(["MaNhanVien", "Mã nhân viên", "Mã NV"], [], 3),
            "staff_name": F(["TenGoi", "Tên nhân viên", "Họ tên"], [], 1),
            "role": F(["ChucVu", "Chức vụ"], [], 1),
            "branch_id": F(["MaChiNhanh"], [], 0.3),
            "start_date": F(["NgayNhanViec"], [], 0.5),
            "end_date": F(["NgayThoiViec"], [], 0.5),
        },
        "need": [["staff_id"], ["staff_name"]],
    },
    "suppliers": {
        "fields": {
            "supplier_id": F(["MaNhaCungCap", "Mã NCC", "Mã nhà cung cấp"], [], 3),
            "supplier_name": F(["TenGoi", "Tên nhà cung cấp", "Nhà cung cấp"], [], 1),
            "phone": F(["SoDienThoai", "Điện thoại"], [], 0.3),
            "address": F(["DiaChiLienHe", "Địa chỉ"], [], 0.3),
        },
        "need": [["supplier_id"], ["supplier_name"]],
    },
    "branches": {
        "fields": {
            "branch_id": F(["MaChiNhanh", "Mã chi nhánh"], [], 3),
            "branch_name": F(["TenGoi", "Tên chi nhánh"], [], 1),
            "address": F(["DiaChiLienHe", "Địa chỉ"], [], 0.3),
            "opened": F(["NgayKhaiTruong"], [], 0.5),
        },
        "need": [["branch_id"], ["branch_name"]],
    },
}

# columns that never carry meaning for the model
IGNORE_HEADERS = {norm_header(x) for x in ["IDCuaHang", "Hình ảnh (url1,url2...)", "Hình ảnh", "hinh_anh", "Mẫu ghi chú",
                                          "mau_ghi_chu", "Mã HH Liên quan", "Bảo hành", "bao_hanh", "Trọng lượng", "Vị trí",
                                          "Vị trí kệ", "vi_tri", "Thuộc tính", "Mô tả sản phẩm", "Mô tả chi tiết", "mo_ta",
                                          "Mã barcode", "Mã vạch EAN", "ma_vach_ean", "Email", "E-mail", "CCCD", "cccd",
                                          "Số CMND/CCCD", "MST", "Mã số thuế", "Người tạo", "nguoi_tao", "Tổng điểm",
                                          "tong_diem", "Điểm tích lũy", "Điểm hiện tại", "diem_hien_tai", "Tên công ty",
                                          "Công ty", "cong_ty", "Thương hiệu", "thuong_hieu", "Định mức tồn tối thiểu",
                                          "Định mức tồn tối đa", "Tồn lớn nhất", "Tồn nhỏ nhất", "ton_lon_nhat",
                                          "ton_nho_nhat", "Được bán trực tiếp", "ban_truc_tiep", "Đang kinh doanh",
                                          "ConKinhDoanh", "Ghi chú KH", "ghi_chu_kh", "ghi_chu_hh", "SoHoaDonDienTu",
                                          "Trạng thái HĐĐT", "TinhTrangHDDT", "trang_thai_kh", "TaoLuc"]}
IGNORE_DESCRIPTIONS = {norm_header("cột trống, không có dữ liệu")}
