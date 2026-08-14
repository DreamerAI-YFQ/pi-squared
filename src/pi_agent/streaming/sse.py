from typing import Iterator


def parse_sse(text: str) -> Iterator[tuple[str | None, str]]:
    """解析 SSE 文本，逐个 yield (event, data) 元组。

    SSE 是流式 HTTP 的协议外壳：`data:`/`event:` 行组成一条消息，
    空行是消息的结束标志。这里把它剥成 (event, data)。
    """
    event: str | None = None
    data_lines: list[str] = []

    for line in text.splitlines():
        # 空行 = 一条事件结束，flush
        if line == "":
            if data_lines:
                yield (event, "\n".join(data_lines))
            event = None
            data_lines = []
            continue

        # 注释行（以 : 开头，无字段名），忽略
        if line.startswith(":"):
            continue

        # 解析 field: value
        if ":" in line:
            field, value = line.split(":", 1)
            if value.startswith(" "):
                value = value[1:]  # 剥掉冒号后的一个分隔空格
        else:
            field, value = line, ""

        if field == "data":
            data_lines.append(value)
        elif field == "event":
            event = value
        # 其他字段（id/retry）P1 忽略

    # 结尾残留：最后一条事件后面可能没有空行
    if data_lines:
        yield (event, "\n".join(data_lines))
