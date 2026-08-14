import asyncio

from pi_agent.harness.env import LocalExecutionEnv
from pi_agent.harness.tools.edit import create_edit_tool
from pi_agent.harness.tools.types import ToolContext, bind_tool


def test_edit_replace(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    env.write_file("a.txt", "hello world\nfoo bar")
    tool = bind_tool(create_edit_tool(), ToolContext(env=env))

    asyncio.run(
        tool.execute(
            "id",
            {"path": "a.txt", "edits": [{"old_text": "world", "new_text": "there"}]},
        )
    )

    r = env.read_text_file("a.txt")
    assert r.value == "hello there\nfoo bar"


def test_edit_non_unique_raises(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    env.write_file("a.txt", "foo foo")
    tool = bind_tool(create_edit_tool(), ToolContext(env=env))

    try:
        asyncio.run(
            tool.execute(
                "id",
                {"path": "a.txt", "edits": [{"old_text": "foo", "new_text": "bar"}]},
            )
        )
        assert False, "应该抛异常"
    except Exception:
        pass


def test_edit_not_found_raises(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    env.write_file("a.txt", "hello")
    tool = bind_tool(create_edit_tool(), ToolContext(env=env))

    try:
        asyncio.run(
            tool.execute(
                "id",
                {"path": "a.txt", "edits": [{"old_text": "nonexistent", "new_text": "x"}]},
            )
        )
        assert False, "应该抛异常"
    except Exception:
        pass
