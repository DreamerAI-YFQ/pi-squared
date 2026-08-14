from pi_agent.harness.messages import CustomMessage, convert_to_llm
from pi_agent.types import UserMessage


def test_standard_message_passthrough():
    user = UserMessage(content="hello", timestamp=0)
    result = convert_to_llm([user])
    assert result == [user]


def test_custom_message_converted():
    custom = CustomMessage(content="这是一段内部记录", timestamp=0)
    result = convert_to_llm([custom])
    assert len(result) == 1
    assert result[0].role == "user"
    assert result[0].content == "这是一段内部记录"


def test_mixed_messages():
    user = UserMessage(content="hi", timestamp=0)
    custom = CustomMessage(content="内部", timestamp=0)
    result = convert_to_llm([user, custom])
    assert len(result) == 2
    assert result[0].role == "user"
    assert result[0].content == "hi"
    assert result[1].role == "user"
    assert result[1].content == "内部"
