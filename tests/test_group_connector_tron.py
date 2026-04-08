"""Парсинг Tron-транзакций (без сети)."""
import group_connector_bot as gcb


def test_extract_amount_transaction_behavior_with_decimals() -> None:
    data = {
        "transactionBehavior": {
            "value": "1000000",
            "token_info": {"tokenDecimal": 6},
        }
    }
    assert gcb.extract_amount_from_transaction_data(data) == 1.0


def test_extract_amount_trc20_list() -> None:
    data = {
        "trc20TransferInfo": [
            {
                "amount_str": "5000000",
                "decimals": 6,
                "from_address": "TAAA",
                "to_address": "TBBB",
            }
        ]
    }
    assert abs(gcb.extract_amount_from_transaction_data(data) - 5.0) < 1e-9


def test_check_wallet_in_trc20() -> None:
    data = {
        "trc20TransferInfo": [
            {
                "from_address": "Tfromxx",
                "to_address": "Ttohere",
            }
        ]
    }
    assert gcb.check_wallet_address_in_transaction(data, "Ttohere")
    assert not gcb.check_wallet_address_in_transaction(data, "Tother")


def test_check_wallet_skips_when_no_address() -> None:
    assert gcb.check_wallet_address_in_transaction({}, None) is True
