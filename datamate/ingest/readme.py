"""Facts extracted from a shop README (plan/thiet_ke/02 §A4).

The README format seen in train:
  ## Cột trong `file.xlsx`[, sheet `Sheet`]      then  - **Column**: description
  ## Quy ước                                     then  - Dữ liệu có đến hết dd/mm/yyyy.
                                                       - **Topic**: text   (may be followed by an indented list)
Quality varies (some READMEs have no column sections), so every field here is optional.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from .parsers import fix_mojibake, parse_date, parse_number

_SECTION = re.compile(r"^#{2,}\s*Cột trong\s+`([^`]+)`(?:\s*,\s*sheet\s+`([^`]+)`)?", re.I)
_COL = re.compile(r"^\s*-\s+\*\*(.+?)\*\*\s*:\s*(.+?)\s*$")
_END = re.compile(r"Dữ liệu có đến hết\s+(\d{1,2}/\d{1,2}/\d{4})")
_CONV = re.compile(r"^\s+-\s+(.+?):\s*1\s+(.+?)\s*=\s*([\d.,]+)\s+(.+?)\s*$")
_TOPIC = re.compile(r"^-\s+\*\*(.+?)\*\*\s*:\s*(.+)$")


@dataclass
class ReadmeFacts:
    columns: dict[tuple[str, str | None], dict[str, str]] = field(default_factory=dict)  # (file, sheet) -> col -> desc
    data_end: dt.date | None = None
    conversions: list[tuple[str, str, float, str]] = field(default_factory=list)       # (product, big_unit, factor, base_unit)
    conventions: dict[str, str] = field(default_factory=dict)                          # topic -> text
    summary: str = ""                                                                  # first paragraph

    def column_desc(self, file: str, sheet: str | None, column: str) -> str | None:
        for key in ((file, sheet), (file, None)):
            d = self.columns.get(key, {}).get(column)
            if d:
                return d
        return None


def parse_readme(text: str) -> ReadmeFacts:
    facts = ReadmeFacts()
    if not text:
        return facts
    lines = text.splitlines()
    paras = [ln.strip() for ln in lines[1:] if ln.strip()]
    facts.summary = paras[0] if paras and not paras[0].startswith("#") else ""
    section: tuple[str, str | None] | None = None
    in_conventions = False
    last_topic = None
    for ln in lines:
        m = _SECTION.match(ln)
        if m:
            section = (fix_mojibake(m.group(1)), m.group(2))
            facts.columns.setdefault(section, {})
            in_conventions = False
            continue
        if ln.startswith("#"):
            section = None
            in_conventions = "quy ước" in ln.lower()
            continue
        if section:
            m = _COL.match(ln)
            if m:
                facts.columns[section][m.group(1).strip()] = m.group(2).strip()
            continue
        if in_conventions:
            m = _END.search(ln)
            if m:
                facts.data_end = parse_date(m.group(1))
                continue
            m = _CONV.match(ln)
            if m and last_topic and "quy đổi" in last_topic.lower():
                factor = parse_number(m.group(3))
                if factor:
                    facts.conversions.append((m.group(1).strip(), m.group(2).strip(), factor, m.group(4).strip()))
                continue
            m = _TOPIC.match(ln.strip())
            if m:
                last_topic = m.group(1).strip()
                facts.conventions[last_topic] = m.group(2).strip()
    return facts
