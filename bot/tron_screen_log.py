"""Структурированные логи пайплайна Tron-скринов и выплат."""
from __future__ import annotations

import logging
from typing import Any, Optional

from aiogram.types import Message

from .tron_screen_parse import TronScreenHints

logger = logging.getLogger(__name__)


def _chat_title(message: Message) -> Optional[str]:
    chat = message.chat
    if not chat:
        return None
    title = getattr(chat, "title", None)
    return str(title).strip() if title else None


def log_tron_screen(
    message: Message,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Единый формат: chat, msg, user, event, детали."""
    parts: list[str] = [f"event={event}"]
    if message.chat:
        parts.append(f"chat_id={message.chat.id}")
        title = _chat_title(message)
        if title:
            parts.append(f"chat_title={title!r}")
    if message.message_id is not None:
        parts.append(f"message_id={message.message_id}")
    if message.from_user:
        parts.append(f"user_id={message.from_user.id}")
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, str) and len(value) > 200:
            value = value[:200] + "…"
        parts.append(f"{key}={value!r}")
    logger.log(level, "Tron screen: %s", " ".join(parts))


def log_tron_hints(message: Message, event: str, hints: TronScreenHints) -> None:
    log_tron_screen(
        message,
        event,
        expected_amount=hints.expected_amount,
        tx_hash=(hints.tx_hash[:16] + "…") if hints.tx_hash else None,
        sending=(hints.sending_address[:8] + "…") if hints.sending_address else None,
        receiving=(hints.receiving_address[:8] + "…") if hints.receiving_address else None,
        created_at_ms=hints.created_at_ms,
    )
