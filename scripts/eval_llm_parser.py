"""Benchmark an LLM as the question parser (G3), zero-shot + few-shot, no fine-tuning.

For each question of a split: prompt (catalog + shop context + BM25 few-shot gold plans from OTHER shops) ->
LLM JSON plan -> grounding -> semantic library -> answer. Compared with the rule parser and combined:

  rule              first rule-parser candidate
  llm               LLM plan
  agree             answer only when LLM and rule answers are identical, else abstain
  llm_else_rule     LLM answer; rule answer when the LLM plan fails to execute
  rule_else_llm     rule answer; LLM answer when the rule plan fails

usage (Kaggle):
  python scripts/eval_llm_parser.py --model Qwen/Qwen3.5-9B --backend vllm --dtype half --tp 2 --split dev
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
from datamate.llm import LLM, LLMConfig, extract_json  # noqa: E402
from datamate.qa.llm_parser import PLAN_SCHEMA, FewShotIndex, build_messages, ground  # noqa: E402
from datamate.qa import consistency  # noqa: E402
from datamate.qa.decide import Signals, decide  # noqa: E402
from datamate.qa.novelty import Novelty, entity_words  # noqa: E402
from datamate.qa.rule_parser import Lexicon, parse  # noqa: E402
from datamate.scoring import score_one  # noqa: E402
from datamate.semantic import NotSupported, ShopStore, Unanswerable, execute  # noqa: E402

SCORE = {"correct": 1, "abstain": 0, "wrong": -1}


def run(store, plan, as_of):
    if not isinstance(plan, dict) or "intent" not in plan:
        return {"type": "abstain", "error": "no plan"}
    try:
        typ, val = execute(store, plan, as_of)
        return {"type": typ, "answer": val}
    except Unanswerable as e:
        return {"type": "unanswerable", "reason": str(e)}
    except NotSupported as e:
        return {"type": "abstain", "error": str(e)}
    except Exception as e:  # noqa: BLE001 - a plan must never crash the run
        return {"type": "abstain", "error": f"BUG {type(e).__name__}: {e}"}


def canon(res: dict) -> str | None:
    if res.get("type") in (None, "abstain"):
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


def combine(llm_res, rule_res) -> dict:
    a, b = canon(llm_res), canon(rule_res)
    abstain = {"type": "abstain"}
    return {
        "rule": rule_res,
        "llm": llm_res,
        "agree": llm_res if a is not None and a == b else abstain,
        "llm_else_rule": llm_res if a is not None else rule_res,
        "rule_else_llm": rule_res if b is not None else llm_res,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--backend", default="vllm", choices=["vllm", "hf", "gold", "replay"],
                    help="gold = echo the gold plan; replay = --model is a rows.jsonl of an earlier run")
    ap.add_argument("--dtype", default="auto")
    ap.add_argument("--quant", default=None)
    ap.add_argument("--tp", type=int, default=1)
    ap.add_argument("--max-model-len", type=int, default=8192)
    ap.add_argument("--max-new-tokens", type=int, default=384)
    ap.add_argument("--gpu-mem", type=float, default=0.90)
    ap.add_argument("--no-guided", action="store_true")
    ap.add_argument("--max-num-seqs", type=int, default=0, help="vllm: concurrent sequences (0 = vLLM default)")
    ap.add_argument("--enforce-eager", action="store_true", help="vllm: skip CUDA graphs (saves memory)")
    ap.add_argument("--text-only", action="store_true",
                    help="vllm: multimodal checkpoint used for text only (no image/video memory profiling)")
    ap.add_argument("--thinking", action="store_true")
    ap.add_argument("--batch-size", type=int, default=8, help="hf backend only")
    ap.add_argument("--data", default="data/train")
    ap.add_argument("--gold", default="out/gold_plans.jsonl")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--pool", default="fit", help="few-shot pool split ('all' = every shop except the question's)")
    ap.add_argument("--shots", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cache", default="work/cdm")
    ap.add_argument("--out", default="out/llm_eval")
    a = ap.parse_args()

    data = Path(a.data)
    splits = json.load(open(Path(__file__).resolve().parents[1] / "configs" / "splits.json", encoding="utf-8"))
    qs = [json.loads(l) for l in open(data / "questions.jsonl", encoding="utf-8")]
    refs = {o["id"]: o for o in (json.loads(l) for l in open(data / "answers.jsonl", encoding="utf-8"))}
    gold = [json.loads(l) for l in open(a.gold, encoding="utf-8")]
    gold_by_id = {g["id"]: g for g in gold}
    # several splits in one run ("dev,holdout"): the model is loaded once (≈9 min on Kaggle T4)
    names = [s.strip() for s in a.split.split(",") if s.strip()]
    split_of = {}
    selected = []
    for name in names:
        part = qs if name == "all" else [q for q in qs if q["business_id"] in set(splits[name])]
        part = [q for q in part if q["id"] not in split_of]
        if a.limit:
            part = part[:a.limit]
        for q in part:
            split_of[q["id"]] = name
        selected += part
    qs = selected
    pool = gold if a.pool == "all" else [g for g in gold if g["business_id"] in set(splits[a.pool])]
    fewshot = FewShotIndex(pool)
    cal = Calendar.load(find_calendar(data))

    # --- Phase A + prompts
    t0 = time.time()
    stores, lexes = {}, {}
    for biz in sorted({q["business_id"] for q in qs}):
        cdm, _ = load_shop(data / "data" / biz, Path(a.cache))
        stores[biz] = ShopStore(cdm, cal)
        lexes[biz] = Lexicon(stores[biz])
    t_ingest = time.time() - t0
    convs = []
    for q in qs:
        shots = fewshot.search(q["question"], a.shots, exclude_biz=q["business_id"])
        convs.append(build_messages(q["question"], q["as_of_date"], stores[q["business_id"]], lexes[q["business_id"]], shots))
    print(f"{len(qs)} questions, {len(stores)} shops, Phase A {t_ingest:.0f}s, pool {len(pool)} gold plans", flush=True)

    # --- LLM
    cfg = LLMConfig(model=a.model, backend=a.backend, dtype=a.dtype, quantization=a.quant, tensor_parallel=a.tp,
                    max_model_len=a.max_model_len, max_new_tokens=a.max_new_tokens, gpu_memory_utilization=a.gpu_mem,
                    enable_thinking=a.thinking, guided_json=not a.no_guided)
    if a.max_num_seqs:
        cfg.extra["max_num_seqs"] = a.max_num_seqs
    if a.enforce_eager:
        cfg.extra["enforce_eager"] = True
    if a.text_only:
        cfg.extra["limit_mm_per_prompt"] = {"image": 0, "video": 0}
    t0 = time.time()
    if a.backend == "replay":   # re-ground/re-score the raw LLM outputs of an earlier run (no GPU)
        prev = {r["id"]: r["raw"] for r in (json.loads(l) for l in open(a.model, encoding="utf-8"))}
        texts, load_s = [prev.get(q["id"], "") for q in qs], 0.0
    elif a.backend == "gold":
        texts, load_s = [json.dumps(gold_by_id[q["id"]]["plan"], ensure_ascii=False) if q["id"] in gold_by_id else ""
                         for q in qs], 0.0
    else:
        llm = LLM(cfg)
        load_s = llm.load_seconds
        t0 = time.time()
        texts = llm.chat(convs, schema=PLAN_SCHEMA, batch_size=a.batch_size)
    t_gen = time.time() - t0
    print(f"model load {load_s:.0f}s, generation {t_gen:.0f}s ({t_gen / max(len(qs), 1):.2f}s/question)", flush=True)

    # --- execute and score
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    novelty = Novelty()
    for q, text in zip(qs, texts):
        biz, as_of, ref = q["business_id"], q["as_of_date"], refs[q["id"]]
        raw = extract_json(text)
        plan = ground(raw, lexes[biz]) if isinstance(raw, dict) else None
        llm_res = run(stores[biz], plan, as_of)
        rule_cands = parse(q["question"], as_of, lexes[biz])
        rule_res = run(stores[biz], rule_cands[0], as_of) if rule_cands else {"type": "abstain"}
        g = gold_by_id.get(q["id"])
        strategies = combine(llm_res, rule_res)
        # "safe" = the decision policy of scripts/predict.py (agreement + unexplained words + LLM "other")
        sig = Signals(unknown_words=novelty.unknown_words(q["question"], entity_words(lexes[biz])),
                      llm_used=a.backend != "none", llm_intent=(plan or {}).get("intent"),
                      rule_issues=consistency.check(q["question"], rule_cands[0], entity_words=entity_words(lexes[biz]), residual=True, as_of=as_of) if rule_cands else [],
                      llm_issues=consistency.check(q["question"], plan, as_of=as_of) if plan else [])
        strategies["safe"] = decide(rule_res if rule_cands else None, llm_res, sig, "safe").result
        scores = {name: score_one(res, ref) for name, res in strategies.items()}
        rows.append({"id": q["id"], "split": split_of[q["id"]], "business_id": biz, "question": q["question"],
                     "ref": ref, "raw": text, "plan": plan, "gold_plan": g["plan"] if g else None,
                     "json_ok": raw is not None, "intent_ok": bool(g and plan and plan.get("intent") == g["plan"]["intent"]),
                     "llm": llm_res, "rule": rule_res, "scores": scores,
                     "llm_score": scores["llm"], "rule_score": scores["rule"]})

    with open(out / "rows.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    def section(title: str, part: list[dict]) -> list[str]:
        n = len(part)
        if not n:
            return []
        out_lines = [f"--- {title}: {n} câu ({len({r['business_id'] for r in part})} shop)",
                     f"  JSON hợp lệ {sum(r['json_ok'] for r in part)}/{n}   "
                     f"intent đúng {sum(r['intent_ok'] for r in part)}/{n}"]
        for name in ("rule", "llm", "agree", "llm_else_rule", "rule_else_llm", "safe"):
            c = collections.Counter(r["scores"][name] for r in part)
            pa = sum(SCORE[k] * v for k, v in c.items()) / n
            out_lines.append(f"  {name:14s} đúng {c['correct']:4d}/{n:<4d} ({c['correct'] / n:6.1%})  "
                             f"sai {c['wrong']:3d}  bỏ trống {c['abstain']:3d}  PA={pa:.4f}")
        out_lines.append("  theo loại đáp án (llm): đúng/tổng, sai")
        by_t = collections.defaultdict(collections.Counter)
        for r in part:
            by_t[r["ref"]["type"]][r["llm_score"]] += 1
        for t, c in sorted(by_t.items()):
            out_lines.append(f"    {t:13s} {c['correct']:4d}/{sum(c.values()):<4d} sai {c['wrong']}")
        return out_lines

    lines = [f"model={a.model} backend={a.backend} dtype={a.dtype} quant={a.quant} shots={a.shots} split={a.split} "
             f"n={len(qs)}   sinh {t_gen / max(len(qs), 1):.2f}s/câu, nạp model {load_s:.0f}s"]
    for name in names:
        lines += section(name, [r for r in rows if r["split"] == name])
    if len(names) > 1:
        lines += section("TỔNG", rows)
    report = "\n".join(lines)
    print(report)
    (out / "report.txt").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
