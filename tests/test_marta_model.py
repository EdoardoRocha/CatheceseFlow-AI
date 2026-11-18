import pytest
from pydantic import ValidationError


def test_marta_chat_request_truncates_history_to_last_10_messages():
    from models.marta_model import MartaChatRequest, MartaMessageItem

    history = [
        MartaMessageItem(role="user" if i % 2 == 0 else "assistant", content=f"msg {i}")
        for i in range(15)
    ]

    req = MartaChatRequest(message="  Quem faltou hoje?  ", history=history)
    assert req.message == "Quem faltou hoje?"
    assert len(req.history) == 10
    assert req.history[0].content == "msg 5"
    assert req.history[-1].content == "msg 14"
    assert req.stream is True


def test_marta_chat_request_rejects_blank_message():
    from models.marta_model import MartaChatRequest

    with pytest.raises(ValidationError):
        MartaChatRequest(message="   ")
