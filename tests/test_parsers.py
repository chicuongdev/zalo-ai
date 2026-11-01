import datetime as dt

import pytest

from datamate.ingest.parsers import (fix_mojibake, is_code, parse_bool, parse_date, parse_datetime, parse_money,
                                     parse_qty_unit, parse_sheet_period)

# values seen in the train data (plan/eda_findings.md §3)
MONEY = [
    ("38,000", 38000), ("55.000đ", 55000), ("25,000.0000", 25000), ("1tr440", 1_440_000),
    ("9tr960", 9_960_000), ("16,56tr", 16_560_000), ("1,84tr", 1_840_000), ("-53.500đ", -53500),
    ("1250k", 1_250_000), ("1tr5", 1_500_000), ("2tr", 2_000_000), ("1.5tr", 1_500_000),
    ("131,789,600", 131_789_600), ("6,719.0000", 6719), ("0", 0), (99000, 99000), (2131200, 2131200),
    ("9.600.000 đồng", 9_600_000), ("720.000đ", 720000), ("18.6", 18.6),
    ("332,5972tr", 332_597_200), ("409tr663", 409_663_000), ("280.183.667đ", 280_183_667), ("26078k", 26_078_000),
]


@pytest.mark.parametrize("raw,expected", MONEY)
def test_money(raw, expected):
    assert parse_money(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", [None, "", "abc", "đ", True])
def test_money_invalid(raw):
    assert parse_money(raw) is None


@pytest.mark.parametrize("raw,expected", [
    ("2 thùng", (2.0, "thùng")), ("1 hộp", (1.0, "hộp")), (3, (3.0, None)), ("1,5 kg", (1.5, "kg")), ("-1", (-1.0, None)),
])
def test_qty_unit(raw, expected):
    assert parse_qty_unit(raw) == expected


@pytest.mark.parametrize("raw,year,expected", [
    ("01/02/2025", None, dt.date(2025, 2, 1)),
    (45717, None, dt.date(2025, 3, 1)),
    (45658, None, dt.date(2025, 1, 1)),
    ("45658", None, dt.date(2025, 1, 1)),
    ("1 thg 1 2025", None, dt.date(2025, 1, 1)),
    ("2 thg 1 2025", None, dt.date(2025, 1, 2)),
    ("1/1", 2025, dt.date(2025, 1, 1)),
    ("31/01/2025", None, dt.date(2025, 1, 31)),
    ("2026-08-15", None, dt.date(2026, 8, 15)),
    (dt.datetime(2025, 2, 1, 6, 0, 25), None, dt.date(2025, 2, 1)),
    ("1/1", None, None),
    ("32/01/2025", None, None),
])
def test_date(raw, year, expected):
    assert parse_date(raw, year) == expected


def test_datetime_keeps_time():
    assert parse_datetime("01/02/2025 14:05") == dt.datetime(2025, 2, 1, 14, 5)


@pytest.mark.parametrize("name,expected", [
    ("T01_2025", (2025, 1)), ("04.2025", (2025, 4)), ("Thang 02 2025", (2025, 2)), ("Tháng 01-2025", (2025, 1)),
    ("T02-2026", (2026, 2)), ("Sheet1", None), ("DanhSachHoaDon", None),
])
def test_sheet_period(name, expected):
    assert parse_sheet_period(name) == expected


@pytest.mark.parametrize("raw,expected", [(True, True), ("TRUE", True), (1, True), ("False", False), (0, False), ("?", None)])
def test_bool(raw, expected):
    assert parse_bool(raw) is expected


def test_code():
    assert is_code("SP0001") and is_code("ORD000001") and is_code("KH0098") and is_code("PN00001")
    assert not is_code("Coca Cola 330ml") and not is_code("123")


def test_mojibake():
    assert fix_mojibake("Danh s├ích h├áng h├│a.xlsx") == "Danh sách hàng hóa.xlsx"
    assert fix_mojibake("SoBanHang.xlsx") == "SoBanHang.xlsx"
