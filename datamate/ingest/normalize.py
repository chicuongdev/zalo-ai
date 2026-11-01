"""Normalisation of enumerated values (order status, payment method, channel) and of entity names.

Dictionaries were built from every distinct value in the train shops; unknown values fall back to keyword rules
and are reported so that the LLM tier (G3) can resolve them.
"""
from __future__ import annotations

import re
import unicodedata

from .parsers import strip_accents

STATUSES = ("completed", "cancelled", "returned", "delivering")


def _key(v) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", strip_accents(str(v)).lower()).split())


_STATUS = {
    "completed": ["Đã hoàn thành", "đã lấy", "xong", "đã xong", "Đã giao", "Thành công", "ok", "completed", "Hoàn thành",
                  "Đặt hàng (Đã duyệt)"],
    "cancelled": ["Đã hủy", "hủy", "Đã hủy đơn", "Huỷ đơn", "cancel", "khách hủy", "hủy đơn", "Không giao được", "cancelled",
                  "Đã huỷ", "Hủy"],
    "returned": ["Đã hoàn hàng", "trả hàng", "Đổi trả", "Đã trả hàng", "hàng trả về", "Hoàn trả", "trả lại", "returned"],
    "delivering": ["Đang giao dịch", "Đang vận chuyển", "Đang giao", "Đang giao hàng", "Đang xử lý", "đang gửi", "shipping",
                   "Chờ giao"],
}
STATUS_MAP = {_key(v): k for k, vs in _STATUS.items() for v in vs}


def norm_status(v) -> str | None:
    """Raw status -> one of STATUSES, or None when unknown/blank."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    k = _key(v)
    if k in STATUS_MAP:
        return STATUS_MAP[k]
    if re.search(r"\b(huy|cancel)", k):
        return "cancelled"
    if re.search(r"\b(tra|return|hoan hang)", k):
        return "returned"
    if re.search(r"\b(dang|cho|ship)", k):
        return "delivering"
    if re.search(r"\b(xong|hoan thanh|thanh cong|ok|done|giao)", k):
        return "completed"
    return None


_PAY = {
    "cash": ["Tiền mặt", "cash", "TM"],
    "transfer": ["Chuyển khoản", "transfer", "CK", "bank"],
    "ewallet": ["Ví điện tử", "ewallet", "momo", "zalopay", "vnpay"],
    "cod": ["Thu hộ (COD)", "cod", "thu ho"],
    "debt": ["Ghi nợ", "debt", "nợ"],
    "card": ["Thẻ", "card", "pos", "quẹt thẻ"],
}
PAY_MAP = {_key(v): k for k, vs in _PAY.items() for v in vs}


def norm_payment(v) -> str | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    k = _key(v)
    if k in PAY_MAP:
        return PAY_MAP[k]
    for word, m in (("cod", "cod"), ("chuyen", "transfer"), ("tien mat", "cash"), ("vi", "ewallet"), ("no", "debt")):
        if re.search(rf"\b{word}\b", k):
            return m
    return "other"


def norm_text(v) -> str | None:
    if v is None:
        return None
    s = unicodedata.normalize("NFC", str(v)).strip()
    return s or None


def name_key(v) -> str:
    """Identity key for names: the official string-matching normalisation (case, punctuation, spaces ignored)."""
    s = unicodedata.normalize("NFC", str(v)).lower()
    s = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in s)
    return " ".join(s.split())


_PHONE_TAIL = re.compile(r"[\s\-–(]*\(?(?:\+?84|0)[\d\s.]{8,13}\)?\s*$")


def person_key(v) -> str:
    """Customer identity for shops without codes (rulebook §3): names differing only in spelling are one customer.
    Spelling = case, diacritics, spaces, punctuation, a trailing phone number."""
    s = _PHONE_TAIL.sub("", unicodedata.normalize("NFC", str(v)))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", strip_accents(s).lower()).split())


WALK_IN = {"khach le", "le", "kl", "khach vang lai", "vang lai", "khach"}


def is_walk_in(name) -> bool:
    return name is None or (isinstance(name, str) and (not name.strip() or person_key(name) in WALK_IN))
