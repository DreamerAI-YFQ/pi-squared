import asyncio

from pi_agent.harness.env import LocalExecutionEnv
from pi_agent.harness.tools.read import create_read_tool
from pi_agent.harness.tools.types import ToolContext, bind_tool


def test_read_file(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    env.write_file("a.txt", "line1\nline2\nline3")
    tool = bind_tool(create_read_tool(), ToolContext(env=env))

    result = asyncio.run(tool.execute("id", {"path": "a.txt"}))
    assert result.content[0].text == "line1\nline2\nline3"


def test_read_with_offset_limit(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    env.write_file("a.txt", "line1\nline2\nline3\nline4")
    tool = bind_tool(create_read_tool(), ToolContext(env=env))

    result = asyncio.run(tool.execute("id", {"path": "a.txt", "offset": 2, "limit": 2}))
    assert result.content[0].text == "line2\nline3"


def test_read_nonexistent_raises(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    tool = bind_tool(create_read_tool(), ToolContext(env=env))

    try:
        asyncio.run(tool.execute("id", {"path": "nope.txt"}))
        assert False, "应该抛异常"
    except Exception:
        pass
