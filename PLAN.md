# pi 智能体核心 Python 复现规划书（v3，ETCLOVG 七层对齐版）

> 目标：以 [earendil-works/pi](https://github.com/earendil-works/pi) 为骨架，用 Python **忠于 pi 地复现**其智能体核心，同时**补齐 ETCLOVG 七层**（pi 薄弱/缺失的层做出"特色 PI"），并引入 LangChain / LangGraph 对比学习。
>
> 学习理念：**先原理后框架**。定位：**忠于 pi + 加强 pi + 做出特色 PI**。
>
> 本版基于对 `packages/agent/src` 全部 60 个源文件 + `packages/ai/src` 核心抽象的逐文件阅读，并对照综述论文《Agent Harness Engineering: A Survey》的 **ETCLOVG 七层分类体系**。

---

## 1. 项目概述

| 项 | 内容 |
|---|---|
| 参考项目 | earendil-works/pi（`packages/agent` = agent-core） |
| 对齐框架 | **ETCLOVG**（执行/工具/上下文/生命周期/可观测性/验证/治理 七层） |
| 语言 | Python 3.11（miniconda `myenv`） |
| 核心依赖 | pydantic v2、asyncio（标准库） |
| 对比框架 | LangChain、LangGraph |
| 项目路径 | `C:\Users\60920\Desktop\PI\compared_pi_python` |

**定位一句话**：pi 是"重运行时、轻治理/评估"的项目；我们**忠实复现 pi 的运行时核心（E/T/C/L），并补强 pi 缺失的 O/V/G 三根控制平面支柱**，做出一个七层齐备的"特色 PI"。

---

## 2. 参考项目结构（完整源码清单）

`packages/agent/src` 共 60 个源文件，分两大块（详见 §3 逐文件对照）：

```text
packages/agent/src/
├── 顶层（8 个）
│   ├── types.ts / agent-loop.ts / agent.ts / stream-fn.ts / index.ts
│   ├── node.ts / proxy.ts          # 长尾
│   └── search/                     # 会话搜索
└── harness/（约 50 个）
    ├── types.ts / result.ts / events.ts / messages.ts
    ├── system-prompt.ts / prompt-templates.ts
    ├── reducer.ts          # 恢复协议（用户要求实现）
    ├── telemetry.ts        # 长尾
    ├── agent-harness.ts            # 编排层（大量未实现骨架）
    ├── compaction/                 # 上下文压缩
    ├── env/nodejs.ts               # 平台适配（长尾）
    ├── session/                    # 会话（types/state/session/memory/context + jsonl）
    ├── tools/                      # bash/read/write/edit/...
    └── utils/                      # truncate / shell-output
```

`packages/ai/src` 约 190 个文件，自写流式层只涉及核心抽象（§3.3）。

---

## 3. 严谨对照表：pi 源码 → 复现映射

### 3.1 packages/agent 顶层

| pi 文件 | 职责 | 判定 | 复现映射 |
|---|---|---|---|
| `types.ts` | 类型契约 | ✅ 核心 | ✅ `types.py` |
| `agent-loop.ts` | 无状态 ReAct 循环 | ✅ 核心 | ✅ `agent_loop.py` |
| `agent.ts` | 有状态 Agent | ✅ 核心 | ⬜ `agent.py`（P0） |
| `stream-fn.ts` | 流函数注入 | ✅ 核心 | ✅ `stream_fn.py` |
| `index.ts` | barrel 出口 | ➖ 转发 | 简化 |
| `search/*` | 会话搜索 | ✅ 核心 | ⬜ P3 |
| `node.ts` / `proxy.ts` | 平台入口/代理 | ❌ 长尾 | 跳过 |

### 3.2 packages/agent/harness

| pi 文件 | 判定 | 复现映射 |
|---|---|---|
| `types.ts`（公共抽象） | ✅ 核心 | ⬜ P2 |
| `result.ts`（Result/TaggedError） | ✅ 核心 | ⬜ P2 |
| `events.ts`（事件总线） | ✅ 核心 | ⬜ P2 |
| `messages.ts`（convertToLlm） | ✅ 核心 | ⬜ P2 |
| `system-prompt.ts`（skills 注入） | ✅ 核心 | ⬜ P2 |
| `prompt-templates.ts`（占位符） | ⚠️ 混合 | ⬜ P2（占位符手写，加载简化） |
| `reducer.ts`（恢复协议） | ✅ 核心 | ⬜ 实现（用户要求，不跳过） |
| `telemetry.ts`（schema） | ❌ 长尾 | 跳过（O 层另有特色加强） |
| `agent-harness.ts`（编排） | ⚠️ 混合 | ⬜ P4（按需实现接口） |
| `compaction/*`（压缩+分支摘要） | ✅ 核心 | ⬜ P3 |
| `env/nodejs.ts`（平台适配） | ❌ 长尾 | Python 原生替代 |
| `session/*`（会话） | ✅ 核心 | ⬜ P3（先内存版，jsonl 简化） |
| `session/testing/conformance.ts` | ❌ 长尾 | 当验收清单参考 |
| `tools/*`（工具集） | ✅ 核心 | ⬜ P3 |
| `tools/path-utils.ts` | ❌ 长尾 | 简化 |
| `utils/truncate.ts` / `shell-output.ts` | ✅ 核心 | ⬜ P3 |

### 3.3 packages/ai（自写流式层）

| pi 文件 | 判定 | 复现映射 |
|---|---|---|
| `types.ts`（消息/事件/工具契约） | ✅ 核心 | 部分已做，P1 补事件协议 |
| `utils/event-stream.ts` | ✅ 核心 | ⬜ P1 |
| `utils/json-parse.ts`（流式 JSON） | ✅ 核心 | ⬜ P1 |
| `utils/abort.ts` | ✅ 核心 | ⬜ P1 |
| `utils/retry.ts` + `provider-retry.ts` | ✅ 核心 | ⬜ P1 |
| `api/anthropic-messages.ts`（手写 SSE） | ✅ 核心 | ⬜ P1 |
| `api/openai-completions.ts` / `openai-responses.ts` | ✅ 核心 | ⬜ P1 |
| `providers/*`、OAuth、图片、compat、deferred | ❌ 长尾 | 跳过 |

---

## 4. ETCLOVG 七层覆盖与来源（本版核心）

> 这是"忠于 pi + 加强 pi"的落点。**「复现」= pi 已有，照搬；「特色」= pi 缺失/薄弱，我们自建。**

| 层 | 论文核心内容 | pi 有什么（复现基础） | 我们的"特色加强" |
|---|---|---|---|
| **E 执行环境** | 沙箱安全/可复现/活性、可替换后端 | `ExecutionEnv`（fs+shell，无沙箱） | **沙箱抽象层**（Sandbox 接口 + 本地/子进程实现，可插拔） |
| **T 工具接口** | MCP、工具描述/发现/选择、schema 标准 | `AgentTool` + 工具集 + typebox schema | **MCP 客户端**（把 MCP server 工具包装成 AgentTool） |
| **C 上下文** | 短/中/长期记忆、压缩、检索 | compaction + session + convertToLlm + system-prompt | **长期记忆**（简单检索层，JSON/向量） |
| **L 生命周期** | 单循环/多智能体/完整流水线、状态管理 | `agent-loop`(单循环) + Agent + agent-harness | **子智能体**（sub-agent）模式 |
| **O 可观测性** | 轨迹 span 树、成本追踪、AgentOps | `events.ts`(事件总线) + `telemetry.ts`(schema) | **轨迹记录** + **token/成本追踪** + 可观测性接口 |
| **V 验证** | 任务落地、轨迹评估、失败归因、回归 | `conformance.ts`(测试) | **评估 harness**（任务→结果→失败归因） |
| **G 治理** | 权限模型、生命周期钩子、章程、审计 | `beforeToolCall/afterToolCall`(弱钩子) | **权限模型** + **审计日志(JSONL)** + 声明式配置 |

**结论**：E/T/C/L 以复现 pi 为主（各加一个特色点），O/V/G 以自建为主（pi 基本空白，是我们的特色所在）。

---

## 5. 核心原理 vs 长尾问题

### 5.1 核心原理（20 项，手写复现）
1. ReAct 循环　2. 消息模型+判别联合　3. 工具定义+参数校验　4. 事件协议+事件总线　5. 依赖注入　6. 有状态 Agent+队列　7. Result/TaggedError　8. convertToLlm　9. 上下文压缩　10. 分支摘要　11. 会话状态机+门面+内存后端　12. entry→上下文还原　13. JSONL 追加日志+重放　14. 工具集语义　15. skills 注入　16. 会话搜索　17. SSE 流式解析　18. tool-call 增量　19. 重试退避　20. 流式事件协议

### 5.2 长尾（跳过/简化）
几十个 provider、OAuth、图片/constrained/deferred、完整错误正则表、`telemetry.ts`（已用 Observability 替代）、`env/nodejs.ts`（Python 原生替代）、`path-utils.ts`、JSONL 生产细节。

---

## 6. 技术栈映射

| pi (TS) | Python |
|---|---|
| typebox | pydantic v2 |
| 判别联合 | `Field(discriminator=...)` |
| EventStream | `asyncio.Queue` / async generator |
| AbortSignal | `asyncio.CancelledError` |
| StreamFn | `Callable[[Context], Awaitable]` |
| Result/TaggedError | `Result` dataclass + 带 tag 异常 |
| ExecutionEnv | `Protocol` + `os/pathlib/subprocess` |
| parseStreamingJson | 手写 + `json`/`partial-json` |

---

## 7. 分阶段计划

```text
P0 核心运行时    → 最小 ReAct 闭环（L+T+C 基础）
P1 自写流式层    → SSE + 2 provider + 重试退避（T 协议 + O 重试）
P2 harness 基础设施 → Result/事件总线/convertToLlm/system-prompt
P3 harness 能力层 → 工具集+会话+压缩+skills（T/C/E 平台）
P4 编排层        → AgentHarness（L）
P5 ETCLOVG 加强层 → O/V/G 自建 + E/T/C/L 特色
P6 框架对比复盘  → LangGraph/LangChain + 差距清单
```

### P0：智能体核心运行时
对应 `types.ts`/`agent-loop.ts`/`stream-fn.ts`/`agent.ts`。
✅ 全部完成：types / events / stream_fn / faux / agent_loop / agent。

### P1：自写流式层
对应 `ai/types.ts`(事件协议)、`event-stream.ts`、`json-parse.ts`、`abort.ts`、`retry.ts`、`provider-retry.ts`、`anthropic-messages.ts`(SSE)、`openai-completions.ts`。
内容：流式事件协议、EventStream、SSE 手写解析、部分 JSON、tool-call 增量、2 provider、重试退避。

### P2：harness 基础设施
对应 `harness/types.ts`/`result.ts`/`events.ts`/`messages.ts`/`system-prompt.ts`/`prompt-templates.ts`。
内容：Result/TaggedError、事件总线、convertToLlm、system-prompt、prompt 模板占位符。

### P3：harness 能力层
对应 `session/*`、`tools/*`、`compaction/*`、`skills.ts`、`search/*`、`utils/*`。
内容：ExecutionEnv、工具集、会话持久化、JSONL、上下文压缩、分支摘要、skills、会话搜索。

### P4：编排层
对应 `agent-harness.ts`（按需实现接口）。
内容：AgentLane/AgentHarness 接口、steering/followUp 完整化、组装 agent+tools+session+compaction。

### P5：ETCLOVG 特色层（分 6 个子阶段）

按「依赖 + 复杂度」排序：

| 序 | 子阶段 | 层 | 复杂度 | 核心交付 | 状态 |
|---|---|---|---|---|---|
| ① | 治理 | G | 轻 | before/after 钩子 + 权限 + 审计 | ✅ |
| ② | 沙箱 | E | 中 | Sandbox 接口 + 本地实现 | ✅ |
| ③ | 可观测性 | O | 中 | 轨迹记录 + 成本追踪 | ✅ |
| ④ | 评估 | V | 中 | 评估 harness + 失败归因 | ✅ |
| ⑤ | 长期记忆 | C | 中 | 跨会话检索层 | ✅ |
| ⑥ | MCP | T | 重 | MCP 客户端 + 工具包装 | ✅ |

**① G 治理**（`harness/governance.py` + 改 `agent_loop.py`）
- `agent_loop.py` 补 `beforeToolCall` / `afterToolCall` 钩子
- 权限模型：allowlist/denylist（工具名、路径）
- 审计日志：JSONL 记录每次工具调用

**② E 沙箱**（`extensions/sandbox/`）
- `Sandbox` 接口（抽象）+ 本地实现（子进程 + 临时目录隔离）
- 集成：bash 工具改成在沙箱里执行

**③ O 可观测性**（`extensions/observability/`）
- 轨迹记录：结构化 span/事件日志（LLM 调用、工具调用、耗时）
- 成本追踪：token 用量 + 成本累加

**④ V 评估**（`extensions/eval/`）
- 评估 harness：任务定义 → 运行 → 结果 → 失败归因
- 回归：失败轨迹转回归用例

**⑤ C 长期记忆**（`extensions/memory/`）
- 记忆存储 + 提取 + 检索（跨会话）

**⑥ T MCP**（`extensions/mcp/`）
- MCP 客户端（JSON-RPC）+ 把 MCP tools 包装成 `AgentTool`

### P6：框架对比复盘（含 L 多智能体）
用 LangGraph 重写 agent loop（含多智能体编排）、LangChain 重写工具层，产出《手写 vs 框架差距清单》+ 开发实录。

---

## 8. 最终目录结构

```text
compared_pi_python/
├── pyproject.toml
├── PLAN.md
├── src/pi_agent/
│   ├── types.py / events.py / stream_fn.py / agent_loop.py   # ✅
│   ├── agent.py                # ✅ P0
│   ├── providers/              # ✅ faux + openai(DeepSeek)
│   ├── streaming/              # ✅ event_stream/sse/json_parse/tool_call
│   ├── harness/
│   │   ├── result.py           # ✅ P2（Result 错误处理范式）
│   │   ├── events.py           # ⬜ P2（事件总线）
│   │   ├── env.py / messages.py / system_prompt.py / prompt_templates.py  # ⬜P2/P3
│   │   ├── skills.py / tools/ / session/ / compaction/ / search/          # ⬜P3
│   │   └── harness.py          # ⬜P4
│   └── extensions/             # ⬜P5 特色层
│       ├── sandbox/            # E 沙箱抽象
│       ├── mcp/                # T MCP 客户端
│       ├── memory/             # C 长期记忆
│       ├── observability/      # O 轨迹+成本
│       ├── eval/               # V 评估 harness
│       └── governance/         # G 权限+审计
└── tests/                      # 每阶段追加
```

---

## 9. 验收标准

1. **P0**：最小 ReAct 闭环跑通，`Agent` 可交互。
2. **P1**：真实 OpenAI/Anthropic 流式 + tool-call 增量 + 重试退避。
3. **P2**：Result/事件总线/convertToLlm/system-prompt 独立可用。
4. **P3**：工具读写文件、会话持久化/恢复、超长对话压缩、skill 加载。
5. **P4**：端到端 coding 任务跑通。
6. **P5**：**ETCLOVG 七层均有可运行的最小实现**（O/V/G 是特色）。
7. **P6**：产出《手写 vs 框架差距清单》+ 开发实录。

---

## 10. 当前进度

| 阶段 | 状态 |
|---|---|
| P0 | ✅ 完成（最小 ReAct 闭环 + Agent 类） |
| P1 | ✅ 完成（流式基础设施 + 真实 DeepSeek provider + 重试退避） |
| P2 | ✅ 完成（Result/事件总线/convertToLlm/system-prompt/prompt 模板） |
| P3 | ✅ 完成（ExecutionEnv + 工具集 + session + compaction + skills + search） |
| P4 | ✅ 完成（AgentHarness 组装 + steering/followUp 完整化） |
| P5 | ✅ 完成（① 治理 · ② 沙箱 · ③ 可观测性 · ④ 评估 · ⑤ 长期记忆 · ⑥ MCP） |
| P6 | ⬜ 未开始 |

> **补缺（P5 之后）**：重试退避（P1）、子智能体 sub-agent（L）、多 lane 会话树（C/L）、span 树可观测性（O）、prompt 文件加载（P2）均已补齐，见 §5.2 剩余长尾。
