"""Сверка данных со скрина с транзакцией в TronScan API."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from .tron_screen_parse import (
    TronScreenHints,
    screen_addresses_unreliable,
    wallet_likely_in_screen_text,
    wallet_matches_address,
    wallet_on_screen_addresses,
)
from .tron_transaction import (
    amounts_match,
    check_wallet_address_in_transaction,
    extract_amount_from_transaction_data,
    transfer_amount_usdt,
    transfer_block_ts_ms,
    transfer_tx_hash,
    wallet_in_trc20_transfer_row,
)
from .tronscan_api import (
    fetch_transaction_info,
    fetch_trc20_for_address,
    fetch_trc20_transfers,
)

logger = logging.getLogger(__name__)

_TS_WINDOW_BEFORE_MS = 10 * 60 * 1000
_TS_WINDOW_AFTER_MS = 45 * 60 * 1000
_FALLBACK_WINDOW_MS = 6 * 60 * 60 * 1000


@dataclass(frozen=True)
class VerifiedTronPayout:
    tx_hash: str
    amount: float


def _transfer_from_address(row: dict) -> str:
    return str(row.get("from_address") or row.get("fromAddress") or "").strip().upper()


def _transfer_to_address(row: dict) -> str:
    return str(row.get("to_address") or row.get("toAddress") or "").strip().upper()


def _distinct_screen_addresses(hints: TronScreenHints) -> bool:
    s, r = hints.sending_address, hints.receiving_address
    if not s or not r:
        return False
    return s.strip().upper() != r.strip().upper()


def _matches_hints(row: dict, hints: TronScreenHints, wallet: str) -> bool:
    if not wallet_in_trc20_transfer_row(row, wallet):
        return False
    amt = transfer_amount_usdt(row)
    if amt is None or amt <= 0:
        return False
    if hints.expected_amount is not None and not amounts_match(amt, hints.expected_amount):
        return False
    # Не принимаем комиссию 1.5 USDT вместо крупного перевода
    if (
        hints.expected_amount is not None
        and hints.expected_amount >= 50
        and amt < 10
    ):
        return False
    if _distinct_screen_addresses(hints):
        if hints.sending_address and wallet_matches_address(wallet, hints.sending_address):
            if not wallet_matches_address(wallet, _transfer_from_address(row)):
                return False
        if hints.receiving_address and wallet_matches_address(wallet, hints.receiving_address):
            if not wallet_matches_address(wallet, _transfer_to_address(row)):
                return False
    if hints.created_at_ms is not None:
        ts = transfer_block_ts_ms(row)
        if ts is not None:
            delta = abs(ts - hints.created_at_ms)
            if delta > _TS_WINDOW_AFTER_MS:
                return False
    return True


def _pick_unique_transfer(
    rows: list[dict], hints: TronScreenHints, wallet: str
) -> Optional[dict]:
    matched = [r for r in rows if _matches_hints(r, hints, wallet)]
    if not matched:
        return None
    if len(matched) == 1:
        return matched[0]

    if hints.created_at_ms is not None:
        scored = []
        for r in matched:
            ts = transfer_block_ts_ms(r)
            if ts is None:
                continue
            scored.append((r, abs(ts - hints.created_at_ms)))
        if scored:
            scored.sort(key=lambda x: x[1])
            best, best_delta = scored[0]
            if len(scored) > 1 and scored[1][1] - best_delta < 60_000:
                return None
            return best

    return None


def _search_time_range(hints: TronScreenHints) -> tuple[int, int]:
    now_ms = int(time.time() * 1000)
    if hints.created_at_ms is not None:
        start = hints.created_at_ms - _TS_WINDOW_BEFORE_MS
        end = hints.created_at_ms + _TS_WINDOW_AFTER_MS
        return start, min(end, now_ms + 60_000)
    return now_ms - _FALLBACK_WINDOW_MS, now_ms


async def _verify_by_hash(hints: TronScreenHints, wallet: str) -> Optional[VerifiedTronPayout]:
    assert hints.tx_hash
    data = await fetch_transaction_info(hints.tx_hash)
    if not data:
        return None
    if not check_wallet_address_in_transaction(data, wallet):
        return None
    amount = extract_amount_from_transaction_data(data, wallet)
    if amount is None or amount <= 0:
        return None
    if hints.expected_amount is not None and not amounts_match(amount, hints.expected_amount):
        logger.warning(
            "hash %s: API amount %s != screen %s",
            hints.tx_hash,
            amount,
            hints.expected_amount,
        )
        return None
    return VerifiedTronPayout(tx_hash=hints.tx_hash, amount=amount)


async def _search_transfers(hints: TronScreenHints, wallet: str) -> Optional[VerifiedTronPayout]:
    start_ts, end_ts = _search_time_range(hints)
    kwargs: dict = {
        "related_address": wallet,
        "start_timestamp": start_ts,
        "end_timestamp": end_ts,
        "limit": 50,
    }
    # from_address только если на скрине уверенно указан отправитель = кошелёк CRM
    if (
        hints.sending_address
        and wallet_matches_address(wallet, hints.sending_address)
        and _distinct_screen_addresses(hints)
    ):
        kwargs["from_address"] = wallet

    rows = await fetch_trc20_transfers(**kwargs)
    if not rows:
        rows = await fetch_trc20_for_address(
            wallet,
            start_timestamp=start_ts,
            end_timestamp=end_ts,
            limit=50,
            direction="0",
        )

    picked = _pick_unique_transfer(rows, hints, wallet)
    if not picked:
        return None

    tx_hash = transfer_tx_hash(picked)
    amount = transfer_amount_usdt(picked)
    if not tx_hash or amount is None:
        return None
    if hints.expected_amount is not None and not amounts_match(amount, hints.expected_amount):
        return None
    if hints.expected_amount is not None and hints.expected_amount >= 50 and amount < 10:
        logger.warning(
            "reject tiny API amount %s for expected screen amount %s",
            amount,
            hints.expected_amount,
        )
        return None
    return VerifiedTronPayout(tx_hash=tx_hash, amount=amount)


async def verify_screen_on_chain(
    hints: TronScreenHints,
    wallet: str,
    *,
    screen_text: str = "",
) -> tuple[Optional[VerifiedTronPayout], str]:
    """
    Сверяет скрин с блокчейном через TronScan.
    Участие кошелька CRM проверяется в API; OCR-адреса — только подсказки.
    """
    wallet = wallet.strip()
    if not wallet:
        return None, "Не задан глобальный кошелёк Tron в CRM."

    on_screen = wallet_on_screen_addresses(hints, wallet) or wallet_likely_in_screen_text(
        screen_text, wallet
    )
    unreliable = screen_addresses_unreliable(hints, wallet)

    if not on_screen and not unreliable:
        logger.warning(
            "wallet %s not in screen addresses: sending=%s receiving=%s all=%s",
            wallet[:8] + "…",
            hints.sending_address,
            hints.receiving_address,
            hints.all_addresses,
        )
        send_s = hints.sending_address or "—"
        recv_s = hints.receiving_address or "—"
        return (
            None,
            f"Кошелёк {wallet} не найден среди адресов на скрине "
            f"(отправитель: {send_s}, получатель: {recv_s}). "
            f"Проверьте CRM или пришлите более чёткий скрин / хеш TronScan.",
        )

    if not on_screen and unreliable:
        logger.warning(
            "screen addresses unreliable, skip on-screen wallet check; "
            "wallet=%s sending=%s receiving=%s all=%s",
            wallet[:8] + "…",
            hints.sending_address,
            hints.receiving_address,
            hints.all_addresses,
        )

    if hints.tx_hash:
        verified = await _verify_by_hash(hints, wallet)
        if verified:
            return verified, ""
        return (
            None,
            "Транзакция по хешу со скрина не найдена в TronScan "
            "или кошелёк не участвует в ней / не совпадает сумма.",
        )

    if hints.expected_amount is None:
        return None, "На скрине не распознана сумма для поиска транзакции."

    verified = await _search_transfers(hints, wallet)
    if verified:
        return verified, ""

    logger.info(
        "Tron verify: no matching transfer wallet=%s… amount=%s created_at_ms=%s tx_hash=%s",
        wallet[:8],
        hints.expected_amount,
        hints.created_at_ms,
        (hints.tx_hash[:16] + "…") if hints.tx_hash else None,
    )
    return (
        None,
        "В TronScan не найдена подходящая USDT-транзакция с участием вашего кошелька "
        "(отправитель или получатель), сумма и время. "
        "Дождитесь подтверждения или пришлите хеш с TronScan.",
    )
