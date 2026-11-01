"""Lunar calendar lookup from the released `calendar.csv` (rulebook §2: Tết is read from this file, not computed).

Columns: date, weekday, lunar_day, lunar_month, lunar_year, lunar_leap, holiday.
"""
from __future__ import annotations

import csv
import datetime as dt
from functools import lru_cache
from pathlib import Path


class Calendar:
    def __init__(self, rows: list[dict]):
        self.solar: dict[dt.date, tuple[int, int, int, bool]] = {}
        self.lunar: dict[tuple[int, int, int, bool], dt.date] = {}
        self.holiday: dict[dt.date, str] = {}
        for r in rows:
            d = dt.date.fromisoformat(r["date"].strip())
            key = (int(r["lunar_year"]), int(r["lunar_month"]), int(r["lunar_day"]),
                   str(r.get("lunar_leap", "")).strip().lower() in ("true", "1", "yes"))
            self.solar[d] = key
            self.lunar.setdefault(key, d)
            if (r.get("holiday") or "").strip():
                self.holiday[d] = r["holiday"].strip()
        self.first = min(self.solar) if self.solar else None
        self.last = max(self.solar) if self.solar else None

    @classmethod
    def load(cls, path: str | Path) -> "Calendar":
        with open(path, encoding="utf-8-sig", newline="") as f:
            return cls(list(csv.DictReader(f)))

    def to_solar(self, lunar_year: int, month: int, day: int, leap: bool = False) -> dt.date | None:
        return self.lunar.get((lunar_year, month, day, leap))

    def to_lunar(self, d: dt.date) -> tuple[int, int, int, bool] | None:
        return self.solar.get(d)

    def tet_range(self, year: int) -> tuple[dt.date, dt.date] | None:
        """Tết of lunar year `year`: 23 tháng Chạp of year−1 .. mùng 10 tháng Giêng of year (both inclusive)."""
        a = self.to_solar(year - 1, 12, 23)
        b = self.to_solar(year, 1, 10)
        return (a, b) if a and b else None


@lru_cache(maxsize=4)
def load_calendar(path: str) -> Calendar:
    return Calendar.load(path)


def find_calendar(data_root: str | Path) -> Path | None:
    """calendar.csv sits next to questions.jsonl; fall back to any copy inside the data tree."""
    root = Path(data_root)
    p = root / "calendar.csv"
    if p.exists():
        return p
    hits = sorted(root.rglob("calendar.csv"))
    return hits[0] if hits else None
