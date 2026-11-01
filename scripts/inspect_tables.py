"""Print the logical tables detected for each business (A1–A2 debugging).

usage: python scripts/inspect_tables.py [--data data/train] [biz_105 biz_112 ...]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datamate.ingest.detect import detect_business  # noqa: E402
from datamate.ingest.readers import read_business  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/train")
    ap.add_argument("biz", nargs="*")
    args = ap.parse_args()
    root = Path(args.data) / "data"
    for d in sorted(root.iterdir()):
        if args.biz and d.name not in args.biz:
            continue
        t0 = time.time()
        sheets, _ = read_business(d)
        tables = detect_business(sheets)
        print(f"=== {d.name}  ({len(sheets)} sheets -> {len(tables)} tables, {time.time() - t0:.1f}s)")
        for t in tables:
            grp = [g for g in t.group_header if g]
            print(f"  [{t.name}] rows={t.n_rows} sources={len(t.sources)} header={t.header}"
                  + (f" groups={sorted(set(grp))}" if grp else ""))
            if t.rows:
                print(f"      first={t.rows[0]}")
                print(f"      last ={t.rows[-1]}")


if __name__ == "__main__":
    main()
