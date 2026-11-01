import datetime as dt

from datamate.ingest.detect import detect_table, merge_tables
from datamate.ingest.readers import RawSheet

HEADER = ["Ngày", "Mã đơn hàng", "Tên hàng hóa", "Số lượng", "Thành tiền", "Trạng thái"]
ROW = ["01/04/2025", "ORD000001", "Cà phê đen (M)", "1 ly", "25,000.0000", "xong"]


def sheet(rows, name="Sheet1", file="f.xlsx"):
    return RawSheet(file, name, [list(r) for r in rows])


def test_title_and_filter_rows_are_skipped():
    rows = [["SỔ CHI TIẾT BÁN HÀNG"] + [None] * 5,
            ["Kỳ báo cáo: toàn bộ", "Kênh bán: Tất cả"] + [None] * 4,
            [None] * 6, HEADER, ROW, ROW]
    t = detect_table(sheet(rows))
    assert t.header == HEADER and t.header_row == 3 and len(t.rows) == 2


def test_two_tier_header():
    rows = [["Hàng", None, "Tiền", None, "Đơn", None], HEADER, ROW]
    t = detect_table(sheet(rows))
    assert t.header == HEADER
    assert t.group_header == ["Hàng", "Hàng", "Tiền", "Tiền", "Đơn", "Đơn"]


def test_summary_and_note_rows_dropped_anywhere():
    rows = [HEADER, ROW, [None, None, "TỔNG THÁNG 7", None, "98,824,600", None], ROW,
            ["Ghi chú: tiền tính bằng đồng"] + [None] * 5, [None, None, "Tổng tháng 8/2026", None, "1,285,034,400", None]]
    t = detect_table(sheet(rows))
    assert len(t.rows) == 2


def test_dense_daily_subtotal_dropped():
    header = ["Tien hang", "TongTien", "Mã bill", "Bên mua", "Ngày giao dịch", "Status", "Da tra", "Chưa trả"]
    rows = [header, ["32,000", "32,000", "ORD000084", "Ngô Mai Duy", "01/05/2025", "Hoàn thành", "32,000", "0"],
            ["5,726,000", "5,786,000", None, "Cộng ngày 01/05/2025", None, None, "5,786,000", "0"]]
    assert len(detect_table(sheet(rows)).rows) == 1


def test_product_named_like_total_is_kept():
    row = ["01/04/2025", "ORD000002", "Tổng hợp hạt dinh dưỡng", "1", "50,000", "xong"]
    assert len(detect_table(sheet([HEADER, row])).rows) == 1


def test_surname_tong_and_product_cong_tac_are_kept():
    rows = [HEADER, ["01/04/2025", "ORD3", "Công tắc 1 chiều Panasonic", "1", "35,000", "xong"],
            ["KH0001", "Tống Nam Quang"] + [None] * 4]   # sparse customer-like row
    assert len(detect_table(sheet(rows)).rows) == 2


def test_monthly_sheets_merge_with_period_and_reordered_columns():
    a = detect_table(sheet([HEADER, ROW], "T01_2025", "So_1.xlsx"))
    b = detect_table(sheet([HEADER[::-1], ROW[::-1]], "T02_2025", "So_2026.xlsx"))
    other = detect_table(sheet([["Mã hàng", "Tên hàng"], ["SP0001", "X"]], "Sheet1", "DanhMuc.xlsx"))
    merged = merge_tables([a, b, other])
    big = next(t for t in merged if t.n_rows == 2)
    assert big.rows[1] == ROW                       # aligned to the first header order
    assert big.source_period == [(2025, 1), (2025, 2)]
    assert len(merged) == 2


def test_datetime_cells_are_not_headers():
    rows = [[dt.datetime(2025, 1, 1), "ORD1", "X", 1, 100, "ok"]] * 3
    t = detect_table(sheet([HEADER] + rows))
    assert t.header == HEADER and len(t.rows) == 3
