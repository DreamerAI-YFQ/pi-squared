from pi_agent.streaming.json_parse import parse_streaming_json
from pi_agent.types import ToolCall


class ToolCallAccumulator:
    """工具调用累积器：接收参数碎片 delta，累积并解析成完整 ToolCall。

    对应 pi 的 scratch buffer 模式：buffer += delta，然后反复 parse。
    """

    def __init__(self, tool_call_id: str, name: str):
        self.tool_call_id = tool_call_id
        self.name = name
        self._buffer = ""
        self.arguments: dict = {}

    def add_delta(self, delta: str) -> None:
        """追加一段参数碎片，并解析当前累积出的部分参数。"""
        self._buffer += delta
        self.arguments = parse_streaming_json(self._buffer)

    def finalize(self) -> ToolCall:
        """流结束，最终解析并构造完整 ToolCall。"""
        self.arguments = parse_streaming_json(self._buffer)
        return ToolCall(id=self.tool_call_id, name=self.name, arguments=self.arguments)
