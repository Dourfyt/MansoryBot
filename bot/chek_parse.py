"""Разбор команды /чек (и алиасов /+, /-): сумма и опционально курс + процент."""
from __future__ import annotations

from typing import Optional, Tuple

from aiogram.filters import BaseFilter
from aiogram.types import Message

from .amount_parse import parse_amount

CHEK_COMMANDS = frozenset({"/чек", "/+", "/-"})


def _command_token_casefold(text: str) -> str:
    """Первый токен команды без @bot, без учёта регистра."""
    return text.split(maxsplit=1)[0].split("@")[0].casefold()


def _parse_rate_or_percent(raw: str) -> float:
    s = (raw or "").strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    if not s:
        raise ValueError("пустое значение")
    return float(s)


def chek_command_from_text(text: str) -> Optional[str]:
    if not text or not text.startswith("/"):
        return None
    cmd_fold = _command_token_casefold(text)
    for cmd in CHEK_COMMANDS:
        if cmd_fold == cmd.casefold():
            return cmd
    return None


class ChekCommandFilter(BaseFilter):
    """/чек, /+ и /- (с опциональным @username бота)."""

    async def __call__(self, message: Message) -> bool:
        return chek_command_from_text(message.text or "") is not None


def split_chek_message(text: str) -> list[str]:
    """Нормализует /+, /- в формат /чек для parse_chek_command."""
    parts = (text or "").strip().split()
    if not parts:
        raise ValueError("пустое сообщение")
    cmd_fold = parts[0].split("@")[0].casefold()
    if cmd_fold == "/чек".casefold():
        return parts
    if cmd_fold == "/+".casefold():
        return ["/чек", *parts[1:]]
    if cmd_fold == "/-".casefold():
        rest = list(parts[1:])
        if not rest:
            raise ValueError("нет суммы")
        if not rest[0].startswith("-"):
            rest[0] = "-" + rest[0].lstrip("+")
        return ["/чек", *rest]
    raise ValueError("не команда чека")


def parse_chek_message(text: str) -> Tuple[float, Optional[float], Optional[float]]:
    return parse_chek_command(split_chek_message(text))


def parse_chek_command(parts: list[str]) -> Tuple[float, Optional[float], Optional[float]]:
    """
    /чек <сумма>
    /чек <сумма> <курс> <процент>

    Возвращает (amount, rate_value|None, percent_value|None).
    Курс и процент задаются только парой.
    """
    argc = len(parts) - 1
    if argc < 1:
        raise ValueError("нет аргументов")
    if argc == 1:
        return parse_amount(parts[1]), None, None
    if argc == 3:
        amount = parse_amount(parts[1])
        rate = _parse_rate_or_percent(parts[2])
        percent = _parse_rate_or_percent(parts[3])
        return amount, rate, percent
    raise ValueError("неверное число аргументов")
