"""B1 — question normalizer: accent-free lowercase text with Telex typos and teencode repaired.

The output is only used for matching (regex parser, few-shot retrieval, entity lookup); the LLM always sees the
original question as well.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

TEENCODE = {
    "dthu": "doanh thu", "dt": "doanh thu", "bn": "bao nhieu", "bnhiu": "bao nhieu", "bnhieu": "bao nhieu",
    "bao nhiu": "bao nhieu", "nhiu": "nhieu", "nhìu": "nhieu", "dc": "duoc", "đc": "duoc", "hqua": "hom qua",
    "hnay": "hom nay", "hum nay": "hom nay", "hum qua": "hom qua", "bua qua": "hom qua", "bua nay": "hom nay",
    "sp": "san pham", "ko": "khong", "k": "khong", "kh": "khong", "trc": "truoc", "vs": "voi", "th": "thang",
    "thg": "thang", "j": "gi", "z": "", "ak": "", "mik": "minh", "mk": "minh", "lun": "luon",
    "revenue": "doanh thu", "order": "don", "orders": "don", "bill": "don", "total": "tong cong", "best seller": "ban chay",
    "top seller": "ban chay", "mn": "moi nguoi", "dk": "duoc", "dx": "duoc",
    "ntn": "nhu the nao", "tm": "tien mat", "ck": "chuyen khoan", "hok": "khong", "sl": "so luong", "kh hang": "khach hang", "nv": "nhan vien", "ncc": "nha cung cap",
    "tb": "trung binh", "hd": "hoa don", "pt": "phan tram", "ti le": "ti le", "ty le": "ti le", "tỷ": "ti",
    "bnhiêu": "bao nhieu", "mn": "moi nguoi", "ng": "nguoi", "tg": "thoi gian", "lgi": "loi gi",
}

_TELEX_VOWEL = [("uwow", "uo"), ("uow", "uo"), ("aa", "a"), ("aw", "a"), ("ee", "e"), ("oo", "o"), ("ow", "o"),
                ("uw", "u"), ("dd", "d")]
_TONE = re.compile(r"(?<=[aeiouy])([sfrxj])(?=[a-z]*$)|(?<=[a-z])([sfrxj])$")


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


def base_text(q: str) -> str:
    s = strip_accents(unicodedata.normalize("NFC", q)).lower()
    s = s.replace("≥", " >= ").replace("≤", " <= ").replace("–", "-").replace("—", "-")
    s = re.sub(r"(\d)\s*%", r"\1 %", s)
    s = re.sub(r"[^a-z0-9%/.,:<>=\-() ]+", " ", s)
    return " ".join(s.split())


def telex_fix(tok: str, vocab: set[str]) -> str:
    """Undo Telex input left in a word ("thangs" -> "thang", "dduwowcj" -> "duoc") if the result is a known word."""
    if tok in vocab or not tok.isalpha():
        return tok
    cands = []
    t = tok
    for a, b in _TELEX_VOWEL:
        t = t.replace(a, b)
    cands.append(t)
    for x in (tok, t):
        if x and x[-1] in "sfrxj":
            cands.append(x[:-1])
        m = re.sub(r"([aeiouy])[sfrxj]([a-z]*)$", r"\1\2", x)
        cands.append(m)
        if m and m[-1] in "sfrxj":
            cands.append(m[:-1])
    for c in cands:
        if c in vocab:
            return c
    return tok


DEFAULT_VOCAB = set("""
thang nam ngay tuan quy hom nay qua truoc roi doanh thu ban duoc bao nhieu tien don huy ti le phan tram tang giam
cua hang tong cong nhieu nhat chay mat san pham khach mua no tra nhap gia binh quan ton kho het lai gop rong chi phi
trung binh mot moi tu den dau cuoi gan lien nhau ket thuc o cung ky so voi hon kem nao la gi ai nhung liet ke top
ca sang chieu nhom size thuoc ke khong hoat chat lo han dung dot giao xe vien hop goi chai lon thung bao cay cuon
nguoi vay nhi a co may tinh rieng giup xem cho minh hoi biet toi em phieu nha cung cap tri gia von hien con dang
chiu cac trang thai khi hay bi duoi tren tro len gio ly mon phi phuc vu theo hinh thuc thanh toan tien mat chuyen
khoan vi dien tu kenh zalo tai quay voucher giam giam gia nhan vien gioi dau tien thu ve ra mua chiu
""".split())


VOCAB_FILE = Path(__file__).resolve().parents[2] / "configs" / "vocab.txt"


@lru_cache(maxsize=1)
def default_vocab() -> frozenset:
    words = set(DEFAULT_VOCAB)
    if VOCAB_FILE.exists():
        words |= set(VOCAB_FILE.read_text(encoding="utf-8").split())
    return frozenset(words)


def build_vocab(questions: list[str], min_count: int = 5) -> set[str]:
    """Words frequent enough to be correctly typed (typos are rare per spelling)."""
    from collections import Counter
    c = Counter(t for q in questions for t in base_text(q).split() if t.isalpha())
    return {w for w, n in c.items() if n >= min_count}


def normalize_question(q: str, vocab: set[str] | None = None) -> str:
    vocab = vocab or default_vocab()
    s = base_text(q)
    toks = [telex_fix(t, vocab) for t in s.split()]
    s = " " + " ".join(toks) + " "
    for k in sorted(TEENCODE, key=len, reverse=True):
        kk = strip_accents(k)
        s = re.sub(rf"(?<=[\s(]){re.escape(kk)}(?=[\s,.?)])", TEENCODE[k], s)
    return normalize_periods(" ".join(s.split()))


DIALECT = {"mo": "nao", "ni": "nay", "chi": "gi", "rua": "sao", "tê": "kia", "te": "kia"}


def normalize_periods(s: str) -> str:
    """Month / quarter spellings seen in the public test: "th7/2026", "t4/2026", "th 5/26", "05/2026",
    "8-2025", "3/26" after "thang" -> "thang M/YYYY"; Central dialect "ngày mô", "tuần ni"."""
    s = " " + s + " "
    s = re.sub(r"(?<=\s)(?:thang|th|thg|t)\s?(\d{1,2})\s?[/.-]\s?(\d{4}|\d{2})(?=[\s,.?:;)])",
               lambda m: f"thang {int(m.group(1))}/{_year(m.group(2))}", s)
    s = re.sub(r"(?<=\s)(?:quy|q)\s?([1-4])\s?[/.-]\s?(\d{4}|\d{2})(?=[\s,.?:;)])",
               lambda m: f"quy {m.group(1)}/{_year(m.group(2))}", s)
    # bare "05/2026", "8-2025" (not part of a dd/mm/yyyy date)
    s = re.sub(r"(?<![\d/.-])(?<!thang )(?<!quy )(\d{1,2})\s?[/-]\s?(20\d{2})(?![\d/.-])",
               lambda m: f"thang {int(m.group(1))}/{m.group(2)}" if 1 <= int(m.group(1)) <= 12 else m.group(0), s)
    # dialect question words (only after the words they modify, to keep names like "Chi")
    s = re.sub(r"(?<=\s)(ngay|hom|khach|mon|hang|tuan|thang|nam|ca|nhom|sp|san pham|mat hang|nguoi|ai|cai|loai|"
               r"nha cung cap|nhan vien|tho|xe|may) (mo|ni)(?=\s)",
               lambda m: f"{m.group(1)} {DIALECT[m.group(2)]}", s)
    return " ".join(s.split())


def _year(y: str) -> str:
    return y if len(y) == 4 else f"20{y}"
