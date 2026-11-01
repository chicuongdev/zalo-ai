"""Disk cache of built shops for development loops (Phase A takes 2–40 s per shop).

The key covers the shop's files (name, size, mtime) and the source of the ingest package, so editing either
invalidates the entry. At inference the cache directory lives under /tmp and starts empty.
"""
from __future__ import annotations

import hashlib
import pickle
from pathlib import Path

from . import ingest_business
from .validate import build_manifest

PKG = Path(__file__).resolve().parent
NOT_IN_KEY = {"validate.py", "cache.py"}   # manifest is recomputed on load, so editing checks keeps the cache


def _key(biz_dir: Path) -> str:
    h = hashlib.sha1()
    for p in sorted(biz_dir.iterdir()):
        st = p.stat()
        h.update(f"{p.name}|{st.st_size}|{int(st.st_mtime)}".encode())
    for p in sorted(PKG.glob("*.py")):
        if p.name not in NOT_IN_KEY:
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def load_shop(biz_dir: Path, cache_dir: Path | None = Path("work/cdm")):
    """(cdm, mappings) for a shop, from cache when possible."""
    biz_dir = Path(biz_dir)
    if cache_dir is None:
        return ingest_business(biz_dir)
    path = Path(cache_dir) / f"{biz_dir.name}-{_key(biz_dir)}.pkl"
    if path.exists():
        with open(path, "rb") as f:
            cdm, mappings = pickle.load(f)
        cdm.manifest = build_manifest(cdm)
        return cdm, mappings
    result = ingest_business(biz_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    for old in path.parent.glob(f"{biz_dir.name}-*.pkl"):
        old.unlink()
    with open(path, "wb") as f:
        pickle.dump(result, f, protocol=pickle.HIGHEST_PROTOCOL)
    return result
