import json
from pathlib import Path

import pytest

from datamate.scoring import ABSTAIN, CORRECT, WRONG, normalize_str, score_all, score_one

TRAIN = Path(__file__).resolve().parents[1] / "data" / "train"


def test_normalize():
    assert normalize_str("Sting dâu 330ml") == "sting dâu 330ml"
    assert normalize_str("  Từ Hải Thanh - 0359470831 ") == "từ hải thanh 0359470831"
    assert normalize_str("Trà sữa ô long (L)") == "trà sữa ô long l"


REF_STR = {"type": "string", "answer": "Sting dâu 330ml", "alias": ["SP0042"]}


@pytest.mark.parametrize("pred,outcome", [
    ({"type": "string", "answer": "sting dâu 330ml"}, CORRECT),
    ({"type": "string", "answer": "sp0042"}, CORRECT),
    ({"type": "string", "answer": "Sting dầu 330ml"}, WRONG),        # wrong diacritic
    ({"type": "string", "answer": ["Sting dâu 330ml"]}, WRONG),      # wrong format
    ({"type": "list", "answer": ["Sting dâu 330ml"]}, WRONG),        # wrong type
    ({"type": "abstain"}, ABSTAIN),
    (None, ABSTAIN),
])
def test_string(pred, outcome):
    assert score_one(pred, REF_STR) == outcome


def test_number_and_percent():
    ref = {"type": "number", "answer": 4820000, "alias": []}
    assert score_one({"type": "number", "answer": 4820000.0}, ref) == CORRECT
    assert score_one({"type": "number", "answer": "4820000"}, ref) == WRONG
    assert score_one({"type": "number", "answer": 4820001}, ref) == WRONG
    pref = {"type": "percent", "answer": -12.45, "alias": []}
    assert score_one({"type": "percent", "answer": -12.449}, pref) == CORRECT
    assert score_one({"type": "percent", "answer": 12.45}, pref) == WRONG
    assert score_one({"type": "percent", "answer": -0.1245}, pref) == WRONG


def test_list_with_position_aliases():
    ref = {"type": "list", "answer": ["Cà phê sữa (M)", "Trà đào cam sả (M)"], "alias": [["SP0003"], ["SP0017"]]}
    assert score_one({"type": "list", "answer": ["SP0003", "trà đào cam sả (m)"]}, ref) == CORRECT
    assert score_one({"type": "list", "answer": ["Trà đào cam sả (M)", "Cà phê sữa (M)"]}, ref) == WRONG
    assert score_one({"type": "list", "answer": [16, 1]}, {"type": "list", "answer": [16, 1], "alias": []}) == CORRECT


def test_table():
    ref = {"type": "table", "answer": {"columns": ["khach_hang", "so_tien_no"],
                                       "rows": [["Ông Quang Hoàng", 145500], ["Từ Hải Thanh", 123000]]},
           "alias": [["KH0098"], ["KH0165", "Từ Hải Thanh 0359470831"]]}
    rows_swapped = {"columns": ["khach_hang", "so_tien_no"], "rows": [["Từ Hải Thanh 0359470831", 123000], ["KH0098", 145500]]}
    assert score_one({"type": "table", "answer": rows_swapped}, ref) == CORRECT
    other_names = {"columns": ["ten", "no"], "rows": [["Ông Quang Hoàng", 145500], ["Từ Hải Thanh", 123000]]}
    assert score_one({"type": "table", "answer": other_names}, ref) == CORRECT  # by position
    bad = {"columns": ["khach_hang", "so_tien_no"], "rows": [["Ông Quang Hoàng", 145500], ["Từ Hải Thanh", 1]]}
    assert score_one({"type": "table", "answer": bad}, ref) == WRONG


def test_unanswerable():
    ref = {"type": "unanswerable", "answer": None, "alias": []}
    assert score_one({"type": "unanswerable", "reason": "không có giá vốn"}, ref) == CORRECT
    assert score_one({"type": "unanswerable", "reason": 3}, ref) == ABSTAIN
    assert score_one({"type": "number", "answer": 0}, ref) == WRONG
    assert score_one({"type": "unanswerable"}, {"type": "number", "answer": 5, "alias": []}) == WRONG


@pytest.mark.skipif(not (TRAIN / "answers.jsonl").exists(), reason="train data not extracted")
def test_reference_answers_score_perfectly():
    refs = {}
    with open(TRAIN / "answers.jsonl", encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            refs[o["id"]] = o
    preds = {k: ({"type": "unanswerable"} if v["answer"] is None else {"type": v["type"], "answer": v["answer"]})
             for k, v in refs.items()}
    rep, _ = score_all(preds, refs)
    assert rep.counts[CORRECT] == len(refs) and rep.pa == 1.0
