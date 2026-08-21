"""HTML для Telegram: кастомные emoji и fallback при ENTITY_TEXT_INVALID."""
from __future__ import annotations

import re

_TG_EMOJI_TAG_RE = re.compile(
    r'<tg-emoji emoji-id="\d+">(.*?)</tg-emoji>',
    re.DOTALL,
)


def strip_tg_emoji_tags(text: str) -> str:
    """Убирает <tg-emoji>, оставляет плейсхолдеры (обычные emoji/текст)."""
    return _TG_EMOJI_TAG_RE.sub(r"\1", text)
