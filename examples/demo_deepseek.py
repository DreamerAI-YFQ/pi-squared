import asyncio

from pydantic import BaseModel

from pi_agent.agent import Agent
from pi_agent.providers.openai import deepseek_stream
from pi_agent.types import AgentTool, AgentToolResult, TextContent


class ReadParams(BaseModel):
    path: str


async def read(tool_call_id: str, params: dict) -> AgentToolResult:
    return AgentToolResult(
        content=[TextContent(text=f"文件 {params['path']} 的内容是: hello world")],
        details={},
    )


async def main():
    tool = AgentTool(name="read", description="读取指定路径的文件内容", parameters=ReadParams, execute=read)
    agent = Agent(
        stream_fn=deepseek_stream,
        system_prompt="你是一个助手，回答用户问题。",
        tools=[tool],
    )

    await agent.prompt("读取 a.txt 文件，告诉我内容")

    print("=" * 50)
    for msg in agent.messages:
        print(f"[{msg.role}]")
        print(msg)
        print("-" * 50)


if __name__ == "__main__":
    asyncio.run(main())
