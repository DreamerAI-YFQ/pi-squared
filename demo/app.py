"""Pi² 在线 Demo（Streamlit）——单文件包住 AgentHarness。

部署到 Hugging Face Spaces（Streamlit 模板）即获得公开在线演示：
- 默认 faux provider：无需 API key，返回脚本化的真实工具调用（read a.txt）
- 侧栏填入 DeepSeek key：切换为真实模型
- 会话以 JSONL 持久化在沙箱目录，页面刷新不丢（会话引擎的真实能力）
"""
import asyncio
import os
import tempfile
from pathlib import Path

import streamlit as st

from pi_agent.harness.env import LocalExecutionEnv
from pi_agent.harness.harness import AgentHarness
from pi_agent.harness.session.context import build_session_context
from pi_agent.harness.session.session import Session
from pi_agent.harness.session.storage import JsonlSessionStorage
from pi_agent.harness.tools.bash import create_bash_tool
from pi_agent.harness.tools.edit import create_edit_tool
from pi_agent.harness.tools.read import create_read_tool
from pi_agent.harness.tools.write import create_write_tool

GITHUB_URL = "https://github.com/DreamerAI-YFQ/pi-squared"

SYSTEM_PROMPT = (
    "你是 Pi² 演示智能体，在演示沙箱目录内工作。"
    "优先使用工具（read/write/edit/bash）完成任务，完成后用一句话总结。"
)

st.set_page_config(page_title="Pi² Demo", page_icon="🥧", layout="centered")


# ============ 工具函数 ============

def _text_of(content) -> str:
    """消息 content（str 或 block 列表）→ 纯文本。"""
    if isinstance(content, str):
        return content
    return "".join(b.text for b in content or [] if getattr(b, "type", None) == "text")


def _tool_calls_of(content):
    """assistant content 里的 toolCall 块。"""
    if isinstance(content, str):
        return []
    return [b for b in content or [] if getattr(b, "type", None) == "toolCall"]


def _secret_key() -> str:
    try:
        return st.secrets.get("DEEPSEEK_API_KEY", "") or ""
    except Exception:
        return ""


@st.cache_resource
def _demo_workspace() -> str:
    """每个进程一个演示沙箱：临时目录 + 预置 a.txt，让工具调用有真实结果。"""
    ws = tempfile.mkdtemp(prefix="pi2-demo-")
    Path(ws, "a.txt").write_text("Pi² 演示工作区：你好，世界！\n", encoding="utf-8")
    return ws


def _session_file() -> str:
    return str(Path(_demo_workspace()) / "demo-session.jsonl")


def _stream_fn():
    """provider 选择：有 key 用 DeepSeek，否则 faux（离线可演示）。"""
    key = st.session_state.get("api_key") or _secret_key()
    if key:
        os.environ["DEEPSEEK_API_KEY"] = key
        from pi_agent.providers.openai import deepseek_stream

        return deepseek_stream
    from pi_agent.providers.faux import faux_stream

    return faux_stream


def _build_harness() -> AgentHarness:
    ws = _demo_workspace()
    path = _session_file()
    storage = (
        JsonlSessionStorage.open(path) if Path(path).exists()
        else JsonlSessionStorage.create(path, session_id="demo")
    )
    return AgentHarness(
        stream_fn=_stream_fn(),
        env=LocalExecutionEnv(cwd=ws),
        session=Session(storage),
        harness_tools=[create_read_tool(), create_write_tool(), create_edit_tool(), create_bash_tool()],
        system_prompt=SYSTEM_PROMPT,
    )


async def _load_history() -> list:
    """从 JSONL 恢复历史（页面首次加载 / 刷新时）。"""
    path = _session_file()
    if not Path(path).exists():
        return []
    session = Session(JsonlSessionStorage.open(path))
    entries = sorted(await session.find_entries(), key=lambda e: e.seq)
    return build_session_context(entries)


# ============ UI ============

with st.sidebar:
    st.title("🥧 Pi²")
    st.caption("自研 Agent 运行时内核 · ETCLOVG 七层")
    st.markdown(f"[![GitHub](https://img.shields.io/badge/GitHub-pi--squared-181717)]({GITHUB_URL})")
    st.divider()
    st.session_state["api_key"] = st.text_input(
        "DeepSeek API Key", type="password",
        help="留空使用 faux 演示模型（脚本化工具调用，无需联网）",
    )
    st.divider()
    st.caption("演示运行在临时沙箱目录，会话以 JSONL 持久化，刷新页面不丢。")

st.title("Pi² Agent Demo")
st.caption("试试让它「读取 a.txt」或「写一个 hello.py 并执行」——每一次工具调用都来自手写的 ReAct 内核。")

if "messages" not in st.session_state:
    st.session_state.messages = asyncio.run(_load_history())

user_text = st.chat_input("让智能体做点什么…")

if user_text:
    harness = _build_harness()
    try:
        with st.spinner("agent 运行中…"):
            st.session_state.messages = asyncio.run(harness.prompt(user_text))
    except Exception as exc:  # noqa: BLE001 — 演示页面直接展示错误
        st.error(f"运行失败：{type(exc).__name__}: {exc}")

# 渲染完整消息流（user / assistant / toolResult）
for msg in st.session_state.messages:
    role = msg.role
    if role == "user":
        with st.chat_message("user"):
            st.markdown(_text_of(msg.content))
    elif role == "assistant":
        with st.chat_message("assistant"):
            text = _text_of(msg.content)
            if text:
                st.markdown(text)
            for tc in _tool_calls_of(msg.content):
                st.code(f"{tc.name}({', '.join(f'{k}={v!r}' for k, v in tc.arguments.items())})", language="python")
    elif role == "toolResult":
        with st.chat_message("assistant", avatar="🔧"):
            label = f"{msg.toolName} · {'❌ 失败' if msg.isError else '✅ 完成'}"
            with st.expander(label):
                st.text(_text_of(msg.content)[:2000] or "(空结果)")
