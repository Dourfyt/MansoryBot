# Mansory Bot — Telegram-бот для учёта чеков и связок групп

## Описание

Один процесс бота (`group_connector_bot.py`): учёт чеков, связи клиент ↔ проверяющие, Tron, планировщик (сброс, сводки, стикеры), HTTP для рассылки из CRM, тикеты поддержки.

## Установка и запуск

### 1. Зависимости

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Конфигурация

Скопируйте `.env.example` в `.env` и задайте как минимум **`BOT_TOKEN`** (токен от [@BotFather](https://t.me/BotFather)).

### 3. Запуск бота

```bash
python group_connector_bot.py
```

Для продакшена удобен systemd, см. пример `group-connector-bot.service` (путь `WorkingDirectory` и `ExecStart` подставьте свои).

### 4. Docker (бот + админка)

После настройки `.env`:

```bash
docker compose up -d --build
```

- Бот и планировщик — сервис `bot`, SQLite и логи в томах `app_data` и `bot_logs`.
- Админка — сервис `admin`, веб: `http://localhost:3000`. Рассылка ходит на бота по сети compose: `BOT_BROADCAST_URL=http://bot:8765`.

Опционально PostgreSQL (пока приложение на SQLite): `docker compose --profile postgres up -d`.

## Структура проекта (основное)

- `group_connector_bot.py` — точка входа: polling, планировщик, рассылка, связи
- `bot/` — модули бота: `loader`, `config`, `scheduler`, `group_manager`, `crm_support`
- `admin-app/` — веб-CRM (Next.js), тот же домен, что и раньше

## Планировщик

Время задаётся в `bot/scheduler.py` (cron, UTC). Для проверки вручную можно использовать `check_scheduler.py`.


## Админка (CRM)

См. `admin-app/README` или запуск в каталоге `admin-app`: `npm install && npm run dev`.

## Логирование

Логи планировщика: каталог `logs/` (см. `bot/scheduler.py`).
