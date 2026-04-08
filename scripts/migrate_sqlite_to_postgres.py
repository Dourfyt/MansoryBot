#!/usr/bin/env python3
"""
Перенос данных из старых SQLite БД (папка databases/) в PostgreSQL (схема bot/pg.py).

Ожидаемые файлы:
  - group_connections.db — connections, global_settings, processed_transactions,
    broadcast_chats, broadcast_inaccessible
  - data_group_<chat_id>.db — настройки группы (таблица settings или group_settings),
    exchange_rates, retention_rates, receipts, payouts, linked_groups (если есть)

Важно: внутренний id чеков в PostgreSQL будет новым (SERIAL), но номер чека в чате (receipt_no)
восстанавливается по порядку строк в SQLite внутри каждого chat_id. Курсы/проценты переносятся
с пересборкой ссылок default_* и FK в receipts.

Использование:
  export DATABASE_URL=postgresql://...
  python scripts/migrate_sqlite_to_postgres.py [--dry-run] [--databases-dir PATH] [--init-schema]

Из корня проекта: PYTHONPATH=. python3 scripts/migrate_sqlite_to_postgres.py

Зависимости (или одна команда из корня проекта):
  python3 -m pip install -r requirements.txt
  # минимум: python3 -m pip install psycopg2-binary
  # python-dotenv не обязателен — .env подхватывается встроенным парсером
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

# Корень проекта в PYTHONPATH
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_dot_env(path: Path) -> None:
    """Подставляет переменные из .env без зависимости python-dotenv (как setdefault)."""
    if not path.is_file():
        return
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        if not key:
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        os.environ.setdefault(key, val)


try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    _load_dot_env(_ROOT / ".env")

try:
    import psycopg2
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "Нужен драйвер PostgreSQL. Установите:\n"
        "  apt install -y python3-pip && python3 -m pip install psycopg2-binary\n"
        "или из корня проекта: python3 -m pip install -r requirements.txt"
    ) from e

DATA_GROUP_RE = re.compile(r"^data_group_(-?\d+)\.db$", re.IGNORECASE)


def get_pg_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("Задайте DATABASE_URL (PostgreSQL)")
    return url


def sqlite_tables(conn: sqlite3.Connection) -> List[str]:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [r[0] for r in cur.fetchall()]


def sqlite_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.execute(f'PRAGMA table_info("{table}")')
    return [str(r[1]) for r in cur.fetchall()]


def pick_settings_table(tables: Set[str]) -> Optional[str]:
    if "group_settings" in tables:
        return "group_settings"
    if "settings" in tables:
        return "settings"
    return None


def sqlite_order_by_id(cols: Sequence[str]) -> str:
    if "id" in cols:
        return "ORDER BY id"
    return "ORDER BY rowid"


def row_to_dict(columns: Sequence[str], row: Tuple[Any, ...]) -> Dict[str, Any]:
    return dict(zip(columns, row))


def migrate_global_sqlite(
    sqlite_path: Path,
    pg: Any,
    dry_run: bool,
) -> None:
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        tables = set(sqlite_tables(conn))
        cur_pg = None if dry_run else pg.cursor()

        if "connections" in tables:
            cols = sqlite_columns(conn, "connections")
            q = f'SELECT {", ".join(cols)} FROM connections'
            rows = conn.execute(q).fetchall()
            print(f"  connections: {len(rows)} строк")
            if not dry_run and cur_pg is not None:
                for r in rows:
                    d = row_to_dict(cols, tuple(r))
                    vals = [
                        d.get("client_group_id"),
                        d.get("verifier_group_id"),
                        d.get("client_group_name"),
                        d.get("verifier_group_name"),
                        d.get("created_at"),
                        bool(d.get("is_active", 1)),
                    ]
                    cur_pg.execute(
                        """
                        INSERT INTO connections (
                            client_group_id, verifier_group_id, client_group_name,
                            verifier_group_name, created_at, is_active
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (client_group_id, verifier_group_id) DO NOTHING
                        """,
                        vals,
                    )

        if "global_settings" in tables:
            cols = sqlite_columns(conn, "global_settings")
            row = conn.execute(f"SELECT {', '.join(cols)} FROM global_settings LIMIT 1").fetchone()
            if row:
                d = row_to_dict(cols, tuple(row))
                print("  global_settings: 1 строка")
                if not dry_run and cur_pg is not None:
                    cur_pg.execute(
                        """
                        INSERT INTO global_settings (id, wallet_address, welcome_message, welcome_links)
                        VALUES (1, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            wallet_address = COALESCE(EXCLUDED.wallet_address, global_settings.wallet_address),
                            welcome_message = COALESCE(EXCLUDED.welcome_message, global_settings.welcome_message),
                            welcome_links = COALESCE(EXCLUDED.welcome_links, global_settings.welcome_links)
                        """,
                        (
                            d.get("wallet_address"),
                            d.get("welcome_message"),
                            d.get("welcome_links"),
                        ),
                    )

        if "processed_transactions" in tables:
            cols = sqlite_columns(conn, "processed_transactions")
            rows = conn.execute(f"SELECT {', '.join(cols)} FROM processed_transactions").fetchall()
            print(f"  processed_transactions: {len(rows)} строк")
            if not dry_run and cur_pg is not None:
                for r in rows:
                    d = row_to_dict(cols, tuple(r))
                    cur_pg.execute(
                        """
                        INSERT INTO processed_transactions (hash, amount, chat_id, ts)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (hash) DO NOTHING
                        """,
                        (d.get("hash"), d.get("amount"), d.get("chat_id"), d.get("ts")),
                    )

        if "broadcast_chats" in tables:
            cols = sqlite_columns(conn, "broadcast_chats")
            rows = conn.execute(f"SELECT {', '.join(cols)} FROM broadcast_chats").fetchall()
            print(f"  broadcast_chats: {len(rows)} строк")
            if not dry_run and cur_pg is not None:
                for r in rows:
                    d = row_to_dict(cols, tuple(r))
                    cur_pg.execute(
                        """
                        INSERT INTO broadcast_chats (chat_id, name) VALUES (%s, %s)
                        ON CONFLICT (chat_id) DO NOTHING
                        """,
                        (d.get("chat_id"), d.get("name")),
                    )

        if "broadcast_inaccessible" in tables:
            cols = sqlite_columns(conn, "broadcast_inaccessible")
            rows = conn.execute(f"SELECT {', '.join(cols)} FROM broadcast_inaccessible").fetchall()
            print(f"  broadcast_inaccessible: {len(rows)} строк")
            if not dry_run and cur_pg is not None:
                for r in rows:
                    d = row_to_dict(cols, tuple(r))
                    cur_pg.execute(
                        """
                        INSERT INTO broadcast_inaccessible (chat_id) VALUES (%s)
                        ON CONFLICT (chat_id) DO NOTHING
                        """,
                        (d.get("chat_id"),),
                    )
    finally:
        conn.close()


def migrate_group_sqlite(
    sqlite_path: Path,
    chat_id: int,
    pg: Any,
    dry_run: bool,
) -> None:
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        tables = set(sqlite_tables(conn))
        cur_pg = None if dry_run or pg is None else pg.cursor()

        ex_map: Dict[int, int] = {}
        ret_map: Dict[int, int] = {}

        if "exchange_rates" in tables:
            cols = sqlite_columns(conn, "exchange_rates")
            ob = sqlite_order_by_id(cols)
            rows = conn.execute(
                f"SELECT {', '.join(cols)} FROM exchange_rates {ob}"
            ).fetchall()
            print(f"    exchange_rates: {len(rows)}")
            if dry_run:
                pass
            else:
                assert cur_pg is not None
                for i, r in enumerate(rows):
                    d = row_to_dict(cols, tuple(r))
                    old_id = int(d["id"]) if "id" in cols else i + 1
                    rate = d.get("rate")
                    cur_pg.execute(
                        "INSERT INTO exchange_rates (chat_id, rate) VALUES (%s, %s) RETURNING id",
                        (chat_id, rate),
                    )
                    new_id = int(cur_pg.fetchone()[0])
                    ex_map[old_id] = new_id

        if "retention_rates" in tables:
            cols = sqlite_columns(conn, "retention_rates")
            ob = sqlite_order_by_id(cols)
            rows = conn.execute(
                f"SELECT {', '.join(cols)} FROM retention_rates {ob}"
            ).fetchall()
            print(f"    retention_rates: {len(rows)}")
            if dry_run:
                pass
            else:
                assert cur_pg is not None
                for i, r in enumerate(rows):
                    d = row_to_dict(cols, tuple(r))
                    old_id = int(d["id"]) if "id" in cols else i + 1
                    pct = d.get("percent")
                    cur_pg.execute(
                        "INSERT INTO retention_rates (chat_id, percent) VALUES (%s, %s) RETURNING id",
                        (chat_id, pct),
                    )
                    new_id = int(cur_pg.fetchone()[0])
                    ret_map[old_id] = new_id

        settings_table = pick_settings_table(tables)
        if settings_table:
            cols = sqlite_columns(conn, settings_table)
            row = conn.execute(f"SELECT {', '.join(cols)} FROM {settings_table} LIMIT 1").fetchone()
            if row:
                d = row_to_dict(cols, tuple(row))
                print(f"    {settings_table}: 1 строка")
                if not dry_run and cur_pg is not None:
                    def_ex = d.get("default_exchange_rate_id")
                    def_ret = d.get("default_retention_rate_id")
                    if def_ex is not None and int(def_ex) in ex_map:
                        def_ex = ex_map[int(def_ex)]
                    elif def_ex is not None:
                        def_ex = None
                    if def_ret is not None and int(def_ret) in ret_map:
                        def_ret = ret_map[int(def_ret)]
                    elif def_ret is not None:
                        def_ret = None

                    cur_pg.execute(
                        """
                        INSERT INTO group_settings (
                            chat_id, trader_rate, payout, exchange_rate,
                            default_exchange_rate_id, default_retention_rate_id, wallet_address
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (chat_id) DO UPDATE SET
                            trader_rate = EXCLUDED.trader_rate,
                            payout = EXCLUDED.payout,
                            exchange_rate = EXCLUDED.exchange_rate,
                            default_exchange_rate_id = EXCLUDED.default_exchange_rate_id,
                            default_retention_rate_id = EXCLUDED.default_retention_rate_id,
                            wallet_address = EXCLUDED.wallet_address
                        """,
                        (
                            chat_id,
                            d.get("trader_rate", 10),
                            d.get("payout", 0),
                            d.get("exchange_rate", 100),
                            def_ex,
                            def_ret,
                            d.get("wallet_address"),
                        ),
                    )
        elif not dry_run and cur_pg is not None:
            cur_pg.execute(
                """
                INSERT INTO group_settings (chat_id, trader_rate, payout, exchange_rate)
                VALUES (%s, 10, 0, 100)
                ON CONFLICT (chat_id) DO NOTHING
                """,
                (chat_id,),
            )

        if "receipts" in tables:
            cols = sqlite_columns(conn, "receipts")
            rows = conn.execute(f"SELECT {', '.join(cols)} FROM receipts").fetchall()
            print(f"    receipts: {len(rows)}")
            if not dry_run and cur_pg is not None:

                def _receipt_sort_key(tup: Tuple[Any, ...]) -> Tuple[int, int]:
                    d0 = row_to_dict(cols, tup)
                    cid0 = int(d0.get("chat_id") or chat_id)
                    oid0 = int(d0.get("id") or 0)
                    return (cid0, oid0)

                rows_sorted = sorted(rows, key=_receipt_sort_key)
                receipt_no_by_chat: Dict[int, int] = defaultdict(int)
                for r in rows_sorted:
                    d = row_to_dict(cols, tuple(r))
                    ex_id = d.get("exchange_rate_id")
                    rt_id = d.get("retention_rate_id")
                    if ex_id is not None:
                        ex_id = ex_map.get(int(ex_id))
                    if rt_id is not None:
                        rt_id = ret_map.get(int(rt_id))
                    cid = d.get("chat_id")
                    if cid is None:
                        cid = chat_id
                    cid = int(cid)
                    receipt_no_by_chat[cid] += 1
                    rno = receipt_no_by_chat[cid]
                    cur_pg.execute(
                        """
                        INSERT INTO receipts (chat_id, receipt_no, amount, exchange_rate_id, retention_rate_id, ts)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (cid, rno, d.get("amount"), ex_id, rt_id, d.get("ts")),
                    )

        if "payouts" in tables:
            cols = sqlite_columns(conn, "payouts")
            rows = conn.execute(f"SELECT {', '.join(cols)} FROM payouts").fetchall()
            print(f"    payouts: {len(rows)}")
            if not dry_run and cur_pg is not None:
                for r in rows:
                    d = row_to_dict(cols, tuple(r))
                    cid = d.get("chat_id")
                    if cid is None:
                        cid = chat_id
                    cur_pg.execute(
                        """
                        INSERT INTO payouts (chat_id, amount, ts) VALUES (%s, %s, %s)
                        """,
                        (cid, d.get("amount"), d.get("ts")),
                    )

        if "linked_groups" in tables:
            cols = sqlite_columns(conn, "linked_groups")
            rows = conn.execute(f"SELECT {', '.join(cols)} FROM linked_groups").fetchall()
            print(f"    linked_groups: {len(rows)}")
            if not dry_run and cur_pg is not None:
                for r in rows:
                    d = row_to_dict(cols, tuple(r))
                    cid = d.get("chat_id")
                    if cid is None:
                        cid = chat_id
                    cur_pg.execute(
                        """
                        INSERT INTO linked_groups (chat_id, linked_group_id, ts)
                        VALUES (%s, %s, %s)
                        """,
                        (cid, d.get("linked_group_id"), d.get("ts")),
                    )
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="SQLite → PostgreSQL migration")
    parser.add_argument(
        "--databases-dir",
        type=Path,
        default=_ROOT / "databases",
        help="Каталог с group_connections.db и data_group_*.db",
    )
    parser.add_argument("--dry-run", action="store_true", help="Только печать объёмов, без записи в PG")
    parser.add_argument(
        "--init-schema",
        action="store_true",
        help="Вызвать bot.pg.init_schema() перед миграцией",
    )
    args = parser.parse_args()
    base: Path = args.databases_dir.resolve()

    if not base.is_dir():
        raise SystemExit(f"Каталог не найден: {base}")

    global_db = base / "group_connections.db"
    if args.init_schema:
        if args.dry_run:
            print("Пропуск init_schema при --dry-run.")
        else:
            from bot.pg import init_schema

            print("init_schema()...")
            init_schema()

    if args.dry_run:
        print("Режим --dry-run: объёмы ниже, в PostgreSQL ничего не пишется.")

    pg: Any = None
    if not args.dry_run:
        pg = psycopg2.connect(get_pg_url())
    try:
        if global_db.is_file():
            print(f"→ {global_db.name}")
            migrate_global_sqlite(global_db, pg, args.dry_run)
            if not args.dry_run:
                pg.commit()
        else:
            print(f"Пропуск: нет {global_db.name}")

        group_files = sorted(base.glob("data_group_*.db"))
        for path in group_files:
            m = DATA_GROUP_RE.match(path.name)
            if not m:
                print(f"Пропуск (имя файла): {path.name}")
                continue
            cid = int(m.group(1))
            print(f"→ {path.name} (chat_id={cid})")
            migrate_group_sqlite(path, cid, pg, args.dry_run)
            if not args.dry_run:
                pg.commit()

        print("Готово.")
    finally:
        if pg is not None:
            pg.close()


if __name__ == "__main__":
    main()
