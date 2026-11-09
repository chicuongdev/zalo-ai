"""Plan ↔ question consistency (plan/11 G1, after the first public submission: 34% of rule-parser answers wrong).

A plan that ignores part of the question is the main source of confident wrong answers: a month list read as
one month, "nhóm trà sữa" without a group filter, "từ 10 củ" without a threshold, a year taken as top-k, a product
linked to the wrong item. These checks need no answer key and no knowledge of the concept: they only verify that
everything the question says is used by the plan and that the answer type fits the question form.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..ingest.normalize import name_key
from ..semantic.intents import INTENTS
from .normalize import normalize_question, strip_accents

NUM = re.compile(r"\d+(?:[.,]\d+)*")
PCT_TYPES = {"percent"}
NAME_TYPES = {"string", "list", "table", "date"}


def _numbers(text: str) -> list[str]:
    return NUM.findall(text)


def _num_values(tok: str) -> set[float]:
    out = set()
    for cand in (tok.replace(".", "").replace(",", ""), tok.replace(",", "."), tok.replace(".", "").replace(",", ".")):
        try:
            out.add(float(cand))
        except ValueError:
            pass
    return out


def _plan_numbers(plan: dict) -> set[float]:
    """Every number the plan uses, with the scaled forms of money thresholds (10 củ -> 10 and 10e6)."""
    out: set[float] = set()

    def walk(x):
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            v = float(x)
            out.update({v, v / 1e3, v / 1e6, v % 100})
        elif isinstance(x, str):
            for t in _numbers(x):
                out.update(_num_values(t))
            if re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", x):          # ISO dates: day, month, year, 2-digit year
                parts = [int(p) for p in x.split("-")]
                out.update(float(p) for p in parts)
                out.add(float(parts[0] % 100))
        elif isinstance(x, dict):
            for k, v in x.items():
                if k == "y" and isinstance(v, int):
                    out.add(float(v % 100))
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
    walk(plan)
    # counts implied by the period: "3 tháng 11/2025, 12/2025, 1/2026", "120 ngày tới" (range length)
    for key in ("period", "compare"):
        p = plan.get(key) or {}
        if isinstance(p.get("items"), list):
            out.add(float(len(p["items"])))
        if p.get("kind") == "month_range":
            try:
                a, b = p["from"], p["to"]
                out.add(float((int(b["y"]) * 12 + int(b["m"])) - (int(a["y"]) * 12 + int(a["m"])) + 1))
            except (KeyError, TypeError, ValueError):
                pass
        if p.get("kind") == "range":
            import datetime as dt
            try:
                d = (dt.date.fromisoformat(p["to"]) - dt.date.fromisoformat(p["from"])).days
                out.update({float(d), float(d + 1)})
            except (KeyError, TypeError, ValueError):
                pass
    return out


def check(question: str, plan: dict | None, result_type: str | None = None, entity_words: set[str] | None = None,
          residual: bool = False, as_of=None) -> list[str]:
    """Problems that make the plan an incomplete reading of the question (empty list = consistent)."""
    if not plan or plan.get("intent") in (None, "other"):
        return ["no plan"]
    issues = []
    s = normalize_question(question)
    intent = plan["intent"]
    typ = result_type or INTENTS.get(intent, ("?", None))[0]
    f = plan.get("filters") or {}
    for key in ("product", "ingredient", "group"):
        if isinstance(f.get(key), str):           # numbers / "%" inside a linked name belong to the name
            s = _mask(s, f[key])

    # 1. every number of the question is used by the plan (period, threshold, k, n, entity name, unit)
    used = _plan_numbers(plan)
    price_ctx = re.compile(r"(gia|len|tu|xuong)\s+(\S+\s+)?$")
    for m in NUM.finditer(s):
        tok = m.group(0)
        vals = _num_values(tok)
        if vals & used or any(v in (0.0, 1.0) for v in vals):
            continue
        after = s[m.end():m.end() + 6]
        if f.get("product") and re.match(r"\s?(d|dong|k|nghin|ngan|tr|trieu)\b", after) and price_ctx.search(s[:m.start()]):
            continue                                # "đổi giá từ 26.000đ lên 27.500đ": the price event, not a slot
        issues.append(f"number {tok} unused")

    # 2. top-k sanity
    k = plan.get("k")
    if isinstance(k, int) and not 1 <= k <= 50:
        issues.append(f"k={k}")

    # 3. a mentioned group must be a filter (or the subject of a group ranking); "nhôm" is not "nhóm"
    mentions_group = re.search(r"\bnhom\b(?! tuoi| \d)", s) and (not _accented(question) or "nhóm" in question.lower())
    if mentions_group and not (f.get("group") or f.get("customer_group") or plan.get("filters_list")):
        issues.append("'nhóm' without group filter")

    # 4. answer type vs question form
    asks_pct = bool(re.search(r"%|phan tram|ti le|ti trong", s))
    asks_which = (bool(re.search(r"\b(mat hang|san pham|mon|hang|khach|ngay|thang|nha cung cap|nhan vien|tho|thuoc|"
                                 r"loai|nhom|xe|may) nao\b|\bai\b|la gi\b|nhung (mat hang|mon|san pham|khach)", s))
                  and not re.search(r"bao nhieu|\bmay\b|\bdem\b|so (mat hang|mon|khach|san pham)", s))
    asks_count = bool(re.search(r"bao nhieu|\bmay\b|so luong|tong|\bdem\b", s))
    if typ in PCT_TYPES and not asks_pct:
        issues.append("percent answer to a non-% question")
    if asks_pct and typ not in PCT_TYPES and typ != "unanswerable":
        issues.append("% question, non-% answer")
    if asks_which and typ in ("number", "percent") and not asks_count:
        issues.append("'which/who' question, numeric answer")
    if typ in ("string", "date") and asks_count and not asks_which:
        issues.append("'how much' question, name/date answer")

    # 5. a flow quantity (revenue, orders, …) cannot be asked "as of end of day X"
    per = plan.get("period") or {}
    if intent in FLOW_INTENTS and per.get("kind") == "as_of_end_of":
        issues.append("flow intent with a state period")

    # 6. (rule parser plans) every content word is explained by the intent's training vocabulary
    if residual:
        rest = residual_words(question, plan, entity_words)
        if rest:
            issues.append(f"unexplained for {intent}: {rest[:4]}")

    # 7. a linked entity must share its distinctive words with the question (codes like KH0038 are skipped)
    q_plain = " " + normalize_question(question) + " "
    for key in ("product", "customer", "supplier", "staff"):
        name = f.get(key)
        if isinstance(name, str) and not re.fullmatch(r"[A-Za-z]{1,5}\d{2,}", name.strip()):
            words = [w for w in strip_accents(name_key(name)).split() if len(w) > 2 and not w.isdigit()]
            if words and not any(f" {w} " in q_plain for w in words):
                issues.append(f"{key} {name!r} not in question")

    # 8. an explicit calendar date in the plan must be written in the question (or be today): an invented date
    #    (e.g. the day of a price increase the question leaves to the data) gives a confident wrong answer
    for d in _plan_dates(plan):
        if d == str(as_of or "")[:10]:
            continue
        y, m, dd = (int(p) for p in d.split("-"))
        pat = rf"\b0?{dd}\s*[/\-.]\s*0?{m}\b|\bngay\s+0?{dd}\s+thang\s+0?{m}\b"
        if not re.search(pat, q_plain):
            issues.append(f"date {d} not in question")
    return issues


def _plan_dates(plan: dict) -> list[str]:
    out = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("date", "from", "to") and isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                    out.append(v)
                else:
                    walk(v)
    for key in ("period", "compare"):
        walk(plan.get(key))
    return out


# ------------------------------------------------------------------ residual words (every word must be explained)

INTENT_VOCAB_FILE = Path(__file__).resolve().parents[2] / "configs" / "intent_vocab.json"
FLOW_INTENTS = {"revenue", "revenue_series", "revenue_change_pct", "revenue_diff", "revenue_share", "revenue_multi",
                "order_count", "order_count_change_pct", "cancel_count", "cancel_rate", "avg_order_value", "best_day",
                "best_month", "top_items", "best_item", "item_qty", "qty_by_base_unit", "top_customers",
                "best_customer", "customer_count", "customer_share", "gross_profit", "net_profit", "purchase_total"}


def build_intent_vocab(gold: list[dict], min_count: int = 1, generic_intents: int = 3) -> dict[str, list[str]]:
    """Words used in training questions of each intent (vocabulary statistics only)."""
    from collections import Counter, defaultdict
    c: dict[str, Counter] = defaultdict(Counter)
    for r in gold:
        words = [t for t in normalize_question(r["question"]).split() if t.isalpha()]
        f = r["plan"].get("filters") or {}
        names = set()
        for v in f.values():
            if isinstance(v, str):
                names |= set(strip_accents(name_key(v)).split())
        c[r["plan"]["intent"]].update(w for w in words if w not in names)
    out = {k: sorted(w for w, n in v.items() if n >= min_count) for k, v in c.items()}
    # words used across many intents are generic question vocabulary, not concept words
    spread = Counter(w for v in out.values() for w in v)
    out["*"] = sorted(w for w, n in spread.items() if n >= generic_intents)
    return out


_INTENT_VOCAB: dict | None = None


def intent_vocab() -> dict:
    global _INTENT_VOCAB
    if _INTENT_VOCAB is None:
        import json
        _INTENT_VOCAB = ({k: set(v) for k, v in json.loads(INTENT_VOCAB_FILE.read_text(encoding="utf-8")).items()}
                         if INTENT_VOCAB_FILE.exists() else {})
    return _INTENT_VOCAB


GENERIC = set("""
thang nam ngay tuan quy hom nay qua truoc roi nay toi den het tu dau cuoi gan nhat lien ke ky cung so voi bao nhieu
may la gi nao ai cua cho minh toi em hoi xem giup gium biet cua hang shop tiem quan nha thuoc tiem tong cong
duoc va hay voi trong thi o tai luc khi trieu nghin ngan dong gio toan bo kenh sau truoc them bay chu nhe nhi
rua chong vo goi ru hen ne ta ha a u ui
""".split())


def residual_words(question: str, plan: dict, entity_words: set[str] | None = None,
                   vocab: dict | None = None) -> list[str]:
    """Content words of the question never seen in training questions of the plan's intent."""
    from .novelty import FILLER
    allv = vocab if vocab is not None else intent_vocab()
    voc = allv.get(plan.get("intent"))
    if not voc:
        return []
    voc = set(voc) | set(allv.get("*", ()))
    f = plan.get("filters") or {}
    names = set(entity_words or ())
    for v in f.values():
        if isinstance(v, str):
            names |= set(strip_accents(name_key(v)).split())
    out = []
    for t in normalize_question(question).split():
        if t.isalpha() and len(t) > 1 and t not in voc and t not in GENERIC and t not in FILLER and t not in names:
            out.append(t)
    return out


def _accented(text: str) -> bool:
    return strip_accents(text) != text


def _mask(s: str, name: str) -> str:
    toks = re.sub(r"[^a-z0-9%]+", " ", strip_accents(name).lower().replace("%", " % ")).split()
    if not toks:
        return s
    pat = r"(?<![a-z0-9])" + r"[^a-z0-9%]*".join(re.escape(t) for t in toks) + r"(?![a-z0-9])"
    return re.sub(pat, " ENTITY ", s, count=1)
