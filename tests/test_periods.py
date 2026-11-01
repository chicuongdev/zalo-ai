"""Rulebook §2 — one test per row of the time table, plus §7 clipping."""
import datetime as dt
from pathlib import Path

import pytest

from datamate.calendar import Calendar
from datamate.qa.periods import PeriodError, Span, infer_year, resolve

D = dt.date
CAL_PATH = Path("data/train/calendar.csv")


@pytest.fixture(scope="module")
def cal():
    if CAL_PATH.exists():
        return Calendar.load(CAL_PATH)
    # minimal stand-in: Tết 2026 (23 Chạp = 10/02/2026, mùng 10 = 26/02/2026)
    rows = [{"date": "2026-02-10", "lunar_year": 2025, "lunar_month": 12, "lunar_day": 23, "lunar_leap": "false"},
            {"date": "2026-02-26", "lunar_year": 2026, "lunar_month": 1, "lunar_day": 10, "lunar_leap": "false"}]
    return Calendar(rows)


def sp(expr, as_of, **kw):
    return resolve(expr, as_of, **kw).spans


def test_day_today_yesterday():
    assert sp({"kind": "today"}, "2026-08-19") == [Span(D(2026, 8, 19), D(2026, 8, 19))]
    assert sp({"kind": "yesterday"}, "2026-08-01") == [Span(D(2026, 7, 31), D(2026, 7, 31))]
    assert sp({"kind": "day", "date": "2025-03-05"}, "2026-01-01") == [Span(D(2025, 3, 5), D(2025, 3, 5))]


def test_day_without_year():
    # 05/03 not after today -> this year; 20/12 after today -> last year
    assert sp({"kind": "day", "m": 3, "d": 5}, "2026-08-19")[0].start == D(2026, 3, 5)
    assert sp({"kind": "day", "m": 12, "d": 20}, "2026-08-19")[0].start == D(2025, 12, 20)


def test_as_of_end_of_is_state_from_data_start():
    r = resolve({"kind": "as_of_end_of", "date": "2026-08-19"}, "2026-08-25", data_start="2025-01-01", data_end="2026-09-30")
    assert r.state_at
    assert r.clipped == [Span(D(2025, 1, 1), D(2026, 8, 19))]
    r = resolve({"kind": "as_of_end_of"}, "2026-08-25", data_start="2025-01-01", data_end="2026-09-30")
    assert r.clipped[0].end == D(2026, 8, 25)


def test_range_inclusive():
    assert sp({"kind": "range", "from": "2025-10-20", "to": "2025-10-26"}, "2026-01-01")[0].days == 7
    with pytest.raises(PeriodError):
        sp({"kind": "range", "from": "2025-10-27", "to": "2025-10-26"}, "2026-01-01")


def test_last_n_days_includes_today():
    s = sp({"kind": "last_n_days", "n": 30}, "2026-08-19")[0]
    assert s == Span(D(2026, 7, 21), D(2026, 8, 19)) and s.days == 30


def test_weeks_start_monday():
    # 2026-08-19 is a Wednesday
    assert sp({"kind": "this_week"}, "2026-08-19") == [Span(D(2026, 8, 17), D(2026, 8, 19))]
    assert sp({"kind": "last_week"}, "2026-08-19") == [Span(D(2026, 8, 10), D(2026, 8, 16))]
    # on a Monday this week is just today, last week is the full previous Mon–Sun
    assert sp({"kind": "this_week"}, "2026-08-17") == [Span(D(2026, 8, 17), D(2026, 8, 17))]
    assert sp({"kind": "last_week"}, "2026-08-23") == [Span(D(2026, 8, 10), D(2026, 8, 16))]   # Sunday


def test_month_full():
    assert sp({"kind": "month", "m": 2, "y": 2024}, "2026-01-01") == [Span(D(2024, 2, 1), D(2024, 2, 29))]
    assert sp({"kind": "month", "m": 4, "y": 2025}, "2026-01-01") == [Span(D(2025, 4, 1), D(2025, 4, 30))]


def test_this_month_and_prev_same_days():
    assert sp({"kind": "this_month_to_date"}, "2026-08-19") == [Span(D(2026, 8, 1), D(2026, 8, 19))]
    assert sp({"kind": "prev_month_same_days"}, "2026-08-19") == [Span(D(2026, 7, 1), D(2026, 7, 19))]
    # previous month has no such day -> to its end
    assert sp({"kind": "prev_month_same_days"}, "2026-03-31") == [Span(D(2026, 2, 1), D(2026, 2, 28))]
    assert sp({"kind": "prev_period", "of": {"kind": "this_month_to_date"}}, "2026-03-30") == \
        [Span(D(2026, 2, 1), D(2026, 2, 28))]


def test_ytd():
    assert sp({"kind": "ytd"}, "2026-08-19") == [Span(D(2026, 1, 1), D(2026, 8, 19))]


def test_month_quarter_without_year():
    assert infer_year(D(2026, 8, 19), 8) == 2026      # current month: not after today
    assert infer_year(D(2026, 8, 19), 9) == 2025
    assert sp({"kind": "month", "m": 10}, "2026-08-19")[0].start == D(2025, 10, 1)
    assert sp({"kind": "quarter", "q": 3}, "2026-08-19") == [Span(D(2026, 7, 1), D(2026, 9, 30))]
    assert sp({"kind": "quarter", "q": 4}, "2026-08-19") == [Span(D(2025, 10, 1), D(2025, 12, 31))]
    assert sp({"kind": "quarter", "q": 1, "y": 2026}, "2026-08-19") == [Span(D(2026, 1, 1), D(2026, 3, 31))]


def test_tet(cal):
    assert sp({"kind": "tet", "y": 2026}, "2026-08-19", cal=cal) == [Span(D(2026, 2, 10), D(2026, 2, 26))]
    # "so với trước Tết": same number of days right before 23 tháng Chạp
    before = sp({"kind": "before_tet", "y": 2026}, "2026-08-19", cal=cal)[0]
    assert before == Span(D(2026, 1, 24), D(2026, 2, 9)) and before.days == 17
    assert sp({"kind": "before_tet", "y": 2026, "n": 7}, "2026-08-19", cal=cal) == [Span(D(2026, 2, 3), D(2026, 2, 9))]
    assert sp({"kind": "prev_period", "of": {"kind": "tet", "y": 2026}}, "2026-08-19", cal=cal) == [before]


@pytest.mark.skipif(not CAL_PATH.exists(), reason="train calendar not present")
def test_tet_other_years(cal):
    assert cal.tet_range(2025) == (D(2025, 1, 22), D(2025, 2, 7))
    assert cal.tet_range(2024) == (D(2024, 2, 2), D(2024, 2, 19))


def test_prev_period_and_last_year():
    assert sp({"kind": "prev_period", "of": {"kind": "month", "m": 1, "y": 2026}}, "2026-08-19") == \
        [Span(D(2025, 12, 1), D(2025, 12, 31))]
    assert sp({"kind": "prev_period", "of": {"kind": "quarter", "q": 1, "y": 2026}}, "2026-08-19") == \
        [Span(D(2025, 10, 1), D(2025, 12, 31))]
    assert sp({"kind": "prev_period", "of": {"kind": "today"}}, "2026-08-19") == [Span(D(2026, 8, 18), D(2026, 8, 18))]
    assert sp({"kind": "prev_period", "of": {"kind": "last_n_days", "n": 7}}, "2026-08-19") == \
        [Span(D(2026, 8, 6), D(2026, 8, 12))]
    assert sp({"kind": "same_period_last_year", "of": {"kind": "month", "m": 2, "y": 2025}}, "2026-08-19") == \
        [Span(D(2024, 2, 1), D(2024, 2, 29))]
    assert sp({"kind": "same_period_last_year", "of": {"kind": "month", "m": 2, "y": 2024}}, "2026-08-19") == \
        [Span(D(2023, 2, 1), D(2023, 2, 28))]


def test_months_ending_at():
    s = sp({"kind": "months_ending_at", "m": 2, "y": 2026, "count": 3}, "2026-08-19")
    assert [x.start for x in s] == [D(2025, 12, 1), D(2026, 1, 1), D(2026, 2, 1)]


def test_n_days_from_before():
    assert sp({"kind": "n_days_from", "date": "2025-06-10", "n": 7}, "2026-01-01") == [Span(D(2025, 6, 10), D(2025, 6, 16))]
    assert sp({"kind": "n_days_before", "date": "2025-06-10", "n": 7}, "2026-01-01") == [Span(D(2025, 6, 3), D(2025, 6, 9))]


def test_clip_partial_and_out_of_range():
    kw = dict(data_start="2025-02-01", data_end="2026-06-24")
    r = resolve({"kind": "month", "m": 1, "y": 2025}, "2026-08-19", **kw)
    assert r.out_of_range and r.clipped == [None]
    r = resolve({"kind": "month", "m": 6, "y": 2026}, "2026-08-19", **kw)
    assert not r.out_of_range and r.clipped == [Span(D(2026, 6, 1), D(2026, 6, 24))]
    # records after today count as not yet happened
    r = resolve({"kind": "this_month_to_date"}, "2026-06-10", **kw)
    assert r.clipped == [Span(D(2026, 6, 1), D(2026, 6, 10))]
    r = resolve({"kind": "as_of_end_of", "date": "2025-01-15"}, "2026-08-19", **kw)
    assert r.out_of_range
