"""Intents beyond sales: debt (§4), purchases / stock / cost / profit (§5), industry rules (§6)."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from ..ingest.normalize import name_key
from .intents import (Ctx, NotSupported, Unanswerable, _cmp, absent, customer_code, factor, find_product, intent, item_lines,
                      need, order_mask, pct, rank, revenue_of, round2, round_money)
from .store import ShopStore

MARKETPLACE = {"shopee", "lazada", "tiki", "tiktok", "tiktok shop", "san tmdt", "sendo"}


def _ts(d: dt.date) -> pd.Timestamp:
    return pd.Timestamp(d)


def _end(d: dt.date) -> pd.Timestamp:
    return pd.Timestamp(d) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)


def _num(x) -> float:
    return int(x) if float(x).is_integer() else round2(x)


# ------------------------------------------------------------------ debt (§4)

def _debt_orders(s: ShopStore) -> pd.DataFrame:
    """Orders that can carry debt: not cancelled (returned orders still count), not COD, not marketplace."""
    need(s, "payments")
    o = s.orders
    m = o["status"] != "cancelled"
    if "payment_method" in o:
        m &= o["payment_method"] != "cod"
    if "channel" in o:
        m &= ~o["channel"].map(lambda v: name_key(v) if isinstance(v, str) else "").isin(MARKETPLACE)
    df = o[m].copy()
    total = "grand_total" if "grand_total" in df and df["grand_total"].notna().any() else "goods_total"
    df["_total"] = pd.to_numeric(df[total], errors="coerce").fillna(0)
    return df


def _payments(s: ShopStore) -> pd.DataFrame:
    p = s.t["payments"].copy()
    p["pay_date"] = pd.to_datetime(p["pay_ts"], errors="coerce").dt.normalize()
    return p


def outstanding(s: ShopStore, d: dt.date) -> pd.DataFrame:
    """Per order: unpaid part of the order total counting payments up to the end of day d; only owed > 0."""
    o = _debt_orders(s)
    o = o[o["order_date"] <= _ts(d)]
    p = _payments(s)
    paid = p[p["pay_date"] <= _ts(d)].groupby("order_id")["amount"].sum()
    o["owed"] = o["_total"] - o["order_id"].map(paid).fillna(0)
    o["age"] = (_ts(d) - o["order_date"]).dt.days
    return o[o["owed"] > 0.5]


def _as_of_date(c: Ctx) -> dt.date:
    r = c.period(required=False)
    if r is None:
        return c.as_of
    return r.spans[0].end


@intent("debt_total", "number")
def i_debt_total(c: Ctx):
    o = outstanding(c.s, _as_of_date(c))
    th = c.plan.get("age_threshold")
    if th:
        o = o[_cmp(o["age"], th)]
    if c.f.get("customer"):
        from .intents import customer_key
        o = o[o["ckey"] == customer_key(c.s, c.f["customer"])]
    return round_money(o["owed"].sum())


@intent("debtor_count", "number")
def i_debtor_count(c: Ctx):
    o = outstanding(c.s, _as_of_date(c))
    return int(o["ckey"].dropna().nunique())


def _debt_by_customer(c: Ctx) -> pd.Series:
    o = outstanding(c.s, _as_of_date(c))
    return o.dropna(subset=["ckey"]).groupby("ckey")["owed"].sum()


@intent("top_debtors", "table")
def i_top_debtors(c: Ctx):
    v = _debt_by_customer(c)
    ids = rank(v, customer_code(c.s), int(c.plan.get("k", 3)))
    rows = [[c.s.customer_display.get(k, k), round_money(v[k])] for k in ids]
    return {"columns": ["khach_hang", "so_tien_no"], "rows": rows}


@intent("top_debtors_list", "list")
def i_top_debtors_list(c: Ctx):
    v = _debt_by_customer(c)
    return [c.s.customer_display.get(k, k) for k in rank(v, customer_code(c.s), int(c.plan.get("k", 3)))]


@intent("debt_aging_buckets", "list")
def i_debt_aging(c: Ctx):
    """buckets: [[lo, hi], ...] in days, hi None = open; e.g. 0–7, 8–15, > 15."""
    o = outstanding(c.s, _as_of_date(c))
    out = []
    for lo, hi in c.plan.get("buckets") or [[0, 7], [8, 15], [16, None]]:
        m = o["age"] >= lo
        if hi is not None:
            m &= o["age"] <= hi
        out.append(round_money(o.loc[m, "owed"].sum()))
    return out


def _new_and_paid(c: Ctx) -> tuple[int, int]:
    """§4: new debt = unpaid-on-the-day part of credit orders placed in the period;
    paid = payments after the purchase day, dated in the period, on any credit order."""
    s = c.s
    o = _debt_orders(s)
    o = o[o["payment_method"] == "debt"] if "payment_method" in o else o
    if c.f.get("customer"):
        from .intents import customer_key
        o = o[o["ckey"] == customer_key(s, c.f["customer"])]
    p = _payments(s).merge(o[["order_id", "order_date"]], on="order_id")
    new = paid = 0
    for span in c.spans():
        inside = o[ShopStore.in_span(o["order_date"], span)]
        same_day = p[(p["pay_date"] == p["order_date"])].groupby("order_id")["amount"].sum()
        new += (inside["_total"] - inside["order_id"].map(same_day).fillna(0)).clip(lower=0).sum()
        later = p[(p["pay_date"] > p["order_date"]) & ShopStore.in_span(p["pay_date"], span)]
        paid += later["amount"].sum()
    return round_money(new), round_money(paid)


@intent("debt_new_and_paid", "list")
def i_debt_new_paid(c: Ctx):
    return list(_new_and_paid(c))


@intent("debt_new", "number")
def i_debt_new(c: Ctx):
    return _new_and_paid(c)[0]


@intent("debt_paid", "number")
def i_debt_paid(c: Ctx):
    return _new_and_paid(c)[1]


# ------------------------------------------------------------------ purchases (§5)

def _receipts(s: ShopStore) -> pd.DataFrame:
    need(s, "purchases")
    pr = s.t.get("purchases")
    if pr is None:
        raise Unanswerable("no purchase receipts")
    pr = pr.copy()
    if "status" in pr:
        pr = pr[~pr["status"].map(lambda v: isinstance(v, str) and ("huy" in name_key(v) or "hủy" in name_key(v)
                                                                      or "cancel" in v.lower()))]
    return pr


@intent("purchase_total", "number")
def i_purchase_total(c: Ctx):
    pr = _receipts(c.s)
    tot = 0
    for span in c.spans():
        m = ShopStore.in_span(pr["receipt_date"], span)
        if c.f.get("supplier"):
            m &= _supplier_names(c.s, pr).map(name_key) == name_key(c.f["supplier"])
        tot += pd.to_numeric(pr.loc[m, "total"], errors="coerce").sum()
    return round_money(tot)


def _supplier_names(s: ShopStore, pr: pd.DataFrame) -> pd.Series:
    if "supplier_name" in pr and pr["supplier_name"].notna().any():
        return pr["supplier_name"].fillna("")
    if "supplier_id" in pr:
        sup = s.t.get("suppliers")
        if sup is not None and "supplier_name" in sup:
            names = dict(zip(sup["supplier_id"], sup["supplier_name"]))
            return pr["supplier_id"].map(lambda x: names.get(x, x))
        return pr["supplier_id"].fillna("")
    raise Unanswerable("no supplier on receipts")


@intent("top_supplier", "string")
def i_top_supplier(c: Ctx):
    pr = _receipts(c.s)
    span = c.span()
    m = ShopStore.in_span(pr["receipt_date"], span)
    names = _supplier_names(c.s, pr)
    v = pd.to_numeric(pr.loc[m, "total"], errors="coerce").groupby(names[m]).sum()
    if v.empty:
        raise Unanswerable("no receipts in period")
    sid = pr.loc[m].groupby(names[m])["supplier_id"].first() if "supplier_id" in pr else None
    code = (lambda n: str(sid.get(n, n))) if sid is not None else str
    return rank(v, code, 1)[0]


def _purchase_lines(c: Ctx) -> pd.DataFrame:
    s = c.s
    need(s, "purchase_lines")
    pl = s.t["purchase_lines"].copy()
    if "receipt_date" not in pl or pl["receipt_date"].isna().all():
        pr = s.t.get("purchases")
        pl["receipt_date"] = pl["receipt_id"].map(dict(zip(pr["receipt_id"], pr["receipt_date"])))
    ok = set(_receipts(s)["receipt_id"]) if s.t.get("purchases") is not None else None
    if ok is not None:
        pl = pl[pl["receipt_id"].isin(ok)]
    pl["qty_base"] = [q * factor(s, p, u) if isinstance(u, str) else q for q, p, u in zip(pl["qty"], pl["product_id"], pl["unit"])]
    return pl


@intent("avg_purchase_price", "number")
def i_avg_purchase_price(c: Ctx):
    """§5: quantity-weighted average purchase price in the month, per purchase unit (or the asked unit)."""
    pid = find_product(c.s, c.f.get("product"))
    pl = _purchase_lines(c)
    span = c.span()
    rows = pl[(pl["product_id"] == pid) & ShopStore.in_span(pl["receipt_date"], span)]
    if rows.empty:
        raise Unanswerable("no purchase of the item in period")
    amt = pd.to_numeric(rows["amount"], errors="coerce").sum()
    unit = c.plan.get("unit")
    if unit:
        return round_money(amt / rows["qty_base"].sum() * factor(c.s, pid, unit))
    return round_money(amt / rows["qty"].sum())


@intent("purchase_qty", "number")
def i_purchase_qty(c: Ctx):
    pid = find_product(c.s, c.f.get("product"))
    pl = _purchase_lines(c)
    q = sum(pl[(pl["product_id"] == pid) & ShopStore.in_span(pl["receipt_date"], s)]["qty_base"].sum() for s in c.spans())
    return _num(q / factor(c.s, pid, c.plan["unit"]) if c.plan.get("unit") else q)


@intent("purchase_minus_sales", "number")
def i_purchase_minus_sales(c: Ctx):
    """§5: purchased − sold (valid orders), same unit."""
    pid = find_product(c.s, c.f.get("product"))
    pl = _purchase_lines(c)
    bought = sold = 0.0
    for span in c.spans():
        bought += pl[(pl["product_id"] == pid) & ShopStore.in_span(pl["receipt_date"], span)]["qty_base"].sum()
        sold += item_lines(c, span)["qty_base"].sum()
    q = bought - sold
    unit = c.plan.get("unit")
    return _num(q / factor(c.s, pid, unit) if unit else q)


# ------------------------------------------------------------------ stock (§5)

def _sold_base(s: ShopStore, pid=None, after=None, upto=None) -> pd.Series:
    """Base quantity leaving stock per product: lines of non-cancelled orders in (after, upto]."""
    ln = s.lines
    m = ln["status"] != "cancelled"
    if pid is not None:
        m &= ln["product_id"] == pid
    if after is not None:
        m &= ln["order_date"] > _ts(after)
    if upto is not None:
        m &= ln["order_date"] <= _ts(upto)
    return ln[m].groupby("product_id")["qty_base"].sum()


def _bought_base(c: Ctx, after=None, upto=None) -> pd.Series:
    if not c.s.caps.get("purchase_lines"):
        return pd.Series(dtype=float)
    pl = _purchase_lines(c)
    m = pd.Series(True, index=pl.index)
    if after is not None:
        m &= pl["receipt_date"] > _ts(after)
    if upto is not None:
        m &= pl["receipt_date"] <= _ts(upto)
    return pl[m].groupby("product_id")["qty_base"].sum()


def lot_remaining(c: Ctx, d: dt.date) -> pd.DataFrame:
    s = c.s
    lots = s.t["lots"].copy()
    pr = s.t.get("purchases")
    if "receipt_id" in lots and pr is not None:
        lots["in_date"] = lots["receipt_id"].map(dict(zip(pr["receipt_id"], pr["receipt_date"])))
    else:
        lots["in_date"] = pd.NaT
    lots = lots[lots["in_date"].isna() | (lots["in_date"] <= _ts(d))]
    ll = s.t["line_lots"].merge(s.orders[["order_id", "order_date", "status"]], on="order_id", how="left")
    ll = ll[(ll["order_date"] <= _ts(d)) & (ll["status"] != "cancelled")]
    out = ll.groupby("lot_id")["qty_base"].sum() - ll.groupby("lot_id")["qty_return_base"].sum().fillna(0)
    lots["remaining"] = lots["qty_in_base"] - lots["lot_id"].map(out).fillna(0)
    return lots


def stock_at(c: Ctx, d: dt.date) -> pd.Series:
    """Base-unit stock per product at end of day d (source order: ledger, lots, snapshot)."""
    s = c.s
    src = s.caps.get("stock_source")
    if src == "ledger":
        led = s.t["stock_ledger"]
        ts = pd.to_datetime(led["ts"], errors="coerce")
        return led[ts <= _end(d)].groupby("product_id")["qty_delta_base"].sum()
    if src == "lots":
        return lot_remaining(c, d).groupby("product_id")["remaining"].sum()
    if src == "snapshot":
        snap = s.t["stock_snapshot"].copy()
        snap["base"] = [q * factor(s, p, u) if isinstance(u, str) else q
                        for q, p, u in zip(snap["stock_qty"], snap["product_id"], snap["unit"])]
        st = snap.groupby("product_id")["base"].sum()
        end = s.data_end
        if d >= end:
            return st
        bought = _bought_base(c, after=d, upto=end)
        sold = _sold_base(s, after=d, upto=end)
        return st.sub(bought, fill_value=0).add(sold, fill_value=0).reindex(st.index)
    absent(s, "stock_snapshot", "shop has no stock records")


def _stock_date(c: Ctx) -> dt.date:
    r = c.period(required=False)
    return c.as_of if r is None else r.spans[0].end


@intent("stock_qty", "number")
def i_stock_qty(c: Ctx):
    pid = find_product(c.s, c.f.get("product"))
    st = stock_at(c, _stock_date(c))
    q = float(st.get(pid, 0) or 0)
    unit = c.plan.get("unit")
    return _num(q / factor(c.s, pid, unit) if unit else q)


@intent("stock_big_unit", "list")
def i_stock_big_unit(c: Ctx):
    """§5: [whole big units, leftover base units]."""
    pid = find_product(c.s, c.f.get("product"))
    q = float(stock_at(c, _stock_date(c)).get(pid, 0) or 0)
    unit = c.plan.get("unit")
    f = factor(c.s, pid, unit) if unit else 1.0
    if f == 1.0:
        conv = c.s.t["unit_conversions"]
        fs = conv.loc[conv["product_id"] == pid, "factor_to_base"]
        if fs.empty:
            raise NotSupported("no big unit")
        f = float(fs.max())
    whole = int(q // f)
    return [whole, _num(q - whole * f)]


@intent("stock_value", "number")
def i_stock_value(c: Ctx):
    need(c.s, "catalog_cost")
    st = stock_at(c, _stock_date(c))
    cost = c.s.products.set_index("product_id")["cost_price"]
    st = st[st > 0]
    return round_money((st * st.index.map(cost).astype(float)).sum())


@intent("out_of_stock_count", "number")
def i_out_of_stock(c: Ctx):
    st = stock_at(c, _stock_date(c))
    prod = c.s.products.set_index("product_id")
    if "item_type" in prod:
        made = prod["item_type"].map(lambda v: isinstance(v, str) and ("che bien" in name_key(v) or "pha che" in name_key(v)
                                                                         or "chế biến" in name_key(v) or "pha chế" in name_key(v)))
        st = st[~st.index.map(made).fillna(False).astype(bool)]
    return int((st.round(6) <= 0).sum())


@intent("out_of_stock_items", "list")
def i_out_of_stock_items(c: Ctx):
    st = stock_at(c, _stock_date(c))
    ids = sorted(st[st.round(6) <= 0].index, key=c.s.product_code)
    return [c.s.product_name(p) for p in ids]


def _expiring(c: Ctx) -> pd.DataFrame:
    """§6 pharmacy: lots still in stock today with expiry in [today, today + N] (or the given range)."""
    need(c.s, "lots", "expiry")
    from ..qa.periods import resolve
    if not c.plan.get("period"):
        raise NotSupported("expiry window needed")
    r = resolve(c.plan["period"], c.as_of, c.s.cal)      # no data-range check: the window is in the future
    if r.state_at:
        raise NotSupported("expiry window needed")
    span = r.spans[0]                  # expiry windows lie in the future: not clipped to the data range
    lots = lot_remaining(c, c.as_of)
    lots = lots[(lots["remaining"] > 0) & lots["expiry"].notna()]
    exp = pd.to_datetime(lots["expiry"])
    return lots[(exp >= _ts(span.start)) & (exp <= _ts(span.end))]


@intent("expiring_items", "list")
def i_expiring_items(c: Ctx):
    lots = _expiring(c)
    first = lots.groupby("product_id")["expiry"].min()
    ids = sorted(first.index, key=lambda p: (first[p], c.s.product_code(p)))
    return [c.s.product_name(p) for p in ids]


@intent("expiring_count", "number")
def i_expiring_count(c: Ctx):
    return int(_expiring(c)["product_id"].nunique())


@intent("expiring_value", "number")
def i_expiring_value(c: Ctx):
    lots = _expiring(c)
    return round_money((lots["remaining"] * lots["unit_cost_base"]).sum())


@intent("nearest_expiry_lot", "date")
def i_nearest_expiry(c: Ctx):
    pid = find_product(c.s, c.f.get("product"))
    lots = lot_remaining(c, c.as_of)
    lots = lots[(lots["product_id"] == pid) & (lots["remaining"] > 0) & (pd.to_datetime(lots["expiry"]) >= _ts(c.as_of))]
    if lots.empty:
        raise Unanswerable("no lot in stock")
    return pd.to_datetime(lots["expiry"]).min().date().isoformat()


# ------------------------------------------------------------------ profit (§5)

def _gross_profit(c: Ctx, span) -> float:
    need(c.s, "line_cost")
    ln = c.s.lines
    from .intents import line_mask
    m = order_mask(c, ln, span) & line_mask(c, ln)
    rows = ln[m]
    return rows["line_amount"].sum() - (rows["qty"] * rows["sale_cost"].fillna(0)).sum()


@intent("gross_profit", "number")
def i_gross_profit(c: Ctx):
    return round_money(sum(_gross_profit(c, s) for s in c.spans()))


@intent("net_profit", "number")
def i_net_profit(c: Ctx):
    need(c.s, "expenses")
    ex = c.s.t["expenses"]
    tot = 0.0
    for s in c.spans():
        tot += _gross_profit(c, s) - pd.to_numeric(ex.loc[ShopStore.in_span(ex["expense_date"], s), "amount"]).sum()
    return round_money(tot)


# ------------------------------------------------------------------ other

@intent("delivery_trips", "number")
def i_delivery_trips(c: Ctx):
    """§6 building materials: each trip of each order is one trip."""
    need(c.s, "deliveries")
    dv = c.s.t["deliveries"]
    n = 0
    for s in c.spans():
        rows = dv[ShopStore.in_span(pd.to_datetime(dv["delivery_date"]), s)]
        n += len(rows.drop_duplicates(["order_id", "trip_no"]))
    return n


@intent("best_staff", "string")
def i_best_staff(c: Ctx):
    need(c.s, "staff")
    o = c.s.orders
    m = order_mask(c, o, c.span()) & o["staff_id"].notna()
    v = o[m].groupby("staff_id")["revenue"].sum()
    if v.empty:
        raise Unanswerable("no staff sales")
    sid = rank(v, str, 1)[0]
    st = c.s.t.get("staff")
    if st is not None and "staff_name" in st:
        names = dict(zip(st["staff_id"], st["staff_name"]))
        return names.get(sid, sid)
    return sid


def price_increase_date(c: Ctx, pid: str, price: float) -> dt.date:
    """§5: the first day the item's price rose to `price` (price list; else the sale lines' unit prices)."""
    ph = c.s.t.get("price_history")
    if ph is not None and "new_price" in ph:
        rows = ph[(ph["product_id"] == pid)].sort_values("effective_date")
        hit = rows[(pd.to_numeric(rows["new_price"]) == price)
                   & (pd.to_numeric(rows.get("old_price", rows["new_price"] - 1)).fillna(-1) < price)]
        if len(hit):
            return pd.Timestamp(hit["effective_date"].iloc[0]).date()
    ln = c.s.lines
    rows = ln[(ln["product_id"] == pid) & ln["unit_price"].notna()].sort_values("order_date")
    per_day = rows.groupby("order_date")["unit_price"].max()
    prev = None
    for d, p in per_day.items():
        if p == price and prev is not None and prev < price:
            return d.date()
        prev = p
    raise NotSupported("price increase date not found")


@intent("item_qty_change_pct", "percent")
def i_item_qty_change(c: Ctx):
    """§5 price-increase effect: base quantity over N days from D vs the N days right before D (valid orders)."""
    ev = c.plan.get("price_event")
    if ev:
        d = price_increase_date(c, find_product(c.s, c.f.get("product")), float(ev["price"])).isoformat()
        per = c.plan.get("period") or {}
        if per.get("date") not in (None, d):
            # the date written in the plan contradicts the shop's own price history: a misread, not an answer
            raise NotSupported(f"price event date {d} != plan date {per.get('date')}")
        c.plan = {**c.plan, "period": {"kind": "n_days_from", "date": d, "n": ev["n"]},
                  "compare": {"kind": "n_days_before", "date": d, "n": ev["n"]}}
    per = c.plan.get("period") or {}
    if not c.plan.get("compare") and per.get("kind") == "n_days_from":
        # §5: N days from D are always compared with the N days right before D
        c.plan = {**c.plan, "compare": {"kind": "n_days_before", "date": per.get("date"), "n": per.get("n")}}
    cur = sum(item_lines(c, s)["qty_base"].sum() for s in c.spans("period"))
    old = sum(item_lines(c, s)["qty_base"].sum() for s in c.spans("compare"))
    return pct(cur, old)


@intent("unanswerable", "unanswerable")
def i_unanswerable(c: Ctx):
    """Parser decided the question asks for information the shop does not record (§7)."""
    cap = c.plan.get("needs")
    if cap and c.s.caps.get(cap):
        raise NotSupported(f"shop does record {cap}")
    if cap:
        absent(c.s, cap, c.plan.get("reason") or "not recorded")
    raise Unanswerable(c.plan.get("reason") or "not recorded")


@intent("other", "unanswerable")
def i_other(c: Ctx):
    """The parser could not place the question in the catalog (plan/11 G1): abstain or go to the fallback."""
    raise NotSupported("question outside the intent catalog")


@intent("revenue_multi", "list")
def i_revenue_multi(c: Ctx):
    out = []
    for f in c.plan.get("filters_list") or []:
        cc = Ctx(c.s, {**c.plan, "filters": f}, c.as_of)
        out.append(sum(revenue_of(cc, s) for s in cc.spans()))
    return out
