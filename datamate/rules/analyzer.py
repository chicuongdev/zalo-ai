"""Rulebook analyzer (plan/11 G4): the runtime rulebook is input data, not a constant.

Every table row of the rulebook (`| term | definition |`) is hashed. Rows whose hash is not among the training
rulebook's rows are **new or changed**. Their terms form a runtime glossary; a question that mentions one of
those terms must not be answered by a library intent written for the training rules, unless that concept has
been implemented explicitly (HANDLED_CONCEPTS).

Only hashes of the training rows are shipped (configs/rulebook_train_rows.json), never the rulebook text.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..qa.normalize import normalize_question, strip_accents

ROWS_FILE = Path(__file__).resolve().parents[2] / "configs" / "rulebook_train_rows.json"

# concepts of non-training rulebooks already implemented by an intent: signature -> intent name
HANDLED_CONCEPTS: dict[str, str] = {}


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9%]+", " ", strip_accents(text).lower()).split())


def _row_hash(section: str, cells: list[str]) -> str:
    return hashlib.sha1(("|".join([_norm(section)] + [_norm(c) for c in cells])).encode()).hexdigest()[:16]


@dataclass
class Row:
    section: str
    term: str
    definition: str
    hash: str


def parse_rows(text: str) -> list[Row]:
    rows, section = [], ""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            section = s.lstrip("#").strip()
            continue
        if not s.startswith("|") or re.match(r"^\|\s*-", s):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2 or cells[0].lower() in ("luật", "cách nói", "cách ghi", "từ", "type"):
            continue
        rows.append(Row(section, cells[0], " | ".join(cells[1:]), _row_hash(section, cells)))
    return rows


def save_train_hashes(rulebook_path: str | Path, out: Path = ROWS_FILE) -> int:
    rows = parse_rows(Path(rulebook_path).read_text(encoding="utf-8"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sorted({r.hash for r in rows}), indent=0), encoding="utf-8")
    return len(rows)


@dataclass
class Concept:
    term: str
    section: str
    phrase: str                   # accent-free contiguous core phrase, e.g. "tra gop"
    phrase_acc: str               # same span with diacritics, e.g. "trả góp"
    status: str                   # "new" | "changed"


def _acc_norm(text: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFC", text).lower()
    return " ".join(re.sub(r"[^\w%]+", " ", s).split())


def _has_accents(text: str) -> bool:
    return strip_accents(text) != text


@dataclass
class RulebookDiff:
    rows: list[Row]
    changed: list[Row] = field(default_factory=list)
    concepts: list[Concept] = field(default_factory=list)
    new_sections: list[str] = field(default_factory=list)

    def concepts_in(self, question: str) -> list[Concept]:
        """Concepts whose core phrase occurs in the question. A question typed with diacritics must match with
        diacritics ("trả góp" is not "lãi gộp", "dòng máy" is not "mấy")."""
        plain = " " + normalize_question(question) + " "
        acc = " " + _acc_norm(question) + " "
        accented = _has_accents(question)
        out = []
        for c in self.concepts:
            if f" {c.phrase} " not in plain:
                continue
            if accented and c.phrase_acc and f" {c.phrase_acc} " not in acc:
                continue
            out.append(c)
        return out


# words too common in questions to identify a concept on their own
COMMON = set("""
khach hang mat san pham don nhieu nhat it so tien ngay thang nam ky trong cua cac la co the va khi tinh theo
ban mua tra no thu chi gia ca mot hai ba gom khong tren duoi tu den het hom nay qua nhan vien tho cua shop
doanh thoi gian gio dong ghi phieu nao x duoc hay voi lan toi moi
""".split())


BIGRAMS_FILE = Path(__file__).resolve().parents[2] / "configs" / "train_bigrams.txt"


def save_train_bigrams(questions: list[str], min_count: int = 2, out: Path = BIGRAMS_FILE) -> int:
    """Word pairs frequent in training questions (vocabulary statistics only, no question text)."""
    from collections import Counter
    c = Counter()
    for q in questions:
        toks = normalize_question(q).split()
        c.update(f"{a} {b}" for a, b in zip(toks, toks[1:]))
    keep = sorted(k for k, n in c.items() if n >= min_count)
    out.write_text("\n".join(keep), encoding="utf-8")
    return len(keep)


_BIGRAMS: set[str] | None = None


def _known_bigrams() -> set[str]:
    global _BIGRAMS
    if _BIGRAMS is None:
        _BIGRAMS = set(BIGRAMS_FILE.read_text(encoding="utf-8").split("\n")) if BIGRAMS_FILE.exists() else set()
    return _BIGRAMS


def _familiar(words: list[str]) -> bool:
    """Every adjacent pair already common in training questions => the phrase names an existing concept."""
    known = _known_bigrams()
    return len(words) >= 2 and all(f"{a} {b}" in known for a, b in zip(words, words[1:]))


def _core(term: str) -> tuple[str, str] | None:
    """Contiguous span from the first to the last distinctive word of the term (accent-free, accented).
    A single short core word is extended by its neighbour ("sộp" -> "khách sộp", "góp" -> "trả góp"); a phrase that
    is already familiar from training questions is extended to the right until it is new ("trung bình" ->
    "trung bình mỗi ngày")."""
    acc = _acc_norm(term).split()
    plain = [strip_accents(t) for t in acc]
    idx = [i for i, t in enumerate(plain) if t.isalpha() and t not in COMMON and len(t) > 1]
    if not idx:
        return None
    a, b = idx[0], idx[-1]
    if a == b and len(plain[a]) <= 5:
        if a > 0:
            a -= 1
        elif b + 1 < len(plain):
            b += 1
        else:
            return None
    while _familiar(plain[a:b + 1]) and b + 1 < len(plain) and plain[b + 1] not in ("x", "cua", "ky"):
        b += 1
    if _familiar(plain[a:b + 1]):
        return None                     # nothing in the term is new: a rule change, not an askable concept
    return " ".join(plain[a:b + 1]), " ".join(acc[a:b + 1])


def analyze(rulebook_text: str, train_vocab: set[str] | None = None) -> RulebookDiff:
    """Diff a runtime rulebook against the training one. Without the shipped hashes every row counts as known."""
    rows = parse_rows(rulebook_text)
    known_hashes = set(json.loads(ROWS_FILE.read_text(encoding="utf-8"))) if ROWS_FILE.exists() else {r.hash for r in rows}
    train_sections = {r.section for r in rows if r.hash in known_hashes}
    diff = RulebookDiff(rows)
    for r in rows:
        if r.hash in known_hashes:
            continue
        diff.changed.append(r)
        status = "new" if r.section not in train_sections else "changed"
        for term in re.split(r",|/| và ", re.sub(r"\*", "", r.term)):
            term = term.strip()
            core = _core(term) if len(term) >= 3 else None
            if core:
                diff.concepts.append(Concept(term, r.section, core[0], core[1], status))
        if r.section not in train_sections and r.section not in diff.new_sections:
            diff.new_sections.append(r.section)
    return diff
