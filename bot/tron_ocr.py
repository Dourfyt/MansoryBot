"""OCR текста со скрина (опционально: нужен tesseract в системе)."""
from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from typing import Optional

from aiogram import Bot

logger = logging.getLogger(__name__)


def _ocr_image_bytes(data: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.warning("tesseract OCR недоступен: не установлены pytesseract/Pillow")
        return ""

    try:
        img = Image.open(BytesIO(data))
        return pytesseract.image_to_string(img, lang="eng") or ""
    except Exception as e:
        logger.warning("tesseract OCR failed: %s", e)
        return ""


async def ocr_telegram_photo(
    bot: Bot,
    file_id: str,
    *,
    chat_id: int | None = None,
    message_id: int | None = None,
) -> str:
    """Скачивает фото из Telegram и распознаёт текст (пустая строка если OCR недоступен)."""
    ctx = f" chat_id={chat_id} message_id={message_id}" if chat_id is not None else ""
    try:
        buf = BytesIO()
        await bot.download(file_id, destination=buf)
        data = buf.getvalue()
        if not data:
            logger.warning("ocr_telegram_photo: пустой файл%s", ctx)
            return ""
        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(None, _ocr_image_bytes, data)
        if not text.strip():
            logger.warning("ocr_telegram_photo: OCR вернул пустой текст%s", ctx)
        else:
            logger.info(
                "ocr_telegram_photo: распознано %s символов%s",
                len(text.strip()),
                ctx,
            )
        return text
    except Exception as e:
        logger.warning("ocr_telegram_photo:%s %s", ctx, e)
        return ""
