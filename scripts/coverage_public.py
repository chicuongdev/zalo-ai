"""Coverage of the rule parser + library on an unlabeled question set (no answers).

Reports, per shop and per first-candidate intent, how many questions get an executable plan, and dumps
questions without one (to find new intents / Phase A gaps).

usage: python scripts/coverage_public.py [--data data/public_test] [--show 40]
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datamate.calendar import Calendar, find_calendar  # noqa: E402
from datamate.ingest.cache import load_shop  # noqa: E402
from datamate.qa.rule_parser import Lexicon, parse  # noqa: E402
from datamate.semantic import NotSupported, ShopStore, Unanswerable, execute  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/public_test")
    ap.add_argument("--out", default="out/coverage_public.jsonl")
    ap.add_argument("--show", type=int, default=0)
    a = ap.parse_args()
    data = Path(a.data)
    qs = [json.loads(l) for l in open(data / "questions.jsonl", encoding="utf-8")]
    cal = Calendar.load(find_calendar(data))
    by_biz = collections.defaultdict(list)
    for q in qs:
        by_biz[q["business_id"]].append(q)
    shop_stat = collections.defaultdict(collections.Counter)
    intent_stat = collections.defaultdict(collections.Counter)
    rows = []
    for biz in sorted(by_biz):
        store = ShopStore(load_shop(data / "data" / biz)[0], cal)
        lex = Lexicon(store)
        for q in by_biz[biz]:
            cands = parse(q["question"], q["as_of_date"], lex)
            status, res = "no_plan", None
            for p in cands[:1]:
                try:
                    typ, val = execute(store, p, q["as_of_date"])
                    status, res = "answer", {"type": typ, "answer": val}
                except Unanswerable as e:
                    status, res = "unanswerable", {"reason": str(e)}
                except NotSupported as e:
                    status, res = "abstain", {"error": str(e)}
                except Exception as e:  # noqa: BLE001
                    status, res = "bug", {"error": f"{type(e).__name__}: {e}"}
            intent = cands[0]["intent"] if cands else "NO_PLAN"
            shop_stat[biz][status] += 1
            intent_stat[intent][status] += 1
            rows.append({**q, "status": status, "plan": cands[0] if cands else None, "result": res})
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    def table(title, st):
        print(f"\n== {title}  (answer / unanswerable / abstain / bug / no_plan)")
        tot = collections.Counter()
        for k in sorted(st, key=lambda k: -sum(st[k].values())):
            c = st[k]
            tot.update(c)
            print(f"  {k:24s} n={sum(c.values()):4d}  ans={c['answer']:4d} unans={c['unanswerable']:3d} "
                  f"abst={c['abstain']:3d} bug={c['bug']:3d} noplan={c['no_plan']:3d}")
        print(f"  {'TOTAL':24s} n={sum(tot.values()):4d}  ans={tot['answer']:4d} unans={tot['unanswerable']:3d} "
              f"abst={tot['abstain']:3d} bug={tot['bug']:3d} noplan={tot['no_plan']:3d}")
    table("by shop", shop_stat)
    table("by first intent", intent_stat)
    shown = 0
    for r in rows:
        if r["status"] in ("abstain", "bug", "no_plan") and shown < a.show:
            shown += 1
            print(f"- {r['business_id']} [{r['status']}] {r['question'][:110]} -> {str(r['result'])[:100]}")


if __name__ == "__main__":
    main()
