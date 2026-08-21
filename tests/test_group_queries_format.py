"""Форматирование отчёта /инфо без обращения к БД."""
from datetime import datetime

from bot.group_queries import format_info_message_html


def test_format_info_message_html_minimal_snapshot() -> None:
    snapshot = {
        "rows": [
            (
                1,
                100.0,
                datetime(2025, 3, 24, 12, 30, 0),
                50.0,
                10.0,
            ),
        ],
        "default_rate_value": 50.0,
        "default_retention_value": 10.0,
        "total_default_amount": 100.0,
        "other_group_amounts": [],
        "total_orders_converted_sum": 2.0,
        "total_to_pay": 1.8,
        "paid_already": 0.0,
        "remaining": 1.8,
    }
    text = format_info_message_html(snapshot, daily_report=False)
    assert "Чек №1" in text
    assert "100" in text
    assert "Оборот за день" in text
    assert "2" in text


def test_format_info_daily_header() -> None:
    snapshot = {
        "rows": [],
        "default_rate_value": None,
        "default_retention_value": None,
        "total_default_amount": 0.0,
        "other_group_amounts": [],
        "total_orders_converted_sum": 0.0,
        "total_to_pay": 0.0,
        "paid_already": 0.0,
        "remaining": 0.0,
    }
    text = format_info_message_html(snapshot, daily_report=True)
    assert "Сводка ·" in text
    assert "5192707317329575611" in text
    assert "5192964774849165242" in text


def test_format_info_intermediate_header() -> None:
    snapshot = {
        "rows": [],
        "default_rate_value": None,
        "default_retention_value": None,
        "total_default_amount": 0.0,
        "other_group_amounts": [],
        "total_orders_converted_sum": 0.0,
        "total_to_pay": 0.0,
        "paid_already": 0.0,
        "remaining": 0.0,
    }
    text = format_info_message_html(snapshot, intermediate=True)
    assert "Промежуточный итог ·" in text
