"""B9 — answer formatter: library values -> the submission format (rulebook §9, subject/02.evaluation.json).

Values coming out of pandas are numpy scalars; the submission needs plain JSON numbers / strings / booleans.
"""
from __future__ import annotations

import datetime as dt
import math

import numpy as np


def _plain(x):
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        f = float(x)
        if math.isnan(f) or math.isinf(f):
            raise ValueError("non-finite number")
        return int(f) if f.is_integer() else f
    if isinstance(x, (dt.date, dt.datetime)):
        return x.isoformat()[:10]
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items()}
    return x


def format_answer(qid: str, typ: str, value=None, reason: str | None = None) -> dict:
    """One submission line. Raises ValueError when the value does not fit the type (caller abstains)."""
    if typ == "abstain":
        return {"id": qid, "type": "abstain"}
    if typ == "unanswerable":
        return {"id": qid, "type": "unanswerable", "reason": str(reason or "not in data")[:200]}
    v = _plain(value)
    if typ in ("number", "percent"):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"{typ} needs a number, got {v!r}")
        if typ == "percent":
            v = round(float(v), 2)
            v = int(v) if float(v).is_integer() else v
    elif typ == "boolean":
        if not isinstance(v, bool):
            raise ValueError("boolean needs true/false")
    elif typ == "date":
        if not isinstance(v, str) or len(v) not in (7, 10):
            raise ValueError("date needs YYYY-MM or YYYY-MM-DD")
    elif typ == "string":
        if not isinstance(v, str) or not v.strip():
            raise ValueError("string needs a name")
    elif typ == "list":
        if not isinstance(v, list):
            raise ValueError("list needs a JSON array")
    elif typ == "table":
        if not (isinstance(v, dict) and isinstance(v.get("columns"), list) and isinstance(v.get("rows"), list)):
            raise ValueError("table needs columns + rows")
    else:
        raise ValueError(f"unknown type {typ}")
    return {"id": qid, "type": typ, "answer": v}
