"""A4 — decide the kind of each logical table and map its columns to canonical fields (plan/thiet_ke/02 §A4).

Deterministic tiers: README column description -> header synonym -> fuzzy header. Value types veto impossible
matches (a date field must hold dates, an amount field numbers). Tables that fit no kind are kept as `extra`.
An LLM tier for low-confidence tables will plug in later (G3).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .detect import LogicalTable
from .parsers import is_code, parse_date, parse_money, parse_qty_unit
from .readme import ReadmeFacts
from .readers import _blank
from .schema import IGNORE_DESCRIPTIONS, IGNORE_HEADERS, KINDS, norm_header

DATE_FIELDS = {"order_date", "receipt_date", "pay_ts", "order_ts", "expiry", "effective_date", "delivery_date",
               "due_date", "expense_date", "return_ts", "ts", "birthday", "start_date", "end_date", "opened"}
NUMERIC_FIELDS = {"qty_base", "unit_price", "line_discount", "line_amount", "sale_cost", "goods_total", "order_discount",
                  "shipping_fee", "vat", "grand_total", "paid", "debt", "list_price", "cost_price", "factor", "amount",
                  "total", "unit_cost", "qty_in_base", "unit_cost_base", "qty_return_base", "stock_qty", "balance_after",
                  "qty_delta_base", "new_price", "old_price", "days_allowed", "trip_no", "guests", "refund", "line_no",
                  "big_unit_price", "vat_rate"}
QTY_FIELDS = {"qty"}  # may carry a unit: '2 thùng'
SAMPLE = 400
_SUPPLIER = KINDS["purchase_lines"]["fields"]["supplier_name"]
_CUSTOMER = KINDS["sales_flat"]["fields"]["customer_name"]
FOREIGN = {"sales_flat": _SUPPLIER, "order_lines": _SUPPLIER, "orders": _SUPPLIER,
           "purchase_lines": _CUSTOMER, "purchases": _CUSTOMER}


@dataclass
class ColumnProfile:
    name: str
    desc: str | None
    n: int
    date_rate: float
    num_rate: float
    qty_rate: float
    code_rate: float
    samples: list = field(default_factory=list)


@dataclass
class TableMapping:
    table: str
    kind: str                              # canonical kind or 'extra'
    columns: dict[str, str]                # canonical field -> source column
    score: float
    unmapped: list[str]
    evidence: dict[str, str]               # field -> 'desc' | 'header' | 'fuzzy'
    candidates: list[tuple[str, float]]    # other kinds considered (kind, score)


def profile_columns(lt: LogicalTable, readme: ReadmeFacts) -> list[ColumnProfile]:
    files = [(s.split("#", 1) + [None])[:2] for s in lt.sources]
    out = []
    step = max(1, len(lt.rows) // SAMPLE)
    rows = lt.rows[::step][:SAMPLE]
    for j, name in enumerate(lt.header):
        vals = [r[j] for r in rows if j < len(r) and not _blank(r[j])]
        n = len(vals) or 1
        desc = next((readme.column_desc(f, s, name) for f, s in files if readme.column_desc(f, s, name)), None)
        out.append(ColumnProfile(
            name=name, desc=desc, n=len(vals),
            date_rate=sum(parse_date(v, 2025) is not None for v in vals) / n,
            num_rate=sum(parse_money(v) is not None for v in vals) / n,
            qty_rate=sum(parse_qty_unit(v) is not None for v in vals) / n,
            code_rate=sum(is_code(v) for v in vals) / n,
            samples=vals[:5],
        ))
    return out


def _type_ok(fld: str, p: ColumnProfile) -> bool:
    if p.n == 0:
        return True                       # empty column: no evidence against
    if fld in DATE_FIELDS:
        return p.date_rate >= 0.9
    if fld in NUMERIC_FIELDS:
        return p.num_rate >= 0.9
    if fld in QTY_FIELDS:
        return p.qty_rate >= 0.9
    return True


def _match(fld_spec: dict, p: ColumnProfile) -> tuple[float, str] | None:
    h = norm_header(p.name)
    if p.desc and norm_header(p.desc) in fld_spec["d"]:
        return 1.0, "desc"
    if p.desc:   # README wording varies: a long description starting with a known phrase (>= 3 words)
        dsc = norm_header(p.desc) + " "
        if any(len(d.split()) >= 3 and dsc.startswith(d + " ") for d in fld_spec["d"]):
            return 0.95, "desc"
    if h in fld_spec["h"]:
        return 0.9, "header"
    best = max((fuzz.ratio(h, s) for s in fld_spec["h"]), default=0)
    if best >= 92:
        return 0.6, "fuzzy"
    return None


def _ignored(p: ColumnProfile) -> bool:
    return norm_header(p.name) in IGNORE_HEADERS or (p.desc is not None and norm_header(p.desc) in IGNORE_DESCRIPTIONS) \
        or norm_header(p.name).startswith("col")


def score_kind(kind: str, profiles: list[ColumnProfile]):
    spec = KINDS[kind]
    cands = []
    for p in profiles:
        if _ignored(p):
            continue
        for fld, fs in spec["fields"].items():
            m = _match(fs, p)
            if m and _type_ok(fld, p):
                cands.append((m[0] * fs["w"], m[0], fld, p.name, m[1]))
    cands.sort(key=lambda x: (-x[0], x[3]))
    used_f, used_c, cols, ev, score = set(), set(), {}, {}, 0.0
    for s, _, fld, col, how in cands:
        if fld in used_f or col in used_c:
            continue
        used_f.add(fld)
        used_c.add(col)
        cols[fld] = col
        ev[fld] = how
        score += s
    ok = all(any(f in cols for f in group) for group in spec["need"])
    unmapped = [p.name for p in profiles if p.name not in used_c and not _ignored(p)]
    # a column that is the counterparty of the OTHER direction (supplier in a sales book, customer in a purchase
    # book) contradicts the kind: a purchase book read as sales adds purchases to revenue
    foreign = FOREIGN.get(kind)
    if foreign and any(_match(foreign, p) and p.name in unmapped for p in profiles):
        score -= 5.0
    return ok, score - 0.3 * len(unmapped), cols, ev, unmapped


def map_table(lt: LogicalTable, readme: ReadmeFacts) -> TableMapping:
    profiles = profile_columns(lt, readme)
    results = []
    for kind in KINDS:
        ok, score, cols, ev, unmapped = score_kind(kind, profiles)
        if ok:
            results.append((score, kind, cols, ev, unmapped))
    results.sort(key=lambda x: -x[0])
    if not results:
        return TableMapping(lt.name, "extra", {}, 0.0, [p.name for p in profiles], {}, [])
    score, kind, cols, ev, unmapped = results[0]
    return TableMapping(lt.name, kind, cols, round(score, 2), unmapped, ev, [(k, round(s, 2)) for s, k, *_ in results[1:4]])
