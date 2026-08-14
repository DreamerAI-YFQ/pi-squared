"""子智能体 sub-agent（对应 ETCLOVG 的 L 层多智能体，特色实现）。

原理：把一个 Agent 包装成可被父 Agent 调用的工具。
父 Agent 调用它时，传入子任务描述，子 Agent 用独立的 system_prompt + tools
跑自己的 ReAct 循环，把最终回复作为工具结果返回给父 Agent。
"""
from pydantic import BaseModel

from pi_agent.agent import Agent
from pi_agent.stream_fn import StreamFn
from pi_agent.types import AgentTool, AgentToolResult, TextContent


class SubAgentParams(BaseModel):
    task: str  # 委托给子智能体的子任务


class SubAgent:
    """子智能体：独立的 prompt / tools / system_prompt，可被父 Agent 调用。"""

    def __init__(
        self,
        name: str,
        description: str,
        stream_fn: StreamFn,
        system_prompt: str,
        tools: list[AgentTool] | None = None,
    ):
        self.name = name
        self.description = description
        self._stream_fn = stream_fn
        self._system_prompt = system_prompt
        self._tools = tools or []

    async def run(self, task: str) -> str:
        """运行一次子任务，返回子 Agent 的最终文本回复。"""
        agent = Agent(
            stream_fn=self._stream_fn,
            system_prompt=self._system_prompt,
            tools=self._tools,
        )
        await agent.prompt(task)
        return self._final_text(agent)

    def _final_text(self, agent: Agent) -> str:
        for m in reversed(agent.messages):
            if m.role == "assistant":
                texts = [c.text for c in m.content if c.type == "text"]
                if texts:
                    return "\n".join(texts)
        return ""

    def as_tool(self) -> AgentTool:
        """把子智能体包装成父 Agent 可调用的 AgentTool。"""

        async def execute(tool_call_id: str, params: dict) -> AgentToolResult:
            result_text = await self.run(params["task"])
            return AgentToolResult(content=[TextContent(text=result_text)])

        return AgentTool(
            name=self.name,
            description=self.description,
            parameters=SubAgentParams,
            execute=execute,
        )
