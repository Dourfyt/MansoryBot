import asyncio
import time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from pytz import timezone
import subprocess
import sys
import os
from datetime import datetime
import logging
from logging.handlers import TimedRotatingFileHandler
from .loader import bot, initialize_db
from .pg import list_group_chat_ids
from .group_queries import (
    build_info_snapshot,
    format_info_message_html,
    count_receipts_on_local_date,
    reset_group_data,
)
from .anonymous_chat import (
    anonymous_today_msk_date_str,
    build_anonymous_info_snapshot,
    count_anonymous_receipts_today,
    format_anonymous_info_html,
    get_child_bot_token,
    list_active_anonymous_room_ids,
    list_member_telegram_ids_for_room,
    reset_anonymous_receipts_for_room,
    purge_stale_anonymous_chat_data_with_telegram,
)
from aiogram import Bot as AiogramBot
from aiogram.types import Sticker

# Настройка логирования
def setup_logging():
    """Настройка логирования для планировщика с разбиением по датам"""
    # Создаем папку для логов, если её нет
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Создаем логгер
    logger = logging.getLogger('scheduler')
    logger.setLevel(logging.INFO)
    
    # Очищаем существующие обработчики, если есть
    logger.handlers.clear()
    
    # Формат логов
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Обработчик для файлов с ротацией по датам (каждый день в полночь)
    file_handler = TimedRotatingFileHandler(
        filename='logs/scheduler.log',
        when='midnight',
        interval=1,
        backupCount=30,  # Храним логи за последние 30 дней
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    file_handler.suffix = '%Y-%m-%d'  # Формат даты в имени файла
    
    # Обработчик для консоли
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Добавляем обработчики к логгеру
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Инициализируем логгер
logger = setup_logging()

# Кэш для хранения информации о доступных ботах для каждого чата
bot_cache = {}

# Счетчик для периодической очистки кэша
cache_hit_counter = 0

def log_error_details(logger_func, error: Exception, context: str = ""):
    """Безопасно логирует детали ошибки"""
    try:
        logger_func(f"   Тип ошибки: {type(error).__name__}")
        logger_func(f"   Сообщение: {str(error)}")
        
        # Проверяем атрибуты с помощью getattr для безопасности
        if hasattr(error, 'response'):
            response = getattr(error, 'response', None)
            if response is not None:
                logger_func(f"   Response: {response}")
        
        if hasattr(error, 'status_code'):
            status_code = getattr(error, 'status_code', None)
            if status_code is not None:
                logger_func(f"   Status Code: {status_code}")
        
        if hasattr(error, 'description'):
            description = getattr(error, 'description', None)
            if description is not None:
                logger_func(f"   Description: {description}")
        
        if hasattr(error, 'error_code'):
            error_code = getattr(error, 'error_code', None)
            if error_code is not None:
                logger_func(f"   Error Code: {error_code}")
                
    except Exception:
        logger_func(f"   Не удалось получить детали ошибки")

async def get_chat_info(bot_instance, chat_id):
    """Получает информацию о чате для проверки доступности бота"""
    try:
        chat = await bot_instance.get_chat(chat_id)
        return chat
    except Exception as e:
        error_str = str(e)
        
        # Подробное логирование ошибок при проверке доступности
        logger.debug(f"🔍 Ошибка при проверке доступности бота к чату {chat_id}:")
        log_error_details(logger.debug, e)
        
        if "Forbidden" in error_str or "Chat not found" in error_str:
            logger.debug(f"❌ Бот не имеет доступа к чату {chat_id}")
            return None
        raise e

async def find_available_bot(chat_id, force_refresh=False):
    """Находит первого доступного бота для указанного чата"""
    # Просто возвращаем первого бота, так как теперь send_message_optimized
    # сама пробует всех ботов по очереди
    logger.debug(f"🔍 Возвращаем первого бота для чата {chat_id}")
    return bot

def _is_permanent_send_error(error_str):
    """Ошибки, после которых группу считаем недоступной для рассылки."""
    s = (error_str or "").lower()
    return (
        "bot was kicked" in s
        or "bot was blocked" in s
        or "chat not found" in s
    )


async def send_message_optimized(chat_id, message, parse_mode=None, is_sticker=False, on_inaccessible=None):
    """Оптимизированная отправка сообщения через подходящего бота.
    on_inaccessible: опциональный callback(chat_id) при постоянной недоступности чата."""
    bots = [bot]
    bot_names = ["bot"]
    last_error = None

    for bot_index, bot_instance in enumerate(bots):
        logger.info(f"🤖 Пробуем отправить через {bot_names[bot_index]} в чат {chat_id}")
        for attempt in range(SCHEDULER_CONFIG['MAX_RETRY_ATTEMPTS']):
            try:
                if is_sticker:
                    await bot_instance.send_sticker(chat_id, message)
                else:
                    await bot_instance.send_message(chat_id, message, parse_mode=parse_mode)
                logger.info(f"✅ Сообщение успешно отправлено в чат {chat_id} через {bot_names[bot_index]}")
                return True
            except Exception as e:
                error_str = str(e)
                last_error = error_str
                logger.error(f"🚨 Ошибка от {bot_names[bot_index]} для чата {chat_id} (попытка {attempt + 1}/{SCHEDULER_CONFIG['MAX_RETRY_ATTEMPTS']}):")
                log_error_details(logger.error, e)
                if "bot was kicked" in error_str or "bot was blocked" in error_str:
                    logger.warning(f"🔄 {bot_names[bot_index]} заблокирован/исключен для чата {chat_id}")
                    try:
                        bot_info = await bot_instance.get_me()
                        chat_member = await bot_instance.get_chat_member(chat_id, bot_info.id)
                        logger.info(f"📊 Статус {bot_names[bot_index]} в группе {chat_id}: {chat_member.status}")
                        if chat_member.status not in ["left", "kicked"]:
                            logger.info(f"✅ {bot_names[bot_index]} активен в группе {chat_id}, пробуем повторную отправку")
                            await asyncio.sleep(2)
                            continue
                    except Exception as status_error:
                        logger.warning(f"⚠️ Не удалось проверить статус {bot_names[bot_index]}: {status_error}")
                    logger.warning(f"⚠️ {bot_names[bot_index]} заблокирован, переходим к следующему боту")
                    break
                elif "Too Many Requests" in error_str:
                    logger.warning(f"⏳ Превышен лимит запросов для {bot_names[bot_index]} в чат {chat_id}")
                    if attempt < SCHEDULER_CONFIG['MAX_RETRY_ATTEMPTS'] - 1:
                        await asyncio.sleep(SCHEDULER_CONFIG['ERROR_DELAY_LONG'])
                    continue
                else:
                    logger.error(f"❌ Неизвестная ошибка от {bot_names[bot_index]} в чат {chat_id}")
                    if attempt < SCHEDULER_CONFIG['MAX_RETRY_ATTEMPTS'] - 1:
                        await asyncio.sleep(SCHEDULER_CONFIG['ERROR_DELAY_SHORT'])
                    continue

    logger.error(f"❌ Не удалось отправить сообщение в чат {chat_id} через ни одного бота")
    if on_inaccessible and last_error and _is_permanent_send_error(last_error):
        try:
            on_inaccessible(chat_id)
        except Exception as cb_err:
            logger.warning(f"Ошибка в on_inaccessible: {cb_err}")
    return False

# Конфигурация для работы с большим количеством чатов (оптимизированная)
SCHEDULER_CONFIG = {
    # Задержки между отправками (в секундах) - уменьшены для ускорения
    'STICKER_DELAY_BASE': float(os.getenv('STICKER_DELAY_BASE', '0.1')),        # Базовая задержка между стикерами
    'STICKER_DELAY_10': float(os.getenv('STICKER_DELAY_10', '0.5')),          # Задержка каждые 10 чатов
    'STICKER_DELAY_50': float(os.getenv('STICKER_DELAY_50', '1.0')),          # Задержка каждые 50 чатов
    
    'INFO_DELAY_BASE': float(os.getenv('INFO_DELAY_BASE', '0.05')),           # Базовая задержка между информацией
    'INFO_DELAY_20': float(os.getenv('INFO_DELAY_20', '0.5')),             # Задержка каждые 20 чатов
    
    'RESET_DELAY_BASE': float(os.getenv('RESET_DELAY_BASE', '0.01')),          # Базовая задержка между сбросами
    'RESET_DELAY_50': float(os.getenv('RESET_DELAY_50', '0.2')),            # Задержка каждые 50 баз
    
    # Количество повторных попыток - уменьшено
    'MAX_RETRY_ATTEMPTS': int(os.getenv('MAX_RETRY_ATTEMPTS', '2')),
    
    # Задержки при ошибках (в секундах) - уменьшены
    'ERROR_DELAY_SHORT': float(os.getenv('ERROR_DELAY_SHORT', '2')),           # Короткая задержка при ошибке
    'ERROR_DELAY_LONG': float(os.getenv('ERROR_DELAY_LONG', '10')),           # Длинная задержка при превышении лимитов
}

async def send_daily_info_if_receipts():
    """Отправляет информацию о чеках за день, если был добавлен хотя бы один чек"""
    start_time = datetime.now()
    logger.info("🚀 Запуск функции send_daily_info_if_receipts")

    today = datetime.now().strftime('%Y-%m-%d')

    global bot_cache
    logger.info("🧹 Кэш ботов сохранен для оптимизации")

    try:
        logger.info("📊 Начинаем отправку ежедневной информации по всем чатам")
        print("[📊] Начинаем отправку ежедневной информации по всем чатам...")

        chat_ids = list_group_chat_ids()
        total_chats = len(chat_ids)

        logger.info(f"📊 Всего чатов для проверки: {total_chats}")
        print(f"[📊] Всего чатов для проверки: {total_chats}")

        successful_sends = 0
        failed_sends = 0
        chats_with_receipts = 0

        for i, chat_id in enumerate(chat_ids, 1):
            try:
                initialize_db(chat_id)
                receipts_today = count_receipts_on_local_date(chat_id, today)
                logger.info(f"📊 Чат {chat_id}: найдено чеков за сегодня: {receipts_today}")

                if receipts_today > 0:
                    chats_with_receipts += 1
                    logger.info(f"📤 Отправляем ежедневную информацию в чат {chat_id} (чеков: {receipts_today})")
                    print(f"[📤] [{i}/{total_chats}] Отправляем ежедневную информацию в чат {chat_id} (чеков за день: {receipts_today})")

                    snapshot = build_info_snapshot(chat_id, today)
                    if snapshot is None:
                        logger.error(f"❌ Чат {chat_id}: нет настроек в базе данных")
                        failed_sends += 1
                        print(f"[❌] [{i}/{total_chats}] Нет настроек для чата {chat_id}")
                        continue

                    response = format_info_message_html(snapshot, daily_report=True)
                    logger.info(f"📤 Чат {chat_id}: начинаем отправку сообщения (длина: {len(response)} символов)")
                    success = await send_message_optimized(chat_id, response, parse_mode="HTML")

                    if success:
                        successful_sends += 1
                        logger.info(f"✅ Успешно отправлена информация в чат {chat_id}")
                        print(f"[✅] [{i}/{total_chats}] Информация отправлена в чат {chat_id}")
                    else:
                        failed_sends += 1
                        logger.error(f"❌ Не удалось отправить информацию в чат {chat_id} через оба бота")
                        print(f"[❌] [{i}/{total_chats}] Не удалось отправить информацию в чат {chat_id}")
                else:
                    logger.debug(f"⏭️ Чат {chat_id}: нет чеков за сегодня, пропускаем")

                if i < total_chats:
                    delay = SCHEDULER_CONFIG['INFO_DELAY_BASE']
                    if i % 20 == 0:
                        delay = SCHEDULER_CONFIG['INFO_DELAY_20']
                        logger.info(f"⏸️ Пауза {delay} сек после {i} чатов")
                        print(f"[⏸️] Пауза {delay} сек после {i} чатов...")

                    await asyncio.sleep(delay)

            except Exception as e:
                failed_sends += 1
                logger.error(f"💥 Критическая ошибка при обработке чата {chat_id}:")
                log_error_details(logger.error, e)
                print(f"[!] Критическая ошибка при обработке чата {chat_id}: {e}")
                continue

        await send_daily_anonymous_info_if_receipts()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info(f"⏱️ Время выполнения функции: {duration:.2f} секунд")
        logger.info(f"📊 Итоговая статистика: успешно: {successful_sends}, ошибок: {failed_sends}, чатов с чеками: {chats_with_receipts}")
        success_rate = (successful_sends / total_chats * 100) if total_chats > 0 else 0
        result_msg = (
            f"✅ Ежедневная информация обработана! Успешно: {successful_sends}, Ошибок: {failed_sends}, "
            f"Чатов с чеками: {chats_with_receipts}, Всего: {total_chats}, Успешность: {success_rate:.1f}%, "
            f"Время выполнения: {duration:.2f} сек"
        )
        logger.info(result_msg)
        print(f"[{result_msg}]")

    except Exception as e:
        error_msg = f"💥 Критическая ошибка в send_daily_info_if_receipts: {e}"
        logger.error(error_msg)
        logger.exception("Полный стек ошибки:")
        print(f"[{error_msg}]")


async def send_daily_anonymous_info_if_receipts():
    """Ежедневный отчёт по анонимным комнатам: каждому участнику в ЛС (дочерний бот, если задан)."""
    start_time = datetime.now()
    logger.info("🚀 Запуск send_daily_anonymous_info_if_receipts")
    today = anonymous_today_msk_date_str()
    try:
        room_ids = list_active_anonymous_room_ids()
        total_rooms = len(room_ids)
        successful_member_sends = 0
        failed_member_sends = 0
        rooms_with_receipts = 0
        for j, room_id in enumerate(room_ids, 1):
            try:
                n = count_anonymous_receipts_today(room_id, today)
                if n <= 0:
                    continue
                rooms_with_receipts += 1
                snapshot = build_anonymous_info_snapshot(room_id, today)
                if snapshot is None:
                    logger.warning(f"Анонимная комната {room_id}: нет снимка (неактивна?)")
                    continue
                response = format_anonymous_info_html(snapshot, daily_report=True)
                members = list_member_telegram_ids_for_room(room_id)
                if not members:
                    logger.warning(f"Анонимная комната {room_id}: нет участников для рассылки")
                    continue
                child_token = get_child_bot_token(room_id)
                if not child_token:
                    logger.warning(
                        "Анонимная комната %s: нет дочернего бота — ежедневный отчёт в ЛС не отправляем "
                        "(анонимные чаты только через отдельного бота).",
                        room_id,
                    )
                    continue
                child = AiogramBot(token=child_token)
                try:
                    for uid in members:
                        try:
                            await child.send_message(uid, response, parse_mode="HTML")
                            successful_member_sends += 1
                        except Exception as e:
                            failed_member_sends += 1
                            logger.warning(
                                f"Аноним {room_id}: не отправлено пользователю {uid} (child): {e}"
                            )
                        await asyncio.sleep(SCHEDULER_CONFIG["INFO_DELAY_BASE"])
                finally:
                    await child.session.close()
                if j < total_rooms:
                    await asyncio.sleep(SCHEDULER_CONFIG["INFO_DELAY_BASE"])
            except Exception as e:
                logger.error(f"💥 Ошибка анонимной комнаты {room_id}:")
                log_error_details(logger.error, e)
                continue
        duration = (datetime.now() - start_time).total_seconds()
        logger.info(
            f"📊 Анонимные ежедневные отчёты: комнат с чеками={rooms_with_receipts}, "
            f"отправок ок={successful_member_sends}, ошибок={failed_member_sends}, "
            f"время={duration:.2f} с"
        )
    except Exception as e:
        logger.error(f"💥 Критическая ошибка в send_daily_anonymous_info_if_receipts: {e}")
        logger.exception("Полный стек:")


async def send_morning_sticker():
    """Отправляет стикер во все чаты в 7 утра с задержками и повторными попытками"""
    start_time = datetime.now()

    global bot_cache
    logger.info("🧹 Кэш ботов сохранен для оптимизации")

    try:
        logger.info("🌅 Начинаем отправку утреннего стикера во все чаты")
        print("[🌅] Отправляем утренний стикер во все чаты...")

        message_text = "CAACAgIAAxkBAAKQkGigjQSfa96fJoGphBQT_N7mVtfSAALGewAC3t_ASP0jBidiRz_UNgQ"

        chat_ids = list_group_chat_ids()
        total_chats = len(chat_ids)

        logger.info(f"📊 Всего чатов для отправки сообщения: {total_chats}")
        print(f"[📊] Всего чатов для отправки: {total_chats}")

        successful_sends = 0
        failed_sends = 0

        for i, chat_id in enumerate(chat_ids, 1):
            try:
                success = await send_message_optimized(chat_id, message_text, is_sticker=True)

                if success:
                    successful_sends += 1
                    logger.info(f"✓ [{i}/{total_chats}] Сообщение успешно отправлено в чат {chat_id}")
                    print(f"[✓] [{i}/{total_chats}] Сообщение отправлено в чат {chat_id}")
                else:
                    failed_sends += 1
                    logger.error(f"❌ [{i}/{total_chats}] Не удалось отправить сообщение в чат {chat_id} через оба бота")
                    print(f"[❌] [{i}/{total_chats}] Не удалось отправить сообщение в чат {chat_id}")

                if i < total_chats:
                    delay = SCHEDULER_CONFIG['STICKER_DELAY_BASE']
                    if i % 10 == 0:
                        delay = SCHEDULER_CONFIG['STICKER_DELAY_10']
                    if i % 50 == 0:
                        delay = SCHEDULER_CONFIG['STICKER_DELAY_50']
                        logger.info(f"⏸️ Пауза {delay} сек после {i} чатов...")
                        print(f"[⏸️] Пауза {delay} сек после {i} чатов...")

                    await asyncio.sleep(delay)

            except Exception as e:
                failed_sends += 1
                logger.error(f"💥 Критическая ошибка при обработке чата {chat_id}:")
                log_error_details(logger.error, e)
                print(f"[!] Критическая ошибка при обработке чата {chat_id}: {e}")
                continue

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        success_rate = (successful_sends / total_chats * 100) if total_chats > 0 else 0
        result_msg = (
            f"✅ Утренний стикер отправлен! Успешно: {successful_sends}, Ошибок: {failed_sends}, "
            f"Всего: {total_chats}, Успешность: {success_rate:.1f}%, Время выполнения: {duration:.2f} сек"
        )
        logger.info(result_msg)
        print(f"[{result_msg}]")

    except Exception as e:
        error_msg = f"! Критическая ошибка в send_morning_sticker: {e}"
        logger.error(error_msg)
        print(f"[{error_msg}]")


async def reset_all_databases():
    """Автоматически сбрасывает все базы данных в полночь с задержками"""
    start_time = datetime.now()
    try:
        logger.info("🔄 Выполняем автоматический сброс всех баз данных")
        print("[🔄] Выполняем автоматический сброс всех баз данных...")

        chat_ids = list_group_chat_ids()
        total_chats = len(chat_ids)

        logger.info(f"📊 Всего баз данных для сброса: {total_chats}")
        print(f"[📊] Всего баз данных для сброса: {total_chats}")

        successful_resets = 0
        failed_resets = 0

        for i, chat_id in enumerate(chat_ids, 1):
            try:
                initialize_db(chat_id)
                reset_group_data(chat_id)

                successful_resets += 1
                print(f"[✅] [{i}/{total_chats}] База данных для чата {chat_id} сброшена")

                if i < total_chats:
                    delay = SCHEDULER_CONFIG['RESET_DELAY_BASE']
                    if i % 50 == 0:
                        delay = SCHEDULER_CONFIG['RESET_DELAY_50']
                        print(f"[⏸️] Пауза {delay} сек после {i} баз данных...")

                    await asyncio.sleep(delay)

            except Exception as e:
                failed_resets += 1
                logger.error(f"💥 Ошибка при сбросе БД для чата {chat_id}:")
                log_error_details(logger.error, e)
                print(f"[❌] [{i}/{total_chats}] Ошибка при сбросе БД для чата {chat_id}: {e}")
                continue

        anonymous_room_ids = list_active_anonymous_room_ids()
        total_anon = len(anonymous_room_ids)
        anon_ok = 0
        anon_fail = 0
        logger.info(f"📊 Сброс чеков анонимных комнат: {total_anon} шт.")
        for k, room_id in enumerate(anonymous_room_ids, 1):
            try:
                reset_anonymous_receipts_for_room(room_id)
                anon_ok += 1
                if k < total_anon:
                    delay = SCHEDULER_CONFIG["RESET_DELAY_BASE"]
                    if k % 50 == 0:
                        delay = SCHEDULER_CONFIG["RESET_DELAY_50"]
                    await asyncio.sleep(delay)
            except Exception as e:
                anon_fail += 1
                logger.error(f"💥 Сброс анонимных чеков для комнаты {room_id}:")
                log_error_details(logger.error, e)
                continue

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        result_msg = (
            f"✅ Автоматический сброс всех баз данных завершён! Группы: успешно {successful_resets}, "
            f"ошибок {failed_resets}, всего {total_chats}; анонимные комнаты: успешно {anon_ok}, "
            f"ошибок {anon_fail}, всего {total_anon}; время {duration:.2f} сек"
        )
        logger.info(result_msg)
        print(f"[{result_msg}]")

    except Exception as e:
        error_msg = f"! Критическая ошибка в reset_all_databases: {e}"
        logger.error(error_msg)
        print(f"[{error_msg}]")


async def test_daily_info_sending(limit=5):
    """Тестирует отправку ежедневной информации в ограниченное количество чатов"""
    try:
        print(f"[🧪] Тестируем отправку ежедневной информации в первые {limit} чатов...")

        all_ids = list_group_chat_ids()
        test_chats = all_ids[:limit]
        total_test_chats = len(test_chats)

        print(f"[📊] Тестируем в {total_test_chats} чатах из {len(all_ids)} доступных")

        successful_sends = 0
        failed_sends = 0
        chats_with_receipts = 0
        today = datetime.now().strftime('%Y-%m-%d')

        for i, chat_id in enumerate(test_chats, 1):
            try:
                initialize_db(chat_id)
                receipts_today = count_receipts_on_local_date(chat_id, today)
                print(f"[📊] Чат {chat_id}: найдено чеков за сегодня: {receipts_today}")

                if receipts_today > 0:
                    chats_with_receipts += 1
                    print(f"[📤] [{i}/{total_test_chats}] Отправляем ежедневную информацию в чат {chat_id} (чеков: {receipts_today})")

                    test_message = (
                        f"📅 Тестовый ежедневный отчёт за {datetime.now().strftime('%d.%m.%Y')}\n\n"
                        f"Чеков за сегодня: {receipts_today}"
                    )

                    success = await send_message_optimized(chat_id, test_message, parse_mode="HTML")

                    if success:
                        successful_sends += 1
                        print(f"[✅] [{i}/{total_test_chats}] Тестовое сообщение отправлено в чат {chat_id}")
                    else:
                        failed_sends += 1
                        print(f"[❌] [{i}/{total_test_chats}] Не удалось отправить тестовое сообщение в чат {chat_id}")
                else:
                    print(f"[⏭️] [{i}/{total_test_chats}] Чат {chat_id}: нет чеков за сегодня, пропускаем")

                if i < total_test_chats:
                    await asyncio.sleep(1.0)

            except Exception as e:
                failed_sends += 1
                print(f"[❌] [{i}/{total_test_chats}] Ошибка при тестовой отправке в чат {chat_id}:")
                log_error_details(print, e)
                continue

        success_rate = (successful_sends / total_test_chats * 100) if total_test_chats > 0 else 0
        print(
            f"[🧪] Тест завершен! Успешно: {successful_sends}, Ошибок: {failed_sends}, "
            f"Чатов с чеками: {chats_with_receipts}, Успешность: {success_rate:.1f}%"
        )

    except Exception as e:
        print(f"[!] Ошибка в test_daily_info_sending: {e}")

def clear_group_cache(chat_id):
    """Очищает кэш для конкретной группы"""
    global bot_cache
    if chat_id in bot_cache:
        del bot_cache[chat_id]
        print(f"🧹 Кэш для группы {chat_id} очищен")
    else:
        print(f"ℹ️ Кэш для группы {chat_id} не найден")

async def check_bot_status_in_group(chat_id):
    """Проверяет статус обоих ботов в указанной группе"""
    try:
        print(f"🔍 Проверяем статус ботов в группе {chat_id}...")

        bots = [bot]
        bot_names = ["bot"]

        for i, bot_instance in enumerate(bots):
            try:
                bot_info = await bot_instance.get_me()
                chat_member = await bot_instance.get_chat_member(chat_id, bot_info.id)

                print(f"📊 {bot_names[i]} (@{bot_info.username}, ID: {bot_info.id}):")
                print(f"   Статус в группе: {chat_member.status}")

                can_send_messages = getattr(chat_member, 'can_send_messages', None)
                can_send_media = getattr(chat_member, 'can_send_media_messages', None)

                print(f"   Может отправлять сообщения: {can_send_messages if can_send_messages is not None else 'N/A'}")
                print(f"   Может отправлять медиа: {can_send_media if can_send_media is not None else 'N/A'}")

                try:
                    test_msg = f"🧪 Тестовое сообщение от {bot_names[i]}"
                    await bot_instance.send_message(chat_id, test_msg)
                    print(f"   ✅ Тестовая отправка: УСПЕШНО")
                except Exception as send_error:
                    print(f"   ❌ Тестовая отправка: ОШИБКА - {send_error}")

            except Exception as e:
                print(f"❌ {bot_names[i]}: Ошибка при проверке - {e}")

    except Exception as e:
        print(f"💥 Общая ошибка при проверке группы {chat_id}: {e}")

async def test_sticker_sending(limit=10):
    """Тестирует отправку стикеров в ограниченное количество чатов"""
    try:
        print(f"[🧪] Тестируем отправку стикеров в первые {limit} чатов...")

        sticker_id = "CAACAgIAAxkBAAKQkGigjQSfa96fJoGphBQT_N7mVtfSAALGewAC3t_ASP0jBidiRz_UNgQ"

        all_ids = list_group_chat_ids()
        test_chats = all_ids[:limit]
        total_test_chats = len(test_chats)

        print(f"[📊] Тестируем в {total_test_chats} чатах из {len(all_ids)} доступных")

        successful_sends = 0
        failed_sends = 0

        for i, chat_id in enumerate(test_chats, 1):
            try:
                success = await send_message_optimized(chat_id, sticker_id, is_sticker=True)

                if success:
                    successful_sends += 1
                    print(f"[✅] [{i}/{total_test_chats}] Тестовый стикер отправлен в чат {chat_id}")
                else:
                    failed_sends += 1
                    print(f"[❌] [{i}/{total_test_chats}] Не удалось отправить тестовый стикер в чат {chat_id}")

                if i < total_test_chats:
                    await asyncio.sleep(1.0)

            except Exception as e:
                failed_sends += 1
                print(f"[❌] [{i}/{total_test_chats}] Ошибка при тестовой отправке в чат {chat_id}:")
                log_error_details(print, e)
                continue

        print(f"[🧪] Тест завершен! Успешно: {successful_sends}, Ошибок: {failed_sends}")

    except Exception as e:
        print(f"[!] Ошибка в test_sticker_sending: {e}")

async def send_afternoon_dot():
    """Отправляет точку во все чаты в 16:15 с задержками и повторными попытками"""
    start_time = datetime.now()

    global bot_cache
    logger.info("🧹 Кэш ботов сохранен для оптимизации")

    try:
        logger.info("🌤️ Начинаем отправку дневной точки во все чаты")
        print("[🌤️] Отправляем дневную точку во все чаты...")

        message_text = "."

        chat_ids = list_group_chat_ids()
        total_chats = len(chat_ids)

        logger.info(f"📊 Всего чатов для отправки сообщения: {total_chats}")
        print(f"[📊] Всего чатов для отправки: {total_chats}")

        successful_sends = 0
        failed_sends = 0

        for i, chat_id in enumerate(chat_ids, 1):
            try:
                success = await send_message_optimized(chat_id, message_text)

                if success:
                    successful_sends += 1
                    logger.info(f"✓ [{i}/{total_chats}] Сообщение успешно отправлено в чат {chat_id}")
                    print(f"[✓] [{i}/{total_chats}] Сообщение отправлено в чат {chat_id}")
                else:
                    failed_sends += 1
                    logger.error(f"❌ [{i}/{total_chats}] Не удалось отправить сообщение в чат {chat_id}")
                    print(f"[❌] [{i}/{total_chats}] Не удалось отправить сообщение в чат {chat_id}")

                if i < total_chats:
                    delay = SCHEDULER_CONFIG['STICKER_DELAY_BASE']
                    if i % 10 == 0:
                        delay = SCHEDULER_CONFIG['STICKER_DELAY_10']
                    if i % 50 == 0:
                        delay = SCHEDULER_CONFIG['STICKER_DELAY_50']
                        logger.info(f"⏸️ Пауза {delay} сек после {i} чатов...")
                        print(f"[⏸️] Пауза {delay} сек после {i} чатов...")

                    await asyncio.sleep(delay)

            except Exception as e:
                failed_sends += 1
                logger.error(f"💥 Критическая ошибка при обработке чата {chat_id}:")
                log_error_details(logger.error, e)
                print(f"[!] Критическая ошибка при обработке чата {chat_id}: {e}")
                continue

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        success_rate = (successful_sends / total_chats * 100) if total_chats > 0 else 0
        result_msg = (
            f"✅ Дневная точка отправлена! Успешно: {successful_sends}, Ошибок: {failed_sends}, "
            f"Всего: {total_chats}, Успешность: {success_rate:.1f}%, Время выполнения: {duration:.2f} сек"
        )
        logger.info(result_msg)
        print(f"[{result_msg}]")

    except Exception as e:
        error_msg = f"! Критическая ошибка в send_afternoon_dot: {e}"
        logger.error(error_msg)
        print(f"[{error_msg}]")


async def purge_stale_anonymous_chat_data_job():
    """Почасовая очистка истории и служебных таблиц анонимных чатов (старше 48 ч)."""
    try:
        stats = await purge_stale_anonymous_chat_data_with_telegram(bot, retention_hours=48)
        total = sum(stats.values())
        if total:
            logger.info(
                "🧹 purge_stale_anonymous_chat_data_with_telegram: удалено всего строк: %s (%s)",
                total,
                stats,
            )
    except Exception as e:
        logger.exception("Ошибка purge_stale_anonymous_chat_data_with_telegram: %s", e)


def setup_scheduler():
    scheduler = AsyncIOScheduler(timezone=timezone("UTC"))

    scheduler.add_job(
        func=reset_all_databases,
        trigger=CronTrigger(hour=23, minute=59),  # 23:59 UTC
        name="daily_reset_all_databases"
    )
    
    scheduler.add_job(
        func=send_daily_info_if_receipts,
        trigger=CronTrigger(hour=21, minute=30),  # 21:30 UTC
        name="daily_info_send"
    )
    
    scheduler.add_job(
        func=send_morning_sticker,
        trigger=CronTrigger(hour=6, minute=50),  # 6:50 UTC
        name="morning_sticker_send"
    )

    scheduler.add_job(
        func=purge_stale_anonymous_chat_data_job,
        trigger=IntervalTrigger(hours=1),
        name="purge_anonymous_chat_stale_48h",
    )
    
    # send_afternoon_dot - тестовая функция, не регистрируем в планировщике

    scheduler.start()
    logger.info("✓ Планировщик автоматического сброса баз данных запущен в 23:59 UTC")
    logger.info("✓ Планировщик ежедневной отправки информации запущен в 21:30 UTC")
    logger.info("✓ Планировщик утреннего стикера запущен в 6:50 UTC")
    logger.info("✓ Планировщик очистки анонимных чатов (>48ч) — каждый час")
    print("[✓] Планировщик автоматического сброса баз данных запущен в 23:59 UTC")
    print("[✓] Планировщик ежедневной отправки информации запущен в 21:30 UTC")
    print("[✓] Планировщик утреннего стикера запущен в 6:50 UTC")
    print("[✓] Планировщик очистки анонимных чатов (>48ч) — каждый час")
