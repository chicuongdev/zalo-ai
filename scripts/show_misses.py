"""Print label misses grouped by first-candidate intent. usage: python scripts/show_misses.py [intent] [n]"""
import collections, json, sys
from pathlib import Path
rows = [json.loads(l) for l in open(Path("out/label_misses.jsonl"), encoding="utf-8")]
want = sys.argv[1] if len(sys.argv) > 1 else None
n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
g = collections.defaultdict(list)
for r in rows:
    g[r["candidates"][0]["plan"]["intent"] if r["candidates"] else "NO_PLAN"].append(r)
for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
    if want and k != want:
        continue
    print(f"=== {k} ({len(v)})")
    for r in v[:n]:
        print(f"- {r['business_id']} [{r['as_of_date']}] {r['question'][:110]!r}\n    ref={r['ref']['type']}:{str(r['ref'].get('answer'))[:70]}")
        for c in r["candidates"][:2]:
            p = {k2: v2 for k2, v2 in c["plan"].items() if k2 != "intent"}
            print(f"    {c['plan']['intent']} {json.dumps(p, ensure_ascii=False)[:150]} -> {str(c['result'].get('answer', c['result']))[:90]}")
