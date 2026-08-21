"""Разбор ответа transaction-info и строк TRC20 transfer."""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _field(row: dict, *keys: str) -> Any:
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return None


def transfer_amount_usdt(row: dict) -> Optional[float]:
    amount_str = _field(row, "amount_str", "amount")
    decimals = _field(row, "decimals", "tokenDecimal")
    if amount_str is not None and decimals is not None:
        try:
            return int(str(amount_str)) / (10 ** int(decimals))
        except (TypeError, ValueError):
            pass
    quant = _field(row, "quant", "value")
    if quant is not None:
        try:
            return int(str(quant)) / 1_000_000.0
        except (TypeError, ValueError):
            pass
    return None


def transfer_tx_hash(row: dict) -> Optional[str]:
    h = _field(row, "transaction_id", "hash", "transactionHash")
    if h is None:
        return None
    s = str(h).strip()
    return s if len(s) == 64 else None


def transfer_block_ts_ms(row: dict) -> Optional[int]:
    ts = _field(row, "block_ts", "block_timestamp", "timestamp")
    if ts is None:
        return None
    try:
        ts_i = int(ts)
    except (TypeError, ValueError):
        return None
    if ts_i < 1_000_000_000_000:
        return ts_i * 1000
    return ts_i


def extract_amount_from_transaction_data(
    data: dict, wallet_address: Optional[str] = None
) -> Optional[float]:
    """Извлекает сумму USDT из transaction-info (как для хеша в чате)."""
    try:
        if "transactionBehavior" in data and data["transactionBehavior"]:
            behavior = data["transactionBehavior"]
            if "value" in behavior:
                value_str = str(behavior["value"])
                if "token_info" in behavior and "tokenDecimal" in behavior["token_info"]:
                    decimals = behavior["token_info"]["tokenDecimal"]
                    return float(int(value_str) / (10 ** decimals))
                return float(int(value_str) / (10**6))

        if "trc20TransferInfo" in data and isinstance(data["trc20TransferInfo"], list):
            transfers = data["trc20TransferInfo"]
            max_amount = 0.0
            selected = None
            wallet_u = wallet_address.strip().upper() if wallet_address else None

            for transfer_info in transfers:
                if wallet_u:
                    from_addr = transfer_info.get("from_address", "").upper()
                    to_addr = transfer_info.get("to_address", "").upper()
                    if from_addr != wallet_u and to_addr != wallet_u:
                        continue
                if "amount_str" in transfer_info and "decimals" in transfer_info:
                    amount = int(transfer_info["amount_str"]) / (
                        10 ** transfer_info["decimals"]
                    )
                    if amount > max_amount:
                        max_amount = amount
                        selected = transfer_info

            if selected is None:
                for transfer_info in transfers:
                    if "amount_str" in transfer_info and "decimals" in transfer_info:
                        amount = int(transfer_info["amount_str"]) / (
                            10 ** transfer_info["decimals"]
                        )
                        if amount > max_amount:
                            max_amount = amount
                            selected = transfer_info

            if selected and max_amount > 0:
                return float(max_amount)

            if transfers:
                last = transfers[-1]
                if "amount_str" in last and "decimals" in last:
                    return float(int(last["amount_str"]) / (10 ** last["decimals"]))

        if "tokenTransferInfo" in data and data["tokenTransferInfo"]:
            transfer_info = data["tokenTransferInfo"]
            if "amount_str" in transfer_info and "decimals" in transfer_info:
                return float(
                    int(transfer_info["amount_str"])
                    / (10 ** transfer_info["decimals"])
                )

        if "contractData" in data and "amount" in data["contractData"]:
            amount = data["contractData"]["amount"]
            if "tokenInfo" in data.get("contractData", {}):
                token_decimal = data["contractData"]["tokenInfo"].get("tokenDecimal", 0)
                if token_decimal > 0:
                    amount = amount / (10**token_decimal)
            return float(amount)

        logger.warning("Amount не найден в данных транзакции")
        return None
    except Exception as e:
        logger.error("extract_amount_from_transaction_data: %s", e)
        return None


def check_wallet_address_in_transaction(data: dict, wallet_address: Optional[str]) -> bool:
    if not wallet_address:
        return True

    wallet_address = wallet_address.strip().upper()

    if "tokenTransferInfo" in data and data["tokenTransferInfo"]:
        transfer_info = data["tokenTransferInfo"]
        from_addr = transfer_info.get("from_address", "").upper()
        to_addr = transfer_info.get("to_address", "").upper()
        if from_addr == wallet_address or to_addr == wallet_address:
            return True

    if "trc20TransferInfo" in data and isinstance(data["trc20TransferInfo"], list):
        for transfer_info in data["trc20TransferInfo"]:
            from_addr = transfer_info.get("from_address", "").upper()
            to_addr = transfer_info.get("to_address", "").upper()
            if from_addr == wallet_address or to_addr == wallet_address:
                return True

    owner_addr = data.get("ownerAddress", "").upper()
    to_addr = data.get("toAddress", "").upper()
    if owner_addr == wallet_address or to_addr == wallet_address:
        return True

    if "contractData" in data:
        contract_data = data["contractData"]
        owner_addr = contract_data.get("owner_address", "").upper()
        to_addr = contract_data.get("to_address", "").upper()
        if owner_addr == wallet_address or to_addr == wallet_address:
            return True

    return False


def amounts_match(a: float, b: float, *, abs_tol: float = 0.02, rel_tol: float = 0.001) -> bool:
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b), 1.0))


def wallet_in_trc20_transfer_row(row: dict, wallet_address: str) -> bool:
    """Кошелёк — отправитель или получатель в строке TRC20 transfer."""
    w = wallet_address.strip().upper()
    from_addr = str(row.get("from_address") or row.get("fromAddress") or "").upper()
    to_addr = str(row.get("to_address") or row.get("toAddress") or "").upper()
    return from_addr == w or to_addr == w
