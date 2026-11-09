"""Safety layers (plan/11): rulebook diff, novelty, decision policy, formatter, 3-state manifest."""
import numpy as np
import pytest

from datamate.ingest.validate import maybe_records
from datamate.qa.decide import Signals, canon, decide
from datamate.qa.formatter import format_answer
from datamate.qa.novelty import Novelty
from datamate.rules.analyzer import analyze, parse_rows

TRAIN_RB = """# Rulebook (train)
## 3. Xếp hạng
| Luật | Mặc định |
|---|---|
| Bán chạy | theo số lượng |
"""
NEW_RB = TRAIN_RB + """| Khách sộp nhất | khách có giá trị trung bình một đơn cao nhất |
### Điện thoại
| Luật | Mặc định |
|---|---|
| Trả góp | đơn trả góp là đơn ghi nợ |
"""


def test_rulebook_rows_and_diff(tmp_path, monkeypatch):
    import datamate.rules.analyzer as A
    rows = parse_rows(TRAIN_RB)
    assert [r.term for r in rows] == ["Bán chạy"]
    f = tmp_path / "rows.json"
    monkeypatch.setattr(A, "ROWS_FILE", f)
    A.save_train_hashes(_write(tmp_path, TRAIN_RB), out=f)
    assert analyze(TRAIN_RB).concepts == []
    d = analyze(NEW_RB)
    terms = {c.term for c in d.concepts}
    assert {"Khách sộp nhất", "Trả góp"} <= terms
    assert d.concepts_in("Tháng này khách sộp nhất là ai?")
    assert d.concepts_in("khach sop nhat thang nay la ai")
    # accents disambiguate: "lãi gộp" is not "trả góp"; an accent-free question still matches "tra gop"
    assert not d.concepts_in("Tháng 3 lãi gộp bao nhiêu?")
    assert d.concepts_in("con bao nhieu tien tra gop")


def _write(tmp_path, text):
    p = tmp_path / "rb.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_novelty_flags_unknown_words_only():
    n = Novelty()
    assert n.unknown_words("Doanh thu tháng 8/2025 là bao nhiêu?") == []
    assert "sop" in n.unknown_words("Khách sộp nhất tháng 8/2025?")
    assert n.unknown_words("Khách Lê Xuân Toàn mua bao nhiêu?", {"le", "xuan", "toan"}) == []


def test_decide_policy():
    a = {"type": "number", "answer": 5}
    b = {"type": "number", "answer": 6}
    s = Signals(llm_used=True)
    assert decide(a, a, s).source == "agree"
    assert decide(a, b, s).result["type"] == "abstain"                    # disagreement
    assert decide(None, a, s).source == "llm"
    assert decide(None, a, Signals(llm_used=True, unknown_words=["sop"])).result["type"] == "abstain"
    assert decide(a, None, Signals(llm_used=True, llm_intent="other")).result["type"] == "abstain"
    assert decide(a, a, Signals(llm_used=True, new_concepts=["Khách sộp nhất"])).result["type"] == "abstain"
    assert decide(a, None, Signals()).source == "rule"                    # no LLM, clean question
    assert canon({"type": "percent", "answer": 1.0000001}) == canon({"type": "percent", "answer": 1.0})


def test_formatter_plain_json():
    assert format_answer("q", "number", np.int64(5)) == {"id": "q", "type": "number", "answer": 5}
    assert format_answer("q", "percent", np.float64(12.5))["answer"] == 12.5
    assert format_answer("q", "percent", np.float64(40.0))["answer"] == 40
    assert format_answer("q", "list", [np.int64(3), np.int64(0)])["answer"] == [3, 0]
    assert format_answer("q", "boolean", np.bool_(True))["answer"] is True
    assert format_answer("q", "unanswerable", reason="x")["type"] == "unanswerable"
    with pytest.raises(ValueError):
        format_answer("q", "number", "5")
    with pytest.raises(ValueError):
        format_answer("q", "number", float("nan"))


def test_manifest_three_states():
    man = {"unread": {"tables": [{"name": "Sổ nợ", "header": ["Khách", "Nợ", "Đã trả"]}],
                      "columns": [{"kind": "sales_flat", "table": "ban_hang", "column": "Nhân viên bán"}]}}
    assert maybe_records(man, "debt")              # an unread debt book: unknown, not absent
    assert maybe_records(man, "staff")
    assert not maybe_records({"unread": {"tables": [], "columns": []}}, "staff")


# ---- LLM plan slips (Kaggle dev run): period written into compare_filters answered 0%
def test_ground_moves_period_out_of_compare_filters():
    from datamate.qa.llm_parser import ground

    class _Lex:
        products = groups = customers = ingredients = suppliers = staff = customer_groups = channels = units = {}
    per = {"kind": "month", "m": 5, "y": 2026}
    p = ground({"intent": "revenue_change_pct", "period": per, "filters": {},
                "compare_filters": {"kind": "prev_period", "of": per}}, _Lex())
    assert p["compare"] == {"kind": "prev_period", "of": per} and "compare_filters" not in p
    p = ground({"intent": "revenue_change_pct", "period": per, "filters": {}, "compare_filters": {}, "filters_list": []}, _Lex())
    assert "compare_filters" not in p and "filters_list" not in p


def test_validate_plan_rejects_malformed():
    import pytest
    from datamate.semantic import NotSupported
    from datamate.semantic.intents import validate_plan
    per = {"kind": "month", "m": 5, "y": 2026}
    for bad in ({"intent": "revenue", "period": per, "filters": {"kind": "x"}},
                {"intent": "revenue_change_pct", "period": per, "filters": {}, "compare_filters": {}},
                {"intent": "revenue_change_pct", "period": per, "filters": {"shift": "morning"},
                 "compare_filters": {"shift": "morning"}},
                {"intent": "revenue", "period": {"m": 5}, "filters": {}}):
        with pytest.raises(NotSupported):
            validate_plan(bad)
    validate_plan({"intent": "revenue_change_pct", "period": per, "filters": {"shift": "afternoon"},
                   "compare_filters": {"shift": "morning"}})


def test_invented_date_flagged():
    from datamate.qa.consistency import check
    q = "Kể từ khi Decolgen Forte lên giá 1.400 đồng/viên, 14 ngày đầu bán được nhiều hay ít hơn 14 ngày liền trước bao nhiêu %?"
    plan = {"intent": "item_qty_change_pct", "filters": {"product": "Decolgen Forte"},
            "period": {"kind": "n_days_from", "date": "2026-05-11", "n": 14}}
    assert any(i.startswith("date") for i in check(q, plan, as_of="2026-06-30"))
    q2 = "Từ ngày 16/03/2025, Decolgen Forte tăng giá. So 7 ngày kể từ ngày 16/03/2025 với 7 ngày trước, thay đổi bao nhiêu %?"
    plan2 = {"intent": "item_qty_change_pct", "filters": {"product": "Decolgen Forte"},
             "period": {"kind": "n_days_from", "date": "2025-03-16", "n": 7}}
    assert not any(i.startswith("date") for i in check(q2, plan2, as_of="2026-06-30"))
