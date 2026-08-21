"""Polling дочерних ботов анонимных чатов: синхронизация с БД, автозапуск и остановка."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import Dict, Optional

from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage

from bot.anonymous_bot_commands import setup_anonymous_private_bot_commands
from bot.anonymous_chat import list_active_child_bot_tokens
from bot.anonymous_relay_handlers import register_anonymous_handlers
from bot.config import ANONYMOUS_CHATS_ENABLED
from bot.pg import init_schema

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

POLL_INTERVAL = float(os.environ.get("ANONYMOUS_CHILD_POLL_INTERVAL", "15"))


class ChildBotHandle:
    """Один дочерний бот: polling до stop_polling или падения (с повтором)."""

    __slots__ = ("room_id", "token", "bot", "dp", "_task")

    def __init__(self, room_id: int, token: str) -> None:
        self.room_id = room_id
        self.token = token
        self.bot = Bot(token=token)
        self.dp = Dispatcher(storage=MemoryStorage())
        router = Router()
        register_anonymous_handlers(
            router,
            master_mode=False,
            include_private_catchall=True,
            child_room_id=self.room_id,
        )
        self.dp.include_router(router)
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"anon-child-{self.room_id}")

    async def _reset_bot(self) -> None:
        try:
            await self.bot.session.close()
        except Exception:
            pass
        self.bot = Bot(token=self.token)

    async def _run(self) -> None:
        try:
            while True:
                try:
                    await setup_anonymous_private_bot_commands(self.bot)
                    await self.dp.start_polling(
                        self.bot,
                        close_bot_session=True,
                        polling_timeout=30,
                    )
                    return
                except asyncio.CancelledError:
                    raise
                except TelegramNetworkError as e:
                    logger.warning(
                        "Child room_id=%s: сеть Telegram (%s), повтор через 30 с",
                        self.room_id,
                        e,
                    )
                    await self._reset_bot()
                    await asyncio.sleep(30)
                except Exception:
                    logger.exception(
                        "Child-бот room_id=%s, повтор через 5 с", self.room_id
                    )
                    await self._reset_bot()
                    await asyncio.sleep(5)
        finally:
            try:
                await self.bot.session.close()
            except Exception:
                pass

    async def stop(self) -> None:
        try:
            await self.dp.stop_polling()
        except Exception:
            logger.debug("stop_polling room_id=%s", self.room_id, exc_info=True)
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=45)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            except asyncio.CancelledError:
                pass
        self._task = None


async def _sync_children(active: Dict[int, ChildBotHandle]) -> None:
    pairs = list_active_child_bot_tokens()
    want = {rid: tok for rid, tok in pairs}

    for room_id, h in list(active.items()):
        if room_id not in want or h.token != want[room_id]:
            logger.info("Останавливаем child room_id=%s (токен удалён или сменился)", room_id)
            await h.stop()
            del active[room_id]

    for room_id, token in want.items():
        if room_id not in active:
            logger.info("Запускаем child room_id=%s", room_id)
            h = ChildBotHandle(room_id, token)
            active[room_id] = h
            h.start()


async def main() -> None:
    if not ANONYMOUS_CHATS_ENABLED:
        logger.info(
            "Анонимные чаты отключены (ANONYMOUS_CHATS_ENABLED=false). "
            "Супервизор дочерних ботов не запускается — контейнер в ожидании."
        )
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:
                pass
        await stop.wait()
        return
    init_schema()
    active: Dict[int, ChildBotHandle] = {}
    stop = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    logger.info(
        "Супервизор дочерних ботов: интервал опроса БД %.1f с (ANONYMOUS_CHILD_POLL_INTERVAL)",
        POLL_INTERVAL,
    )

    try:
        while not stop.is_set():
            try:
                await _sync_children(active)
            except Exception:
                logger.exception("Ошибка синхронизации дочерних ботов")
            try:
                await asyncio.wait_for(stop.wait(), timeout=POLL_INTERVAL)
            except asyncio.TimeoutError:
                pass
    finally:
        logger.info("Останавливаем %s дочерних ботов…", len(active))
        for h in list(active.values()):
            await h.stop()
        active.clear()


if __name__ == "__main__":
    asyncio.run(main())
