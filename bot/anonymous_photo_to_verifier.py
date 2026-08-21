"""Отправка фото с /п из анонимного ЛС в группу проверяющих (как /п в группе клиентов).

Основной бот: пересылка напрямую. Дочерний бот: байты фото → HTTP на процесс основного бота
(колбэки и /чек в группе проверяющих остаются у основного бота).
"""
from __future__ import annotations

import json
import logging
import os
from io import BytesIO
from typing import Optional

import aiohttp
from aiogram.types import Message

from bot.anonymous_chat import (
    get_relay_display_name,
    get_verifier_group_id_for_room,
    resolve_anonymous_room_for_dm,
    save_anonymous_verifier_notify_targets,
)
from bot import ui_copy as ui
from bot.anonymous_relay_handlers import _relay_anonymous_to_peers

logger = logging.getLogger(__name__)

_DEFAULT_RELAY = "http://127.0.0.1:8765/broadcast/relay-anonymous-photo-check"


def _relay_url() -> str:
    u = (os.environ.get("BROADCAST_RELAY_URL") or "").strip()
    return u if u else _DEFAULT_RELAY


async def _relay_photo_via_main_http(
    message: Message, verifier_group_id: int, anonymous_chat_id: int
) -> None:
    if not message.from_user or not message.photo:
        return

    buf = BytesIO()
    await message.bot.download(message.photo[-1], destination=buf)
    raw = buf.getvalue()

    url = _relay_url()
    headers: dict[str, str] = {}
    secret = (os.environ.get("BROADCAST_INTERNAL_SECRET") or "").strip()
    if secret:
        headers["X-Internal-Secret"] = secret

    data = aiohttp.FormData()
    data.add_field("user_id", str(message.from_user.id))
    data.add_field("verifier_group_id", str(verifier_group_id))
    data.add_field("anonymous_chat_id", str(anonymous_chat_id))
    data.add_field("original_message_id", str(message.message_id))
    data.add_field(
        "photo",
        raw,
        filename="check.jpg",
        content_type="image/jpeg",
    )

    try:
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=data, headers=headers) as resp:
                text = await resp.text()
                try:
                    body: Optional[dict] = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    body = None
                if resp.status != 200:
                    err = ""
                    if isinstance(body, dict):
                        err = (body.get("error") or "").strip()
                    if not err:
                        err = text[:500] if text else f"HTTP {resp.status}"
                    await message.answer(err)
                    return
    except aiohttp.ClientError as e:
        logger.exception("Relay /п на основной бот: %s", e)
        await message.answer(
            "Не удалось связаться с основным ботом. Убедитесь, что сервис основного бота запущен "
            "и для контейнера дочерних ботов задан BROADCAST_RELAY_URL."
        )
        return
    except Exception as e:
        logger.exception("Ошибка relay /п: %s", e)
        await message.answer(f"Не удалось отправить фото в группу проверяющих: {e}")
        return

    await message.answer("Фото чека отправлено на проверку!")


async def handle_anonymous_photo_check_command(
    message: Message,
    *,
    master_mode: bool,
    child_room_id: Optional[int] = None,
) -> None:
    """Обработать /п с фото в ЛС анонимной комнаты. Если группа проверяющих не задана — только релей пирам."""
    if not message.from_user or not message.photo:
        return

    room_id = resolve_anonymous_room_for_dm(message.from_user.id, child_room_id)
    if not room_id:
        return

    verifier_group_id = get_verifier_group_id_for_room(room_id)
    if not verifier_group_id:
        nick = get_relay_display_name(message.from_user.id, room_id)
        if nick:
            await _relay_anonymous_to_peers(message, nick, room_id)
        return

    if not master_mode:
        await _relay_photo_via_main_http(message, verifier_group_id, room_id)
        return

    import group_connector_bot as gcb

    rv_markup = gcb.receipt_verification_keyboard(message.chat.id, message.message_id)
    try:
        bot_info = await gcb.bot.get_me()
        chat_member = await gcb.bot.get_chat_member(verifier_group_id, bot_info.id)
        if chat_member.status in ("left", "kicked"):
            await message.answer(
                f"Бот не в группе проверяющих (статус: {chat_member.status}). Добавьте бота в группу."
            )
            return
    except Exception as e:
        logger.warning("Проверка бота в группе проверяющих: %s", e)

    try:
        sent_photo = await gcb.safe_send_photo(
            gcb.bot,
            verifier_group_id,
            message.photo[-1].file_id,
            caption=ui.CAPTION_VERIFY,
            reply_markup=rv_markup,
        )
        gcb.message_links[(message.chat.id, message.message_id)] = (
            verifier_group_id,
            sent_photo.message_id,
            room_id,
        )
        nick = get_relay_display_name(message.from_user.id, room_id)
        if nick:
            targets = await _relay_anonymous_to_peers(message, nick, room_id)
            if targets:
                save_anonymous_verifier_notify_targets(
                    room_id, message.from_user.id, message.message_id, targets
                )
        await message.answer(f"{ui.LBL_VERIFIED}: чек ушёл на проверку")
    except Exception as e:
        logger.exception("Ошибка пересылки /п из анонимного чата: %s", e)
        await message.answer(f"Не удалось отправить фото в группу проверяющих: {e}")
