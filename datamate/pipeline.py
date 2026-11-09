"""End-to-end prediction: test folder -> submission.jsonl (+ logs). Core of the Docker image (predict.sh).

Per shop: Phase A -> rule parser + (optional) LLM parser -> semantic library -> signals -> decide -> format.
Answers are written shop by shop, so a run stopped by the time limit keeps everything written so far (Rule 8).
"""
from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

from .calendar import Calendar, find_calendar
from .ingest.cache import load_shop
from .qa import consistency
from .qa.decide import Signals, decide
from .qa.formatter import format_answer
from .qa.llm_parser import PLAN_SCHEMA, FewShotIndex, build_messages, ground
from .qa.novelty import Novelty, entity_words
from .qa.rule_parser import Lexicon, parse
from .rules.analyzer import HANDLED_CONCEPTS, analyze
from .semantic import NotSupported, ShopStore, Unanswerable, execute


def run_plan(store, plan, as_of) -> dict:
    if not isinstance(plan, dict) or "intent" not in plan:
        return {"type": "abstain", "error": "no plan"}
    try:
        typ, val = execute(store, plan, as_of)
        return {"type": typ, "answer": val}
    except Unanswerable as e:
        return {"type": "unanswerable", "reason": str(e)}
    except NotSupported as e:
        return {"type": "abstain", "error": str(e)}
    except Exception as e:  # noqa: BLE001 - one bad plan must never stop the run
        return {"type": "abstain", "error": f"BUG {type(e).__name__}: {e}"}


def _safe_parse(question, as_of, lex):
    try:
        return parse(question, as_of, lex)
    except Exception:  # noqa: BLE001
        return []


def predict(data_dir: str | Path, out_path: str | Path, log_dir: str | Path, llm=None, gold_path: str | Path | None = None,
            cache_dir: str | Path | None = None, policy: str = "safe", shots: int = 6, only: set[str] | None = None,
            exclude_same_shop: bool = True) -> dict:
    data_dir, out_path, log_dir = Path(data_dir), Path(out_path), Path(log_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    qs = [json.loads(l) for l in open(data_dir / "questions.jsonl", encoding="utf-8") if l.strip()]
    if only:
        qs = [q for q in qs if q["business_id"] in only]
    cal_path = find_calendar(data_dir)
    cal = Calendar.load(cal_path) if cal_path else None
    rb_path = data_dir / "rulebook.md"
    diff = analyze(rb_path.read_text(encoding="utf-8")) if rb_path.exists() else None
    gold = [json.loads(l) for l in open(gold_path, encoding="utf-8")] if gold_path and Path(gold_path).exists() else []
    fewshot = FewShotIndex(gold) if gold else None
    novelty = Novelty()

    by_biz: dict[str, list] = {}
    for q in qs:
        by_biz.setdefault(q["business_id"], []).append(q)

    stats = {"questions": len(qs), "answered": 0, "unanswerable": 0, "abstain": 0, "by_source": {}}
    with open(out_path, "w", encoding="utf-8") as sub, open(log_dir / "decisions.jsonl", "w", encoding="utf-8") as lg:
        info = {"event": "start", "questions": len(qs), "shops": len(by_biz), "llm": bool(llm), "policy": policy,
                "rulebook_new_concepts": [c.term for c in diff.concepts] if diff else None}
        lg.write(json.dumps(info, ensure_ascii=False) + "\n")
        for biz in sorted(by_biz):
            t0 = time.time()
            items = by_biz[biz]
            try:
                cdm, _ = load_shop(data_dir / "data" / biz, Path(cache_dir) if cache_dir else None)
                store = ShopStore(cdm, cal)
                lex = Lexicon(store)
                ent = entity_words(lex)
            except Exception as e:  # noqa: BLE001 - unreadable shop: abstain on its questions
                lg.write(json.dumps({"event": "shop_failed", "business_id": biz, "error": repr(e),
                                     "trace": traceback.format_exc()[-2000:]}, ensure_ascii=False) + "\n")
                for q in items:
                    sub.write(json.dumps(format_answer(q["id"], "abstain"), ensure_ascii=False) + "\n")
                    stats["abstain"] += 1
                sub.flush()
                continue

            # LLM parses for the whole shop in one batch
            llm_plans: list = [None] * len(items)
            raw_texts: list = [None] * len(items)
            if isinstance(llm, dict):   # replay: {question id: raw LLM text} from an earlier decisions.jsonl
                from .llm import extract_json
                raw_texts = [llm.get(q["id"]) or "" for q in items]
                for i, t in enumerate(raw_texts):
                    raw = extract_json(t)
                    llm_plans[i] = ground(raw, lex) if isinstance(raw, dict) else None
            elif llm is not None:
                convs = []
                for q in items:
                    ex = fewshot.search(q["question"], shots, exclude_biz=biz if exclude_same_shop else None) if fewshot else []
                    convs.append(build_messages(q["question"], q["as_of_date"], store, lex, ex))
                try:
                    from .llm import extract_json
                    raw_texts = llm.chat(convs, schema=PLAN_SCHEMA)
                    for i, t in enumerate(raw_texts):
                        raw = extract_json(t)
                        llm_plans[i] = ground(raw, lex) if isinstance(raw, dict) else None
                except Exception as e:  # noqa: BLE001
                    lg.write(json.dumps({"event": "llm_failed", "business_id": biz, "error": repr(e)}) + "\n")

            for i, q in enumerate(items):
                cands = _safe_parse(q["question"], q["as_of_date"], lex)
                rule_res = run_plan(store, cands[0], q["as_of_date"]) if cands else None
                llm_plan = llm_plans[i]
                llm_res = run_plan(store, llm_plan, q["as_of_date"]) if llm_plan else None
                concepts = [c.term for c in (diff.concepts_in(q["question"]) if diff else [])
                            if c.phrase not in HANDLED_CONCEPTS]
                sig = Signals(new_concepts=concepts, unknown_words=novelty.unknown_words(q["question"], ent),
                              llm_used=llm is not None, llm_intent=(llm_plan or {}).get("intent"),
                              rule_intent=cands[0]["intent"] if cands else None,
                              rule_issues=consistency.check(q["question"], cands[0], entity_words=ent, residual=True, as_of=q["as_of_date"]) if cands else [],
                              llm_issues=consistency.check(q["question"], llm_plan, as_of=q["as_of_date"]) if llm_plan else [])
                d = decide(rule_res, llm_res, sig, policy)
                res = d.result
                try:
                    line = format_answer(q["id"], res["type"], res.get("answer"), res.get("reason"))
                except ValueError as e:
                    line, d.reason = format_answer(q["id"], "abstain"), f"format error: {e}"
                sub.write(json.dumps(line, ensure_ascii=False) + "\n")
                key = "abstain" if line["type"] == "abstain" else ("unanswerable" if line["type"] == "unanswerable"
                                                                   else "answered")
                stats[key] += 1
                stats["by_source"][d.source] = stats["by_source"].get(d.source, 0) + 1
                lg.write(json.dumps({"id": q["id"], "business_id": biz, "question": q["question"],
                                     "rule_plan": cands[0] if cands else None, "rule": rule_res,
                                     "llm_plan": llm_plan, "llm": llm_res, "llm_raw": raw_texts[i],
                                     "signals": sig.__dict__, "decision": d.source, "reason": d.reason,
                                     "submitted": line}, ensure_ascii=False, default=str) + "\n")
            sub.flush()
            lg.write(json.dumps({"event": "shop_done", "business_id": biz, "questions": len(items),
                                 "seconds": round(time.time() - t0, 1)}) + "\n")
            lg.flush()
        stats["seconds"] = round(time.time() - t_start, 1)
        lg.write(json.dumps({"event": "end", **stats}, ensure_ascii=False) + "\n")
    return stats
