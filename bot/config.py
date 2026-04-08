"""Конфигурация бота связывания групп — из переменных окружения."""
import os
from dotenv import load_dotenv

load_dotenv()


def _parse_admin_ids(raw: str) -> list:
    out = []
    for part in (raw or "").replace(" ", "").split(","):
        if part.isdigit() or (part.startswith("-") and part[1:].isdigit()):
            out.append(int(part))
    return out


# Кэш из env; актуальный токен при работе — из БД (bot_instances) или env, см. bot.bot_token.resolve_bot_token
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip() or os.environ.get("GROUP_CONNECTOR_BOT_TOKEN", "").strip()

ADMINS = _parse_admin_ids(os.environ.get("TELEGRAM_ADMIN_IDS", ""))
if not ADMINS:
    import logging

    logging.getLogger(__name__).warning("TELEGRAM_ADMIN_IDS is empty; no Telegram admins configured.")

# Только PostgreSQL: строка подключения (например postgresql://user:pass@host:5432/dbname)
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required (PostgreSQL connection string)")

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FILE = os.environ.get("LOG_FILE", "logs/group_connector.log")

BOT_NAME = os.environ.get("BOT_NAME", "Group Connector Bot")
# Отображаемое имя мастер-бота (как в Telegram). Пусто → в заголовках /инфо подставляется «Анонимный чат».
BOT_DISPLAY_NAME = os.environ.get("BOT_DISPLAY_NAME", "").strip()
BOT_DESCRIPTION = os.environ.get("BOT_DESCRIPTION", "Бот для связывания групп клиентов с группами проверяющих")

BOT_COMMANDS = [
    ("start", "Запустить бота"),
    ("connect", "Связать группу клиентов с группой проверяющих"),
    ("disconnect", "Разорвать связь между группами"),
    ("list", "Показать все связи"),
    ("stats", "Статистика по связям"),
    ("help", "Справка"),
    ("peer_id", "Показать ID группы"),
    ("update_group_id", "Обновить ID группы (при обновлении до супергруппы)"),
    ("проверить", "Отправить фото чека (только в группах клиентов)"),
    ("чек", "Отметить чек (только в группах проверяющих)"),
]
