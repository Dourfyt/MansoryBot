import pytest

from bot.amount_parse import parse_amount


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1000", 1000.0),
        ("1к", 1000.0),
        ("1К", 1000.0),
        ("1k", 1000.0),
        ("1кк", 1_000_000.0),
        ("1kk", 1_000_000.0),
        ("1.000", 1000.0),
        ("1.000.000", 1_000_000.0),
        ("100.00", 100.0),
        ("1,5к", 1500.0),
        ("-50к", -50_000.0),
        ("2.5кк", 2_500_000.0),
        ("1 000", 1000.0),
    ],
)
def test_parse_amount(raw: str, expected: float) -> None:
    assert parse_amount(raw) == expected


def test_parse_amount_invalid() -> None:
    with pytest.raises(ValueError):
        parse_amount("")
