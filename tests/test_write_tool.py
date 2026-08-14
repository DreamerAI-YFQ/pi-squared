import asyncio

from pi_agent.harness.env import LocalExecutionEnv
from pi_agent.harness.tools.types import ToolContext, bind_tool
from pi_agent.harness.tools.write import create_write_tool


def test_write_file(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    tool = bind_tool(create_write_tool(), ToolContext(env=env))

    result = asyncio.run(tool.execute("id", {"path": "out.txt", "content": "hello world"}))

    r = env.read_text_file("out.txt")
    assert r.value == "hello world"
    assert "out.txt" in result.content[0].text


def test_write_creates_parent_dirs(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    tool = bind_tool(create_write_tool(), ToolContext(env=env))

    asyncio.run(tool.execute("id", {"path": "sub/dir/out.txt", "content": "x"}))

    r = env.read_text_file("sub/dir/out.txt")
    assert r.value == "x"
