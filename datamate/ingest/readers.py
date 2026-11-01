"""A1 — read every data file of a business into raw sheets (design: plan/thiet_ke/02 §A1).

Cells are kept as read (str / float / datetime / None) so that parsers decide types per column later.
"""
from __future__ import annotations

import csv
import io
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from python_calamine import CalamineWorkbook

from .parsers import fix_mojibake

CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp1258", "latin-1")


@dataclass
class RawSheet:
    file: str                 # display file name (mojibake fixed)
    sheet: str | None         # sheet / table name; None for csv
    rows: list[list] = field(repr=False)
    kind: str = "xlsx"        # csv | xlsx | sqlite

    @property
    def source(self) -> str:
        return f"{self.file}#{self.sheet}" if self.sheet else self.file


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _trim(rows: list[list]) -> list[list]:
    """Drop trailing blank rows and trailing all-blank columns."""
    while rows and all(_blank(v) for v in rows[-1]):
        rows.pop()
    width = max((max((i + 1 for i, v in enumerate(r) if not _blank(v)), default=0) for r in rows), default=0)
    return [list(r[:width]) + [None] * (width - len(r)) for r in rows]


def read_csv(path: Path) -> RawSheet:
    raw = path.read_bytes()
    for enc in CSV_ENCODINGS:
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:20000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [[None if c == "" else c for c in r] for r in csv.reader(io.StringIO(text), dialect)]
    return RawSheet(fix_mojibake(path.name), None, _trim(rows), "csv")


def read_xlsx(path: Path) -> list[RawSheet]:
    wb = CalamineWorkbook.from_path(str(path))
    out = []
    for name in wb.sheet_names:
        rows = [[None if (isinstance(c, str) and c == "") else c for c in r]
                for r in wb.get_sheet_by_name(name).to_python()]
        rows = _trim(rows)
        if rows:
            out.append(RawSheet(fix_mojibake(path.name), name, rows, "xlsx"))
    return out


def read_sqlite(path: Path) -> list[RawSheet]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        out = []
        tables = [r[0] for r in con.execute("select name from sqlite_master where type in ('table','view') order by name")]
        for t in tables:
            cur = con.execute(f'select * from "{t}"')
            header = [d[0] for d in cur.description]
            rows = [header] + [list(r) for r in cur.fetchall()]
            out.append(RawSheet(fix_mojibake(path.name), t, rows, "sqlite"))
        return out
    finally:
        con.close()


def read_business(biz_dir: Path) -> tuple[list[RawSheet], str]:
    """All sheets of one business + README text ('' when missing)."""
    sheets: list[RawSheet] = []
    readme = ""
    for p in sorted(Path(biz_dir).iterdir()):
        suffix = p.suffix.lower()
        if p.name.lower() == "readme.md":
            readme = p.read_text(encoding="utf-8", errors="replace")
        elif suffix == ".csv":
            sheets.append(read_csv(p))
        elif suffix in (".xlsx", ".xlsm", ".xls"):
            sheets.extend(read_xlsx(p))
        elif suffix in (".sqlite", ".sqlite3", ".db"):
            sheets.extend(read_sqlite(p))
    return sheets, readme
