"""Regex / keyword parser: question -> candidate QueryPlans.

Used (1) to label gold plans on train by execution matching (scripts/label_plans.py) and (2) as a cross-check of
the LLM parser at inference. It returns several candidates, most likely first; it never computes dates itself
(periods are expressions resolved by qa/periods.py).
"""
from __future__ import annotations

import datetime as dt
import re

from ..ingest.normalize import name_key, person_key
from .normalize import base_text, normalize_question, strip_accents

DATE = r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?"
MY = r"(\d{1,2})(?: ?/ ?| nam )(\d{4})"
MONTH = re.compile(rf"thang {MY}")
MONTH_NOYEAR = re.compile(r"thang (\d{1,2})\b(?! ?/| nam \d)")
QUARTER = re.compile(rf"quy (\d)(?: ?/ ?| nam )(\d{{4}})")
QUARTER_NOYEAR = re.compile(r"quy (\d)\b(?! ?/| nam \d)")
RANGE = re.compile(rf"tu (?:ngay )?{DATE},? (?:den|toi|-) (?:het )?(?:ngay )?{DATE}")
MONTH_RANGE = re.compile(rf"tu thang {MY},? (?:den|toi|-) (?:het )?thang {MY}")
DAY = re.compile(rf"(?:ngay|hom|bua) {DATE}")
FULL_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
BARE_MONTH = re.compile(r"(?<![/\d])(\d{1,2}) ?/ ?(\d{4})\b")
LAST_N = re.compile(r"(\d+) ngay (?:gan (?:nhat|day)|qua|vua qua|vua roi|lien gan nhat|cuoi|tro lai)")
MONTHS_ENDING = re.compile(rf"(\d+) thang (?:lien (?:nhau|tiep) )?(?:ket thuc|cuoi cung|den het|toi het|tinh den)\s*(?:o |vao |la |bang |tai )?thang {MY}")
TET = re.compile(r"tet(?: am lich| nguyen dan| am)?(?: nam)? (\d{4})")
BEFORE_TET = re.compile(r"(\d+) ngay (?:ngay )?(?:lien )?truoc tet")
N_DAYS_FROM = re.compile(rf"(\d+) ngay (?:ke )?tu (?:ngay )?{DATE}")
N_DAYS_FROM_THAT = re.compile(r"(\d+) ngay (?:ke )?tu (?:ngay )?(?:do|tang gia|doi gia|len gia|ap dung)")
NEXT_N = re.compile(r"(\d+) ngay toi")
UNITS = (r"lon|chai|thung|ly|coc|hop|goi|vien|cai|bao|cay|kg|m3|cuon|bich|tui|vi|tuyp|lo|khoi|xe|bo|tam|thien|"
         r"met|m|binh|can|ket|loc|day|phan|suat|dia|to|cuc|ong|chiec|soi|tan|thanh|mieng|qua|trai|bao|hu|vi|lit|"
         r"cap|doi|tho|bo|xe 4m3|xe 5m3|m2")


def _d(dd, mm, yy, as_of: dt.date) -> str:
    y = int(yy) if yy else (as_of.year if dt.date(as_of.year, int(mm), 1) <= as_of else as_of.year - 1)
    return dt.date(y, int(mm), int(dd)).isoformat()


def parse_period(s: str, as_of: dt.date) -> tuple[dict | None, dict | None]:
    """(main period, compare period). `s` is normalized text."""
    cmp = None
    if re.search(r"cung (ky|thang|quy) (cua )?nam (truoc|ngoai)|nam (truoc|ngoai) cung (ky|thang)", s):
        cmp = "same_period_last_year"
    elif re.search(r"so (voi|vs|sanh)|hon hay kem|tang hay giam|thay doi|tang giam|tang truong|chenh", s):
        cmp = "prev_period"

    state = bool(re.search(r"(den|toi) (het|cuoi)|tinh den|tinh toi|cuoi ngay|het ngay|het hom nay|hien (tai|gio|con)|"
                           r"con (no|ton|lai)|dang no|con thieu|ton kho|trong kho", s))

    t = TET.search(s)
    if not t and re.search(r"\btet\b", s):
        # "Tết năm nay so với Tết năm ngoái": the year of this Tết is the lunar year of today
        this = as_of.year
        if re.search(r"tet (nam )?nay|dip tet nay", s) and re.search(r"tet (nam )?(truoc|ngoai)", s):
            return {"kind": "tet", "y": this}, {"kind": "tet", "y": this - 1}
        if re.search(r"tet (nam )?(truoc|ngoai)", s):
            return {"kind": "tet", "y": this - 1}, None
        if re.search(r"tet (nam )?nay|\btet\b", s):
            m = BEFORE_TET.search(s)
            return {"kind": "tet", "y": this}, ({"kind": "before_tet", "y": this, "n": int(m.group(1))} if m else
                                                ({"kind": "before_tet", "y": this} if cmp else None))
    if t:
        y = int(t.group(1))
        m = BEFORE_TET.search(s)
        if m:
            return {"kind": "tet", "y": y}, {"kind": "before_tet", "y": y, "n": int(m.group(1))}
        return {"kind": "tet", "y": y}, ({"kind": "before_tet", "y": y} if cmp else None)
    if (m := MONTHS_ENDING.search(s)):
        return {"kind": "months_ending_at", "count": int(m.group(1)), "m": int(m.group(2)), "y": int(m.group(3))}, None
    if (m := MONTH_RANGE.search(s)):
        return {"kind": "month_range", "from": {"m": int(m.group(1)), "y": int(m.group(2))},
                "to": {"m": int(m.group(3)), "y": int(m.group(4))}}, None
    nd = N_DAYS_FROM.search(s)
    if nd:
        d, n = _d(nd.group(2), nd.group(3), nd.group(4), as_of), int(nd.group(1))
        return {"kind": "n_days_from", "date": d, "n": n}, {"kind": "n_days_before", "date": d, "n": n}
    nt = N_DAYS_FROM_THAT.search(s)
    if nt and (dm := DAY.search(s) or re.search(rf"\b{DATE}\b", s)):
        d, n = _d(*dm.group(1, 2, 3), as_of), int(nt.group(1))
        return {"kind": "n_days_from", "date": d, "n": n}, {"kind": "n_days_before", "date": d, "n": n}

    main = None
    months = MONTH.findall(s)
    if (m := re.search(rf"tu (?:nay|hom nay) (?:den|toi) (?:het )?(?:ngay )?{DATE}", s)):
        return {"kind": "range", "from": as_of.isoformat(), "to": _d(*m.group(1, 2, 3), as_of)}, None
    if (m := RANGE.search(s)):
        main = {"kind": "range", "from": _d(*m.group(1, 2, 3), as_of), "to": _d(*m.group(4, 5, 6), as_of)}
    elif (m := NEXT_N.search(s)):
        n = int(m.group(1))
        main = {"kind": "n_days_from", "date": as_of.isoformat(), "n": n + 1}
    elif re.search(r"(tu )?dau thang (nay )?(den|toi) (het )?(hom )?nay|thang nay", s):
        main = {"kind": "this_month_to_date"}
    elif re.search(r"(tu )?dau nam|nam nay|1/1 den het hom nay", s):
        main = {"kind": "ytd"}
    elif len(BARE_MONTH.findall(s)) >= 2 and not cmp and not FULL_DATE.search(s):
        items = []
        for a, b in BARE_MONTH.findall(s):
            it = {"m": int(a), "y": int(b)}
            if it not in items:
                items.append(it)
        main = {"kind": "month_list", "items": items}
    elif len(months) >= 2 and not cmp:
        main = {"kind": "month_list", "items": [{"m": int(a), "y": int(b)} for a, b in months]}
    elif months:
        main = {"kind": "month", "m": int(months[0][0]), "y": int(months[0][1])}
    elif (m := QUARTER.search(s)):
        main = {"kind": "quarter", "q": int(m.group(1)), "y": int(m.group(2))}
    elif (m := LAST_N.search(s)):
        main = {"kind": "last_n_days", "n": int(m.group(1))}
    elif re.search(r"tuan (truoc|roi|vua roi|qua)", s):
        main = {"kind": "last_week"}
    elif re.search(r"tuan nay", s):
        main = {"kind": "this_week"}
    elif re.search(r"hom qua", s):
        main = {"kind": "yesterday"}
    elif (m := DAY.search(s)):
        main = {"kind": "day", "date": _d(*m.group(1, 2, 3), as_of)}
    elif (m := FULL_DATE.search(s)):
        main = {"kind": "day", "date": _d(*m.group(1, 2, 3), as_of)}
    elif re.search(r"hom nay|ngay nay", s):
        main = {"kind": "today"}
    elif re.search(r"thang truoc|thang roi", s):
        main = {"kind": "last_month"}
    elif (m := MONTH_NOYEAR.search(s)):
        main = {"kind": "month", "m": int(m.group(1))}
    elif (m := QUARTER_NOYEAR.search(s)):
        main = {"kind": "quarter", "q": int(m.group(1))}

    if state and main and main["kind"] in ("day", "today"):
        main = {"kind": "as_of_end_of", "date": main.get("date", "today")}

    compare = None
    if cmp and main:
        if len(months) >= 2 and main["kind"] == "month":
            # "tháng 3/2026 so với tháng 3/2025": the month after "so với" is the base
            compare = {"kind": "month", "m": int(months[1][0]), "y": int(months[1][1])}
            pos_cmp = s.find("so ")
            first_pos = s.find(f"thang {months[0][0]}")
            if 0 <= pos_cmp < first_pos:      # "so với tháng 3/2025, tháng 3/2026 ..." – base comes first
                main, compare = {"kind": "month", "m": int(months[1][0]), "y": int(months[1][1])}, \
                    {"kind": "month", "m": int(months[0][0]), "y": int(months[0][1])}
        elif main["kind"] == "this_month_to_date" and cmp == "prev_period":
            compare = {"kind": "prev_month_same_days"}
        else:
            compare = {"kind": cmp, "of": main}
    return main, compare


# ------------------------------------------------------------------ entities

class Lexicon:
    """Accent-free name keys of a shop's products, groups, customers… for substring lookup in questions."""

    def __init__(self, store):
        self.products: dict[str, str] = {}
        for pid, name, variants in zip(store.products["product_id"], store.products["name"], store.products["name_variants"]):
            for n in [name, *(variants or [])]:
                if isinstance(n, str) and self._k(n):
                    self.products.setdefault(self._k(n), name or n)
            if isinstance(pid, str) and not pid.startswith("@"):
                self.products.setdefault(self._k(pid), name or pid)
        groups = store.products["group"].dropna().unique() if "group" in store.products else []
        self.groups = self._index((g, g) for g in groups if isinstance(g, str))
        self.customers = self._index((v, k) for k, v in store.customer_display.items() if isinstance(v, str))
        for k, v in store.customer_display.items():
            if isinstance(v, str):
                self.customers.setdefault(person_key(v), k)
        st = store.t.get("staff")
        self.staff = self._index(zip(st["staff_name"], st["staff_id"])) if st is not None and "staff_name" in st else {}
        cust = store.t.get("customers")
        cgroups = cust["customer_group"].dropna().unique() if cust is not None and "customer_group" in cust else []
        self.customer_groups = self._index((g, g) for g in cgroups if isinstance(g, str))
        drugs = store.t.get("drugs")
        ings = drugs["ingredient"].dropna().unique() if drugs is not None and "ingredient" in drugs else []
        self.ingredients = self._index((i, i) for i in ings if isinstance(i, str))
        enums = store.manifest.get("enums", {})
        self.units = {self._k(u): u for u in enums.get("units", []) + enums.get("base_unit", []) if isinstance(u, str)}
        self.channels = self._index((c, c) for c in enums.get("channel", []))
        pur = store.t.get("purchases")
        sups = []
        if pur is not None and "supplier_name" in pur:
            sups = list(pur["supplier_name"].dropna().unique())
        self.suppliers = self._index((x, x) for x in sups if isinstance(x, str))

    @staticmethod
    def _k(name: str) -> str:
        return " ".join(strip_accents(name_key(name)).split())

    def _index(self, pairs) -> dict[str, str]:
        out = {}
        for name, val in pairs:
            k = self._k(name)
            if k:
                out.setdefault(k, val)
        return out

    @staticmethod
    def find(table: dict[str, str], s: str) -> list[str]:
        """Longest names occurring in s (word-bounded), longest first, non-overlapping; in order of appearance."""
        s2 = " " + " ".join(re.sub(r"[^a-z0-9 ]+", " ", s).split()) + " "
        hits = []
        for k in sorted(table, key=len, reverse=True):
            i = s2.find(" " + k + " ")
            if i >= 0:
                hits.append((i, k))
                s2 = s2[:i] + " " + "#" * len(k) + " " + s2[i + len(k) + 2:]
        return [table[k] for _, k in sorted(hits)]


def _money(num: str, unit: str | None) -> float:
    if "," in num and "." not in num and len(num.split(",")[-1]) != 3:
        v = float(num.replace(",", "."))
    else:
        v = float(num.replace(".", "").replace(",", ""))
    return v * {"trieu": 1e6, "tr": 1e6, "k": 1e3, "nghin": 1e3, "ngan": 1e3}.get(unit or "", 1)


def _threshold(s: str) -> dict | None:
    m = re.search(r"(it nhat|tu|toi thieu|tren|hon|qua|duoi|nhieu hon|it hon|>=|<=|>|<|o|dat|bang)\s*(\d+(?:[.,]\d+)*)\s*"
                  r"(trieu|tr|k|nghin|ngan|d|dong)?\s*(?:don|lan|bill|hoa don|ngay)?(?: (?:hang )?(?:khac nhau )?(tro len|tro xuong))?", s)
    if not m:
        return None
    word, num, unit, tail = m.groups()
    v = _money(num, unit)
    if tail == "tro len" or word in ("it nhat", "toi thieu", ">="):
        op = "ge"
    elif tail == "tro xuong" or word == "<=":
        op = "le"
    elif word in ("duoi", "it hon", "<"):
        op = "lt"
    elif word in ("tu", "o", "dat", "bang"):
        op = "ge"
    else:
        op = "gt"
    return {"op": op, "value": v}


def _k(s: str) -> int | None:
    m = re.search(r"(?:top|liet ke|cho (?:minh|toi|em)?|ke ra|nhung|bang)\s*(\d+)\b(?! ?/)|\b(\d+) (?:mat hang|san pham|mon|hang|khach|nguoi|thuoc|nha cung cap|loai|sp|best)", s)
    if m:
        return int(m.group(1) or m.group(2))
    return None


def _unit(s: str, lex: "Lexicon | None") -> str | None:
    if lex is not None and lex.units:
        alts = "|".join(re.escape(u) for u in sorted(lex.units, key=len, reverse=True) if u)
        m = re.search(rf"(?:mot|1|moi|bao nhieu|may|so|tinh theo|theo|bang|nhieu|duoc) ({alts})\b(?! nhieu)", s)
        if m:
            return lex.units[m.group(1)]
    m = re.search(rf"(?:mot|1|moi|bao nhieu|may|so|tinh theo|theo|bang|nhieu) ({UNITS})\b(?! nhieu)", s)
    if not m:
        return None
    u = m.group(1)
    return lex.units.get(u, u) if lex is not None else u


UNSUPPORTED = [
    (r"\bnu\b|nam gioi|gioi tinh|khach (nam|nu)|dan ong|phu nu", "customer_gender"),
    (r"le phep|chu dao|thai do|khen|vui ve|niem no|phuc vu (tot|kem)|cham chi", None),
    (r"uong (moi|1|mot) lan|lieu dung|cach dung|tac dung phu|chong chi dinh|nen uong", None),
    (r"thoi tiet|mua (mua|nang)|nhiet do", None),
    (r"dia chi|o dau|nha o|que quan|khach( hang)? (o )?(duong|phuong|quan|khu) ", "customer_address"),
    (r"quy men|tan tam|yeu men|thien cam|tan tinh|nhiet tinh", None),
    (r"\bhuy (vi|do)\b|ly do huy|nguyen nhan huy", None),
    (r"sinh nhat|tuoi khach|bao nhieu tuoi", "customer_birthday"),
    (r"ly do tra|tra (hang )?vi|loi (san pham|hang)|mua nham", "returns_table"),
]


def parse(question: str, as_of, lex: Lexicon | None = None, vocab=None) -> list[dict]:
    as_of = as_of if isinstance(as_of, dt.date) else dt.date.fromisoformat(str(as_of)[:10])
    s = normalize_question(question, vocab)
    raw = base_text(question)          # entity names are looked up before teencode rewriting too ("Total", "Bill")
    try:
        period, compare = parse_period(s, as_of)
    except ValueError:                 # impossible date in the text ("31/02", "13/2025"): leave it to the LLM
        period, compare = None, None
    filters: dict = {}
    if lex is not None:
        prods = Lexicon.find(lex.products, raw) or Lexicon.find(lex.products, s)
        if prods:
            filters["product"] = prods[0]
        cg = re.search(r"khach (?:hang )?(?:thuoc )?nhom (.+)", s)
        if cg:
            g = Lexicon.find(lex.customer_groups, cg.group(1))
            filters["customer_group"] = g[0] if g else cg.group(1).split(" chiem")[0].split(" la ")[0][:30]
        else:
            for text in (raw, s):
                gm = re.search(r"nhom (?:hang )?(.+)", text)
                if gm:
                    g = Lexicon.find(lex.groups, gm.group(1)) or Lexicon.find(lex.groups, "nhom " + gm.group(1))
                    if g:
                        filters["group"] = g[0]
                        break
        cm = Lexicon.find(lex.customers, s)
        if cm and re.search(r"khach|anh|chi|\bco\b|chu|ong|\bba\b|\bai\b", s):
            filters["customer"] = cm[0]
        ing = Lexicon.find(lex.ingredients, s)
        if ing and "hoat chat" in s:
            filters["ingredient"] = ing[0]
            filters.pop("product", None)
        sup = Lexicon.find(lex.suppliers, s)
        if sup:
            filters["supplier"] = sup[0]
    if re.search(r"(khong|hong) ke don|khong can ke don|otc|khong theo don|khong can (don|toa)|khong (can )?(don )?bac si|"
                 r"tru (cac )?(thuoc|hang|mat hang) (phai )?ke don", s):
        filters["rx"] = False
    elif re.search(r"ke don|theo don|phai co don|theo toa|ke toa", s):
        filters["rx"] = True
    if (m := re.search(r"size ([ml])\b", s)) and "product" not in filters:
        filters["size"] = m.group(1).upper()
    both_shifts = re.search(r"ca sang", s) and re.search(r"ca chieu", s)
    if not both_shifts:
        if re.search(r"ca sang", s):
            filters["shift"] = "morning"
        elif re.search(r"ca chieu", s):
            filters["shift"] = "afternoon"
    pays = [] if re.search(r"tra (bot )?no|thu (hoi )?no|no them|chiu them", s) else _find_kw(PAYMENT_KW, s)
    if pays and re.search(r"thanh toan|tra (bang|qua|tien)|hinh thuc|bang|qua|cac don|\bdon\b", s):
        filters["payment_method"] = pays[0]
    chans = _channels(s, lex)
    if chans:
        filters["channel"] = chans[0]

    staff = re.search(r"\b(nv ?\d+)\b", s)
    if staff:
        filters["staff"] = staff.group(1).replace(" ", "").upper()
    elif lex is not None and lex.staff and (sn := Lexicon.find(lex.staff, s)):
        filters["staff"] = sn[0]
        staff = True
    if filters.get("product"):
        # keywords inside the product name ("0,1%", "hộp 30 viên", "Total") must not drive the intent
        s = _mask(s, Lexicon._k(filters["product"]))
    base = {"period": period, "filters": filters}
    if compare:
        base["compare"] = compare
    k = _k(s)
    th = _threshold(s)
    unit = _unit(s, lex)
    cands: list[dict] = []

    def add(intent, **kw):
        p = {"intent": intent, **base, **kw}
        p = {k_: v for k_, v in p.items() if v is not None or k_ == "filters"}
        if p not in cands:
            cands.append(p)
        f = p.get("filters") or {}
        if f.get("product") and (f.get("group") or f.get("ingredient") or f.get("customer")):
            # a product name found inside a group / customer phrase: also try without it
            q = {**p, "filters": {k_: v for k_, v in f.items() if k_ != "product"}}
            if q not in cands:
                cands.append(q)

    def f_without(*keys):
        return {k_: v for k_, v in filters.items() if k_ not in keys}

    item_word = r"(mat hang|san pham|\bmon\b|\bhang\b|\bsp\b|thuoc|\bmat\b|best seller|do uong|nuoc|loai)"
    asc = bool(re.search(r"it nhat|thap nhat|cham nhat|kem nhat", s))
    pct_q = bool(re.search(r"%|phan tram", s))

    # --- unsupported attributes (§7)
    for pat, cap in UNSUPPORTED:
        if re.search(pat, s):
            add("unanswerable", needs=cap, reason=pat)

    # --- debt (§4)
    debt_q = re.search(r"\bno\b|cong no|ghi no|mua chiu|con thieu|chua tra|tra bot|thu hoi", s)
    if debt_q:
        age = re.search(r"(?:qua|hon|tren|lau hon) (\d+) ngay|tuoi (?:no )?(?:qua|tren) (\d+)", s)
        if re.search(r"no them|chiu them|ghi them", s):
            if re.search(r"tra|thu", s):
                add("debt_new_and_paid")
            add("debt_new")
        if re.search(r"tra (bot )?no|thu (hoi )?(duoc )?(tien )?(cong )?no|tra duoc|thu duoc|thu hoi", s) and not re.search(r"no them|chiu them", s):
            add("debt_paid")
        if re.search(r"tuoi no|nhom \d+ ?- ?\d+|0 ?- ?7", s):
            nums = [int(x) for x in re.findall(r"\d+", re.sub(rf"{DATE}", " ", s))]
            add("debt_aging_buckets", buckets=_buckets(s))
        if re.search(r"(bao nhieu|may|so) (khach|nguoi)", s):
            add("debtor_count")
        if re.search(r"nhieu nhat|lon nhat|top|cao nhat", s):
            add("top_debtors", k=k or 3)
            add("top_debtors_list", k=k or 3)
        add("debt_total", age_threshold={"op": "gt", "value": int(age.group(1) or age.group(2))} if age else None)

    # --- stock / lots (§5, §6)
    stock_q = re.search(r"\bton\b|trong kho|con lai|con (bao nhieu|may)|het hang|con hang", s) and not debt_q \
        and not re.search(r"(mat hang|san pham|thuoc) con lai (ban|thu)", s)
    if re.search(r"het han|han dung|han su dung|sap het han|can date", s):
        if re.search(r"tien von|gia tri|bao nhieu tien", s):
            add("expiring_value")
        if re.search(r"(bao nhieu|may|so) (mat hang|san pham|thuoc|loai)", s):
            add("expiring_count")
        if re.search(r"lo .*(gan|som) nhat|gan het han nhat", s) and "product" in filters:
            add("nearest_expiry_lot")
        add("expiring_items")
        add("expiring_count")
    if re.search(r"nhap tru (so )?ban|chenh (lech )?(giua )?nhap va ban|nhap .*tru .*ban", s):
        add("purchase_minus_sales", unit=unit)
    if stock_q:
        if re.search(r"gia tri|gia von|bao nhieu tien|tien hang", s):
            add("stock_value")
        if re.search(r"het hang|ton (bang )?0|khong con", s):
            if re.search(r"(bao nhieu|may|so) (mat hang|san pham|mon|loai)", s):
                add("out_of_stock_count")
            add("out_of_stock_items")
            add("out_of_stock_count")
        if "product" in filters:
            if re.search(r"chan|\ble\b|nguyen", s):
                add("stock_big_unit", unit=unit)
            add("stock_qty", unit=unit)
            add("stock_big_unit", unit=unit)

    # --- purchases (§5)
    if re.search(r"nhap|nha cung cap|ncc", s) and not stock_q:
        if re.search(r"binh quan|trung binh", s) and "product" in filters:
            add("avg_purchase_price", unit=unit)
        if re.search(r"nha cung cap|ncc|tu (cty|cong ty)", s) and re.search(r"nhat|nhieu|cao|lon", s):
            add("top_supplier")
        if "product" in filters and re.search(r"bao nhieu|may|so luong", s) and not re.search(r"tien|gia", s):
            add("purchase_qty", unit=unit)
        add("purchase_total")

    # --- profit
    if re.search(r"lai rong|loi nhuan rong|tru (het )?chi phi|con lai bao nhieu", s):
        add("net_profit")
    if re.search(r"lai gop|loi gop|loi nhuan gop|tien lai|tien loi", s) and not re.search(r"nhat", s):
        add("gross_profit")
    if re.search(r"nhan vien|\bnv\b|nguoi ban|thu ngan", s) and re.search(r"gioi|nhat|nhieu|cao", s) and not staff:
        add("best_staff")
    if re.search(r"dot (giao|hang)|chuyen (giao|hang|xe)|xe .*giao|giao .*dot", s):
        add("delivery_trips")

    # --- price increase effect (§5)
    if re.search(r"tang gia|doi gia|len gia|tang len", s) and period and period["kind"] == "n_days_from":
        add("item_qty_change_pct")
        add("revenue_change_pct")
    elif re.search(r"tang gia|doi gia|len gia", s) and not period and "product" in filters:
        # "kể từ khi X lên giá 44.000đ, 14 ngày đầu …": the date comes from the price list (§5)
        nm = re.search(r"(\d+) ngay", s)
        pm = re.search(r"gia (?:len |tu [\d.,]+ ?(?:d|dong)? len )?(\d[\d.,]*)\s*(trieu|tr|k|nghin|ngan|d|dong)?", s)
        if nm and pm:
            base.pop("period", None)
            add("item_qty_change_pct", price_event={"price": _money(pm.group(1), pm.group(2)), "n": int(nm.group(1))})

    # --- cancellations (§1)
    if re.search(r"ti le (don )?(bi )?huy|ti le huy|phan tram (so )?don (bi )?huy|% don (bi )?huy|don (bi )?huy chiem", s):
        add("cancel_rate")
    if re.search(r"\bhuy\b", s) and re.search(r"(so|bao nhieu|may|dem) (don|bill|hoa don)|don .*\bhuy\b|\bhuy\b.*don", s):
        add("cancel_count")

    if re.search(r"(ngay|hom) nao", s):
        add("best_day", metric="orders" if re.search(r"(nhieu|it) don", s) else "revenue", order="asc" if asc else None)
    if re.search(r"thang nao", s):
        add("best_month", order="asc" if asc else None)
    if re.search(r"trung binh|binh quan", s) and re.search(r"\bdon\b|bill|order|hoa don", s) and not re.search(r"nhap", s):
        add("avg_order_value")

    # shift comparison: ca chiều vs ca sáng (§2: base is the morning shift)
    if both_shifts:
        cf = {**filters, "shift": "morning"}
        f2 = {**filters, "shift": "afternoon"}
        b2 = {**base, "filters": f2, "compare": None}
        orders_q = re.search(r"so (don|bill|hoa don)|bao nhieu don|luong don", s)
        names = (("order_count_change_pct",) if orders_q else ()) + (("revenue_change_pct",) if pct_q else ("revenue_diff",))
        for intent_ in names:
            p = {"intent": intent_, **{k_: v for k_, v in b2.items() if v is not None}, "compare_filters": cf}
            cands.append(p)

    share_filter = any(filters.get(x) not in (None, "") for x in ("group", "rx", "payment_method", "product", "size",
                                                                     "ingredient", "channel", "customer_group", "shift"))
    if re.search(r"chiem|ti trong|phan tram|%|ti le", s) and share_filter and not compare and not re.search(r"\bhuy\b", s):
        add("revenue_share")
    if compare and pct_q:
        if re.search(r"so don|bao nhieu don|luong don|don hang", s):
            add("order_count_change_pct")
        if re.search(r"so luong|so (ly|chai|lon|goi|hop|cai)|ban (duoc )?nhieu hay it", s):
            add("item_qty_change_pct")
        add("revenue_change_pct")
    if compare and not pct_q:
        add("revenue_diff")

    if re.search(r"ban chay|chay nhat|ban nhieu nhat|ban duoc nhieu nhat|hot nhat|ban it nhat|ban cham|best seller|loi nhat|"
                 r"loi nhuan (gop )?(lon|cao|nhieu) nhat|"
                 r"lai (gop )?(ca thang )?(cao|nhieu|lon) nhat|doanh thu cao nhat|nhieu tien nhat|thu (ve )?nhieu nhat", s) \
            and re.search(item_word, s) and not re.search(r"khach|\bai\b", s):
        metric = "gross_profit" if re.search(r"loi|lai", s) else (
            "revenue" if re.search(r"doanh thu|tien", s) and not re.search(r"ban chay|chay nhat", s) else "qty_base")
        order = "asc" if asc else None
        if k or re.search(r"liet ke|nhung|top|cac", s):
            add("top_items", k=k or 5, metric=metric, order=order)
        add("best_item", metric=metric, order=order)
        if k is None:
            add("top_items", k=5, metric=metric, order=order)
    cust_q = re.search(r"khach|nguoi mua|\bai\b", s)
    if cust_q and re.search(r"nhieu (tien )?nhat|chi tieu|mua nhieu|top|cao nhat|lon nhat", s) and not debt_q:
        metric = "orders" if re.search(r"nhieu don|so don|nhieu lan", s) else "revenue"
        if k or re.search(r"liet ke|nhung|top|cac", s):
            add("top_customers", k=k or 5, metric=metric)
        add("best_customer", metric=metric)
        if k is None:
            add("top_customers", k=3, metric=metric)
    if re.search(r"(bao nhieu|may|so|dem|nhieu)( %| phan tram)? (khach|nguoi)", s) and not debt_q:
        if pct_q:
            add("customer_share", threshold=th)
        add("customer_count", threshold=th if re.search(r"\d+ (don|lan|bill)", s) else None)
    if re.search(r"(bao nhieu|may|so|nhieu) ngay", s) and th:
        add("days_meeting_threshold", threshold=th)
    chain = re.search(r"cao hon thang [\d/ ]+ va thang [\d/ ]+ cao hon", s)
    if re.search(r"tang (dan|lien tuc|deu)|luon (cao|tang)|thang sau .*(cao|hon)", s) or chain:
        add("trend_increasing")
    if not chain and (m := re.search(r"co phai (?:la )?thang (\d{1,2}) ?/ ?(\d{4}) (cao|thap|lon|nho|nhieu|it) hon", s)):
        # "có phải tháng 10/2025 cao hơn tháng 9/2025 và tháng 11/2025": target vs every other listed month
        add("month_is_extreme", target={"m": int(m.group(1)), "y": int(m.group(2))},
            order="asc" if m.group(3) in ("thap", "nho", "it") else None)
    if re.search(r"gia ban|ban (voi )?gia|gia bao nhieu|gia (la )?bao nhieu|gia mot|bao nhieu (tien )?mot", s) and "product" in filters \
            and not re.search(r"nhap", s):
        add("price_on_day", unit=unit)

    # items: unsold, counted by orders
    if re.search(r"(bi|hang|mat hang|san pham|mon|sp|thuoc) e\b|\be han\b|khong ban (duoc|ra)|chua ban|khong ai mua|"
                 r"ban khong (duoc|dc)|khong co (don|ai)", s) \
            and re.search(r"mat hang|san pham|mon|hang|loai|sp|thuoc", s):
        if re.search(r"liet ke|nhung|nao|ten", s) and not re.search(r"bao nhieu|may", s):
            add("unsold_items_list")
        add("unsold_items")
    if re.search(r"(\d+) (don|bill|hoa don)(?: hang)?(?: khac nhau)?|(it nhat|toi thieu|>=|tu) \d+ (don|bill)", s) \
            and re.search(r"mat hang|san pham|\bsp\b|mon|loai", s):
        add("item_count_sold", threshold=th)

    if ("product" in filters or filters.get("size") or re.search(r"tinh moi loai|cong (tat ca|moi)", s)) \
            and re.search(r"bao nhieu|may|so luong|\bso\b|nhieu", s) and not re.search(r"tien|doanh thu|gia|%", s):
        add("item_qty", unit=unit)
    if "product" not in filters and not re.search(r"tien|doanh thu|%", s) and (
            (m := re.search(rf"(?:bao nhieu|may|so|duoc|nhieu) ({UNITS})\b(?! nhieu)", s)) or unit):
        add("qty_by_base_unit", unit=unit or (lex.units.get(m.group(1), m.group(1)) if lex else m.group(1)))
        add("item_qty", unit=None)
    if re.search(r"(bao nhieu|may|so|dem|nhieu|tong( cong)?) (don|hoa don|bill|order)|don hang", s) and not re.search(r"\bhuy\b", s):
        order_th = re.search(r"(don|bill).*(tren|hon|tu|duoi|it nhat|dat|>=|<=|>|<)\s*\d|\d.*tro (len|xuong)", s)
        add("order_count", threshold=th if order_th else None)

    # multiple filtered revenues in one question ("tại quầy … qua zalo oa …")
    if len(chans) >= 2:
        add("revenue_multi", filters_list=[{**f_without("channel"), "channel": c} for c in chans])
    if len(pays) >= 2:
        add("revenue_multi", filters_list=[{**f_without("payment_method"), "payment_method": p_} for p_ in pays])
    # no default intent: a question nothing matched gets no plan (abstain / LLM), never a guessed "revenue" (plan/11 G1)
    if re.search(r"doanh thu|ban duoc|thu (ve|duoc)|tien hang|tien ban|nhieu tien|ban ra|kiem duoc", s):
        if period and period["kind"] in ("months_ending_at", "month_list", "month_range"):
            add("revenue_series")
        add("revenue")
    return cands


PAYMENT_KW = [(r"tien mat|tien tuoi|\btm\b", "cash"), (r"chuyen khoan|\bck\b|banking", "transfer"),
              (r"vi dien tu|vi (momo|zalopay|zalo pay)|e ?wallet|\bmomo\b", "ewallet"), (r"\bcod\b|thu ho\b", "cod"),
              (r"quet the|the (tin dung|ngan hang|atm)|\bpos\b", "card"), (r"ghi no|mua chiu", "debt")]
CHANNEL_KW = [(r"tai quay|tai cua hang|truc tiep|mua tai cho|offline", ("store", "tai quay", "tai cua hang", "truc tiep", "offline")),
              (r"zalo( oa)?", ("zalo_oa", "zalo oa", "zalo")),
              (r"(qua |goi )?dien thoai|hotline|goi dien", ("phone", "dien thoai", "hotline")),
              (r"shopee", ("shopee",)), (r"lazada", ("lazada",)), (r"tiktok", ("tiktok", "tiktok shop")),
              (r"facebook|\bfb\b", ("facebook", "fb")), (r"grab", ("grab", "grabfood")), (r"website|\bweb\b", ("website", "web"))]


def _find_kw(table, s: str) -> list:
    """Canonical values of keywords present in s, in order of first appearance."""
    hits = []
    for pat, val in table:
        m = re.search(pat, s)
        if m:
            hits.append((m.start(), val))
    out = []
    for _, v in sorted(hits):
        if v not in out:
            out.append(v)
    return out


def _channels(s: str, lex) -> list:
    """Shop channel values mentioned in s (by synonyms), in order of appearance. A channel the shop does not
    have is kept as its synonym, so the filter matches nothing and the shop check raises unanswerable."""
    found = []
    for pat, syns in CHANNEL_KW:
        m = re.search(pat, s)
        if m:
            found.append((m.start(), syns))
    if not found:
        return []
    shop = {}
    if lex is not None:
        shop = {strip_accents(name_key(v)).replace("_", " "): v for v in lex.channels.values()}
    out = []
    for _, syns in sorted(found):
        v = next((shop[sy.replace("_", " ")] for sy in syns if sy.replace("_", " ") in shop), syns[0])
        if v not in out:
            out.append(v)
    return out


def _mask(s: str, key: str) -> str:
    """Replace an entity name (accent-free key) inside normalized text by a neutral token."""
    toks = key.split()
    if not toks:
        return s
    pat = r"(?<![a-z0-9])" + r"[^a-z0-9]*".join(re.escape(t) for t in toks) + r"(?![a-z0-9])"
    return re.sub(pat, " ENTITY ", s, count=1)


def _buckets(s: str) -> list:
    pairs = re.findall(r"(\d+) ?- ?(\d+) ngay|(\d+) ?- ?(\d+)", s)
    out = []
    for a, b, c_, d in pairs:
        lo, hi = (a, b) if a else (c_, d)
        out.append([int(lo), int(hi)])
    m = re.search(r"(?:tren|qua|hon) (\d+) ngay", s)
    if m:
        out.append([int(m.group(1)) + 1, None])
    return out or [[0, 7], [8, 15], [16, None]]
