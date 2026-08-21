import pytest

from bot.chek_parse import (
    chek_command_from_text,
    parse_chek_command,
    parse_chek_message,
)


def test_parse_chek_amount_only() -> None:
    assert parse_chek_command(["/чек", "1к"]) == (1000.0, None, None)


def test_parse_chek_with_rate_and_percent() -> None:
    assert parse_chek_command(["/чек", "1500", "93.5", "10"]) == (
        1500.0,
        93.5,
        10.0,
    )


def test_parse_chek_invalid_arity() -> None:
    with pytest.raises(ValueError):
        parse_chek_command(["/чек", "100", "93.5"])


def test_plus_alias() -> None:
    assert parse_chek_message("/+ 1к") == (1000.0, None, None)
    assert chek_command_from_text("/+@SomeBot 500") == "/+"


def test_minus_alias_negates_amount() -> None:
    assert parse_chek_message("/- 500") == (-500.0, None, None)
    assert parse_chek_message("/- 1к 93.5 10") == (-1000.0, 93.5, 10.0)


def test_chek_case_insensitive() -> None:
    assert parse_chek_message("/Чек 1к") == (1000.0, None, None)
    assert chek_command_from_text("/ЧЕК@Bot 100") == "/чек"
