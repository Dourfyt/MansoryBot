from bot.tron_screen_parse import (
    TronScreenHints,
    addresses_similar,
    parse_wallet_screen_text,
    wallet_on_screen_addresses,
)
from bot.tron_verify import _pick_unique_transfer


def _row(
    *,
    tx: str,
    amount_str: str,
    to_addr: str,
    from_addr: str,
    block_ts: int,
) -> dict:
    return {
        "transaction_id": tx,
        "amount_str": amount_str,
        "decimals": 6,
        "to_address": to_addr,
        "from_address": from_addr,
        "block_ts": block_ts,
    }


def test_wallet_on_screen_matches_any_parsed_address() -> None:
    wallet = "TDePnbzdJPYmewK6udBpwVPLVFhWt6MvsQ"
    hints = TronScreenHints(
        expected_amount=885.0,
        receiving_address="TXwrong",
        sending_address="TXwrong2",
        created_at_ms=None,
        tx_hash=None,
        all_addresses=(wallet, "TXtAyfupawtqqpGUqmWHyHErop1J58GocX"),
    )
    assert wallet_on_screen_addresses(hints, wallet)


def test_addresses_similar_ocr_8_vs_b() -> None:
    crm = "TE8ET2SXG5yptG3hsLGRte6EqEYw4rS9YA"
    ocr = "TEBET2SXG5yptG3hsLGRte6EqEYw4rS9YA"
    assert addresses_similar(crm, ocr)


def test_pick_unique_incoming() -> None:
    wallet = "TXtAyfupawtqqpGUqmWHyHErop1J58GocX"
    hints = TronScreenHints(
        expected_amount=885.0,
        receiving_address=wallet,
        sending_address="TDePnbzdJPYmewK6udBpwVPLVFhWt6MvsQ",
        created_at_ms=1_700_000_000_000,
        tx_hash=None,
    )
    rows = [
        _row(
            tx="a" * 64,
            amount_str="885000000",
            to_addr=wallet,
            from_addr="TDePnbzdJPYmewK6udBpwVPLVFhWt6MvsQ",
            block_ts=1_700_000_000_100,
        ),
        _row(
            tx="b" * 64,
            amount_str="100000000",
            to_addr=wallet,
            from_addr="Tother",
            block_ts=1_700_000_000_100,
        ),
    ]
    picked = _pick_unique_transfer(rows, hints, wallet)
    assert picked is not None
    assert picked["transaction_id"] == "a" * 64


def test_pick_unique_outgoing_wallet_is_sender() -> None:
    wallet = "TDePnbzdJPYmewK6udBpwVPLVFhWt6MvsQ"
    hints = TronScreenHints(
        expected_amount=500.0,
        receiving_address="TXother",
        sending_address=wallet,
        created_at_ms=1_700_000_000_000,
        tx_hash=None,
    )
    rows = [
        _row(
            tx="c" * 64,
            amount_str="500000000",
            from_addr=wallet,
            to_addr="TXother",
            block_ts=1_700_000_000_050,
        ),
    ]
    picked = _pick_unique_transfer(rows, hints, wallet)
    assert picked is not None
    assert picked["transaction_id"] == "c" * 64
