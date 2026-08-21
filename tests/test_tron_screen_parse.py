from bot.tron_screen_parse import (
    looks_like_tron_wallet_screen,
    parse_wallet_screen_text,
    screen_addresses_unreliable,
)

SAMPLE = """
Transaction Details
Processing
Permit Transfer
-886.5 USDT
Sending Account
Imported GasFree
TDePnbzdJPYmewK6udBpwVPLVFhWt6MvsQ
Receiving Account
GasFree
TXtAyfupawtqqpGUqmWHyHErop1J58GocX
Transaction Type
Permit Transfer
Est. Receiving Amount
885 USDT
Est. Transaction Fee
1.5 USDT
Created At
05/25/2026 13:10:40
"""


def test_looks_like_screen() -> None:
    assert looks_like_tron_wallet_screen(SAMPLE)


def test_parse_hints() -> None:
    r = parse_wallet_screen_text(SAMPLE)
    assert r is not None
    assert r.expected_amount == 885.0
    assert r.receiving_address == "TXtAyfupawtqqpGUqmWHyHErop1J58GocX"
    assert r.sending_address == "TDePnbzdJPYmewK6udBpwVPLVFhWt6MvsQ"
    assert r.created_at_ms is not None


def test_pick_addresses_clears_duplicate_sending_receiving() -> None:
    from bot.tron_screen_parse import _pick_addresses

    text = """
Receiving Account
TQjzRvujvMBThp6Uhk687Yb8sZ1BeAXo1s
Est. Receiving Amount
566 USDT
"""
    sending, receiving, all_addrs = _pick_addresses(text)
    assert receiving == "TQjzRvujvMBThp6Uhk687Yb8sZ1BeAXo1s"
    assert sending is None
    assert screen_addresses_unreliable(
        parse_wallet_screen_text(
            "Transaction Details\nPermit Transfer\n" + text
        )
    )


def test_wallet_likely_in_screen_text_partial() -> None:
    from bot.tron_screen_parse import wallet_likely_in_screen_text

    wallet = "TDePnbzdJPYmewK6udBpwVPLVFhWt6MvsQ"
    ocr = "Sending Account\nTDePnbzdJPYmewK6udBpwVPLVFhWt6MvsQ\nReceiving\nTQjzRvujvMBThp6Uhk687Yb8sZ1BeAXo1s"
    assert wallet_likely_in_screen_text(ocr, wallet)


def test_parse_expected_amount_ignores_fee() -> None:
    text = """
Transaction Details
Permit Transfer
-13163.5 USDT
Est. Receiving Amount
13162 USDT
Est. Transaction Fee
1.5 USDT
"""
    r = parse_wallet_screen_text(
        "Transaction Details\nPermit Transfer\nSending Account\nReceiving Account\n" + text
    )
    assert r is not None
    assert r.expected_amount == 13162.0


def test_parse_fee_only_fallback_uses_gross_not_fee() -> None:
    text = """
Transaction Details
Permit Transfer
-13163.5 USDT
Est. Transaction Fee
1.5 USDT
"""
    r = parse_wallet_screen_text(
        "Transaction Details\nPermit Transfer\nSending Account\nReceiving Account\n" + text
    )
    assert r is not None
    assert r.expected_amount == 13163.5


def test_parse_addresses_by_sending_receiving_labels() -> None:
    """OCR с контрактом USDT в тексте не должен подменять sending/receiving."""
    text = """
Transaction Details
Permit Transfer
TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t
Sending Account
TDePnbzdJPYmewK6udBpwVPLVFhWt6MvsQ
Receiving Account
TXtAyfupawtqqpGUqmWHyHErop1J58GocX
Est. Receiving Amount
885 USDT
"""
    r = parse_wallet_screen_text(text)
    assert r is not None
    assert r.sending_address == "TDePnbzdJPYmewK6udBpwVPLVFhWt6MvsQ"
    assert r.receiving_address == "TXtAyfupawtqqpGUqmWHyHErop1J58GocX"
    assert "TDePnbzdJPYmewK6udBpwVPLVFhWt6MvsQ" in r.all_addresses


def test_parse_1700_screen() -> None:
    text = """
Transaction Details
Permit Transfer
-1,701.5 USDT
Est. Receiving Amount
1 700 USDT
TDhjEZ9gnG3mTPeczcmKpj2Ne9ZCzbJksT
"""
    r = parse_wallet_screen_text(text)
    assert r is not None
    assert r.expected_amount == 1700.0
