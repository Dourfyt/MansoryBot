"""Общая логика зачисления выплаты по Tron (только после проверки в API)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from aiogram import Bot
from aiogram.types import Message

from .group_queries import (
    get_global_wallet_address,
    insert_payout,
    is_transaction_hash_processed,
    mark_transaction_processed,
)
from .stickers import send_paid_sticker
from .tron_screen_log import log_tron_screen
from .tron_screen_parse import TronScreenHints
from .tron_verify import verify_screen_on_chain
from .ui_copy import format_money

logger = logging.getLogger(__name__)


async def record_tron_payout(
    message: Message,
    bot: Bot,
    chat_id: int,
    amount: float,
    tx_hash: str,
    *,
    msg_payout_ok,
    msg_err,
) -> bool:
    """Записывает выплату по подтверждённому хешу транзакции (сумма из API)."""
    if is_transaction_hash_processed(tx_hash):
        short = tx_hash[:16] + "..."
        log_tron_screen(message, "payout_duplicate", tx_hash=short)
        try:
            await message.reply(f"⚠️ Транзакция {short} уже была зафиксирована")
        except Exception:
            pass
        return False

    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        insert_payout(chat_id, amount, timestamp)
        mark_transaction_processed(tx_hash, amount, chat_id)
        await send_paid_sticker(bot, chat_id)
        await message.reply(
            **msg_payout_ok(
                f"Выплата добавлена: {format_money(amount)} "
                f"(TronScan, {tx_hash[:12]}…)"
            )
        )
        logger.info("Tron payout %s amount=%s chat=%s", tx_hash, amount, chat_id)
        log_tron_screen(message, "payout_saved", amount=amount, tx_hash=tx_hash[:16] + "…")
        return True
    except Exception as e:
        logger.exception("record_tron_payout: %s", e)
        log_tron_screen(message, "payout_save_error", error=str(e))
        try:
            await message.reply(**msg_err(f"Ошибка при сохранении выплаты: {e}"))
        except Exception:
            pass
        return False


async def process_screen_hints_payout(
    message: Message,
    bot: Bot,
    chat_id: int,
    hints: TronScreenHints,
    *,
    screen_text: str = "",
    msg_payout_ok,
    msg_err,
) -> bool:
    """Скрин/текст → поиск в TronScan → сверка → выплата суммой из API."""
    wallet = get_global_wallet_address()
    if not wallet:
        log_tron_screen(message, "verify_skip", reason="no_global_wallet")
        try:
            await message.reply(
                **msg_err("Не задан глобальный кошелёк Tron в CRM — сверка с API невозможна.")
            )
        except Exception:
            pass
        return False

    verified, err = await verify_screen_on_chain(hints, wallet, screen_text=screen_text)
    if err:
        log_tron_screen(message, "verify_failed", reason=err)
        try:
            await message.reply(**msg_err(err))
        except Exception:
            pass
        return False
    if not verified:
        log_tron_screen(message, "verify_failed", reason="no_verified_payload")
        try:
            await message.reply(**msg_err("Не удалось подтвердить транзакцию в TronScan."))
        except Exception:
            pass
        return False

    log_tron_screen(
        message,
        "verify_ok",
        amount=verified.amount,
        tx_hash=verified.tx_hash[:16] + "…",
    )

    return await record_tron_payout(
        message,
        bot,
        chat_id,
        verified.amount,
        verified.tx_hash,
        msg_payout_ok=msg_payout_ok,
        msg_err=msg_err,
    )
