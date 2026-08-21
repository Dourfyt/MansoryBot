"""Лог обработки апдейтов с chat_id / названием группы (вместо голого aiogram.event)."""
from __future__ import annotations

import logging
import time
from typing import Any, Optional, Tuple

from aiogram import Dispatcher
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.enums import ContentType
from aiogram.types import Message, Update

logger = logging.getLogger("bot.update")


def chat_from_update(update: Update) -> Tuple[Optional[int], Optional[str]]:
    """chat_id и отображаемое имя чата из любого типа апдейта."""
    chat = None
    for attr in (
        "message",
        "edited_message",
        "channel_post",
        "edited_channel_post",
    ):
        msg = getattr(update, attr, None)
        if msg is not None:
            chat = msg.chat
            break
    if chat is None and update.callback_query and update.callback_query.message:
        chat = update.callback_query.message.chat
    if chat is None:
        return None, None
    label = (chat.title or chat.username or chat.first_name or "").strip() or None
    return chat.id, label


def _message_content_label(message: Message) -> str:
    """Тип содержимого сообщения: photo, text, document, …"""
    ct = message.content_type
    if ct == ContentType.PHOTO:
        return "photo"
    if ct == ContentType.TEXT:
        text = (message.text or "").strip()
        if text.startswith("/"):
            return "command"
        return "text"
    if ct == ContentType.DOCUMENT:
        mime = (message.document.mime_type or "") if message.document else ""
        if mime.startswith("image/"):
            return "document_image"
        return "document"
    if hasattr(ct, "value"):
        return str(ct.value)
    return str(ct)


def describe_update(update: Update) -> Tuple[str, Optional[str]]:
    """
    Тип апдейта и содержимое.
    update_kind: message, callback_query, edited_message, …
    content: photo, text, command, callback, …
    """
    if update.message:
        return "message", _message_content_label(update.message)
    if update.edited_message:
        return "edited_message", _message_content_label(update.edited_message)
    if update.channel_post:
        return "channel_post", _message_content_label(update.channel_post)
    if update.edited_channel_post:
        return "edited_channel_post", _message_content_label(update.edited_channel_post)
    if update.callback_query:
        data = (update.callback_query.data or "").strip()
        if len(data) > 48:
            data = data[:48] + "…"
        return "callback_query", f"callback:{data}" if data else "callback"
    if update.inline_query:
        q = (update.inline_query.query or "").strip()[:40]
        return "inline_query", q or None
    if update.my_chat_member:
        return "my_chat_member", str(update.my_chat_member.new_chat_member.status)
    if update.chat_member:
        return "chat_member", str(update.chat_member.new_chat_member.status)
    if update.chat_join_request:
        return "chat_join_request", None
    if update.message_reaction:
        return "message_reaction", None
    if update.message_reaction_count:
        return "message_reaction_count", None
    if update.poll:
        return "poll", None
    if update.poll_answer:
        return "poll_answer", None
    dumped = update.model_dump(exclude_none=True)
    if dumped:
        return next(iter(dumped.keys())), None
    return "unknown", None


def register_update_logging(dp: Dispatcher, *, bot_id: int | None = None) -> None:
    """
    Подменяет INFO-логи aiogram.event строкой с chat_id / chat_title.
    """
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)

    @dp.update.outer_middleware()
    async def log_update_with_chat(handler, event: Update, data: dict[str, Any]):
        if not isinstance(event, Update):
            return await handler(event, data)

        start = time.perf_counter()
        handled = False
        had_error = False
        try:
            response = await handler(event, data)
            handled = response is not UNHANDLED
            return response
        except Exception:
            had_error = True
            raise
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            chat_id, chat_title = chat_from_update(event)
            update_kind, content = describe_update(event)
            bid = bot_id
            if bid is None:
                bot_obj = data.get("bot")
                bid = getattr(bot_obj, "id", None) if bot_obj is not None else None

            if had_error:
                status = "error"
            elif handled:
                status = "handled"
            else:
                status = "not handled"

            parts = [
                f"Update id={event.update_id}",
                f"is {status}",
                f"Duration {duration_ms} ms",
            ]
            if bid is not None:
                parts.append(f"by bot id={bid}")
            if chat_id is not None:
                parts.append(f"chat_id={chat_id}")
            if chat_title:
                parts.append(f"chat_title={chat_title!r}")
            parts.append(f"update_kind={update_kind}")
            if content:
                parts.append(f"content={content!r}")

            logger.info(" ".join(parts))
