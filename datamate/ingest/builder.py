"""A5 — build the canonical data model (CDM) of one shop from mapped tables (plan/thiet_ke/01, 02 §A5).

Output: dict of pandas DataFrames keyed by CDM table name, plus build notes. Column names follow
plan/thiet_ke/01_mo_hinh_du_lieu_chuan.md. Raw spellings are kept (`*_raw`, `name_variants`) so answers can quote
names exactly as written in the data.
"""
from __future__ import annotations

import datetime as dt
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import pandas as pd

from .detect import LogicalTable, source_year
from .mapper import DATE_FIELDS, NUMERIC_FIELDS, TableMapping
from .normalize import is_walk_in, name_key, norm_payment, norm_status, norm_text, status_from_note
from .parsers import parse_bool, parse_datetime, parse_money, parse_qty_unit, strip_accents
from .readme import ReadmeFacts
from .readers import _blank

BOOL_FIELDS = {"is_rx"}
MONEY_INT_FIELDS = {"line_amount", "unit_price", "line_discount", "goods_total", "order_discount", "shipping_fee", "vat", "revenue",
                    "grand_total", "paid", "debt", "list_price", "amount", "total", "new_price", "old_price", "refund",
                    "big_unit_price"}
ORDER_LEVEL = ["order_date", "order_ts", "status", "customer_name", "customer_id",
               # order-level fields a flat sales book may repeat (or write on the first line only) — rulebook §8
               "goods_total", "order_discount", "shipping_fee", "grand_total", "paid", "debt", "payment_method",
               "channel", "staff_id", "customer_group", "customer_phone", "customer_address"]
SERVICE_FEE_KEYS = {name_key("Phí phục vụ")}


@dataclass
class ShopCDM:
    business_id: str
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    data_end: dt.date | None = None
    data_start: dt.date | None = None
    manifest: dict = field(default_factory=dict)


# ------------------------------------------------------------------ extraction

def extract(lt: LogicalTable, m: TableMapping) -> pd.DataFrame:
    """Mapped columns -> typed DataFrame (one column per canonical field)."""
    out: dict[str, list] = {}
    years = [source_year(lt, i) for i in range(len(lt.rows))]
    for fld, col in m.columns.items():
        j = lt.header.index(col)
        raw = [r[j] if j < len(r) else None for r in lt.rows]
        if fld in DATE_FIELDS:
            vals = _memo(lambda kv: parse_datetime(kv[0], kv[1]), list(zip(raw, years)), lambda kv: _blank(kv[0]))
        elif fld == "qty":
            parsed = _memo(parse_qty_unit, raw)
            vals = [p[0] if p else None for p in parsed]
            out["_qty_unit"] = [p[1] if p else None for p in parsed]
        elif fld in NUMERIC_FIELDS:
            vals = _memo(parse_money, raw)
        elif fld in BOOL_FIELDS:
            vals = _memo(parse_bool, raw)
        else:
            vals = _memo(norm_text, raw)
        out[fld] = vals
    df = pd.DataFrame(out)
    df["_src"] = [lt.sources[k] for k in lt.row_source]
    return df


def _memo(fn, values: list, blank=_blank) -> list:
    """Apply a parser once per distinct value (dates and amounts repeat a lot)."""
    cache: dict = {}
    out = []
    for v in values:
        if blank(v):
            out.append(None)
            continue
        k = (type(v), v) if not isinstance(v, tuple) else tuple((type(x), x) for x in v)
        if k not in cache:
            cache[k] = fn(v)
        out.append(cache[k])
    return out


def _round_money(df: pd.DataFrame) -> pd.DataFrame:
    for c in MONEY_INT_FIELDS & set(df.columns):
        df[c] = pd.to_numeric(df[c], errors="coerce").round().astype("Int64")
    return df


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame | None:
    frames = [f for f in frames if f is not None and len(f)]
    return pd.concat(frames, ignore_index=True) if frames else None


# ------------------------------------------------------------------ products & units

class ProductIndex:
    """Resolves product names/codes from every table to one product_id; keeps all spellings."""

    def __init__(self, catalog: pd.DataFrame | None):
        self.by_id: dict[str, dict] = {}
        self.by_key: dict[str, str] = {}
        self.variants: dict[str, Counter] = defaultdict(Counter)
        self.by_plain: dict[str, str | None] = {}     # accent-free key -> id (None when two products share it)
        if catalog is not None:
            for r in catalog.to_dict("records"):
                pid = r.get("product_id") or None
                name = r.get("product_name")
                if not pid and not name:
                    continue
                pid = pid or self._synthetic(name)
                self.by_id[pid] = r
                if name:
                    self.by_key.setdefault(name_key(name), pid)
                    self._plain(name, pid)
                    self.variants[pid][name] += 1

    def _plain(self, name: str, pid: str) -> None:
        k = strip_accents(name_key(name))
        if k in self.by_plain and self.by_plain[k] != pid:
            self.by_plain[k] = None
        else:
            self.by_plain[k] = pid

    @staticmethod
    def _synthetic(name: str) -> str:
        return "@P:" + name_key(name)

    def resolve(self, pid: str | None, name: str | None) -> str | None:
        if pid:
            if name:
                self.variants[pid][name] += 1
                self.by_key.setdefault(name_key(name), pid)
            return pid
        if not name:
            return None
        k = name_key(name)
        pid = self.by_key.get(k)
        if pid is None:
            # §8: spellings that differ only in accents / case / spacing are the same product
            pid = self.by_plain.get(strip_accents(k)) or self._synthetic(name)
            self.by_key[k] = pid
            self._plain(name, pid)
        self.variants[pid][name] += 1
        return pid

    def display_name(self, pid: str) -> str | None:
        cat = self.by_id.get(pid, {}).get("product_name")
        if cat:
            return cat
        v = self.variants.get(pid)
        return v.most_common(1)[0][0] if v else None


def build_conversions(tables: dict[str, list[pd.DataFrame]], readme: ReadmeFacts, products: ProductIndex) -> pd.DataFrame:
    rows = []
    for df in tables.get("unit_conversions", []):
        for r in df.to_dict("records"):
            pid = products.resolve(r.get("product_id"), r.get("product_name"))
            if pid and r.get("big_unit") and r.get("factor"):
                rows.append((pid, r["big_unit"], float(r["factor"]), r.get("base_unit")))
    for name, big, factor, base in readme.conversions:
        pid = products.resolve(None, name)
        rows.append((pid, big, float(factor), base))
    conv = pd.DataFrame(rows, columns=["product_id", "unit", "factor_to_base", "base_unit"])
    conv["unit_key"] = conv["unit"].map(name_key)
    return conv.drop_duplicates(["product_id", "unit_key"])


# ------------------------------------------------------------------ sales

def _is_group_key(df: pd.DataFrame, col: str) -> bool:
    """Blank on some rows, and blank exactly where the order-level columns are blank too (continuation rows)."""
    blank = df[col].isna()
    others = [c for c in ORDER_LEVEL if c in df and c not in ("order_date", "order_ts") and df[c].notna().any()]
    if not others or blank.all():
        return False
    if blank.any():
        # written on the first row of each group only: blank exactly where the order-level columns are blank
        if not 0.05 <= blank.mean() <= 0.9 or blank.iloc[0]:
            return False
        return bool(df.loc[blank, others].isna().all(axis=1).mean() >= 0.95)
    # repeated on every row of the group: consecutive runs of one value, order-level columns constant in a run
    v = df[col].astype(str)
    run = (v != v.shift()).cumsum()
    if run.max() > 0.9 * len(df) or run.max() != v.nunique():
        return False
    multi = run.map(run.value_counts()) > 1
    if not multi.any():
        return False
    # names are spelled differently line by line ("A (09..)", "A - 09.."): one constant order-level column is enough
    const = df[multi].groupby(run[multi])[others].nunique(dropna=True).le(1).mean()
    return bool(const.max() >= 0.95)


def _fill_down_orders(df: pd.DataFrame) -> pd.DataFrame:
    """Rulebook §8: blank cells in the following rows of a group repeat the first row of the group."""
    df = df.copy()
    if "order_id" not in df and "line_no" in df and _is_group_key(df, "line_no"):
        # a "STT" column filled only on the first row of each group is the order number, not a line number
        df = df.rename(columns={"line_no": "order_id"})
    if "order_id" in df and df["order_id"].notna().any():
        df["order_id"] = df["order_id"].ffill()
        cols = [c for c in ORDER_LEVEL if c in df]
        if cols:
            g = df.groupby("order_id", sort=False)
            df[cols] = g[cols].ffill()
            df[cols] = df.groupby("order_id", sort=False)[cols].bfill()
    else:
        df["order_id"] = [f"@R{i}" for i in range(len(df))]   # hand-kept ledger: every row is one record (§8)
    return df


def build_sales(tables: dict[str, list[pd.DataFrame]], products: ProductIndex, conv: pd.DataFrame, notes: list[str]):
    flat = _concat(tables.get("sales_flat", []))
    lines = _concat(tables.get("order_lines", []))
    orders = _concat(tables.get("orders", []))

    if flat is not None:
        flat = _fill_down_orders(flat)
        # identical rows within one order are an export error, counted once (§8)
        key_cols = [c for c in flat.columns if c not in ("_src",)]
        has_ids = not flat["order_id"].astype(str).str.startswith("@R").all()
        if has_ids:
            before = len(flat)
            flat = flat.drop_duplicates(subset=key_cols)
            if before != len(flat):
                notes.append(f"sales_flat: dropped {before - len(flat)} duplicated lines within orders")
        grp = flat.groupby("order_id", sort=False)
        agg = {c: "first" for c in ORDER_LEVEL if c in flat}
        derived = grp.agg(agg).reset_index() if agg else pd.DataFrame({"order_id": flat["order_id"].unique()})
        if has_ids and "note" in flat and flat["note"].notna().any():
            notes_by = grp["note"].agg(lambda s: " | ".join(str(v) for v in s.dropna().unique()))
            derived["note"] = derived["order_id"].map(notes_by)
        orders = derived if orders is None else orders
        line_cols = [c for c in flat.columns if c not in ORDER_LEVEL or c == "status"]
        lines = flat[line_cols].rename(columns={"status": "line_status"}) if lines is None else lines

    if lines is None:
        notes.append("no order lines")
        lines = pd.DataFrame(columns=["order_id", "product_id", "qty", "qty_base", "line_amount"])
    if orders is None:
        orders = pd.DataFrame({"order_id": lines["order_id"].unique()})
    elif "order_lines" in tables and tables.get("orders"):
        # explicit orders table + lines table: drop duplicated lines within an order (§8)
        before = len(lines)
        lines = lines.drop_duplicates(subset=[c for c in lines.columns if c != "_src"])   # identical in every cell
        if before != len(lines):
            notes.append(f"order_lines: dropped {before - len(lines)} duplicated lines")

    # --- orders
    orders = orders.copy()
    if "order_date" not in orders and "order_ts" in orders:
        orders["order_date"] = orders["order_ts"]
    if "order_date" in orders:
        orders["order_date"] = pd.to_datetime(orders["order_date"]).dt.normalize()
    orders["status_raw"] = orders.get("status")
    if "status" in orders:
        orders["status"] = orders["status_raw"].map(norm_status)
    elif "note" in orders and orders["note"].notna().any():
        # rulebook: a book without a status column writes the status in the notes (no mention = completed)
        orders["status"] = orders["note"].map(status_from_note)
        orders["status_raw"] = orders["note"].fillna("")          # the shop records statuses (in its notes)
        notes.append(f"status from notes: {orders['status'].value_counts().to_dict()}")
    else:
        orders["status"] = "completed"
    unknown = orders.loc[orders["status"].isna() & orders["status_raw"].notna(), "status_raw"].unique()
    if len(unknown):
        notes.append(f"unknown status values: {list(unknown)[:10]}")
    if "payment_method" in orders:
        orders["payment_method_raw"] = orders["payment_method"]
        orders["payment_method"] = orders["payment_method"].map(norm_payment)
    name = orders["customer_name"] if "customer_name" in orders else pd.Series([None] * len(orders))
    cid = orders["customer_id"] if "customer_id" in orders else pd.Series([None] * len(orders))
    orders["is_walk_in"] = [(c is None or pd.isna(c)) and is_walk_in(n if isinstance(n, str) else None)
                            for c, n in zip(cid, name)]

    # --- lines
    lines = lines.copy()
    if "unit" not in lines:
        lines["unit"] = None
    if "_qty_unit" in lines:
        lines["unit"] = lines["unit"].fillna(lines["_qty_unit"])
        lines = lines.drop(columns=["_qty_unit"])
    lines = _split_combined_cells(lines, products, notes)
    pid = lines["product_id"] if "product_id" in lines else pd.Series([None] * len(lines))
    pname = lines["product_name"] if "product_name" in lines else pd.Series([None] * len(lines))
    lines["product_name_raw"] = pname
    lines["product_id"] = [products.resolve(a if isinstance(a, str) else None, b if isinstance(b, str) else None)
                           for a, b in zip(pid, pname)]
    if "qty" not in lines and "qty_base" in lines:
        lines["qty"] = lines["qty_base"]
    lines["qty_base"] = _qty_base(lines, conv, products)
    lines["is_service_fee"] = [name_key(products.display_name(p) or "") in SERVICE_FEE_KEYS for p in lines["product_id"]]
    if "line_amount" not in lines and "unit_price" in lines:
        disc = lines["line_discount"].fillna(0) if "line_discount" in lines else 0
        lines["line_amount"] = lines["qty"] * lines["unit_price"] - disc

    # --- returns: status, negative lines, lot returns, return slips (rulebook §1: any return -> whole order out)
    ret = set(orders.loc[orders["status"] == "returned", "order_id"])
    if "line_status" in lines:
        ls = lines["line_status"].map(norm_status)
        ret |= set(lines.loc[ls == "returned", "order_id"])
    ret |= set(lines.loc[lines["qty"].fillna(0) < 0, "order_id"])
    for df in tables.get("line_lots", []):
        if "qty_return_base" in df:
            ret |= set(df.loc[df["qty_return_base"].fillna(0) > 0, "order_id"])
    for df in tables.get("returns", []):
        ret |= set(df["order_id"].dropna())
    orders["has_return"] = orders["order_id"].isin(ret)

    lines = _round_money(lines)
    orders, lines = _split_adjustment_lines(orders, lines, products, notes)
    # order revenue (rulebook §1): sum of line amounts after line discounts; shops without lines record it on the order
    by_order = lines.groupby("order_id")["line_amount"].sum(min_count=1)
    orders["revenue"] = orders["order_id"].map(by_order)
    if "goods_total" in orders:
        orders["revenue"] = orders["revenue"].fillna(pd.to_numeric(orders["goods_total"], errors="coerce"))
    return _round_money(orders), lines


_ADDON = re.compile(r"^(?:(\d+)\s*(?:x\s*)?)?(.+?)\s*\(\s*([\d.,]+\s*(?:đ|d|k|vnd|vnđ)?)\s*\)$", re.I)


def _known_names(lines: pd.DataFrame, products: ProductIndex) -> dict[str, str]:
    """plain name key -> name, for catalog items and items sold on their own line (no lookup side effects)."""
    out = {}
    for pid, r in products.by_id.items():
        if r.get("product_name"):
            out.setdefault(strip_accents(name_key(r["product_name"])), r["product_name"])
    for v in lines["product_name"].dropna().unique():
        if isinstance(v, str) and " + " not in v:
            out.setdefault(strip_accents(name_key(v)), v)
    return out


def _find_known(known: dict[str, str], name: str) -> str | None:
    for cand in (name, f"Topping {name}"):
        hit = known.get(strip_accents(name_key(cand)))
        if hit:
            return hit
    return None


def _split_combined_cells(lines: pd.DataFrame, products: ProductIndex, notes: list[str]) -> pd.DataFrame:
    """Rulebook: an add-on written in the item's cell ("Latte (M) + 2 Trân châu đen (14.000đ)") is a separate
    item sold: its portions (number before the name, default 1) and its money (in brackets, already inside the
    line amount) belong to the add-on, not to the item. Split only when the item and every add-on are known
    items (catalog, or sold on a line of their own) and every add-on has bracketed money, so an item whose own
    name contains '+' is never cut."""
    if "product_name" not in lines or "line_amount" not in lines:
        return lines
    cand = lines["product_name"].map(lambda v: isinstance(v, str) and " + " in v)
    if not cand.any():
        return lines
    known = _known_names(lines, products)
    lines = lines.copy()
    extra, n_split = [], 0
    for idx, row in lines[cand].iterrows():
        parts = [p.strip() for p in row["product_name"].split(" + ")]
        base = _find_known(known, parts[0])
        addons = []
        for p in parts[1:]:
            m = _ADDON.match(p)
            name = _find_known(known, m.group(2).strip()) if m else None
            money = parse_money(m.group(3)) if m else None
            if name is None or money is None:
                addons = None
                break
            addons.append((name, float(m.group(1) or 1), float(money)))
        if not addons or base is None:
            continue
        n_split += 1
        total = pd.to_numeric(pd.Series([row["line_amount"]]), errors="coerce").iloc[0]
        lines.at[idx, "product_name"] = base
        if pd.notna(total):
            lines.at[idx, "line_amount"] = total - sum(a[2] for a in addons)
        for name, qty, money in addons:
            r = row.copy()
            r["product_name"], r["qty"], r["line_amount"], r["unit"] = name, qty, money, None
            if "product_id" in r:
                r["product_id"] = None
            if "unit_price" in r:
                r["unit_price"] = money / qty if qty else None
            for c in ("qty_base", "line_discount"):
                if c in r:
                    r[c] = None
            extra.append(r)
    if not n_split:
        return lines
    notes.append(f"split {n_split} lines with add-ons written in the item cell into {len(extra)} add-on lines")
    return pd.concat([lines, pd.DataFrame(extra)], ignore_index=True)


_ADJ_DISCOUNT = re.compile(r"^(voucher|ma giam gia|giam gia( hoa don| don| ca don)?|chiet khau( hoa don| don)?|"
                           r"khuyen mai( hoa don)?|dung \d+ diem|tru \d+ diem|doi \d+ diem|tru diem|dung diem)\b")
_ADJ_SHIP = re.compile(r"^(phi ship|tien ship|phi giao( hang)?|phi van chuyen|ship)\b")


def _split_adjustment_lines(orders: pd.DataFrame, lines: pd.DataFrame, products: ProductIndex, notes: list[str]):
    """Rows of a sales book that are order-level money, not goods ("Voucher", "Dùng 200 điểm", "Phí ship"):
    rulebook §1 revenue = goods lines only (order discounts not deducted, shipping not included). They have no
    quantity; their amount moves to the order (order_discount as a positive number, shipping_fee)."""
    if lines.empty or "product_name" not in lines:
        return orders, lines
    key = lines["product_name"].map(lambda v: strip_accents(str(v)).lower().strip() if isinstance(v, str) else "")
    key = key.str.replace(r"[^a-z0-9 ]+", " ", regex=True).str.split().str.join(" ")
    no_qty = lines["qty"].isna() | (lines["qty"].fillna(0) == 0)
    disc = key.str.match(_ADJ_DISCOUNT) & no_qty
    ship = key.str.match(_ADJ_SHIP) & no_qty
    if not (disc.any() or ship.any()):
        return orders, lines
    amt = pd.to_numeric(lines["line_amount"], errors="coerce").fillna(0)
    orders = orders.copy()
    for mask, col, sign in ((disc, "order_discount", -1), (ship, "shipping_fee", 1)):
        if mask.any():
            add = (sign * amt[mask]).groupby(lines.loc[mask, "order_id"]).sum()
            base = pd.to_numeric(orders[col], errors="coerce") if col in orders else pd.Series(0, index=orders.index)
            orders[col] = base.fillna(0) + orders["order_id"].map(add).fillna(0)
    notes.append(f"order-level rows moved out of goods lines: {int(disc.sum())} discount, {int(ship.sum())} shipping")
    return orders, lines[~(disc | ship)].copy()


def _qty_base(lines: pd.DataFrame, conv: pd.DataFrame, products: ProductIndex) -> pd.Series:
    given = lines["qty_base"] if "qty_base" in lines else pd.Series([None] * len(lines), index=lines.index)
    fac = {(p, u): f for p, u, f in zip(conv["product_id"], conv["unit_key"], conv["factor_to_base"])}
    base_unit = {pid: name_key(r.get("base_unit") or "") for pid, r in products.by_id.items()}
    out = []
    for g, q, p, u in zip(given, lines["qty"], lines["product_id"], lines["unit"]):
        if g is not None and not pd.isna(g):
            out.append(float(g))
        elif q is None or pd.isna(q):
            out.append(None)
        else:
            uk = name_key(u) if isinstance(u, str) else ""
            f = fac.get((p, uk))
            if f is None and uk and uk == base_unit.get(p):
                f = 1.0
            out.append(float(q) * (f if f else 1.0))
    return pd.Series(out, index=lines.index, dtype="float64")


# ------------------------------------------------------------------ other tables

def _with_products(df: pd.DataFrame, products: ProductIndex) -> pd.DataFrame:
    df = df.copy()
    pid = df["product_id"] if "product_id" in df else pd.Series([None] * len(df), index=df.index)
    name = df["product_name"] if "product_name" in df else pd.Series([None] * len(df), index=df.index)
    df["product_id"] = [products.resolve(a if isinstance(a, str) else None, b if isinstance(b, str) else None)
                        for a, b in zip(pid, name)]
    return df


def build_shop(business_id: str, mapped: list[tuple[LogicalTable, TableMapping]], readme: ReadmeFacts) -> ShopCDM:
    cdm = ShopCDM(business_id, data_end=readme.data_end)
    by_kind: dict[str, list[pd.DataFrame]] = defaultdict(list)
    for lt, m in mapped:
        if m.kind == "extra":
            cdm.notes.append(f"unmapped table {lt.name}")
            continue
        by_kind[m.kind].append(extract(lt, m))

    catalog = _concat(by_kind.get("products", []))
    products = ProductIndex(catalog)
    conv = build_conversions(by_kind, readme, products)
    orders, lines = build_sales(by_kind, products, conv, cdm.notes)
    t = cdm.tables
    t["orders"], t["order_lines"], t["unit_conversions"] = orders, lines, conv

    for kind in ("purchase_lines", "lots", "stock_snapshot", "price_history", "deliveries", "drugs"):
        df = _concat(by_kind.get(kind, []))
        if df is not None:
            t[kind] = _round_money(_with_products(df, products))
    for kind in ("customers", "payments", "purchases", "line_lots", "stock_ledger", "debt_terms", "expenses", "dining",
                 "returns", "staff", "suppliers", "branches"):
        df = _concat(by_kind.get(kind, []))
        if df is not None:
            t[kind] = _round_money(df)
    if "payments" in t and "method" in t["payments"]:
        t["payments"]["method_raw"] = t["payments"]["method"]
        t["payments"]["method"] = t["payments"]["method"].map(norm_payment)
    if "purchase_lines" in t:
        pl = t["purchase_lines"]
        if "amount" not in pl and "unit_cost" in pl:
            pl["amount"] = (pl["qty"] * pl["unit_cost"]).round().astype("Int64")
        if "purchases" not in t and "receipt_date" in pl:
            # hand-kept purchase ledger: receipt header derived from its lines
            agg = {c: "first" for c in ("receipt_date", "supplier_name", "note") if c in pl}
            hdr = pl.groupby("receipt_id", sort=False).agg(agg).reset_index()
            hdr["total"] = pl.groupby("receipt_id", sort=False)["amount"].sum().values
            t["purchases"] = hdr

    # products table: catalog + every product seen in sales/stock
    prod = pd.DataFrame([{"product_id": pid, **{k: v for k, v in r.items() if k != "_src"}}
                         for pid, r in products.by_id.items()]) if products.by_id else pd.DataFrame(columns=["product_id"])
    seen = set(lines["product_id"].dropna()) | set(products.variants)
    extra = [p for p in seen if p not in products.by_id]
    if extra:
        prod = pd.concat([prod, pd.DataFrame({"product_id": extra})], ignore_index=True)
    prod["name"] = prod["product_id"].map(products.display_name)
    prod["name_variants"] = prod["product_id"].map(lambda p: sorted(products.variants.get(p, {})))
    if "product_group" in lines and lines["product_group"].notna().any():
        # group written on the sale lines (no catalog group): most frequent group of each product
        line_group = (lines.dropna(subset=["product_id", "product_group"]).groupby("product_id")["product_group"]
                      .agg(lambda s: s.value_counts().index[0]))
        from_lines = prod["product_id"].map(line_group)
        prod["group"] = prod["group"].fillna(from_lines) if "group" in prod else from_lines
    t["products"] = _round_money(prod)

    if "order_date" in orders and orders["order_date"].notna().any():
        cdm.data_start = orders["order_date"].min().date()
        last = orders["order_date"].max().date()
        if cdm.data_end is None:
            cdm.data_end = last
        elif last != cdm.data_end:
            cdm.notes.append(f"README data_end {cdm.data_end} != last order date {last}")
    return cdm
