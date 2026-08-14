"""端到端 demo（完整版）：在编排层 + 特色模块上跑整体项目。

把这条链路串起来：
    AgentHarness（编排） + JsonlSessionStorage（会话落盘）
    + Governance（权限 + 审计落盘） + Observability（轨迹落盘）
    + JsonMemoryStore（长期记忆落盘） + read/write/edit/bash 工具
    + 真实 DeepSeek 模型。

落盘产物统一放在 demo_out/：
    session.jsonl   会话记录
    audit.jsonl     治理审计日志
    memory.json     长期记忆
    trace.json      可观测性轨迹
    workspace/      agent 的工作目录（文件真实写入这里）

运行：
    D:\\miniconda3\\envs\\myenv\\python.exe demo.py
"""
import asyncio
import shutil
from pathlib import Path

from pi_agent.extensions.memory import JsonMemoryStore, extract_memories
from pi_agent.extensions.observability import Observability
from pi_agent.harness.env import LocalExecutionEnv
from pi_agent.harness.governance import Governance
from pi_agent.harness.harness import AgentHarness
from pi_agent.harness.session.session import Session
from pi_agent.harness.session.storage import JsonlSessionStorage
from pi_agent.harness.tools.bash import create_bash_tool
from pi_agent.harness.tools.edit import create_edit_tool
from pi_agent.harness.tools.read import create_read_tool
from pi_agent.harness.tools.write import create_write_tool
from pi_agent.providers.openai import DEEPSEEK_MODEL, deepseek_stream

OUT = Path("demo_out")
WORKSPACE = OUT / "workspace"
SESSION_PATH = OUT / "session.jsonl"
AUDIT_PATH = OUT / "audit.jsonl"
MEMORY_PATH = OUT / "memory.json"
TRACE_PATH = OUT / "trace.json"

SYSTEM_PROMPT = (
    "你是一个 coding 智能体，在本地文件系统上工作。"
    "使用提供的工具（read/write/edit/bash）完成任务，先想清楚步骤再调用工具。"
)
TASK = "在当前目录创建一个 hello.py 文件，内容是一个打印 Hello, World! 的 Python 程序。"


def _print_message(m) -> None:
    if m.role == "user":
        print(f"[user] {m.content}")
    elif m.role == "assistant":
        for c in m.content:
            if c.type == "text":
                print(f"[assistant] {c.text}")
            elif c.type == "toolCall":
                print(f"[assistant] -> 调用工具 {c.name}({c.arguments})")
    elif m.role == "toolResult":
        text = "".join(c.text for c in m.content if c.type == "text")
        print(f"[tool:{m.toolName}] {text[:200]}")


def _line_count(path: Path) -> int:
    with open(path, encoding="utf-8") as f:
        return sum(1 for _ in f)


async def main() -> None:
    # 重建输出目录
    if OUT.exists():
        shutil.rmtree(OUT)
    WORKSPACE.mkdir(parents=True)

    env = LocalExecutionEnv(cwd=str(WORKSPACE))
    session = Session(JsonlSessionStorage.create(str(SESSION_PATH)))
    governance = Governance(
        allowlist=["read", "write", "edit", "bash"],
        audit_path=str(AUDIT_PATH),
    )
    obs = Observability()

    async def obs_listener(event) -> None:
        if event.type == "agent_start":
            obs.start_span("agent")
        elif event.type == "agent_end":
            obs.end_span()
        elif event.type == "turn_start":
            obs.record("turn_start")
            obs.start_span("turn")
        elif event.type == "turn_end":
            obs.end_span()
        elif event.type == "tool_execution_start":
            obs.record("tool_call_start", tool=event.toolName, args=event.args)
            obs.start_span("tool", tool=event.toolName)
        elif event.type == "tool_execution_end":
            obs.record_tool(event.toolName, event.isError)
            obs.end_span()
        elif event.type == "message_end" and event.message.role == "assistant":
            text = "".join(c.text for c in event.message.content if c.type == "text")
            obs.record("assistant_message", text=text[:200])
            usage = getattr(event.message, "usage", None)
            if usage is not None:
                obs.record_usage(DEEPSEEK_MODEL, usage.prompt_tokens, usage.completion_tokens)

    tools = [create_read_tool(), create_write_tool(), create_edit_tool(), create_bash_tool()]

    harness = AgentHarness(
        stream_fn=deepseek_stream,
        env=env,
        session=session,
        harness_tools=tools,
        system_prompt=SYSTEM_PROMPT,
        before_tool_call=governance.before_tool_call,
        after_tool_call=governance.after_tool_call,
        event_listeners=[obs_listener],
    )

    print(f"[demo] 任务: {TASK}")
    print("[demo] 运行中...\n")

    messages = await harness.prompt(TASK)

    # 长期记忆：从本次会话提取并落盘
    memory_store = JsonMemoryStore(str(MEMORY_PATH))
    for mem in extract_memories(messages, session_id="demo"):
        memory_store.add(mem)

    # 可观测性轨迹落盘
    obs.save(str(TRACE_PATH))

    print("\n[demo] 运行完成，对话消息：\n")
    for m in messages:
        _print_message(m)

    print("\n" + "=" * 50)
    print("[demo] 落盘产物：")
    print(f"  会话记录  {SESSION_PATH}  ({_line_count(SESSION_PATH)} 行)")
    print(f"  审计日志  {AUDIT_PATH}  ({_line_count(AUDIT_PATH)} 行)")
    print(f"  长期记忆  {MEMORY_PATH}")
    print(f"  轨迹      {TRACE_PATH}")
    print(f"  工作目录  {WORKSPACE}")

    hello = WORKSPACE / "hello.py"
    print("\n" + "=" * 50)
    if hello.exists():
        print("[demo] 验证通过：hello.py 已生成")
    else:
        print("[demo] 验证失败：未找到 hello.py")


if __name__ == "__main__":
    asyncio.run(main())
