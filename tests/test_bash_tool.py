import asyncio

from pi_agent.harness.env import LocalExecutionEnv
from pi_agent.harness.tools.bash import create_bash_tool
from pi_agent.harness.tools.types import ToolContext, bind_tool


def test_bash_exec(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    tool = bind_tool(create_bash_tool(), ToolContext(env=env))

    result = asyncio.run(tool.execute("id", {"command": "echo hello"}))

    assert "hello" in result.content[0].text
