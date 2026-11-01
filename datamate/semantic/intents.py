"""Intent catalog (plan/thiet_ke/03 §3): each intent turns a QueryPlan + ShopStore into a raw typed value.

A QueryPlan is a plain dict:
    {"intent": "revenue", "period": {"kind": "month", "m": 8, "y": 2025},
     "compare": {...period...}, "filters": {"product": "...", "group": "...", ...}, "k": 5, ...}
Every rule cites its rulebook section. Values are returned unformatted; `execute` returns (type, value).
"""
from __future__ import annotations

import datetime as dt
import math
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable

import pandas as pd

from ..ingest.normalize import name_key, norm_payment
from ..qa.periods import Resolved, Span, resolve
from .store import ShopStore

INTENTS: dict[str, tuple[str, Callable]] = {}


class Unanswerable(Exception):
    """Rulebook §7: the released data cannot answer the question."""


class NotSupported(Exception):
    """The library cannot evaluate this plan (bad slots, missing entity…): abstain or fallback, never unanswerable."""


def intent(name: str, typ: str):
    def deco(fn):
        INTENTS[name] = (typ, fn)
        return fn
    return deco


# ------------------------------------------------------------------ rounding (§9)

def round_money(x: float) -> int:
    return int(Decimal(repr(float(x))).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def round2(x: float, nd: int = 2) -> float:
    return float(Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP))


def pct(new: float, old: float) -> float:
    if not old:
        raise Unanswerable("base period has zero value")
    return round2((new - old) / abs(old) * 100)


# ------------------------------------------------------------------ context

class Ctx:
    def __init__(self, store: ShopStore, plan: dict, as_of):
        self.s, self.plan = store, plan
        self.as_of = as_of if isinstance(as_of, dt.date) else dt.date.fromisoformat(str(as_of)[:10])

    def period(self, key: str = "period", required: bool = True) -> Resolved | None:
        expr = self.plan.get(key)
        if expr is None:
            if required:
                raise NotSupported(f"missing {key}")
            return None
        r = resolve(expr, self.as_of, self.s.cal, self.s.data_start, self.s.data_end)
        if r.out_of_range:
            raise Unanswerable(f"{key} outside data range")
        return r

    def spans(self, key: str = "period") -> list[Span]:
        r = self.period(key)
        return [c for c in r.clipped if c is not None]

    def span(self, key: str = "period") -> Span:
        r = self.period(key)
        c = [x for x in r.clipped if x is not None]
        return Span(c[0].start, c[-1].end)

    @property
    def f(self) -> dict:
        return self.plan.get("filters") or {}


def need(store: ShopStore, *caps: str):
    for c in caps:
        if not store.caps.get(c):
            raise Unanswerable(f"shop does not record {c}")


# ------------------------------------------------------------------ entity resolution

def find_product(store: ShopStore, name: str) -> str:
    if not name:
        raise NotSupported("no product")
    k = name_key(name)
    pid = store.product_keys.get(k)
    if pid is None and name in set(store.products["product_id"]):
        pid = name
    if pid is None:
        raise NotSupported(f"unknown product {name!r}")
    return pid


def group_mask(store: ShopStore, df: pd.DataFrame, group: str) -> pd.Series:
    """§3: product group by exact group name (spelling-insensitive), never merging similar names."""
    if "p_group" not in df:
        raise Unanswerable("shop has no product groups")
    k = name_key(group)
    keys = df["p_group"].map(lambda g: name_key(g) if isinstance(g, str) else None)
    if k not in set(keys.dropna()):
        k2 = name_key("nhóm " + group) if not k.startswith("nhom") else k.replace("nhom ", "", 1)
        if k2 in set(keys.dropna()):
            k = k2
        else:
            raise NotSupported(f"unknown group {group!r}")
    return keys == k


# ------------------------------------------------------------------ order / line selection

def order_mask(c: Ctx, o: pd.DataFrame, span: Span, valid_only: bool = True) -> pd.Series:
    m = ShopStore.in_span(o["order_date"], span)
    if valid_only:
        m &= o["valid"]
    f = c.f
    if f.get("payment_method"):
        need(c.s, "payment_method")
        pm = f["payment_method"]
        want = norm_payment(pm) or pm
        m &= o["payment_method"] == want
    if f.get("channel"):
        need(c.s, "channel")
        keys = o["channel"].map(lambda v: name_key(v) if isinstance(v, str) else None)
        if name_key(f["channel"]) not in set(keys.dropna()):
            raise Unanswerable(f"shop has no channel {f['channel']!r}")
        m &= keys == name_key(f["channel"])
    if f.get("shift"):
        need(c.s, "order_ts")
        lo, hi = c.s.cfg.morning if f["shift"] == "morning" else c.s.cfg.afternoon
        m &= o["hour"].between(lo, hi)
    if f.get("customer_group"):
        need(c.s, "customer_group")
        cust = c.s.t["customers"]
        ids = set(cust.loc[cust["customer_group"].map(lambda v: name_key(v) if isinstance(v, str) else "")
                           == name_key(f["customer_group"]), "customer_id"])
        m &= o["customer_id"].isin(ids)
    if f.get("customer"):
        m &= o["ckey"] == customer_key(c.s, f["customer"])
    if f.get("staff"):
        need(c.s, "staff")
        m &= o["staff_id"].astype(str) == str(f["staff"])
    return m


LINE_FILTERS = ("product", "group", "size", "rx", "ingredient", "base_unit")


def line_mask(c: Ctx, ln: pd.DataFrame) -> pd.Series:
    f, s = c.f, c.s
    m = pd.Series(True, index=ln.index)
    if f.get("product"):
        m &= ln["product_id"] == find_product(s, f["product"])
    if f.get("group"):
        m &= group_mask(s, ln, f["group"])
    if f.get("size"):
        sz = f["size"].upper()
        m &= ln["p_name"].fillna("").str.strip().str.upper().str.endswith(f"({sz})")
    if f.get("rx") is not None or f.get("ingredient"):
        need(s, "prescription" if f.get("rx") is not None else "active_ingredient")
        drugs = s.t["drugs"].drop_duplicates("product_id").set_index("product_id")
        if f.get("rx") is not None:
            rx = ln["product_id"].map(drugs["is_rx"]).map(lambda v: v is True or v == 1)
            m &= rx if f["rx"] else ~rx
        if f.get("ingredient"):
            ing = ln["product_id"].map(drugs["ingredient"]).map(lambda v: name_key(v) if isinstance(v, str) else None)
            m &= ing == name_key(f["ingredient"])
    if f.get("base_unit"):
        m &= ln["p_base_unit"].map(lambda v: name_key(v) if isinstance(v, str) else None) == name_key(f["base_unit"])
    return m


def has_line_filter(c: Ctx) -> bool:
    return any(c.f.get(k) not in (None, "") for k in LINE_FILTERS)


def revenue_of(c: Ctx, span: Span) -> int:
    """§1: Σ line amounts of valid orders by order date; no order discount, VAT or shipping."""
    s = c.s
    if has_line_filter(c):
        need(s, "order_lines")
        ln = s.lines
        om = order_mask(c, ln, span)
        return round_money(ln.loc[om & line_mask(c, ln), "line_amount"].sum())
    o = s.orders
    return round_money(o.loc[order_mask(c, o, span), "revenue"].sum())


def item_lines(c: Ctx, span: Span, valid_only: bool = True) -> pd.DataFrame:
    """Lines of real items (§3: service-fee lines are not items) passing the filters."""
    need(c.s, "order_lines")
    ln = c.s.lines
    m = order_mask(c, ln, span, valid_only) & line_mask(c, ln) & ~ln["is_service_fee"].fillna(False) & ln["product_id"].notna()
    return ln[m]


def rank(values: pd.Series, code: Callable[[str], str], k: int | None = None, ascending: bool = False) -> list:
    """§9: by value (desc by default), ties by code ascending; returns the ids."""
    df = pd.DataFrame({"id": values.index, "v": values.values})
    df["code"] = df["id"].map(code)
    df = df.sort_values(["v", "code"], ascending=[ascending, True])
    ids = list(df["id"])
    return ids if k is None else ids[:k]


def customer_key(store: ShopStore, name: str):
    o = store.orders
    if "customer_id" in o and name in set(o["customer_id"].dropna()):
        return name
    from ..ingest.normalize import person_key
    pk = person_key(name)
    for k, disp in store.customer_display.items():
        if person_key(disp) == pk or (isinstance(k, str) and person_key(k) == pk):
            return k
    raise NotSupported(f"unknown customer {name!r}")


def customer_code(store: ShopStore):
    return lambda k: (str(k) if store.caps.get("customer_codes") else store.customer_display.get(k, str(k)))


# ------------------------------------------------------------------ revenue & orders (§1)

@intent("revenue", "number")
def i_revenue(c: Ctx):
    return sum(revenue_of(c, s) for s in c.spans())


@intent("revenue_series", "list")
def i_revenue_series(c: Ctx):
    r = c.period()
    return [revenue_of(c, s) if s is not None else 0 for s in r.clipped]


def _two(c: Ctx, fn) -> tuple[float, float]:
    """(value of the asked period, value of the compared one). `compare_filters` compares two slices of the
    same period (ca chiều vs ca sáng); otherwise the compare period defaults to the previous period (§1)."""
    cur = sum(fn(c, s) for s in c.spans("period"))
    cf = c.plan.get("compare_filters")
    if c.plan.get("compare") is None:
        c.plan = {**c.plan, "compare": c.plan["period"] if cf is not None else {"kind": "prev_period", "of": c.plan["period"]}}
    cc = Ctx(c.s, {**c.plan, "filters": cf}, c.as_of) if cf is not None else c
    old = sum(fn(cc, s) for s in cc.spans("compare"))
    return cur, old


@intent("revenue_change_pct", "percent")
def i_revenue_change_pct(c: Ctx):
    cur, old = _two(c, revenue_of)
    return pct(cur, old)


@intent("revenue_diff", "number")
def i_revenue_diff(c: Ctx):
    cur, old = _two(c, revenue_of)
    return round_money(cur - old)


@intent("revenue_share", "percent")
def i_revenue_share(c: Ctx):
    """§1: share of a group over the whole shop's revenue in the same period (walk-ins included)."""
    part = sum(revenue_of(c, s) for s in c.spans())
    whole_ctx = Ctx(c.s, {**c.plan, "filters": {}}, c.as_of)
    whole = sum(revenue_of(whole_ctx, s) for s in whole_ctx.spans())
    if not whole:
        raise Unanswerable("no revenue in period")
    return round2(part / whole * 100)


def _order_count(c: Ctx, span: Span) -> int:
    s = c.s
    if has_line_filter(c):
        ln = s.lines
        m = order_mask(c, ln, span) & line_mask(c, ln) & ~ln["is_service_fee"].fillna(False)
        return int(ln.loc[m, "order_id"].nunique())
    o = s.orders
    m = order_mask(c, o, span)
    th = c.plan.get("threshold")
    if th:
        m &= _cmp(o["revenue"], th)
    return int(m.sum())


def _cmp(v: pd.Series, th: dict) -> pd.Series:
    """§2: 'quá/hơn/trên/dưới N' exclude N; 'từ N trở lên' includes N."""
    x = float(th["value"])
    return {"gt": v > x, "ge": v >= x, "lt": v < x, "le": v <= x, "eq": v == x}[th.get("op", "gt")]


@intent("order_count", "number")
def i_order_count(c: Ctx):
    return sum(_order_count(c, s) for s in c.spans())


@intent("order_count_change_pct", "percent")
def i_order_count_change(c: Ctx):
    cur, old = _two(c, _order_count)
    return pct(cur, old)


def _cancelled(c: Ctx, span: Span) -> tuple[int, int]:
    need(c.s, "order_status")
    o = c.s.orders
    m = order_mask(c, o, span, valid_only=False)
    return int((m & (o["status"] == "cancelled")).sum()), int(m.sum())


@intent("cancel_count", "number")
def i_cancel_count(c: Ctx):
    return sum(_cancelled(c, s)[0] for s in c.spans())


@intent("cancel_rate", "percent")
def i_cancel_rate(c: Ctx):
    """§1: cancelled / every order placed in the period (all statuses)."""
    n = d = 0
    for s in c.spans():
        a, b = _cancelled(c, s)
        n, d = n + a, d + b
    if not d:
        raise Unanswerable("no orders in period")
    return round2(n / d * 100)


@intent("avg_order_value", "number")
def i_avg_order_value(c: Ctx):
    """§3: revenue / number of valid orders, rounded to the dong, half up."""
    rev = sum(revenue_of(c, s) for s in c.spans())
    n = sum(_order_count(c, s) for s in c.spans())
    if not n:
        raise Unanswerable("no orders in period")
    return round_money(rev / n)


def _daily(c: Ctx, span: Span) -> pd.Series:
    o = c.s.orders
    if has_line_filter(c):
        ln = c.s.lines
        m = order_mask(c, ln, span) & line_mask(c, ln)
        return ln[m].groupby("order_date")["line_amount"].sum()
    m = order_mask(c, o, span)
    return o[m].groupby("order_date")["revenue"].sum()


@intent("best_day", "date")
def i_best_day(c: Ctx):
    metric = c.plan.get("metric", "revenue")
    span = c.span()
    if metric == "orders":
        o = c.s.orders
        d = o[order_mask(c, o, span)].groupby("order_date")["order_id"].count()
    else:
        d = _daily(c, span)
    if d.empty:
        raise Unanswerable("no sales in period")
    best = rank(d, lambda x: str(x), 1, ascending=c.plan.get("order") == "asc")[0]
    return pd.Timestamp(best).date().isoformat()


@intent("best_month", "date")
def i_best_month(c: Ctx):
    vals = {}
    for s in c.spans():
        vals[s.start.strftime("%Y-%m")] = revenue_of(c, s)
    if c.plan.get("period", {}).get("kind") not in ("months_ending_at", "months_of_year", "month_list", "month_range"):
        span = c.span()
        o = c.s.orders
        m = order_mask(c, o, span)
        vals = o[m].groupby(o.loc[m, "order_date"].dt.strftime("%Y-%m"))["revenue"].sum().to_dict()
    ser = pd.Series(vals)
    return rank(ser, str, 1, ascending=c.plan.get("order") == "asc")[0]


@intent("days_meeting_threshold", "number")
def i_days_threshold(c: Ctx):
    d = _daily(c, c.span())
    return int(_cmp(d, c.plan["threshold"]).sum())


@intent("month_is_extreme", "boolean")
def i_month_is_extreme(c: Ctx):
    """True when the target month's revenue is strictly above (order=asc: below) every other listed month."""
    t = c.plan["target"]
    vals = {}
    for s in c.spans():
        vals[(s.start.year, s.start.month)] = revenue_of(c, s)
    key = (int(t["y"]), int(t["m"]))
    if key not in vals:
        raise NotSupported("target month not in the list")
    others = [v for k, v in vals.items() if k != key]
    if c.plan.get("order") == "asc":
        return all(vals[key] < v for v in others)
    return all(vals[key] > v for v in others)


@intent("trend_increasing", "boolean")
def i_trend(c: Ctx):
    vals = i_revenue_series(c)
    return all(b > a for a, b in zip(vals, vals[1:]))


# ------------------------------------------------------------------ items (§3)

def _item_metric(c: Ctx, span: Span, metric: str) -> pd.Series:
    ln = item_lines(c, span)
    if metric == "revenue":
        return ln.groupby("product_id")["line_amount"].sum()
    if metric == "gross_profit":
        need(c.s, "line_cost")
        gp = ln["line_amount"] - ln["qty"] * ln["sale_cost"]
        return gp.groupby(ln["product_id"]).sum()
    if metric == "orders":
        return ln.groupby("product_id")["order_id"].nunique()
    return ln.groupby("product_id")["qty_base"].sum()


@intent("top_items", "list")
def i_top_items(c: Ctx):
    v = _item_metric(c, c.span(), c.plan.get("metric", "qty_base"))
    v = v[v != 0] if c.plan.get("order") != "asc" else v
    ids = rank(v, c.s.product_code, int(c.plan.get("k", 5)), ascending=c.plan.get("order") == "asc")
    return [c.s.product_name(p) for p in ids]


@intent("best_item", "string")
def i_best_item(c: Ctx):
    v = _item_metric(c, c.span(), c.plan.get("metric", "qty_base"))
    if v.empty:
        raise Unanswerable("no sales in period")
    return c.s.product_name(rank(v, c.s.product_code, 1, ascending=c.plan.get("order") == "asc")[0])


@intent("item_qty", "number")
def i_item_qty(c: Ctx):
    """§3/§10: quantity in base units; asking in a big unit divides by its factor."""
    q = sum(item_lines(c, s)["qty_base"].sum() for s in c.spans())
    return _in_unit(c, q)


def _in_unit(c: Ctx, q_base: float):
    unit = c.plan.get("unit")
    pid = find_product(c.s, c.f["product"]) if c.f.get("product") else None
    if unit and pid:
        f = factor(c.s, pid, unit)
        q_base = q_base / f
    return int(q_base) if float(q_base).is_integer() else round2(q_base)


def factor(store: ShopStore, pid: str, unit: str) -> float:
    conv = store.t["unit_conversions"]
    m = (conv["product_id"] == pid) & (conv["unit_key"] == name_key(unit))
    return float(conv.loc[m, "factor_to_base"].iloc[0]) if m.any() else 1.0


@intent("qty_by_base_unit", "number")
def i_qty_by_base_unit(c: Ctx):
    """§3: Σ base-unit quantity of items whose base unit is <unit>, big-unit lines included."""
    unit = c.plan.get("unit") or c.f.get("base_unit")
    c.plan = {**c.plan, "filters": {**c.f, "base_unit": unit}}
    ln = pd.concat([item_lines(c, s) for s in c.spans()])
    if "p_base_unit" not in ln or ln["p_base_unit"].isna().all():
        raise Unanswerable("shop has no base units")
    q = ln["qty_base"].sum()
    return int(q) if float(q).is_integer() else round2(q)


@intent("item_count_sold", "number")
def i_item_count(c: Ctx):
    """Number of distinct items sold in the period (optionally in ≥ N orders)."""
    span = c.span()
    ln = item_lines(c, span)
    per = ln.groupby("product_id")["order_id"].nunique()
    th = c.plan.get("threshold")
    return int(_cmp(per, th).sum()) if th else int(len(per))


@intent("unsold_items", "number")
def i_unsold(c: Ctx):
    """§5: items sold before the period (valid orders) with no valid order inside it."""
    span = c.span()
    ln = c.s.lines
    base = ln["valid"] & ~ln["is_service_fee"].fillna(False) & ln["product_id"].notna()
    before = set(ln.loc[base & (ln["order_date"] < pd.Timestamp(span.start)), "product_id"])
    inside = set(ln.loc[base & ShopStore.in_span(ln["order_date"], span), "product_id"])
    return len(before - inside)


@intent("unsold_items_list", "list")
def i_unsold_list(c: Ctx):
    span = c.span()
    ln = c.s.lines
    base = ln["valid"] & ~ln["is_service_fee"].fillna(False) & ln["product_id"].notna()
    before = set(ln.loc[base & (ln["order_date"] < pd.Timestamp(span.start)), "product_id"])
    inside = set(ln.loc[base & ShopStore.in_span(ln["order_date"], span), "product_id"])
    ids = sorted(before - inside, key=c.s.product_code)
    return [c.s.product_name(p) for p in ids]


@intent("price_on_day", "number")
def i_price_on_day(c: Ctx):
    """§5: unit price on the sale lines of day D for one base unit, before line discount, all statuses."""
    span = c.span()
    pid = find_product(c.s, c.f.get("product"))
    ln = c.s.lines
    m = ShopStore.in_span(ln["order_date"], span) & (ln["product_id"] == pid)
    rows = ln[m]
    if rows.empty or "unit_price" not in rows:
        raise Unanswerable("no sale of the item that day")
    per_base = (rows["unit_price"] * rows["qty"] / rows["qty_base"]).where(rows["qty_base"] != 0, rows["unit_price"])
    p = per_base.mode().iloc[0]
    unit = c.plan.get("unit")
    if unit:
        p = p * factor(c.s, pid, unit)
    return round_money(p)


# ------------------------------------------------------------------ customers (§3)

def _cust_metric(c: Ctx, span: Span, metric: str) -> pd.Series:
    need(c.s, "customers")
    o = c.s.orders
    m = order_mask(c, o, span) & o["ckey"].notna()
    g = o[m].groupby("ckey")
    return g["order_id"].count() if metric == "orders" else g["revenue"].sum()


@intent("top_customers", "list")
def i_top_customers(c: Ctx):
    v = _cust_metric(c, c.span(), c.plan.get("metric", "revenue"))
    ids = rank(v, customer_code(c.s), int(c.plan.get("k", 5)))
    return [c.s.customer_display.get(k, k) for k in ids]


@intent("best_customer", "string")
def i_best_customer(c: Ctx):
    v = _cust_metric(c, c.span(), c.plan.get("metric", "revenue"))
    if v.empty:
        raise Unanswerable("no customer orders in period")
    k = rank(v, customer_code(c.s), 1)[0]
    return c.s.customer_display.get(k, k)


@intent("customer_share", "percent")
def i_customer_share(c: Ctx):
    """Share of buying customers (§1 'khách đã mua') meeting the order-count condition."""
    v = _cust_metric(c, c.span(), "orders")
    if v.empty:
        raise Unanswerable("no customer orders in period")
    return round2(_cmp(v, c.plan["threshold"]).sum() / len(v) * 100)


@intent("customer_count", "number")
def i_customer_count(c: Ctx):
    v = _cust_metric(c, c.span(), "orders")
    th = c.plan.get("threshold")
    return int(_cmp(v, th).sum()) if th else int(len(v))


# ------------------------------------------------------------------ executor

def execute(store: ShopStore, plan: dict, as_of) -> tuple[str, object]:
    name = plan.get("intent")
    if name not in INTENTS:
        raise NotSupported(f"unknown intent {name!r}")
    typ, fn = INTENTS[name]
    try:
        value = fn(Ctx(store, dict(plan), as_of))
    except Unanswerable:
        raise
    except (NotSupported, KeyError, ValueError, IndexError) as e:
        raise NotSupported(f"{type(e).__name__}: {e}") from e
    if isinstance(value, float) and math.isnan(value):
        raise NotSupported("NaN result")
    return plan.get("type", typ), value
