"""Zip the code (+ gold plans) for upload as a PRIVATE Kaggle dataset.

    python scripts/make_kaggle_bundle.py            -> dist/datamate_code.zip

Upload it on kaggle.com/datasets as "datamate-code" (visibility: Private). Upload train.zip separately as the
private dataset "datamate-train". Competition data must never be public.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ["datamate", "scripts", "configs", "tests", "requirements.txt", "pytest.ini", "notebooks"]
EXTRA = ["out/gold_plans.jsonl"]          # derived from train answers; needed for few-shot prompts


def main():
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    target = dist / "datamate_code.zip"
    files = []
    for item in INCLUDE + EXTRA:
        p = ROOT / item
        for f in ([p] if p.is_file() else sorted(p.rglob("*")) if p.exists() else []):
            if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
                files.append(f)
    h = hashlib.sha1()
    for f in files:
        h.update(f.relative_to(ROOT).as_posix().encode())
        h.update(f.read_bytes())
    info = (f"built_at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"code_hash {h.hexdigest()[:12]}\nfiles {len(files)}\n")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.relative_to(ROOT).as_posix())
        z.writestr("BUILD_INFO.txt", info)
    missing = [e for e in EXTRA if not (ROOT / e).exists()]
    print(f"{target} ({len(files)} files, {target.stat().st_size / 1e6:.1f} MB)")
    print(info, end="")
    if missing:
        print("WARNING missing (run scripts/label_plans.py first):", missing)


if __name__ == "__main__":
    main()
