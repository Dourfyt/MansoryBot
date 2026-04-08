"""Интеграция group_queries + PostgreSQL."""
import uuid

import pytest

from tests.conftest import cleanup_chat_data


@pytest.mark.integration
def test_receipt_flow_and_snapshot(
    db_ready,
    unique_chat_id: int,
) -> None:
    chat_id = unique_chat_id
    try:
        from bot.pg import ensure_group_row
        from bot.group_queries import (
            apply_chat_defaults,
            build_info_snapshot,
            count_receipts_on_local_date,
            get_default_rate_ids,
            has_receipt_on_local_date,
            insert_receipt,
            reset_group_data,
        )

        ensure_group_row(chat_id)
        apply_chat_defaults(chat_id, 100.0, 5.0)
        ex_id, rt_id = get_default_rate_ids(chat_id)
        assert ex_id is not None and rt_id is not None

        ts = "2025-03-24 10:00:00"
        insert_receipt(chat_id, 200.0, ex_id, rt_id, ts)
        assert count_receipts_on_local_date(chat_id, "2025-03-24") >= 1
        assert has_receipt_on_local_date(chat_id, "2025-03-24")

        snap = build_info_snapshot(chat_id, "2025-03-24")
        assert snap is not None
        assert snap["total_orders_converted_sum"] >= 0

        reset_group_data(chat_id)
    finally:
        cleanup_chat_data(chat_id)


@pytest.mark.integration
def test_global_wallet_and_processed_tx(db_ready) -> None:
    from bot.group_queries import (
        get_global_wallet_address,
        is_transaction_hash_processed,
        mark_transaction_processed,
    )

    get_global_wallet_address()

    h = uuid.uuid4().hex
    assert not is_transaction_hash_processed(h)
    mark_transaction_processed(h, 1.5, -100)
    assert is_transaction_hash_processed(h)
