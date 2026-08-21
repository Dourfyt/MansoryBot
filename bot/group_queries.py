"""Операции с данными группы в PostgreSQL (раньше — отдельный SQLite-файл на chat_id)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from . import ui_copy as ui
from .ui_copy import MONEY_DECIMAL_PLACES, format_money
from .pg import connection

_UTC = ZoneInfo("UTC")
_MSK = ZoneInfo("Europe/Moscow")


def get_default_rate_ids(chat_id: int) -> Tuple[Optional[int], Optional[int]]:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT default_exchange_rate_id, default_retention_rate_id
            FROM group_settings WHERE chat_id = %s
            """,
            (chat_id,),
        )
        row = cur.fetchone()
        if not row:
            return None, None
        return row[0], row[1]


def insert_receipt(
    chat_id: int,
    amount: float,
    exchange_rate_id: Optional[int],
    retention_rate_id: Optional[int],
    ts: str,
) -> None:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(MAX(receipt_no), 0) + 1 FROM receipts WHERE chat_id = %s",
            (chat_id,),
        )
        row = cur.fetchone()
        next_no = int(row[0]) if row and row[0] is not None else 1
        cur.execute(
            """
            INSERT INTO receipts (chat_id, receipt_no, amount, exchange_rate_id, retention_rate_id, ts)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (chat_id, next_no, amount, exchange_rate_id, retention_rate_id, ts),
        )


def update_trader_rate(chat_id: int, rate: float) -> None:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE group_settings SET trader_rate = %s WHERE chat_id = %s",
            (rate, chat_id),
        )


def delete_receipt(chat_id: int, receipt_no: int) -> int:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM receipts WHERE chat_id = %s AND receipt_no = %s",
            (chat_id, receipt_no),
        )
        return cur.rowcount


def insert_payout(chat_id: int, amount: float, ts: str) -> None:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO payouts (chat_id, amount, ts) VALUES (%s, %s, %s)",
            (chat_id, amount, ts),
        )


def resolve_receipt_rate_ids(
    chat_id: int,
    rate_value: Optional[float],
    percent_value: Optional[float],
) -> Tuple[Optional[int], Optional[int]]:
    """ID курса и процента для чека: явные значения или дефолты чата."""
    default_rate_id, default_retention_id = get_default_rate_ids(chat_id)
    if rate_value is not None:
        exchange_rate_id = find_or_create_exchange_rate(chat_id, rate_value)
    else:
        exchange_rate_id = default_rate_id
    if percent_value is not None:
        retention_rate_id = find_or_create_retention_rate(chat_id, percent_value)
    else:
        retention_rate_id = default_retention_id
    return exchange_rate_id, retention_rate_id


def find_or_create_exchange_rate(chat_id: int, rate: float) -> int:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM exchange_rates WHERE chat_id = %s AND rate = %s LIMIT 1",
            (chat_id, rate),
        )
        row = cur.fetchone()
        if row:
            return int(row[0])
        cur.execute(
            "INSERT INTO exchange_rates (chat_id, rate) VALUES (%s, %s) RETURNING id",
            (chat_id, rate),
        )
        return int(cur.fetchone()[0])


def find_or_create_retention_rate(chat_id: int, percent: float) -> int:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM retention_rates WHERE chat_id = %s AND percent = %s LIMIT 1",
            (chat_id, percent),
        )
        row = cur.fetchone()
        if row:
            return int(row[0])
        cur.execute(
            "INSERT INTO retention_rates (chat_id, percent) VALUES (%s, %s) RETURNING id",
            (chat_id, percent),
        )
        return int(cur.fetchone()[0])


def update_receipt_rates(
    chat_id: int,
    receipt_no: int,
    exchange_rate_id: int,
    retention_rate_id: int,
) -> int:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE receipts SET exchange_rate_id = %s, retention_rate_id = %s
            WHERE chat_id = %s AND receipt_no = %s
            """,
            (exchange_rate_id, retention_rate_id, chat_id, receipt_no),
        )
        return cur.rowcount


def receipt_exists(chat_id: int, receipt_no: int) -> bool:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM receipts WHERE chat_id = %s AND receipt_no = %s",
            (chat_id, receipt_no),
        )
        return cur.fetchone() is not None


def apply_chat_defaults(
    chat_id: int,
    new_rate_value: Optional[float],
    new_retention_percent: Optional[float],
) -> None:
    """Команда /дефолт: обновляет дефолтный курс и процент в group_settings и связанных строках."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO group_settings (chat_id, trader_rate, payout, exchange_rate)
            VALUES (%s, 10, 0, 100)
            ON CONFLICT (chat_id) DO NOTHING
            """,
            (chat_id,),
        )
        cur.execute(
            """
            SELECT default_exchange_rate_id, default_retention_rate_id
            FROM group_settings WHERE chat_id = %s
            """,
            (chat_id,),
        )
        row = cur.fetchone()
        if not row:
            return
        current_default_rate_id, current_default_retention_id = row

        rate_id = current_default_rate_id
        if new_rate_value is not None:
            if current_default_rate_id:
                cur.execute(
                    "UPDATE exchange_rates SET rate = %s WHERE id = %s AND chat_id = %s",
                    (new_rate_value, current_default_rate_id, chat_id),
                )
            else:
                cur.execute(
                    "INSERT INTO exchange_rates (chat_id, rate) VALUES (%s, %s) RETURNING id",
                    (chat_id, new_rate_value),
                )
                rate_id = int(cur.fetchone()[0])
                cur.execute(
                    "UPDATE group_settings SET default_exchange_rate_id = %s WHERE chat_id = %s",
                    (rate_id, chat_id),
                )

        retention_id = current_default_retention_id
        if new_retention_percent is not None:
            if current_default_retention_id:
                cur.execute(
                    "UPDATE retention_rates SET percent = %s WHERE id = %s AND chat_id = %s",
                    (new_retention_percent, current_default_retention_id, chat_id),
                )
            else:
                cur.execute(
                    "INSERT INTO retention_rates (chat_id, percent) VALUES (%s, %s) RETURNING id",
                    (chat_id, new_retention_percent),
                )
                retention_id = int(cur.fetchone()[0])
                cur.execute(
                    "UPDATE group_settings SET default_retention_rate_id = %s WHERE chat_id = %s",
                    (retention_id, chat_id),
                )


def unassign_exchange_rate(chat_id: int, receipt_no: int) -> int:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE receipts SET exchange_rate_id = NULL
            WHERE chat_id = %s AND receipt_no = %s
            """,
            (chat_id, receipt_no),
        )
        return cur.rowcount


def unassign_retention_rate(chat_id: int, receipt_no: int) -> int:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE receipts SET retention_rate_id = NULL
            WHERE chat_id = %s AND receipt_no = %s
            """,
            (chat_id, receipt_no),
        )
        return cur.rowcount


def reset_group_data(chat_id: int) -> None:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM receipts WHERE chat_id = %s", (chat_id,))
        cur.execute("DELETE FROM payouts WHERE chat_id = %s", (chat_id,))
        cur.execute("DELETE FROM exchange_rates WHERE chat_id = %s", (chat_id,))
        cur.execute("DELETE FROM retention_rates WHERE chat_id = %s", (chat_id,))
        cur.execute(
            """
            UPDATE group_settings SET
                trader_rate = 10, payout = 0, exchange_rate = 100,
                default_exchange_rate_id = NULL, default_retention_rate_id = NULL
            WHERE chat_id = %s
            """,
            (chat_id,),
        )


def get_global_wallet_address() -> Optional[str]:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT wallet_address FROM global_settings WHERE id = 1")
        row = cur.fetchone()
        if not row or row[0] is None:
            return None
        return str(row[0]).strip() or None


def is_transaction_hash_processed(tx_hash: str) -> bool:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM processed_transactions WHERE hash = %s",
            (tx_hash,),
        )
        return cur.fetchone() is not None


def mark_transaction_processed(tx_hash: str, amount: float, chat_id: int) -> None:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO processed_transactions (hash, amount, chat_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (hash) DO UPDATE SET
                amount = EXCLUDED.amount,
                chat_id = EXCLUDED.chat_id,
                ts = CURRENT_TIMESTAMP
            """,
            (tx_hash, amount, chat_id),
        )


def has_receipt_on_local_date(chat_id: int, ymd: str) -> bool:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM receipts
            WHERE chat_id = %s AND (ts::date) = %s::date
            LIMIT 1
            """,
            (chat_id, ymd),
        )
        return cur.fetchone() is not None


def count_receipts_on_local_date(chat_id: int, ymd: str) -> int:
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) FROM receipts
            WHERE chat_id = %s AND (ts::date) = %s::date
            """,
            (chat_id, ymd),
        )
        return int(cur.fetchone()[0])


def _normalize_ts(ts: Any) -> datetime:
    if isinstance(ts, datetime):
        return ts
    s = str(ts).replace("Z", "+00:00")
    if " " in s and "T" not in s:
        s = s.replace(" ", "T", 1)
    return datetime.fromisoformat(s)


_MONTHS_GEN_RU = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def _format_datetime_ru(dt: datetime) -> str:
    """Дата/время для /инфо: без locale (%B иначе даёт March и т.д. в EN)."""
    return f"{dt.day} {_MONTHS_GEN_RU[dt.month]} {dt.year}, {dt.strftime('%H:%M')}"


def format_ts_ru_msk(ts: Any) -> str:
    """Отображение timestamp из БД в Europe/Moscow (устраняет сдвиг ~3 ч при UTC в timestamp)."""
    dt = _normalize_ts(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_UTC)
    dt = dt.astimezone(_MSK)
    return f"{dt.day} {_MONTHS_GEN_RU[dt.month]} {dt.year}, {dt.strftime('%H:%M')}"


def build_info_snapshot(chat_id: int, today: str) -> Optional[Dict[str, Any]]:
    """Данные для /инфо и ежедневного отчёта (последние 15 чеков за сегодня)."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT trader_rate, payout, exchange_rate,
                   default_exchange_rate_id, default_retention_rate_id
            FROM group_settings WHERE chat_id = %s
            """,
            (chat_id,),
        )
        result = cur.fetchone()
        if result is None:
            return None
        (
            trader_rate,
            payout,
            exchange_rate,
            default_rate_id,
            default_retention_id,
        ) = result

        default_rate_value: Optional[float] = None
        default_retention_value: Optional[float] = None
        if default_rate_id:
            cur.execute(
                "SELECT rate FROM exchange_rates WHERE id = %s AND chat_id = %s",
                (default_rate_id, chat_id),
            )
            row = cur.fetchone()
            default_rate_value = float(row[0]) if row else None
        if default_retention_id:
            cur.execute(
                "SELECT percent FROM retention_rates WHERE id = %s AND chat_id = %s",
                (default_retention_id, chat_id),
            )
            row = cur.fetchone()
            default_retention_value = float(row[0]) if row else None

        cur.execute(
            """
            SELECT r.receipt_no, r.amount, r.ts, e.rate, t.percent
            FROM receipts r
            LEFT JOIN exchange_rates e
              ON r.exchange_rate_id = e.id AND e.chat_id = r.chat_id
            LEFT JOIN retention_rates t
              ON r.retention_rate_id = t.id AND t.chat_id = r.chat_id
            WHERE r.chat_id = %s AND (r.ts::date) = %s::date
            ORDER BY r.id DESC
            LIMIT 15
            """,
            (chat_id, today),
        )
        rows = cur.fetchall()

        cur.execute(
            """
            SELECT COALESCE(SUM(r.amount / er.rate), 0)
            FROM receipts r
            JOIN exchange_rates er
              ON r.exchange_rate_id = er.id AND er.chat_id = r.chat_id
            WHERE r.chat_id = %s AND (r.ts::date) = %s::date
            """,
            (chat_id, today),
        )
        turnover = float(cur.fetchone()[0] or 0)
        total_orders_converted_sum = turnover
        if default_rate_value is not None:
            cur.execute(
                """
                SELECT COALESCE(SUM(amount / %s), 0)
                FROM receipts
                WHERE chat_id = %s AND exchange_rate_id IS NULL
                  AND (ts::date) = %s::date
                """,
                (default_rate_value, chat_id, today),
            )
            total_orders_converted_sum += float(cur.fetchone()[0] or 0)

        cur.execute(
            """
            SELECT exchange_rate_id, retention_rate_id, COALESCE(SUM(amount), 0)
            FROM receipts
            WHERE chat_id = %s
            GROUP BY exchange_rate_id, retention_rate_id
            """,
            (chat_id,),
        )
        grouped_rows = cur.fetchall()
        default_pair = (default_rate_id, default_retention_id)
        group_totals: Dict[Tuple[Optional[int], Optional[int]], float] = {}
        for ex_id, rt_id, total in grouped_rows:
            effective_ex_id = ex_id if ex_id is not None else default_rate_id
            effective_rt_id = rt_id if rt_id is not None else default_retention_id
            key = (effective_ex_id, effective_rt_id)
            group_totals[key] = group_totals.get(key, 0.0) + float(total or 0)

        total_default_amount = float(group_totals.pop(default_pair, 0.0) or 0.0)
        other_group_amounts = list(group_totals.values())

        cur.execute(
            """
            SELECT COALESCE(SUM(
                r.amount / er.rate * (1 - COALESCE(rr.percent, 0) / 100.0)
            ), 0)
            FROM receipts r
            JOIN exchange_rates er
              ON r.exchange_rate_id = er.id AND er.chat_id = r.chat_id
            LEFT JOIN retention_rates rr
              ON r.retention_rate_id = rr.id AND rr.chat_id = r.chat_id
            WHERE r.chat_id = %s AND (r.ts::date) = %s::date
            """,
            (chat_id, today),
        )
        total_to_pay = float(cur.fetchone()[0] or 0)
        if default_rate_value is not None:
            cur.execute(
                """
                SELECT COALESCE(SUM(
                    amount / %s * (1 - COALESCE(rr.percent, %s) / 100.0)
                ), 0)
                FROM receipts r
                LEFT JOIN retention_rates rr
                  ON r.retention_rate_id = rr.id AND rr.chat_id = r.chat_id
                WHERE r.chat_id = %s AND r.exchange_rate_id IS NULL
                  AND (r.ts::date) = %s::date
                """,
                (
                    default_rate_value,
                    default_retention_value or 0,
                    chat_id,
                    today,
                ),
            )
            total_to_pay += float(cur.fetchone()[0] or 0)

        cur.execute(
            """
            SELECT COALESCE(SUM(amount), 0) FROM payouts
            WHERE chat_id = %s AND (ts::date) = %s::date
            """,
            (chat_id, today),
        )
        paid_already = float(cur.fetchone()[0] or 0)
        remaining = total_to_pay - paid_already

        return {
            "rows": rows,
            "trader_rate": trader_rate,
            "payout": payout,
            "exchange_rate": exchange_rate,
            "default_rate_id": default_rate_id,
            "default_retention_id": default_retention_id,
            "default_rate_value": default_rate_value,
            "default_retention_value": default_retention_value,
            "total_orders_converted_sum": total_orders_converted_sum,
            "total_default_amount": total_default_amount,
            "other_group_amounts": other_group_amounts,
            "total_to_pay": total_to_pay,
            "paid_already": paid_already,
            "remaining": remaining,
        }


def build_cheki_today_snapshot(chat_id: int, today: str) -> Optional[Dict[str, Any]]:
    """Все чеки за сегодня для /чеки_сегодня (HTML)."""
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT default_exchange_rate_id, default_retention_rate_id
            FROM group_settings WHERE chat_id = %s
            """,
            (chat_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        default_rate_id, default_retention_id = row

        default_rate_value: Optional[float] = None
        default_retention_value: Optional[float] = None
        if default_rate_id:
            cur.execute(
                "SELECT rate FROM exchange_rates WHERE id = %s AND chat_id = %s",
                (default_rate_id, chat_id),
            )
            r = cur.fetchone()
            default_rate_value = float(r[0]) if r else None
        if default_retention_id:
            cur.execute(
                "SELECT percent FROM retention_rates WHERE id = %s AND chat_id = %s",
                (default_retention_id, chat_id),
            )
            r = cur.fetchone()
            default_retention_value = float(r[0]) if r else None

        cur.execute(
            """
            SELECT r.receipt_no, r.amount, r.ts, e.rate, t.percent,
                   r.exchange_rate_id, r.retention_rate_id
            FROM receipts r
            LEFT JOIN exchange_rates e
              ON r.exchange_rate_id = e.id AND e.chat_id = r.chat_id
            LEFT JOIN retention_rates t
              ON r.retention_rate_id = t.id AND t.chat_id = r.chat_id
            WHERE r.chat_id = %s AND (r.ts::date) = %s::date
            ORDER BY r.receipt_no ASC
            """,
            (chat_id, today),
        )
        rows = cur.fetchall()

        cur.execute(
            """
            SELECT exchange_rate_id, retention_rate_id, COALESCE(SUM(amount), 0)
            FROM receipts
            WHERE chat_id = %s
            GROUP BY exchange_rate_id, retention_rate_id
            """,
            (chat_id,),
        )
        grouped_rows = cur.fetchall()
        default_pair = (default_rate_id, default_retention_id)
        group_totals: Dict[Tuple[Optional[int], Optional[int]], float] = {}
        for ex_id, rt_id, total in grouped_rows:
            effective_ex_id = ex_id if ex_id is not None else default_rate_id
            effective_rt_id = rt_id if rt_id is not None else default_retention_id
            key = (effective_ex_id, effective_rt_id)
            group_totals[key] = group_totals.get(key, 0.0) + float(total or 0)

        total_default_amount = float(group_totals.pop(default_pair, 0.0) or 0.0)
        other_group_amounts = list(group_totals.values())

        table_rows: List[List[Any]] = []
        total_converted = 0.0
        total_payout = 0.0
        for (
            receipt_no,
            amount,
            ts,
            exch_rate,
            retention_percent,
            ex_id,
            rt_id,
        ) in rows:
            time_str = _normalize_ts(ts).strftime("%H:%M")
            effective_rate = (
                float(exch_rate) if exch_rate is not None else default_rate_value
            )
            effective_retention = (
                float(retention_percent)
                if retention_percent is not None
                else default_retention_value
            )
            converted = (
                round(float(amount) / effective_rate, MONEY_DECIMAL_PLACES)
                if effective_rate is not None
                else None
            )
            payout_val: Optional[float] = None
            if converted is not None:
                if effective_retention is not None:
                    payout_val = round(
                        converted * (1 - effective_retention / 100.0),
                        MONEY_DECIMAL_PLACES,
                    )
                else:
                    payout_val = converted
            if converted is not None:
                total_converted += converted
            if payout_val is not None:
                total_payout += payout_val
            table_rows.append(
                [
                    receipt_no,
                    time_str,
                    format_money(amount),
                    f"{effective_rate}" if effective_rate is not None else "—",
                    f"{effective_retention}"
                    if effective_retention is not None
                    else "—",
                    format_money(converted) if converted is not None else "—",
                    format_money(payout_val) if payout_val is not None else "—",
                ]
            )

        return {
            "rows": rows,
            "table_rows": table_rows,
            "default_rate_value": default_rate_value,
            "default_retention_value": default_retention_value,
            "total_default_amount": total_default_amount,
            "other_group_amounts": other_group_amounts,
            "total_converted": total_converted,
            "total_payout": total_payout,
        }


def format_info_message_html(
    snapshot: Dict[str, Any],
    daily_report: bool = False,
    intermediate: bool = False,
) -> str:
    """Текст ответа /инфо, ежедневной или промежуточной рассылки."""
    rows = snapshot["rows"]
    default_rate_value = snapshot["default_rate_value"]
    default_retention_value = snapshot["default_retention_value"]
    total_default_amount = snapshot["total_default_amount"]
    other_group_amounts: List[float] = snapshot["other_group_amounts"]
    total_orders_converted_sum = snapshot["total_orders_converted_sum"]
    total_to_pay = snapshot["total_to_pay"]
    paid_already = snapshot["paid_already"]
    remaining = snapshot["remaining"]

    blocks: List[str] = []
    for receipt_no, amount, ts, exch_rate, retention_percent in rows:
        effective_rate = (
            float(exch_rate) if exch_rate is not None else default_rate_value
        )
        effective_percent = (
            float(retention_percent)
            if retention_percent is not None
            else default_retention_value
        )
        ts_fmt = _format_datetime_ru(_normalize_ts(ts))
        amt = float(amount)

        if effective_rate is not None:
            converted = round(amt / effective_rate, MONEY_DECIMAL_PLACES)
            payout = (
                round(converted * (1 - effective_percent / 100.0), MONEY_DECIMAL_PLACES)
                if effective_percent is not None
                else converted
            )
            blocks.append(
                ui.info_receipt_block(
                    receipt_no,
                    ts_fmt,
                    amt,
                    rate=effective_rate,
                    percent=effective_percent,
                    payout=payout,
                )
            )
        else:
            blocks.append(
                ui.info_receipt_block(
                    receipt_no,
                    ts_fmt,
                    amt,
                    percent=effective_percent,
                    rate_missing=True,
                )
            )

    body = "\n".join(blocks) if blocks else "<i>За сегодня операций пока нет.</i>\n"
    header = ""
    if intermediate:
        header = ui.intermediate_report_header_html()
    elif daily_report:
        header = ui.daily_report_header_html()
    sums = " · ".join(
        [format_money(total_default_amount)]
        + [format_money(a) for a in other_group_amounts]
    )
    rate_s = default_rate_value if default_rate_value is not None else "—"
    pct_s = default_retention_value if default_retention_value is not None else "—"
    footer = ui.info_footer(
        rate_s=str(rate_s),
        pct_s=str(pct_s),
        sums=sums,
        turnover=total_orders_converted_sum,
        total_to_pay=total_to_pay,
        paid=paid_already,
        remaining=remaining,
    )
    return f"{header}<b>Последние чеки</b>\n{body}\n{footer}"
