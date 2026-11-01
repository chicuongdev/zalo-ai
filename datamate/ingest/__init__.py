"""Phase A: raw shop files -> canonical data model."""
from __future__ import annotations

from pathlib import Path

from .builder import ShopCDM, build_shop
from .detect import detect_business
from .mapper import map_table
from .readers import read_business
from .readme import parse_readme
from .validate import build_manifest


def ingest_business(biz_dir: Path) -> tuple[ShopCDM, list]:
    """Read, detect, map and build one shop. Returns (cdm, mappings) — mappings kept for reports and logs."""
    biz_dir = Path(biz_dir)
    sheets, readme_text = read_business(biz_dir)
    readme = parse_readme(readme_text)
    mapped = [(lt, map_table(lt, readme)) for lt in detect_business(sheets)]
    cdm = build_shop(biz_dir.name, mapped, readme)
    cdm.manifest = build_manifest(cdm)
    return cdm, [m for _, m in mapped]
