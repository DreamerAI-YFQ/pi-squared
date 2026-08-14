"""可观测性（对应 ETCLOVG 的 O 层，特色实现）。

轨迹记录（结构化事件）+ 成本追踪（token/成本累加）。
通过 Agent 事件订阅或 stream_fn 包装接入。
"""
import json
import time

# 价格表：每 100 万 token 的美元价格（演示用，实际以官方最新价为准）
PRICING: dict[str, tuple[float, float]] = {
    "deepseek-chat": (0.27, 1.10),  # (输入, 输出)
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """按价格表估算一次 LLM 调用的成本（美元）。"""
    input_price, output_price = PRICING.get(model, (0.0, 0.0))
    return (prompt_tokens / 1_000_000) * input_price + (completion_tokens / 1_000_000) * output_price


class Observability:
    def __init__(self):
        self._events: list[dict] = []
        self._total_tokens = 0
        self._total_cost = 0.0
        self._span_stack: list[dict] = []
        self._spans: list[dict] = []

    def record(self, kind: str, **data) -> None:
        """记录一条轨迹事件。"""
        self._events.append({"kind": kind, "timestamp": int(time.time() * 1000), **data})

    def record_llm(self, model: str, tokens: int, cost: float) -> None:
        """记录一次 LLM 调用（含 token/成本）。"""
        self.record("llm_call", model=model, tokens=tokens, cost=cost)
        self._total_tokens += tokens
        self._total_cost += cost

    def record_tool(self, tool_name: str, is_error: bool) -> None:
        """记录一次工具调用。"""
        self.record("tool_call", tool=tool_name, isError=is_error)

    def record_usage(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        """记录一次 LLM 的真实 token 用量，并按价格表累计成本。"""
        total = prompt_tokens + completion_tokens
        cost = estimate_cost(model, prompt_tokens, completion_tokens)
        self.record_llm(model, total, cost)

    def start_span(self, name: str, **attrs) -> None:
        """开启一个 span，自动挂到父 span 下（构成 span 树）。"""
        span = {"name": name, "start_ms": int(time.time() * 1000), "attrs": attrs, "children": []}
        if self._span_stack:
            self._span_stack[-1]["children"].append(span)
        else:
            self._spans.append(span)
        self._span_stack.append(span)

    def end_span(self) -> None:
        """关闭当前 span，记录耗时。"""
        if not self._span_stack:
            return
        span = self._span_stack.pop()
        span["duration_ms"] = int(time.time() * 1000) - span["start_ms"]

    def annotate(self, **attrs) -> None:
        """更新当前 span 的属性（如把 token 用量挂到 turn span 上）。"""
        if self._span_stack:
            self._span_stack[-1]["attrs"].update(attrs)

    @property
    def spans(self) -> list[dict]:
        return list(self._spans)

    @property
    def events(self) -> list[dict]:
        return list(self._events)

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def total_cost(self) -> float:
        return self._total_cost

    def llm_calls(self) -> list[dict]:
        return [e for e in self._events if e["kind"] == "llm_call"]

    def tool_calls(self) -> list[dict]:
        return [e for e in self._events if e["kind"] == "tool_call"]

    def save(self, path: str) -> None:
        """把轨迹和成本快照落盘为 JSON。"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "events": self._events,
                    "spans": self._spans,
                    "total_tokens": self._total_tokens,
                    "total_cost": self._total_cost,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
