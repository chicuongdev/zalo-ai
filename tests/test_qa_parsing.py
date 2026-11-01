"""Question normalizer, rule parser periods and the semantic helpers that encode §2/§9 rules."""
import datetime as dt

import pandas as pd

from datamate.qa.normalize import normalize_question as norm
from datamate.qa.rule_parser import _threshold, parse, parse_period
from datamate.semantic.intents import _cmp, rank, round2, round_money

AS_OF = dt.date(2026, 8, 19)


def test_normalize_telex_and_teencode():
    assert norm("thangs 5/2025 dthu các đơn trả bawngf cod đươc bao nhiêu") == \
        "thang 5/2025 doanh thu cac don tra bang cod duoc bao nhieu"
    assert norm("hqua cos tổng cộng nhiêu ddown") == "hom qua co tong cong nhieu don"
    assert norm("bao nhiu mặt hàng bị ế") == "bao nhieu mat hang bi e"       # "ế" must not become "em"
    assert ">=" in norm("có mặt ở ≥ 92 đơn")
    assert "0-7" in norm("nhóm 0–7 ngày")


def test_parse_period_basic():
    p, c = parse_period(norm("doanh thu tháng 8/2025"), AS_OF)
    assert p == {"kind": "month", "m": 8, "y": 2025} and c is None
    p, c = parse_period(norm("dthu từ đầu tháng này đến hết hôm nay so với cùng kỳ tháng trước"), AS_OF)
    assert p == {"kind": "this_month_to_date"} and c == {"kind": "prev_month_same_days"}
    p, _ = parse_period(norm("Tính đến hết ngày 19/08/2026, khách còn nợ"), AS_OF)
    assert p == {"kind": "as_of_end_of", "date": "2026-08-19"}
    p, _ = parse_period(norm("dthu 30 ngày gần nhất"), AS_OF)
    assert p == {"kind": "last_n_days", "n": 30}


def test_parse_period_compare_explicit_month_and_last_year():
    p, c = parse_period(norm("Doanh thu tháng 3/2026 so với tháng 3/2025 tăng hay giảm bao nhiêu %?"), AS_OF)
    assert p == {"kind": "month", "m": 3, "y": 2026} and c == {"kind": "month", "m": 3, "y": 2025}
    p, c = parse_period(norm("so cùng kỳ năm trước, doanh thu thangs 5/2026 tawng/giamr mấy %"), AS_OF)
    assert c == {"kind": "same_period_last_year", "of": {"kind": "month", "m": 5, "y": 2026}}


def test_parse_period_lists_and_price_effect():
    p, _ = parse_period(norm("Doanh thu từng tháng của 3 tháng 11/2025, 12/2025, 1/2026 lần lượt là bao nhiêu?"), AS_OF)
    assert p["kind"] == "month_list" and [i["m"] for i in p["items"]] == [11, 12, 1]
    p, _ = parse_period(norm("Từ tháng 9/2025 đến tháng 11/2025, doanh thu mỗi tháng là bao nhiêu?"), AS_OF)
    assert p["kind"] == "month_range"
    p, c = parse_period(norm("Phở Vifon bò đổi giá vào ngày 29/06/2025. 7 ngày kể từ ngày đó bán được nhiều hay ít hơn"), AS_OF)
    assert p == {"kind": "n_days_from", "date": "2025-06-29", "n": 7}
    assert c == {"kind": "n_days_before", "date": "2025-06-29", "n": 7}


def test_tet_this_year_vs_last():
    p, c = parse_period(norm("doanh thu tết năm nay so vs tết năm trước thay đổi mấy %"), AS_OF)
    assert p == {"kind": "tet", "y": 2026} and c == {"kind": "tet", "y": 2025}


def test_threshold_rules():
    # §2: "quá/trên N" excludes N, "từ N trở lên" includes N
    assert _threshold(norm("mua từ 4 đơn trở lên")) == {"op": "ge", "value": 4.0}
    assert _threshold(norm("doanh thu trên 5 triệu"))["op"] == "gt"
    assert _threshold(norm("doanh thu đạt 9.800.000 đồng trở lên")) == {"op": "ge", "value": 9800000.0}
    v = pd.Series([3, 4, 5])
    assert list(_cmp(v, {"op": "gt", "value": 4})) == [False, False, True]
    assert list(_cmp(v, {"op": "ge", "value": 4})) == [False, True, True]


def test_rounding_half_up():
    assert round_money(1.5) == 2 and round_money(2.5) == 3 and round_money(-0.4) == 0
    assert round2(2.675) == 2.68 and round2(-10.685) == -10.69


def test_rank_ties_by_code():
    v = pd.Series({"SP0003": 10, "SP0001": 10, "SP0002": 12})
    assert rank(v, str) == ["SP0002", "SP0001", "SP0003"]
    assert rank(v, str, 1, ascending=True) == ["SP0001"]


def test_parse_intents_without_shop():
    top = parse("Liệt kê 5 mặt hàng bán chạy nhất tuần rồi.", AS_OF)[0]
    assert top["intent"] == "top_items" and top["k"] == 5 and top["period"] == {"kind": "last_week"}
    assert parse("thang 6/2026 co bao nhieu don hang bi huy ta", AS_OF)[0]["intent"] == "cancel_count"
    assert parse("ti le huy don thang 3/2025 la bao nhieu %", AS_OF)[0]["intent"] == "cancel_rate"
    assert parse("Tính đến hết ngày 19/08/2026, có bao nhiêu khách còn nợ cửa hàng?", AS_OF)[0]["intent"] == "debtor_count"
    shift = [c for c in parse("tuần trước dthu ca chiều chênh ca sáng bao nhiêu %", AS_OF) if "compare_filters" in c]
    assert shift and shift[0]["filters"]["shift"] == "afternoon" and shift[0]["compare_filters"]["shift"] == "morning"
