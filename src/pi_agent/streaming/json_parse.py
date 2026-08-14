import json
from typing import Any


def parse_streaming_json(s: str) -> dict[str, Any]:
    """解析可能残缺的 JSON 字符串，返回 dict。

    tool-call 参数是流式吐出的，中间状态是残缺 JSON（如 {"path":"a.txt），
    不能直接 json.loads。这里先直接解析，失败则补全缺失的闭合符再试。
    """
    s = s.strip()
    if not s:
        return {}

    result = _try_parse_dict(s)
    if result is not None:
        return result

    repaired = _repair(s)
    result = _try_parse_dict(repaired)
    if result is not None:
        return result

    return {}


def _try_parse_dict(s: str) -> dict[str, Any] | None:
    try:
        result = json.loads(s)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None


def _repair(s: str) -> str:
    """统计未闭合的引号和括号，在末尾补上对应闭合符。"""
    stack: list[str] = []
    in_string = False
    escape = False

    for ch in s:
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack and ((ch == "}" and stack[-1] == "{") or (ch == "]" and stack[-1] == "[")):
                stack.pop()

    suffix = ""
    if in_string:
        suffix += '"'  # 补未闭合的字符串引号
    for opener in reversed(stack):
        suffix += "}" if opener == "{" else "]"
    return s + suffix
