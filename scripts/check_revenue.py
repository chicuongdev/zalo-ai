"""Sanity check of Phase A: monthly / quarterly shop revenue computed on the CDM vs. train answers.

Revenue (rulebook §1): sum of line amounts of orders that are not cancelled and have no returned item,
by order date, records after as_of ignored. Only plain "doanh thu tháng M/YYYY" style questions are used.

usage: python scripts/check_revenue.py [biz_101 ...]
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datamate.ingest.cache import load_shop  # noqa: E402
from datamate.ingest.parsers import strip_accents  # noqa: E402

DATA = Path("data/train")
REVENUE = re.compile(r"doanh thu|dthu|revenue|ban (duoc|dc|đc|duoc|đươc)?.*(tong cong|total)?.*bao nhi\w* tien|ban duoc tong cong")
EXCLUDE = re.compile(r"mat hang|san pham|nhom|ngay nao|thang nao|%|phan tram|don|trung binh|binh quan|ca sang|ca chieu|size|"
                     r"hoat chat|ke don|khach|tien mat|chuyen khoan|cod|vi dien tu|kenh|zalo|tai quay|dien thoai|so voi|hon|"
                     r"tang|giam|moi thang|lien|tung|lan luot|hom|tuan|gan nhat|tu dau|den het|thu ve|tien ban|ban ra|cua \w|"
                     r"nhan vien|bill|\bmon\b|\bhang (?!ban)|\bban (?!(duoc|dc|duo|tong)\b)")
MONTH = re.compile(r"thang (\d{1,2})(?:/| nam )(\d{4})")
QUARTER = re.compile(r"quy (\d)(?:/| nam )(\d{4})")


def plain(q: str) -> str:
    s = strip_accents(q).lower()
    return " ".join(re.sub(r"[^a-z0-9%/ ]+", " ", s).split())


def main():
    only = set(sys.argv[1:])
    qs = [json.loads(l) for l in open(DATA / "questions.jsonl", encoding="utf-8")]
    ans = {o["id"]: o for o in (json.loads(l) for l in open(DATA / "answers.jsonl", encoding="utf-8"))}
    by_biz: dict[str, list] = {}
    for q in qs:
        a = ans[q["id"]]
        s = plain(q["question"])
        if a["type"] != "number" or not REVENUE.search(s) or EXCLUDE.search(s):
            continue
        m, qm = MONTH.search(s), QUARTER.search(s)
        if m:
            y, mo = int(m.group(2)), int(m.group(1))
            months = [(y, mo)]
        elif qm:
            y, qn = int(qm.group(2)), int(qm.group(1))
            months = [(y, 3 * (qn - 1) + k) for k in (1, 2, 3)]
        else:
            continue
        by_biz.setdefault(q["business_id"], []).append((q, a["answer"], months))

    total = ok = 0
    for biz in sorted(by_biz):
        if only and biz not in only:
            continue
        t0 = time.time()
        cdm, _ = load_shop(DATA / "data" / biz)
        o = cdm.tables["orders"]
        rev = o[~o["status"].isin(["cancelled", "returned"]) & ~o["has_return"]].rename(columns={"revenue": "line_amount"})
        hits = []
        for q, ref, months in by_biz[biz]:
            asof = pd_ts(q["as_of_date"])
            r = rev[rev["order_date"] <= asof]
            mask = False
            for y, mo in months:
                mask = mask | ((r["order_date"].dt.year == y) & (r["order_date"].dt.month == mo))
            got = int(r.loc[mask, "line_amount"].sum())
            hits.append(got == ref)
            if got != ref:
                print(f"   MISS {biz} {q['question'][:60]!r} got={got} ref={ref} diff={got - ref}")
        total += len(hits)
        ok += sum(hits)
        print(f"{biz}: {sum(hits)}/{len(hits)}  ({time.time() - t0:.1f}s)  notes={cdm.notes[:3]}")
    print(f"\nTOTAL {ok}/{total}")


def pd_ts(s):
    import pandas as pd
    return pd.Timestamp(s)


if __name__ == "__main__":
    main()
