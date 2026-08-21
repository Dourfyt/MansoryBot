"""Клиент TronScan API (https://docs.tronscan.org/en/api/transactions-and-transfers)."""
from __future__ import annotations

import logging
import ssl
from typing import Any, Optional

import aiohttp

from .loader import TRON_PRO_API_KEY

logger = logging.getLogger(__name__)

TRONSCAN_API_BASE = "https://apilist.tronscanapi.com/api"
# USDT TRC20 mainnet
USDT_TRC20_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

_ssl_context: Optional[ssl.SSLContext] = None


def _ssl() -> ssl.SSLContext:
    global _ssl_context
    if _ssl_context is None:
        _ssl_context = ssl.create_default_context()
        _ssl_context.check_hostname = False
        _ssl_context.verify_mode = ssl.CERT_NONE
    return _ssl_context


def _headers() -> dict[str, str]:
    h: dict[str, str] = {}
    if TRON_PRO_API_KEY:
        h["TRON-PRO-API-KEY"] = TRON_PRO_API_KEY
    return h


async def tronscan_get(path: str, params: Optional[dict[str, Any]] = None) -> Optional[dict]:
    url = f"{TRONSCAN_API_BASE}{path}"
    try:
        connector = aiohttp.TCPConnector(ssl=_ssl())
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, params=params, headers=_headers()) as response:
                if response.status == 200:
                    return await response.json()
                logger.error("TronScan %s status=%s params=%s", path, response.status, params)
                return None
    except Exception as e:
        logger.exception("TronScan request failed %s: %s", path, e)
        return None


async def fetch_transaction_info(tx_hash: str) -> Optional[dict]:
    return await tronscan_get("/transaction-info", {"hash": tx_hash})


async def fetch_trc20_transfers(
    *,
    to_address: Optional[str] = None,
    from_address: Optional[str] = None,
    related_address: Optional[str] = None,
    start_timestamp: Optional[int] = None,
    end_timestamp: Optional[int] = None,
    limit: int = 50,
    confirm: str = "0,1",
) -> list[dict]:
    """GET /api/token_trc20/transfers"""
    params: dict[str, Any] = {
        "limit": min(limit, 50),
        "start": 0,
        "contract_address": USDT_TRC20_CONTRACT,
        "filterTokenValue": "0",
        "confirm": confirm,
    }
    if to_address:
        params["toAddress"] = to_address
    if from_address:
        params["fromAddress"] = from_address
    if related_address:
        params["relatedAddress"] = related_address
    if start_timestamp is not None:
        params["start_timestamp"] = start_timestamp
    if end_timestamp is not None:
        params["end_timestamp"] = end_timestamp

    data = await tronscan_get("/token_trc20/transfers", params)
    if not data:
        return []
    items = data.get("token_transfers") or data.get("data") or []
    return items if isinstance(items, list) else []


async def fetch_trc20_for_address(
    address: str,
    *,
    start_timestamp: Optional[int] = None,
    end_timestamp: Optional[int] = None,
    limit: int = 50,
    direction: str = "0",
) -> list[dict]:
    """GET /api/transfer/trc20 — USDT; direction 0=оба, 1=входящие, 2=исходящие."""
    params: dict[str, Any] = {
        "address": address,
        "trc20Id": USDT_TRC20_CONTRACT,
        "direction": direction,
        "limit": min(limit, 50),
        "start": 0,
        "reverse": "true",
        "db_version": "1",
    }
    if start_timestamp is not None:
        params["start_timestamp"] = start_timestamp
    if end_timestamp is not None:
        params["end_timestamp"] = end_timestamp

    data = await tronscan_get("/transfer/trc20", params)
    if not data:
        return []
    items = data.get("data") or data.get("token_transfers") or []
    return items if isinstance(items, list) else []


async def fetch_inbound_trc20_for_address(
    address: str,
    *,
    start_timestamp: Optional[int] = None,
    end_timestamp: Optional[int] = None,
    limit: int = 50,
) -> list[dict]:
    """Входящие USDT (обратная совместимость)."""
    return await fetch_trc20_for_address(
        address,
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
        limit=limit,
        direction="1",
    )
