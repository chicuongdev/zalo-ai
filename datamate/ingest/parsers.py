"""Value parsers for messy Vietnamese shop data (design: plan/thiet_ke/02 §A3).

Every parser returns None when the value cannot be parsed, never raises.
"""
from __future__ import annotations

import datetime as dt
import math
import re
import unicodedata

EXCEL_EPOCH = dt.date(1899, 12, 30)
EXCEL_SERIAL_RANGE = (20000, 80000)  # 1954 .. 2119


def _clean(v) -> str:
    return unicodedata.normalize("NFC", str(v)).strip()


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s).replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# ---------------------------------------------------------------- numbers

_CURRENCY = re.compile(r"(vnđ|vnd|đồng|dong|đ|₫|d)$", re.I)


def parse_plain_number(s: str):
    """'38,000' '55.000' '25,000.0000' '18.6' '0,9' '-53.500' -> float."""
    s = s.replace(" ", "").replace(" ", "")
    if not s:
        return None
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = s.strip("-+()")
    if not re.fullmatch(r"[\d.,]+", s) or not re.search(r"\d", s):
        return None
    has_dot, has_comma = "." in s, "," in s
    if has_dot and has_comma:
        dec = "." if s.rfind(".") > s.rfind(",") else ","
        thou = "," if dec == "." else "."
        s = s.replace(thou, "").replace(dec, ".")
    elif has_dot or has_comma:
        sep = "." if has_dot else ","
        parts = s.split(sep)
        # thousands separator: repeated, or a single one followed by exactly 3 digits
        if len(parts) > 2 or (len(parts[-1]) == 3 and parts[0] not in ("", "0")):
            if not all(len(p) == 3 for p in parts[1:]):
                return None
            s = "".join(parts)
        else:
            s = s.replace(sep, ".")
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


def parse_money(v):
    """VND amount -> float (caller rounds). Handles '1tr440', '16,56tr', '9tr960', '1250k', '55.000đ'."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return None if isinstance(v, float) and math.isnan(v) else float(v)
    s = _clean(v).lower().replace(" ", "")
    if not s:
        return None
    s = _CURRENCY.sub("", s)
    neg = s.startswith("-")
    s = s.lstrip("-+")
    # '1tr440' = 1 triệu 440 nghìn; '1tr5' = 1 triệu 500 nghìn
    m = re.fullmatch(r"(\d+)(?:tr|triệu|trieu)(\d{1,3})", s)
    if m:
        x = int(m.group(1)) * 1_000_000 + int(m.group(2).ljust(3, "0")) * 1000
        return float(-x if neg else x)
    for suffix, mult in (("triệu", 1e6), ("trieu", 1e6), ("tr", 1e6), ("nghìn", 1e3), ("ngàn", 1e3), ("ngan", 1e3), ("k", 1e3)):
        if s.endswith(suffix):
            base = parse_plain_number(s[: -len(suffix)])
            if base is None:
                return None
            # before 'tr' a single separator is a decimal mark: '16,56tr', '1.5tr', '332,5972tr'
            if mult >= 1e6 and re.fullmatch(r"\d+[.,]\d+", s[: -len(suffix)]):
                base = float(s[: -len(suffix)].replace(",", "."))
            x = round(base * mult, 6)
            return -x if neg else x
    x = parse_plain_number(s)
    if x is None:
        return None
    return -x if neg else x


def parse_number(v):
    """Generic numeric cell (quantities, factors)."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return None if isinstance(v, float) and math.isnan(v) else float(v)
    return parse_plain_number(_clean(v))


_QTY_UNIT = re.compile(r"^(-?\d+(?:[.,]\d+)?)\s*([^\d\s].*)?$")


def parse_qty_unit(v):
    """'2 thùng' -> (2.0, 'thùng'); 3 -> (3.0, None); '1,5 kg' -> (1.5, 'kg')."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return None if isinstance(v, float) and math.isnan(v) else (float(v), None)
    m = _QTY_UNIT.match(_clean(v))
    if not m:
        return None
    unit = m.group(2).strip() if m.group(2) else None
    return float(m.group(1).replace(",", ".")), unit


# ---------------------------------------------------------------- dates

_DMY = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$")
_YMD = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?")
_DM = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})$")
_THG = re.compile(r"^(\d{1,2})\s*thg\s*(\d{1,2})(?:[,\s]+(\d{4}))?$", re.I)  # '1 thg 1 2025'
_TEXT = re.compile(r"ngày\s*(\d{1,2})\s*tháng\s*(\d{1,2})(?:\s*năm\s*(\d{4}))?", re.I)


def _mk_date(y, m, d):
    try:
        y = int(y)
        if y < 100:
            y += 2000
        return dt.date(y, int(m), int(d))
    except ValueError:
        return None


def parse_datetime(v, default_year: int | None = None):
    """Any date-ish cell -> datetime (time 00:00 when unknown). Day-first for slash dates.

    default_year: year of the sheet, for rows that omit it (rulebook §8: 'Ngày không ghi năm').
    """
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, dt.datetime):
        return v
    if isinstance(v, dt.date):
        return dt.datetime(v.year, v.month, v.day)
    if isinstance(v, (int, float)):
        if isinstance(v, float) and math.isnan(v):
            return None
        if EXCEL_SERIAL_RANGE[0] <= v <= EXCEL_SERIAL_RANGE[1]:
            return dt.datetime.combine(EXCEL_EPOCH, dt.time()) + dt.timedelta(days=float(v))
        return None
    s = _clean(v)
    if re.fullmatch(r"\d{5}(\.\d+)?", s):
        return parse_datetime(float(s))
    m = _DMY.match(s)
    if m:
        d = _mk_date(m.group(3), m.group(2), m.group(1))
        if d is None:
            return None
        hh, mm, ss = (int(x) if x else 0 for x in m.group(4, 5, 6))
        return dt.datetime(d.year, d.month, d.day, hh, mm, ss)
    m = _YMD.match(s)
    if m:
        d = _mk_date(m.group(1), m.group(2), m.group(3))
        if d is None:
            return None
        hh, mm, ss = (int(x) if x else 0 for x in m.group(4, 5, 6))
        return dt.datetime(d.year, d.month, d.day, hh, mm, ss)
    for rx in (_THG, _TEXT):
        m = rx.search(s)
        if m:
            year = m.group(3) or default_year
            d = _mk_date(year, m.group(2), m.group(1)) if year else None
            return dt.datetime(d.year, d.month, d.day) if d else None
    m = _DM.match(s)
    if m and default_year:
        d = _mk_date(default_year, m.group(2), m.group(1))
        return dt.datetime(d.year, d.month, d.day) if d else None
    return None


def parse_date(v, default_year: int | None = None):
    x = parse_datetime(v, default_year)
    return x.date() if x else None


_SHEET_PERIOD = [
    re.compile(r"(?:^|\D)(\d{1,2})[._\-\s/](\d{4})(?:\D|$)"),  # T01_2025, 04.2025, Tháng 01-2025, Thang 02 2025
    re.compile(r"(?:^|\D)(\d{4})[._\-\s/](\d{1,2})(?:\D|$)"),  # 2025-01
]


def parse_sheet_period(name: str):
    """Sheet name -> (year, month) or None. 'T01_2025', '04.2025', 'Thang 02 2025', 'T02-2026'."""
    if not name:
        return None
    s = strip_accents(_clean(name)).lower()
    m = _SHEET_PERIOD[0].search(s)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(2)), int(m.group(1))
    m = _SHEET_PERIOD[1].search(s)
    if m and 1 <= int(m.group(2)) <= 12:
        return int(m.group(1)), int(m.group(2))
    return None


# ---------------------------------------------------------------- misc

_TRUE = {"true", "1", "có", "co", "x", "yes", "y", "đúng", "dung"}
_FALSE = {"false", "0", "không", "khong", "no", "n", "sai", ""}


def parse_bool(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return None if isinstance(v, float) and math.isnan(v) else bool(v)
    s = _clean(v).lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    return None


_CODE = re.compile(r"^[A-Z]{1,5}\d{3,}$")


def is_code(v) -> bool:
    return isinstance(v, str) and bool(_CODE.match(v.strip()))


def fix_mojibake(name: str) -> str:
    """File names extracted from zips without the UTF-8 flag: 'Danh s├ích' -> 'Danh sách'."""
    try:
        fixed = name.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name
    return fixed
