"""Official DataMate scoring rules (subject/02.evaluation.json + rulebook §9).

Shared by scripts/evaluate.py and by the formatter's round-trip check.
"""
from __future__ import annotations

import math
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

CORRECT, WRONG, ABSTAIN = "correct", "wrong", "abstain"
SCORE = {CORRECT: 1, ABSTAIN: 0, WRONG: -1}
FLOAT_EPS = 1e-9  # relative; money must match to the đồng, only float error is tolerated


def normalize_str(s) -> str:
    """NFC -> lowercase -> non letter/digit/whitespace to space -> collapse spaces. Diacritics kept."""
    s = unicodedata.normalize("NFC", str(s)).lower()
    s = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in s)
    return " ".join(s.split())


def _is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and not math.isnan(x)


def match_number(pred, ref) -> bool:
    # rulebook §9: JSON number only ("4820000" as a string is wrong); only float error is tolerated
    return _is_number(pred) and _is_number(ref) and abs(pred - ref) <= FLOAT_EPS * max(1.0, abs(ref))


def match_percent(pred, ref) -> bool:
    return _is_number(pred) and _is_number(ref) and abs(round(pred, 2) - round(ref, 2)) < 1e-9


def match_string(pred, ref, aliases=()) -> bool:
    if not isinstance(pred, str):
        return False
    accepted = {normalize_str(ref)} | {normalize_str(a) for a in aliases or ()}
    return normalize_str(pred) in accepted


def match_element(pred, ref, aliases=()) -> bool:
    """Element rule inside lists/tables: number rule for numeric references, string rule otherwise."""
    if _is_number(ref):
        return match_number(pred, ref)
    return match_string(pred, ref, aliases)


def _position_aliases(alias, i: int, n: int):
    # list/table answers carry aliases per position: [[...], [...], ...]
    if isinstance(alias, list) and len(alias) == n and all(isinstance(a, list) for a in alias):
        return alias[i]
    return ()


def match_list(pred, ref, alias=None) -> bool:
    if not isinstance(pred, list) or len(pred) != len(ref):
        return False
    return all(match_element(p, r, _position_aliases(alias, i, len(ref)))
               for i, (p, r) in enumerate(zip(pred, ref)))


def match_table(pred, ref, alias=None) -> bool:
    if not isinstance(pred, dict) or not isinstance(pred.get("columns"), list) or not isinstance(pred.get("rows"), list):
        return False
    rcols, pcols = ref["columns"], pred["columns"]
    if len(rcols) != len(pcols):
        return False
    # columns by normalized name; if the names do not match, by position
    pnorm = [normalize_str(c) for c in pcols]
    if sorted(pnorm) == sorted(normalize_str(c) for c in rcols):
        order = [pnorm.index(normalize_str(c)) for c in rcols]
    else:
        order = list(range(len(rcols)))
    rrows = ref["rows"]
    if len(pred["rows"]) != len(rrows):
        return False
    # rows are matched as a set; aliases apply to the name cell (first column) of each reference row
    unused = list(range(len(rrows)))
    for prow in pred["rows"]:
        if not isinstance(prow, list) or len(prow) != len(rcols):
            return False
        cells = [prow[j] for j in order]
        hit = next((k for k in unused
                    if all(match_element(c, r, _position_aliases(alias, k, len(rrows)) if j == 0 else ())
                           for j, (c, r) in enumerate(zip(cells, rrows[k])))), None)
        if hit is None:
            return False
        unused.remove(hit)
    return True


def ref_type(ref: dict) -> str:
    return "unanswerable" if ref.get("answer") is None else ref["type"]


def score_one(pred: dict | None, ref: dict) -> str:
    if pred is None or pred.get("type") in (None, "abstain"):
        return ABSTAIN
    # rulebook §7: a row whose reason is not a string cannot be read and counts as blank
    if "reason" in pred and pred["reason"] is not None and not isinstance(pred["reason"], str):
        return ABSTAIN
    rtype = ref_type(ref)
    if pred["type"] != rtype:
        return WRONG
    if rtype == "unanswerable":
        return CORRECT
    p, r, alias = pred.get("answer"), ref["answer"], ref.get("alias")
    if rtype == "number":
        ok = match_number(p, r)
    elif rtype == "percent":
        ok = match_percent(p, r)
    elif rtype == "string":
        ok = match_string(p, r, alias)
    elif rtype == "date":
        ok = isinstance(p, str) and p == r
    elif rtype == "boolean":
        ok = isinstance(p, bool) and p == r
    elif rtype == "list":
        ok = match_list(p, r, alias)
    elif rtype == "table":
        ok = match_table(p, r, alias)
    else:
        ok = False
    return CORRECT if ok else WRONG


@dataclass
class Report:
    n: int = 0
    counts: Counter = field(default_factory=Counter)
    groups: dict = field(default_factory=dict)  # group name -> Counter of outcomes

    @property
    def pa(self) -> float:
        return sum(SCORE[o] * c for o, c in self.counts.items()) / self.n if self.n else 0.0

    @property
    def accuracy(self) -> float:
        return self.counts[CORRECT] / self.n if self.n else 0.0


def score_all(preds: dict, refs: dict, group_of=None) -> tuple[Report, dict]:
    """preds/refs keyed by question id. group_of(qid, ref) -> list of group labels for breakdowns."""
    rep, outcomes = Report(), {}
    for qid, ref in refs.items():
        o = score_one(preds.get(qid), ref)
        outcomes[qid] = o
        rep.n += 1
        rep.counts[o] += 1
        for g in (group_of(qid, ref) if group_of else ()):
            rep.groups.setdefault(g, Counter())[o] += 1
    return rep, outcomes
