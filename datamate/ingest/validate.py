"""A6 — invariant checks on a built shop + the capability manifest (plan/thiet_ke/01 §3, 02 §A6).

Each check scores 0–1 (fraction of rows passing) or is None when it does not apply. The manifest says which
kinds of information the shop records; answerability (B5) compares a question's needs against it, and the
parser prompt shows `enums` so the LLM knows the shop's real labels.
"""
from __future__ import annotations

import pandas as pd

from .builder import ShopCDM
from .normalize import name_key

TOL = 1.0   # one dong: money is integer VND


def _has(cdm: ShopCDM, table: str, col: str | None = None, min_rate: float = 0.0) -> bool:
    df = cdm.tables.get(table)
    if df is None or len(df) == 0:
        return False
    if col is None:
        return True
    if col not in df:
        return False
    rate = df[col].notna().mean()
    return bool(rate > min_rate)


def _rate(mask: pd.Series) -> float | None:
    return None if len(mask) == 0 else round(float(mask.mean()), 4)


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype("float64")


# ------------------------------------------------------------------ checks

def check_lines_vs_goods_total(cdm: ShopCDM) -> float | None:
    o, ln = cdm.tables["orders"], cdm.tables["order_lines"]
    if "goods_total" not in o or "line_amount" not in ln or ln["line_amount"].notna().sum() == 0:
        return None
    s = ln.groupby("order_id")["line_amount"].sum(min_count=1)
    df = pd.DataFrame({"lines": o["order_id"].map(s).astype("float64"), "total": _num(o["goods_total"])}).dropna()
    return _rate((df["lines"] - df["total"]).abs() <= TOL)


def check_line_arith(cdm: ShopCDM) -> float | None:
    ln = cdm.tables["order_lines"]
    if not {"qty", "unit_price", "line_amount"} <= set(ln.columns):
        return None
    disc = _num(ln["line_discount"]).fillna(0) if "line_discount" in ln else 0.0
    df = pd.DataFrame({"q": _num(ln["qty"]), "p": _num(ln["unit_price"]), "a": _num(ln["line_amount"])})
    df["d"] = disc
    df = df.dropna(subset=["q", "p", "a"])
    if df.empty:
        return None
    gross = (df["q"] * df["p"]).abs()
    amt = df["a"].abs()
    expect = (df["q"] * df["p"] - df["d"]).abs()
    # exact (± rounding), or an unrecorded line discount: amount after discount lies in [50 %, 100 %] of qty × price.
    # A wrong money column shows up as amount > qty × price or far below it.
    ok = ((expect - amt).abs() <= TOL + 0.005 * amt) | ((amt <= gross + TOL) & (amt >= 0.5 * gross))
    return _rate(ok)


def check_qty_base(cdm: ShopCDM) -> float | None:
    ln, conv = cdm.tables["order_lines"], cdm.tables["unit_conversions"]
    if "qty_base" not in ln or "qty" not in ln:
        return None
    df = ln[["product_id", "qty", "qty_base"]].dropna()
    df = df[_num(df["qty"]) != 0]
    if df.empty:
        return None
    known: dict = {}
    for p, f in zip(conv["product_id"], conv["factor_to_base"]):
        known.setdefault(p, {1.0}).add(float(f))
    ratio = _num(df["qty_base"]) / _num(df["qty"])
    ok = [any(abs(r - f) < 1e-6 for f in known.get(p, {1.0})) for p, r in zip(df["product_id"], ratio)]
    return _rate(pd.Series(ok))


def check_status(cdm: ShopCDM) -> float | None:
    o = cdm.tables["orders"]
    if "status_raw" not in o or o["status_raw"].isna().all():
        return None
    has_raw = o["status_raw"].notna()
    return _rate(o.loc[has_raw, "status"].notna())


def check_dates(cdm: ShopCDM) -> float | None:
    o = cdm.tables["orders"]
    if "order_date" not in o or o["order_date"].isna().all():
        return None
    d = o["order_date"].dropna()
    if cdm.data_end is None:
        return 1.0
    return _rate(d <= pd.Timestamp(cdm.data_end))


def check_order_date_present(cdm: ShopCDM) -> float | None:
    o = cdm.tables["orders"]
    if "order_date" not in o:
        return 0.0
    return _rate(o["order_date"].notna())


def check_payments(cdm: ShopCDM) -> float | None:
    if not _has(cdm, "payments", "amount"):
        return None
    o, p = cdm.tables["orders"], cdm.tables["payments"]
    total_col = "grand_total" if "grand_total" in o and o["grand_total"].notna().any() else "goods_total"
    if total_col not in o:
        return None
    s = p.groupby("order_id")["amount"].sum(min_count=1)
    df = pd.DataFrame({"paid": o["order_id"].map(s).astype("float64"), "total": _num(o[total_col])}).dropna()
    return _rate(df["paid"] <= df["total"] + TOL)


def check_stock_nonneg(cdm: ShopCDM) -> float | None:
    if not _has(cdm, "stock_snapshot", "stock_qty"):
        return None
    return _rate(_num(cdm.tables["stock_snapshot"]["stock_qty"]).dropna() >= 0)


def check_lines_have_product(cdm: ShopCDM) -> float | None:
    ln = cdm.tables["order_lines"]
    if ln.empty:
        return None
    return _rate(ln["product_id"].notna())


CHECKS = {
    "lines_sum_vs_goods_total": check_lines_vs_goods_total,
    "line_arith": check_line_arith,
    "qty_base_consistency": check_qty_base,
    "status_mapped": check_status,
    "order_date_present": check_order_date_present,
    "order_date_le_data_end": check_dates,
    "payments_le_total": check_payments,
    "stock_snapshot_nonneg": check_stock_nonneg,
    "lines_have_product": check_lines_have_product,
}


def validate(cdm: ShopCDM) -> dict[str, float | None]:
    return {name: fn(cdm) for name, fn in CHECKS.items()}


# ------------------------------------------------------------------ manifest

def _values(cdm: ShopCDM, table: str, col: str, limit: int = 50) -> list[str]:
    df = cdm.tables.get(table)
    if df is None or col not in df:
        return []
    vc = df[col].dropna().astype(str).str.strip()
    vc = vc[vc != ""].value_counts()
    return list(vc.index[:limit])


def has_order_ids(cdm: ShopCDM) -> bool:
    o = cdm.tables["orders"]
    return bool(len(o)) and not o["order_id"].astype(str).str.startswith("@R").all()


def stock_source(cdm: ShopCDM) -> str | None:
    if _has(cdm, "stock_ledger", "qty_delta_base"):
        return "ledger"
    if _has(cdm, "lots", "qty_in_base") and _has(cdm, "line_lots", "qty_base"):
        return "lots"
    if _has(cdm, "stock_snapshot", "stock_qty"):
        return "snapshot"
    return None


def capabilities(cdm: ShopCDM) -> dict:
    o, ln = cdm.tables["orders"], cdm.tables["order_lines"]
    prod = cdm.tables["products"]
    customer_codes = _has(cdm, "orders", "customer_id")
    named_customers = _has(cdm, "orders", "customer_name")
    ts = "order_ts" in o and pd.to_datetime(o["order_ts"], errors="coerce").dt.hour.fillna(0).ne(0).any()
    drugs = cdm.tables.get("drugs")
    group_from_customers = _has(cdm, "customers", "customer_group")
    return {
        "order_ids": has_order_ids(cdm),
        "order_lines": bool(len(ln)) and _has(cdm, "order_lines", "product_id"),
        "order_ts": bool(ts),
        "order_status": _has(cdm, "orders", "status_raw"),
        "customers": customer_codes or named_customers,
        "customer_codes": customer_codes,
        "customers_table": _has(cdm, "customers"),
        "customer_group": group_from_customers,
        "customer_gender": _has(cdm, "customers", "gender"),
        "customer_address": _has(cdm, "customers", "address"),
        "customer_birthday": _has(cdm, "customers", "birthday"),
        "payment_method": _has(cdm, "orders", "payment_method") or _has(cdm, "payments", "method"),
        "channel": _has(cdm, "orders", "channel"),
        "payments": _has(cdm, "payments", "amount"),
        "debt": _has(cdm, "orders", "debt") or _has(cdm, "orders", "paid") or _has(cdm, "payments", "amount"),
        "debt_terms": _has(cdm, "debt_terms"),
        "line_cost": _has(cdm, "order_lines", "sale_cost"),
        "catalog_cost": _has(cdm, "products", "cost_price"),
        "list_price": _has(cdm, "products", "list_price"),
        "unit_price": _has(cdm, "order_lines", "unit_price"),
        "line_discount": _has(cdm, "order_lines", "line_discount"),
        "order_discount": _has(cdm, "orders", "order_discount"),
        "shipping_fee": _has(cdm, "orders", "shipping_fee"),
        "vat": _has(cdm, "orders", "vat"),
        "product_group": _has(cdm, "products", "group"),
        "item_type": _has(cdm, "products", "item_type"),
        "purchases": _has(cdm, "purchases") or _has(cdm, "purchase_lines"),
        "purchase_lines": _has(cdm, "purchase_lines"),
        "suppliers": _has(cdm, "purchases", "supplier_name") or _has(cdm, "purchases", "supplier_id")
                     or _has(cdm, "purchase_lines", "supplier_name"),
        "lots": _has(cdm, "lots"),
        "expiry": _has(cdm, "lots", "expiry") or _has(cdm, "purchase_lines", "expiry"),
        "stock_snapshot": _has(cdm, "stock_snapshot"),
        "stock_ledger": _has(cdm, "stock_ledger"),
        "stock_source": stock_source(cdm),
        "price_history": _has(cdm, "price_history"),
        "unit_conversions": bool(len(cdm.tables["unit_conversions"])),
        "expenses": _has(cdm, "expenses"),
        "staff": _has(cdm, "orders", "staff_id") or _has(cdm, "staff"),
        "branches": _has(cdm, "orders", "branch_id") or _has(cdm, "branches"),
        "shifts": _has(cdm, "orders", "shift_id"),
        "deliveries": _has(cdm, "deliveries"),
        "dining": _has(cdm, "dining"),
        "returns_table": _has(cdm, "returns"),
        "promotions": _has(cdm, "orders", "promo_id"),
        "prescription": drugs is not None and "is_rx" in drugs and drugs["is_rx"].notna().any(),
        "active_ingredient": drugs is not None and "ingredient" in drugs and drugs["ingredient"].notna().any(),
        "service_fee_lines": bool(ln["is_service_fee"].any()) if "is_service_fee" in ln else False,
        "size_labels": bool(prod["name"].dropna().str.contains(r"\((?:M|L)\)\s*$", case=False, regex=True).any()),
    }


def build_manifest(cdm: ShopCDM, checks: dict | None = None) -> dict:
    checks = validate(cdm) if checks is None else checks
    o = cdm.tables["orders"]
    status_counts = o["status"].value_counts(dropna=False).to_dict() if "status" in o else {}
    groups = _values(cdm, "products", "group")
    return {
        "business_id": cdm.business_id,
        "data_start": cdm.data_start.isoformat() if cdm.data_start else None,
        "data_end": cdm.data_end.isoformat() if cdm.data_end else None,
        "n_orders": int(len(o)),
        "n_lines": int(len(cdm.tables["order_lines"])),
        "n_products": int(len(cdm.tables["products"])),
        "tables": sorted(k for k, v in cdm.tables.items() if v is not None and len(v)),
        "capabilities": capabilities(cdm),
        "enums": {
            "status_raw": _values(cdm, "orders", "status_raw"),
            "payment_method_raw": _values(cdm, "orders", "payment_method_raw") or _values(cdm, "payments", "method_raw"),
            "channel": _values(cdm, "orders", "channel"),
            "customer_group": _values(cdm, "customers", "customer_group"),
            "product_group": groups,
            "product_group_keys": sorted({name_key(g) for g in groups}),
            "item_type": _values(cdm, "products", "item_type"),
            "expense_category": _values(cdm, "expenses", "category"),
            "base_unit": _values(cdm, "products", "base_unit"),
            "units": sorted(set(_values(cdm, "order_lines", "unit", 200)) | set(_values(cdm, "unit_conversions", "unit", 200))),
        },
        "status_counts": {str(k): int(v) for k, v in status_counts.items()},
        "validation": checks,
        "notes": list(cdm.notes),
    }


def min_score(checks: dict) -> float:
    vals = [v for v in checks.values() if v is not None]
    return min(vals) if vals else 1.0
