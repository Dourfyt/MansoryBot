"""Разбор migrate_to_chat_id из исключений Telegram."""
import group_connector_bot as gcb


def test_analyze_exception_migrate_from_message() -> None:
    class E(Exception):
        pass

    e = E("group chat was upgraded migrate_to_chat_id: -1001234567890")
    assert gcb.analyze_exception_for_migrate_id(e) == -1001234567890


def test_analyze_exception_no_match() -> None:
    assert gcb.analyze_exception_for_migrate_id(ValueError("other")) is None
