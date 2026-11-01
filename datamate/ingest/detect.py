"""A2 — find the real header of each raw sheet and merge same-shaped sheets (design: plan/thiet_ke/02 §A2).

Handles title rows ("SỔ CHI TIẾT BÁN HÀNG"), filter lines ("Kỳ báo cáo: toàn bộ"), two-tier headers
(group row "Hàng | Tiền | Đơn" above the real header), footer total rows, and monthly sheets.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .parsers import parse_sheet_period, strip_accents
from .readers import RawSheet, _blank

HEADER_SCAN_ROWS = 15
# summary / note rows: "Tổng cộng", "TỔNG THÁNG 7", "Tổng tháng 8/2026", "Cộng ngày 01/05/2025", "Ghi chú: số liệu ghi tay"
# matched WITH diacritics: 'tổng/cộng' are labels, 'Tống' (surname) and 'Công tắc' (product) are data
STRONG_SUMMARY = re.compile(r"^(tổng|cộng)\s+(cộng|ngày|tháng|kỳ|kì|số|quý|năm)\b")  # dropped even when the row is dense
SUMMARY_ROW = re.compile(r"^((tổng|cộng|total|subtotal)\b|ghi chú\s*:)")             # dropped only in sparse rows


@dataclass
class Table:
    """One detected table inside one raw sheet."""
    source: str
    file: str
    sheet: str | None
    header: list[str]
    group_header: list[str | None]          # two-tier header label per column, or None
    rows: list[list] = field(repr=False)
    header_row: int = 0


@dataclass
class LogicalTable:
    """Same-shaped tables merged (monthly sheets, split files). Rows aligned to `header`."""
    name: str
    header: list[str]
    group_header: list[str | None]
    sources: list[str]
    rows: list[list] = field(repr=False)
    row_source: list[int] = field(repr=False)             # index into sources, per row
    source_period: list[tuple[int, int] | None] = field(default_factory=list)  # (year, month) per source

    @property
    def n_rows(self) -> int:
        return len(self.rows)


def _is_header_cell(v) -> bool:
    return isinstance(v, str) and 0 < len(v.strip()) <= 60 and not v.strip().replace(".", "").replace(",", "").isdigit()


def _row_width(r) -> int:
    return sum(not _blank(v) for v in r)


def find_header_row(rows: list[list]) -> int:
    """Index of the header row: wide, all-text, followed by rows of similar width."""
    width = max((len(r) for r in rows), default=0)
    best, best_score = 0, -1.0
    for i, r in enumerate(rows[:HEADER_SCAN_ROWS]):
        w = _row_width(r)
        if w < max(2, 0.6 * width):
            continue
        if not all(_is_header_cell(v) for v in r if not _blank(v)):
            continue
        below = [_row_width(x) for x in rows[i + 1:i + 6]]
        support = sum(b >= 0.5 * w for b in below) / max(len(below), 1)
        # prefer earlier rows when tied (a data row is never all-text and as wide as a header)
        score = w / width + support - 0.01 * i
        if score > best_score:
            best, best_score = i, score
    return best


def _group_header(rows: list[list], h: int, width: int) -> list[str | None]:
    """Two-tier header: sparse text row right above the header, forward-filled across columns."""
    if h == 0:
        return [None] * width
    prev = rows[h - 1]
    if _row_width(prev) < 2 or not all(_is_header_cell(v) for v in prev if not _blank(v)):
        return [None] * width
    out, cur = [], None
    for j in range(width):
        v = prev[j] if j < len(prev) else None
        if not _blank(v):
            cur = str(v).strip()
        out.append(cur)
    return out


def is_summary_row(r, width: int) -> bool:
    """Row whose text is a total / note label ('Cộng ngày …' subtotals can be as dense as data rows)."""
    labels = [unicodedata.normalize("NFC", v).lower().strip() for v in r if isinstance(v, str)]
    if any(STRONG_SUMMARY.match(s) for s in labels):
        return True
    if _row_width(r) > max(1, width // 2):
        return False
    return any(SUMMARY_ROW.match(s) for s in labels)


def _unique(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for n in names:
        k = n
        if k in seen:
            seen[k] += 1
            k = f"{n}__{seen[n]}"
        else:
            seen[k] = 0
        out.append(k)
    return out


def detect_table(raw: RawSheet) -> Table | None:
    rows = raw.rows
    if not rows:
        return None
    if raw.kind == "sqlite":
        return Table(raw.source, raw.file, raw.sheet, [str(c) for c in rows[0]], [None] * len(rows[0]), rows[1:], 0)
    h = find_header_row(rows)
    width = len(rows[h])
    header = _unique([str(v).strip() if not _blank(v) else f"_col{j}" for j, v in enumerate(rows[h])])
    data = [r for r in rows[h + 1:] if _row_width(r) > 0 and not is_summary_row(r, width)]
    return Table(raw.source, raw.file, raw.sheet, header, _group_header(rows, h, width), data, h)


def _family(file: str) -> str:
    """'SoBanHang_1.xlsx', 'SoBanHang_2026.xlsx', 'DanhSachHoaDonChiTiet_2.xlsx' -> 'sobanhang' / ... ."""
    stem = strip_accents(file.rsplit(".", 1)[0]).lower()
    parts = stem.replace("-", "_").split("_")
    while len(parts) > 1 and parts[-1].isdigit():
        parts.pop()
    return "_".join(parts)


def merge_tables(tables: list[Table]) -> list[LogicalTable]:
    """Merge tables with the same header set coming from the same file family (or the same file)."""
    groups: dict[tuple, list[Table]] = {}
    for t in tables:
        key = (frozenset(t.header), _family(t.file) if t.sheet is None or _is_period_sheet(t.sheet) else f"{t.file}#{t.sheet}")
        groups.setdefault(key, []).append(t)
    out = []
    for (_, fam), ts in groups.items():
        first = ts[0]
        lt = LogicalTable(name=_logical_name(first, len(ts) > 1, fam), header=first.header,
                          group_header=first.group_header, sources=[], rows=[], row_source=[])
        for t in ts:
            idx = [t.header.index(c) for c in first.header]
            k = len(lt.sources)
            lt.sources.append(t.source)
            lt.source_period.append(parse_sheet_period(t.sheet) if t.sheet else None)
            for r in t.rows:
                lt.rows.append([r[i] if i < len(r) else None for i in idx])
                lt.row_source.append(k)
        out.append(lt)
    return out


def _is_period_sheet(sheet: str) -> bool:
    return parse_sheet_period(sheet) is not None or sheet.lower().startswith("sheet")


def _logical_name(t: Table, merged: bool, fam: str) -> str:
    if t.sheet and not _is_period_sheet(t.sheet):
        return t.sheet                      # named sheet inside a multi-list workbook, or sqlite table
    return fam


def detect_business(sheets: list[RawSheet]) -> list[LogicalTable]:
    tables = [t for t in (detect_table(s) for s in sheets) if t is not None and t.rows]
    return merge_tables(tables)


def source_year(lt: LogicalTable, row: int, fallback: int | None = None) -> int | None:
    """Year of the sheet holding a row (rulebook §8: dates without a year take the sheet's year)."""
    p = lt.source_period[lt.row_source[row]] if lt.source_period else None
    return p[0] if p else fallback

