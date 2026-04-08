"""
Перед импортом бота задаём переменные окружения (loader требует BOT_TOKEN).
Интеграционные тесты используют DATABASE_URL или TEST_DATABASE_URL.
"""
from __future__ import annotations

import os

# Должно выполниться до импорта bot.loader / group_connector_bot
os.environ.setdefault("BOT_TOKEN", "0000000000:TEST_TOKEN_FOR_PYTEST_ONLY_INVALID_ON_TELEGRAM")
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://balenciaga_admin:S5VSaX0%2FOvWCP%2BDDYFplAOdrDPSDzcpl3qIcUnqPZrQ%3D@127.0.0.1:5432/crm",
    ),
)

import pytest


@pytest.fixture(scope="session")
def postgres_available() -> bool:
    try:
        import psycopg2

        psycopg2.connect(os.environ["DATABASE_URL"]).close()
        return True
    except Exception:
        return False


_schema_done = False


@pytest.fixture
def db_ready(postgres_available: bool):
    """Один раз за прогон вызывает init_schema; без БД — skip."""
    global _schema_done
    if not postgres_available:
        pytest.skip("PostgreSQL недоступен (DATABASE_URL)")
    if not _schema_done:
        from bot.pg import init_schema

        init_schema()
        _schema_done = True


@pytest.fixture
def unique_chat_id(request) -> int:
    """Уникальный отрицательный chat_id, чтобы не пересекаться с реальными группами."""
    h = abs(hash(request.node.nodeid)) % 10_000_000_000
    return -(9_000_000_000_000 + h)


def cleanup_chat_data(chat_id: int) -> None:
    from bot.pg import connection

    with connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM receipts WHERE chat_id = %s", (chat_id,))
        cur.execute("DELETE FROM payouts WHERE chat_id = %s", (chat_id,))
        cur.execute("DELETE FROM exchange_rates WHERE chat_id = %s", (chat_id,))
        cur.execute("DELETE FROM retention_rates WHERE chat_id = %s", (chat_id,))
        cur.execute("DELETE FROM group_settings WHERE chat_id = %s", (chat_id,))
