"""Конфигурация подключения к PostgreSQL."""
import pytest


def test_get_database_url_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from bot.pg import get_database_url

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        get_database_url()


def test_get_database_url_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    from bot.pg import get_database_url

    monkeypatch.setenv("DATABASE_URL", "postgresql://a:b@host:5432/db")
    assert get_database_url() == "postgresql://a:b@host:5432/db"
