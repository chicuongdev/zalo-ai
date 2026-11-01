"""Print table kind + column mapping for each business (A4 debugging).

usage: python scripts/inspect_mapping.py [--data data/train] [biz_105 ...]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datamate.ingest.detect import detect_business  # noqa: E402
from datamate.ingest.mapper import map_table  # noqa: E402
from datamate.ingest.readers import read_business  # noqa: E402
from datamate.ingest.readme import parse_readme  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/train")
    ap.add_argument("biz", nargs="*")
    args = ap.parse_args()
    for d in sorted((Path(args.data) / "data").iterdir()):
        if args.biz and d.name not in args.biz:
            continue
        sheets, readme_text = read_business(d)
        readme = parse_readme(readme_text)
        print(f"=== {d.name}  end={readme.data_end} conv={len(readme.conversions)} conventions={list(readme.conventions)}")
        for lt in detect_business(sheets):
            m = map_table(lt, readme)
            cols = ", ".join(f"{f}={c}{'' if m.evidence[f] == 'desc' else '(' + m.evidence[f][0] + ')'}"
                             for f, c in m.columns.items())
            print(f"  [{lt.name}] -> {m.kind} ({m.score}) alt={m.candidates[:2]}\n      {cols}")
            if m.unmapped:
                print(f"      UNMAPPED: {m.unmapped}")


if __name__ == "__main__":
    main()
