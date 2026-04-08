"""Меню команд (кнопка «Меню») для анонимных ботов в личке."""
from __future__ import annotations

import logging
from typing import Any

from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats

logger = logging.getLogger(__name__)

# Имена команд в меню — только a-z, 0-9, _ (ограничение Telegram Bot API).
ANONYMOUS_PRIVATE_BOT_COMMANDS = [
    BotCommand(
        command="delete",
        description="удалить своё последнее сообщение",
    ),
    BotCommand(
        command="info",
        description="информация по комнате",
    ),
    BotCommand(
        command="cheki_segodnya",
        description="все чеки за сегодня (файл)",
    ),
]


async def setup_anonymous_private_bot_commands(bot: Any) -> None:
    """Показывает в личке список команд у кнопки «Меню» (только дочерние боты анонимных чатов)."""
    try:
        await bot.set_my_commands(
            ANONYMOUS_PRIVATE_BOT_COMMANDS,
            scope=BotCommandScopeAllPrivateChats(),
        )
    except Exception:
        logger.exception("Не удалось установить меню команд анонимного бота (set_my_commands)")
