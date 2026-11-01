"""A6 report: validator scores and capability manifest of every shop.

usage: python scripts/validate_shops.py [--dump out/manifests] [biz_101 ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datamate.ingest.cache import load_shop  # noqa: E402
from datamate.ingest.validate import build_manifest, min_score  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("biz", nargs="*")
    ap.add_argument("--data", default="data/train/data")
    ap.add_argument("--dump", default=None, help="write <biz>.json manifests here")
    a = ap.parse_args()
    dirs = [d for d in sorted(Path(a.data).iterdir()) if d.is_dir() and (not a.biz or d.name in a.biz)]
    worst = []
    for d in dirs:
        cdm, _ = load_shop(d)
        man = build_manifest(cdm)        # recomputed: cheap, and always matches the current validator
        v = man["validation"]
        low = {k: x for k, x in v.items() if x is not None and x < 0.99}
        caps = man["capabilities"]
        on = [k for k, x in caps.items() if x is True]
        print(f"{d.name}: min={min_score(v):.4f} stock={caps['stock_source']} codes={caps['customer_codes']} "
              f"range={man['data_start']}..{man['data_end']}")
        if low:
            print(f"   LOW {low}")
        print(f"   caps: {' '.join(on)}")
        worst.append((min_score(v), d.name))
        if a.dump:
            out = Path(a.dump)
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{d.name}.json").write_text(json.dumps(man, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("\nworst:", sorted(worst)[:5])


if __name__ == "__main__":
    main()
