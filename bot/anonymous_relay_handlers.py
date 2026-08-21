"""Анонимные чаты: релей, инвайты, команды. Обработчики регистрируются только на дочерних ботах (anonymous_child_runner)."""
from __future__ import annotations

import logging
import os
import tempfile
import uuid
from html import escape as html_escape
from datetime import datetime
from typing import Any, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import BaseFilter, CommandObject, StateFilter

from bot.filters_cmd import Cmd, CmdStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.group_queries import format_ts_ru_msk

from bot.anonymous_chat import (
    anonymous_today_msk_date_str,
    build_anonymous_cheki_today_html,
    build_anonymous_info_snapshot,
    complete_join_after_nickname,
    count_anonymous_room_members,
    generate_random_nickname_options,
    count_anonymous_receipts_today,
    delete_all_relayed_for_sender,
    delete_anonymous_receipt,
    delete_last_relayed_for_sender,
    format_anonymous_info_html,
    format_relay_line,
    format_relay_media_caption,
    get_child_bot_username_for_room,
    get_peer_telegram_ids,
    get_relay_display_name,
    list_member_telegram_ids_for_room,
    insert_anonymous_receipt,
    resolve_anonymous_room_for_dm,
    try_switch_active_room_by_invite_token,
    is_anonymous_room_crm_owner,
    is_anonymous_room_support_admin,
    leave_room,
    lookup_relay_dm_reply_context,
    lookup_valid_invite,
    record_anonymous_message,
    record_relay_delivery,
    relay_reply_target_message_id_for_peer,
    reset_anonymous_room_by_staff,
    room_has_child_bot,
)
from bot.config import ADMINS, ANONYMOUS_CHATS_ENABLED
from bot import ui_copy as ui
from bot.chek_parse import ChekCommandFilter, parse_chek_message
from bot.ui_copy import CHEK_FORMAT_HINT, format_money
from bot.custom_emojis import e_receipt, plain_receipt_prefix

logger = logging.getLogger(__name__)

_ANON_PRIVATE_COMMAND_NAMES = frozenset({
    "п",
    "leave",
    "выйти",
    "чек",
    "+",
    "-",
    "удалить_чек",
    "сброс",
    "reset",
    "инфо",
    "info",
    "чеки_сегодня",
    "cheki_segodnya",
    "помощь",
    "delete",
    "delete_all",
    "deleteall",
})


def is_anonymous_private_command(text: str) -> bool:
    """Команды анонимного чата в ЛС (без ответа, если фича выключена)."""
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return False
    token = raw.split(maxsplit=1)[0]
    if "@" in token:
        token = token.split("@", 1)[0]
    name = (token[1:] if token.startswith("/") else token).casefold()
    if name == "start":
        return len(raw.split(maxsplit=1)) > 1 and bool(raw.split(maxsplit=1)[1].strip())
    return name in _ANON_PRIVATE_COMMAND_NAMES
_MSK = ZoneInfo("Europe/Moscow")

NICKNAME_OPTIONS_COUNT = 5

_NICK_JOIN_PROMPT = ui.ANON_NICK_PROMPT


def _nickname_invite_keyboard(invite_id: int, options: List[str]) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for i, opt in enumerate(options):
        label = opt if len(opt) <= 64 else opt[:61] + "…"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"anp:{invite_id}:{i}")])
    rows.append([InlineKeyboardButton(text="Другие варианты", callback_data=f"anr:{invite_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _welcome_anon_room_text(nick: str) -> str:
    return (
        f"{ui.ANON_WELCOME_INTRO.format(nick=html_escape(nick))}\n\n"
        f"{ui.ANON_HELP_HTML}"
    )


async def _notify_room_anonymous_join(
    bot: Any,
    room_id: int,
    nickname: str,
    member_count: int,
) -> None:
    """Всем участникам комнаты (включая вошедшего): кто вошёл и сколько человек в чате."""
    text = ui.ANON_JOIN_NOTIFY.format(
        nick=html_escape(nickname),
        count=member_count,
    )
    for uid in list_member_telegram_ids_for_room(room_id):
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
        except Exception:
            logging.exception("Уведомление о входе в анонимный чат uid=%s", uid)


class AnonymousChatStates(StatesGroup):
    waiting_nickname = State()


class AnonymousRoomFilter(BaseFilter):
    def __init__(self, child_room_id: Optional[int] = None):
        self.child_room_id = child_room_id

    async def __call__(self, message: Message) -> bool:
        if message.chat.type != "private" or not message.from_user:
            return False
        return (
            resolve_anonymous_room_for_dm(message.from_user.id, self.child_room_id) is not None
        )


class AnonymousPlainPhotoAsCheckFilter(BaseFilter):
    """Фото без команды в подписи: сценарий «как /п». Подпись /п обрабатывает Cmd('п') выше по цепочке."""

    def __init__(self, child_room_id: Optional[int] = None):
        self.child_room_id = child_room_id

    async def __call__(self, message: Message) -> bool:
        if message.chat.type != "private" or not message.from_user or not message.photo:
            return False
        room_id = resolve_anonymous_room_for_dm(message.from_user.id, self.child_room_id)
        if room_id is None:
            return False
        uid = message.from_user.id
        if uid in ADMINS or is_anonymous_room_support_admin(room_id, uid):
            return False
        cap = (message.caption or "").strip()
        if cap.startswith("/"):
            return False
        return True


def _anonymous_message_body(message: Message) -> str:
    if message.text:
        return message.text.strip()
    if message.caption:
        return message.caption.strip()
    if message.photo:
        return "[фото]"
    if message.document:
        return "[документ]"
    if message.sticker:
        return "[стикер]"
    if message.voice:
        return "[голосовое]"
    if message.video:
        return "[видео]"
    if message.pinned_message is not None:
        return _anonymous_history_line(message)
    return "[сообщение]"


def _anonymous_history_line(message: Message) -> str:
    if message.pinned_message is not None:
        inner = _anonymous_history_line(message.pinned_message)
        return f"Закрепил: {inner}"[:8000]
    if message.text:
        return message.text.strip()[:8000]
    if message.photo:
        c = (message.caption or "").strip()
        return (f"Фото: {c}" if c else "Фото")[:8000]
    if message.document:
        fn = (message.document.file_name or "файл").strip()
        c = (message.caption or "").strip()
        base = f"Документ «{fn}»"
        return (f"{base}: {c}" if c else base)[:8000]
    if message.video:
        c = (message.caption or "").strip()
        return (f"Видео: {c}" if c else "Видео")[:8000]
    if message.animation:
        c = (message.caption or "").strip()
        return (f"GIF: {c}" if c else "GIF")[:8000]
    if message.voice:
        c = (message.caption or "").strip()
        return (f"Голосовое: {c}" if c else "Голосовое сообщение")[:8000]
    if message.audio:
        c = (message.caption or "").strip()
        t = (message.audio.title or message.audio.file_name or "аудио").strip()
        return (f"Аудио «{t}»: {c}" if c else f"Аудио «{t}»")[:8000]
    if message.video_note:
        return "Видеосообщение (кружок)"
    if message.sticker:
        e = message.sticker.emoji or ""
        return f"Стикер{e}"
    return (_anonymous_message_body(message))[:8000]


async def _relay_send_message(
    tg_bot: Any, peer_id: int, text: str, reply_to_message_id: Optional[int]
) -> Any:
    if reply_to_message_id is not None:
        try:
            return await tg_bot.send_message(
                peer_id, text, parse_mode="HTML", reply_to_message_id=reply_to_message_id
            )
        except Exception:
            logging.exception("relay send_message reply_to peer=%s", peer_id)
    return await tg_bot.send_message(peer_id, text, parse_mode="HTML")


async def _relay_send_photo(
    tg_bot: Any,
    peer_id: int,
    file_id: str,
    caption: str,
    reply_to_message_id: Optional[int],
) -> Any:
    if reply_to_message_id is not None:
        try:
            return await tg_bot.send_photo(
                peer_id,
                file_id,
                caption=caption,
                parse_mode="HTML",
                reply_to_message_id=reply_to_message_id,
            )
        except Exception:
            logging.exception("relay send_photo reply_to peer=%s", peer_id)
    return await tg_bot.send_photo(peer_id, file_id, caption=caption, parse_mode="HTML")


async def _relay_send_document(
    tg_bot: Any,
    peer_id: int,
    file_id: str,
    caption: str,
    reply_to_message_id: Optional[int],
) -> Any:
    if reply_to_message_id is not None:
        try:
            return await tg_bot.send_document(
                peer_id,
                file_id,
                caption=caption,
                parse_mode="HTML",
                reply_to_message_id=reply_to_message_id,
            )
        except Exception:
            logging.exception("relay send_document reply_to peer=%s", peer_id)
    return await tg_bot.send_document(peer_id, file_id, caption=caption, parse_mode="HTML")


async def _relay_send_video(
    tg_bot: Any,
    peer_id: int,
    file_id: str,
    caption: str,
    reply_to_message_id: Optional[int],
) -> Any:
    if reply_to_message_id is not None:
        try:
            return await tg_bot.send_video(
                peer_id,
                file_id,
                caption=caption,
                parse_mode="HTML",
                reply_to_message_id=reply_to_message_id,
            )
        except Exception:
            logging.exception("relay send_video reply_to peer=%s", peer_id)
    return await tg_bot.send_video(peer_id, file_id, caption=caption, parse_mode="HTML")


async def _relay_send_animation(
    tg_bot: Any,
    peer_id: int,
    file_id: str,
    caption: str,
    reply_to_message_id: Optional[int],
) -> Any:
    if reply_to_message_id is not None:
        try:
            return await tg_bot.send_animation(
                peer_id,
                file_id,
                caption=caption,
                parse_mode="HTML",
                reply_to_message_id=reply_to_message_id,
            )
        except Exception:
            logging.exception("relay send_animation reply_to peer=%s", peer_id)
    return await tg_bot.send_animation(peer_id, file_id, caption=caption, parse_mode="HTML")


async def _relay_send_voice(
    tg_bot: Any,
    peer_id: int,
    file_id: str,
    caption: str,
    reply_to_message_id: Optional[int],
) -> Any:
    if reply_to_message_id is not None:
        try:
            return await tg_bot.send_voice(
                peer_id,
                file_id,
                caption=caption,
                parse_mode="HTML",
                reply_to_message_id=reply_to_message_id,
            )
        except Exception:
            logging.exception("relay send_voice reply_to peer=%s", peer_id)
    return await tg_bot.send_voice(peer_id, file_id, caption=caption, parse_mode="HTML")


async def _relay_send_audio(
    tg_bot: Any,
    peer_id: int,
    file_id: str,
    caption: str,
    reply_to_message_id: Optional[int],
) -> Any:
    if reply_to_message_id is not None:
        try:
            return await tg_bot.send_audio(
                peer_id,
                file_id,
                caption=caption,
                parse_mode="HTML",
                reply_to_message_id=reply_to_message_id,
            )
        except Exception:
            logging.exception("relay send_audio reply_to peer=%s", peer_id)
    return await tg_bot.send_audio(peer_id, file_id, caption=caption, parse_mode="HTML")


async def _relay_send_video_note(
    tg_bot: Any, peer_id: int, file_id: str, reply_to_message_id: Optional[int]
) -> Any:
    if reply_to_message_id is not None:
        try:
            return await tg_bot.send_video_note(
                peer_id, file_id, reply_to_message_id=reply_to_message_id
            )
        except Exception:
            logging.exception("relay send_video_note reply_to peer=%s", peer_id)
    return await tg_bot.send_video_note(peer_id, file_id)


async def _relay_send_sticker(
    tg_bot: Any, peer_id: int, file_id: str, reply_to_message_id: Optional[int]
) -> Any:
    if reply_to_message_id is not None:
        try:
            return await tg_bot.send_sticker(peer_id, file_id, reply_to_message_id=reply_to_message_id)
        except Exception:
            logging.exception("relay send_sticker reply_to peer=%s", peer_id)
    return await tg_bot.send_sticker(peer_id, file_id)


async def _relay_anonymous_to_peers(message: Message, nick: str, room_id: int) -> List[Tuple[int, int]]:
    """Релей сообщения участникам. Возвращает (peer_id, message_id) для reply при уведомлениях о /п."""
    tg_bot = message.bot
    uid = message.from_user.id if message.from_user else 0
    out: List[Tuple[int, int]] = []

    relay_broadcast_id = str(uuid.uuid4())
    reply_ctx: Optional[Tuple[int, Optional[int], Optional[str]]] = None
    if message.reply_to_message:
        reply_ctx = lookup_relay_dm_reply_context(
            room_id, uid, message.reply_to_message.message_id
        )

    async def _rec(peer_id: int, mid: int) -> None:
        record_relay_delivery(
            room_id,
            uid,
            peer_id,
            mid,
            source_message_id=message.message_id,
            relay_broadcast_id=relay_broadcast_id,
        )

    for peer_id in get_peer_telegram_ids(room_id, uid):
        rid = relay_reply_target_message_id_for_peer(room_id, peer_id, reply_ctx)
        try:
            if message.text:
                sm = await _relay_send_message(
                    tg_bot,
                    peer_id,
                    format_relay_line(nick, message.text.strip()),
                    rid,
                )
                await _rec(peer_id, sm.message_id)
                out.append((peer_id, sm.message_id))
            elif message.pinned_message is not None:
                body = _anonymous_history_line(message)
                sm = await _relay_send_message(
                    tg_bot, peer_id, format_relay_line(nick, body), rid
                )
                await _rec(peer_id, sm.message_id)
                out.append((peer_id, sm.message_id))
            elif message.photo:
                cap = format_relay_media_caption(nick, message.caption)
                sm = await _relay_send_photo(
                    tg_bot, peer_id, message.photo[-1].file_id, cap, rid
                )
                await _rec(peer_id, sm.message_id)
                out.append((peer_id, sm.message_id))
            elif message.document:
                cap = format_relay_media_caption(nick, message.caption)
                sm = await _relay_send_document(
                    tg_bot, peer_id, message.document.file_id, cap, rid
                )
                await _rec(peer_id, sm.message_id)
                out.append((peer_id, sm.message_id))
            elif message.video:
                cap = format_relay_media_caption(nick, message.caption)
                sm = await _relay_send_video(
                    tg_bot, peer_id, message.video.file_id, cap, rid
                )
                await _rec(peer_id, sm.message_id)
                out.append((peer_id, sm.message_id))
            elif message.animation:
                cap = format_relay_media_caption(nick, message.caption)
                sm = await _relay_send_animation(
                    tg_bot, peer_id, message.animation.file_id, cap, rid
                )
                await _rec(peer_id, sm.message_id)
                out.append((peer_id, sm.message_id))
            elif message.voice:
                cap = format_relay_media_caption(nick, message.caption)
                sm = await _relay_send_voice(
                    tg_bot, peer_id, message.voice.file_id, cap, rid
                )
                await _rec(peer_id, sm.message_id)
                out.append((peer_id, sm.message_id))
            elif message.audio:
                cap = format_relay_media_caption(nick, message.caption)
                sm = await _relay_send_audio(
                    tg_bot, peer_id, message.audio.file_id, cap, rid
                )
                await _rec(peer_id, sm.message_id)
                out.append((peer_id, sm.message_id))
            elif message.video_note:
                sm1 = await _relay_send_message(
                    tg_bot,
                    peer_id,
                    format_relay_media_caption(nick, None),
                    rid,
                )
                await _rec(peer_id, sm1.message_id)
                sm2 = await _relay_send_video_note(
                    tg_bot, peer_id, message.video_note.file_id, None
                )
                await _rec(peer_id, sm2.message_id)
                out.append((peer_id, sm2.message_id))
            elif message.sticker:
                sm1 = await _relay_send_message(
                    tg_bot,
                    peer_id,
                    format_relay_media_caption(nick, None),
                    rid,
                )
                await _rec(peer_id, sm1.message_id)
                sm2 = await _relay_send_sticker(tg_bot, peer_id, message.sticker.file_id, None)
                await _rec(peer_id, sm2.message_id)
                out.append((peer_id, sm2.message_id))
            else:
                body = _anonymous_message_body(message)
                if not body:
                    body = "[сообщение]"
                sm = await _relay_send_message(
                    tg_bot, peer_id, format_relay_line(nick, body), rid
                )
                await _rec(peer_id, sm.message_id)
                out.append((peer_id, sm.message_id))
        except Exception:
            logging.exception("Релей анонимного чата peer=%s", peer_id)
    if message.from_user:
        try:
            record_anonymous_message(
                room_id,
                message.from_user.id,
                nick,
                _anonymous_history_line(message),
            )
        except Exception:
            logging.exception("Запись истории анонимного чата")
    return out


async def relay_anonymous_photo_bytes_to_peers(
    tg_bot,
    room_id: int,
    from_telegram_user_id: int,
    nick: str,
    file_bytes: bytes,
    filename: str = "check.jpg",
    *,
        source_message_id: Optional[int] = None,
) -> List[Tuple[int, int]]:
    """Тот же релей фото, что и /п, но из байтов (основной бот после relay HTTP)."""
    out: List[Tuple[int, int]] = []
    cap = format_relay_media_caption(nick, None)
    relay_broadcast_id = str(uuid.uuid4())
    for peer_id in get_peer_telegram_ids(room_id, from_telegram_user_id):
        try:
            buf = BufferedInputFile(file_bytes, filename=filename)
            sm = await tg_bot.send_photo(peer_id, buf, caption=cap, parse_mode="HTML")
            record_relay_delivery(
                room_id,
                from_telegram_user_id,
                peer_id,
                sm.message_id,
                source_message_id=source_message_id,
                relay_broadcast_id=relay_broadcast_id,
            )
            out.append((peer_id, sm.message_id))
        except Exception:
            logging.exception("Релей фото /п (bytes) peer=%s", peer_id)
    return out


async def _relay_receipt_added_to_peers(
    message: Message,
    room_id: int,
    receipt_no: int,
    amount: float,
    timestamp: str,
) -> None:
    """Уведомляет остальных участников комнаты о добавленном чеке (аналог релея текста)."""
    if not message.from_user:
        return
    uid = message.from_user.id
    nick = get_relay_display_name(uid, room_id)
    if not nick:
        return
    sign = "добавлен" if amount > 0 else "учтён"
    body_plain = f"{plain_receipt_prefix()} Чек №{receipt_no} на {format_money(amount)} {sign} ({timestamp})"
    body_html = f"{e_receipt()} Чек №{receipt_no} на {format_money(amount)} {sign} ({timestamp})"
    html_line = f"<b>{html_escape(nick)}</b>: {body_html}"
    tg_bot = message.bot
    for peer_id in get_peer_telegram_ids(room_id, uid):
        try:
            await tg_bot.send_message(peer_id, html_line, parse_mode="HTML")
        except Exception:
            logging.exception("Уведомление о чеке peer=%s", peer_id)
    try:
        record_anonymous_message(room_id, uid, nick, body_plain)
    except Exception:
        logging.exception("История CRM после /чек")


async def try_anonymous_private_message(
    message: Message, *, master_mode: bool, child_room_id: Optional[int] = None
) -> bool:
    """Обработка ЛС в анонимной комнате. True — дальше support не вызывать."""
    if not message.from_user:
        return False
    if not ANONYMOUS_CHATS_ENABLED:
        if message.text and is_anonymous_private_command(message.text):
            return True
        return False
    # Основной бот не ведёт комнаты с дочерним ботом — только подсказка.
    if master_mode and child_room_id is None:
        room_id = resolve_anonymous_room_for_dm(message.from_user.id, None)
        if room_id and room_has_child_bot(room_id):
            un = get_child_bot_username_for_room(room_id)
            if un:
                await message.answer(
                    f"Эта комната в отдельном боте — напишите в @{un}."
                )
            else:
                await message.answer(
                    "Эта комната в отдельном боте — откройте его по приглашению."
                )
            return True
        if not room_id:
            return False
        # Комната на мастер-боте (без child) — релей ниже.
    else:
        room_id = resolve_anonymous_room_for_dm(message.from_user.id, child_room_id)
        if not room_id:
            return False
    if message.text and message.text.startswith("/"):
        return True
    nick = get_relay_display_name(message.from_user.id, room_id)
    if nick:
        await _relay_anonymous_to_peers(message, nick, room_id)
    return True


def register_anonymous_handlers(
    router: Router,
    *,
    master_mode: bool,
    include_private_catchall: bool,
    child_room_id: Optional[int] = None,
) -> None:
    """Регистрация обработчиков (только процесс дочернего бота: child_room_id = комната процесса)."""
    arf = AnonymousRoomFilter(child_room_id=child_room_id)
    plain_photo_filter = AnonymousPlainPhotoAsCheckFilter(child_room_id=child_room_id)

    @router.message(CmdStart(deep_link=True), F.chat.type == "private")
    async def cmd_start_anonymous_invite(message: Message, command: CommandObject, state: FSMContext):
        if not message.from_user:
            return
        token = (command.args or "").strip()
        if not token:
            return
        if master_mode and child_room_id is None:
            switched = try_switch_active_room_by_invite_token(message.from_user.id, token)
            if switched is not None:
                await message.answer(
                    "Комната переключена. Можно писать."
                )
                return
        found = lookup_valid_invite(token)
        if not found:
            await message.answer("Ссылка недействительна, уже использована или истекла.")
            return
        invite_id, room_id = found
        if child_room_id is not None and int(room_id) != int(child_room_id):
            await message.answer(
                "Эта ссылка к другому боту. Возьмите приглашение из настроек нужной комнаты."
            )
            return
        if master_mode and room_has_child_bot(room_id):
            un = get_child_bot_username_for_room(room_id)
            if un:
                await message.answer(
                    f"Комната в отдельном боте — откройте @{un} по ссылке из приглашения."
                )
            else:
                await message.answer(
                    "Комната в отдельном боте — откройте его по ссылке из приглашения."
                )
            return
        options = generate_random_nickname_options(NICKNAME_OPTIONS_COUNT)
        await state.set_state(AnonymousChatStates.waiting_nickname)
        await state.update_data(pending_invite_id=invite_id, nickname_choices=options)
        await message.answer(
            _NICK_JOIN_PROMPT,
            reply_markup=_nickname_invite_keyboard(invite_id, options),
            parse_mode="HTML",
        )

    @router.callback_query(F.data.startswith("anp:"), StateFilter(AnonymousChatStates.waiting_nickname))
    async def anonymous_nickname_pick(query: CallbackQuery, state: FSMContext):
        if not query.from_user or not query.message:
            await query.answer()
            return
        parts = (query.data or "").split(":")
        if len(parts) != 3:
            await query.answer()
            return
        try:
            invite_id = int(parts[1])
            idx = int(parts[2])
        except ValueError:
            await query.answer()
            return
        data = await state.get_data()
        if data.get("pending_invite_id") != invite_id:
            await query.answer("Сессия устарела. Откройте приглашение снова.", show_alert=True)
            return
        choices = data.get("nickname_choices") or []
        if idx < 0 or idx >= len(choices):
            await query.answer("Список устарел. Откройте приглашение снова или обновите варианты.", show_alert=True)
            return
        nick = choices[idx]
        try:
            _room_id, nick = complete_join_after_nickname(invite_id, query.from_user.id, nick)
        except ValueError as e:
            err = str(e)
            if err == "nickname_length":
                await query.answer("Ошибка никнейма.", show_alert=True)
            else:
                await query.answer("Ссылка недействительна или уже использована.", show_alert=True)
            await state.clear()
            return
        await query.answer()
        await state.clear()
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            logging.exception("Снятие клавиатуры после выбора ника")
        member_count = count_anonymous_room_members(_room_id)
        await query.message.answer(_welcome_anon_room_text(nick), parse_mode="HTML")
        await _notify_room_anonymous_join(query.message.bot, _room_id, nick, member_count)

    @router.callback_query(F.data.startswith("anr:"), StateFilter(AnonymousChatStates.waiting_nickname))
    async def anonymous_nickname_refresh_options(query: CallbackQuery, state: FSMContext):
        if not query.message:
            await query.answer()
            return
        parts = (query.data or "").split(":")
        if len(parts) != 2:
            await query.answer()
            return
        try:
            invite_id = int(parts[1])
        except ValueError:
            await query.answer()
            return
        data = await state.get_data()
        if data.get("pending_invite_id") != invite_id:
            await query.answer("Сессия устарела. Откройте приглашение снова.", show_alert=True)
            return
        options = generate_random_nickname_options(NICKNAME_OPTIONS_COUNT)
        await state.update_data(nickname_choices=options)
        await query.answer()
        try:
            await query.message.edit_text(
                _NICK_JOIN_PROMPT,
                reply_markup=_nickname_invite_keyboard(invite_id, options),
            )
        except Exception:
            logging.exception("Обновление вариантов ника")

    @router.message(StateFilter(AnonymousChatStates.waiting_nickname), F.chat.type == "private")
    async def anonymous_chat_nickname_no_free_text(message: Message, state: FSMContext):
        if not message.from_user:
            return
        if message.text and message.text.startswith("/"):
            return
        await message.answer(
            "Имя только из списка — нажмите кнопку под сообщением выше или «Другие варианты»."
        )

    @router.message(Cmd("п"), F.chat.type == "private", arf, F.photo)
    async def cmd_anonymous_photo_check(message: Message):
        from bot.anonymous_photo_to_verifier import handle_anonymous_photo_check_command

        if not message.from_user:
            return
        room_id = resolve_anonymous_room_for_dm(message.from_user.id, child_room_id)
        if not room_id:
            return
        uid = message.from_user.id
        if uid in ADMINS or is_anonymous_room_support_admin(room_id, uid):
            nick = get_relay_display_name(uid, room_id)
            if nick:
                await _relay_anonymous_to_peers(message, nick, room_id)
            return
        await handle_anonymous_photo_check_command(
            message, master_mode=master_mode, child_room_id=child_room_id
        )

    @router.message(Cmd("п"), F.chat.type == "private", arf, ~F.photo)
    async def cmd_anonymous_p_no_photo(message: Message):
        await message.answer("Команда /п должна быть отправлена вместе с фото (подпись к фото может содержать /п).")

    @router.message(F.chat.type == "private", plain_photo_filter)
    async def anonymous_plain_photo_as_check(message: Message):
        """Фото без команды в подписи — тот же сценарий, что /п с фото (проверяющие + релей пирам)."""
        from bot.anonymous_photo_to_verifier import handle_anonymous_photo_check_command

        await handle_anonymous_photo_check_command(
            message, master_mode=master_mode, child_room_id=child_room_id
        )

    @router.message(Cmd("leave"), F.chat.type == "private")
    @router.message(Cmd("выйти"), F.chat.type == "private")
    async def cmd_leave_anonymous(message: Message, state: FSMContext):
        if not message.from_user:
            return
        await state.clear()
        uid = message.from_user.id
        # Дочерний бот: выходим из комнаты этого процесса (child_room_id), а не из «активной» в ЛС основного бота.
        rid = resolve_anonymous_room_for_dm(uid, child_room_id)
        if rid is None:
            await message.answer("Вы не в комнате.")
            return
        if leave_room(uid, rid):
            await message.answer("Вы вышли из комнаты.")
        else:
            await message.answer("Вы не в комнате.")

    @router.message(ChekCommandFilter(), F.chat.type == "private", arf)
    async def cmd_anonymous_chek(message: Message):
        if not message.from_user or not message.text:
            return
        try:
            amount, rate_value, percent_value = parse_chek_message(message.text)
        except ValueError:
            return await message.answer(CHEK_FORMAT_HINT)
        if rate_value is not None:
            return await message.answer(
                "Курс и процент в /чек доступны только в группах. "
                "В анонимном чате: /чек <сумма>."
            )
        room_id = resolve_anonymous_room_for_dm(message.from_user.id, child_room_id)
        if not room_id:
            return
        timestamp = format_ts_ru_msk(datetime.now(_MSK))
        no = insert_anonymous_receipt(room_id, message.from_user.id, amount)
        if no is None:
            return await message.answer("Комната недоступна.")
        sign = "добавлен" if amount > 0 else "учтён"
        await _relay_receipt_added_to_peers(message, room_id, no, amount, timestamp)
        return await message.answer(
            f"{e_receipt()} <b>№{no}</b> · <b>{format_money(amount)}</b> ({sign}) · <i>{timestamp}</i>",
            parse_mode="HTML",
        )

    @router.message(Cmd("удалить_чек"), F.chat.type == "private", arf)
    async def cmd_anonymous_delete_receipt(message: Message):
        if not message.from_user or not message.text:
            return
        room_id = resolve_anonymous_room_for_dm(message.from_user.id, child_room_id)
        if not room_id:
            return
        parts = message.text.split()
        if len(parts) != 2:
            return await message.answer(
                "Укажите номер чека в этой комнате, например: /удалить_чек 3"
            )
        try:
            receipt_no = int(parts[1])
        except ValueError:
            return await message.answer(
                "Номер чека должен быть целым числом, например: /удалить_чек 3"
            )
        uid = message.from_user.id
        force = (
            uid in ADMINS
            or is_anonymous_room_support_admin(room_id, uid)
            or is_anonymous_room_crm_owner(room_id, uid)
        )
        result = delete_anonymous_receipt(room_id, receipt_no, uid, force=force)
        if result == "ok":
            return await message.answer(f"Чек №{receipt_no} удалён.")
        if result == "not_found":
            return await message.answer(f"Чек №{receipt_no} не найден в этой комнате.")
        if result == "forbidden":
            return await message.answer(
                "Удалять чеки могут только администраторы бота, создатель этой комнаты и назначенные саппорты."
            )
        return await message.answer("Комната недоступна.")

    @router.message(Cmd("сброс", "reset"), F.chat.type == "private")
    async def cmd_anonymous_staff_reset(message: Message):
        """Сброс чеков в комнате (как reset_anonymous_receipts_for_room): админы и саппорты комнаты."""
        if not message.from_user:
            return
        uid = message.from_user.id
        txt = (message.text or "").strip()
        if message.bot and getattr(message.bot, "username", None):
            txt = txt.replace(f"@{message.bot.username}", "")
        parts = txt.split()
        explicit_room_id: Optional[int] = None
        if len(parts) >= 2:
            try:
                explicit_room_id = int(parts[1])
            except ValueError:
                pass

        room_id = resolve_anonymous_room_for_dm(uid, child_room_id)
        if room_id is None and child_room_id is not None and (
            uid in ADMINS or is_anonymous_room_support_admin(child_room_id, uid)
        ):
            room_id = child_room_id
        if room_id is None and explicit_room_id is not None:
            if uid in ADMINS or is_anonymous_room_support_admin(explicit_room_id, uid):
                room_id = explicit_room_id

        if room_id is None:
            return await message.answer(
                "Не удалось определить комнату. Будучи в чате по приглашению, отправьте /сброс "
                "или /reset. Саппорт и админ могут указать id: /сброс 12"
            )
        if uid not in ADMINS and not is_anonymous_room_support_admin(room_id, uid):
            return await message.answer(
                "Команду могут выполнять только администраторы бота и назначенные саппорты этой комнаты."
            )

        stats = reset_anonymous_room_by_staff(room_id)
        if stats is None:
            return await message.answer("Комната не найдена.")
        logging.info(
            "receipt_reset room_id=%s by uid=%s stats=%s",
            room_id,
            uid,
            stats,
        )
        return await message.answer(
            f"Чеки в комнате сброшены (удалено записей: {stats['receipts_removed']})."
        )

    @router.message(Cmd("удалить_чек"), F.chat.type == "private")
    async def cmd_delete_receipt_private_fallback(message: Message):
        if message.from_user and resolve_anonymous_room_for_dm(message.from_user.id, child_room_id):
            return
        return await message.answer("Команда доступна после входа по приглашению.")

    @router.message(ChekCommandFilter(), F.chat.type == "private")
    async def cmd_chek_private_fallback(message: Message):
        if message.from_user and resolve_anonymous_room_for_dm(message.from_user.id, child_room_id):
            return
        return await message.answer("Команда доступна после входа по приглашению.")

    @router.message(Cmd("инфо", "info"), F.chat.type == "private", arf)
    async def get_anonymous_info_cmd(message: Message):
        if not message.from_user:
            return
        room_id = resolve_anonymous_room_for_dm(message.from_user.id, child_room_id)
        if not room_id:
            return
        today = anonymous_today_msk_date_str()
        snap = build_anonymous_info_snapshot(room_id, today)
        if snap is None:
            return await message.answer("Ошибка: комната не найдена.")
        return await message.answer(format_anonymous_info_html(snap), parse_mode="HTML")

    @router.message(Cmd("инфо", "info"), F.chat.type == "private")
    async def cmd_info_private_fallback(message: Message):
        return await message.answer("Команда доступна после входа по приглашению.")

    @router.message(Cmd("чеки_сегодня", "cheki_segodnya"), F.chat.type == "private", arf)
    async def get_anonymous_all_today_receipts(message: Message):
        if not message.from_user:
            return
        room_id = resolve_anonymous_room_for_dm(message.from_user.id, child_room_id)
        if not room_id:
            return
        today = anonymous_today_msk_date_str()
        if count_anonymous_receipts_today(room_id, today) == 0:
            return await message.answer("За сегодня чеков нет.")
        html = build_anonymous_cheki_today_html(room_id, today)
        if html is None:
            return await message.answer("Ошибка: комната не найдена.")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
            tmp.write(html.encode("utf-8"))
            tmp_path = tmp.name
        filename = f"anon_cheki_{today}.html"
        try:
            await message.answer_document(document=FSInputFile(tmp_path, filename=filename))
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    @router.message(Cmd("чеки_сегодня", "cheki_segodnya"), F.chat.type == "private")
    async def cmd_cheki_private_fallback(message: Message):
        return await message.answer("Команда доступна после входа по приглашению.")

    @router.message(Cmd("помощь"), F.chat.type == "private", arf)
    async def cmd_anonymous_help(message: Message):
        if not message.from_user:
            return
        if not resolve_anonymous_room_for_dm(message.from_user.id, child_room_id):
            return
        await message.answer(ui.ANON_HELP_HTML, parse_mode="HTML")

    @router.message(Cmd("помощь"), F.chat.type == "private")
    async def cmd_help_private_fallback(message: Message):
        return await message.answer("Команда доступна после входа по приглашению.")

    @router.message(Cmd("delete"), F.chat.type == "private", arf)
    async def cmd_delete_anon(message: Message):
        if not message.from_user:
            return
        room_id = resolve_anonymous_room_for_dm(message.from_user.id, child_room_id)
        if not room_id:
            return
        uid = message.from_user.id
        pairs = delete_last_relayed_for_sender(room_id, uid)
        if not pairs:
            await message.answer("Нечего удалять.")
            return
        tg_bot = message.bot
        ok = 0
        for peer_id, mid, _src in pairs:
            try:
                await tg_bot.delete_message(peer_id, mid)
                ok += 1
            except Exception:
                logging.exception("delete peer=%s mid=%s", peer_id, mid)
        seen_src: Set[int] = set()
        ok_me = 0
        for _peer_id, _mid, src in pairs:
            if src is None or src in seen_src:
                continue
            seen_src.add(src)
            try:
                await tg_bot.delete_message(uid, src)
                ok_me += 1
            except Exception:
                logging.exception("delete sender copy uid=%s mid=%s", uid, src)
        await message.answer(
            f"Готово. У собеседников: {ok}/{len(pairs)}. У вас: {ok_me}/{len(seen_src)}."
        )

    @router.message(Cmd("delete_all"), F.chat.type == "private", arf)
    async def cmd_delete_all_anon(message: Message):
        if not message.from_user or not message.text:
            return
        room_id = resolve_anonymous_room_for_dm(message.from_user.id, child_room_id)
        if not room_id:
            return
        parts = message.text.split()
        minutes: Optional[int] = None
        if len(parts) >= 2:
            try:
                minutes = int(parts[1])
            except ValueError:
                await message.answer("Формат: /delete_all или /delete_all 120")
                return
        uid = message.from_user.id
        pairs = delete_all_relayed_for_sender(room_id, uid, minutes=minutes)
        if not pairs:
            await message.answer("Нечего удалять.")
            return
        tg_bot = message.bot
        ok = 0
        for peer_id, mid, _src in pairs:
            try:
                await tg_bot.delete_message(peer_id, mid)
                ok += 1
            except Exception:
                logging.exception("delete_all peer=%s mid=%s", peer_id, mid)
        seen_src: Set[int] = set()
        ok_me = 0
        for _peer_id, _mid, src in pairs:
            if src is None or src in seen_src:
                continue
            seen_src.add(src)
            try:
                await tg_bot.delete_message(uid, src)
                ok_me += 1
            except Exception:
                logging.exception("delete_all sender copy uid=%s mid=%s", uid, src)
        await message.answer(
            f"Готово. У собеседников: {ok}/{len(pairs)}. У вас: {ok_me}/{len(seen_src)}."
        )

    if include_private_catchall:

        @router.message(CmdStart(), F.chat.type == "private")
        async def cmd_start_child_plain(message: Message):
            if not message.from_user:
                return
            if resolve_anonymous_room_for_dm(message.from_user.id, child_room_id):
                return
            await message.answer(
                "Откройте бота по ссылке из приглашения."
            )

        @router.message(F.chat.type == "private")
        async def _anon_private_catchall(message: Message):
            if await try_anonymous_private_message(
                message, master_mode=False, child_room_id=child_room_id
            ):
                return
            if not message.from_user:
                return
            if resolve_anonymous_room_for_dm(message.from_user.id, child_room_id):
                return
            if message.text and message.text.startswith("/"):
                await message.answer("Сначала откройте ссылку из приглашения.")
                return
            await message.answer(
                "Этот бот для анонимной комнаты. Нужна ссылка-приглашение."
            )
