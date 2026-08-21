from bot.ui_copy import format_money


def test_format_money_thousands_and_decimals() -> None:
    assert format_money(1500.5) == "1.500,50"
    assert format_money(1234567.89) == "1.234.567,89"


def test_format_money_negative() -> None:
    assert format_money(-50.25) == "−50,25"
