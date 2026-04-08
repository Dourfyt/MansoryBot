import os
from functools import wraps
from typing import Union, Callable, Awaitable, Optional

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.enums import ChatType
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery

load_dotenv()


class BotHolder:
    """Один объект-обёртка: при смене токена подменяется внутренний Bot (все import bot видят актуальный)."""

    __slots__ = ("_bot",)

    def __init__(self) -> None:
        self._bot: Optional[Bot] = None

    def init(self, token: str) -> None:
        self._bot = Bot(token=token)

    async def replace(self, token: str) -> None:
        """Новый Bot; старый закрываем (повторный close после start_polling — безопасно)."""
        if self._bot is not None:
            try:
                await self._bot.session.close()
            except Exception:
                pass
        self._bot = Bot(token=token)

    @property
    def inner(self) -> Bot:
        if self._bot is None:
            raise RuntimeError("Bot not initialized (call init after init_schema)")
        return self._bot

    def __getattr__(self, name: str):
        if self._bot is None:
            raise RuntimeError("Bot not initialized")
        return getattr(self._bot, name)


bot = BotHolder()
dp = Dispatcher(storage=MemoryStorage())

TRON_PRO_API_KEY = os.environ.get("TRON_PRO_API_KEY", "").strip()
if not TRON_PRO_API_KEY:
    import logging

    logging.getLogger(__name__).warning("TRON_PRO_API_KEY is not set; Tron API calls may fail.")


def initialize_db(chat_id: int) -> None:
    """Гарантирует строку настроек для группы в PostgreSQL (chat_id — ID группы Telegram)."""
    from bot.pg import ensure_group_row

    ensure_group_row(chat_id)


last_bot_messages = {}


async def delete_last_bot_message(message: Message):
    if message.from_user is None:
        return
    user_id = message.from_user.id
    chat_id = message.chat.id
    if user_id in last_bot_messages:
        try:
            await bot.delete_message(chat_id, last_bot_messages[user_id])
        except Exception as e:
            print(f"Не удалось удалить сообщение: {e}")
        del last_bot_messages[user_id]


def with_clean_previous(delete_user_message: bool = True):
    def decorator(func: Callable[..., Awaitable[Union[Message, None]]]):
        @wraps(func)
        async def wrapper(event: Union[Message, CallbackQuery], *args, **kwargs):
            if isinstance(event, Message):
                if event.from_user is None:
                    return await func(event, *args, **kwargs)
                user_id = event.from_user.id
                chat_id = event.chat.id
                message_id = event.message_id
                chat_type = event.chat.type
            elif isinstance(event, CallbackQuery):
                if event.from_user is None or event.message is None:
                    return await func(event, *args, **kwargs)
                user_id = event.from_user.id
                chat_id = event.message.chat.id
                message_id = event.message.message_id
                chat_type = event.message.chat.type
            else:
                raise TypeError("Поддерживается только Message или CallbackQuery")

            if user_id in last_bot_messages:
                try:
                    await bot.delete_message(chat_id, last_bot_messages[user_id])
                except Exception as e:
                    print(f"[!] Не удалось удалить предыдущее сообщение бота: {e}")
                del last_bot_messages[user_id]

            if delete_user_message:
                try:
                    await bot.delete_message(chat_id, message_id)
                except Exception as e:
                    print(f"[!] Не удалось удалить сообщение пользователя: {e}")

            sent = await func(event, *args, **kwargs)

            if isinstance(sent, Message):
                last_bot_messages[user_id] = sent.message_id

        return wrapper

    return decorator
