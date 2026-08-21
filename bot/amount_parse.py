"""Разбор сумм: 1к, 1кк, 1.000, 1.000.000 и обычные числа."""
from __future__ import annotations

import re

_THOUSAND_DOTS = re.compile(r"^-?\d{1,3}(\.\d{3})+$")
_SUFFIX_KK = re.compile(r"^([+-]?)([\d.,\s]+?)(?:кк|kk)$", re.IGNORECASE)
_SUFFIX_K = re.compile(r"^([+-]?)([\d.,\s]+?)(?:к|k)$", re.IGNORECASE)
_DECIMAL_COMMA = re.compile(r"^-?\d+,\d{1,3}$")


def parse_amount(raw: str) -> float:
    """
    Примеры: 1000, 1к, 1кк, 1.000, 1.000.000, 100.00, -50к, 1,5к.
    к / k — тысяча, кк / kk — миллион.
    """
    s = (raw or "").strip().replace("\u00a0", "").replace(" ", "")
    if not s:
        raise ValueError("пустая сумма")

    sign = 1.0
    if s[0] in "+-":
        if s[0] == "-":
            sign = -1.0
        s = s[1:]

    multiplier = 1.0
    m = _SUFFIX_KK.match(s)
    if m:
        s = m.group(2)
        multiplier = 1_000_000.0
    else:
        m = _SUFFIX_K.match(s)
        if m:
            s = m.group(2)
            multiplier = 1_000.0

    value = _parse_number_core(s)
    return sign * value * multiplier


def _parse_number_core(s: str) -> float:
    if not s:
        raise ValueError("пустое число")

    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        if _DECIMAL_COMMA.match(s):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")

    if _THOUSAND_DOTS.match(s):
        s = s.replace(".", "")

    return float(s)
