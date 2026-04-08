"""PostgreSQL: подключение и создание схемы (единая БД вместо SQLite)."""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, List

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    _env = Path(__file__).resolve().parent.parent / ".env"
    if _env.is_file():
        try:
            for line in _env.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, _, v = s.partition("=")
                k, v = k.strip(), v.strip()
                if k and k not in os.environ:
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                        v = v[1:-1]
                    os.environ.setdefault(k, v)
        except OSError:
            pass

logger = logging.getLogger(__name__)

try:
    import psycopg2
    from psycopg2.extensions import connection as PgConnection
except ImportError as e:  # pragma: no cover
    raise RuntimeError("Install psycopg2-binary: pip install psycopg2-binary") from e


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is required (PostgreSQL connection string)")
    return url


@contextmanager
def connection() -> Generator[PgConnection, None, None]:
    conn = psycopg2.connect(get_database_url())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _exec_many(conn, statements: List[str]) -> None:
    cur = conn.cursor()
    for stmt in statements:
        s = stmt.strip()
        if s:
            cur.execute(s)


def _migrate_anonymous_chat_members_composite_pk(conn) -> None:
    """Старые БД: PK только по telegram_user_id → составной ключ; backfill активной комнаты для ЛС."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(array_length(c.conkey, 1), 0)
        FROM pg_constraint c
        JOIN pg_class t ON c.conrelid = t.oid
        WHERE t.relname = 'anonymous_chat_members' AND c.contype = 'p'
        """
    )
    row = cur.fetchone()
    nkeys = int(row[0]) if row and row[0] is not None else 0
    if nkeys != 1:
        return
    cur.execute(
        """
        INSERT INTO anonymous_dm_active_room (telegram_user_id, anonymous_chat_id)
        SELECT telegram_user_id, anonymous_chat_id FROM anonymous_chat_members
        ON CONFLICT (telegram_user_id) DO NOTHING
        """
    )
    cur.execute("ALTER TABLE anonymous_chat_members DROP CONSTRAINT anonymous_chat_members_pkey")
    cur.execute(
        """
        ALTER TABLE anonymous_chat_members
        ADD PRIMARY KEY (telegram_user_id, anonymous_chat_id)
        """
    )
    logger.info(
        "PostgreSQL: anonymous_chat_members → составной PK, anonymous_dm_active_room заполнена"
    )


def _migrate_anonymous_receipts_author_nickname(conn) -> None:
    """Старые строки: подставить ник из anonymous_chat_members, если участник ещё в комнате."""
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE anonymous_receipts r
        SET receipt_author_nickname = NULLIF(TRIM(m.nickname), '')
        FROM anonymous_chat_members m
        WHERE r.from_telegram_user_id = m.telegram_user_id
          AND r.anonymous_chat_id = m.anonymous_chat_id
          AND (r.receipt_author_nickname IS NULL OR TRIM(r.receipt_author_nickname) = '')
        """
    )
    n = cur.rowcount
    if n:
        logger.info("PostgreSQL: receipt_author_nickname backfill для %s строк anonymous_receipts", n)


def init_schema() -> None:
    """Создаёт все таблицы при старте (идемпотентно)."""
    statements: List[str] = [
        """
        CREATE TABLE IF NOT EXISTS connections (
            id SERIAL PRIMARY KEY,
            client_group_id BIGINT NOT NULL,
            verifier_group_id BIGINT NOT NULL,
            client_group_name TEXT,
            verifier_group_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            UNIQUE(client_group_id, verifier_group_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS global_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            wallet_address TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            welcome_message TEXT,
            welcome_links TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS processed_transactions (
            hash TEXT PRIMARY KEY,
            amount DOUBLE PRECISION NOT NULL,
            chat_id BIGINT NOT NULL,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS broadcast_chats (
            chat_id BIGINT PRIMARY KEY,
            name TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS broadcast_inaccessible (
            chat_id BIGINT PRIMARY KEY
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS broadcast_always_exclude (
            chat_id BIGINT PRIMARY KEY
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS admin_chat_invite_links (
            chat_id BIGINT PRIMARY KEY,
            invite_link TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bot_instances (
            id SERIAL PRIMARY KEY,
            label TEXT NOT NULL DEFAULT 'primary',
            telegram_bot_token TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS crm_users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'support')),
            totp_secret TEXT,
            totp_enabled INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "ALTER TABLE crm_users ADD COLUMN IF NOT EXISTS telegram_user_id BIGINT",
        "ALTER TABLE crm_users ADD COLUMN IF NOT EXISTS support_permissions JSONB DEFAULT NULL",
        """
        CREATE TABLE IF NOT EXISTS crm_sessions (
            id SERIAL PRIMARY KEY,
            token_hash TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL REFERENCES crm_users(id) ON DELETE CASCADE,
            created_at BIGINT NOT NULL,
            expires_at BIGINT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS support_tickets (
            id SERIAL PRIMARY KEY,
            bot_instance_id INTEGER NOT NULL DEFAULT 1 REFERENCES bot_instances(id),
            telegram_user_id BIGINT NOT NULL,
            telegram_username TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            last_message_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(bot_instance_id, telegram_user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS support_messages (
            id SERIAL PRIMARY KEY,
            ticket_id INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
            direction TEXT NOT NULL CHECK (direction IN ('in', 'out')),
            body TEXT,
            extra TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            action TEXT NOT NULL,
            detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_support_tickets_user ON support_tickets(telegram_user_id)",
        "CREATE INDEX IF NOT EXISTS idx_support_messages_ticket_created ON support_messages(ticket_id, created_at DESC)",
        """
        CREATE TABLE IF NOT EXISTS support_ticket_reads (
            crm_user_id INTEGER NOT NULL REFERENCES crm_users(id) ON DELETE CASCADE,
            ticket_id INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
            last_read_message_id INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (crm_user_id, ticket_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_support_ticket_reads_user ON support_ticket_reads(crm_user_id)",
        "CREATE INDEX IF NOT EXISTS idx_crm_sessions_expires ON crm_sessions(expires_at)",
        """
        CREATE TABLE IF NOT EXISTS anonymous_chats (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by_crm_user_id INTEGER REFERENCES crm_users(id) ON DELETE SET NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE
        )
        """,
        "ALTER TABLE anonymous_chats ADD COLUMN IF NOT EXISTS child_bot_token TEXT",
        "ALTER TABLE anonymous_chats ADD COLUMN IF NOT EXISTS child_bot_username TEXT",
        "ALTER TABLE anonymous_chats ADD COLUMN IF NOT EXISTS child_bot_id BIGINT",
        "ALTER TABLE anonymous_chats ADD COLUMN IF NOT EXISTS child_bot_first_name TEXT",
        "ALTER TABLE anonymous_chats ADD COLUMN IF NOT EXISTS verifier_group_id BIGINT",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_anonymous_chats_child_token
        ON anonymous_chats (child_bot_token) WHERE child_bot_token IS NOT NULL
        """,
        """
        CREATE TABLE IF NOT EXISTS anonymous_chat_invites (
            id SERIAL PRIMARY KEY,
            anonymous_chat_id INTEGER NOT NULL REFERENCES anonymous_chats(id) ON DELETE CASCADE,
            token TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP,
            used_by_telegram_user_id BIGINT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_anonymous_chat_invites_token ON anonymous_chat_invites(token)",
        """
        CREATE TABLE IF NOT EXISTS anonymous_chat_members (
            telegram_user_id BIGINT NOT NULL,
            anonymous_chat_id INTEGER NOT NULL REFERENCES anonymous_chats(id) ON DELETE CASCADE,
            nickname TEXT NOT NULL,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (telegram_user_id, anonymous_chat_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_anonymous_chat_members_room ON anonymous_chat_members(anonymous_chat_id)",
        """
        CREATE TABLE IF NOT EXISTS anonymous_dm_active_room (
            telegram_user_id BIGINT PRIMARY KEY,
            anonymous_chat_id INTEGER NOT NULL REFERENCES anonymous_chats(id) ON DELETE CASCADE,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_anon_dm_active_room_chat ON anonymous_dm_active_room(anonymous_chat_id)",
        """
        CREATE TABLE IF NOT EXISTS anonymous_chat_support_admins (
            anonymous_chat_id INTEGER NOT NULL REFERENCES anonymous_chats(id) ON DELETE CASCADE,
            crm_user_id INTEGER NOT NULL REFERENCES crm_users(id) ON DELETE CASCADE,
            label TEXT NOT NULL CHECK (char_length(label) = 1 AND label >= 'A' AND label <= 'Z'),
            PRIMARY KEY (anonymous_chat_id, crm_user_id)
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_anon_support_room_label ON anonymous_chat_support_admins(anonymous_chat_id, label)",
        """
        CREATE TABLE IF NOT EXISTS anonymous_chat_messages (
            id SERIAL PRIMARY KEY,
            anonymous_chat_id INTEGER NOT NULL REFERENCES anonymous_chats(id) ON DELETE CASCADE,
            from_telegram_user_id BIGINT NOT NULL,
            nickname TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_anon_msg_room_created ON anonymous_chat_messages(anonymous_chat_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_anon_msg_created_at ON anonymous_chat_messages(created_at)",
        """
        CREATE TABLE IF NOT EXISTS anonymous_receipts (
            id SERIAL PRIMARY KEY,
            anonymous_chat_id INTEGER NOT NULL REFERENCES anonymous_chats(id) ON DELETE CASCADE,
            receipt_no INTEGER NOT NULL,
            amount DOUBLE PRECISION NOT NULL,
            from_telegram_user_id BIGINT NOT NULL,
            receipt_author_nickname TEXT,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(anonymous_chat_id, receipt_no)
        )
        """,
        "ALTER TABLE anonymous_receipts ADD COLUMN IF NOT EXISTS receipt_author_nickname TEXT",
        "CREATE INDEX IF NOT EXISTS idx_anon_receipts_room ON anonymous_receipts(anonymous_chat_id)",
        """
        CREATE TABLE IF NOT EXISTS anonymous_relay_targets (
            id SERIAL PRIMARY KEY,
            anonymous_chat_id INTEGER NOT NULL REFERENCES anonymous_chats(id) ON DELETE CASCADE,
            from_telegram_user_id BIGINT NOT NULL,
            peer_telegram_user_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_anon_rel_room_sender ON anonymous_relay_targets(anonymous_chat_id, from_telegram_user_id)",
        "CREATE INDEX IF NOT EXISTS idx_anon_rel_sent_at ON anonymous_relay_targets(sent_at)",
        "ALTER TABLE anonymous_relay_targets ADD COLUMN IF NOT EXISTS source_message_id BIGINT",
        "ALTER TABLE anonymous_relay_targets ADD COLUMN IF NOT EXISTS relay_broadcast_id UUID",
        """
        CREATE INDEX IF NOT EXISTS idx_anon_rel_broadcast_peer
        ON anonymous_relay_targets(anonymous_chat_id, relay_broadcast_id, peer_telegram_user_id)
        WHERE relay_broadcast_id IS NOT NULL
        """,
        """
        CREATE TABLE IF NOT EXISTS anonymous_verifier_notify_reply (
            anonymous_chat_id INTEGER NOT NULL REFERENCES anonymous_chats(id) ON DELETE CASCADE,
            from_telegram_user_id BIGINT NOT NULL,
            dm_source_message_id BIGINT NOT NULL,
            peer_telegram_user_id BIGINT NOT NULL,
            relay_message_id BIGINT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (anonymous_chat_id, from_telegram_user_id, dm_source_message_id, peer_telegram_user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS group_settings (
            chat_id BIGINT PRIMARY KEY,
            trader_rate DOUBLE PRECISION DEFAULT 10,
            payout DOUBLE PRECISION DEFAULT 0,
            exchange_rate DOUBLE PRECISION DEFAULT 100,
            default_exchange_rate_id INTEGER,
            default_retention_rate_id INTEGER,
            wallet_address TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS exchange_rates (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            rate DOUBLE PRECISION NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_exchange_rates_chat ON exchange_rates(chat_id)",
        """
        CREATE TABLE IF NOT EXISTS retention_rates (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            percent DOUBLE PRECISION NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_retention_rates_chat ON retention_rates(chat_id)",
        """
        CREATE TABLE IF NOT EXISTS receipts (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            receipt_no INTEGER NOT NULL,
            amount DOUBLE PRECISION NOT NULL,
            exchange_rate_id INTEGER,
            retention_rate_id INTEGER,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_receipts_chat ON receipts(chat_id)",
        "CREATE INDEX IF NOT EXISTS idx_receipts_ts ON receipts(ts)",
        "ALTER TABLE receipts ADD COLUMN IF NOT EXISTS receipt_no INTEGER",
        """
        UPDATE receipts r SET receipt_no = s.n
        FROM (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY chat_id ORDER BY id) AS n
            FROM receipts
        ) s
        WHERE r.id = s.id AND (r.receipt_no IS NULL)
        """,
        "ALTER TABLE receipts ALTER COLUMN receipt_no SET NOT NULL",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_receipts_chat_receipt_no
        ON receipts (chat_id, receipt_no)
        """,
        """
        CREATE TABLE IF NOT EXISTS payouts (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            amount DOUBLE PRECISION NOT NULL,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_payouts_chat ON payouts(chat_id)",
        """
        CREATE TABLE IF NOT EXISTS linked_groups (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            linked_group_id BIGINT NOT NULL,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_linked_groups_chat ON linked_groups(chat_id)",
        """
        INSERT INTO global_settings (id, wallet_address)
        VALUES (1, 'TFNX7TKYCm1kUYDECjkrogBwYZvt69XQNy')
        ON CONFLICT (id) DO NOTHING
        """,
    ]
    with connection() as conn:
        _exec_many(conn, statements)
        _migrate_anonymous_chat_members_composite_pk(conn)
        _migrate_anonymous_receipts_author_nickname(conn)
    logger.info("PostgreSQL: схема проверена/создана")


def list_group_chat_ids() -> List[int]:
    """Все группы с записью в group_settings (аналог списка data_group_*.db)."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT chat_id FROM group_settings ORDER BY chat_id")
        return [int(r[0]) for r in cur.fetchall()]


def list_all_broadcast_chat_ids() -> List[int]:
    """Чаты из group_settings и из активных connections (для рассылки/стикеров)."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT cid FROM (
                SELECT chat_id AS cid FROM group_settings
                UNION
                SELECT client_group_id FROM connections WHERE is_active = TRUE
                UNION
                SELECT verifier_group_id FROM connections WHERE is_active = TRUE
            ) s ORDER BY cid
            """
        )
        return [int(r[0]) for r in cur.fetchall()]


def migrate_telegram_chat_id(old_id: int, new_id: int) -> None:
    """
    Заменяет ID чата после миграции обычной группы в супергруппу (Telegram migrate_to_chat_id).
    Обновляет все таблицы, где хранится chat_id / client_group_id / verifier_group_id.
    """
    if old_id == new_id:
        return
    pk_tables = (
        "broadcast_chats",
        "broadcast_inaccessible",
        "broadcast_always_exclude",
        "admin_chat_invite_links",
        "group_settings",
    )
    with connection() as conn:
        cur = conn.cursor()
        for tbl in pk_tables:
            cur.execute(
                f"""
                DELETE FROM {tbl}
                WHERE chat_id = %s
                  AND EXISTS (SELECT 1 FROM {tbl} AS t2 WHERE t2.chat_id = %s)
                """,
                (old_id, new_id),
            )
            cur.execute(
                f"UPDATE {tbl} SET chat_id = %s WHERE chat_id = %s",
                (new_id, old_id),
            )
        cur.execute(
            "UPDATE processed_transactions SET chat_id = %s WHERE chat_id = %s",
            (new_id, old_id),
        )
        cur.execute(
            "UPDATE exchange_rates SET chat_id = %s WHERE chat_id = %s",
            (new_id, old_id),
        )
        cur.execute(
            "UPDATE retention_rates SET chat_id = %s WHERE chat_id = %s",
            (new_id, old_id),
        )
        # UNIQUE (chat_id, receipt_no): если уже есть строки с new_id, удаляем дубли
        # со старым id с тем же receipt_no, иначе UPDATE нарушит индекс.
        cur.execute(
            """
            DELETE FROM receipts r
            WHERE r.chat_id = %s
              AND EXISTS (
                SELECT 1 FROM receipts r2
                WHERE r2.chat_id = %s AND r2.receipt_no = r.receipt_no
              )
            """,
            (old_id, new_id),
        )
        cur.execute(
            "UPDATE receipts SET chat_id = %s WHERE chat_id = %s",
            (new_id, old_id),
        )
        cur.execute(
            "UPDATE payouts SET chat_id = %s WHERE chat_id = %s",
            (new_id, old_id),
        )
        cur.execute(
            "UPDATE linked_groups SET chat_id = %s WHERE chat_id = %s",
            (new_id, old_id),
        )
        cur.execute(
            "UPDATE linked_groups SET linked_group_id = %s WHERE linked_group_id = %s",
            (new_id, old_id),
        )
        cur.execute(
            """
            UPDATE connections SET
                client_group_id = CASE WHEN client_group_id = %s THEN %s ELSE client_group_id END,
                verifier_group_id = CASE WHEN verifier_group_id = %s THEN %s ELSE verifier_group_id END
            WHERE client_group_id = %s OR verifier_group_id = %s
            """,
            (
                old_id,
                new_id,
                old_id,
                new_id,
                old_id,
                old_id,
            ),
        )
        cur.execute(
            "UPDATE anonymous_chats SET verifier_group_id = %s WHERE verifier_group_id = %s",
            (new_id, old_id),
        )
    logger.info("Telegram chat_id migrated in DB: %s -> %s", old_id, new_id)


def upsert_admin_chat_invite_link(chat_id: int, invite_link: str) -> None:
    """Сохраняет вечную ссылку-приглашение, сгенерированную ботом для веб-интерфейса /admin/chats."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO admin_chat_invite_links (chat_id, invite_link, updated_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (chat_id) DO UPDATE SET
                invite_link = EXCLUDED.invite_link,
                updated_at = CURRENT_TIMESTAMP
            """,
            (chat_id, invite_link.strip()),
        )


def ensure_group_row(chat_id: int) -> None:
    """Гарантирует строку group_settings для чата."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO group_settings (chat_id, trader_rate, payout, exchange_rate)
            VALUES (%s, 10, 0, 100)
            ON CONFLICT (chat_id) DO NOTHING
            """,
            (chat_id,),
        )
