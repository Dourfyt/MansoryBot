"""Текст/подпись сообщения для Tron: хеши, ссылки, скрины."""
from __future__ import annotations

import re
from typing import List

from aiogram.types import Message

_TRONSCAN_LINK = re.compile(
    r"https?://(?:www\.)?tronscan\.org/#/transaction/([a-fA-F0-9]{64})",
    re.IGNORECASE,
)
_HEX64 = re.compile(r"[a-fA-F0-9]{64}")
_INVISIBLE = re.compile(r"[\u200b\u200c\u200d\ufeff]")


def message_tron_content(message: Message) -> str:
    """Текст сообщения + подпись к фото/документу."""
    parts = [message.text or "", message.caption or ""]
    return "\n".join(p for p in parts if p).strip()


def find_tron_tx_hashes(content: str) -> List[str]:
    """64-символьные hex-хеши (без жёстких \\b — надёжнее для копипаста)."""
    if not content:
        return []
    cleaned = _INVISIBLE.sub("", content)
    seen: set[str] = set()
    out: list[str] = []
    for m in _HEX64.finditer(cleaned):
        h = m.group(0).lower()
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def find_tron_hashes_and_links(content: str) -> List[str]:
    hashes: list[str] = []
    for h in _TRONSCAN_LINK.findall(content or ""):
        hl = h.lower()
        if hl not in hashes:
            hashes.append(hl)
    for h in find_tron_tx_hashes(content):
        if h not in hashes:
            hashes.append(h)
    return hashes


def message_image_file_id(message: Message) -> str | None:
    """file_id картинки: photo или document с image/*."""
    if message.photo:
        return message.photo[-1].file_id
    doc = message.document
    if doc and (doc.mime_type or "").startswith("image/"):
        return doc.file_id
    return None


def tron_filter_skip_reason(message: Message) -> str | None:
    """
    Почему сообщение не пойдёт в handle_tron_payout.
    None — обработчик Tron будет вызван (фильтр пройден).
    """
    if message.chat.type not in ("group", "supergroup"):
        return "not_group"
    if message.from_user and message.from_user.is_bot:
        return "from_bot"
    content = message_tron_content(message)
    if content.startswith("/"):
        return "caption_is_command"
    if find_tron_hashes_and_links(content):
        return None
    from .tron_screen_parse import looks_like_tron_wallet_screen

    if content and looks_like_tron_wallet_screen(content):
        return None
    if message_image_file_id(message) and not content:
        return None
    return "not_tron_candidate"


def looks_like_tron_payout_message(message: Message) -> bool:
    """Нужно ли обрабатывать это сообщение как Tron-выплату."""
    return tron_filter_skip_reason(message) is None
