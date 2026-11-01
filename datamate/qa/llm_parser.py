"""B2 — LLM question parser: question -> QueryPlan JSON (plan/thiet_ke/04).

The LLM only labels: intent, period expression, filters, slots. Dates are resolved by qa/periods.py and every
number is computed by the semantic library. Prompt = catalog + shop context + few-shot gold plans (BM25 over
normalized questions) + the question. Entity strings are grounded to the shop's real names afterwards.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter

from ..ingest.normalize import name_key
from .normalize import normalize_question, strip_accents
from .rule_parser import Lexicon

INTENT_DOCS = {
    "revenue": "doanh thu / bán được bao nhiêu tiền / tiền hàng trong kỳ (lọc được theo filters)",
    "revenue_series": "doanh thu từng kỳ của nhiều tháng (list theo thứ tự thời gian)",
    "revenue_change_pct": "% thay đổi doanh thu so với kỳ compare (mặc định kỳ trước); so ca chiều/ca sáng dùng compare_filters",
    "revenue_diff": "chênh lệch doanh thu (số tiền) kỳ hỏi − kỳ so",
    "revenue_share": "doanh thu phần lọc chiếm bao nhiêu % doanh thu cả shop cùng kỳ",
    "revenue_multi": "doanh thu của nhiều nhóm lọc trong một câu, filters_list theo đúng thứ tự câu hỏi",
    "order_count": "số đơn (không huỷ, không trả); threshold cho 'đơn có tiền hàng từ X'",
    "order_count_change_pct": "% thay đổi số đơn so với kỳ/ca so sánh",
    "cancel_count": "số đơn bị huỷ",
    "cancel_rate": "tỉ lệ % đơn huỷ",
    "avg_order_value": "giá trị trung bình một đơn",
    "best_day": "ngày có doanh thu (metric=revenue) hoặc số đơn (metric=orders) cao nhất; order=asc nếu thấp nhất",
    "best_month": "tháng có doanh thu cao nhất trong các tháng nêu",
    "days_meeting_threshold": "số ngày trong kỳ có doanh thu thoả threshold",
    "trend_increasing": "doanh thu các tháng nêu có tăng liên tục không (boolean)",
    "month_is_extreme": "có phải tháng target cao hơn (order=asc: thấp hơn) mọi tháng còn lại (boolean)",
    "top_items": "k mặt hàng đứng đầu theo metric (qty_base=bán chạy, revenue, gross_profit); order=asc nếu ít nhất",
    "best_item": "một mặt hàng đứng đầu theo metric",
    "item_qty": "số lượng bán của mặt hàng / size / nhóm (unit = đơn vị câu hỏi hỏi)",
    "qty_by_base_unit": "tổng số lượng các mặt hàng có đơn vị cơ bản là unit (vd bao nhiêu ly, bao nhiêu lon)",
    "item_count_sold": "số mặt hàng có mặt trong >= N đơn (threshold op/value)",
    "unsold_items": "số mặt hàng ế: từng bán trước kỳ nhưng trong kỳ không bán được",
    "unsold_items_list": "danh sách mặt hàng ế",
    "price_on_day": "đơn giá bán của mặt hàng trong ngày (unit = đơn vị hỏi)",
    "item_qty_change_pct": "hiệu ứng tăng giá: % thay đổi số lượng N ngày kể từ ngày tăng so với N ngày trước; nếu câu không ghi ngày dùng price_event{price,n}",
    "top_customers": "k khách mua nhiều nhất (metric revenue hoặc orders)",
    "best_customer": "khách mua nhiều nhất",
    "customer_count": "số khách đã mua (threshold cho 'mua từ N đơn')",
    "customer_share": "% khách thoả threshold số đơn trên tổng khách đã mua",
    "debt_total": "tổng tiền khách còn nợ đến hết ngày (age_threshold cho 'nợ quá N ngày')",
    "debtor_count": "số khách còn nợ",
    "top_debtors": "bảng k khách nợ nhiều nhất kèm số tiền (table)",
    "top_debtors_list": "danh sách tên k khách nợ nhiều nhất",
    "debt_aging_buckets": "tiền nợ theo nhóm tuổi nợ, buckets [[0,7],[8,15],[16,null]]",
    "debt_new_and_paid": "[nợ thêm, trả nợ] trong kỳ (có thể theo khách)",
    "debt_new": "nợ thêm trong kỳ",
    "debt_paid": "tiền khách trả nợ / thu hồi công nợ trong kỳ",
    "purchase_total": "tổng tiền nhập hàng (giá trị phiếu nhập) trong kỳ",
    "top_supplier": "nhà cung cấp có tiền nhập cao nhất",
    "avg_purchase_price": "giá nhập bình quân của mặt hàng trong tháng (unit = đơn vị hỏi)",
    "purchase_qty": "số lượng nhập của mặt hàng",
    "purchase_minus_sales": "số nhập trừ số bán của mặt hàng trong kỳ",
    "stock_qty": "tồn kho của mặt hàng cuối ngày (period as_of_end_of)",
    "stock_big_unit": "tồn kho dạng [số đơn vị lớn chẵn, số lẻ đơn vị cơ bản]",
    "stock_value": "giá trị hàng tồn kho theo giá vốn",
    "out_of_stock_count": "số mặt hàng hết hàng cuối ngày",
    "out_of_stock_items": "danh sách mặt hàng hết hàng",
    "expiring_items": "danh sách hàng còn tồn có hạn dùng trong khoảng (period range)",
    "expiring_count": "số mặt hàng còn tồn sắp hết hạn trong khoảng",
    "expiring_value": "tiền vốn của các lô còn tồn sắp hết hạn",
    "nearest_expiry_lot": "hạn dùng của lô gần hết hạn nhất của một mặt hàng",
    "gross_profit": "lãi gộp trong kỳ",
    "net_profit": "lãi ròng (lãi gộp trừ chi phí) trong tháng",
    "delivery_trips": "số đợt giao hàng trong kỳ",
    "best_staff": "nhân viên bán giỏi nhất (theo doanh thu)",
    "unanswerable": "câu hỏi về thông tin shop không ghi (giới tính, thái độ, địa chỉ, liều dùng…); needs = capability nếu có",
}

PERIOD_DOC = """period.kind (LLM chỉ gắn nhãn, không tự tính ngày; ngày viết YYYY-MM-DD):
today | yesterday | day{date} | this_week | last_week | this_month_to_date | last_month | prev_month_same_days |
month{m,y} | quarter{q,y} | year{y} | ytd | range{from,to} | last_n_days{n} | as_of_end_of{date|"today"} |
tet{y} | before_tet{y,n?} | n_days_from{date,n} | n_days_before{date,n} | months_ending_at{m,y,count} |
month_list{items:[{m,y}]} | month_range{from:{m,y},to:{m,y}} | prev_period{of} | same_period_last_year{of}
Tháng/quý không ghi năm thì bỏ y. "đến hết ngày X", "cuối ngày" (tồn, nợ) => as_of_end_of."""

FILTER_DOC = """filters: product, group, size("M"/"L"), rx(true/false: thuốc kê đơn), ingredient, payment_method
(cash|transfer|ewallet|cod|card|debt), channel, shift(morning|afternoon), customer, customer_group, staff, supplier.
Tên viết như trong câu hỏi; hệ thống tự khớp với dữ liệu. threshold/age_threshold: {"op":"gt|ge|lt|le","value":số}
("quá/trên/hơn N" = gt, "từ N trở lên" = ge, "dưới N" = lt)."""

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": sorted(INTENT_DOCS)},
        "period": {"type": ["object", "null"]},
        "compare": {"type": ["object", "null"]},
        "filters": {"type": "object"},
        "compare_filters": {"type": ["object", "null"]},
        "filters_list": {"type": ["array", "null"]},
        "k": {"type": ["integer", "null"]},
        "metric": {"type": ["string", "null"]},
        "order": {"type": ["string", "null"]},
        "unit": {"type": ["string", "null"]},
        "threshold": {"type": ["object", "null"]},
        "age_threshold": {"type": ["object", "null"]},
        "buckets": {"type": ["array", "null"]},
        "target": {"type": ["object", "null"]},
        "price_event": {"type": ["object", "null"]},
        "needs": {"type": ["string", "null"]},
    },
    "required": ["intent", "filters"],
}


def system_prompt() -> str:
    lines = [f"- {k}: {v}" for k, v in INTENT_DOCS.items()]
    return ("Bạn chuyển câu hỏi tiếng Việt (có thể không dấu, viết tắt, gõ Telex) của chủ cửa hàng thành một "
            "QueryPlan JSON. Chỉ trả về JSON, không giải thích.\n\nIntent:\n" + "\n".join(lines) +
            "\n\n" + PERIOD_DOC + "\n\n" + FILTER_DOC)


# ------------------------------------------------------------------ few-shot retrieval (BM25, 0 parameters)

def _tokens(q: str) -> list[str]:
    s = re.sub(r"\d+", "#", normalize_question(q))
    toks = s.split()
    return toks + [a + "_" + b for a, b in zip(toks, toks[1:])]


class FewShotIndex:
    def __init__(self, gold: list[dict], k1: float = 1.2, b: float = 0.75):
        self.rows = gold
        self.docs = [Counter(_tokens(r["question"])) for r in gold]
        self.len = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.len) / max(len(self.len), 1)
        df = Counter(t for d in self.docs for t in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.k1, self.b = k1, b

    def search(self, question: str, k: int = 6, exclude_biz: str | None = None) -> list[dict]:
        q = set(_tokens(question))
        scored = []
        for i, d in enumerate(self.docs):
            if exclude_biz and self.rows[i]["business_id"] == exclude_biz:
                continue
            s = 0.0
            for t in q:
                f = d.get(t)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
            scored.append((s, i))
        scored.sort(reverse=True)
        out, seen = [], set()
        for s, i in scored:
            r = self.rows[i]
            key = (r["plan"]["intent"], normalize_question(r["question"])[:40])
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
            if len(out) >= k:
                break
        return out


# ------------------------------------------------------------------ shop context

def shop_context(store, lex: Lexicon, question: str) -> str:
    man = store.manifest
    caps = man.get("capabilities", {})
    enums = man.get("enums", {})
    have = [k for k, v in caps.items() if v is True]
    lines = [f"Shop ghi các loại thông tin: {', '.join(have)}"]
    if enums.get("product_group"):
        lines.append("Nhóm hàng: " + "; ".join(enums["product_group"][:40]))
    for key, label in (("channel", "Kênh bán"), ("payment_method_raw", "Hình thức thanh toán"),
                       ("customer_group", "Nhóm khách"), ("units", "Đơn vị")):
        if enums.get(key):
            lines.append(f"{label}: " + "; ".join(map(str, enums[key][:25])))
    s = normalize_question(question)
    hits = Lexicon.find(lex.products, s)[:3] + Lexicon.find(lex.customers, s)[:2]
    if hits:
        lines.append("Tên có trong dữ liệu khớp với câu hỏi: " + "; ".join(map(str, hits)))
    return "\n".join(lines)


def _compact(plan: dict) -> str:
    return json.dumps({k: v for k, v in plan.items() if v not in (None, {}, []) or k == "filters"}, ensure_ascii=False)


def build_messages(question: str, as_of: str, store, lex: Lexicon, shots: list[dict]) -> list[dict]:
    msgs = [{"role": "system", "content": system_prompt()}]
    for r in shots:
        msgs.append({"role": "user", "content": f"Hôm nay: {r['as_of_date']}\nCâu hỏi: {r['question']}"})
        msgs.append({"role": "assistant", "content": _compact(r["plan"])})
    msgs.append({"role": "user", "content": f"{shop_context(store, lex, question)}\n\nHôm nay: {as_of}\nCâu hỏi: {question}"})
    return msgs


# ------------------------------------------------------------------ grounding

def _best(table: dict[str, str], text: str, cutoff: int = 85) -> str | None:
    if not table or not isinstance(text, str) or not text.strip():
        return None
    from rapidfuzz import fuzz, process
    k = " ".join(strip_accents(name_key(text)).split())
    if k in table:
        return table[k]
    hit = process.extractOne(k, list(table), scorer=fuzz.WRatio, score_cutoff=cutoff)
    return table[hit[0]] if hit else None


def ground(plan: dict, lex: Lexicon) -> dict:
    """Map entity strings written by the LLM to the shop's own names (unknown names are left as is:
    execution then fails with NotSupported and the question is abstained, never guessed)."""
    plan = {k: v for k, v in plan.items() if v is not None}
    plan.setdefault("filters", {})

    def fix(f: dict) -> dict:
        f = {k: v for k, v in (f or {}).items() if v not in (None, "")}
        for key, table in (("product", lex.products), ("group", lex.groups), ("customer", lex.customers),
                           ("ingredient", lex.ingredients), ("supplier", lex.suppliers), ("staff", lex.staff),
                           ("customer_group", lex.customer_groups)):
            if key in f:
                g = _best(table, str(f[key]))
                if g is not None:
                    f[key] = g
        if "channel" in f and lex.channels:
            g = _best(lex.channels, str(f["channel"]), 70)
            if g is not None:
                f["channel"] = g
        return f

    plan["filters"] = fix(plan["filters"])
    if isinstance(plan.get("compare_filters"), dict):
        plan["compare_filters"] = fix(plan["compare_filters"])
    if isinstance(plan.get("filters_list"), list):
        plan["filters_list"] = [fix(f) for f in plan["filters_list"] if isinstance(f, dict)]
    if plan.get("unit") and lex.units:
        plan["unit"] = _best(lex.units, plan["unit"], 90) or plan["unit"]
    return plan
