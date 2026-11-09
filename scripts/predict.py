"""Predict a test folder -> submission.jsonl.

  python scripts/predict.py --data data/public_test --out result/submission.jsonl                       # rule parser only
  python scripts/predict.py --data /data --out /result/submission.jsonl --logs /result/logs \\
         --model /models/qwen3.5-9b --tp 2 --dtype bfloat16                                                # with LLM

The folder holds questions.jsonl, rulebook.md, calendar.csv and data/<business_id>/.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from datamate.pipeline import predict  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="result/submission.jsonl")
    ap.add_argument("--logs", default=None, help="default: <out dir>/logs")
    ap.add_argument("--gold", default=str(ROOT / "out" / "gold_plans.jsonl"), help="few-shot pool")
    ap.add_argument("--cache", default=None, help="Phase A cache dir (dev only)")
    ap.add_argument("--policy", default="safe", choices=["safe", "llm_first", "rule_only"])
    ap.add_argument("--only", nargs="*", default=None, help="business ids")
    # LLM (omit --model to run the rule parser alone)
    ap.add_argument("--model", default=None)
    ap.add_argument("--backend", default="vllm")
    ap.add_argument("--dtype", default="auto")
    ap.add_argument("--quant", default=None)
    ap.add_argument("--tp", type=int, default=1)
    ap.add_argument("--max-model-len", type=int, default=4096)
    ap.add_argument("--max-num-seqs", type=int, default=0)
    ap.add_argument("--gpu-mem", type=float, default=0.90)
    ap.add_argument("--enforce-eager", action="store_true")
    ap.add_argument("--text-only", action="store_true")
    ap.add_argument("--shots", type=int, default=6)
    a = ap.parse_args()

    llm = None
    if a.backend == "replay":   # --model = decisions.jsonl of an earlier LLM run: re-decide with current code, no GPU
        llm = {d["id"]: d.get("llm_raw") for d in (json.loads(l) for l in open(a.model, encoding="utf-8"))
               if "id" in d and d.get("llm_raw")}
        print(f"replaying {len(llm)} LLM outputs", flush=True)
    elif a.model:
        from datamate.llm import LLM, LLMConfig
        cfg = LLMConfig(model=a.model, backend=a.backend, dtype=a.dtype, quantization=a.quant, tensor_parallel=a.tp,
                        max_model_len=a.max_model_len, gpu_memory_utilization=a.gpu_mem)
        if a.max_num_seqs:
            cfg.extra["max_num_seqs"] = a.max_num_seqs
        if a.enforce_eager:
            cfg.extra["enforce_eager"] = True
        if a.text_only:
            cfg.extra["limit_mm_per_prompt"] = {"image": 0, "video": 0}
        llm = LLM(cfg)
        print(f"model loaded in {llm.load_seconds:.0f}s", flush=True)

    out = Path(a.out)
    logs = Path(a.logs) if a.logs else out.parent / "logs"
    stats = predict(a.data, out, logs, llm=llm, gold_path=a.gold, cache_dir=a.cache, policy=a.policy, shots=a.shots,
                    only=set(a.only) if a.only else None)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
