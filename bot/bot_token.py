"""Активный токен Telegram: приоритет БД (bot_instances), иначе BOT_TOKEN из окружения."""
from __future__ import annotations

import logging
import os
logger = logging.getLogger(__name__)


def resolve_bot_token() -> str:
    """Токен из bot_instances id=1, если задан; иначе BOT_TOKEN / GROUP_CONNECTOR_BOT_TOKEN."""
    try:
        from bot.pg import connection

        with connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT telegram_bot_token FROM bot_instances
                WHERE id = 1 AND COALESCE(is_active, 1) = 1
                """
            )
            row = cur.fetchone()
            if row and row[0]:
                t = str(row[0]).strip()
                if t:
                    return t
    except Exception as e:
        logger.debug("resolve_bot_token: DB: %s", e)

    env = os.environ.get("BOT_TOKEN", "").strip() or os.environ.get(
        "GROUP_CONNECTOR_BOT_TOKEN", ""
    ).strip()
    if env:
        return env
    raise RuntimeError(
        "Нет токена бота: задайте telegram_bot_token в bot_instances (id=1) или BOT_TOKEN в окружении"
    )

