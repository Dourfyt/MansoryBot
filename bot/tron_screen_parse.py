"""Парсинг скринов кошелька Tron — только подсказки для поиска в API (сумму не доверяем)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Tuple

from .amount_parse import parse_amount

_TRON_ADDR = re.compile(r"\bT[1-9A-HJ-NP-Za-km-z]{33}\b")
# USDT TRC20 — часто попадает в OCR, не отправитель/получатель выплаты
_USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
_TX_HASH = re.compile(r"\b([a-fA-F0-9]{64})\b")
_USDT_AMOUNT = re.compile(
    r"(-?[\d][\d\s.,]*)\s*USDT",
    re.IGNORECASE,
)
_EST_RECEIVING = re.compile(
    r"(?:est\.?\s*receiving\s*amount|estimated\s*receiving\s*amount)"
    r"[\s\n:]*(-?[\d][\d\s.,]*)\s*USDT",
    re.IGNORECASE | re.DOTALL,
)
_CREATED_AT = re.compile(
    r"(?:created\s*at|created)[\s\n:]*"
    r"(\d{1,2}[/.]\d{1,2}[/.]\d{4}\s+\d{1,2}:\d{2}(?::\d{2})?)",
    re.IGNORECASE,
)

_DATE_FORMATS = (
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
)

_FEE_USDT = re.compile(
    r"(?:est\.?\s*transaction\s*fee|transaction\s*fee)"
    r"[\s\n:]*(-?[\d][\d\s.,]*)\s*USDT",
    re.IGNORECASE | re.DOTALL,
)
# Крупная сумма в шапке скрина (Permit Transfer -13 163.5 USDT)
_GROSS_OUT_USDT = re.compile(
    r"(-[\d][\d\s.,]{2,})\s*USDT",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TronScreenHints:
    """Данные со скрина для поиска транзакции в TronScan (не источник суммы выплаты)."""

    expected_amount: Optional[float]
    receiving_address: Optional[str]
    sending_address: Optional[str]
    created_at_ms: Optional[int]
    tx_hash: Optional[str]
    all_addresses: tuple[str, ...] = field(default_factory=tuple)


def looks_like_tron_wallet_screen(text: str) -> bool:
    if not text or len(text) < 12:
        return False
    low = text.lower()
    if "permit transfer" in low or "transaction details" in low:
        return True
    if "est. receiving amount" in low or "est receiving amount" in low:
        return True
    if "gasfree" in low and "usdt" in low:
        return True
    if "sending account" in low and "receiving account" in low and "usdt" in low:
        return True
    return False


def _parse_usdt_token(raw: str) -> float:
    s = raw.strip().replace("\u00a0", "").replace(" ", "")
    if not s:
        raise ValueError("пустая сумма")
    return parse_amount(s)


def _is_usdt_contract(addr: str) -> bool:
    return addr.strip().upper() == _USDT_CONTRACT.upper()


def _unique_tron_addresses(text: str) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _TRON_ADDR.findall(text):
        key = m.upper()
        if key not in seen:
            seen.add(key)
            out.append(m)
    return tuple(out)


def _address_after_label(text: str, *labels: str) -> Optional[str]:
    """Первый Tron-адрес в блоке после подписи Sending/Receiving Account."""
    low = text.lower()
    for label in labels:
        idx = low.find(label)
        if idx < 0:
            continue
        chunk = text[idx : idx + 600]
        for m in _TRON_ADDR.finditer(chunk):
            addr = m.group(0)
            if not _is_usdt_contract(addr):
                return addr
    return None


def _pick_addresses(text: str) -> Tuple[Optional[str], Optional[str], tuple[str, ...]]:
    all_addrs = _unique_tron_addresses(text)
    user_addrs = tuple(a for a in all_addrs if not _is_usdt_contract(a))

    sending = _address_after_label(
        text, "sending account", "sending address", "sending account address"
    )
    receiving = _address_after_label(
        text, "receiving account", "receiving address", "receiving account address"
    )

    if not sending and not receiving and len(user_addrs) >= 2:
        sending, receiving = user_addrs[0], user_addrs[-1]
    elif not sending and len(user_addrs) >= 2:
        for a in user_addrs:
            if a != receiving:
                sending = a
                break
    elif not receiving and len(user_addrs) == 1:
        receiving = user_addrs[0]
    elif not receiving and len(user_addrs) >= 2:
        receiving = user_addrs[-1]

    if (
        sending
        and receiving
        and sending.strip().upper() == receiving.strip().upper()
    ):
        # OCR часто не видит отправителя — не дублируем получателя в оба поля
        sending = None

    return sending, receiving, all_addrs


def wallet_likely_in_screen_text(text: str, wallet: str) -> bool:
    """Кошелёк есть в сыром OCR-тексте (даже если regex адресов не собрал T-строку)."""
    if not text or not wallet:
        return False
    w = re.sub(r"\s+", "", wallet.strip().upper())
    compact = re.sub(r"[^A-Z0-9]", "", text.upper())
    if len(w) < 10:
        return False
    if w in compact:
        return True
    # Начало + конец адреса (типичные ошибки OCR в середине)
    if len(w) >= 16 and w[:10] in compact and w[-8:] in compact:
        return True
    return False


def screen_addresses_unreliable(hints: TronScreenHints, wallet: str = "") -> bool:
    """Парсер адресов со скрина ненадёжен — опираемся на API и кошелёк CRM."""
    if not hints.all_addresses:
        return True
    if len(hints.all_addresses) < 2:
        return True
    s, r = hints.sending_address, hints.receiving_address
    if s and r and s.strip().upper() == r.strip().upper():
        return True
    if wallet.strip() and not wallet_on_screen_addresses(hints, wallet):
        return True
    return False


def addresses_similar(a: str, b: str, *, max_diff: int = 2) -> bool:
    """Сравнение Tron-адресов с допуском на ошибки OCR (8/B, r/rr и т.д.)."""
    x, y = a.strip().upper(), b.strip().upper()
    if not x or not y:
        return False
    if x == y:
        return True
    if len(x) == len(y) and len(x) >= 30:
        if sum(1 for i, j in zip(x, y) if i != j) <= max_diff:
            return True
    if len(x) >= 12 and len(y) >= 12 and x[:8] == y[:8] and x[-6:] == y[-6:]:
        return True
    return False


def wallet_matches_address(wallet: str, addr: str) -> bool:
    return addresses_similar(wallet, addr)


def wallet_on_screen_addresses(hints: TronScreenHints, wallet: str) -> bool:
    """Кошелёк CRM совпадает с любым адресом на скрине (включая fuzzy OCR)."""
    for addr in hints.all_addresses:
        if wallet_matches_address(wallet, addr):
            return True
    for addr in (hints.sending_address, hints.receiving_address):
        if addr and wallet_matches_address(wallet, addr):
            return True
    return False


def _parse_fee_usdt(text: str) -> Optional[float]:
    m = _FEE_USDT.search(text)
    if not m:
        return None
    try:
        return abs(_parse_usdt_token(m.group(1)))
    except ValueError:
        return None


def _parse_gross_out_usdt(text: str) -> Optional[float]:
    m = _GROSS_OUT_USDT.search(text)
    if not m:
        return None
    try:
        return abs(_parse_usdt_token(m.group(1)))
    except ValueError:
        return None


def _parse_expected_amount(text: str) -> Optional[float]:
    """Est. Receiving Amount; иначе крупнейшая USDT-сумма на скрине, не комиссия."""
    m_est = _EST_RECEIVING.search(text)
    if m_est:
        try:
            return abs(_parse_usdt_token(m_est.group(1)))
        except ValueError:
            pass

    fee_val = _parse_fee_usdt(text)
    gross_val = _parse_gross_out_usdt(text)

    candidates: list[float] = []
    for m in _USDT_AMOUNT.finditer(text):
        start = m.start()
        ctx = text[max(0, start - 100) : start].lower()
        if "fee" in ctx or "nonce" in ctx:
            continue
        try:
            v = abs(_parse_usdt_token(m.group(1)))
            if v > 0:
                candidates.append(v)
        except ValueError:
            continue

    if not candidates:
        return None

    if fee_val is not None:
        filtered = [c for c in candidates if abs(c - fee_val) > 0.001]
        if filtered:
            candidates = filtered

    large = [c for c in candidates if c >= 10.0]
    pick_from = large if large else candidates
    expected = max(pick_from)

    if gross_val is not None and gross_val >= 50 and expected < 10:
        better = [c for c in candidates if c >= 50]
        if better:
            expected = max(better)

    return expected


def _parse_created_at_ms(text: str) -> Optional[int]:
    m = _CREATED_AT.search(text)
    if not m:
        return None
    raw = m.group(1).strip()
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(raw, fmt)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    return None


def parse_wallet_screen_text(text: str) -> Optional[TronScreenHints]:
    """
    Извлекает подсказки со скрина. expected_amount — Est. Receiving Amount для сверки с API.
    """
    if not looks_like_tron_wallet_screen(text):
        return None

    expected_amount = _parse_expected_amount(text)

    sending, receiving, all_addrs = _pick_addresses(text)
    hm = _TX_HASH.search(text)
    tx_hash = hm.group(1) if hm else None
    created_at_ms = _parse_created_at_ms(text)

    if expected_amount is None and tx_hash is None:
        return None

    return TronScreenHints(
        expected_amount=expected_amount,
        receiving_address=receiving,
        sending_address=sending,
        created_at_ms=created_at_ms,
        tx_hash=tx_hash,
        all_addresses=all_addrs,
    )
