# Telegram-бот (polling + HTTP рассылки)
FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libfreetype6 \
        libjpeg62-turbo \
        libpng16-16 \
        tesseract-ocr \
        tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY group_connector_bot.py .
COPY anonymous_child_runner.py .
COPY bot/ ./bot/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# HTTP для CRM должен слушать все интерфейсы внутри сети Docker
ENV BROADCAST_SERVER_HOST=0.0.0.0

CMD ["python", "group_connector_bot.py"]
