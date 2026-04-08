"""CRM: тикеты поддержки (PostgreSQL)."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

from .pg import connection

# Антиспам (переменные окружения, сек. / сообщений в минуту на пользователя)
_MIN_INTERVAL_SEC = float(os.environ.get("SUPPORT_MIN_INTERVAL_SEC", "4"))
_MAX_IN_PER_MINUTE = int(os.environ.get("SUPPORT_MAX_MSG_PER_MINUTE", "18"))


class SupportSpamError(Exception):
    """Слишком частые сообщения в поддержку."""

    def __init__(self, reason: str = "rate_limited") -> None:
        self.reason = reason
        super().__init__(reason)


def ensure_default_bot_instance(token: str) -> None:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM bot_instances WHERE id = 1")
        if cur.fetchone():
            return
        cur.execute(
            """
            INSERT INTO bot_instances (id, label, telegram_bot_token, is_active)
            VALUES (1, 'primary', %s, 1)
            """,
            (token,),
        )


def init_crm_schema(bot_token: str) -> None:
    """Таблицы CRM создаются в bot.pg.init_schema; здесь — только первичный bot_instance."""
    ensure_default_bot_instance(bot_token)


def _check_incoming_rate_limits(cur, ticket_id: int) -> None:
    cur.execute(
        """
        SELECT COUNT(*) FROM support_messages
        WHERE ticket_id = %s AND direction = 'in'
          AND created_at > NOW() - INTERVAL '1 minute'
        """,
        (ticket_id,),
    )
    n = int(cur.fetchone()[0])
    if n >= _MAX_IN_PER_MINUTE:
        raise SupportSpamError("too_many_per_minute")

    cur.execute(
        """
        SELECT EXTRACT(EPOCH FROM (NOW() - created_at))::double precision
        FROM support_messages
        WHERE ticket_id = %s AND direction = 'in'
        ORDER BY id DESC LIMIT 1
        """,
        (ticket_id,),
    )
    row = cur.fetchone()
    if row and row[0] is not None and float(row[0]) < _MIN_INTERVAL_SEC:
        raise SupportSpamError("too_fast")


def record_support_message_from_user(
    telegram_user_id: int,
    telegram_username: Optional[str],
    text: Optional[str],
    bot_instance_id: int = 1,
    extra: Optional[str] = None,
) -> Tuple[int, bool]:
    """Сохраняет входящее сообщение пользователя в ЛС.

    Возвращает (ticket_id, reopened): reopened=True, если тикет был closed и снова открыт.
    """
    with connection() as conn:
        cur = conn.cursor()
        now = datetime.utcnow()
        prev_status: Optional[str] = None
        cur.execute(
            """
            SELECT id, status FROM support_tickets
            WHERE bot_instance_id = %s AND telegram_user_id = %s
            """,
            (bot_instance_id, telegram_user_id),
        )
        row = cur.fetchone()
        if row:
            ticket_id = int(row[0])
            prev_status = str(row[1]) if row[1] is not None else "open"
            _check_incoming_rate_limits(cur, ticket_id)
            cur.execute(
                """
                UPDATE support_tickets
                SET last_message_at = %s, status = 'open',
                    telegram_username = COALESCE(%s, telegram_username)
                WHERE id = %s
                """,
                (now, telegram_username, ticket_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO support_tickets
                (bot_instance_id, telegram_user_id, telegram_username, status, last_message_at)
                VALUES (%s, %s, %s, 'open', %s)
                RETURNING id
                """,
                (bot_instance_id, telegram_user_id, telegram_username, now),
            )
            ticket_id = int(cur.fetchone()[0])
        body = (text or "").strip() or "[медиа или вложение]"
        cur.execute(
            """
            INSERT INTO support_messages (ticket_id, direction, body, extra)
            VALUES (%s, 'in', %s, %s)
            """,
            (ticket_id, body[:10000], extra),
        )
    reopened = prev_status == "closed"
    return ticket_id, reopened


def notify_support_staff_new_ticket_message(ticket_id: int, body_preview: str) -> None:
    """Шлёт в Telegram всем support с заполненным crm_users.telegram_user_id."""
    import json
    import urllib.error
    import urllib.request

    try:
        from bot.bot_token import resolve_bot_token

        token = resolve_bot_token()
    except Exception as e:
        logger.debug("notify_support_staff: no token: %s", e)
        return

    try:
        with connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT telegram_user_id FROM crm_users
                WHERE role = 'support' AND telegram_user_id IS NOT NULL
                """
            )
            targets = [int(r[0]) for r in cur.fetchall() if r[0] is not None]
    except Exception as e:
        logger.warning("notify_support_staff: list users: %s", e)
        return

    if not targets:
        return

    preview = (body_preview or "")[:400]
    text = f"💬 Новое сообщение в тикете #{ticket_id}\n\n{preview or '—'}"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chat_id in set(targets):
        try:
            payload = json.dumps(
                {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
            ).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=15)
        except (urllib.error.URLError, OSError, ValueError) as e:
            logger.warning("notify_support_staff: chat %s: %s", chat_id, e)
