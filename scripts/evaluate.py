"""Score a submission against reference answers.

usage:
  python scripts/evaluate.py --pred out/submission.jsonl --data data/train [--split dev] [--dump out/outcomes.jsonl]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from datamate.scoring import ABSTAIN, CORRECT, SCORE, WRONG, ref_type, score_all  # noqa: E402


def read_jsonl(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return {o["id"]: o for o in (json.loads(line) for line in f if line.strip())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--data", default="data/train", help="split dir with questions.jsonl and answers.jsonl")
    ap.add_argument("--split", choices=["fit", "dev", "holdout"], help="restrict to businesses of configs/splits.json")
    ap.add_argument("--dump", help="write per-question outcomes to this jsonl")
    args = ap.parse_args()

    data = Path(args.data)
    questions = read_jsonl(data / "questions.jsonl")
    refs = read_jsonl(data / "answers.jsonl")
    preds = read_jsonl(args.pred)
    if args.split:
        keep = set(json.loads((ROOT / "configs/splits.json").read_text(encoding="utf-8"))[args.split])
        refs = {k: v for k, v in refs.items() if questions[k]["business_id"] in keep}

    rep, outcomes = score_all(preds, refs, lambda qid, ref: [f"type:{ref_type(ref)}", f"biz:{questions[qid]['business_id']}"])

    c = rep.counts
    print(f"N={rep.n}  correct={c[CORRECT]}  wrong={c[WRONG]}  abstain={c[ABSTAIN]}")
    print(f"PA={rep.pa:.4f}  accuracy={rep.accuracy:.4f}")
    print(f"\n{'group':<22}{'n':>6}{'correct':>9}{'wrong':>7}{'abstain':>9}{'PA':>8}")
    for g, gc in sorted(rep.groups.items()):
        n = sum(gc.values())
        pa = sum(SCORE[o] * k for o, k in gc.items()) / n
        print(f"{g:<22}{n:>6}{gc[CORRECT]:>9}{gc[WRONG]:>7}{gc[ABSTAIN]:>9}{pa:>8.3f}")

    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as f:
            for qid, o in outcomes.items():
                f.write(json.dumps({"id": qid, "outcome": o, "question": questions[qid]["question"],
                                    "pred": preds.get(qid), "ref": refs[qid]}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
