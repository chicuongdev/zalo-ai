"""B4 — Period resolver (rulebook §2). The parser only labels a period expression; dates are computed here.

An expression is a dict with `kind` plus slots, e.g. {"kind": "month", "m": 8, "y": 2025},
{"kind": "last_n_days", "n": 30}, {"kind": "prev_period", "of": {...}}. See plan/thiet_ke/04 §B4.

`resolve()` returns closed date spans [start, end]. With the shop's data range it also clips each span to
[data_start, min(data_end, as_of)] and flags spans that lie entirely outside the data (rulebook §7).
"""
from __future__ import annotations

import calendar as _pycal
import datetime as dt
from dataclasses import dataclass, field

from ..calendar import Calendar

D = dt.date
ONE = dt.timedelta(days=1)


@dataclass(frozen=True)
class Span:
    start: D
    end: D

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def contains(self, d: D) -> bool:
        return self.start <= d <= self.end


@dataclass
class Resolved:
    kind: str
    spans: list[Span]
    state_at: bool = False                 # "đến hết ngày X": state at end of `end`, everything from data start
    clipped: list[Span | None] = field(default_factory=list)
    out_of_range: bool = False             # every span lies entirely outside the shop's data

    @property
    def span(self) -> Span:
        return self.spans[0]


class PeriodError(ValueError):
    pass


# ------------------------------------------------------------------ calendar helpers

def month_span(y: int, m: int) -> Span:
    return Span(D(y, m, 1), D(y, m, _pycal.monthrange(y, m)[1]))


def add_months(y: int, m: int, k: int) -> tuple[int, int]:
    i = y * 12 + (m - 1) + k
    return i // 12, i % 12 + 1


def quarter_span(y: int, q: int) -> Span:
    if not 1 <= q <= 4:
        raise PeriodError(f"bad quarter {q}")
    return Span(D(y, 3 * q - 2, 1), month_span(y, 3 * q).end)


def week_start(d: D) -> D:
    return d - dt.timedelta(days=d.weekday())        # Monday


def shift_year(d: D, k: int) -> D:
    try:
        return d.replace(year=d.year + k)
    except ValueError:                                # 29/02 -> 28/02
        return d.replace(year=d.year + k, day=28)


def _date(v) -> D:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, D):
        return v
    if isinstance(v, str):
        return D.fromisoformat(v[:10])
    raise PeriodError(f"bad date {v!r}")


def infer_year(as_of: D, m: int, d: int = 1) -> int:
    """Rulebook §2: a month/quarter/day without a year is this year's unless it starts after today."""
    try:
        start = D(as_of.year, m, d)
    except ValueError:
        start = D(as_of.year, m, 1)
    return as_of.year if start <= as_of else as_of.year - 1


# ------------------------------------------------------------------ base expressions

def _spans(e: dict, as_of: D, cal: Calendar | None) -> tuple[list[Span], bool]:
    k = e["kind"]
    if k == "today":
        return [Span(as_of, as_of)], False
    if k == "yesterday":
        return [Span(as_of - ONE, as_of - ONE)], False
    if k == "day":
        if "date" in e:
            d = _date(e["date"])
        else:
            y = e.get("y") or infer_year(as_of, int(e["m"]), int(e["d"]))
            d = D(int(y), int(e["m"]), int(e["d"]))
        return [Span(d, d)], False
    if k == "this_week":
        return [Span(week_start(as_of), as_of)], False
    if k == "last_week":
        s = week_start(as_of) - dt.timedelta(days=7)
        return [Span(s, s + dt.timedelta(days=6))], False
    if k == "week_of":
        s = week_start(_date(e["date"]))
        return [Span(s, s + dt.timedelta(days=6))], False
    if k == "this_month_to_date":
        return [Span(as_of.replace(day=1), as_of)], False
    if k in ("last_month", "prev_month_same_days"):
        y, m = add_months(as_of.year, as_of.month, -1)
        full = month_span(y, m)
        if k == "last_month":
            return [full], False
        return [Span(full.start, min(full.end, D(y, m, min(as_of.day, full.end.day))))], False
    if k == "month":
        m = int(e["m"])
        y = int(e["y"]) if e.get("y") else infer_year(as_of, m)
        return [month_span(y, m)], False
    if k == "this_quarter":
        q = (as_of.month - 1) // 3 + 1
        return [Span(quarter_span(as_of.year, q).start, as_of)], False
    if k == "last_quarter":
        q = (as_of.month - 1) // 3 + 1
        y, q = (as_of.year, q - 1) if q > 1 else (as_of.year - 1, 4)
        return [quarter_span(y, q)], False
    if k == "quarter":
        q = int(e["q"])
        y = int(e["y"]) if e.get("y") else infer_year(as_of, 3 * q - 2)
        return [quarter_span(y, q)], False
    if k == "year":
        y = int(e["y"])
        return [Span(D(y, 1, 1), D(y, 12, 31))], False
    if k == "last_year":
        y = as_of.year - 1
        return [Span(D(y, 1, 1), D(y, 12, 31))], False
    if k in ("ytd", "this_year"):
        return [Span(D(as_of.year, 1, 1), as_of)], False
    if k == "range":
        a, b = _date(e["from"]), _date(e["to"])
        if b < a:
            raise PeriodError(f"empty range {a}..{b}")
        return [Span(a, b)], False
    if k == "last_n_days":
        n = int(e["n"])
        return [Span(as_of - dt.timedelta(days=n - 1), as_of)], False
    if k == "n_days_from":
        d, n = _date(e["date"]), int(e["n"])
        return [Span(d, d + dt.timedelta(days=n - 1))], False
    if k == "n_days_before":
        d, n = _date(e["date"]), int(e["n"])
        return [Span(d - dt.timedelta(days=n), d - ONE)], False
    if k == "as_of_end_of":
        d = as_of if e.get("date") in (None, "today") else _date(e["date"])
        return [Span(D.min, d)], True
    if k in ("tet", "before_tet"):
        if cal is None:
            raise PeriodError("Tết needs calendar.csv")
        y = int(e.get("y") or as_of.year)
        r = cal.tet_range(y)
        if r is None:
            raise PeriodError(f"calendar has no Tết {y}")
        if k == "tet":
            return [Span(*r)], False
        n = int(e.get("n") or ((r[1] - r[0]).days + 1))    # "N ngày trước Tết", default same length as Tết
        return [Span(r[0] - dt.timedelta(days=n), r[0] - ONE)], False
    if k == "months_ending_at":
        m = int(e["m"])
        y = int(e["y"]) if e.get("y") else infer_year(as_of, m)
        cnt = int(e["count"])
        return [month_span(*add_months(y, m, i - cnt + 1)) for i in range(cnt)], False
    if k == "month_list":
        out = []
        for it in e["items"]:
            m = int(it["m"])
            out.append(month_span(int(it["y"]) if it.get("y") else infer_year(as_of, m), m))
        return out, False
    if k == "month_range":
        a, b = e["from"], e["to"]
        ya = int(a["y"]) if a.get("y") else infer_year(as_of, int(a["m"]))
        yb = int(b["y"]) if b.get("y") else infer_year(as_of, int(b["m"]))
        n = (yb * 12 + int(b["m"])) - (ya * 12 + int(a["m"])) + 1
        if n < 1:
            raise PeriodError("empty month range")
        return [month_span(*add_months(ya, int(a["m"]), i)) for i in range(n)], False
    if k == "months_of_year":
        y = int(e["y"])
        last = 12 if y < as_of.year else as_of.month
        return [month_span(y, m) for m in range(1, last + 1)], False
    if k == "prev_period":
        return _prev(e["of"], as_of, cal), False
    if k == "same_period_last_year":
        return _last_year(e["of"], as_of, cal), False
    raise PeriodError(f"unknown period kind {k!r}")


def _prev(base: dict, as_of: D, cal: Calendar | None) -> list[Span]:
    """The period right before `base` (rulebook §1: growth compares with the previous period)."""
    k = base["kind"]
    spans, _ = _spans(base, as_of, cal)
    s = spans[0]
    if k == "this_month_to_date":
        return _spans({"kind": "prev_month_same_days"}, as_of, cal)[0]
    if k in ("month", "last_month"):
        y, m = add_months(s.start.year, s.start.month, -1)
        return [month_span(y, m)]
    if k in ("quarter", "last_quarter"):
        y, m = add_months(s.start.year, s.start.month, -3)
        return [quarter_span(y, (m - 1) // 3 + 1)]
    if k == "this_quarter":
        y, m = add_months(s.start.year, s.start.month, -3)
        start = D(y, m, 1)
        return [Span(start, min(quarter_span(y, (m - 1) // 3 + 1).end, start + (s.end - s.start)))]
    if k in ("year", "last_year"):
        return [Span(D(s.start.year - 1, 1, 1), D(s.start.year - 1, 12, 31))]
    if k in ("ytd", "this_year"):
        return [Span(shift_year(s.start, -1), shift_year(s.end, -1))]
    if k in ("tet",):
        return _spans({**base, "kind": "before_tet"}, as_of, cal)[0]
    if k in ("last_week", "week_of"):
        return [Span(s.start - dt.timedelta(days=7), s.end - dt.timedelta(days=7))]
    if k == "this_week":
        return [Span(s.start - dt.timedelta(days=7), s.end - dt.timedelta(days=7))]
    # day, today, yesterday, last_n_days, range, n_days_*: same length right before
    n = s.days
    return [Span(s.start - dt.timedelta(days=n), s.start - ONE)]


def _last_year(base: dict, as_of: D, cal: Calendar | None) -> list[Span]:
    k = base["kind"]
    spans, _ = _spans(base, as_of, cal)
    if k in ("month", "last_month", "quarter", "last_quarter", "year", "last_year", "months_ending_at"):
        out = []
        for s in spans:
            a = shift_year(s.start, -1)
            out.append(Span(a, month_span(a.year, s.end.month).end if s.end == month_span(s.end.year, s.end.month).end
                            else shift_year(s.end, -1)))
        return out
    return [Span(shift_year(s.start, -1), shift_year(s.end, -1)) for s in spans]


# ------------------------------------------------------------------ public API

def resolve(expr: dict, as_of, cal: Calendar | None = None, data_start=None, data_end=None,
            clip_to_as_of: bool = True) -> Resolved:
    as_of = _date(as_of)
    spans, state = _spans(expr, as_of, cal)
    res = Resolved(expr["kind"], spans, state_at=state)
    if data_start is None and data_end is None:
        res.clipped = list(spans)
        return res
    lo = _date(data_start) if data_start else D.min
    hi = _date(data_end) if data_end else D.max
    if clip_to_as_of:
        hi = min(hi, as_of)
    for s in spans:
        if state:
            # state at end of day: nothing recorded yet if the day is before the data starts
            res.clipped.append(Span(lo, min(s.end, hi)) if s.end >= lo else None)
        else:
            a, b = max(s.start, lo), min(s.end, hi)
            res.clipped.append(Span(a, b) if a <= b else None)
    res.out_of_range = all(c is None for c in res.clipped)
    return res
