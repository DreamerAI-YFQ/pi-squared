import asyncio

from pi_agent.harness.env import LocalExecutionEnv
from pi_agent.harness.harness import AgentHarness
from pi_agent.harness.session.memory import InMemorySessionRepo
from pi_agent.harness.session.session import Session
from pi_agent.harness.tools.read import create_read_tool
from pi_agent.providers.faux import faux_stream


def test_harness_prompt_and_persist(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    env.write_file("a.txt", "hello")

    repo = InMemorySessionRepo()
    session = Session(asyncio.run(repo.create()))

    harness = AgentHarness(
        stream_fn=faux_stream,
        env=env,
        session=session,
        harness_tools=[create_read_tool()],
    )

    messages = asyncio.run(harness.prompt("读 a.txt"))

    # 完整 ReAct：user → assistant(toolCall) → toolResult → assistant(最终)
    assert [m.role for m in messages] == ["user", "assistant", "toolResult", "assistant"]

    # 持久化：session 里有 4 条消息 entry
    entries = asyncio.run(session.find_entries())
    assert len(entries) == 4


def test_harness_restores_history(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    env.write_file("a.txt", "hello")

    repo = InMemorySessionRepo()
    storage = asyncio.run(repo.create())
    session = Session(storage)

    harness = AgentHarness(
        stream_fn=faux_stream,
        env=env,
        session=session,
        harness_tools=[create_read_tool()],
    )
    asyncio.run(harness.prompt("读 a.txt"))

    # 第二次 prompt 会从 session 恢复历史（faux 看到 toolResult 会返回最终回答）
    messages2 = asyncio.run(harness.prompt("继续"))
    # 历史被恢复，新 prompt 追加
    assert len(messages2) > 4
