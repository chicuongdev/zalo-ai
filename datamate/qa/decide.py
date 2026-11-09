"""B8 — answer or abstain (plan/11 G1–G3, G8).

Scoring: correct +1, wrong −1, abstain 0, so an answer is only worth giving when P(correct) > 0.5. Without a
calibrated model yet, the policy is a conservative rule set over independent signals:

  * the question uses a rulebook concept that is new / redefined for this test (and not implemented)  -> abstain
  * rule parser and LLM give the same answer                                                     -> answer
  * they disagree                                                                                 -> abstain
  * only one of them produced an answer: answer only if the question has no unexplained words and the
    LLM did not say "other"
Every decision records its reason and signals (written to the logs).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


def canon(res: dict | None) -> str | None:
    """Comparable form of an executed result (None = no answer)."""
    if not res or res.get("type") in (None, "abstain"):
        return None
    if res["type"] == "unanswerable":
        return "unanswerable"

    def norm(x):
        if isinstance(x, float):
            return round(x, 6)
        if isinstance(x, list):
            return [norm(v) for v in x]
        if isinstance(x, dict):
            return {k: norm(v) for k, v in x.items()}
        return x
    return json.dumps([res["type"], norm(res.get("answer"))], ensure_ascii=False, sort_keys=True, default=str)


@dataclass
class Signals:
    new_concepts: list[str] = field(default_factory=list)   # rulebook terms new/changed vs training
    unknown_words: list[str] = field(default_factory=list)
    llm_used: bool = False
    llm_intent: str | None = None
    rule_intent: str | None = None
    rule_issues: list[str] = field(default_factory=list)    # plan ↔ question inconsistencies (qa/consistency.py)
    llm_issues: list[str] = field(default_factory=list)


@dataclass
class Decision:
    result: dict              # {"type", "answer"} / {"type": "unanswerable", "reason"} / {"type": "abstain"}
    source: str               # agree | rule | llm | none
    reason: str


ABSTAIN = {"type": "abstain"}


def decide(rule_res: dict | None, llm_res: dict | None, sig: Signals, policy: str = "safe") -> Decision:
    if sig.new_concepts:
        return Decision(ABSTAIN, "none", f"new rulebook concept: {sig.new_concepts[:3]}")
    # a plan that leaves part of the question unused is not an answer to that question
    if sig.rule_issues:
        rule_res = None
    if sig.llm_issues:
        llm_res = None
    r, l_ = canon(rule_res), canon(llm_res)
    if r is None and l_ is None and (sig.rule_issues or sig.llm_issues):
        return Decision(ABSTAIN, "none", f"plan inconsistent with question: {(sig.rule_issues or sig.llm_issues)[:3]}")
    clean = not sig.unknown_words

    if policy == "rule_only" or not sig.llm_used:
        if r is not None and (clean or policy == "rule_only"):
            return Decision(rule_res, "rule", "rule parser, no unexplained words")
        return Decision(ABSTAIN, "none", "no LLM; " + ("no rule answer" if r is None else
                                                       f"unexplained words {sig.unknown_words[:5]}"))
    if r is not None and l_ is not None:
        if r == l_:
            return Decision(llm_res, "agree", "rule parser and LLM agree")
        if policy == "llm_first":
            return Decision(llm_res, "llm", "disagreement, policy llm_first")
        return Decision(ABSTAIN, "none", "rule parser and LLM disagree")
    if l_ is not None:
        if clean and policy in ("safe", "llm_first"):
            return Decision(llm_res, "llm", "LLM only (rule parser had no answer), no unexplained words")
        return Decision(ABSTAIN, "none", f"LLM only with unexplained words {sig.unknown_words[:5]}")
    if r is not None:
        if sig.llm_intent == "other":
            return Decision(ABSTAIN, "none", "LLM says the question is outside the catalog")
        if clean:
            return Decision(rule_res, "rule", "rule parser only (LLM plan failed), no unexplained words")
        return Decision(ABSTAIN, "none", f"rule only with unexplained words {sig.unknown_words[:5]}")
    return Decision(ABSTAIN, "none", "no executable plan")
