"""Стикеры Mansory (набор mansory_stick)."""
from __future__ import annotations

import logging
import random

from aiogram import Bot

logger = logging.getLogger(__name__)

# 🤝 утренний
MORNING_STICKER_FILE_ID = (
    "CAACAgIAAxkBAANgagxGdgnqGyvpxY4uWX1XHNoIIfUAAnaVAALMe7hL2I8fU3yMVVo7BA"
)

# 🏛️ / 💵 при выплате (один наугад)
PAID_STICKER_FILE_IDS: tuple[str, ...] = (
    "CAACAgIAAxkBAANiagxGocMa2out1Bo-H4NsMSBkWg4AAtyaAALeH7lLBwt_F0ZjSMs7BA",
)


def pick_paid_sticker_file_id() -> str:
    return random.choice(PAID_STICKER_FILE_IDS)


async def send_paid_sticker(bot: Bot, chat_id: int) -> None:
    try:
        await bot.send_sticker(chat_id, pick_paid_sticker_file_id())
    except Exception:
        logger.exception("Не удалось отправить стикер выплаты в чат %s", chat_id)
