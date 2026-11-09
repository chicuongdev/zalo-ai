"""ShopStore — the CDM of one shop prepared for the semantic library (plan/thiet_ke/03 §2).

Pandas is used directly (tables are ≤ 200k rows); the DuckDB layer in the design is only needed by the
code-generation fallback and can be added there.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from functools import cached_property

import pandas as pd

from ..calendar import Calendar
from ..ingest.builder import ShopCDM
from ..ingest.normalize import name_key, person_key


@dataclass(frozen=True)
class RuleConfig:
    """Rulebook parameters (defaults = train rulebook). Private rulebook diffs change these, not the code."""
    exclude_partial_return_orders: bool = True
    count_delivering_as_sale: bool = True
    morning: tuple[int, int] = (6, 13)          # hours, inclusive: 06:00–13:59
    afternoon: tuple[int, int] = (14, 21)       # 14:00–21:59
    pct_decimals: int = 2
    cod_is_cash: bool = False
    walk_in_belongs_to_group: bool = False


class ShopStore:
    def __init__(self, cdm: ShopCDM, cal: Calendar | None = None, cfg: RuleConfig = RuleConfig()):
        self.cdm, self.cal, self.cfg = cdm, cal, cfg
        self.t = cdm.tables
        self.manifest = cdm.manifest
        self.caps = cdm.manifest.get("capabilities", {}) if cdm.manifest else {}
        self.data_start = cdm.data_start
        self.data_end = cdm.data_end

    # ------------------------------------------------------------------ orders & lines
    @cached_property
    def orders(self) -> pd.DataFrame:
        o = self.t["orders"].copy()
        bad = {"cancelled", "returned"} if self.cfg.count_delivering_as_sale else {"cancelled", "returned", "delivering"}
        o["valid"] = ~o["status"].isin(bad) & ~o["has_return"]
        if "order_ts" in o:
            ts = pd.to_datetime(o["order_ts"], errors="coerce")
            o["hour"] = ts.dt.hour.where(ts.notna())
        o["ckey"] = self._customer_keys(o)
        return o

    @cached_property
    def lines(self) -> pd.DataFrame:
        """Order lines joined with the order-level fields used for filtering."""
        ln = self.t["order_lines"]
        cols = [c for c in ("order_id", "order_date", "valid", "status", "ckey", "hour", "payment_method", "channel",
                            "customer_id", "customer_name", "staff_id", "branch_id", "customer_group", "is_walk_in")
                if c in self.orders]
        o = self.orders[cols].drop_duplicates("order_id")
        drop = [c for c in cols if c != "order_id" and c in ln]
        df = ln.drop(columns=drop).merge(o, on="order_id", how="left")
        prod = self.products.set_index("product_id")
        for c in ("group", "cost_price", "item_type"):
            if c in prod:
                df[f"p_{c}"] = df["product_id"].map(prod[c])
        df["p_name"] = df["product_id"].map(prod["name"])
        df["p_base_unit"] = df["product_id"].map(self.base_units)
        return df

    @cached_property
    def base_units(self) -> dict:
        """§10 base unit per product: catalog, else conversion table, else the line unit that has no conversion."""
        out = {}
        prod = self.products
        if "base_unit" in prod:
            out.update({p: u for p, u in zip(prod["product_id"], prod["base_unit"]) if isinstance(u, str) and u.strip()})
        conv = self.t["unit_conversions"]
        big = set(zip(conv["product_id"], conv["unit_key"]))
        if "base_unit" in conv:
            for p, u in zip(conv["product_id"], conv["base_unit"]):
                if isinstance(u, str) and u.strip():
                    out.setdefault(p, u)
        ln = self.t["order_lines"]
        if "unit" in ln:
            small = ln[["product_id", "unit"]].dropna()
            keep = [(p, name_key(u)) not in big for p, u in zip(small["product_id"], small["unit"])]
            small = small.loc[pd.Series(keep, index=small.index, dtype=bool)]
            if len(small):
                for p, u in small.groupby("product_id")["unit"].agg(lambda x: x.value_counts().index[0]).items():
                    out.setdefault(p, u)
        return out

    @cached_property
    def products(self) -> pd.DataFrame:
        return self.t["products"]

    def _customer_keys(self, o: pd.DataFrame) -> pd.Series:
        """Rulebook §3: by customer code when the shop has codes, else by name (spelling-insensitive); walk-ins → None."""
        if self.caps.get("customer_codes") or ("customer_id" in o and o["customer_id"].notna().any()):
            return o["customer_id"].where(o["customer_id"].notna(), None)
        if "customer_name" not in o:
            return pd.Series([None] * len(o), index=o.index)
        keys = [None if w or not isinstance(n, str) else person_key(n) for n, w in zip(o["customer_name"], o["is_walk_in"])]
        return pd.Series(keys, index=o.index)

    @cached_property
    def customer_display(self) -> dict:
        """ckey -> name as written (most frequent spelling)."""
        o = self.orders
        out = {}
        if "customers" in self.t and "customer_id" in self.t["customers"]:
            c = self.t["customers"]
            out.update({k: v for k, v in zip(c["customer_id"], c.get("customer_name", c["customer_id"])) if isinstance(k, str)})
        if "customer_name" in o:
            names = o.dropna(subset=["ckey", "customer_name"]).groupby("ckey")["customer_name"].agg(
                lambda s: s.value_counts().index[0])
            for k, v in names.items():
                out.setdefault(k, v)
        return out

    @cached_property
    def product_keys(self) -> dict:
        """name_key of every product spelling -> product_id."""
        out = {}
        for pid, name, variants in zip(self.products["product_id"], self.products["name"], self.products["name_variants"]):
            for n in [name, *(variants or [])]:
                if isinstance(n, str):
                    out.setdefault(name_key(n), pid)
        return out

    def product_code(self, pid: str) -> str:
        """Sort key for ties (§9: by code; no code → by name)."""
        if isinstance(pid, str) and not pid.startswith("@P:"):
            return pid
        return "~" + (self.product_name(pid) or "")

    def product_name(self, pid) -> str | None:
        r = self.products.loc[self.products["product_id"] == pid, "name"]
        return r.iloc[0] if len(r) else None

    @staticmethod
    def in_span(dates: pd.Series, span) -> pd.Series:
        return (dates >= pd.Timestamp(span.start)) & (dates <= pd.Timestamp(span.end))

    @staticmethod
    def as_ts(d: dt.date) -> pd.Timestamp:
        return pd.Timestamp(d)
