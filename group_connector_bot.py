import logging
import asyncio
import sys
from datetime import datetime
from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.exceptions import TelegramMigrateToChat
from aiogram.filters import Command, CommandStart, BaseFilter, StateFilter
from aiogram.types import Message, FSInputFile, CallbackQuery
import tempfile
import html as html_lib
import os
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.formatting import Bold, CustomEmoji, Text
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import locale
import time
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
import re
import aiohttp
import ssl
import json

from bot.loader import dp, initialize_db, with_clean_previous, TRON_PRO_API_KEY, bot
from bot.pg import (
    migrate_telegram_chat_id,
    upsert_admin_chat_invite_link,
    clear_rekvizit_outbound_for_verifier,
    add_rekvizit_outbound,
    list_rekvizit_outbound_for_verifier,
    delete_rekvizit_outbound_row,
    REKVIZIT_KIND_CLIENT_GROUP,
    REKVIZIT_KIND_ANON_DM,
)
from bot.group_queries import (
    get_default_rate_ids,
    insert_receipt,
    update_trader_rate,
    delete_receipt,
    insert_payout,
    find_or_create_exchange_rate,
    find_or_create_retention_rate,
    update_receipt_rates,
    receipt_exists,
    apply_chat_defaults,
    build_info_snapshot,
    format_info_message_html,
    build_cheki_today_snapshot,
    unassign_exchange_rate,
    unassign_retention_rate,
    reset_group_data,
    get_global_wallet_address,
    is_transaction_hash_processed,
    mark_transaction_processed,
    has_receipt_on_local_date,
)
from bot.scheduler import setup_scheduler, send_message_optimized
from bot.group_manager import GroupConnectionManager
from bot.config import ADMINS as CONFIG_ADMINS
from bot.crm_support import (
    SupportSpamError,
    notify_support_staff_new_ticket_message,
    record_support_message_from_user,
)
from bot.anonymous_chat import (
    get_anonymous_room_id_for_dm_verifier_key,
    list_anonymous_room_ids_for_verifier_group,
    list_member_telegram_ids_for_room,
    resolve_anonymous_room_for_verifier_group,
    get_child_bot_token,
    get_relay_display_name,
    insert_anonymous_receipt,
    is_verifier_group_linked_to_anonymous_room,
    pop_anonymous_verifier_notify_targets,
    room_has_child_bot,
    save_anonymous_verifier_notify_targets,
)
from bot.anonymous_relay_handlers import (
    relay_anonymous_photo_bytes_to_peers,
    try_anonymous_private_message,
)

# Инициализация менеджера групп
group_manager = GroupConnectionManager()

# Словарь для отслеживания связи между сообщениями с фото и их пересылками
# Ключ: (source_group_id, source_message_id)
# Значение: (verifier_group_id, message_id_в_группе_проверяющих [, anonymous_chat_id | None])
message_links = {}

# Словарь для отслеживания последнего подтвержденного фото чека в каждой группе проверяющих
# Ключ: verifier_group_id, Значение: (client_group_id, photo_message_id)
last_confirmed_photo = {}

# Словарь для отслеживания времени последнего подтверждения фото чека
# Ключ: verifier_group_id, Значение: timestamp последнего подтверждения
last_confirmation_time = {}

# Список ID администраторов (из TELEGRAM_ADMIN_IDS в .env)
ADMINS = list(CONFIG_ADMINS)

# Настройки бота
BOT_NAME = "Balenciaga Bot"


def _configure_time_locale() -> None:
    """Русские названия месяцев, если локаль есть в ОС; иначе C.UTF-8 (Docker slim)."""
    if sys.platform == "win32":
        candidates: tuple[str, ...] = ("Russian_Russia",)
    else:
        candidates = (
            "ru_RU.UTF-8",
            "ru_RU.utf8",
            "C.UTF-8",
            "C",
        )
    for name in candidates:
        try:
            locale.setlocale(locale.LC_TIME, name)
            return
        except locale.Error:
            continue
    try:
        locale.setlocale(locale.LC_TIME, "")
    except locale.Error:
        pass


_configure_time_locale()

router = Router()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Анонимные чаты: только дочерние боты (anonymous_child_runner). Основной бот — verifier, relay HTTP, CRM.

class RateStates(StatesGroup):
    waiting_for_new_rate = State()
    waiting_for_rate_update = State()


_REK_CMD_PREFIX = re.compile(r"^/\s*рек(?:@[\w_]+)?\s*", re.IGNORECASE)


def _rek_normalize_card_digits(text: str) -> Optional[str]:
    digits = re.sub(r"\D", "", text or "")
    if len(digits) != 16 or not digits.isdigit():
        return None
    return digits


def _rek_format_card_display(card16: str) -> str:
    return " ".join(card16[i : i + 4] for i in range(0, 16, 4))


def _rek_normalize_phone(text: str) -> Optional[str]:
    raw = (text or "").strip()
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 10 or len(digits) > 15:
        return None
    return raw


def _parse_rek_one_message_text(raw: str) -> Optional[Tuple[str, str, str, str]]:
    """
    /рек: банк, ФИО (одна или несколько строк), карта (16 цифр); телефон — последняя строка, необязательно.
    Если телефона нет, последняя строка — карта (достаточно 3 строк после /рек).
    """
    body = _REK_CMD_PREFIX.sub("", (raw or "").strip())
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if len(lines) < 3:
        return None

    last_phone = _rek_normalize_phone(lines[-1])
    prev_card = _rek_normalize_card_digits(lines[-2]) if len(lines) >= 2 else None
    last_card = _rek_normalize_card_digits(lines[-1])

    if len(lines) >= 4 and last_phone is not None and prev_card is not None:
        bank = lines[0]
        fio = " ".join(lines[1:-2]).strip()
        card16 = prev_card
        phone = last_phone
    elif last_card is not None:
        bank = lines[0]
        fio = " ".join(lines[1:-1]).strip()
        card16 = last_card
        phone = ""
    else:
        return None

    if not bank or len(bank) > 500:
        return None
    if not fio or len(fio) > 500:
        return None
    return bank, fio, card16, phone


async def broadcast_rekvizit_to_linked_chats(
    verifier_group_id: int, bank: str, fio: str, card16: str, phone: str
) -> dict:
    """
    Рассылка реквизитов в клиентские группы (connections) и участникам анонимных комнат
    с тем же verifier_group_id. Сохраняет message_id для ответа командой /стопрек.
    """
    clear_rekvizit_outbound_for_verifier(verifier_group_id)
    bank_e = html_lib.escape(bank.strip())
    fio_e = html_lib.escape(fio.strip())
    card_disp = _rek_format_card_display(card16)
    phone_st = (phone or "").strip()
    parts = [
        "<b>Реквизиты для оплаты</b>\n\n",
        f"Банк: {bank_e}\n",
        f"ФИО: {fio_e}\n",
        f"Карта: <code>{html_lib.escape(card_disp)}</code>",
    ]
    if phone_st:
        parts.append(f"\nТелефон: {html_lib.escape(phone_st)}")
    text = "".join(parts)
    stats = {
        "client_sent": 0,
        "client_failed": 0,
        "anon_sent": 0,
        "anon_failed": 0,
    }
    for row in group_manager.get_client_groups(verifier_group_id):
        cid = int(row[0])
        mid: Optional[int] = None
        for attempt in range(2):
            try:
                sm = await bot.send_message(cid, text, parse_mode="HTML")
                mid = sm.message_id
                break
            except Exception:
                logging.exception("Реквизиты /рек: не отправлено в группу клиента %s", cid)
                if attempt == 0:
                    await asyncio.sleep(0.35)
        if mid is not None:
            stats["client_sent"] += 1
            add_rekvizit_outbound(verifier_group_id, REKVIZIT_KIND_CLIENT_GROUP, cid, mid, None)
        else:
            stats["client_failed"] += 1
        await asyncio.sleep(0.05)

    room_ids = list_anonymous_room_ids_for_verifier_group(verifier_group_id)
    for room_id in room_ids:
        members = list_member_telegram_ids_for_room(room_id)
        if not members:
            continue
        child_token = get_child_bot_token(room_id) if room_has_child_bot(room_id) else None
        child_bot: Optional[Bot] = None
        try:
            if child_token:
                child_bot = Bot(token=child_token)
                send_bot: Bot = child_bot
            else:
                send_bot = bot
                logging.warning(
                    "Анонимная комната %s: нет дочернего бота — /рек отправляем основным ботом в ЛС",
                    room_id,
                )
            for uid in members:
                try:
                    sm = await send_bot.send_message(uid, text, parse_mode="HTML")
                    stats["anon_sent"] += 1
                    add_rekvizit_outbound(
                        verifier_group_id,
                        REKVIZIT_KIND_ANON_DM,
                        uid,
                        sm.message_id,
                        room_id,
                    )
                except Exception:
                    logging.exception(
                        "Реквизиты /рек: не отправлено в ЛС uid=%s room_id=%s", uid, room_id
                    )
                    stats["anon_failed"] += 1
                await asyncio.sleep(0.05)
        finally:
            if child_bot is not None:
                try:
                    await child_bot.session.close()
                except Exception:
                    pass
        await asyncio.sleep(0.05)
    return stats


async def broadcast_stop_rek_replies(verifier_group_id: int) -> Tuple[int, int]:
    """
    Ответ (reply) на сохранённые сообщения с реквизитами. Успешные строки удаляются из БД.
    Возвращает (число успехов, число ошибок).
    """
    rows = list_rekvizit_outbound_for_verifier(verifier_group_id)
    ok, fail = 0, 0
    client_rows: List[Tuple[int, int, int]] = []
    anon_by_room: Dict[int, List[Tuple[int, int, int]]] = defaultdict(list)
    for row_id, kind, chat_id, message_id, room_id in rows:
        if kind == REKVIZIT_KIND_CLIENT_GROUP:
            client_rows.append((row_id, chat_id, message_id))
        elif kind == REKVIZIT_KIND_ANON_DM:
            if room_id is None:
                fail += 1
                continue
            anon_by_room[int(room_id)].append((row_id, chat_id, message_id))

    for row_id, cid, mid in client_rows:
        try:
            await bot.send_message(cid, reply_to_message_id=mid, **stop_rek_broadcast_kwargs())
            ok += 1
            delete_rekvizit_outbound_row(row_id)
        except Exception:
            logging.exception("стопрек: не отправлен ответ в группу клиента %s", cid)
            fail += 1
        await asyncio.sleep(0.05)

    for room_id, lst in anon_by_room.items():
        child_token = get_child_bot_token(room_id) if room_has_child_bot(room_id) else None
        child_bot: Optional[Bot] = None
        try:
            if child_token:
                child_bot = Bot(token=child_token)
                send_bot: Bot = child_bot
            else:
                send_bot = bot
            for row_id, uid, mid in lst:
                try:
                    await send_bot.send_message(
                        uid,
                        reply_to_message_id=mid,
                        **stop_rek_broadcast_kwargs(),
                    )
                    ok += 1
                    delete_rekvizit_outbound_row(row_id)
                except Exception:
                    logging.exception(
                        "стопрек: не отправлен ответ в ЛС uid=%s room=%s", uid, room_id
                    )
                    fail += 1
                await asyncio.sleep(0.05)
        finally:
            if child_bot is not None:
                try:
                    await child_bot.session.close()
                except Exception:
                    pass
        await asyncio.sleep(0.05)
    return ok, fail


# Кастомный фильтр для проверки роли группы
class GroupRoleFilter(BaseFilter):
    def __init__(self, role: str):
        self.role = role

    async def __call__(self, message: Message) -> bool:
        # Применяется только к групповым чатам
        if message.chat.type == "private":
            return False
        
        current_role = group_manager.get_group_role(message.chat.id)
        return current_role == self.role


class VerifierGroupOrAnonymousLinkedFilter(BaseFilter):
    """Группа проверяющих по connections ИЛИ только по привязке из анонимной комнаты (без строки в connections)."""

    async def __call__(self, message: Message) -> bool:
        if message.chat.type == "private":
            return False
        if group_manager.get_group_role(message.chat.id) == "verifier":
            return True
        return is_verifier_group_linked_to_anonymous_room(message.chat.id)

# Фильтр для команд, которые должны обрабатываться только в связанных группах  
class ConnectedGroupFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        # Применяется только к групповым чатам
        if message.chat.type == "private":
            return False
        
        # Проверяем, что группа связана (имеет любую роль)
        current_role = group_manager.get_group_role(message.chat.id)
        return current_role is not None

# Фильтр для команд, которые должны обрабатываться только в НЕсвязанных группах  
class UnconnectedGroupFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        # Применяется только к групповым чатам
        if message.chat.type == "private":
            return False
        
        # Проверяем, что группа НЕ связана (не имеет роли)
        current_role = group_manager.get_group_role(message.chat.id)
        return current_role is None


def is_admin(user_id: int) -> bool:
    """Проверить, является ли пользователь администратором"""
    return user_id in ADMINS


async def can_broadcast_rek(message: Message) -> bool:
    """/рек: ADMINS бота или создатель/администратор этой группы в Telegram."""
    if not message.from_user or not message.chat:
        return False
    if is_admin(message.from_user.id):
        return True
    if message.chat.type not in ("group", "supergroup"):
        return False
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ("creator", "administrator")
    except Exception:
        logging.exception(
            "can_broadcast_rek: get_chat_member chat=%s user=%s",
            message.chat.id,
            message.from_user.id,
        )
        return False


# Кастомные emoji на кнопках под фото чека (Telegram custom emoji id)
CONFIRM_RECEIPT_CUSTOM_EMOJI_ID = "5870844977914842593"
FAKE_RECEIPT_CUSTOM_EMOJI_ID = "5805597488316419570"  # «Фейк/Нету» на первом ряду
# Крестик: подтверждение отмены фейка (❌) и итог «Проверено» после фейка
CROSS_CUSTOM_EMOJI_ID = "5397841719960022238"
# Успешное сообщение о фиксации выплаты (/выплата, Tron)
PAYOUT_OK_CUSTOM_EMOJI_ID = "5350452584119279096"
# /стопрек: «СТОП» + кастомный знак стоп в тексте предупреждения
STOP_REK_CUSTOM_EMOJI_ID = "5260293700088511294"


def stop_rek_broadcast_kwargs() -> dict:
    """Предупреждение /стопрек для send_message(**kwargs, reply_to_message_id=...)."""
    return Text(
        Bold("СТОП"),
        CustomEmoji("\u26d4", custom_emoji_id=STOP_REK_CUSTOM_EMOJI_ID),
        Bold(": по этим реквизитам сейчас не переводите деньги."),
    ).as_kwargs()


def _msg_with_custom_prefix(placeholder: str, emoji_id: str, body: str) -> dict:
    """Сообщение с кастомным emoji вместо первого символа-заглушки (✅/❌)."""
    if not body.startswith(" "):
        body = f" {body}"
    return Text(CustomEmoji(placeholder, custom_emoji_id=emoji_id), body).as_kwargs()


def msg_ok(body: str) -> dict:
    return _msg_with_custom_prefix("✅", CONFIRM_RECEIPT_CUSTOM_EMOJI_ID, body)


def msg_payout_ok(body: str) -> dict:
    return _msg_with_custom_prefix("✅", PAYOUT_OK_CUSTOM_EMOJI_ID, body)


def msg_err(body: str) -> dict:
    return _msg_with_custom_prefix("❌", CROSS_CUSTOM_EMOJI_ID, body)


def receipt_verification_keyboard(client_group_id: int, photo_message_id: int) -> InlineKeyboardMarkup:
    """Кнопки под фото чека: success — «Подтвердить», danger — «Фейк/Нету» (Telegram Bot API `style`)."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Подтвердить",
        callback_data=f"confirm_receipt:{client_group_id}:{photo_message_id}",
        style="success",
        icon_custom_emoji_id=CONFIRM_RECEIPT_CUSTOM_EMOJI_ID,
    )
    builder.button(
        text="Фейк/Нету",
        callback_data=f"fake_receipt:{client_group_id}:{photo_message_id}",
        style="danger",
        icon_custom_emoji_id=FAKE_RECEIPT_CUSTOM_EMOJI_ID,
    )
    builder.adjust(2)
    return builder.as_markup()


def analyze_exception_for_migrate_id(exception: Exception) -> Optional[int]:
    """Анализирует исключение для поиска migrate_to_chat_id"""
    try:
        from aiogram.exceptions import TelegramMigrateToChat

        if isinstance(exception, TelegramMigrateToChat):
            return int(exception.migrate_to_chat_id)
        # Логируем всю информацию об исключении для отладки
        logging.info(f"=== АНАЛИЗ ИСКЛЮЧЕНИЯ ===")
        logging.info(f"Тип исключения: {type(exception)}")
        logging.info(f"Сообщение: {str(exception)}")
        
        # Проверяем атрибуты исключения
        if hasattr(exception, '__dict__'):
            logging.info(f"Атрибуты исключения: {exception.__dict__}")
            for key, value in exception.__dict__.items():
                logging.info(f"  {key}: {value} (тип: {type(value)})")
        
        # Проверяем, есть ли migrate_to_chat_id в строке ошибки
        error_msg = str(exception)
        if "migrate_to_chat_id" in error_msg:
            import re
            # Ищем число после migrate_to_chat_id
            match = re.search(r'migrate_to_chat_id[:\s]*(-?\d+)', error_msg)
            if match:
                migrate_id = int(match.group(1))
                logging.info(f"✅ Найден migrate_to_chat_id в строке ошибки: {migrate_id}")
                return migrate_id
        
        # Проверяем атрибуты на наличие migrate или chat_id
        if hasattr(exception, '__dict__'):
            for key, value in exception.__dict__.items():
                key_str = str(key).lower()
                if ('migrate' in key_str or 'chat_id' in key_str) and isinstance(value, int):
                    logging.info(f"✅ Найден потенциальный ID в атрибуте {key}: {value}")
                    return value
        
        # Проверяем, есть ли response или parameters
        response = getattr(exception, 'response', None)
        if response:
            logging.info(f"Найден атрибут response: {response}")
            parameters = getattr(response, 'parameters', None)
            if parameters:
                logging.info(f"Найден атрибут parameters: {parameters}")
                migrate_id = getattr(parameters, 'migrate_to_chat_id', None)
                if migrate_id:
                    logging.info(f"✅ Найден migrate_to_chat_id в response.parameters: {migrate_id}")
                    return migrate_id
        
        logging.info("❌ migrate_to_chat_id не найден в исключении")
        err = str(exception)
        m = re.search(
            r"supergroup with id\s+(-?\d+)\s+from\s+(-?\d+)",
            err,
            re.IGNORECASE,
        )
        if m:
            return int(m.group(1))
        
    except Exception as analysis_error:
        logging.error(f"Ошибка при анализе исключения: {analysis_error}")
        return None

async def safe_send_message(bot_instance, chat_id: int, text: str, **kwargs):
    """Безопасная отправка сообщения с автоматическим обновлением ID группы при необходимости"""
    try:
        return await bot_instance.send_message(chat_id, text, **kwargs)
    except Exception as e:
        error_msg = str(e)
        if "bot was kicked from the group chat" in error_msg:
            # Бот был кикнут, но может быть снова добавлен
            logging.warning(f"Бот был кикнут из группы {chat_id}, но может быть снова добавлен")
            # Пробуем отправить еще раз через небольшую задержку
            import asyncio
            await asyncio.sleep(1)
            try:
                return await bot_instance.send_message(chat_id, text, **kwargs)
            except Exception as retry_error:
                logging.error(f"Повторная попытка отправки в группу {chat_id} не удалась: {retry_error}")
                raise e
        elif "bot was blocked by the user" in error_msg:
            # Пользователь заблокировал бота
            logging.warning(f"Пользователь заблокировал бота в чате {chat_id}")
            raise e
        elif isinstance(e, TelegramMigrateToChat) or "group chat was upgraded to a supergroup chat" in error_msg:
            # Группа была обновлена до супергруппы, нужно получить новый ID
            try:
                logging.info(f"Группа {chat_id} была обновлена до супергруппы, получаем новый ID...")
                
                # Анализируем исключение для поиска migrate_to_chat_id
                new_chat_id = analyze_exception_for_migrate_id(e)
                
                # Если не нашли через анализ, пробуем через get_chat
                if not new_chat_id:
                    try:
                        new_chat = await bot_instance.get_chat(chat_id)
                        new_chat_id = new_chat.id
                        logging.info(f"Получен новый ID через get_chat: {new_chat_id}")
                    except Exception as get_chat_error:
                        logging.warning(f"Не удалось получить новый ID через get_chat: {get_chat_error}")
                        raise e
                
                if new_chat_id:
                    # Обновляем ID группы в менеджере
                    if group_manager.update_group_id(chat_id, new_chat_id):
                        logging.info(f"ID группы обновлен: {chat_id} -> {new_chat_id}")
                        # Повторяем отправку с новым ID
                        return await bot_instance.send_message(new_chat_id, text, **kwargs)
                    else:
                        logging.error(f"Не удалось обновить ID группы {chat_id}")
                        raise e
                else:
                    logging.error(f"Не удалось получить новый ID группы для {chat_id}")
                    raise e
                    
            except Exception as update_error:
                logging.error(f"Ошибка при обновлении ID группы: {update_error}")
                raise e
        else:
            # Другая ошибка
            raise e

async def safe_send_photo(bot_instance, chat_id: int, photo, **kwargs):
    """Безопасная отправка фото с автоматическим обновлением ID группы при необходимости"""
    try:
        return await bot_instance.send_photo(chat_id, photo, **kwargs)
    except Exception as e:
        error_msg = str(e)
        if "bot was kicked from the group chat" in error_msg:
            # Бот был кикнут, но может быть снова добавлен
            logging.warning(f"Бот был кикнут из группы {chat_id}, но может быть снова добавлен")
            
            # Проверяем текущий статус бота в группе
            try:
                bot_info = await bot_instance.get_me()
                chat_member = await bot_instance.get_chat_member(chat_id, bot_info.id)
                logging.info(f"Текущий статус бота в группе {chat_id}: {chat_member.status}")
                
                if chat_member.status in ["left", "kicked"]:
                    logging.error(f"Бот действительно не в группе {chat_id} (статус: {chat_member.status})")
                    raise e
                    
            except Exception as status_error:
                logging.warning(f"Не удалось проверить статус бота: {status_error}")
            
            # Пробуем отправить еще раз через небольшую задержку
            import asyncio
            await asyncio.sleep(2)  # Увеличиваем задержку до 2 секунд
            try:
                logging.info(f"Повторная попытка отправки в группу {chat_id}")
                return await bot_instance.send_photo(chat_id, photo, **kwargs)
            except Exception as retry_error:
                logging.error(f"Повторная попытка отправки в группу {chat_id} не удалась: {retry_error}")
                raise e
        elif "bot was blocked by the user" in error_msg:
            # Пользователь заблокировал бота
            logging.warning(f"Пользователь заблокировал бота в чате {chat_id}")
            raise e
        elif isinstance(e, TelegramMigrateToChat) or "group chat was upgraded to a supergroup chat" in error_msg:
            # Группа была обновлена до супергруппы, нужно получить новый ID
            try:
                logging.info(f"Группа {chat_id} была обновлена до супергруппы, получаем новый ID...")
                
                # Анализируем исключение для поиска migrate_to_chat_id
                new_chat_id = analyze_exception_for_migrate_id(e)
                
                # Если не нашли через анализ, пробуем через get_chat
                if not new_chat_id:
                    try:
                        new_chat = await bot_instance.get_chat(chat_id)
                        new_chat_id = new_chat.id
                        logging.info(f"Получен новый ID через get_chat: {new_chat_id}")
                    except Exception as get_chat_error:
                        logging.warning(f"Не удалось получить новый ID через get_chat: {get_chat_error}")
                        raise e
                
                if new_chat_id:
                    # Обновляем ID группы в менеджере
                    if group_manager.update_group_id(chat_id, new_chat_id):
                        logging.info(f"ID группы обновлен: {chat_id} -> {new_chat_id}")
                        # Повторяем отправку с новым ID
                        return await bot_instance.send_photo(new_chat_id, photo, **kwargs)
                    else:
                        logging.error(f"Не удалось обновить ID группы {chat_id}")
                        raise e
                else:
                    logging.error(f"Не удалось получить новый ID группы для {chat_id}")
                    raise e
                    
            except Exception as update_error:
                logging.error(f"Ошибка при обновлении ID группы: {update_error}")
                raise e
        else:
            # Другая ошибка
            raise e


async def _notify_anonymous_verifier_outcome(
    *,
    source_group_id: int,
    source_message_id: int,
    text: str,
    entities: Optional[Any] = None,
) -> None:
    """Уведомление по результату проверки чека: пиры и отправитель — reply на релей с фото /п (дочерний бот в ЛС)."""
    from aiogram import Bot as AiogramBot

    room_id = get_anonymous_room_id_for_dm_verifier_key(source_group_id, source_message_id)
    if room_id is None:
        link = message_links.get((source_group_id, source_message_id))
        if link:
            vg = int(link[0])
            explicit = int(link[2]) if len(link) >= 3 and link[2] is not None else None
            room_id = resolve_anonymous_room_for_verifier_group(vg, explicit)
    if room_id is None:
        try:
            await safe_send_message(
                bot,
                source_group_id,
                text,
                entities=entities,
                reply_to_message_id=source_message_id,
            )
        except Exception:
            await safe_send_message(bot, source_group_id, text, entities=entities)
        return

    pairs = pop_anonymous_verifier_notify_targets(room_id, source_group_id, source_message_id)
    child_token = get_child_bot_token(room_id) if room_has_child_bot(room_id) else None

    async def _send_dm(tg, peer: int, reply_mid: Optional[int]) -> None:
        try:
            if reply_mid is not None:
                await tg.send_message(peer, text, entities=entities, reply_to_message_id=reply_mid)
            else:
                await tg.send_message(peer, text, entities=entities)
        except Exception:
            await tg.send_message(peer, text, entities=entities)

    if child_token:
        child = AiogramBot(token=child_token)
        try:
            for peer_id, relay_mid in pairs:
                try:
                    await _send_dm(child, peer_id, relay_mid)
                except Exception as e:
                    logging.warning("Аноним-уведомление peer=%s (child): %s", peer_id, e)
            try:
                await _send_dm(child, source_group_id, source_message_id)
            except Exception as e:
                logging.error("Аноним-уведомление отправителю (child): %s", e)
        finally:
            await child.session.close()
        return

    for peer_id, relay_mid in pairs:
        try:
            await safe_send_message(
                bot,
                peer_id,
                text,
                entities=entities,
                reply_to_message_id=relay_mid,
            )
        except Exception as e:
            logging.warning("Аноним-уведомление peer=%s: %s", peer_id, e)
    try:
        await safe_send_message(
            bot,
            source_group_id,
            text,
            entities=entities,
            reply_to_message_id=source_message_id,
        )
    except Exception:
        try:
            await safe_send_message(bot, source_group_id, text, entities=entities)
        except Exception as e:
            logging.error("Аноним-уведомление отправителю: %s", e)


def _verifier_group_relay_error_hint(verifier_group_id: int, bot_username: Optional[str], bot_id: int) -> str:
    """Пояснение при chat not found: токен процесса ≠ бот в группе (см. bot_instances id=1)."""
    label = f"@{bot_username}" if bot_username else f"id={bot_id}"
    return (
        f"Группа проверяющих {verifier_group_id} недоступна для бота {label}. "
        "Частая причина: в CRM в «Настройки бота» (bot_instances id=1) указан токен одного бота, "
        "а в группу проверяющих добавлен другой — Telegram отвечает «chat not found». "
        f"Добавьте в эту группу именно {label}, либо укажите в CRM токен того бота, который уже в группе. "
        "ID супергруппы обычно начинается с -100…"
    )


async def relay_anonymous_photo_check_from_bytes(
    user_id: int,
    verifier_group_id: int,
    file_bytes: bytes,
    filename: str = "check.jpg",
    original_dm_message_id: Optional[int] = None,
    anonymous_chat_id: Optional[int] = None,
) -> int:
    """
    Чек в группу проверяющих основным ботом (дочерний бот шлёт байты по HTTP).
    Если передан original_dm_message_id (id фото /п в ЛС с дочерним ботом) — не шлём дубль в ЛС основным,
    ключ message_links/callback = этот id; релей в анонимный чат с дочернего бота.
    Иначе — временное фото в ЛС основным (как раньше) и релей основным.
    """
    from aiogram import Bot as AiogramBot
    from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
    from aiogram.types import BufferedInputFile

    bot_info = await bot.get_me()

    try:
        await bot.get_chat(verifier_group_id)
    except TelegramBadRequest as e:
        err = (str(e) or "").lower()
        if any(x in err for x in ("chat not found", "peer_id_invalid")):
            raise ValueError(
                _verifier_group_relay_error_hint(verifier_group_id, bot_info.username, bot_info.id)
            ) from e
        raise ValueError(f"Группа {verifier_group_id}: {e}") from e

    try:
        chat_member = await bot.get_chat_member(verifier_group_id, bot_info.id)
        if chat_member.status in ("left", "kicked"):
            label = f"@{bot_info.username}" if bot_info.username else str(bot_info.id)
            raise ValueError(
                f"Бот {label} не состоит в группе проверяющих (статус: {chat_member.status}). Добавьте бота в группу."
            )
    except ValueError:
        raise
    except TelegramBadRequest as e:
        err = (str(e) or "").lower()
        if "chat not found" in err or "user not found" in err:
            raise ValueError(
                _verifier_group_relay_error_hint(verifier_group_id, bot_info.username, bot_info.id)
            ) from e
        logging.warning("Проверка бота в группе проверяющих (relay): %s", e)

    buf_ver = BufferedInputFile(file_bytes, filename=filename)

    un = os.environ.get("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    start_hint = (
        f"Откройте основного бота @{un} и нажмите Start, затем снова отправьте /п с фото."
        if un
        else "Откройте основного бота и нажмите Start, затем снова отправьте /п с фото."
    )

    n_rooms = len(list_anonymous_room_ids_for_verifier_group(verifier_group_id))
    if n_rooms > 1 and anonymous_chat_id is None:
        raise ValueError(
            "Несколько анонимных комнат на эту группу проверяющих: в запросе обязателен anonymous_chat_id."
        )
    # Комната: явный id (дочерний бот) или единственная в БД с этим verifier_group_id.
    room_id_early = resolve_anonymous_room_for_verifier_group(
        verifier_group_id, anonymous_chat_id
    )
    if anonymous_chat_id is not None and room_id_early is None:
        raise ValueError(
            "anonymous_chat_id не соответствует этой группе проверяющих или комната неактивна."
        )
    child_token_pre = (
        get_child_bot_token(room_id_early)
        if room_id_early and room_has_child_bot(room_id_early)
        else None
    )
    # Ключ callback/reply — id фото в ЛС с дочерним ботом; без дубля временного фото от основного
    can_use_child_dm_key = (
        original_dm_message_id is not None
        and room_id_early is not None
        and child_token_pre is not None
    )

    sent_user: Optional[Any] = None
    if can_use_child_dm_key:
        link_key = int(original_dm_message_id)
    else:
        buf_user = BufferedInputFile(file_bytes, filename=filename)
        try:
            sent_user = await bot.send_photo(user_id, buf_user)
            link_key = sent_user.message_id
        except TelegramForbiddenError as e:
            raise ValueError(start_hint) from e
        except TelegramBadRequest as e:
            err = (str(e) or "").lower()
            if "chat not found" in err or "user is deactivated" in err or "bot can't initiate" in err:
                raise ValueError(start_hint) from e
            raise ValueError(f"Не удалось отправить чек основным ботом: {e}") from e

    rv_markup = receipt_verification_keyboard(user_id, link_key)
    try:
        sent_photo = await safe_send_photo(
            bot,
            verifier_group_id,
            buf_ver,
            caption="Выберите действие:",
            reply_markup=rv_markup,
        )
        message_links[(user_id, link_key)] = (
            verifier_group_id,
            sent_photo.message_id,
            room_id_early,
        )
        room_id = room_id_early
        nick = get_relay_display_name(user_id, room_id) if room_id else None
        if room_id and nick:
            ct = get_child_bot_token(room_id) if room_has_child_bot(room_id) else None
            if ct and can_use_child_dm_key:
                child = AiogramBot(token=ct)
                try:
                    targets = await relay_anonymous_photo_bytes_to_peers(
                        child,
                        room_id,
                        user_id,
                        nick,
                        file_bytes,
                        filename,
                        source_message_id=original_dm_message_id,
                    )
                    if targets:
                        save_anonymous_verifier_notify_targets(room_id, user_id, link_key, targets)
                finally:
                    await child.session.close()
            else:
                targets = await relay_anonymous_photo_bytes_to_peers(
                    bot,
                    room_id,
                    user_id,
                    nick,
                    file_bytes,
                    filename,
                    source_message_id=original_dm_message_id,
                )
                if targets:
                    save_anonymous_verifier_notify_targets(room_id, user_id, link_key, targets)
    except TelegramBadRequest as e:
        if sent_user is not None:
            try:
                await bot.delete_message(user_id, sent_user.message_id)
            except Exception:
                pass
        err = (str(e) or "").lower()
        if "chat not found" in err or "peer_id" in err:
            raise ValueError(
                _verifier_group_relay_error_hint(verifier_group_id, bot_info.username, bot_info.id)
            ) from e
        raise ValueError(f"Не удалось отправить фото в группу проверяющих: {e}") from e
    except Exception:
        if sent_user is not None:
            try:
                await bot.delete_message(user_id, sent_user.message_id)
            except Exception:
                pass
        raise

    if sent_user is not None:
        try:
            await bot.delete_message(user_id, sent_user.message_id)
        except Exception:
            logging.debug("Не удалось удалить временное фото в ЛС (relay)", exc_info=True)

    return link_key


@router.message(Command("start"), F.chat.type.in_({"group", "supergroup"}))
async def start(message: Message):
    """/start только в группах. Личку обрабатывает cmd_start_private ниже."""
    chat_id = message.chat.id
    role = group_manager.get_group_role(chat_id)
    if role == 'client':
        await message.answer(
            f"🔗 Я {BOT_NAME}.\n\n"
            "Доступные команды:\n"
            "• /п - отправить фото чека (только с фото)\n"
            "• /инфо - показать статистику\n"
            "• /помощь - справка\n\n"
            "💡 Фото чека будет отправлено на проверку."
        )
    elif role == 'verifier':
        await message.answer(
            f"🔗 Я {BOT_NAME}.\n\n"
            "Доступные команды:\n"
            "• Кнопки 'Подтвердить' и 'Фейк/Нету' под фото чека\n"
            "• /чек <сумма> - добавить чек с указанной суммой\n"
            "• /инфо - показать статистику\n"
            "• /помощь - справка\n\n"
        )
    else:
        initialize_db(chat_id)
        await message.answer("Бот запущен!")

# Модифицируем существующий обработчик команды /чек для работы с группами проверяющих
@router.message(Command("чек"), VerifierGroupOrAnonymousLinkedFilter())
async def cmd_check_verifier(message: Message):
    """Обработчик команды /чек в группе проверяющих (роль verifier в connections или привязка из анонимной комнаты)."""
    # Фильтр уже проверил доступ (VerifierGroupOrAnonymousLinkedFilter)
    
    logging.info(f"🔍 Обрабатываем команду /чек в группе проверяющих {message.chat.id}")
    
    try:
        # Проверяем формат команды (должна быть сумма)
        parts = (message.text or "").split()
        if len(parts) != 2:
            await message.answer(**msg_err("Некорректный формат. Используйте: /чек 100.00 или /чек -50.00"))
            return
        
        # Проверяем, что второй параметр - это число
        try:
            amount = float(parts[1])
        except ValueError:
            await message.answer(**msg_err("Сумма должна быть числом. Используйте: /чек 100.00 или /чек -50.00"))
            return
        
        logging.info(f"💰 Обрабатываем чек на сумму {amount}")
        
        # Ищем связь между сообщениями для определения исходной группы клиентов
        source_message_id = None
        source_group_id = None
        db_path = None  # Инициализируем db_path
        # logging.info(f"Ищем связь для группы {message.chat.id} (проверяющие)")
        # logging.info(f"Доступные связи: {message_links}")
        # logging.info(f"Последние подтвержденные фото: {last_confirmed_photo}")
        
        # Используем информацию о последнем подтвержденном фото чека
        if message.chat.id in last_confirmed_photo:
            source_group_id, source_message_id = last_confirmed_photo[message.chat.id]
            logging.info(f"✅ Найдена связь по последнему подтвержденному фото: ({source_group_id}, {source_message_id})")
            
            source_role = group_manager.get_group_role(source_group_id)
            logging.info(f"Роль источника {source_group_id}: {source_role}")
            
            if source_role == "client":
                should_notify_client = True
                logging.info("✅ Источник — группа клиентов")
            elif (
                source_group_id > 0
                and (source_group_id, source_message_id) in message_links
                and message_links[(source_group_id, source_message_id)][0] == message.chat.id
            ):
                # Личка пользователя: /п из анонимного чата (не группа в connections)
                should_notify_client = True
                logging.info("✅ Источник — анонимный чек из ЛС")
            else:
                await message.answer(**msg_err("Ошибка: найденная группа не является группой клиентов."))
                return
        else:
            logging.warning(f"❌ Нет подтвержденного фото для группы проверяющих {message.chat.id}")
            logging.info(f"Доступные подтвержденные фото: {last_confirmed_photo}")
            
            # Не отправляем уведомление в группу клиентов
            should_notify_client = False
            logging.info(f"❌ should_notify_client установлен в False")
        
        # ВСЕГДА добавляем чек в БД группы проверяющих (PostgreSQL)
        logging.info(f"✅ Добавляем чек в БД группы проверяющих {message.chat.id}")
        initialize_db(message.chat.id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        default_rate_id, default_retention_id = get_default_rate_ids(message.chat.id)
        insert_receipt(message.chat.id, amount, default_rate_id, default_retention_id, timestamp)
        logging.info(f"✅ Чек на {amount} добавлен в БД группы проверяющих {message.chat.id}")
        
        if should_notify_client and source_group_id:
            src_role = group_manager.get_group_role(source_group_id)
            if src_role == "client":
                logging.info(f"✅ Добавляем чек также в БД группы клиентов {source_group_id}")
                initialize_db(source_group_id)
                dr2, dret2 = get_default_rate_ids(source_group_id)
                insert_receipt(source_group_id, amount, dr2, dret2, timestamp)
                logging.info(f"✅ Чек на {amount} добавлен также в БД группы клиентов {source_group_id}")
            else:
                logging.info(
                    "Пропуск второй вставки receipts: источник не группа клиентов (анонимный чек в ЛС)"
                )
                room_id = get_anonymous_room_id_for_dm_verifier_key(
                    source_group_id, source_message_id
                )
                if room_id is None and (source_group_id, source_message_id) in message_links:
                    tup = message_links[(source_group_id, source_message_id)]
                    explicit = (
                        int(tup[2]) if len(tup) >= 3 and tup[2] is not None else None
                    )
                    room_id = resolve_anonymous_room_for_verifier_group(
                        message.chat.id, explicit
                    )
                if room_id is not None:
                    rno = insert_anonymous_receipt(room_id, source_group_id, amount)
                    if rno is not None:
                        logging.info(
                            "✅ Чек на %s записан в анонимную комнату id=%s, receipt_no=%s",
                            amount,
                            room_id,
                            rno,
                        )
                    else:
                        logging.warning(
                            "Не удалось записать чек в anonymous_receipts для комнаты id=%s",
                            room_id,
                        )
                else:
                    logging.warning(
                        "Анонимная комната для группы проверяющих chat_id=%s не найдена в CRM "
                        "(нет verifier_group_id → anonymous_chats или неактивна). Чек в анонимную БД не пишем.",
                        message.chat.id,
                    )
        
        # Подтверждение: группа клиентов с reply на фото; анонимный ЛС — релей в анонимный чат с reply
        if should_notify_client and source_group_id and source_message_id:
            logging.info(f"Пытаемся отправить уведомление источнику {source_group_id}")
            _p = msg_ok(f"Чек на {amount} добавлен в {timestamp}.")
            is_anon_dm = (
                source_group_id > 0
                and (source_group_id, source_message_id) in message_links
                and message_links[(source_group_id, source_message_id)][0] == message.chat.id
            )
            try:
                if is_anon_dm:
                    await _notify_anonymous_verifier_outcome(
                        source_group_id=source_group_id,
                        source_message_id=source_message_id,
                        text=_p["text"],
                        entities=_p.get("entities"),
                    )
                else:
                    await safe_send_message(
                        bot,
                        source_group_id,
                        _p["text"],
                        entities=_p.get("entities"),
                        reply_to_message_id=source_message_id,
                    )
                logging.info("✅ Уведомление источнику отправлено")
            except Exception as e:
                logging.error(f"Ошибка при отправке с reply: {e}")
                if not is_anon_dm:
                    try:
                        _p2 = msg_ok(f"Чек на {amount} добавлен в {timestamp}.")
                        await safe_send_message(
                            bot,
                            source_group_id,
                            _p2["text"],
                            entities=_p2.get("entities"),
                        )
                        logging.info("✅ Отправлено обычное сообщение в группу клиентов без reply")
                    except Exception as fallback_error:
                        logging.error(f"Ошибка при отправке обычного сообщения: {fallback_error}")
        else:
            logging.info(f"Уведомление в группу клиентов НЕ отправляется:")
            logging.info(f"  should_notify_client: {should_notify_client}")
            logging.info(f"  source_group_id: {source_group_id}")
            logging.info(f"  source_message_id: {source_message_id}")
        
        # Заменяем кнопки на «Проверено» с кастомной галочкой после успешного добавления чека
        if should_notify_client and source_group_id and source_message_id:
            try:
                # Находим сообщение с фото в группе проверяющих и заменяем кнопки
                for key, value in message_links.items():
                    if key == (source_group_id, source_message_id):
                        target_group_id = value[0]
                        target_message_id = value[1]
                        if target_group_id == message.chat.id:  # Это группа проверяющих
                            # Создаем новую клавиатуру с кнопкой «Проверено» (кастомная галочка)
                            builder = InlineKeyboardBuilder()
                            builder.button(
                                text="Проверено",
                                callback_data=f"already_checked:{amount}",
                                style="success",
                                icon_custom_emoji_id=CONFIRM_RECEIPT_CUSTOM_EMOJI_ID,
                            )
                            builder.adjust(1)
                            
                            # Обновляем подпись и кнопки
                            await bot.edit_message_caption(
                                chat_id=target_group_id,
                                message_id=target_message_id,
                                caption="Проверено",
                            )
                            await bot.edit_message_reply_markup(
                                chat_id=target_group_id,
                                message_id=target_message_id,
                                reply_markup=builder.as_markup()
                            )
                            logging.info(f"✅ Подпись и кнопки обновлены после добавления чека")
                            break
            except Exception as e:
                logging.error(f"Ошибка при замене кнопок: {e}")
        
        # Сбрасываем состояние подтвержденного фото после успешного добавления чека
        if should_notify_client and message.chat.id in last_confirmed_photo:
            del last_confirmed_photo[message.chat.id]
            # Очищаем также время последнего подтверждения
            if message.chat.id in last_confirmation_time:
                del last_confirmation_time[message.chat.id]
            logging.info(f"Состояние подтвержденного фото сброшено для группы проверяющих {message.chat.id} после добавления чека")
        
        # Показываем соответствующее сообщение
        if should_notify_client:
            await message.answer(**msg_ok(f"Чек на {amount} добавлен в {timestamp}"))
        else:
            await message.answer(**msg_ok(f"Чек на {amount} добавлен в {timestamp}"))
        
    except Exception as e:
        logging.error(f"Ошибка при обработке команды /чек: {e}")
        await message.answer(**msg_err("Произошла ошибка при обработке чека."))


@router.message(Command("чек"), F.chat.type.in_({"group", "supergroup"}))
async def add_receipt_command(message: Message):
    try:
        chat_id = message.chat.id
        initialize_db(chat_id)
        parts = (message.text or "").split()
        if len(parts) != 2:
            raise ValueError("Неверный формат")

        amount = float(parts[1])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        dr, dret = get_default_rate_ids(chat_id)
        insert_receipt(chat_id, amount, dr, dret, timestamp)

        sign = "добавлен" if amount > 0 else "удален"
        return await message.answer(f"Чек на {amount} {sign} в {timestamp}.")

    except (IndexError, ValueError):
        return await message.answer("Некорректный формат. Используйте: /чек 100.00 или /чек -50.00")



@router.message(Command("процент"))
async def set_trader_rate(message: Message):
    try:
        chat_id = message.chat.id
        initialize_db(chat_id)
        rate = float((message.text or "").split()[1])
        update_trader_rate(chat_id, rate)
        return await message.answer(f"Процент чата установлена: {rate}%")
    except (IndexError, ValueError):
        return await message.answer("Некорректный формат. Используйте: /процент 10")


@router.message(Command("дефолт"))
async def set_chat_defaults(message: Message):
    chat_id = message.chat.id
    user = message.from_user
    if not user:
        return await message.answer("Ошибка: не удалось определить пользователя.")
    user_id = user.id

    # Только админ
    chat_admins = await bot.get_chat_administrators(chat_id)
    if user_id not in [admin.user.id for admin in chat_admins]:
        return await message.answer("⛔ Только админ может менять настройки по умолчанию.")

    try:
        parts = (message.text or "").strip().split()
        if len(parts) != 3:
            raise ValueError
        # Новая семантика: задаём сами значения курса и процента
        new_rate_value = float(parts[1]) if parts[1] != "-" else None
        new_retention_percent = float(parts[2]) if parts[2] != "-" else None
    except ValueError:
        return await message.answer(
            **msg_err(
                "Неверный формат. Используйте: /дефолт <курс|-> <процент|->\nПримеры: /дефолт 93.5 10  |  /дефолт 92.8 -  |  /дефолт - 12"
            )
        )

    initialize_db(chat_id)
    apply_chat_defaults(chat_id, new_rate_value, new_retention_percent)

    return await message.answer(
        **msg_ok(
            f"Установлено по умолчанию: курс = {new_rate_value if new_rate_value is not None else '—'}, процент = {new_retention_percent if new_retention_percent is not None else '—'}"
        )
    )

@router.message(Command("удалить_чек"))
async def handle_delete_receipt(message: Message):
    chat_id = message.chat.id
    user = message.from_user
    if not user:
        return await message.answer("Ошибка: не удалось определить пользователя.")
    user_id = user.id

    # Проверка прав администратора
    admins = await bot.get_chat_administrators(chat_id)
    if user_id not in [admin.user.id for admin in admins]:
        return await message.answer("⛔ Только админ может удалять чеки.")

    try:
        receipt_id = int((message.text or "").strip().split()[1])
    except (IndexError, ValueError):
        return await message.answer(**msg_err("Укажи номер чека в этом чате, например: /удалить_чек 3"))

    initialize_db(chat_id)
    if not receipt_exists(chat_id, receipt_id):
        return await message.answer(**msg_err(f"Чек №{receipt_id} не найден в этом чате."))
    delete_receipt(chat_id, receipt_id)

    return await message.answer(**msg_ok(f"Чек №{receipt_id} удалён."))


@router.message(Command("выплата"))
async def handle_manual_payout(message: Message):
    chat_id = message.chat.id
    user = message.from_user
    if not user:
        return await message.answer("Ошибка: не удалось определить пользователя.")
    user_id = user.id

    # Проверка на админа
    admins = await bot.get_chat_administrators(chat_id)
    if user_id not in [admin.user.id for admin in admins]:
        return await message.answer("⛔ Только админ может фиксировать выплаты.")

    try:
        payout_amount = float((message.text or "").strip().split()[1])
    except (IndexError, ValueError):
        return await message.answer(**msg_err("Укажи сумму выплаты, например: /выплата 1200"))

    initialize_db(chat_id)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    insert_payout(chat_id, payout_amount, timestamp)

    return await message.answer(**msg_payout_ok(f"Выплата {payout_amount:.2f} зафиксирована."))

@router.message(Command("пкп"))
async def assign_rate_and_retention_to_receipt(message: Message):
    chat_id = message.chat.id
    user = message.from_user
    if not user:
        return await message.answer("Ошибка: не удалось определить пользователя.")
    user_id = user.id

    # Проверка прав администратора
    admins = await bot.get_chat_administrators(chat_id)
    if user_id not in [admin.user.id for admin in admins]:
        return await message.answer("⛔ Только админ может присваивать курс и процент чеку.")

    try:
        parts = (message.text or "").strip().split()
        if len(parts) != 4:
            raise ValueError

        rate_value = float(parts[1])
        percent_value = float(parts[2])
        receipt_id = int(parts[3])
    except (ValueError, IndexError):
        return await message.answer(
            **msg_err("Неверный формат. Используйте: /пкп <курс> <процент> <номер_чека>\nНапример: /пкп 93.5 10 3")
        )

    initialize_db(chat_id)
    if not receipt_exists(chat_id, receipt_id):
        return await message.answer(**msg_err(f"Чек №{receipt_id} не найден в этом чате."))

    exchange_rate_id = find_or_create_exchange_rate(chat_id, rate_value)
    retention_rate_id = find_or_create_retention_rate(chat_id, percent_value)
    update_receipt_rates(chat_id, receipt_id, exchange_rate_id, retention_rate_id)

    return await message.answer(
        **msg_ok(
            f"К чеку №{receipt_id} присвоены значения: курс = {rate_value}, процент = {percent_value}%"
        )
    )

@router.message(Command("помощь"))
async def help_command(message: Message):
    chat_id = message.chat.id
    role = group_manager.get_group_role(chat_id)
    
    if role == 'client':
        # Группа клиентов
        help_text = (
            f"🤖 *{BOT_NAME}*\n\n"
            "📥 /п — Отправить фото чека на проверку\n"
            "📊 /инфо — Показать статистику\n"
            "🆘 /помощь — Показать это сообщение\n\n"
            "💡 *Как использовать:*\n"
            "1. Отправьте фото чека с командой /п\n"
            "2. Фото будет отправлено в группу проверяющих\n"
            "3. После проверки вы получите уведомление"
        )
    elif role == 'verifier':
        # Группа проверяющих
        help_text = (
            f"🤖 *{BOT_NAME}*\n\n"
            "📥 /чек `<сумма>` — Добавить чек после подтверждения фото\n"
            "📊 /инфо — Показать статистику\n"
            "🆘 /помощь — Показать это сообщение\n\n"
            "💡 *Как работать:*\n"
            "1. Нажмите '✅ Подтвердить' под фото чека\n"
            "2. Введите сумму командой /чек <сумма>\n"
            "3. Или нажмите '❌ Фейк/Нету' для отклонения"
        )
    else:
        # Обычная группа (несвязанная)
        help_text = (
            "🤖 *Доступные команды:*\n\n"
            "📥 /чек `<сумма>` — Добавить чек\n"
            "💸 /выплата (-)`<сумма>` — Зафиксировать выплату *(админ)*\n"
            "📊 /инфо — Показать последние чеки и баланс\n"
            "🧾 /чеки\\_сегодня — Показать все чеки за сегодня\n"
            "⚙️ /дефолт `<курс>` `<процент>` — Установить значения по умолчанию для чата *(админ)*\n"
            "✅ /присвоить\\_курс\\_проценты `<курс>` `<процент>` `<ID>` — Присвоить курс и процент конкретному чеку *(админ)*\n"
            "❌ /отвязать\\_курс ID — Отвязать курс от чека *(админ)*\n"
            "❌ /отвязать\\_процент ID — Отвязать процент от чека *(админ)*\n"
            "🆘 /помощь — Показать это сообщение\n"
            "❌ /сброс — Сбросить все данные *(админ)*\n"
            "❌ /удалить\\_чек ID — Удалить чек *(админ)*"
        )
    
    return await message.answer(help_text, parse_mode="Markdown")

# Управление курсами отключено — используется только /дефолт
@router.message(Command("курс"))
async def show_exchange_rates(message: Message):
    return await message.answer("Команда отключена. Используйте /дефолт <курс> <процент>.")

@router.callback_query(F.data.startswith("edit_rate:"))
async def handle_edit_rate(callback: types.CallbackQuery, state: FSMContext):
    return await callback.answer("Отключено", show_alert=False)

@router.message(RateStates.waiting_for_rate_update)
async def update_existing_rate(message: Message, state: FSMContext):
    return await message.answer("Отключено. Используйте /дефолт <курс> <процент>.")




@router.callback_query(F.data == "add_rate")
async def handle_add_rate(callback: types.CallbackQuery, state: FSMContext):
    return await callback.answer("Отключено", show_alert=False)



@router.message(RateStates.waiting_for_new_rate)
async def save_new_rate(message: Message, state: FSMContext):
    return await message.answer("Отключено. Используйте /дефолт <курс> <процент>.")



@router.callback_query(F.data.startswith("confirm_delete_rate:"))
async def confirm_delete_rate(callback: types.CallbackQuery):
    return await callback.answer("Отключено", show_alert=False)


@router.callback_query(F.data.startswith("delete_rate:"))
async def delete_rate(callback: types.CallbackQuery):
    return await callback.answer("Отключено", show_alert=False)



# @router.message(Command("присвоить_курс_диапазон"))
# 
# async def assign_rate_to_range(message: Message):
#     return await message.answer("Команда отключена. Используйте /дефолт для установки курса по умолчанию.")


# @router.message(Command("присвоить_проценты_диапазон"))
# 
# async def assign_retention_to_range(message: Message):
#     return await message.answer("Команда отключена. Используйте /дефолт для установки процента по умолчанию.")


@router.message(Command("отвязать_курс"))
async def unassign_rate(message: Message):
    chat_id = message.chat.id
    user = message.from_user
    if not user:
        return await message.answer("Ошибка: не удалось определить пользователя.")
    user_id = user.id

    # Проверка на админа
    chat_admins = await bot.get_chat_administrators(chat_id)
    if user_id not in [admin.user.id for admin in chat_admins]:
        return await message.answer("⛔ Только админ может отвязывать курсы.")


    try:
        parts = (message.text or "").split()
        if len(parts) != 2:
            raise ValueError("Неверный формат команды")

        receipt_id = int(parts[1])
        initialize_db(chat_id)
        n = unassign_exchange_rate(chat_id, receipt_id)
        if n == 0:
            return await message.answer(**msg_err("Чек с таким номером не найден в этом чате"))
        return await message.answer(**msg_ok(f"Курс отвязан от чека №{receipt_id}"))



    except ValueError:
        return await message.answer(**msg_err("Неверный формат. Используйте: /отвязать_курс <номер_чека>"))


@router.message(Command("отвязать_процент"))
async def unassign_retention(message: Message):
    chat_id = message.chat.id
    user = message.from_user
    if not user:
        return await message.answer("Ошибка: не удалось определить пользователя.")
    user_id = user.id

    # Проверка на админа
    chat_admins = await bot.get_chat_administrators(chat_id)
    if user_id not in [admin.user.id for admin in chat_admins]:
        return await message.answer("⛔ Только админ может отвязывать проценты.")


    try:
        parts = (message.text or "").split()
        if len(parts) != 2:
            raise ValueError("Неверный формат команды")

        receipt_id = int(parts[1])
        initialize_db(chat_id)
        n = unassign_retention_rate(chat_id, receipt_id)
        if n == 0:
            return await message.answer(**msg_err("Чек с таким номером не найден в этом чате"))
        return await message.answer(**msg_ok(f"Процент отвязан от чека №{receipt_id}"))

    except ValueError:
        return await message.answer(**msg_err("Неверный формат. Используйте: /отвязать_процент <номер_чека>"))

@router.callback_query(F.data == "cancel_delete")

async def cancel_delete(callback: types.CallbackQuery):
    return await callback.answer("Отменено", show_alert=False)



# Ручное присваивание курса отключено

@router.callback_query(F.data.startswith("assign_rate:"))

async def handle_assign_rate(callback: types.CallbackQuery, state: FSMContext):
    # Команда отключена вместе с ручным присвоением
    await callback.answer("Отключено", show_alert=False)


@router.message(Command("инфо"), F.chat.type.in_({"group", "supergroup"}))
async def get_last_receipts(message: Message):
    chat_id = message.chat.id
    initialize_db(chat_id)
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot = build_info_snapshot(chat_id, today)
    if snapshot is None:
        return await message.answer("Ошибка: настройки не найдены.")
    response = format_info_message_html(snapshot, daily_report=False)
    return await message.answer(response, parse_mode="HTML")


@router.message(Command("чеки_сегодня"), F.chat.type.in_({"group", "supergroup"}))
async def get_all_today_receipts(message: Message):
    chat_id = message.chat.id
    initialize_db(chat_id)
    today = datetime.now().strftime("%Y-%m-%d")
    snap = build_cheki_today_snapshot(chat_id, today)
    if snap is None:
        return await message.answer("Ошибка: настройки не найдены.")
    if not snap["rows"]:
        return await message.answer("За сегодня чеков нет.")

    table_rows = snap["table_rows"]
    total_default_amount = snap["total_default_amount"]
    other_group_amounts = snap["other_group_amounts"]
    total_converted = snap["total_converted"]
    total_payout = snap["total_payout"]

    sums_split_str = " | ".join([f"{total_default_amount:.2f}"] + [f"{amt:.2f}" for amt in other_group_amounts])

    # Создаем красивую HTML страницу в стиле prototype.html
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Чеки за {datetime.now().strftime('%d.%m.%Y')}</title>
        <style>
            :root {{
                --background: #0f1115;
                --card: #171a21;
                --card-stroke: #222733;
                --text: #eef2ff;
                --muted: #a7b0c0;
                --accent: #4f7cff;
                --accent-pressed: #3f67d4;
                --success: #1fb980;
                --danger: #ff5d5d;
                --shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
                --radius: 14px;
            }}

            body {{
                margin: 0;
                font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Inter, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji";
                background: var(--background);
                color: var(--text);
                -webkit-font-smoothing: antialiased;
                -moz-osx-font-smoothing: grayscale;
                min-height: 100vh;
                position: relative;
            }}

            body::before {{
                content: '';
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: radial-gradient(circle at 20% 80%, rgba(79, 124, 255, 0.1) 0%, transparent 50%),
                            radial-gradient(circle at 80% 20%, rgba(79, 124, 255, 0.1) 0%, transparent 50%);
                pointer-events: none;
                z-index: -1;
            }}

            .app {{
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                align-items: center;
            }}

            .safe-wrap {{
                width: 100%;
                max-width: 1200px;
                margin: 0 auto;
                padding: 0 16px;
                box-sizing: border-box;
            }}

            .header {{
                position: sticky;
                top: 0;
                z-index: 3;
                backdrop-filter: saturate(140%) blur(10px);
                background: rgba(15, 17, 21, 0.7);
                border-bottom: 1px solid rgba(255, 255, 255, 0.06);
                width: 100%;
                box-shadow: 0 0 30px rgba(79, 124, 255, 0.3);
            }}

            .header .title {{
                padding: 20px 0;
                font-size: 24px;
                font-weight: 600;
                letter-spacing: 0.2px;
                text-align: center;
                text-shadow: 0 0 20px rgba(79, 124, 255, 0.8);
            }}

            .content {{
                width: 100%;
                flex: 1;
                padding: 20px 0;
                box-sizing: border-box;
            }}

            .summary {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 12px;
                margin-bottom: 20px;
            }}

            .summary-item {{
                background: rgba(23, 26, 33, 0.7);
                backdrop-filter: blur(20px) saturate(180%);
                -webkit-backdrop-filter: blur(20px) saturate(180%);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: var(--radius);
                padding: 16px;
                font-size: 14px;
                color: var(--muted);
                text-align: center;
                box-shadow: 0 0 20px rgba(79, 124, 255, 0.2),
                            0 8px 32px rgba(0, 0, 0, 0.3),
                            inset 0 1px 0 rgba(255, 255, 255, 0.1);
                transition: all 0.3s ease;
                position: relative;
                overflow: hidden;
            }}

            .summary-item::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 0.1) 0%, 
                    rgba(255, 255, 255, 0.05) 50%, 
                    rgba(255, 255, 255, 0.02) 100%);
                border-radius: var(--radius);
                pointer-events: none;
            }}

            .summary-item:hover {{
                background: rgba(23, 26, 33, 0.8);
                box-shadow: 0 0 30px rgba(79, 124, 255, 0.4),
                            0 12px 40px rgba(0, 0, 0, 0.4),
                            inset 0 1px 0 rgba(255, 255, 255, 0.15);
                transform: translateY(-2px);
                border-color: rgba(79, 124, 255, 0.3);
            }}

            .summary-item .label {{
                color: var(--muted);
                margin-bottom: 8px;
                font-size: 13px;
                position: relative;
                z-index: 1;
            }}

            .summary-item .value {{
                color: var(--text);
                font-weight: 700;
                font-size: 18px;
                text-shadow: 0 0 15px rgba(79, 124, 255, 0.6);
                position: relative;
                z-index: 1;
            }}

            .table-container {{
                background: var(--card);
                border: 1px solid var(--card-stroke);
                border-radius: var(--radius);
                overflow: hidden;
                box-shadow: var(--shadow), 0 0 25px rgba(79, 124, 255, 0.15);
                margin-bottom: 20px;
            }}

            table {{
                width: 100%;
                border-collapse: collapse;
                background: var(--card);
            }}

            th {{
                background: var(--accent);
                color: white;
                padding: 12px 8px;
                text-align: center;
                font-weight: 600;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                text-shadow: 0 0 10px rgba(255, 255, 255, 0.6);
                box-shadow: inset 0 0 15px rgba(255, 255, 255, 0.1);
            }}

            td {{
                padding: 10px 8px;
                text-align: center;
                border-bottom: 1px solid var(--card-stroke);
                font-size: 12px;
                color: var(--text);
            }}

            tr:nth-child(even) {{
                background-color: rgba(255, 255, 255, 0.02);
            }}

            tr:hover {{
                background-color: rgba(79, 124, 255, 0.1);
                transition: all 0.3s ease;
                box-shadow: 0 0 15px rgba(79, 124, 255, 0.3);
            }}

            @media (max-width: 768px) {{
                .safe-wrap {{
                    max-width: 100%;
                    padding: 0 12px;
                }}
                th, td {{
                    padding: 8px 4px;
                    font-size: 11px;
                }}
                .summary {{
                    grid-template-columns: 1fr;
                    gap: 8px;
                }}
                .header .title {{
                    font-size: 20px;
                    padding: 16px 0;
                }}
            }}

            @media (max-width: 480px) {{
                .safe-wrap {{
                    padding: 0 8px;
                }}
                th, td {{
                    padding: 6px 2px;
                    font-size: 10px;
                }}
                .header .title {{
                    font-size: 18px;
                    padding: 14px 0;
                }}
                .content {{
                    padding: 16px 0;
                }}
            }}

            @media (max-width: 360px) {{
                th, td {{
                    padding: 4px 1px;
                    font-size: 9px;
                }}
                .safe-wrap {{
                    padding: 0 6px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="app">
            <header class="header">
                <div class="safe-wrap">
                    <div class="title">🧾 Чеки за {datetime.now().strftime('%d.%m.%Y')}</div>
                </div>
            </header>

            <main class="content">
                <div class="safe-wrap">
                    <div class="summary">
                        <div class="summary-item">
                            <div class="label">📦 Сумма всех чеков</div>
                            <div class="value">{sums_split_str}</div>
                        </div>
                        <div class="summary-item">
                            <div class="label">♻️ Оборот за сегодня</div>
                            <div class="value">{total_converted:.2f}</div>
                        </div>
                        <div class="summary-item">
                            <div class="label">💸 Всего к выплате</div>
                            <div class="value">{total_payout:.2f}</div>
                        </div>
                    </div>

                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>№</th>
                                    <th>Время</th>
                                    <th>Сумма</th>
                                    <th>Курс</th>
                                    <th>%</th>
                                    <th>В валюте</th>
                                    <th>К выплате</th>
                                </tr>
                            </thead>
                            <tbody>
                                {''.join(f'<tr><td>{row[0]}</td><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td><td>{row[4]}</td><td>{row[5]}</td><td>{row[6]}</td></tr>' for row in table_rows)}
                            </tbody>
                        </table>
                    </div>
                </div>
            </main>
        </div>
    </body>
    </html> 
    """

    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
        tmp.write(html_content.encode("utf-8"))
        tmp_path = tmp.name

    filename = f"cheki_{datetime.now().strftime('%Y-%m-%d')}.html"
    await message.answer_document(document=FSInputFile(tmp_path, filename=filename))
    try:
        os.remove(tmp_path)
    except Exception:
        pass
    return

@router.message(Command("сброс"), F.chat.type.in_({"group", "supergroup"}))
async def reset_data(message: Message):
    chat_id = message.chat.id
    initialize_db(chat_id)
    reset_group_data(chat_id)

    return await message.answer("<b>Все данные для этой группы сброшены!</b>", parse_mode="HTML")


# ===== ОБРАБОТЧИКИ КОМАНД ДЛЯ СВЯЗЫВАНИЯ ГРУПП =====

@router.message(CommandStart(), ConnectedGroupFilter())
async def cmd_start_connected_group(message: Message):
    """Обработчик команды /start в связанных группах"""
    # Определяем роль группы и показываем соответствующие команды
    role = group_manager.get_group_role(message.chat.id)
    if role == 'client':
        await message.answer(
            f"🔗 Я {BOT_NAME}.\n\n"
            "Доступные команды:\n"
            "• /п - отправить фото чека (только с фото)\n\n"
            "💡 Фото чека будет отправлено на проверку."
        )
    elif role == 'verifier':
        await message.answer(
            f"🔗 Я {BOT_NAME}.\n\n"
            "Доступные команды:\n"
            "• Кнопки «Подтвердить» и «Фейк/Нету» под фото чека (после ввода суммы подпись «Проверено» и кнопка с галочкой)\n"
            "• /чек <сумма> - добавить чек с указанной суммой\n"
            "• /рек — реквизиты одним сообщением (админы бота или админы группы в Telegram; банк, ФИО, карта, телефон — строками под командой)\n"
            "• /стопрек — предупредить об остановке приема платежей по реквизитам\n\n"
        )

@router.message(CommandStart())
async def cmd_start_private(message: Message):
    """Обработчик команды /start в приватных чатах"""
    if message.chat.type != "private":
        return
    if not message.from_user:
        return

    # Админ: показываем команды управления
    if is_admin(message.from_user.id):
        await message.answer(
            f"👋 Привет! Я {BOT_NAME}.\n\n"
            "🔗 Используйте команду /connect для настройки связки групп:\n"
            "/connect <chat_id_клиентов> <chat_id_проверяющих>\n\n"
            "📋 Доступные команды:\n"
            "/connect - связать группу клиентов с группой проверяющих\n"
            "/disconnect - разорвать связь\n"
            "/list - список всех связей с ID групп\n"
            "/stats - статистика\n"
            "/peer_id - показать ID группы\n"
            "/help - справка"
        )
        return

    # Не админ: приветствие и актуальные ссылки из веб-интерфейса
    welcome_text, welcome_links = group_manager.get_welcome_content()
    has_text = bool(welcome_text and welcome_text.strip())
    has_links = bool(welcome_links)

    if has_text or has_links:
        text = welcome_text.strip() if welcome_text else "👋 Добро пожаловать!"
        reply_markup = None
        if welcome_links:
            builder = InlineKeyboardBuilder()
            for link in welcome_links:
                label = (link.get("label") or "Ссылка").strip() or "Ссылка"
                url = (link.get("url") or "").strip()
                if url:
                    builder.button(text=label, url=url)
            builder.adjust(1)
            reply_markup = builder.as_markup()
        await message.answer(text, reply_markup=reply_markup)
    else:
        await message.answer(
            "👋 Здравствуйте! Напишите сообщение в этот чат — оно уйдёт в поддержку, мы ответим здесь.\n\n"
            "💡 Администраторы настраивают связки групп через команды бота в личке."
        )

@router.message(Command("connect"))
async def cmd_connect(message: Message):
    """Обработчик команды /connect для связывания групп"""
    if message.chat.type != "private":
        return
    
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer(**msg_err("У вас нет прав для выполнения этой команды."))
        return
    
    try:
        if not message.text:
            await message.answer(**msg_err("Неверный формат команды."))
            return
        args = message.text.split()[1:]
        if len(args) != 2:
            await message.answer(
                **msg_err(
                    "Неверный формат команды.\n"
                "Используйте: /connect <chat_id_клиентов> <chat_id_проверяющих>"
                )
            )
            return
        
        client_group_id = int(args[0])
        verifier_group_id = int(args[1])
        
        # Проверяем, что группы существуют и бот может получить информацию о них
        try:
            client_chat = await bot.get_chat(client_group_id)
            verifier_chat = await bot.get_chat(verifier_group_id)
        except Exception as e:
            await message.answer(**msg_err("Не удалось получить информацию об одной из групп. Проверьте ID групп."))
            return
        
        # Проверяем, что группа клиентов не связана уже с другими
        client_role = group_manager.get_group_role(client_group_id)
        if client_role:
            await message.answer(**msg_err(f"Группа {client_group_id} уже связана как {client_role}."))
            return
        
        # Проверяем роль группы проверяющих
        verifier_role = group_manager.get_group_role(verifier_group_id)
        if verifier_role and verifier_role != 'verifier':
            await message.answer(**msg_err(f"Группа {verifier_group_id} уже связана как {verifier_role}."))
            return
        
        # Если группа проверяющих уже связана, это нормально - она может обслуживать несколько групп клиентов
        if verifier_role == 'verifier':
            # Получаем существующие группы клиентов для этой группы проверяющих
            existing_clients = group_manager.get_client_groups(verifier_group_id)
            client_names = [name for _, name in existing_clients]
            
            await message.answer(
                f"ℹ️ Группа проверяющих уже связана с {len(existing_clients)} группами клиентов.\n\n"
                f"Добавляем новую группу клиентов..."
            )
        
        # Добавляем связь через менеджер
        if group_manager.add_connection(
            client_group_id, verifier_group_id, 
            getattr(client_chat, 'title', None) or str(client_group_id), 
            getattr(verifier_chat, 'title', None) or str(verifier_group_id)
        ):
            # Получаем обновленный список групп клиентов
            updated_clients = group_manager.get_client_groups(verifier_group_id)
            client_names = [name for _, name in updated_clients]
            
            await message.answer(
                **msg_ok(
                    f"Группы успешно связаны!\n\n"
                f"📱 Группа клиентов: {getattr(client_chat, 'title', None) or 'Группа клиентов'}\n"
                f"👥 Группа проверяющих: {getattr(verifier_chat, 'title', None) or 'Группа проверяющих'}\n\n"
                f"📋 Теперь группа проверяющих обслуживает {len(updated_clients)} групп клиентов.\n\n"
                f"Команды будут работать в соответствии с ролями групп."
                )
            )
        else:
            await message.answer(**msg_err("Ошибка при связывании групп."))
            
    except ValueError:
        await message.answer(**msg_err("ID групп должны быть числами."))
    except Exception as e:
        logging.error(f"Ошибка при связывании групп: {e}")
        await message.answer(**msg_err("Произошла ошибка при связывании групп."))

@router.message(Command("disconnect"))
async def cmd_disconnect(message: Message):
    """Обработчик команды /disconnect для разрыва связи"""
    if message.chat.type != "private":
        return
    
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer(**msg_err("У вас нет прав для выполнения этой команды."))
        return
    
    try:
        if not message.text:
            await message.answer(**msg_err("Неверный формат команды."))
            return
        args = message.text.split()[1:]
        if len(args) != 2:
            await message.answer(
                **msg_err(
                    "Неверный формат команды.\n"
                "Используйте: /disconnect <chat_id_клиентов> <chat_id_проверяющих>"
                )
            )
            return
        
        client_group_id = int(args[0])
        verifier_group_id = int(args[1])
        
        # Разрываем связь через менеджер
        if group_manager.remove_connection(client_group_id, verifier_group_id):
            await message.answer(**msg_ok("Связь между группами разорвана."))
        else:
            await message.answer(**msg_err("Связь между этими группами не найдена."))
            
    except ValueError:
        await message.answer(**msg_err("ID групп должны быть числами."))
    except Exception as e:
        logging.error(f"Ошибка при разрыве связи: {e}")
        await message.answer(**msg_err("Произошла ошибка при разрыве связи."))

@router.message(Command("list"))
async def cmd_list(message: Message):
    """Показать список всех связей"""
    if message.chat.type != "private":
        return
    
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer(**msg_err("У вас нет прав для выполнения этой команды."))
        return
    
    connections = group_manager.get_all_connections()
    
    if not connections:
        await message.answer("📋 Связи между группами не найдены.")
        return
    
    # Группируем связи по группам проверяющих
    verifier_groups = {}
    for client_group_id, verifier_group_id, client_group_name, verifier_group_name, created_at, is_active in connections:
        if verifier_group_id not in verifier_groups:
            verifier_groups[verifier_group_id] = {
                'name': verifier_group_name,
                'clients': [],
                'created_at': created_at
            }
        verifier_groups[verifier_group_id]['clients'].append({
            'id': client_group_id,
            'name': client_group_name
        })
    
    response = "📋 Список всех активных связей:\n\n"
    for i, (verifier_id, verifier_info) in enumerate(verifier_groups.items(), 1):
        response += f"{i}. 👥 Проверяющие: {verifier_info['name'] or 'Группа проверяющих'} (ID: {verifier_id})\n"
        response += f"   📱 Обслуживает {len(verifier_info['clients'])} групп клиентов\n"
        
        for client in verifier_info['clients']:
            response += f"      • {client['name'] or 'Группа клиентов'} (ID: {client['id']})\n"
        
        response += f"   📅 Создано: {verifier_info['created_at']}\n\n"
    
    await message.answer(response)

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Показать статистику по связям"""
    if message.chat.type != "private":
        return
    
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer(**msg_err("У вас нет прав для выполнения этой команды."))
        return
    
    stats = group_manager.get_connection_stats()
    
    response = "📊 Статистика по связям групп:\n\n"
    response += f"🔗 Всего связей: {stats['total']}\n"
    response += f"✅ Активных: {stats['active']}\n"
    response += f"❌ Неактивных: {stats['inactive']}\n"
    response += f"📱 Уникальных групп клиентов: {stats['unique_clients']}\n"
    response += f"👥 Уникальных групп проверяющих: {stats['unique_verifiers']}\n"
    
    await message.answer(response)

@router.message(Command("peer_id"))
async def cmd_peer_id(message: Message):
    """Показать ID группы и информацию о связях"""
    if message.chat.type == "private":
        await message.answer(**msg_err("Эта команда работает только в группах."))
        return
    
    chat_id = message.chat.id
    chat_title = message.chat.title or "Группа"
    chat_type = message.chat.type
    
    # Получаем информацию о роли и связях
    role = group_manager.get_group_role(chat_id)
    
    response = f"📋 Информация о группе:\n\n"
    response += f"🏷️ Название: {chat_title}\n"
    response += f"🆔 ID группы: `{chat_id}`\n"
    response += f"👤 Роль: {role or 'не связана'}\n\n"
    
    await message.answer(response, parse_mode="Markdown")

@router.message(Command("update_group_id"))
async def cmd_update_group_id(message: Message):
    """Обновить ID группы (например, при обновлении до супергруппы)"""
    if message.chat.type != "private":
        return
    
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer(**msg_err("У вас нет прав для выполнения этой команды."))
        return
    
    try:
        if not message.text:
            await message.answer(**msg_err("Неверный формат команды."))
            return
        args = message.text.split()[1:]
        if len(args) != 2:
            await message.answer(
                **msg_err(
                    "Неверный формат команды.\n"
                "Используйте: /update_group_id <старый_id> <новый_id>"
                )
            )
            return
        
        old_group_id = int(args[0])
        new_group_id = int(args[1])
        
        # Проверяем, что новая группа существует
        try:
            new_chat = await bot.get_chat(new_group_id)
        except Exception as e:
            await message.answer(**msg_err("Не удалось получить информацию о новой группе. Проверьте ID."))
            return
        
        # Обновляем ID группы через менеджер
        if group_manager.update_group_id(old_group_id, new_group_id):
            await message.answer(
                **msg_ok(
                    f"ID группы успешно обновлен!\n\n"
                f"🔄 Старый ID: {old_group_id}\n"
                f"🆕 Новый ID: {new_group_id}\n"
                f"🏷️ Название: {getattr(new_chat, 'title', 'Группа')}\n\n"
                f"Теперь все связи будут работать с новым ID группы."
                )
            )
        else:
            await message.answer(**msg_err("Группа с указанным старым ID не найдена в базе данных."))
            
    except ValueError:
        await message.answer(**msg_err("ID групп должны быть числами."))
    except Exception as e:
        logging.error(f"Ошибка при обновлении ID группы: {e}")
        await message.answer(**msg_err("Произошла ошибка при обновлении ID группы."))


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Показать справку"""
    if message.chat.type != "private":
        return
    
    # Проверяем, является ли пользователь администратором
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer(**msg_err("У вас нет прав для выполнения этой команды."))
        return
    
    help_text = f"""
📚 Справка по {BOT_NAME}

🔗 Команды администратора:
/connect <id_клиентов> <id_проверяющих> - связать группу клиентов с группой проверяющих
/disconnect <id_клиентов> <id_проверяющих> - разорвать связь
/list - показать все связи с ID групп
/stats - статистика по связям
/peer_id - показать ID группы
/update_group_id <старый_id> <новый_id> - обновить ID группы (при обновлении до супергруппы)
/help - эта справка

📱 Поведение в группах:

Группа клиентов:
• /п - отправить фото чека (только с фото)

Группа проверяющих:
• Кнопки «Подтвердить» и «Фейк/Нету» под фото чека (после ввода суммы подпись «Проверено» и кнопка с галочкой)
• /чек <сумма> - добавить чек с указанной суммой (только после подтверждения фото чека)

🔄 Автоматические действия:
• Фото чека из группы клиентов пересылается в группу проверяющих с кнопками
• При нажатии "Подтвердить" бот просит ввести сумму командой /чек (кнопки остаются активными)
• При нажатии «Фейк/Нету» — подтверждение «Да/Нет», затем подпись «Проверено · фейк» и кнопка с крестиком
• После добавления чека подпись «Проверено» и кнопка с галочкой (нажатие напоминает, что чек уже проверен)
• Подтверждения отправляются в группу клиентов с reply на сообщение с фото
• Если проверяющий вводит чек без подтверждения фото, чек добавляется только в его группу
• Все остальные сообщения игнорируются
• Автоматическое обновление ID группы при обновлении до супергруппы

💡 Для получения ID группы:
1. Добавьте @userinfobot в группу
2. Отправьте любое сообщение
3. Бот покажет chat_id группы

🔧 Управление связями:
• Одна группа клиентов может быть связана только с одной группой проверяющих
• Одна группа проверяющих может обслуживать несколько групп клиентов одновременно
• При создании новой связи старая автоматически деактивируется
• Используйте /disconnect для разрыва связи
• При обновлении группы до супергруппы ID автоматически обновляется

🎯 Роли групп:
• Группа клиентов - может отправлять фото чеков
• Группа проверяющих - может подтверждать/отклонять чеки и вводить суммы

⚠️ Важно о чеках:
• Чеки добавляются только в ту группу клиентов, из которой пришел фото чека
• Для добавления чека сначала нужно подтвердить фото чека кнопкой "Подтвердить"
• Команды /чек и /удалить_чек работают только с последним подтвержденным фото чека
• Связь между фото чека и группой клиентов определяется автоматически через message_links
• Если связь с фото чека не найдена, команды не выполняются
"""
    
    await message.answer(help_text)

@router.message(Command("п"), GroupRoleFilter("client"))
async def cmd_photo_check(message: Message):
    """Обработчик команды /п в группе клиентов"""
    # Фильтр уже проверил роль группы, поэтому сразу приступаем к обработке
    # Проверяем, есть ли фото
    if not message.photo:
        await message.answer(**msg_err("Команда /п должна содержать фото!"))
        return
    
    # Получаем связанную группу проверяющих через менеджер
    connected_info = group_manager.get_verifier_group(message.chat.id)
    if not connected_info:
        await message.answer(**msg_err("Эта группа клиентов не связана с группой проверяющих."))
        return
    
    verifier_group_id, verifier_group_name = connected_info
    
    try:
        rv_markup = receipt_verification_keyboard(message.chat.id, message.message_id)

        # Пересылаем фото в группу проверяющих с кнопками
        try:
            # Сначала проверяем статус бота в группе
            try:
                bot_info = await bot.get_me()
                chat_member = await bot.get_chat_member(verifier_group_id, bot_info.id)

                if chat_member.status in ["left", "kicked"]:
                    await message.answer(
                        **msg_err(
                            f"Бот не активен в группе проверяющих (статус: {chat_member.status}). Добавьте бота в группу."
                        )
                    )
                    return
                    
            except Exception as status_error:
                logging.warning(f"Не удалось проверить статус бота в группе {verifier_group_id}: {status_error}")
            
            sent_photo = await safe_send_photo(
                bot,
                verifier_group_id,
                message.photo[-1].file_id,
                caption=f"Выберите действие:",
                reply_markup=rv_markup,
            )
        except Exception as e:
            error_msg = str(e)
            logging.error(f"Ошибка при отправке фото в группу {verifier_group_id}: {error_msg}")
            
            # Добавляем диагностику токена
            try:
                bot_info = await bot.get_me()
                logging.debug(
                    "Используемый бот: @%s id=%s", bot_info.username, bot_info.id
                )
            except Exception as token_error:
                logging.error(f"Ошибка при получении информации о боте: {token_error}")
            
            if "bot was kicked from the group chat" in error_msg:
                logging.warning(f"Бот был кикнут из группы проверяющих {verifier_group_id}, но сейчас снова добавлен")
                # Пробуем отправить еще раз, так как бот уже добавлен
                try:
                    sent_photo = await safe_send_photo(
                        bot,
                        verifier_group_id,
                        message.photo[-1].file_id,
                        caption=f"Выберите действие:",
                        reply_markup=rv_markup,
                    )
                    logging.warning(
                        "/п повторная отправка ok verifier=%s client_msg=%s",
                        verifier_group_id,
                        message.message_id,
                    )
                except Exception as retry_error:
                    logging.error(f"Ошибка при повторной отправке фото: {retry_error}")
                    await message.answer(
                        **msg_err(
                            f"Не удалось отправить фото в группу проверяющих (ID: {verifier_group_id}). Проверьте права бота."
                        )
                    )
                    return
            elif "bot was blocked by the user" in error_msg:
                await message.answer(
                    **msg_err(f"Бот заблокирован в группе проверяющих (ID: {verifier_group_id}).")
                )
                return
            elif "chat not found" in error_msg:
                await message.answer(
                    **msg_err(f"Группа проверяющих не найдена (ID: {verifier_group_id}). Проверьте ID группы.")
                )
                return
            elif "not enough rights" in error_msg:
                await message.answer(
                    **msg_err(
                        f"Недостаточно прав для отправки сообщений в группу проверяющих (ID: {verifier_group_id})."
                    )
                )
                return
            else:
                await message.answer(**msg_err(f"Ошибка при отправке фото: {error_msg}"))
                return
        
        # Сохраняем связь между сообщениями для reply
        # Ключ: (source_group_id, source_message_id), Значение: (target_group_id, target_message_id)
        message_links[(message.chat.id, message.message_id)] = (
            verifier_group_id,
            sent_photo.message_id,
            None,
        )
        logging.info(
            "/п client=%s msg=%s verifier=%s sent_msg=%s",
            message.chat.id,
            message.message_id,
            verifier_group_id,
            sent_photo.message_id,
        )
        
        # Связи больше не удаляются автоматически - они остаются до перезапуска бота
        
        await message.answer(**msg_ok("Фото чека отправлено на проверку!"))
        
    except Exception as e:
        logging.error(f"Ошибка при пересылке фото: {e}")
        await message.answer(**msg_err("Ошибка при отправке фото."))

async def fetch_tron_transaction_data(hash_value: str) -> Optional[dict]:
    """Получает данные транзакции Tron по хешу"""
    try:
        url = f"https://apilist.tronscanapi.com/api/transaction-info?hash={hash_value}"
        headers = {
            "TRON-PRO-API-KEY": TRON_PRO_API_KEY
        }
        
        # Создаем SSL-контекст с отключенной проверкой сертификата
        # Это необходимо для работы на macOS, где могут быть проблемы с сертификатами
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    logging.error(f"Ошибка API: статус {response.status} для хеша {hash_value}")
                    return None
    except Exception as e:
        logging.error(f"Ошибка при запросе транзакции Tron: {e}")
        return None

def extract_amount_from_transaction_data(data: dict, wallet_address: Optional[str] = None) -> Optional[float]:
    """Извлекает amount из данных транзакции"""
    try:
        # Приоритет 1: transactionBehavior.value - основное значение транзакции
        if "transactionBehavior" in data and data["transactionBehavior"]:
            behavior = data["transactionBehavior"]
            if "value" in behavior:
                value_str = str(behavior["value"])
                # Проверяем, есть ли информация о токене для конвертации
                if "token_info" in behavior and "tokenDecimal" in behavior["token_info"]:
                    decimals = behavior["token_info"]["tokenDecimal"]
                    amount = int(value_str) / (10 ** decimals)
                    return float(amount)
                # Если decimals нет, пробуем стандартные 6 для USDT
                amount = int(value_str) / (10 ** 6)
                return float(amount)
        
        # Приоритет 2: TRC20 транзакции через trc20TransferInfo (массив)
        # Берем максимальный трансфер или трансфер с участием нужного адреса кошелька
        if "trc20TransferInfo" in data and isinstance(data["trc20TransferInfo"], list) and len(data["trc20TransferInfo"]) > 0:
            transfers = data["trc20TransferInfo"]
            max_amount = 0
            selected_transfer = None
            
            # Если указан адрес кошелька, ищем трансфер с его участием
            if wallet_address:
                wallet_address = wallet_address.strip().upper()
                for transfer_info in transfers:
                    from_addr = transfer_info.get("from_address", "").upper()
                    to_addr = transfer_info.get("to_address", "").upper()
                    if from_addr == wallet_address or to_addr == wallet_address:
                        if "amount_str" in transfer_info and "decimals" in transfer_info:
                            amount_str = transfer_info["amount_str"]
                            decimals = transfer_info["decimals"]
                            amount = int(amount_str) / (10 ** decimals)
                            if amount > max_amount:
                                max_amount = amount
                                selected_transfer = transfer_info
            
            # Если не нашли трансфер с участием адреса, берем максимальный
            if selected_transfer is None:
                for transfer_info in transfers:
                    if "amount_str" in transfer_info and "decimals" in transfer_info:
                        amount_str = transfer_info["amount_str"]
                        decimals = transfer_info["decimals"]
                        amount = int(amount_str) / (10 ** decimals)
                        if amount > max_amount:
                            max_amount = amount
                            selected_transfer = transfer_info
            
            if selected_transfer and max_amount > 0:
                return float(max_amount)
            
            # Если не нашли максимальный, берем последний (обычно основной идет последним)
            if transfers:
                transfer_info = transfers[-1]
                if "amount_str" in transfer_info and "decimals" in transfer_info:
                    amount_str = transfer_info["amount_str"]
                    decimals = transfer_info["decimals"]
                    amount = int(amount_str) / (10 ** decimals)
                    return float(amount)
        
        # Приоритет 3: TRC20 транзакции через tokenTransferInfo (одиночный)
        if "tokenTransferInfo" in data and data["tokenTransferInfo"]:
            transfer_info = data["tokenTransferInfo"]
            if "amount_str" in transfer_info and "decimals" in transfer_info:
                amount_str = transfer_info["amount_str"]
                decimals = transfer_info["decimals"]
                amount = int(amount_str) / (10 ** decimals)
                return float(amount)
        
        # Приоритет 4: Старый формат через contractData (для TRC10)
        if "contractData" in data and "amount" in data["contractData"]:
            amount = data["contractData"]["amount"]
            # Если amount в минимальных единицах (satoshi-like), конвертируем
            if "tokenInfo" in data.get("contractData", {}):
                token_decimal = data["contractData"]["tokenInfo"].get("tokenDecimal", 0)
                if token_decimal > 0:
                    amount = amount / (10 ** token_decimal)
            return float(amount)
        
        logging.warning(f"Amount не найден в данных транзакции")
        return None
    except Exception as e:
        logging.error(f"Ошибка при извлечении amount: {e}")
        return None

def check_wallet_address_in_transaction(data: dict, wallet_address: Optional[str]) -> bool:
    """Проверяет, присутствует ли адрес кошелька в транзакции (from_address или to_address)"""
    if not wallet_address:
        return True  # Если адрес не задан, пропускаем проверку
    
    wallet_address = wallet_address.strip().upper()
    
    # Проверяем TRC20 транзакции
    if "tokenTransferInfo" in data and data["tokenTransferInfo"]:
        transfer_info = data["tokenTransferInfo"]
        from_addr = transfer_info.get("from_address", "").upper()
        to_addr = transfer_info.get("to_address", "").upper()
        if from_addr == wallet_address or to_addr == wallet_address:
            return True
    
    if "trc20TransferInfo" in data and isinstance(data["trc20TransferInfo"], list):
        for transfer_info in data["trc20TransferInfo"]:
            from_addr = transfer_info.get("from_address", "").upper()
            to_addr = transfer_info.get("to_address", "").upper()
            if from_addr == wallet_address or to_addr == wallet_address:
                return True
    
    # Проверяем ownerAddress и toAddress
    owner_addr = data.get("ownerAddress", "").upper()
    to_addr = data.get("toAddress", "").upper()
    if owner_addr == wallet_address or to_addr == wallet_address:
        return True
    
    # Проверяем contractData
    if "contractData" in data:
        contract_data = data["contractData"]
        owner_addr = contract_data.get("owner_address", "").upper()
        to_addr = contract_data.get("to_address", "").upper()
        if owner_addr == wallet_address or to_addr == wallet_address:
            return True
    
    return False


# --- /рек: реквизиты в клиентские группы + анонимные ЛС (до handle_tron_links — порядок важен) ---


@router.message(Command("рек"), VerifierGroupOrAnonymousLinkedFilter())
async def cmd_rek(message: Message):
    """Реквизиты в клиентские группы и анонимные ЛС — одним сообщением (несколько строк под /рек). Админы бота или админы группы в Telegram."""
    if not message.chat or not message.text:
        return
    if not await can_broadcast_rek(message):
        await message.answer(
            **msg_err(
                "Команда /рек доступна администраторам бота или администраторам/создателю этой группы."
            )
        )
        return
    parsed = _parse_rek_one_message_text(message.text)
    if not parsed:
        await message.answer(
            "Отправьте реквизиты <b>одним сообщением</b> сразу после <code>/рек</code> — каждое поле с новой строки:\n\n"
            "<b>1</b> — банк\n"
            "<b>2</b> — ФИО (можно несколько строк подряд)\n"
            "<b>3</b> — номер карты (16 цифр, можно с пробелами)\n"
            "<b>4</b> — телефон по желанию (10–15 цифр), отдельной строкой после карты\n\n"
            "Пример без телефона:\n"
            "<pre>/рек\n"
            "Сбербанк\n"
            "Иванов Иван Иванович\n"
            "1234 5678 9012 3456</pre>\n\n"
            "С телефоном — добавьте строку в конце:\n"
            "<pre>+7 900 123-45-67</pre>",
            parse_mode="HTML",
        )
        return
    bank, fio, card16, phone = parsed
    vgid = message.chat.id
    await message.answer("Рассылаю реквизиты…")
    try:
        stats = await broadcast_rekvizit_to_linked_chats(vgid, bank, fio, card16, phone)
    except Exception as e:
        logging.exception("Ошибка рассылки /рек")
        await message.answer(**msg_err(f"Ошибка рассылки: {e}"))
        return
    if (
        stats["client_sent"] + stats["anon_sent"] == 0
        and stats["client_failed"] + stats["anon_failed"] == 0
    ):
        await message.answer(
            **msg_ok(
                "Некуда отправить: нет привязанных клиентских групп и участников анонимных комнат."
            )
        )
    else:
        await message.answer(**msg_ok("Реквизиты отправлены."))


@router.message(Command("стопрек"), VerifierGroupOrAnonymousLinkedFilter())
async def cmd_stop_rek(message: Message):
    """Ответ на последнюю рассылку /рек: не переводить по этим реквизитам."""
    if not message.chat:
        return
    vgid = message.chat.id
    rows = list_rekvizit_outbound_for_verifier(vgid)
    if not rows:
        await message.answer(
            **msg_err(
                "Нет сохранённых сообщений с реквизитами. Сначала отправьте /рек."
            )
        )
        return
    await message.answer("Отправляю предупреждение…")
    try:
        ok, _fail = await broadcast_stop_rek_replies(vgid)
    except Exception as e:
        logging.exception("Ошибка /стопрек")
        await message.answer(**msg_err(f"Ошибка: {e}"))
        return
    if ok == 0:
        await message.answer(
            **msg_err(
                "Не удалось доставить ответы. Возможно, удалены сообщения с реквизитами."
            )
        )
    else:
        await message.answer(**msg_ok("Готово."))


@router.message(F.text, F.chat.type.in_({"group", "supergroup"}))
async def handle_tron_links(message: Message):
    """Ссылки TronScan и хеши транзакций — только в группах (не в ЛС: там тикеты поддержки)."""
    if not message.text:
        return
    
    # Пропускаем команды (сообщения, начинающиеся с /)
    if message.text.strip().startswith('/'):
        return
    
    hash_values = []
    
    # Ищем ссылки на tronscan.org с транзакциями
    link_pattern = r'https?://(?:www\.)?tronscan\.org/#/transaction/([a-fA-F0-9]{64})'
    link_matches = re.findall(link_pattern, message.text)
    hash_values.extend(link_matches)
    
    # Ищем хеши транзакций напрямую (64 hex-символа)
    # Ищем слова, которые состоят только из hex-символов и имеют длину 64
    hash_pattern = r'\b([a-fA-F0-9]{64})\b'
    hash_matches = re.findall(hash_pattern, message.text)
    
    # Фильтруем найденные хеши, чтобы исключить те, что уже найдены в ссылках
    for hash_match in hash_matches:
        if hash_match not in hash_values:
            hash_values.append(hash_match)
    
    if not hash_values:
        return
    
    chat_id = message.chat.id
    initialize_db(chat_id)

    wallet_address = get_global_wallet_address()
    
    # Обрабатываем каждый найденный хеш
    for hash_value in hash_values:
        logging.info(f"Найден хеш транзакции Tron: {hash_value}")
        
        # Получаем данные транзакции
        transaction_data = await fetch_tron_transaction_data(hash_value)
        
        if transaction_data is None:
            try:
                await message.reply(**msg_err("Не удалось получить данные транзакции"))
            except Exception as e:
                logging.error(f"Ошибка при отправке сообщения об ошибке: {e}")
            continue
        
        # Проверяем адрес кошелька ДО проверки на повторную обработку
        if wallet_address:
            if not check_wallet_address_in_transaction(transaction_data, wallet_address):
                logging.warning(f"Транзакция {hash_value} не содержит адрес кошелька {wallet_address}")
                try:
                    await message.reply(
                        **msg_err(
                            f"Транзакция не содержит адрес кошелька {wallet_address}. Транзакция отклонена."
                        )
                    )
                except Exception as e:
                    logging.error(f"Ошибка при отправке сообщения: {e}")
                continue
        
        # Извлекаем amount из данных транзакции
        amount = extract_amount_from_transaction_data(transaction_data, wallet_address)
        
        if amount is None:
            try:
                await message.reply(**msg_err("Не удалось получить amount из транзакции"))
            except Exception as e:
                logging.error(f"Ошибка при отправке сообщения об ошибке: {e}")
            continue
        
        if is_transaction_hash_processed(hash_value):
            logging.info(f"Транзакция {hash_value} уже была обработана ранее в другой группе, пропускаем")
            try:
                await message.reply(f"⚠️ Транзакция {hash_value[:16]}... уже была обработана ранее")
            except Exception as e:
                logging.error(f"Ошибка при отправке сообщения: {e}")
            continue
        
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            insert_payout(chat_id, amount, timestamp)
            mark_transaction_processed(hash_value, amount, chat_id)
            await message.reply(**msg_payout_ok(f"Выплата добавлена: {amount}"))
            logging.info(f"Добавлена выплата {amount} для транзакции {hash_value}")
        except Exception as e:
            logging.error(f"Ошибка при сохранении выплаты: {e}")
            try:
                await message.reply(**msg_err(f"Ошибка при сохранении выплаты: {e}"))
            except Exception as send_error:
                logging.error(f"Ошибка при отправке сообщения об ошибке: {send_error}")

@router.callback_query()
async def handle_callback(callback: CallbackQuery):
    """Обработчик callback кнопок"""
    try:
        data = callback.data
        if not data:
            await callback.answer("❌ Некорректные данные", show_alert=True)
            return
            
        # Проверяем, что message существует
        if not callback.message:
            await callback.answer("❌ Ошибка: сообщение не найдено", show_alert=True)
            return
        
        # Проверяющие: роль в connections или группа привязана только к анонимной комнате
        role = group_manager.get_group_role(callback.message.chat.id)
        if role != "verifier" and not is_verifier_group_linked_to_anonymous_room(callback.message.chat.id):
            await callback.answer("❌ Кнопки доступны только в группах проверяющих.", show_alert=True)
            return
            
        if data.startswith("confirm_receipt:"):
            # Обработка подтверждения чека
            parts = data.split(":")
            if len(parts) != 3:
                await callback.answer("❌ Некорректные данные", show_alert=True)
                return
                
            source_group_id = int(parts[1])
            source_message_id = int(parts[2])
            
            # Проверяем, что связь с фото чека существует
            if (source_group_id, source_message_id) not in message_links:
                await callback.answer("❌ Связь с фото чека не найдена. Попробуйте еще раз.", show_alert=True)
                return
            
            
            # Проверяем, не было ли уже подтверждено это фото для данной группы проверяющих
            verifier_group_id = callback.message.chat.id
            if (verifier_group_id in last_confirmed_photo and 
                last_confirmed_photo[verifier_group_id] == (source_group_id, source_message_id)):
                # Фото уже подтверждено, просто показываем уведомление
                await callback.answer("✅ Это фото уже подтверждено. Введите сумму командой /чек <сумма>", show_alert=False)
                return
            
            # Проверяем время последнего подтверждения (защита от спама)
            current_time = time.time()
            if (verifier_group_id in last_confirmation_time and 
                current_time - last_confirmation_time[verifier_group_id] < 5):  # 5 секунд между подтверждениями
                await callback.answer("⏳ Подождите немного перед следующим подтверждением", show_alert=False)
                return
            
            # Сохраняем информацию о последнем подтвержденном фото чека для этой группы проверяющих
            last_confirmed_photo[verifier_group_id] = (source_group_id, source_message_id)
            last_confirmation_time[verifier_group_id] = current_time
            logging.info(
                "callback confirm_receipt verifier=%s client=%s mid=%s",
                verifier_group_id,
                source_group_id,
                source_message_id,
            )
            
            # Просим ввести сумму чека - отправляем новое сообщение в чат
            try:
                await bot.send_message(
                    chat_id=callback.message.chat.id,
                    text=f"💰 Введите сумму чека в формате:\n"
                         f"/чек <сумма>\n\n"
                         f"Например: /чек 1500.50"
                )
            except Exception as e:
                logging.error(f"Ошибка при отправке сообщения: {e}")
            
            # Сохраняем информацию о том, кто подтвердил чек
            await callback.answer("✅ Теперь введите сумму чека командой /чек <сумма>")
            
        elif data.startswith("fake_receipt:"):
            # Обработка отметки как фейк - показываем подтверждение
            parts = data.split(":")
            if len(parts) != 3:
                await callback.answer("❌ Некорректные данные", show_alert=True)
                return
                
            source_group_id = int(parts[1])
            source_message_id = int(parts[2])
            
            # Проверяем, что связь с фото чека существует
            if (source_group_id, source_message_id) not in message_links:
                await callback.answer("❌ Связь с фото чека не найдена. Попробуйте еще раз.", show_alert=True)
                return
            
            
            # Заменяем кнопки на "✅ Галочка" и "❌ Крестик" для подтверждения
            try:
                # Создаем новую клавиатуру с кнопками подтверждения
                builder = InlineKeyboardBuilder()
                builder.button(
                    text="Да",
                    callback_data=f"confirm_fake:{source_group_id}:{source_message_id}",
                    style="success",
                    icon_custom_emoji_id=CONFIRM_RECEIPT_CUSTOM_EMOJI_ID,
                )
                builder.button(
                    text="Нет",
                    callback_data=f"cancel_fake:{source_group_id}:{source_message_id}",
                    style="danger",
                    icon_custom_emoji_id=CROSS_CUSTOM_EMOJI_ID,
                )
                builder.adjust(2)
                
                # Обновляем подпись и кнопки
                await bot.edit_message_caption(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    caption="Подтвердите отметку как фейк:"
                )
                await bot.edit_message_reply_markup(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    reply_markup=builder.as_markup()
                )
            except Exception as e:
                logging.error(f"Ошибка при показе кнопок подтверждения: {e}")
            
            await callback.answer("Подтвердите отметку как фейк")
            
        elif data.startswith("confirm_fake:"):
            # Подтверждение отметки как фейк
            parts = data.split(":")
            if len(parts) != 3:
                await callback.answer("❌ Некорректные данные", show_alert=True)
                return
                
            source_group_id = int(parts[1])
            source_message_id = int(parts[2])
            
            # Заменяем кнопки на «Проверено» с кастомным крестиком и обновляем подпись
            try:
                # Создаем новую клавиатуру с кнопкой «Проверено»
                builder = InlineKeyboardBuilder()
                builder.button(
                    text="Проверено",
                    callback_data="already_checked",
                    style="danger",
                    icon_custom_emoji_id=CROSS_CUSTOM_EMOJI_ID,
                )
                builder.adjust(1)
                
                # Обновляем подпись и кнопки
                await bot.edit_message_caption(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    caption="Проверено · фейк",
                )
                await bot.edit_message_reply_markup(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    reply_markup=builder.as_markup()
                )
            except Exception as e:
                logging.error(f"Ошибка при обновлении подписи и кнопок: {e}")
            
            # Отправляем сообщение о том, что чек отмечен как фейк
            try:
                _fake_txt = msg_err("Чек отмечен как фейк/нет чека")
                await bot.send_message(
                    chat_id=callback.message.chat.id,
                    text=_fake_txt["text"],
                    entities=_fake_txt.get("entities"),
                )
            except Exception as e:
                logging.error(f"Ошибка при отправке сообщения: {e}")
            
            _fake_client = msg_err("Чек отмечен как фейк/нет чека")
            is_anon_dm = (
                source_group_id > 0
                and (source_group_id, source_message_id) in message_links
                and message_links[(source_group_id, source_message_id)][0] == callback.message.chat.id
            )
            try:
                if is_anon_dm:
                    await _notify_anonymous_verifier_outcome(
                        source_group_id=source_group_id,
                        source_message_id=source_message_id,
                        text=_fake_client["text"],
                        entities=_fake_client.get("entities"),
                    )
                else:
                    await safe_send_message(
                        bot,
                        source_group_id,
                        _fake_client["text"],
                        entities=_fake_client.get("entities"),
                        reply_to_message_id=source_message_id,
                    )
            except Exception as e:
                logging.error(f"Ошибка при отправке уведомления о фейке с reply: {e}")
                if not is_anon_dm:
                    try:
                        _fake_fb = msg_err("Чек отмечен как фейк/нет чека")
                        await safe_send_message(
                            bot,
                            source_group_id,
                            _fake_fb["text"],
                            entities=_fake_fb.get("entities"),
                        )
                    except Exception as e2:
                        logging.error(f"Ошибка при отправке уведомления о фейке: {e2}")
            
            # Сбрасываем состояние подтвержденного фото после отметки как фейк
            verifier_group_id = callback.message.chat.id
            if verifier_group_id in last_confirmed_photo:
                del last_confirmed_photo[verifier_group_id]
                # Очищаем также время последнего подтверждения
                if verifier_group_id in last_confirmation_time:
                    del last_confirmation_time[verifier_group_id]
            
            await callback.answer("❌ Чек отмечен как фейк")
            
        elif data.startswith("cancel_fake:"):
            # Отмена отметки как фейк - возвращаем исходные кнопки
            parts = data.split(":")
            if len(parts) != 3:
                await callback.answer("❌ Некорректные данные", show_alert=True)
                return
                
            source_group_id = int(parts[1])
            source_message_id = int(parts[2])
            
            # Возвращаем исходные кнопки "Подтвердить" и "Фейк/Нету"
            try:
                # Возвращаем исходную подпись и кнопки
                await bot.edit_message_caption(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    caption="Выберите действие:"
                )
                await bot.edit_message_reply_markup(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    reply_markup=receipt_verification_keyboard(source_group_id, source_message_id),
                )
            except Exception as e:
                logging.error(f"Ошибка при возврате исходных кнопок: {e}")
            
            await callback.answer("Отмена отметки как фейк")
            
        elif data.startswith("already_checked"):
            # Обработка нажатия на кнопку «Проверено» (после успешного чека или после фейка)
            parts = data.split(":")
            if len(parts) == 2:
                # Есть сумма в callback_data
                amount = float(parts[1])
                if amount > 0:
                    await callback.answer(f"✅ Чек на {amount} уже проверен и добавлен в базу данных", show_alert=True)
                else:
                    await callback.answer("✅ Чек уже проверен и добавлен в базу данных", show_alert=True)
            else:
                # Старый формат без суммы (для фейковых чеков)
                await callback.answer("✅ Чек уже проверен и добавлен в базу данных", show_alert=True)
            
    except Exception as e:
        logging.error(f"Ошибка при обработке callback: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@router.message(F.chat.type == "private")
async def private_support_inbox(message: Message):
    """Не-командные сообщения в ЛС от не-админов — тикет в CRM."""
    if not message.from_user:
        return
    if await try_anonymous_private_message(message, master_mode=True):
        return
    if is_admin(message.from_user.id):
        return
    if message.text and message.text.startswith("/"):
        return
    text = (message.text or message.caption or "").strip()
    if message.photo:
        text = text or "[фото]"
    if message.document:
        text = text or "[документ]"
    if message.sticker:
        text = "[стикер]"
    if not text:
        text = "[сообщение]"
    try:
        ticket_id, reopened = record_support_message_from_user(
            message.from_user.id,
            message.from_user.username,
            text,
            bot_instance_id=1,
        )
        try:
            notify_support_staff_new_ticket_message(ticket_id, text)
        except Exception:
            logging.exception("Уведомление support о новом тикете")
        ack = "✉️ Сообщение передано в поддержку. Мы ответим в ближайшее время."
        if reopened:
            ack = "🔄 Обращение снова открыто.\n\n" + ack
        await message.answer(ack)
    except SupportSpamError:
        await message.answer(
            "⏳ Слишком много сообщений подряд. Подождите несколько секунд и напишите ещё раз."
        )
    except Exception as e:
        logging.exception("Ошибка записи тикета поддержки: %s", e)
        await message.answer(**msg_err("Не удалось отправить сообщение. Попробуйте позже."))


BROADCAST_SERVER_HOST = os.environ.get("BROADCAST_SERVER_HOST", "127.0.0.1")
BROADCAST_SERVER_PORT = int(os.environ.get("BROADCAST_SERVER_PORT", "8765"))


async def run_broadcast_server():
    """HTTP-сервер для рассылки из веб-интерфейса: тот же алгоритм, что и в scheduler (send_message_optimized)."""
    from aiohttp import web

    @web.middleware
    async def broadcast_auth_middleware(request: web.Request, handler):
        p = request.path or ""
        if p.startswith("/broadcast") and os.environ.get("BROADCAST_INTERNAL_SECRET", "").strip():
            if request.headers.get("X-Internal-Secret") != os.environ["BROADCAST_INTERNAL_SECRET"].strip():
                return web.json_response({"error": "Unauthorized"}, status=401)
        return await handler(request)

    async def post_broadcast(request: web.Request) -> web.Response:
        try:
            body = await request.json()
            text = (body.get("text") or "").strip()
            exclude_chat_ids = body.get("exclude_chat_ids") or []
            if not text:
                return web.json_response({"error": "Введите текст сообщения"}, status=400)
            exclude = set(int(x) for x in exclude_chat_ids if isinstance(x, (int, float)))
            chat_ids = [c for c in group_manager.get_broadcast_chat_ids() if c not in exclude]
            if not chat_ids:
                return web.json_response({
                    "success": True,
                    "sent": 0,
                    "failed": 0,
                    "total": 0,
                    "message": "Нет групп для рассылки (все исключены или список пуст)",
                })
            sent = 0
            on_inaccessible = lambda cid: group_manager.mark_broadcast_inaccessible(cid)
            for chat_id in chat_ids:
                ok = await send_message_optimized(
                    chat_id, text, parse_mode="HTML", on_inaccessible=on_inaccessible
                )
                if ok:
                    sent += 1
                await asyncio.sleep(0.05)
            return web.json_response({
                "success": True,
                "sent": sent,
                "failed": len(chat_ids) - sent,
                "total": len(chat_ids),
                "message": f"Отправлено: {sent} из {len(chat_ids)}",
            })
        except Exception as e:
            logging.exception("Ошибка в POST /broadcast")
            return web.json_response({"error": str(e)}, status=500)

    async def post_relay_anonymous_photo_check(request: web.Request) -> web.Response:
        """Внутренний relay: байты фото → основной бот → группа проверяющих (дочерние анонимные боты)."""
        try:
            data = await request.post()
            user_id_s = data.get("user_id")
            verifier_gid_s = data.get("verifier_group_id")
            photo_file = data.get("photo")
            if user_id_s is None or verifier_gid_s is None or not photo_file:
                return web.json_response(
                    {"error": "Нужны поля user_id, verifier_group_id и файл photo"},
                    status=400,
                )
            user_id = int(user_id_s)
            verifier_group_id = int(verifier_gid_s)
            raw_file = getattr(photo_file, "file", None)
            if raw_file is not None:
                raw = raw_file.read()
            else:
                raw = bytes(photo_file) if photo_file else b""
            if not raw:
                return web.json_response({"error": "Пустой файл photo"}, status=400)
            fn = getattr(photo_file, "filename", None)
            filename = (fn.strip() if isinstance(fn, str) and fn.strip() else None) or "check.jpg"
            if len(filename) > 96:
                filename = filename[-96:]
            oms = data.get("original_message_id")
            original_dm_message_id: Optional[int] = None
            if oms is not None and str(oms).strip():
                try:
                    original_dm_message_id = int(oms)
                except (TypeError, ValueError):
                    original_dm_message_id = None
            acs = data.get("anonymous_chat_id")
            anonymous_chat_id: Optional[int] = None
            if acs is not None and str(acs).strip():
                try:
                    anonymous_chat_id = int(acs)
                except (TypeError, ValueError):
                    anonymous_chat_id = None
            dm_link = await relay_anonymous_photo_check_from_bytes(
                user_id,
                verifier_group_id,
                raw,
                filename=filename,
                original_dm_message_id=original_dm_message_id,
                anonymous_chat_id=anonymous_chat_id,
            )
            return web.json_response({"success": True, "dm_link_message_id": dm_link})
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        except Exception as e:
            logging.exception("Ошибка в POST /broadcast/relay-anonymous-photo-check")
            return web.json_response({"error": str(e)}, status=500)

    async def post_check_admin_chats(request: web.Request) -> web.Response:
        """Проверка доступа бота к chat_id из веб-интерфейса /admin/chats (параллельно, чтобы уложиться в таймауты прокси)."""
        try:
            body = await request.json()
            raw = body.get("chat_ids") or []
            chat_ids: List[int] = []
            for x in raw:
                try:
                    chat_ids.append(int(x))
                except (TypeError, ValueError):
                    pass
            if not chat_ids:
                return web.json_response({"error": "Нужен непустой массив chat_ids"}, status=400)

            # ~15 одновременных get_chat — быстрее последовательного цикла, безопасно для лимитов Telegram
            sem = asyncio.Semaphore(15)

            async def _probe(cid: int) -> Tuple[str, int, bool]:
                """Возвращает ('ok'|'bad'|'warn', chat_id, name_updated)."""
                async with sem:
                    try:
                        chat = await bot.get_chat(cid)
                        group_manager.clear_broadcast_inaccessible(cid)
                        name = (chat.title or chat.username or chat.first_name or "").strip()
                        if name:
                            group_manager.upsert_broadcast_chat_row(cid, name)
                        return ("ok", cid, bool(name))
                    except Exception as e:
                        err_str = str(e).lower()
                        if any(
                            x in err_str
                            for x in (
                                "kicked",
                                "blocked",
                                "not found",
                                "chat not found",
                                "forbidden",
                                "deactivated",
                                "bot was kicked",
                                "have no rights",
                                "not enough rights",
                            )
                        ):
                            group_manager.mark_broadcast_inaccessible(cid)
                            return ("bad", cid, False)
                        group_manager.clear_broadcast_inaccessible(cid)
                        logging.warning("get_chat admin panel chat_id=%s: %s", cid, e)
                        return ("warn", cid, False)

            parts = await asyncio.gather(*(_probe(cid) for cid in chat_ids), return_exceptions=True)

            accessible_ids: List[int] = []
            inaccessible_ids: List[int] = []
            names_updated = 0
            for item in parts:
                if isinstance(item, BaseException):
                    logging.exception("check-admin-chats: %s", item)
                    continue
                kind, cid, got_name = item
                if kind == "bad":
                    inaccessible_ids.append(cid)
                else:
                    accessible_ids.append(cid)
                    if got_name:
                        names_updated += 1

            return web.json_response(
                {
                    "success": True,
                    "checked": len(chat_ids),
                    "accessible": len(accessible_ids),
                    "inaccessible": len(inaccessible_ids),
                    "accessible_ids": accessible_ids,
                    "inaccessible_ids": inaccessible_ids,
                    "names_updated": names_updated,
                }
            )
        except Exception as e:
            logging.exception("Ошибка в POST /broadcast/check-admin-chats")
            return web.json_response({"error": str(e)}, status=500)

    async def post_create_invite_links(request: web.Request) -> web.Response:
        """Создать дополнительные бессрочные invite-ссылки (бот — админ с правом приглашений)."""
        try:
            body = await request.json()
            raw = body.get("chat_ids") or []
            chat_ids: List[int] = []
            for x in raw:
                try:
                    chat_ids.append(int(x))
                except (TypeError, ValueError):
                    pass
            if not chat_ids:
                return web.json_response({"error": "Нужен непустой массив chat_ids"}, status=400)

            # Меньше параллелизма, чем у get_chat: createChatInviteLink чаще упирается в лимиты
            sem = asyncio.Semaphore(4)

            async def _one_invite(cid: int) -> dict:
                async with sem:
                    try:
                        inv = await bot.create_chat_invite_link(chat_id=cid)
                        upsert_admin_chat_invite_link(cid, inv.invite_link)
                        return {
                            "chat_id": cid,
                            "invite_link": inv.invite_link,
                            "error": None,
                            "migrated_from": None,
                        }
                    except TelegramMigrateToChat as e:
                        new_id = e.migrate_to_chat_id
                        try:
                            migrate_telegram_chat_id(cid, new_id)
                        except Exception as mig_err:
                            logging.exception(
                                "migrate_telegram_chat_id при create_chat_invite_link: %s -> %s",
                                cid,
                                new_id,
                            )
                            return {
                                "chat_id": cid,
                                "invite_link": None,
                                "error": str(mig_err),
                                "migrated_from": None,
                            }
                        try:
                            inv = await bot.create_chat_invite_link(chat_id=new_id)
                            upsert_admin_chat_invite_link(new_id, inv.invite_link)
                            return {
                                "chat_id": new_id,
                                "invite_link": inv.invite_link,
                                "error": None,
                                "migrated_from": cid,
                            }
                        except Exception as e2:
                            return {
                                "chat_id": new_id,
                                "invite_link": None,
                                "error": str(e2),
                                "migrated_from": cid,
                            }
                    except Exception as e:
                        err = str(e)
                        if (
                            "group chat was upgraded to a supergroup chat" in err
                            or "migrated to a supergroup" in err.lower()
                        ):
                            new_id = analyze_exception_for_migrate_id(e)
                            if not new_id:
                                m = re.search(
                                    r"supergroup with id\s+(-?\d+)\s+from\s+(-?\d+)",
                                    err,
                                    re.I,
                                )
                                if m:
                                    new_id = int(m.group(1))
                            if new_id:
                                try:
                                    migrate_telegram_chat_id(cid, new_id)
                                except Exception as mig_err:
                                    return {
                                        "chat_id": cid,
                                        "invite_link": None,
                                        "error": str(mig_err),
                                        "migrated_from": None,
                                    }
                                try:
                                    inv = await bot.create_chat_invite_link(chat_id=new_id)
                                    upsert_admin_chat_invite_link(new_id, inv.invite_link)
                                    return {
                                        "chat_id": new_id,
                                        "invite_link": inv.invite_link,
                                        "error": None,
                                        "migrated_from": cid,
                                    }
                                except Exception as e2:
                                    return {
                                        "chat_id": new_id,
                                        "invite_link": None,
                                        "error": str(e2),
                                        "migrated_from": cid,
                                    }
                        return {
                            "chat_id": cid,
                            "invite_link": None,
                            "error": err,
                            "migrated_from": None,
                        }

            raw_results = await asyncio.gather(*(_one_invite(cid) for cid in chat_ids), return_exceptions=True)
            results: List[Any] = []
            for r in raw_results:
                if isinstance(r, BaseException):
                    logging.exception("create-invite-links: %s", r)
                    continue
                results.append(r)
            return web.json_response({"success": True, "results": results})
        except Exception as e:
            logging.exception("Ошибка в POST /broadcast/create-invite-links")
            return web.json_response({"error": str(e)}, status=500)

    async def post_check_availability(request: web.Request) -> web.Response:
        """Проверка доступности групп: get_chat по каждому, сохранение названий, пометка недоступных."""
        try:
            chat_ids = group_manager.get_broadcast_chat_ids()
            if not chat_ids:
                return web.json_response({
                    "success": True,
                    "checked": 0,
                    "accessible": 0,
                    "inaccessible": 0,
                    "names_updated": 0,
                    "message": "Нет групп для проверки",
                })
            accessible = 0
            inaccessible = 0
            names_updated = 0
            for chat_id in chat_ids:
                try:
                    chat = await bot.get_chat(chat_id)
                    accessible += 1
                    name = (chat.title or chat.username or chat.first_name or "").strip()
                    if name:
                        group_manager.update_broadcast_chat_name(chat_id, name)
                        names_updated += 1
                except Exception as e:
                    err_str = str(e).lower()
                    if any(x in err_str for x in ("kicked", "blocked", "not found", "chat not found", "forbidden")):
                        group_manager.mark_broadcast_inaccessible(chat_id)
                        inaccessible += 1
                    else:
                        accessible += 1
                await asyncio.sleep(0.05)
            return web.json_response({
                "success": True,
                "checked": len(chat_ids),
                "accessible": accessible,
                "inaccessible": inaccessible,
                "names_updated": names_updated,
                "message": f"Проверено: {len(chat_ids)}, доступно: {accessible}, недоступно: {inaccessible}, названий обновлено: {names_updated}",
            })
        except Exception as e:
            logging.exception("Ошибка в POST /broadcast/check-availability")
            return web.json_response({"error": str(e)}, status=500)

    def get_inactive_groups(request: web.Request) -> web.Response:
        """Группы, в которых за текущий день не было ни одного чека."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            chat_ids = group_manager.get_broadcast_chat_ids()
            inactive = []
            for chat_id in chat_ids:
                try:
                    if not has_receipt_on_local_date(chat_id, today):
                        inactive.append(chat_id)
                except Exception:
                    inactive.append(chat_id)
            return web.json_response({"chat_ids": inactive})
        except Exception as e:
            logging.exception("Ошибка в GET /broadcast/inactive-groups")
            return web.json_response({"error": str(e)}, status=500)

    app = web.Application(middlewares=[broadcast_auth_middleware])
    app.router.add_post("/broadcast", post_broadcast)
    app.router.add_post("/broadcast/relay-anonymous-photo-check", post_relay_anonymous_photo_check)
    app.router.add_post("/broadcast/check-availability", post_check_availability)
    app.router.add_post("/broadcast/check-admin-chats", post_check_admin_chats)
    app.router.add_post("/broadcast/create-invite-links", post_create_invite_links)
    app.router.add_get("/broadcast/inactive-groups", get_inactive_groups)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, BROADCAST_SERVER_HOST, BROADCAST_SERVER_PORT)
    await site.start()
    logging.info(f"Сервер рассылки: http://{BROADCAST_SERVER_HOST}:{BROADCAST_SERVER_PORT}/broadcast")
    await asyncio.Event().wait()


async def _watch_bot_token_change(last_token: str) -> None:
    """Пока идёт start_polling: периодически проверяем БД и при смене токена вызываем dp.stop_polling()."""
    from bot.bot_token import resolve_bot_token

    while True:
        await asyncio.sleep(12)
        try:
            cur = resolve_bot_token()
            if cur != last_token:
                logging.info("Обнаружена смена токена бота, корректная остановка polling…")
                try:
                    await dp.stop_polling()
                except RuntimeError as e:
                    if "Polling is not started" not in str(e):
                        logging.warning("stop_polling: %s", e)
                return
        except Exception:
            pass


async def main():
    from bot.bot_token import resolve_bot_token
    from bot.crm_support import init_crm_schema
    from bot.pg import init_schema

    init_schema()
    last_token = resolve_bot_token()
    init_crm_schema(last_token)
    bot.init(last_token)
    setup_scheduler()
    group_manager.refresh_broadcast_chats()
    asyncio.create_task(run_broadcast_server())
    dp.include_router(router)

    while True:
        watch_task = asyncio.create_task(_watch_bot_token_change(last_token))
        try:
            await dp.start_polling(
                bot.inner,
                polling_timeout=30,
                close_bot_session=True,
            )
        except Exception as e:
            logging.exception("Ошибка start_polling: %s", e)
            break
        finally:
            watch_task.cancel()
            try:
                await watch_task
            except asyncio.CancelledError:
                pass

        new_token = resolve_bot_token()
        try:
            await bot.replace(new_token)
        except Exception as e:
            logging.exception("Не удалось пересоздать Bot: %s", e)
            break
        last_token = new_token
        logging.info("Polling перезапущен с актуальным токеном")


if __name__ == "__main__":
    asyncio.run(main())
