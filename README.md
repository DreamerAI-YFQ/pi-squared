# Pi² (pi-squared)

> 从 [earendil-works/pi](https://github.com/earendil-works/pi) 出发，对其智能体核心进行**忠于原作的 Python 复现**与**针对性增强**。
>
> 补齐 ETCLOVG 七层架构，构建一个 principle-first、runtime-complete 的 Agent 内核。

---

## 一句话定位

**Pi² = pi 的运行时核心 + 缺失的控制平面。**

pi 长于事件驱动、流式 ReAct 与会话状态机，但在可观测性（O）、验证（V）、治理（G）三层相对薄弱。Pi² 在忠实复现 pi 的 E/T/C/L 四层运行时的同时，自建 O/V/G 三根支柱，使七层齐备、可运行、可评估、可审计。

---

## 为什么叫 Pi²

- `pi`：底座，代表对原作智能体运行时的尊重与复现。
- `²`：二次增强——把单薄的运行时平方为一个**有控制平面的完整 Agent OS**。

---

## ETCLOVG 七层覆盖

| 层 | 英文名 | 核心能力 | Pi² 实现 |
|---|---|---|---|
| **E** | Execution Environment | 沙箱、安全执行、可替换后端 | `Sandbox` 抽象 + 本地/子进程实现 |
| **T** | Tool Interface | 工具定义、发现、调用、MCP | 内置工具集 + **MCP 客户端**（把 MCP Server 包装为 AgentTool） |
| **C** | Context | 短/中/长期记忆、压缩、检索 | Session 状态机 + 上下文压缩 + **长期记忆检索** |
| **L** | Lifecycle | ReAct 循环、多智能体、流水线 | 有状态 `Agent` + `AgentHarness` + **Sub-Agent** |
| **O** | Observability | 轨迹、span 树、成本追踪 | `Observability`：事件/span/token/成本 |
| **V** | Verification | 任务落地、轨迹评估、失败归因 | `EvalHarness`：运行→评分→回归用例 |
| **G** | Governance | 权限、钩子、审计、章程 | `Governance`：allowlist/denylist + JSONL 审计日志 |

---

## 核心特性

- **手写 ReAct 循环**：不依赖 LangChain/LangGraph，先理解原理再对比框架。
- **流式事件协议**：自写 SSE 解析、tool-call 增量、partial JSON 处理、指数退避重试。
- **有状态 Agent**：内部队列 + 事件总线，支持 steering、follow-up、会话恢复。
- **会话持久化**：JSONL 追加日志 + entry 重放，支持多 lane 会话树。
- **工具集**：bash、read、write、edit，全部带 schema 校验与结果包装。
- **可观测性**：span 树、事件轨迹、token/成本累计，可落盘为 JSON。
- **评估 Harness**：任务定义 → 运行 → 结果 → 失败归因 → 回归测试。
- **MCP 客户端**：把任意 MCP Server 的工具接入 Agent。

---

## 安装

```bash
# Python >= 3.11
pip install -e .
```

如果你需要运行真实 LLM provider，准备 `.env`：

```bash
DEEPSEEK_API_KEY=your_key
```

没有 key 也能跑：网关会自动降级到 faux provider（模拟演示）。
`.env` 已被 `.gitignore` 忽略，不会进入仓库。

---

## Web UI

一条命令启动本地网关，浏览器即可使用：

```bash
pi-squared serve          # 默认 http://127.0.0.1:8000
```

- **单进程**：FastAPI 同时提供前端静态页、REST API 与 SSE 事件流。
- **会话管理**：多会话、历史恢复（从 JSONL 重放）。
- **实时事件流**：Agent 的每一步（工具调用、执行结果、回合结束）以 SSE 事件驱动 UI。
- **本地落盘**：会话 JSONL 与工作区文件全部写入本机数据目录（默认 `~/.pi-squared/`）。

```text
浏览器 ── HTTP/SSE ──► FastAPI 网关 ──► pi_agent 核心 ──► 本机文件系统
```

前端（`web/`，React + TypeScript）二次开发：

```bash
cd web
npm install
npm run dev       # Vite 开发服务器，/api 代理到 127.0.0.1:8000
npm run build     # 产物 web/dist 由 pi-squared serve 直接托管
```

---

## 快速开始

```python
import asyncio
from pi_agent.agent import Agent
from pi_agent.providers.faux import FauxProvider

async def main():
    agent = Agent(
        name="pi-squared-demo",
        provider=FauxProvider(),  # 模拟 provider，可替换为 openai
    )
    result = await agent.run("Hello, Pi²!")
    print(result)

asyncio.run(main())
```

完整示例见 [`examples/demo_deepseek.py`](examples/demo_deepseek.py)。

---

## 运行测试

```bash
python -m pytest
```

当前已覆盖 ReAct 循环、事件流、工具集、会话、可观测性、评估、治理、MCP 等模块。

---

## 项目结构

```text
src/pi_agent/
├── types.py / events.py / stream_fn.py / agent_loop.py  # 核心运行时
├── agent.py                   # 有状态 Agent
├── providers/                 # faux / openai(DeepSeek)
├── streaming/                 # SSE / json_parse / tool_call / retry
├── harness/
│   ├── result.py / events.py / messages.py
│   ├── env.py / system_prompt.py / prompt_templates.py
│   ├── skills.py / tools/ / session/ / compaction/ / search/
│   ├── subagent.py            # 子智能体作为工具
│   └── harness.py             # 编排层
└── extensions/
    ├── sandbox.py             # E 沙箱
    ├── mcp.py                 # T MCP 客户端
    ├── memory.py              # C 长期记忆
    ├── observability.py       # O 可观测性
    ├── eval.py                # V 评估
    └── governance.py          # G 治理

src/pi_agent/server/           # Web 网关（FastAPI + SSE）
web/                           # Web UI（React + TypeScript + Vite）
tests/                         # 各阶段对应测试
```

---

## 设计哲学

> **先原理，后框架。**

每一层都先手写核心机制，再与 LangChain / LangGraph 对比，理解框架到底替你做了什么、省略了什么、约束了什么。最终产出《手写 vs 框架差距清单》。

---

## 当前状态

- ✅ P0 核心运行时
- ✅ P1 自写流式层 + 真实 provider + 重试退避
- ✅ P2 harness 基础设施
- ✅ P3 工具集 / 会话 / 压缩 / skills
- ✅ P4 AgentHarness 编排
- ✅ P5 ETCLOVG 七层特色加强（O/V/G + E/T/C/L 增强点）
- ⬜ P6 框架对比复盘（LangChain / LangGraph）

---

## 致谢

- [earendil-works/pi](https://github.com/earendil-works/pi)：项目骨架与运行时设计来源。
- 《Agent Harness Engineering: A Survey》：ETCLOVG 七层分类体系。

---

## License

MIT
