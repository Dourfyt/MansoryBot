"""loader.initialize_db делегирует в ensure_group_row."""

import pytest


def test_initialize_db_calls_ensure_group_row(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[int] = []

    def fake(cid: int) -> None:
        called.append(cid)

    monkeypatch.setattr("bot.pg.ensure_group_row", fake)
    from bot.loader import initialize_db

    initialize_db(-999888777)
    assert called == [-999888777]
