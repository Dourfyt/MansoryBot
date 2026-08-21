"""Тексты бота Mansory: единый тон, кастомные emoji, HTML."""
from __future__ import annotations

from .custom_emojis import (
    e_bars,
    e_cash,
    e_chart_down,
    e_chart_up,
    e_money_bag,
    e_money_face,
    e_payout,
    e_prohibited,
    e_receipt,
    e_ring,
    e_today_badge,
)

SEP = "━━━━━━━━━━━━━━━━"
MONEY_DECIMAL_PLACES = 3

CHEK_FORMAT_HINT = (
    "Некорректный формат.\n"
    "Примеры: /чек 1000 · /+ 1к · /- 500 · /чек 1к 93.5 10"
)

# обратная совместимость импортов
CHEK_AMOUNT_FORMAT_HINT = CHEK_FORMAT_HINT


def format_money(amount: float | int, *, decimals: int = MONEY_DECIMAL_PLACES) -> str:
    """Сумма с разделением разрядов точками; лишние нули в дробной части убираются."""
    n = float(amount)
    negative = n < 0
    n = abs(n)
    s = f"{n:.{decimals}f}"
    if "." in s:
        int_part, frac_part = s.split(".", 1)
        frac_part = frac_part.rstrip("0")
    else:
        int_part, frac_part = s, ""
    chunks: list[str] = []
    while int_part:
        chunks.append(int_part[-3:])
        int_part = int_part[:-3]
    int_grouped = ".".join(reversed(chunks)) if chunks else "0"
    if frac_part:
        body = f"{int_grouped},{frac_part}"
    else:
        body = int_grouped
    return f"−{body}" if negative else body

# —— Кнопки ——
BTN_CONFIRM = "Принять чек"
BTN_FAKE = "Отклонить"
BTN_YES = "Да, фейк"
BTN_NO = "Отмена"
CAPTION_VERIFY = "Проверьте чек и выберите действие"
LBL_VERIFIED = "Проверено"
LBL_VERIFIED_FAKE = "Отклонён · фейк"
LBL_CONFIRM_FAKE = "Подтвердить отклонение?"


def stop_rek_body() -> str:
    return "по этим реквизитам переводы приостановлены — дождитесь следующего сигнала."


def daily_report_header_html() -> str:
    """Заголовок ежедневной рассылки: ⭐ Сводка · бейдж «Сегодня»."""
    return f"{e_bars()} <b>Сводка ·</b> {e_today_badge()}\n\n"


def intermediate_report_header_html() -> str:
    """Заголовок промежуточной рассылки (13:00 / 18:00 МСК)."""
    return f"{e_bars()} <b>Промежуточный итог ·</b> {e_today_badge()}\n\n"


def info_receipt_block(
    receipt_no: int,
    ts_fmt: str,
    amount: float,
    *,
    rate: float | None = None,
    percent: float | None = None,
    payout: float | None = None,
    rate_missing: bool = False,
) -> str:
    lines = [
        f"{e_receipt()} <b>Чек №{receipt_no}</b>  ·  <i>{ts_fmt}</i>",
        f"{e_money_face()} <b>{format_money(amount)}</b>",
    ]
    if rate_missing:
        lines.append(f"{e_prohibited()} <i>Курс не задан</i>")
    elif rate is not None:
        lines.append(f"{e_ring()} Курс <b>{rate}</b>")
    if percent is not None:
        lines.append(f"{e_chart_down()} Удержание <b>{percent}%</b>")
    elif rate_missing:
        lines.append(f"{e_chart_down()} Удержание <b>—</b>")
    if payout is not None:
        lines.append(f"{e_payout()} К выплате <b>{format_money(payout)}</b>")
    lines.append(SEP)
    return "\n".join(lines)


def info_footer(
    *,
    rate_s: str,
    pct_s: str,
    sums: str,
    turnover: float,
    total_to_pay: float,
    paid: float,
    remaining: float,
) -> str:
    return (
        f"{e_chart_up()} Настройки чата: курс <b>{rate_s}</b>, удержание <b>{pct_s}%</b>\n"
        f"{e_bars()} Сумма чеков: <b>{sums}</b>\n"
        f"{e_chart_up()} Оборот за день: <b>{format_money(turnover)}</b>\n"
        f"{e_payout()} К выплате: <b>{format_money(total_to_pay)}</b>\n"
        f"{e_cash()} Выплачено: <b>{format_money(paid)}</b>\n"
        f"{e_money_bag()} Остаток: <b>{format_money(remaining)}</b>"
    )


def anon_receipt_line(receipt_no: int, ts_fmt: str, nick: str, amount: float) -> str:
    return (
        f"{e_receipt()} <b>№{receipt_no}</b>  ·  <i>{ts_fmt}</i>\n"
        f"👤 {nick}\n"
        f"{e_money_face()} <b>{format_money(amount)}</b>\n"
        f"{SEP}"
    )


# —— Справка и приветствия ——
def help_client_html(bot_name: str) -> str:
    return (
        f"<b>{bot_name}</b>\n{SEP}\n\n"
        f"{e_receipt()} <b>Клиентская группа</b>\n\n"
        f"<code>/п</code> — фото чека на проверку\n"
        f"<code>/инфо</code> — сводка\n"
        f"<code>/помощь</code> — справка\n\n"
        f"<b>Как это работает</b>\n"
        f"1. Фото + <code>/п</code>\n"
        f"2. Чек у проверяющих\n"
        f"3. Уведомление сюда после проверки"
    )


def help_verifier_html(bot_name: str) -> str:
    return (
        f"<b>{bot_name}</b>\n{SEP}\n\n"
        f"{e_chart_up()} <b>Группа проверяющих</b>\n\n"
        f"Кнопки <b>{BTN_CONFIRM}</b> и <b>{BTN_FAKE}</b> под фото\n"
        f"<code>/чек</code> · <code>/+</code> · <code>/-</code> — сумма после принятия\n"
        f"<code>/инфо</code> · <code>/помощь</code>\n\n"
        f"<b>Порядок</b>\n"
        f"1. {BTN_CONFIRM}\n"
        f"2. <code>/чек 1,5к</code> · <code>/чек 1к 93.5 10</code>\n"
        f"3. Или {BTN_FAKE}"
    )


def help_general_html() -> str:
    return (
        f"<b>Команды Mansory</b>\n{SEP}\n\n"
        f"<code>/чек</code> · <code>/+</code> · <code>/-</code> — чек "
        f"(<code>/чек 1к 93.5 10</code> — с курсом и %)\n"
        f"<code>/выплата</code> — выплата <i>(админ)</i>\n"
        f"<code>/инфо</code> — баланс\n"
        f"<code>/чеки_сегодня</code> — выгрузка\n"
        f"<code>/дефолт</code> · <code>/пкп</code> <i>(админ)</i>\n"
        f"<code>/отвязать_курс</code> · <code>/отвязать_процент</code>\n"
        f"<code>/сброс</code> · <code>/удалить_чек</code> <i>(админ)</i>\n"
        f"<code>/помощь</code> — справка"
    )


def start_client_html(bot_name: str) -> str:
    return (
        f"{e_chart_up()} <b>{bot_name}</b>\n\n"
        f"Группа клиентов подключена.\n"
        f"Фото с <code>/п</code> — на проверку."
    )


def start_verifier_html(bot_name: str) -> str:
    return (
        f"{e_chart_up()} <b>{bot_name}</b>\n\n"
        f"Группа проверяющих активна.\n"
        f"Кнопки под фото или <code>/чек</code>."
    )


def start_generic_html() -> str:
    return f"{e_ring()} <b>Mansory</b> готов в этом чате."


def prompt_check_amount_html() -> str:
    return (
        f"{e_money_bag()} <b>Сумма чека</b>\n\n"
        f"<code>/чек {format_money(1500.5)}</code>\n"
        f"<i>Дробная часть через точку</i>"
    )


# —— Анонимный чат ——
ANON_HELP_HTML = (
    f"<b>Команды комнаты</b>\n{SEP}\n\n"
    f"<code>/delete</code> — убрать последнее сообщение\n"
    f"<code>/инфо</code> — сводка\n"
    f"<code>/чеки_сегодня</code> — файл за день\n"
    f"<code>/помощь</code> — справка"
)

ANON_NICK_PROMPT = (
    f"{e_ring()} <b>Имя в чате</b>\n\n"
    f"Его увидят участники.\n"
    f"Выберите вариант или «Другие варианты»."
)
