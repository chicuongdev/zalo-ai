"""Oracle replay / gold-plan labelling (plan/thiet_ke/09).

For every train question: rule parser -> candidate plans -> execute on the shop -> keep the first candidate whose
answer scores correct. Output:
  out/gold_plans.jsonl   {id, business_id, question, as_of_date, plan}       (plan = the matching candidate)
  out/label_misses.jsonl {id, ..., ref, candidates: [{plan, result|error}]}  (to fix the library or parser)
and a report by answer type and by intent of the first candidate.

usage: python scripts/label_plans.py [--split dev] [--biz biz_101 ...] [--show 20]
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datamate.calendar import Calendar, find_calendar  # noqa: E402
from datamate.ingest.cache import load_shop  # noqa: E402
from datamate.qa.rule_parser import Lexicon, parse  # noqa: E402
from datamate.scoring import CORRECT, ref_type, score_one  # noqa: E402
from datamate.semantic import NotSupported, Unanswerable, execute  # noqa: E402
from datamate.semantic.store import ShopStore  # noqa: E402


def run_plan(store, plan, as_of):
    try:
        typ, val = execute(store, plan, as_of)
        return {"type": typ, "answer": val}
    except Unanswerable as e:
        return {"type": "unanswerable", "reason": str(e)}
    except NotSupported as e:
        return {"type": "abstain", "error": str(e)}
    except Exception as e:   # library bug: record, keep going
        return {"type": "abstain", "error": f"BUG {type(e).__name__}: {e}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/train")
    ap.add_argument("--split", default=None, help="fit / dev / holdout (configs/splits.json)")
    ap.add_argument("--biz", nargs="*", default=None)
    ap.add_argument("--out", default="out")
    ap.add_argument("--show", type=int, default=0, help="print N misses")
    a = ap.parse_args()

    data = Path(a.data)
    qs = [json.loads(l) for l in open(data / "questions.jsonl", encoding="utf-8")]
    refs = {o["id"]: o for o in (json.loads(l) for l in open(data / "answers.jsonl", encoding="utf-8"))}
    if a.split:
        split = set(json.load(open("configs/splits.json", encoding="utf-8"))[a.split])
        qs = [q for q in qs if q["business_id"] in split]
    if a.biz:
        qs = [q for q in qs if q["business_id"] in a.biz]
    cal = Calendar.load(find_calendar(data))

    by_biz = collections.defaultdict(list)
    for q in qs:
        by_biz[q["business_id"]].append(q)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    gold_f = open(out / "gold_plans.jsonl", "w", encoding="utf-8")
    miss_f = open(out / "label_misses.jsonl", "w", encoding="utf-8")
    stat_type = collections.defaultdict(collections.Counter)
    stat_intent = collections.defaultdict(collections.Counter)
    first_score = collections.Counter()      # what a submission of the first candidate would score
    preds = {}
    shown = 0
    t0 = time.time()
    for biz in sorted(by_biz):
        cdm, _ = load_shop(data / "data" / biz)
        store = ShopStore(cdm, cal)
        lex = Lexicon(store)
        for q in by_biz[biz]:
            ref = refs[q["id"]]
            rt = ref_type(ref)
            cands = parse(q["question"], q["as_of_date"], lex)
            tried, hit = [], None
            for p in cands:
                res = run_plan(store, p, q["as_of_date"])
                tried.append({"plan": p, "result": res})
                if score_one(res, ref) == CORRECT:
                    hit = p
                    break
            first = cands[0]["intent"] if cands else "NO_PLAN"
            pred = tried[0]["result"] if tried else {"type": "abstain"}
            first_score[score_one(pred, ref)] += 1
            preds[q["id"]] = {"id": q["id"], **{k: v for k, v in pred.items() if k in ("type", "answer", "reason")}}
            status = "gold" if hit else ("no_plan" if not cands else "miss")
            stat_type[rt][status] += 1
            stat_intent[hit["intent"] if hit else first][status] += 1
            row = {"id": q["id"], "business_id": biz, "question": q["question"], "as_of_date": q["as_of_date"]}
            if hit:
                gold_f.write(json.dumps({**row, "plan": hit}, ensure_ascii=False, default=str) + "\n")
            else:
                miss_f.write(json.dumps({**row, "ref": ref, "candidates": tried}, ensure_ascii=False, default=str) + "\n")
                if shown < a.show:
                    shown += 1
                    print(f"MISS {biz} {rt} {q['question'][:90]!r} ref={str(ref.get('answer'))[:60]}")
                    for t in tried[:3]:
                        print(f"     {t['plan']} -> {str(t['result'])[:120]}")
        print(f"{biz}: done ({time.time() - t0:.0f}s)", file=sys.stderr)

    def table(title, st):
        print(f"\n== {title}")
        tot = collections.Counter()
        for k in sorted(st, key=lambda k: -sum(st[k].values())):
            c = st[k]
            n = sum(c.values())
            tot.update(c)
            print(f"  {k:28s} {c['gold']:5d}/{n:<5d} ({c['gold'] / n:6.1%})  miss={c['miss']} no_plan={c['no_plan']}")
        n = sum(tot.values())
        print(f"  {'TOTAL':28s} {tot['gold']:5d}/{n:<5d} ({tot['gold'] / max(n, 1):6.1%})")

    table("by answer type", stat_type)
    table("by intent", stat_intent)
    n = sum(first_score.values())
    pa = (first_score["correct"] - first_score["wrong"]) / max(n, 1)
    print(f"\n== first candidate as submission: correct={first_score['correct']} wrong={first_score['wrong']} "
          f"abstain={first_score['abstain']}  PA={pa:.4f}")
    with open(out / "rule_parser_submission.jsonl", "w", encoding="utf-8") as f:
        for r in preds.values():
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


if __name__ == "__main__":
    main()
