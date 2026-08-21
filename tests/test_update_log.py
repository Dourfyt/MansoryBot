from unittest.mock import MagicMock

from aiogram.enums import ContentType

from bot.update_log import _message_content_label, describe_update


def test_message_content_photo() -> None:
    msg = MagicMock()
    msg.content_type = ContentType.PHOTO
    msg.text = None
    assert _message_content_label(msg) == "photo"


def test_message_content_command() -> None:
    msg = MagicMock()
    msg.content_type = ContentType.TEXT
    msg.text = "/инфо"
    assert _message_content_label(msg) == "command"


def test_describe_update_message() -> None:
    update = MagicMock()
    update.message = MagicMock()
    update.message.content_type = ContentType.PHOTO
    update.message.text = None
    update.message.photo = [MagicMock()]
    update.message.document = None
    for attr in (
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "callback_query",
        "inline_query",
        "my_chat_member",
        "chat_member",
        "chat_join_request",
        "message_reaction",
        "message_reaction_count",
        "poll",
        "poll_answer",
    ):
        setattr(update, attr, None)
    kind, content = describe_update(update)
    assert kind == "message"
    assert content == "photo"
