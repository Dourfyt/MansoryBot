"""Фильтры команд без учёта регистра (/Чек = /чек)."""
from __future__ import annotations

from aiogram.filters import Command, CommandStart


def Cmd(*values, **kwargs):
    return Command(*values, ignore_case=True, **kwargs)


def CmdStart(**kwargs):
    return CommandStart(ignore_case=True, **kwargs)
