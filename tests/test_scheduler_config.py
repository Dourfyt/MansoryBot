"""Планировщик: конфиг и импорт модуля."""


def test_scheduler_config_has_retry() -> None:
    from bot.scheduler import SCHEDULER_CONFIG

    assert SCHEDULER_CONFIG["MAX_RETRY_ATTEMPTS"] >= 1
    assert SCHEDULER_CONFIG["STICKER_DELAY_BASE"] >= 0
