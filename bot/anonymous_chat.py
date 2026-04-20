"""Анонимные комнаты в ЛС: инвайты, участники, релей сообщений (PostgreSQL)."""
from __future__ import annotations

import html as html_lib
import json
import logging
import random
import urllib.error
import urllib.request
from datetime import datetime
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

from aiogram import Bot as AiogramBot
from aiogram.exceptions import TelegramBadRequest

from . import config
from .group_queries import _normalize_ts, format_ts_ru_msk
from .pg import connection

logger = logging.getLogger(__name__)

_MSK_ANON = ZoneInfo("Europe/Moscow")

# Заголовок в /инфо и отчётах, если нет сохранённого имени бота из Telegram.
ANONYMOUS_CHAT_TITLE_FALLBACK = "Анонимный чат"

# naive ts в БД — UTC (как в format_ts_ru_msk); «день» для фильтров — календарный день в Москве.
_SQL_RECEIPT_DATE_MSK = "((r.ts AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Moscow')::date"
_SQL_RECEIPT_DATE_MSK_NO_ALIAS = "((ts AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Moscow')::date"


def anonymous_today_msk_date_str() -> str:
    """Сегодня по Europe/Moscow (совпадает с отображением времени чека)."""
    return datetime.now(_MSK_ANON).strftime("%Y-%m-%d")

# Случайные никнеймы для анонимных комнат (английский + эмодзи, до 32 символов).
_ANON_NICK_EMOJI = (
    "🦊",
    "🌙",
    "⚡",
    "🌊",
    "🔥",
    "✨",
    "🎯",
    "🚀",
    "💎",
    "🌿",
    "🎭",
    "🦄",
    "🐙",
    "🦋",
    "⭐️",
    "🍀",
    "🎸",
    "🌴",
)
_ANON_NICK_ADJ = (
    "Swift",
    "Quiet",
    "Bright",
    "Neon",
    "Cosmic",
    "Silent",
    "Golden",
    "Wild",
    "Lunar",
    "Solar",
    "Misty",
    "Crimson",
    "Azure",
    "Shadow",
    "Frost",
    "Storm",
    "Nova",
    "Pixel",
    "Cyber",
    "Turbo",
    "Rapid",
    "Noble",
    "Brave",
    "Calm",
)
_ANON_NICK_NOUN = (
    "Fox",
    "Owl",
    "Tiger",
    "Wolf",
    "Bear",
    "Hawk",
    "Raven",
    "Dragon",
    "Phoenix",
    "Lynx",
    "Comet",
    "Flux",
    "Wave",
    "Spark",
    "Echo",
    "Vibe",
    "Ninja",
    "Ghost",
    "Wizard",
    "Knight",
    "Panda",
    "Eagle",
    "Shark",
    "Falcon",
)


def generate_random_nickname_options(count: int = 5) -> List[str]:
    """Уникальные случайные никнеймы на английском с эмодзи (1–32 символа для БД)."""
    out: List[str] = []
    seen: Set[str] = set()
    max_attempts = max(80, count * 40)
    for _ in range(max_attempts):
        if len(out) >= count:
            break
        adj = random.choice(_ANON_NICK_ADJ)
        noun = random.choice(_ANON_NICK_NOUN)
        emoji = random.choice(_ANON_NICK_EMOJI)
        nick = f"{emoji} {adj}{noun}"
        if len(nick) > 32:
            nick = f"{emoji} {noun}"
        if len(nick) > 32:
            nick = f"{emoji}{noun}"[:32]
        if nick in seen:
            continue
        seen.add(nick)
        out.append(nick)
    # На крайний случай — добиваем уникальными числовыми суффиксами
    n = 0
    while len(out) < count:
        n += 1
        emoji = random.choice(_ANON_NICK_EMOJI)
        nick = f"{emoji} Guest{n}"
        if nick not in seen and len(nick) <= 32:
            seen.add(nick)
            out.append(nick)
    return out[:count]


def lookup_valid_invite(token: str) -> Optional[Tuple[int, int]]:
    """По токену: (invite_id, anonymous_chat_id) или None."""
    t = (token or "").strip()
    if not t:
        return None
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, anonymous_chat_id FROM anonymous_chat_invites
            WHERE token = %s AND used_at IS NULL AND expires_at > NOW()
            """,
            (t,),
        )
        row = cur.fetchone()
        if not row:
            return None
        cur.execute(
            "SELECT is_active FROM anonymous_chats WHERE id = %s",
            (int(row[1]),),
        )
        r2 = cur.fetchone()
        if not r2 or not r2[0]:
            return None
        return int(row[0]), int(row[1])


def try_switch_active_room_by_invite_token(telegram_user_id: int, token: str) -> Optional[int]:
    """Уже участник: по той же ссылке-приглашению переключить активную комнату в ЛС с основным ботом."""
    t = (token or "").strip()
    if not t:
        return None
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT i.anonymous_chat_id FROM anonymous_chat_invites i
            JOIN anonymous_chats c ON c.id = i.anonymous_chat_id
            WHERE i.token = %s AND c.is_active = TRUE
            """,
            (t,),
        )
        row = cur.fetchone()
        if not row:
            return None
        room_id = int(row[0])
        cur.execute(
            """
            SELECT 1 FROM anonymous_chat_members
            WHERE telegram_user_id = %s AND anonymous_chat_id = %s
            """,
            (telegram_user_id, room_id),
        )
        if not cur.fetchone():
            return None
    set_active_dm_room(telegram_user_id, room_id)
    return room_id


def room_has_child_bot(anonymous_chat_id: int) -> bool:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT child_bot_token FROM anonymous_chats
            WHERE id = %s AND is_active = TRUE
            """,
            (anonymous_chat_id,),
        )
        row = cur.fetchone()
        return bool(row and row[0] and str(row[0]).strip())


def get_child_bot_token(anonymous_chat_id: int) -> Optional[str]:
    """Токен дочернего бота комнаты (для релея и уведомлений в ЛС анонимного чата)."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT child_bot_token FROM anonymous_chats
            WHERE id = %s AND is_active = TRUE
            """,
            (anonymous_chat_id,),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return None
        t = str(row[0]).strip()
        return t if t else None


def get_child_bot_username_for_room(anonymous_chat_id: int) -> Optional[str]:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT child_bot_username FROM anonymous_chats WHERE id = %s",
            (anonymous_chat_id,),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return None
        return str(row[0]).strip().lstrip("@")


def telegram_get_me(token: str) -> Tuple[str, int, str]:
    """Возвращает (username без @, bot id, first_name — отображаемое имя бота в Telegram)."""
    url = f"https://api.telegram.org/bot{token.strip()}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        raise ValueError(f"telegram_error: {e}") from e
    if not data.get("ok"):
        raise ValueError("invalid_token")
    r = data["result"]
    un = str(r.get("username") or "").lstrip("@")
    fn = str(r.get("first_name") or "").strip()
    return un, int(r["id"]), fn


def set_child_bot_token(room_id: int, token: str) -> Tuple[str, int]:
    """Проверяет токен через getMe, сохраняет. Возвращает (username, bot_id)."""
    username, bot_id, first_name = telegram_get_me(token)
    fn_db = first_name if first_name else None
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE anonymous_chats
            SET child_bot_token = %s,
                child_bot_username = %s,
                child_bot_id = %s,
                child_bot_first_name = %s
            WHERE id = %s AND is_active = TRUE
            """,
            (token.strip(), username, bot_id, fn_db, room_id),
        )
        if cur.rowcount != 1:
            raise ValueError("room_not_found")
    return username, bot_id


def _resolve_anon_bot_title_label(has_child_bot: bool, child_first_name: str) -> str:
    """Имя бота из Telegram (first_name); иначе «Анонимный чат» или BOT_DISPLAY_NAME для мастер-бота."""
    fn = (child_first_name or "").strip()
    if fn:
        return fn
    if has_child_bot:
        return ANONYMOUS_CHAT_TITLE_FALLBACK
    if config.BOT_DISPLAY_NAME:
        return config.BOT_DISPLAY_NAME.strip()
    return ANONYMOUS_CHAT_TITLE_FALLBACK


def list_active_child_bot_tokens() -> List[Tuple[int, str]]:
    """Список (room_id, token) для дочерних ботов."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, child_bot_token FROM anonymous_chats
            WHERE is_active = TRUE AND child_bot_token IS NOT NULL
              AND TRIM(child_bot_token) <> ''
            """
        )
        return [(int(r[0]), str(r[1]).strip()) for r in cur.fetchall()]


def save_anonymous_verifier_notify_targets(
    anonymous_chat_id: int,
    from_telegram_user_id: int,
    dm_source_message_id: int,
    peer_rows: List[Tuple[int, int]],
) -> None:
    """Сохраняет id релей-сообщений с фото /п для последующего reply при уведомлении о проверке."""
    if not peer_rows:
        return
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            DELETE FROM anonymous_verifier_notify_reply
            WHERE anonymous_chat_id = %s AND from_telegram_user_id = %s AND dm_source_message_id = %s
            """,
            (anonymous_chat_id, from_telegram_user_id, dm_source_message_id),
        )
        for peer_id, relay_mid in peer_rows:
            cur.execute(
                """
                INSERT INTO anonymous_verifier_notify_reply
                (anonymous_chat_id, from_telegram_user_id, dm_source_message_id, peer_telegram_user_id, relay_message_id)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    anonymous_chat_id,
                    from_telegram_user_id,
                    dm_source_message_id,
                    peer_id,
                    relay_mid,
                ),
            )


def pop_anonymous_verifier_notify_targets(
    anonymous_chat_id: int,
    from_telegram_user_id: int,
    dm_source_message_id: int,
) -> List[Tuple[int, int]]:
    """Забирает и удаляет цели reply для уведомления участников анонимной комнаты."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            DELETE FROM anonymous_verifier_notify_reply
            WHERE anonymous_chat_id = %s AND from_telegram_user_id = %s AND dm_source_message_id = %s
            RETURNING peer_telegram_user_id, relay_message_id
            """,
            (anonymous_chat_id, from_telegram_user_id, dm_source_message_id),
        )
        return [(int(r[0]), int(r[1])) for r in cur.fetchall()]


def record_relay_delivery(
    anonymous_chat_id: int,
    from_telegram_user_id: int,
    peer_telegram_user_id: int,
    message_id: int,
    *,
    source_message_id: Optional[int] = None,
    relay_broadcast_id: Optional[str] = None,
) -> None:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO anonymous_relay_targets
            (anonymous_chat_id, from_telegram_user_id, peer_telegram_user_id, message_id, source_message_id, relay_broadcast_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                anonymous_chat_id,
                from_telegram_user_id,
                peer_telegram_user_id,
                message_id,
                source_message_id,
                relay_broadcast_id,
            ),
        )


def delete_last_relayed_for_sender(
    anonymous_chat_id: int,
    from_telegram_user_id: int,
) -> List[Tuple[int, int, Optional[int]]]:
    """Удаляет последнюю запись на каждого получателя; возвращает [(peer_id, relay_message_id, source_message_id), ...]."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            WITH ranked AS (
              SELECT id, peer_telegram_user_id, message_id, source_message_id,
                     ROW_NUMBER() OVER (
                       PARTITION BY peer_telegram_user_id ORDER BY sent_at DESC, id DESC
                     ) AS rn
              FROM anonymous_relay_targets
              WHERE anonymous_chat_id = %s AND from_telegram_user_id = %s
            )
            DELETE FROM anonymous_relay_targets
            WHERE id IN (SELECT id FROM ranked WHERE rn = 1)
            RETURNING peer_telegram_user_id, message_id, source_message_id
            """,
            (anonymous_chat_id, from_telegram_user_id),
        )
        out: List[Tuple[int, int, Optional[int]]] = []
        for row in cur.fetchall():
            a, b, c = row[0], row[1], row[2]
            out.append((int(a), int(b), int(c) if c is not None else None))
        return out


def delete_all_relayed_for_sender(
    anonymous_chat_id: int,
    from_telegram_user_id: int,
    minutes: Optional[int] = None,
) -> List[Tuple[int, int, Optional[int]]]:
    """Все сообщения отправителя; если minutes — только за последние N минут. source_message_id — исходное в ЛС отправителя."""
    with connection() as conn:
        cur = conn.cursor()
        if minutes is not None and minutes > 0:
            cur.execute(
                """
                DELETE FROM anonymous_relay_targets
                WHERE anonymous_chat_id = %s AND from_telegram_user_id = %s
                  AND sent_at >= NOW() - (%s * INTERVAL '1 minute')
                RETURNING peer_telegram_user_id, message_id, source_message_id
                """,
                (anonymous_chat_id, from_telegram_user_id, int(minutes)),
            )
        else:
            cur.execute(
                """
                DELETE FROM anonymous_relay_targets
                WHERE anonymous_chat_id = %s AND from_telegram_user_id = %s
                RETURNING peer_telegram_user_id, message_id, source_message_id
                """,
                (anonymous_chat_id, from_telegram_user_id),
            )
        out: List[Tuple[int, int, Optional[int]]] = []
        for row in cur.fetchall():
            a, b, c = row[0], row[1], row[2]
            out.append((int(a), int(b), int(c) if c is not None else None))
        return out


def complete_join_after_nickname(
    invite_id: int,
    telegram_user_id: int,
    nickname: str,
) -> Tuple[int, str]:
    """Помечает инвайт использованным, добавляет участника. Возвращает (room_id, nickname)."""
    nick = nickname.strip()
    if len(nick) < 1 or len(nick) > 32:
        raise ValueError("nickname_length")
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT i.id, i.anonymous_chat_id FROM anonymous_chat_invites i
            JOIN anonymous_chats c ON c.id = i.anonymous_chat_id
            WHERE i.id = %s AND i.used_at IS NULL AND i.expires_at > NOW() AND c.is_active = TRUE
            """,
            (invite_id,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("invite_invalid")
        room_id = int(row[1])
        cur.execute(
            """
            UPDATE anonymous_chat_invites
            SET used_at = NOW(), used_by_telegram_user_id = %s
            WHERE id = %s AND used_at IS NULL
            """,
            (telegram_user_id, invite_id),
        )
        if cur.rowcount != 1:
            raise ValueError("invite_race")
        cur.execute(
            """
            INSERT INTO anonymous_chat_members (telegram_user_id, anonymous_chat_id, nickname)
            VALUES (%s, %s, %s)
            ON CONFLICT (telegram_user_id, anonymous_chat_id) DO UPDATE SET
              nickname = EXCLUDED.nickname,
              joined_at = CURRENT_TIMESTAMP
            """,
            (telegram_user_id, room_id, nick),
        )
        set_active_dm_room(telegram_user_id, room_id)
        return room_id, nick


def set_active_dm_room(telegram_user_id: int, anonymous_chat_id: int) -> None:
    """Какую анонимную комнату считать текущей в ЛС с основным ботом (несколько комнат на пользователя)."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO anonymous_dm_active_room (telegram_user_id, anonymous_chat_id)
            VALUES (%s, %s)
            ON CONFLICT (telegram_user_id) DO UPDATE SET
              anonymous_chat_id = EXCLUDED.anonymous_chat_id,
              updated_at = CURRENT_TIMESTAMP
            """,
            (telegram_user_id, anonymous_chat_id),
        )


def get_active_dm_room_id(telegram_user_id: int) -> Optional[int]:
    """Активная комната для ЛС с основным ботом; при несогласованности — последняя по joined_at."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT a.anonymous_chat_id
            FROM anonymous_dm_active_room a
            INNER JOIN anonymous_chat_members m
              ON m.telegram_user_id = a.telegram_user_id AND m.anonymous_chat_id = a.anonymous_chat_id
            INNER JOIN anonymous_chats c ON c.id = m.anonymous_chat_id
            WHERE a.telegram_user_id = %s AND c.is_active = TRUE
            """,
            (telegram_user_id,),
        )
        row = cur.fetchone()
        if row:
            return int(row[0])
        cur.execute(
            """
            SELECT m.anonymous_chat_id FROM anonymous_chat_members m
            JOIN anonymous_chats c ON c.id = m.anonymous_chat_id
            WHERE m.telegram_user_id = %s AND c.is_active = TRUE
            ORDER BY m.joined_at DESC NULLS LAST, m.anonymous_chat_id DESC
            LIMIT 1
            """,
            (telegram_user_id,),
        )
        row2 = cur.fetchone()
        return int(row2[0]) if row2 else None


def get_room_id_for_user(telegram_user_id: int) -> Optional[int]:
    """Совместимость: активная комната в ЛС с основным ботом (как раньше одна «текущая»)."""
    return get_active_dm_room_id(telegram_user_id)


def resolve_anonymous_room_for_dm(
    telegram_user_id: int,
    fixed_child_room_id: Optional[int],
) -> Optional[int]:
    """ЛС с дочерним ботом — комната из токена; с основным — активная комната."""
    if fixed_child_room_id is not None:
        if get_nickname(telegram_user_id, fixed_child_room_id) is None:
            return None
        return fixed_child_room_id
    return get_active_dm_room_id(telegram_user_id)


def list_anonymous_room_ids_for_verifier_group(verifier_group_id: int) -> List[int]:
    """Все активные анонимные комнаты с этой группой проверяющих (их может быть несколько)."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id FROM anonymous_chats
            WHERE verifier_group_id = %s AND is_active = TRUE
            ORDER BY id
            """,
            (verifier_group_id,),
        )
        return [int(r[0]) for r in cur.fetchall()]


def room_is_registered_for_verifier_group(
    anonymous_chat_id: int, verifier_group_id: int
) -> bool:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM anonymous_chats
            WHERE id = %s AND verifier_group_id = %s AND is_active = TRUE
            """,
            (anonymous_chat_id, verifier_group_id),
        )
        return cur.fetchone() is not None


def resolve_anonymous_room_for_verifier_group(
    verifier_group_id: int,
    explicit_anonymous_chat_id: Optional[int] = None,
) -> Optional[int]:
    """
    Однозначная комната для операции с группой проверяющих:
    явный anonymous_chat_id (дочерний бот / message_links) или ровно одна комната с этим verifier_group_id.
    """
    if explicit_anonymous_chat_id is not None:
        if room_is_registered_for_verifier_group(
            explicit_anonymous_chat_id, verifier_group_id
        ):
            return explicit_anonymous_chat_id
        return None
    ids = list_anonymous_room_ids_for_verifier_group(verifier_group_id)
    if len(ids) == 1:
        return ids[0]
    return None


def get_anonymous_room_id_for_verifier_group(verifier_group_id: int) -> Optional[int]:
    """Совместимость: только если в БД ровно одна активная комната с этим verifier_group_id."""
    return resolve_anonymous_room_for_verifier_group(verifier_group_id, None)


def get_anonymous_room_id_for_dm_verifier_key(
    from_telegram_user_id: int,
    dm_source_message_id: int,
) -> Optional[int]:
    """Комната по сохранённым целям reply для /п (если у пользователя несколько комнат)."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT anonymous_chat_id FROM anonymous_verifier_notify_reply
            WHERE from_telegram_user_id = %s AND dm_source_message_id = %s
            LIMIT 1
            """,
            (from_telegram_user_id, dm_source_message_id),
        )
        row = cur.fetchone()
        return int(row[0]) if row else None


def get_verifier_group_id_for_room(anonymous_chat_id: int) -> Optional[int]:
    """ID группы проверяющих (Telegram), куда уходит /п из этой анонимной комнаты; None если не задано."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT verifier_group_id FROM anonymous_chats
            WHERE id = %s AND is_active = TRUE
            """,
            (anonymous_chat_id,),
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            return None
        try:
            return int(row[0])
        except (TypeError, ValueError):
            return None


def is_verifier_group_linked_to_anonymous_room(telegram_group_id: int) -> bool:
    """True, если этот chat_id — группа проверяющих, привязанная к активной анонимной комнате (без роли в connections)."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM anonymous_chats
            WHERE verifier_group_id = %s AND is_active = TRUE
            LIMIT 1
            """,
            (telegram_group_id,),
        )
        return cur.fetchone() is not None


def get_nickname(telegram_user_id: int, room_id: int) -> Optional[str]:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT nickname FROM anonymous_chat_members WHERE telegram_user_id = %s AND anonymous_chat_id = %s",
            (telegram_user_id, room_id),
        )
        row = cur.fetchone()
        return str(row[0]) if row else None


def format_support_relay_display(label: str) -> str:
    """Отображаемое имя назначенного саппорта в релее (латинская буква A–Z)."""
    return f"👁‍🗨 Саппорт {label}"


def get_anonymous_support_label_for_user(room_id: int, telegram_user_id: int) -> Optional[str]:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT acsa.label FROM anonymous_chat_support_admins acsa
            INNER JOIN crm_users u ON u.id = acsa.crm_user_id
            WHERE acsa.anonymous_chat_id = %s AND u.telegram_user_id = %s
            """,
            (room_id, telegram_user_id),
        )
        row = cur.fetchone()
        return str(row[0]).strip() if row and row[0] else None


def get_relay_display_name(telegram_user_id: int, room_id: int) -> Optional[str]:
    """Ник в релее: назначенный саппорт или обычный nickname участника."""
    lab = get_anonymous_support_label_for_user(room_id, telegram_user_id)
    if lab:
        return format_support_relay_display(lab)
    return get_nickname(telegram_user_id, room_id)


def is_anonymous_room_support_admin(room_id: int, telegram_user_id: int) -> bool:
    return get_anonymous_support_label_for_user(room_id, telegram_user_id) is not None


def _receipt_display_nickname_for_info(
    from_uid: int,
    anonymous_chat_id: int,
    *,
    stored_snapshot: Optional[str],
    member_nickname: Optional[str],
) -> str:
    """
    Ник в /инфо и отчётах: сначала снимок при добавлении чека, затем текущий ник в комнате,
    затем релейное имя. Telegram user id никогда не показываем.
    """
    for v in (stored_snapshot, member_nickname):
        if v is not None and str(v).strip():
            return str(v).strip()
    dn = get_relay_display_name(from_uid, anonymous_chat_id)
    if dn:
        return dn
    return "ник не сохранён"


def is_anonymous_room_crm_owner(anonymous_chat_id: int, telegram_user_id: int) -> bool:
    """Создатель комнаты в CRM (created_by_crm_user_id) с тем же telegram_user_id в профиле."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM anonymous_chats ac
            INNER JOIN crm_users u ON u.id = ac.created_by_crm_user_id
            WHERE ac.id = %s AND ac.is_active = TRUE
              AND u.telegram_user_id = %s
            """,
            (anonymous_chat_id, telegram_user_id),
        )
        return cur.fetchone() is not None


def lookup_relay_dm_reply_context(
    anonymous_chat_id: int,
    peer_telegram_user_id: int,
    relay_message_id_at_peer: int,
) -> Optional[Tuple[int, Optional[int], Optional[str]]]:
    """
    Релей, на который участник нажал «ответить» в ЛС с ботом:
    автор исходного текста, source_message_id его сообщения в ЛС и relay_broadcast_id одной рассылки.
    """
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT from_telegram_user_id, source_message_id, relay_broadcast_id
            FROM anonymous_relay_targets
            WHERE anonymous_chat_id = %s AND peer_telegram_user_id = %s AND message_id = %s
            LIMIT 1
            """,
            (anonymous_chat_id, peer_telegram_user_id, relay_message_id_at_peer),
        )
        row = cur.fetchone()
        if not row:
            return None
        src = row[1]
        src_i: Optional[int] = int(src) if src is not None else None
        bid = row[2]
        bid_s: Optional[str] = str(bid) if bid is not None else None
        return int(row[0]), src_i, bid_s


def lookup_relay_peer_message_by_broadcast(
    anonymous_chat_id: int,
    peer_telegram_user_id: int,
    relay_broadcast_id: str,
) -> Optional[int]:
    """message_id в ЛС peer для той же рассылки, что и у других получателей (reply между пирами)."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT message_id FROM anonymous_relay_targets
            WHERE anonymous_chat_id = %s AND peer_telegram_user_id = %s
              AND relay_broadcast_id = %s::uuid
            LIMIT 1
            """,
            (anonymous_chat_id, peer_telegram_user_id, relay_broadcast_id),
        )
        row = cur.fetchone()
        return int(row[0]) if row else None


def find_relay_message_at_peer_for_source(
    anonymous_chat_id: int,
    from_author_uid: int,
    target_peer_uid: int,
    source_message_id: Optional[int],
) -> Optional[int]:
    """message_id в чате target_peer для копии релея автора с данным source_message_id."""
    with connection() as conn:
        cur = conn.cursor()
        if source_message_id is None:
            cur.execute(
                """
                SELECT message_id FROM anonymous_relay_targets
                WHERE anonymous_chat_id = %s AND from_telegram_user_id = %s
                  AND peer_telegram_user_id = %s AND source_message_id IS NULL
                ORDER BY id DESC LIMIT 1
                """,
                (anonymous_chat_id, from_author_uid, target_peer_uid),
            )
        else:
            cur.execute(
                """
                SELECT message_id FROM anonymous_relay_targets
                WHERE anonymous_chat_id = %s AND from_telegram_user_id = %s
                  AND peer_telegram_user_id = %s AND source_message_id = %s
                ORDER BY id ASC LIMIT 1
                """,
                (anonymous_chat_id, from_author_uid, target_peer_uid, source_message_id),
            )
        row = cur.fetchone()
        return int(row[0]) if row else None


def relay_reply_target_message_id_for_peer(
    anonymous_chat_id: int,
    peer_id: int,
    ctx: Optional[Tuple[int, Optional[int], Optional[str]]],
) -> Optional[int]:
    """ID сообщения в чате peer_id для цитаты (reply) в Telegram."""
    if not ctx:
        return None
    author_uid, src_mid, broadcast_id = ctx
    if peer_id == author_uid:
        return src_mid
    if broadcast_id:
        mid = lookup_relay_peer_message_by_broadcast(
            anonymous_chat_id, peer_id, broadcast_id
        )
        if mid is not None:
            return mid
    return find_relay_message_at_peer_for_source(
        anonymous_chat_id, author_uid, peer_id, src_mid
    )


def get_peer_telegram_ids(room_id: int, exclude_telegram_user_id: int) -> List[int]:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT telegram_user_id FROM anonymous_chat_members
            WHERE anonymous_chat_id = %s AND telegram_user_id <> %s
            """,
            (room_id, exclude_telegram_user_id),
        )
        return [int(r[0]) for r in cur.fetchall()]


def list_active_anonymous_room_ids() -> List[int]:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM anonymous_chats WHERE is_active = TRUE ORDER BY id")
        return [int(r[0]) for r in cur.fetchall()]


def list_member_telegram_ids_for_room(room_id: int) -> List[int]:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT telegram_user_id FROM anonymous_chat_members WHERE anonymous_chat_id = %s",
            (room_id,),
        )
        return [int(r[0]) for r in cur.fetchall()]


def count_anonymous_room_members(anonymous_chat_id: int) -> int:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM anonymous_chat_members WHERE anonymous_chat_id = %s",
            (anonymous_chat_id,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0


def reset_anonymous_receipts_for_room(anonymous_chat_id: int) -> int:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM anonymous_receipts WHERE anonymous_chat_id = %s",
            (anonymous_chat_id,),
        )
        return cur.rowcount


def reset_anonymous_room_by_staff(anonymous_chat_id: int) -> Optional[Dict[str, int]]:
    """Сброс чеков в комнате (как reset_anonymous_receipts_for_room), только если комната существует."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM anonymous_chats WHERE id = %s", (anonymous_chat_id,))
        if not cur.fetchone():
            return None
    n = reset_anonymous_receipts_for_room(anonymous_chat_id)
    return {"receipts_removed": n}


def _fetch_verifier_notify_for_telegram_purge(
    retention_hours: int,
) -> List[Tuple[int, int, int]]:
    """Старые цели уведомлений: room_id, peer_id, relay_message_id."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT anonymous_chat_id, peer_telegram_user_id, relay_message_id
            FROM anonymous_verifier_notify_reply
            WHERE created_at < NOW() - (%s * INTERVAL '1 hour')
            ORDER BY anonymous_chat_id
            """,
            (retention_hours,),
        )
        return [(int(a), int(b), int(c)) for a, b, c in cur.fetchall()]


_PURGE_DELETE_EXPECTED_SUBSTRINGS = (
    "can't be deleted",
    "can not be deleted",
    "message to delete not found",
    "message can't be found",
    "message_id_invalid",
    "message identifier is not valid",
    "message is not modified",
)


async def _purge_try_delete_message(
    bot: AiogramBot, chat_id: int, message_id: int, log_what: str
) -> None:
    """Удаление при очистке релея: ожидаемые отказы Telegram — только warning, без traceback."""
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest as e:
        desc = ((getattr(e, "message", None) or str(e)) or "").lower()
        if any(s in desc for s in _PURGE_DELETE_EXPECTED_SUBSTRINGS):
            logger.warning(
                "purge: пропуск удаления %s chat=%s mid=%s — %s",
                log_what,
                chat_id,
                message_id,
                e,
            )
            return
        logger.exception(
            "purge: TelegramBadRequest при удалении %s chat=%s mid=%s",
            log_what,
            chat_id,
            message_id,
        )
    except Exception:
        logger.exception(
            "purge: не удалось удалить %s chat=%s mid=%s",
            log_what,
            chat_id,
            message_id,
        )


async def _delete_verifier_rows_in_telegram(
    bot: AiogramBot,
    rows: List[Tuple[int, int, int]],
) -> None:
    for _room, peer_id, relay_mid in rows:
        await _purge_try_delete_message(
            bot, peer_id, relay_mid, f"verifier relay peer={peer_id}"
        )


async def _purge_telegram_for_stale_anonymous_data(
    main_bot: AiogramBot,
    retention_hours: int,
) -> None:
    """Только anonymous_verifier_notify_reply: релей anonymous_relay_targets по TTL не трогаем."""
    ver_rows = _fetch_verifier_notify_for_telegram_purge(retention_hours)
    ver_by_room: Dict[int, List[Tuple[int, int, int]]] = defaultdict(list)
    for row in ver_rows:
        ver_by_room[row[0]].append(row)

    for room_id in sorted(ver_by_room.keys()):
        token = get_child_bot_token(room_id)
        room_list = ver_by_room[room_id]
        if token:
            child = AiogramBot(token=token)
            try:
                await _delete_verifier_rows_in_telegram(child, room_list)
            finally:
                await child.session.close()
        else:
            await _delete_verifier_rows_in_telegram(main_bot, room_list)


def purge_stale_anonymous_chat_data(retention_hours: int = 48) -> Dict[str, int]:
    """
    Удаляет данные старше retention_hours: историю CRM (anonymous_chat_messages),
    цели reply для уведомлений по /п (anonymous_verifier_notify_reply).

    anonymous_relay_targets по расписанию не удаляются (нужны для reply и /delete).

    Сообщения в Telegram — см. purge_stale_anonymous_chat_data_with_telegram.
    """
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            DELETE FROM anonymous_chat_messages
            WHERE created_at < NOW() - (%s * INTERVAL '1 hour')
            """,
            (retention_hours,),
        )
        n_msg = cur.rowcount
        n_rel = 0
        cur.execute(
            """
            DELETE FROM anonymous_verifier_notify_reply
            WHERE created_at < NOW() - (%s * INTERVAL '1 hour')
            """,
            (retention_hours,),
        )
        n_ver = cur.rowcount
    out = {
        "anonymous_chat_messages": n_msg,
        "anonymous_relay_targets": n_rel,
        "anonymous_verifier_notify_reply": n_ver,
    }
    if n_msg or n_rel or n_ver:
        logger.info(
            "Очистка анонимных данных старше %s ч: %s",
            retention_hours,
            out,
        )
    return out


async def purge_stale_anonymous_chat_data_with_telegram(
    main_bot: AiogramBot,
    retention_hours: int = 48,
) -> Dict[str, int]:
    """Сначала удаляет в Telegram устаревшие сообщения по verifier_notify, затем строки в БД (без anonymous_relay_targets)."""
    await _purge_telegram_for_stale_anonymous_data(main_bot, retention_hours)
    return purge_stale_anonymous_chat_data(retention_hours)


def leave_room(telegram_user_id: int, room_id: Optional[int] = None) -> bool:
    """Выход из комнаты room_id или из активной комнаты; активная ЛС переключается на другую при необходимости."""
    with connection() as conn:
        cur = conn.cursor()
        if room_id is None:
            room_id = get_active_dm_room_id(telegram_user_id)
        if room_id is None:
            return False
        cur.execute(
            """
            DELETE FROM anonymous_chat_members
            WHERE telegram_user_id = %s AND anonymous_chat_id = %s
            """,
            (telegram_user_id, room_id),
        )
        if cur.rowcount == 0:
            return False
        cur.execute(
            "SELECT anonymous_chat_id FROM anonymous_dm_active_room WHERE telegram_user_id = %s",
            (telegram_user_id,),
        )
        active_row = cur.fetchone()
        if active_row and int(active_row[0]) == room_id:
            cur.execute(
                """
                SELECT anonymous_chat_id FROM anonymous_chat_members
                WHERE telegram_user_id = %s
                ORDER BY joined_at DESC NULLS LAST, anonymous_chat_id DESC
                LIMIT 1
                """,
                (telegram_user_id,),
            )
            nxt = cur.fetchone()
            if nxt:
                cur.execute(
                    """
                    UPDATE anonymous_dm_active_room
                    SET anonymous_chat_id = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE telegram_user_id = %s
                    """,
                    (int(nxt[0]), telegram_user_id),
                )
            else:
                cur.execute(
                    "DELETE FROM anonymous_dm_active_room WHERE telegram_user_id = %s",
                    (telegram_user_id,),
                )
        return True


def record_anonymous_message(
    anonymous_chat_id: int,
    from_telegram_user_id: int,
    nickname: str,
    body: str,
) -> None:
    """Сохраняет строку в историю для CRM (после успешного релея)."""
    b = (body or "").strip()
    if len(b) > 10000:
        b = b[:10000] + "…"
    nick = (nickname or "").strip()[:200] or "?"
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO anonymous_chat_messages (anonymous_chat_id, from_telegram_user_id, nickname, body)
            VALUES (%s, %s, %s, %s)
            """,
            (anonymous_chat_id, from_telegram_user_id, nick, b),
        )


def format_relay_line(nickname: str, text: str) -> str:
    return f"<b>{_escape_html(nickname)}</b>: {_escape_html(text)}"


def format_relay_media_caption(nickname: str, user_caption: Optional[str]) -> str:
    """Подпись к пересылаемому медиа (HTML). Без отдельного текста — только ник."""
    nick = _escape_html(nickname)
    if user_caption and user_caption.strip():
        return f"<b>{nick}</b>: {_escape_html(user_caption.strip())}"
    return f"<b>{nick}</b>"


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _snapshot_nickname_for_receipt(
    anonymous_chat_id: int, from_telegram_user_id: int
) -> str:
    """Текущий отображаемый ник в комнате на момент чека (сохраняется в строке чека)."""
    dn = get_relay_display_name(from_telegram_user_id, anonymous_chat_id)
    if dn:
        return dn
    return "участник"


def insert_anonymous_receipt(
    anonymous_chat_id: int,
    from_telegram_user_id: int,
    amount: float,
    *,
    author_nickname: Optional[str] = None,
) -> Optional[int]:
    """Добавляет чек в комнату. Возвращает receipt_no или None, если комната неактивна."""
    snap = (author_nickname or "").strip() if author_nickname is not None else ""
    if not snap:
        snap = _snapshot_nickname_for_receipt(anonymous_chat_id, from_telegram_user_id)
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT is_active FROM anonymous_chats WHERE id = %s",
            (anonymous_chat_id,),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return None
        cur.execute(
            """
            SELECT COALESCE(MAX(receipt_no), 0) + 1 FROM anonymous_receipts
            WHERE anonymous_chat_id = %s
            """,
            (anonymous_chat_id,),
        )
        next_no = int(cur.fetchone()[0])
        cur.execute(
            """
            INSERT INTO anonymous_receipts (
                anonymous_chat_id, receipt_no, amount, from_telegram_user_id, receipt_author_nickname
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (anonymous_chat_id, next_no, amount, from_telegram_user_id, snap),
        )
        return next_no


def delete_anonymous_receipt(
    anonymous_chat_id: int,
    receipt_no: int,
    _requester_telegram_user_id: int,
    *,
    force: bool = False,
) -> str:
    """
    Удаляет чек в комнате только при force=True (TELEGRAM_ADMIN_IDS, саппорты комнаты, создатель комнаты в CRM).
    Автор чека сам удалить не может.
    Возвращает: 'ok' | 'not_found' | 'forbidden' | 'inactive'.
    """
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT is_active FROM anonymous_chats WHERE id = %s",
            (anonymous_chat_id,),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return "inactive"
        cur.execute(
            """
            SELECT 1 FROM anonymous_receipts
            WHERE anonymous_chat_id = %s AND receipt_no = %s
            """,
            (anonymous_chat_id, receipt_no),
        )
        if not cur.fetchone():
            return "not_found"
        if not force:
            return "forbidden"
        cur.execute(
            """
            DELETE FROM anonymous_receipts
            WHERE anonymous_chat_id = %s AND receipt_no = %s
            """,
            (anonymous_chat_id, receipt_no),
        )
        return "ok"


def build_anonymous_info_snapshot(
    anonymous_chat_id: int, today: str
) -> Optional[Dict[str, Any]]:
    """Последние 15 чеков за сегодня, суммы по комнате."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
              is_active,
              (child_bot_token IS NOT NULL AND TRIM(child_bot_token) <> '') AS has_child,
              COALESCE(NULLIF(TRIM(child_bot_first_name), ''), '')
            FROM anonymous_chats
            WHERE id = %s
            """,
            (anonymous_chat_id,),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return None
        has_child = bool(row[1])
        child_fn = str(row[2] or "").strip() if len(row) > 2 else ""
        bot_label = _resolve_anon_bot_title_label(has_child, child_fn)
        cur.execute(
            f"""
            SELECT r.receipt_no, r.amount, r.ts,
                   NULLIF(TRIM(r.receipt_author_nickname), ''),
                   NULLIF(TRIM(m.nickname), ''),
                   r.from_telegram_user_id
            FROM anonymous_receipts r
            LEFT JOIN anonymous_chat_members m
              ON m.telegram_user_id = r.from_telegram_user_id
             AND m.anonymous_chat_id = r.anonymous_chat_id
            WHERE r.anonymous_chat_id = %s AND {_SQL_RECEIPT_DATE_MSK} = %s::date
            ORDER BY r.id DESC
            LIMIT 15
            """,
            (anonymous_chat_id, today),
        )
        raw_rows = cur.fetchall()
        rows = []
        for receipt_no, amount, ts, snap, mem_nick, from_uid in raw_rows:
            dn = _receipt_display_nickname_for_info(
                int(from_uid),
                anonymous_chat_id,
                stored_snapshot=snap,
                member_nickname=mem_nick,
            )
            rows.append((receipt_no, amount, ts, dn))
        cur.execute(
            f"""
            SELECT COALESCE(SUM(amount), 0) FROM anonymous_receipts
            WHERE anonymous_chat_id = %s AND {_SQL_RECEIPT_DATE_MSK_NO_ALIAS} = %s::date
            """,
            (anonymous_chat_id, today),
        )
        sum_today = float(cur.fetchone()[0] or 0)
        cur.execute(
            """
            SELECT COALESCE(SUM(amount), 0) FROM anonymous_receipts
            WHERE anonymous_chat_id = %s
            """,
            (anonymous_chat_id,),
        )
        sum_all = float(cur.fetchone()[0] or 0)
        return {
            "rows": rows,
            "sum_today": sum_today,
            "sum_all": sum_all,
            "bot_label": bot_label,
        }


def get_bot_display_label_for_anonymous_room(anonymous_chat_id: int) -> str:
    """Отображаемое имя бота (first_name из Telegram) или «Анонимный чат» / BOT_DISPLAY_NAME."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
              (child_bot_token IS NOT NULL AND TRIM(child_bot_token) <> '') AS has_child,
              COALESCE(NULLIF(TRIM(child_bot_first_name), ''), '')
            FROM anonymous_chats
            WHERE id = %s AND is_active = TRUE
            """,
            (anonymous_chat_id,),
        )
        row = cur.fetchone()
        if not row:
            return ANONYMOUS_CHAT_TITLE_FALLBACK
        has_child = bool(row[0])
        child_fn = str(row[1] or "").strip() if len(row) > 1 else ""
    return _resolve_anon_bot_title_label(has_child, child_fn)


def format_anonymous_info_html(snapshot: Dict[str, Any], daily_report: bool = False) -> str:
    """Текст /инфо для анонимной комнаты или ежедневной рассылки."""
    rows = snapshot["rows"]
    sum_today = snapshot["sum_today"]
    sum_all = snapshot["sum_all"]
    bot_title = _escape_html(str(snapshot.get("bot_label") or ANONYMOUS_CHAT_TITLE_FALLBACK))
    header = ""
    if daily_report:
        header = (
            f"📅 <b>Ежедневный отчёт за {datetime.now(_MSK_ANON).strftime('%d.%m.%Y')}</b>\n\n"
        )
    if not rows:
        return (
            f"{header}"
            f"📅 <b>{bot_title}</b>\n\n"
            f"За сегодня чеков нет.\n\n"
        )
    lines: List[str] = []
    for receipt_no, amount, ts, who in rows:
        ts_fmt = format_ts_ru_msk(ts)
        nick = _escape_html(str(who))
        lines.append(
            f"<b>🧾 Чек №{receipt_no} | {ts_fmt}</b>\n"
            f"👤 Ник: <b>{nick}</b>\n"
            f"🤑 Сумма: <b>{float(amount):.2f}</b>\n"
            f"<b>_____</b>"
        )
    text = "\n".join(lines)
    return (
        f"{header}"
        f"📅 <b>{bot_title}</b>\n\n"
        f"Последние 15 чеков:\n{text}\n\n"
        f"📦 <b>Сумма всех чеков за сегодня:</b> {sum_today:.2f}\n"
    )


def count_anonymous_receipts_today(anonymous_chat_id: int, today: str) -> int:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT COUNT(*) FROM anonymous_receipts
            WHERE anonymous_chat_id = %s AND {_SQL_RECEIPT_DATE_MSK_NO_ALIAS} = %s::date
            """,
            (anonymous_chat_id, today),
        )
        return int(cur.fetchone()[0])


def build_anonymous_cheki_today_html(anonymous_chat_id: int, today: str) -> Optional[str]:
    """HTML-файл «чеки за сегодня» для анонимной комнаты."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT title FROM anonymous_chats WHERE id = %s AND is_active = TRUE",
            (anonymous_chat_id,),
        )
        trow = cur.fetchone()
        if not trow:
            return None
        title = (trow[0] or "").strip() or "Без названия"
        cur.execute(
            f"""
            SELECT r.receipt_no, r.amount, r.ts,
                   NULLIF(TRIM(r.receipt_author_nickname), ''),
                   NULLIF(TRIM(m.nickname), ''),
                   r.from_telegram_user_id
            FROM anonymous_receipts r
            LEFT JOIN anonymous_chat_members m
              ON m.telegram_user_id = r.from_telegram_user_id
             AND m.anonymous_chat_id = r.anonymous_chat_id
            WHERE r.anonymous_chat_id = %s AND {_SQL_RECEIPT_DATE_MSK} = %s::date
            ORDER BY r.receipt_no ASC
            """,
            (anonymous_chat_id, today),
        )
        raw_data = cur.fetchall()
        data = []
        for receipt_no, amount, ts, snap, mem_nick, from_uid in raw_data:
            dn = _receipt_display_nickname_for_info(
                int(from_uid),
                anonymous_chat_id,
                stored_snapshot=snap,
                member_nickname=mem_nick,
            )
            data.append((receipt_no, amount, ts, dn))
        cur.execute(
            f"""
            SELECT COALESCE(SUM(amount), 0) FROM anonymous_receipts
            WHERE anonymous_chat_id = %s AND {_SQL_RECEIPT_DATE_MSK_NO_ALIAS} = %s::date
            """,
            (anonymous_chat_id, today),
        )
        total = float(cur.fetchone()[0] or 0)

    bot_label = get_bot_display_label_for_anonymous_room(anonymous_chat_id)

    rows_html: List[str] = []
    for receipt_no, amount, ts, who in data:
        ts_fmt = format_ts_ru_msk(ts)
        rows_html.append(
            "<tr>"
            f"<td>{int(receipt_no)}</td>"
            f"<td>{html_lib.escape(ts_fmt)}</td>"
            f"<td>{float(amount):.2f}</td>"
            f"<td>{html_lib.escape(str(who))}</td>"
            "</tr>"
        )
    table_body = "\n".join(rows_html) if rows_html else "<tr><td colspan='4'>Нет чеков</td></tr>"
    day_fmt = datetime.strptime(today, "%Y-%m-%d").strftime("%d.%m.%Y")
    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Чеки за {day_fmt}</title>
<style>
body {{ font-family: system-ui, sans-serif; background: #0f1115; color: #eef2ff; margin: 0; padding: 16px; }}
h1 {{ font-size: 1.1rem; margin: 0 0 12px; }}
.summary {{ margin-bottom: 16px; color: #a7b0c0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ border: 1px solid #222733; padding: 8px; text-align: left; }}
th {{ background: #171a21; }}
</style></head>
<body>
<h1>🧾 Чеки за {html_lib.escape(day_fmt)} — {html_lib.escape(title)}</h1>
<p class="summary">{html_lib.escape(bot_label)} · <b>Сумма за день: {total:.2f}</b></p>
<table>
<thead><tr><th>№</th><th>Время</th><th>Сумма</th><th>Никнейм</th></tr></thead>
<tbody>{table_body}</tbody>
</table>
</body></html>"""

