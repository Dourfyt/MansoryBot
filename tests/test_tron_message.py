from unittest.mock import MagicMock

from bot.tron_message import (
    find_tron_hashes_and_links,
    find_tron_tx_hashes,
    tron_filter_skip_reason,
)

HASH = "17aab09cb839aefe2d757db49613d58f7c152c33c4f064a478030ffff9b84966"


def test_find_hash_plain() -> None:
    assert find_tron_tx_hashes(HASH) == [HASH.lower()]


def test_find_hash_with_link() -> None:
    url = f"https://tronscan.org/#/transaction/{HASH}"
    found = find_tron_hashes_and_links(url)
    assert HASH.lower() in found


def _group_photo_message(*, caption: str = "") -> MagicMock:
    msg = MagicMock()
    msg.chat.type = "supergroup"
    msg.from_user.is_bot = False
    msg.text = None
    msg.caption = caption or None
    msg.photo = [MagicMock(file_id="fid")]
    msg.document = None
    return msg


def test_tron_filter_plain_photo() -> None:
    assert tron_filter_skip_reason(_group_photo_message()) is None


def test_tron_filter_photo_with_command_caption() -> None:
    assert tron_filter_skip_reason(_group_photo_message(caption="/п")) == "caption_is_command"
