import logging
from typing import List, Optional, Tuple

from .pg import connection

logger = logging.getLogger(__name__)


class GroupConnectionManager:
    """Менеджер связей между группами (PostgreSQL)."""

    def __init__(self, db_path: str = "") -> None:
        self._init_database()

    def _init_database(self) -> None:
        """Схема создаётся в bot.pg.init_schema при старте бота."""
        logger.info("GroupConnectionManager готов (PostgreSQL)")

    def get_welcome_content(self) -> Tuple[Optional[str], List[dict]]:
        try:
            with connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT welcome_message, welcome_links FROM global_settings WHERE id = 1"
                )
                row = cur.fetchone()
            if not row:
                return None, []
            msg = (row[0] or "").strip() if row[0] else ""
            links = []
            if row[1]:
                try:
                    import json

                    links = json.loads(row[1])
                    if not isinstance(links, list):
                        links = []
                    links = [
                        {"label": str(x.get("label", "")), "url": str(x.get("url", ""))}
                        for x in links
                        if x.get("url")
                    ]
                except Exception:
                    links = []
            return msg or None, links
        except Exception as e:
            logger.error("Ошибка при чтении приветствия: %s", e)
            return None, []

    def refresh_broadcast_chats(self) -> int:
        """Синхронизирует broadcast_chats с group_settings и активными connections."""
        try:
            with connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO broadcast_chats (chat_id, name)
                    SELECT chat_id, NULL FROM group_settings
                    ON CONFLICT (chat_id) DO NOTHING
                    """
                )
                cur.execute(
                    """
                    SELECT client_group_id FROM connections WHERE is_active = TRUE
                    UNION
                    SELECT verifier_group_id FROM connections WHERE is_active = TRUE
                    """
                )
                ids = [r[0] for r in cur.fetchall()]
                for cid in ids:
                    cur.execute(
                        """
                        INSERT INTO broadcast_chats (chat_id, name)
                        VALUES (%s, NULL)
                        ON CONFLICT (chat_id) DO NOTHING
                        """,
                        (cid,),
                    )
            logger.info("Обновлён список рассылки: %s чатов", len(ids))
            return len(ids)
        except Exception as e:
            logger.error("Ошибка при обновлении broadcast_chats: %s", e)
            return 0

    def update_broadcast_chat_name(self, chat_id: int, name: str) -> None:
        if not name or not name.strip():
            return
        try:
            with connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE broadcast_chats SET name = %s WHERE chat_id = %s",
                    (name.strip(), chat_id),
                )
        except Exception as e:
            logger.error("Ошибка при обновлении названия broadcast_chats: %s", e)

    def mark_broadcast_inaccessible(self, chat_id: int) -> None:
        try:
            with connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO broadcast_inaccessible (chat_id) VALUES (%s)
                    ON CONFLICT (chat_id) DO NOTHING
                    """,
                    (chat_id,),
                )
            logger.info("Группа %s помечена как недоступная для рассылки", chat_id)
        except Exception as e:
            logger.error("Ошибка при записи broadcast_inaccessible: %s", e)

    def clear_broadcast_inaccessible(self, chat_id: int) -> None:
        """Убрать пометку недоступности (бот снова видит чат)."""
        try:
            with connection() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM broadcast_inaccessible WHERE chat_id = %s", (chat_id,))
        except Exception as e:
            logger.error("Ошибка при удалении из broadcast_inaccessible: %s", e)

    def upsert_broadcast_chat_row(self, chat_id: int, name: Optional[str]) -> None:
        """Строка в broadcast_chats для названия после успешного get_chat."""
        nm = (name or "").strip() or None
        try:
            with connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO broadcast_chats (chat_id, name) VALUES (%s, %s)
                    ON CONFLICT (chat_id) DO UPDATE SET name = COALESCE(EXCLUDED.name, broadcast_chats.name)
                    """,
                    (chat_id, nm),
                )
        except Exception as e:
            logger.error("Ошибка при upsert broadcast_chats: %s", e)

    def get_broadcast_chat_ids(self) -> List[int]:
        try:
            with connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT b.chat_id FROM broadcast_chats b
                    LEFT JOIN broadcast_inaccessible i ON b.chat_id = i.chat_id
                    WHERE i.chat_id IS NULL
                    ORDER BY b.chat_id
                    """
                )
                return [int(r[0]) for r in cur.fetchall()]
        except Exception as e:
            logger.error("Ошибка при чтении broadcast_chats: %s", e)
            return []

    def add_connection(
        self,
        client_group_id: int,
        verifier_group_id: int,
        client_group_name: str = None,
        verifier_group_name: str = None,
    ) -> bool:
        try:
            with connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO connections
                    (client_group_id, verifier_group_id, client_group_name, verifier_group_name, is_active)
                    VALUES (%s, %s, %s, %s, TRUE)
                    ON CONFLICT (client_group_id, verifier_group_id)
                    DO UPDATE SET
                        client_group_name = COALESCE(EXCLUDED.client_group_name, connections.client_group_name),
                        verifier_group_name = COALESCE(EXCLUDED.verifier_group_name, connections.verifier_group_name),
                        is_active = TRUE
                    """,
                    (
                        client_group_id,
                        verifier_group_id,
                        client_group_name,
                        verifier_group_name,
                    ),
                )
            logger.info(
                "Связь добавлена: клиенты %s ↔ проверяющие %s",
                client_group_id,
                verifier_group_id,
            )
            return True
        except Exception as e:
            logger.error("Ошибка при добавлении связи: %s", e)
            return False

    def remove_connection(self, client_group_id: int, verifier_group_id: int) -> bool:
        try:
            with connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    UPDATE connections SET is_active = FALSE
                    WHERE client_group_id = %s AND verifier_group_id = %s
                    """,
                    (client_group_id, verifier_group_id),
                )
                ok = cur.rowcount > 0
            if ok:
                logger.info(
                    "Связь удалена: клиенты %s ↔ проверяющие %s",
                    client_group_id,
                    verifier_group_id,
                )
            return ok
        except Exception as e:
            logger.error("Ошибка при удалении связи: %s", e)
            return False

    def get_verifier_group(self, client_group_id: int) -> Optional[Tuple[int, str]]:
        try:
            with connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT verifier_group_id, verifier_group_name FROM connections
                    WHERE client_group_id = %s AND is_active = TRUE
                    """,
                    (client_group_id,),
                )
                return cur.fetchone()
        except Exception as e:
            logger.error("Ошибка при получении группы проверяющих: %s", e)
            return None

    def get_client_groups(self, verifier_group_id: int) -> List[Tuple[int, str]]:
        try:
            with connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT client_group_id, client_group_name FROM connections
                    WHERE verifier_group_id = %s AND is_active = TRUE
                    """,
                    (verifier_group_id,),
                )
                return cur.fetchall()
        except Exception as e:
            logger.error("Ошибка при получении групп клиентов: %s", e)
            return []

    def get_group_role(self, group_id: int) -> Optional[str]:
        try:
            with connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT 1 FROM connections
                    WHERE client_group_id = %s AND is_active = TRUE
                    """,
                    (group_id,),
                )
                if cur.fetchone():
                    return "client"
                cur.execute(
                    """
                    SELECT 1 FROM connections
                    WHERE verifier_group_id = %s AND is_active = TRUE
                    """,
                    (group_id,),
                )
                if cur.fetchone():
                    return "verifier"
            return None
        except Exception as e:
            logger.error("Ошибка при определении роли группы: %s", e)
            return None

    def update_group_id(self, old_group_id: int, new_group_id: int) -> bool:
        try:
            from .pg import migrate_telegram_chat_id

            migrate_telegram_chat_id(old_group_id, new_group_id)
            logger.info("ID группы обновлён (все таблицы): %s -> %s", old_group_id, new_group_id)
            return True
        except Exception as e:
            logger.error("Ошибка при обновлении ID группы: %s", e)
            return False

    def get_connected_group(self, chat_id: int) -> Optional[Tuple[int, str]]:
        role = self.get_group_role(chat_id)
        if role == "client":
            return self.get_verifier_group(chat_id)
        if role == "verifier":
            client_groups = self.get_client_groups(chat_id)
            return client_groups[0] if client_groups else None
        return None

    def get_all_connections(self) -> List[Tuple]:
        try:
            with connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT client_group_id, verifier_group_id, client_group_name, verifier_group_name,
                           created_at, is_active
                    FROM connections WHERE is_active = TRUE
                    ORDER BY created_at DESC
                    """
                )
                return cur.fetchall()
        except Exception as e:
            logger.error("Ошибка при получении всех связей: %s", e)
            return []

    def get_connections_for_group(self, group_id: int) -> List[Tuple]:
        try:
            with connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT client_group_id, verifier_group_id, client_group_name, verifier_group_name,
                           created_at, is_active
                    FROM connections
                    WHERE (client_group_id = %s OR verifier_group_id = %s) AND is_active = TRUE
                    ORDER BY created_at DESC
                    """,
                    (group_id, group_id),
                )
                return cur.fetchall()
        except Exception as e:
            logger.error("Ошибка при получении связей для группы %s: %s", group_id, e)
            return []

    def is_group_connected(self, group_id: int) -> bool:
        return self.get_group_role(group_id) is not None

    def update_group_names(
        self,
        client_group_id: int,
        verifier_group_id: int,
        client_group_name: str = None,
        verifier_group_name: str = None,
    ) -> bool:
        try:
            with connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    UPDATE connections SET
                        client_group_name = COALESCE(%s, client_group_name),
                        verifier_group_name = COALESCE(%s, verifier_group_name)
                    WHERE client_group_id = %s AND verifier_group_id = %s
                    """,
                    (
                        client_group_name,
                        verifier_group_name,
                        client_group_id,
                        verifier_group_id,
                    ),
                )
                return cur.rowcount > 0
        except Exception as e:
            logger.error("Ошибка при обновлении названий групп: %s", e)
            return False

    def get_connection_stats(self) -> dict:
        try:
            with connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM connections WHERE is_active = TRUE")
                total_connections = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM connections WHERE is_active = FALSE")
                inactive_connections = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(DISTINCT verifier_group_id) FROM connections WHERE is_active = TRUE"
                )
                unique_verifiers = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(DISTINCT client_group_id) FROM connections WHERE is_active = TRUE"
                )
                unique_clients = cur.fetchone()[0]
            return {
                "total": total_connections,
                "active": total_connections,
                "inactive": inactive_connections,
                "unique_verifiers": unique_verifiers,
                "unique_clients": unique_clients,
            }
        except Exception as e:
            logger.error("Ошибка при получении статистики: %s", e)
            return {
                "total": 0,
                "active": 0,
                "inactive": 0,
                "unique_verifiers": 0,
                "unique_clients": 0,
            }
