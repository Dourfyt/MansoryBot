"""Кастомные Telegram emoji Mansory (порядок как в наборе бота)."""
from __future__ import annotations

# ID из @BotFather / custom emoji pack
EMOJI_RECEIPT_ID = "5204242830687494041"  # 🧾 терминал
EMOJI_MONEY_FACE_ID = "5193052409361871390"  # 🤑
EMOJI_PROHIBITED_ID = "5877477244938489129"  # 🚫
EMOJI_CHART_DOWN_ID = "5348354617149240696"  # 📉
EMOJI_RING_ID = "5778311685638984859"  # 🔘
EMOJI_BARS_ID = "5433939180621154625"  # ⭐
EMOJI_CHART_UP_ID = "5431603852283487944"  # 🌸
EMOJI_PAYOUT_ID = "5201873447554145566"  # К выплате (чек / инфо)
EMOJI_CASH_ID = "5303404047775057142"  # 👍 пачка купюр
EMOJI_MONEY_BAG_ID = "5224257782013769471"  # 💰
EMOJI_TODAY_1_ID = "5192707317329575611"  # «Се…» бейдж «Сегодня»
EMOJI_TODAY_2_ID = "5192964774849165242"  # «…годня»

PH_RECEIPT = "🧾"
PH_MONEY_FACE = "🤑"
PH_PROHIBITED = "🚫"
PH_CHART_DOWN = "📉"
PH_RING = "🔘"
PH_BARS = "⭐"
PH_CHART_UP = "🌸"
PH_PAYOUT = "💸"
PH_CASH = "👍"
PH_MONEY_BAG = "💰"
# Один символ на тег (требование Telegram для custom emoji в HTML)
PH_TODAY_1 = "🔤"
PH_TODAY_2 = "📅"

# Кнопки и префиксы сообщений (aiogram CustomEmoji / icon_custom_emoji_id)
CONFIRM_RECEIPT_CUSTOM_EMOJI_ID = EMOJI_CASH_ID
FAKE_RECEIPT_CUSTOM_EMOJI_ID = EMOJI_PROHIBITED_ID
CROSS_CUSTOM_EMOJI_ID = EMOJI_PROHIBITED_ID
PAYOUT_OK_CUSTOM_EMOJI_ID = EMOJI_MONEY_BAG_ID
STOP_REK_CUSTOM_EMOJI_ID = EMOJI_PROHIBITED_ID
MSG_OK_CUSTOM_EMOJI_ID = EMOJI_CHART_UP_ID
MSG_ERR_CUSTOM_EMOJI_ID = EMOJI_PROHIBITED_ID


def tg_emoji_html(emoji_id: str, placeholder: str) -> str:
    """HTML для parse_mode=HTML (Bot API 7+)."""
    return f'<tg-emoji emoji-id="{emoji_id}">{placeholder}</tg-emoji>'


def e_receipt() -> str:
    return tg_emoji_html(EMOJI_RECEIPT_ID, PH_RECEIPT)


def e_money_face() -> str:
    return tg_emoji_html(EMOJI_MONEY_FACE_ID, PH_MONEY_FACE)


def e_prohibited() -> str:
    return tg_emoji_html(EMOJI_PROHIBITED_ID, PH_PROHIBITED)


def e_chart_down() -> str:
    return tg_emoji_html(EMOJI_CHART_DOWN_ID, PH_CHART_DOWN)


def e_ring() -> str:
    return tg_emoji_html(EMOJI_RING_ID, PH_RING)


def e_bars() -> str:
    return tg_emoji_html(EMOJI_BARS_ID, PH_BARS)


def e_chart_up() -> str:
    return tg_emoji_html(EMOJI_CHART_UP_ID, PH_CHART_UP)


def e_payout() -> str:
    return tg_emoji_html(EMOJI_PAYOUT_ID, PH_PAYOUT)


def e_cash() -> str:
    return tg_emoji_html(EMOJI_CASH_ID, PH_CASH)


def e_money_bag() -> str:
    return tg_emoji_html(EMOJI_MONEY_BAG_ID, PH_MONEY_BAG)


def e_today_badge() -> str:
    """Бейдж «Сегодня» (два кастомных emoji подряд, как в Telegram)."""
    return tg_emoji_html(EMOJI_TODAY_1_ID, PH_TODAY_1) + tg_emoji_html(
        EMOJI_TODAY_2_ID, PH_TODAY_2
    )


def plain_receipt_prefix() -> str:
    """Плейсхолдер для plain-текста / истории в БД."""
    return PH_RECEIPT
