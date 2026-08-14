from pi_agent.streaming.json_parse import parse_streaming_json


def test_complete_json():
    assert parse_streaming_json('{"path":"a.txt"}') == {"path": "a.txt"}


def test_missing_closing_quote_and_brace():
    # 缺闭合引号和闭合花括号，补全后能解析
    assert parse_streaming_json('{"path":"a.txt') == {"path": "a.txt"}


def test_truncated_key_value():
    # {"path": 缺值，无法补全，返回空 dict（等下一段 delta）
    assert parse_streaming_json('{"path":') == {}


def test_nested_missing_brace():
    assert parse_streaming_json('{"a":{"b":1}') == {"a": {"b": 1}}


def test_empty_and_whitespace():
    assert parse_streaming_json("") == {}
    assert parse_streaming_json("   ") == {}


def test_non_dict():
    # 非对象（数组）不是工具参数，返回空 dict
    assert parse_streaming_json("[1,2,3]") == {}
