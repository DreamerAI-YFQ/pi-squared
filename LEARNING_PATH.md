# Pi² 源码学习路线（从零到全貌）

> 对象：`src/pi_agent`，55 个文件、3736 行，配套 43 个测试文件（166 个用例）。
> 原则：**先原理后框架**——每个概念先在裸层面理解，再看它在系统里的位置。
> 方法：**先跑后读、读改结合**——每个阶段都以"测试全绿 + 能回答自测问题"为通过标准。

---

## 0. 总体地图：先建立空间感

### 0.1 分层依赖图（箭头 = "被谁使用"）

```
                    server/  (HTTP/SSE 服务层，614 行)
                      │
                    harness/ (编排层，门面+治理+压缩+子代理，523 行)
                      │
        ┌─────────────┼──────────────────┐
        │             │                  │
   session/       tools/            (compaction/
   持久化 702 行   工具 159 行        subagent/...)
   + reducer 199      │
        │             │
        │           env.py + result.py  (执行环境，200 行)
        │             │
        └──────┬──────┘
               │
          agent_loop.py + agent.py  (核心循环，221 行)
               │
          stream_fn.py (5 行签名) ← providers/ (209 行：faux + deepseek)
               │
          streaming/ (187 行：SSE/增量JSON/重试)
               │
          types.py + events.py (155 行：数据模型，最底层)

  extensions/ (562 行，横切特色层：沙箱/MCP/记忆/可观测/评估)
```

### 0.2 四个"接缝"（贯穿全项目的核心设计）

| 接缝 | 一句话 | 出现阶段 |
|---|---|---|
| `stream_fn` | "问一次模型"打包成可替换函数 | 阶段 2 |
| `env` + `Result` | 碰世界（文件/shell）的抽象，失败不抛异常 | 阶段 6 |
| `Session` | 会话状态的持久化与重放 | 阶段 7 |
| `Emit`/事件 | 观察者接缝，前端/评估/观测都挂在这 | 阶段 2 |

---

## 阶段 0：跑起来（地基）

**目标**：有一个可运行、可断点的实体，后面所有阅读都在它上面做实验。

**做什么**：
1. 装环境：项目根目录 `.venv`，`pip install -e .`
2. 跑测试：`.venv\Scripts\python.exe -m pytest tests/ -q` → 166 passed
3. 起服务：`.venv\Scripts\pi-squared.exe serve`（无 API key 时自动用 faux 假模型，完全离线）
4. 用 curl 或浏览器发一条消息，亲眼看一次完整响应

**通过标准**：测试全绿 + 服务能起 + 你亲手发出过一条消息。

---

## 阶段 1：数据模型层——学会这门语言的"词汇"（155 行）

**目标**：三级消息体系烂熟于心。后面每个文件都在用这套词汇。

**阅读顺序**：

| 文件 | 行数 | 重点 |
|---|---|---|
| `src/pi_agent/types.py` | 103 | 自底向上四层：内容块（Text/Image/ToolCall）→ 消息（User/Assistant/ToolResult）→ `Message` 联合类型（`Field(discriminator="role")` 自动判别）→ AgentContext/AgentTool |
| `src/pi_agent/events.py` | 52 | 循环会发出哪些事件（AgentStart/TurnStart/MessageStart/ToolExecutionStart...） |

**关键概念**：
- `StopReason`：7 种停机原因，是**循环控制的钥匙**——`toolUse` 继续循环，`stop/length/error/aborted` 退出
- `AgentTool.execute` 的签名：`(tool_call_id, params) -> AgentToolResult`——记住它，阶段 6 会看到它的变体

**动手**：跑 `pytest tests/test_types.py tests/test_events.py -v`

**自测问题**：
1. AssistantMessage 和 ToolResultMessage 是怎么"配对"的？（toolCallId）
2. 为什么 Message 要用 discriminator 而不是一个大杂烩类？
3. stopReason="deferred" 意味着什么？（提示：deferred 写入，阶段 7 会用到）

---

## 阶段 2：最小闭环——手写 ReAct 循环（243 行，全项目的心脏）

**目标**：完全理解"循环怎么转起来"。这是最重要的一阶段。

**阅读顺序**：

| 文件 | 行数 | 重点 |
|---|---|---|
| `src/pi_agent/stream_fn.py` | 5 | 全部内容就一行：`StreamFn = Callable[[AgentContext], Awaitable[AssistantMessage]]`。想清楚：它不是流式实现，是"问一次模型"的契约 |
| `src/pi_agent/providers/faux.py` | 17 | 假模型：看最后一条消息类型决定返回 ToolCall 还是最终回答。**先读它**，因为它是最小可用的 stream_fn |
| `src/pi_agent/agent_loop.py` | 129 | 核心循环。逐行精读，见下方拆解 |
| `src/pi_agent/agent.py` | 92 | Agent 类：把 loop 包一层，加 Listener（事件订阅） |

**agent_loop.py 精读地图**：
- 第 54-59 行：合并历史 + 新消息成 `current`
- 第 71-75 行：双层循环——外层处理 follow-up（停止后又来消息），内层处理工具调用 + steering（运行中插话）
- 第 91 行：`await config.stream_fn(current)` —— 全文唯一的"问模型"
- 第 98 行：从 content 里挑出 ToolCall（`isinstance(c, ToolCall)`）
- 第 104-124 行：逐个执行工具 → ToolResultMessage 回填 → `has_more_tool_calls=True` 再转一圈
- 第 142-185 行 `execute_tool_call`：找工具 → pydantic 校验参数 → before 钩子（可阻断）→ 执行 → after 钩子（可覆写）

**动手**：
1. `pytest tests/test_agent_loop.py tests/test_agent.py -v`
2. 改 `faux.py`：让假模型第一轮调两次工具、第二轮才回答，观察测试和 emit 时序的变化
3. **画一张 emit 事件时序图**（AgentStart→TurnStart→MessageStart→...→AgentEnd）

**自测问题**：
1. 为什么是双层 while 而不是单层？（steering 和 follow-up 的区别）
2. `execute_tool_call` 里参数校验失败会发生什么？工具抛异常呢？
3. 如果模型一次返回两个 ToolCall，执行顺序和消息顺序是什么？

---

## 阶段 3：流协议层——裸协议课（187 行）

**目标**：理解"流式"到底发生在哪、怎么解析。这正是"先原理"的部分：协议本身。

**阅读顺序**（每个文件都很小，逐个吃透）：

| 文件 | 行数 | 对应的"原理" |
|---|---|---|
| `streaming/sse.py` | 31 | SSE 协议：`data:`/`event:` 行 + 空行分隔。先读协议文档再看代码 |
| `streaming/json_parse.py` | 52 | 增量 JSON：字符串/对象/数组逐字符状态机 |
| `streaming/tool_call.py` | 18 | 工具参数分片拼装（Accumulator） |
| `streaming/event_stream.py` | 52 | 异步队列事件流：push/end/`async for`，哨兵结束 |
| `streaming/retry.py` | 33 | 指数退避重试 |

**动手**：`pytest tests/test_sse.py tests/test_json_parse.py tests/test_tool_call.py tests/test_event_stream.py tests/test_retry.py -v`

**自测问题**：
1. 为什么 SSE 解析器要忽略 `:` 开头的行？
2. 工具参数为什么必须用 Accumulator 增量拼，不能直接 json.loads？
3. EventStream 为什么用 `object()` 哨兵而不是 None？

---

## 阶段 4：真实模型接入——对照 faux 看真实现（191 行）

**目标**：看清"同一个签名下的两种人生"。

**阅读**：`providers/openai.py`（191 行），对照你已读的 faux.py（17 行）。

**精读地图**：
- `_to_openai_messages`：内部消息 → OpenAI 格式（ToolResultMessage 变成 `role:"tool"`）
- `_to_openai_tools`：AgentTool → JSON Schema（pydantic 的 `model_json_schema()`）
- `_fetch_sse`：httpx 流式请求
- `deepseek_stream` 主函数：重试 → SSE 解析 → 文本累积 + ToolCallAccumulator → 组装 AssistantMessage
- 注意第 147-152 行的 docstring：**"对外保持 StreamFn 签名，agent_loop 无需改动"**——这就是接缝的价值

**动手**：配 `.env`（DEEPSEEK_API_KEY），起服务真问一次；没 key 就读 `tests/` 里 mock 的方式。

**自测问题**：
1. 从 faux 换成 deepseek，agent_loop 改了几行？（0 行）
2. 429 错误会怎样？重试几次、间隔多少？
3. usage 是从哪个 chunk 里拿的？

---

## 阶段 5：执行环境与工具——怎么"碰世界"（359 行）

**目标**：理解 Result 模式和延迟绑定。

**阅读顺序**：

| 文件 | 行数 | 重点 |
|---|---|---|
| `harness/result.py` | 36 | Result 模式：`ok/err`，失败编码进返回值，**绝不抛异常** |
| `harness/env.py` | 164 | FileSystem/Shell Protocol（本地实现）；`decode_output` 的 UTF-8→GBK 回退（Windows 中文课） |
| `harness/tools/types.py` | 33 | HarnessTool vs AgentTool 的区别：execute 多一个 context 参数；`bind_tool` 延迟绑定 env |
| `harness/tools/read.py` → `write.py` → `edit.py` → `bash.py` | 35/24/40/26 | 四个工具全是"委托 env"的薄壳。重点看 edit 的 old_text 唯一性校验 |

**动手**：`pytest tests/test_result.py tests/test_env.py tests/test_read_tool.py tests/test_write_tool.py tests/test_edit_tool.py tests/test_bash_tool.py -v`

**自测问题**：
1. 工具为什么不直接 `open()` 文件？（换沙箱/远程 env 时会发生什么）
2. edit 为什么要求 old_text 在文件中恰好出现一次？
3. `bind_tool` 返回的闭包捕获了什么？

---

## 阶段 6：会话持久化——记忆与恢复（901 行，最重的硬骨头）

**目标**：理解 Entry/Record 双轨、seq 状态机、崩溃恢复。分两步走。

### 6a. 数据模型与状态机

| 文件 | 行数 | 重点 |
|---|---|---|
| `harness/session/types.py` | 196 | **Entry（7 种，存内容） vs Record（9 种，存过程）**——双轨观是一切的基础 |
| `harness/session/state.py` | 172 | `apply_mutation`：seq 必须连续（`seq != self._sequence + 1` 即拒），重放恢复的地基 |

### 6b. 存储后端与上下文还原

| 文件 | 行数 | 重点 |
|---|---|---|
| `harness/session/memory.py` | 57 | 内存版（先读，最简单） |
| `harness/session/jsonl.py` | 109 | 7 Entry + 9 Record 的编解码 |
| `harness/session/storage.py` | 89 | JSONL 版：追加写盘 + `open()` 逐行重放。注意 create/open 的区别（历史遗留 bug 的教训） |
| `harness/session/session.py` | 52 | 门面 |
| `harness/session/context.py` | 26 | Entry 序列 → LLM 上下文（compaction/branch_summary 怎么进上下文） |

### 6c. 崩溃恢复（reducer）

| 文件 | 行数 | 重点 |
|---|---|---|
| `harness/reducer.py` | 199 | `validate_record_log`：12 种 corruption 检测逐个过一遍；`reduce_lane_state`：从 record log 重建编排状态 |

**动手**：
1. `pytest tests/test_session_types.py tests/test_session_state.py tests/test_session.py tests/test_jsonl.py tests/test_session_context.py tests/test_reducer.py -v`
2. **手工实验**：写一个脚本，用 `JsonlSessionStorage.create()` 建会话、append 几条消息，然后打开 session.jsonl 看每一行；再写个新进程用 `open()` 重放，验证状态还原
3. 故意把 jsonl 里某行的 seq 改掉，看 `open()` 抛什么错

**自测问题**：
1. Entry 和 Record 为什么分开存？崩溃恢复时各自扮演什么角色？
2. seq 为什么必须连续？不连续意味着什么？
3. `multiple_open_operations` 这种 corruption 说明运行时发生过什么异常状况？
4. deferred 的 assistant 消息为什么不进 LLM 上下文？（context.py 第 14-16 行）

---

## 阶段 7：编排层——把零件组装成整车（523 行）

**目标**：看清"一次 prompt 的完整生命周期"。

**阅读顺序**（按重要性）：

| 文件 | 行数 | 重点 |
|---|---|---|
| `harness/harness.py` | 69 | 门面 `prompt()` 三步曲：恢复历史 → bind_tool+跑循环 → 持久化新消息 |
| `harness/compaction.py` | 102 | 上下文压缩：什么时候触发、CompactionEntry 怎么生成 |
| `harness/governance.py` | 39 | 工具审批（配合 agent_loop 的 before 钩子） |
| `harness/subagent.py` | 51 | 子代理：把 agent_loop 递归用 |
| `harness/skills.py` | 55 | 技能加载 |
| `harness/system_prompt.py` + `prompt_templates.py` + `messages.py` + `search.py` + `events.py` | 31/86/26/25/37 | 外围，快速过 |

**动手**：`pytest tests/test_harness.py tests/test_compaction.py tests/test_governance.py tests/test_subagent.py tests/test_skills.py -v`

**自测问题**：
1. `AgentHarness.prompt` 的三步分别对应哪些已学模块？
2. 压缩后的会话，下次恢复历史时 LLM 看到的是什么？（compaction entry 的 summary + retained_tail）
3. 审批是怎么"拦截"工具执行的？（before_tool_call 返回 block）

---

## 阶段 8：服务层——暴露给世界（614 行）

**目标**：理解 HTTP/SSE 服务和会话运行时。

**阅读顺序**：

| 文件 | 行数 | 重点 |
|---|---|---|
| `server/runtime.py` | 326 | **先读**：SessionRuntime（会话运行时）、Registry（注册表）、`resolve_stream_fn`（faux/deepseek/auto 三态选择）、SSE 队列推送 |
| `server/app.py` | 121 | HTTP 路由：prompt/审批/SSE 端点 |
| `server/policy.py` | 113 | 审批策略（autoApprove 列表等） |
| `server/cli.py` + `serialize.py` | 31/23 | 收尾 |

**动手**：
1. `pytest tests/test_server.py tests/test_policy.py tests/test_workspace.py tests/test_observability_api.py -v`
2. 起服务后用 curl 观察原始 SSE 流：`curl -N http://127.0.0.1:8000/api/sessions/{id}/events`
3. 杀进程重启，验证会话历史还在（create vs open 的经典教训）

**自测问题**：
1. 一次 prompt 期间，前端能收到哪几种 SSE 事件？和阶段 2 画的事件时序图对得上吗？
2. Registry 怎么防止同一 session 并发跑两个 prompt？

---

## 阶段 9：特色层——五个独立选修模块（562 行，任意顺序）

每个模块都独立、都很小，按兴趣选读：

| 模块 | 行数 | 一句话 | 对应测试 |
|---|---|---|---|
| `extensions/sandbox.py` | 41 | 临时目录+子进程的最小沙箱 | test_sandbox.py |
| `extensions/observability.py` | 82 | span 树 + token 成本追踪 | test_observability.py |
| `extensions/memory.py` | 106 | 跨会话记忆：bigram 检索（不用向量库） | test_memory.py |
| `extensions/mcp.py` | 134 | 手写 MCP 客户端：initialize→tools/list→tools/call | test_mcp.py |
| `extensions/eval.py` | 198 | 评估闭环：轨迹→断言→失败归因→回归用例 | test_eval.py |

**推荐顺序**：eval（复用你阶段 2 学的 emit/轨迹知识）→ mcp（协议课）→ 其余。

---

## 阶段 10：毕业设计——四个动手练习

完成下面任意两个，才算真正"拥有"这套源码：

1. **加一个工具**：仿照 `read.py` 写一个 `glob` 工具（列文件模式匹配），走完 定义→bind→注册→测试 全链路
2. **换一个 provider**：写一个 `ollama_stream`（本地模型）或 `mock_stream`，验证 agent_loop 一行不改
3. **加一种 Entry**：比如 `TagEntry`（给消息打标签），走完 types→jsonl 编解码→state 状态机→context 还原 全链路，体会"加一种数据"要动几层
4. **对照原版**：挑 pi 原版 TS 的 `reducer.ts` 或 `state.ts`，逐段对照 Python 版，记录：哪些简化了、哪些增强了、为什么

---

## 附录 A：阅读技巧

- **遇到 dataclass/pydantic 先看字段**：这个项目里数据结构就是文档，行为都是薄逻辑
- **async 代码读法**：先忽略 await 找控制流主干，再回头看每个 await 在等什么
- **每个模块都先读 docstring**：全项目注释密度高，docstring 基本都说清了"对应 pi 的哪个文件"
- **测试是最好的用法示例**：读不懂某模块时，先看它的测试怎么构造输入

## 附录 B：一条消息的完整旅程（总复习用）

```
用户输入 → server(HTTP) → AgentHarness.prompt
  → session 读 Entry 序列 → context 还原历史
  → bind_tool 注入 env → run_agent_loop
      → stream_fn(第1次) → provider 发请求 → streaming 收 SSE 增量解析
      → ToolCall → 工具(经 env, Result 模式) → ToolResultMessage → 继续循环
      → stream_fn(第2次) → stopReason="stop" → 退出
  → 新消息写回 session(JSONL, seq 连续)
  → 全程 emit 事件 → SSE 实时推前端
  → （若中途崩溃：reducer 凭 record log 重建状态）
```

学完每个阶段，回来重读这张图，每次都应该能多看懂一层。
