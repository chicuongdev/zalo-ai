"""Novelty signals: how much of a question the system can actually explain (plan/11 G1).

A question whose content words are all known (training vocabulary, rulebook, the shop's own names) is in the
distribution the parser was built for. Unknown words mean a new concept, a new abbreviation or a new spelling,
and any answer derived from it is less certain: the decision layer asks for agreement or abstains.
"""
from __future__ import annotations

import re
from pathlib import Path

from .normalize import default_vocab, normalize_question, strip_accents

# filler / politeness / question words that carry no meaning for the plan
FILLER = set("""
a ad ah ak alo anh ban be bit cam cha chi cho chu co con cua da dau day de di do em giup gium ha hay he hen hoi
ho kia la lam luon ma minh muon nao ne nha nhe nhi nho oi ong ơi qua ra roi sao shop the thi thoi tiem toi tui
uh um vay voi vs xem xin z zay a thanks thank ok oke okay bot ra cai mot hai ba
""".split())


SEEN_FILE = Path(__file__).resolve().parents[2] / "configs" / "vocab_seen.txt"


class Novelty:
    def __init__(self, extra_words: set[str] | None = None):
        seen = set(SEEN_FILE.read_text(encoding="utf-8").split()) if SEEN_FILE.exists() else set()
        self.vocab = set(default_vocab()) | seen | FILLER | (extra_words or set())

    def unknown_words(self, question: str, entity_words: set[str] | None = None) -> list[str]:
        """Content words of the normalized question that nothing explains."""
        s = normalize_question(question)
        out = []
        for t in s.split():
            if not t.isalpha() or len(t) <= 1:
                continue
            if t in self.vocab or (entity_words and t in entity_words):
                continue
            out.append(t)
        return out


def words_of(texts) -> set[str]:
    """Accent-free word set of free texts (rulebook, README, entity names)."""
    out = set()
    for t in texts:
        if isinstance(t, str):
            out.update(re.findall(r"[a-z]+", strip_accents(t).lower()))
    return out


def entity_words(lex) -> set[str]:
    return {w for table in (lex.products, lex.groups, lex.customers, lex.staff, lex.suppliers, lex.ingredients,
                            lex.customer_groups, lex.units, lex.channels)
            for k in table for w in k.split()}
