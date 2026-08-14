// 事件流 → UI 状态的 reducer。
// 与后端 harness/reducer.py 的理念同构：把事件序列"重放"成可渲染的状态。
import type { AgentEvent, ImageContent, Message, TextContent, ToolCall } from "./types";

// ============ UI 状态模型 ============

export interface ToolItem {
  kind: "tool";
  id: string; // toolCallId
  name: string;
  args: Record<string, unknown>;
  resultText: string | null;
  isError: boolean;
  running: boolean;
}

export interface TurnItem {
  kind: "turn";
  id: string; // assistant 消息的时间戳字符串（一回合的 key）
  text: string;
  toolCalls: { id: string; name: string; args: Record<string, unknown> }[];
  running: boolean;
}

export type ChatItem = ToolItem | TurnItem;

export interface ChatState {
  items: ChatItem[];
  running: boolean;
  error: string | null;
}

export const initialState: ChatState = { items: [], running: false, error: null };

/** UI action：Agent 事件 + 两个本地动作（追加条目 / 重置视图）。 */
export type UiAction =
  | AgentEvent
  | { type: "ui_append"; item: ChatItem }
  | { type: "ui_reset" };

// ============ 辅助 ============

function messageText(content: Message["content"]): string {
  if (typeof content === "string") return content;
  // content 是判别联合（不同消息角色的数组元素类型不同），摊平后统一过滤
  const blocks = content as (TextContent | ImageContent | ToolCall)[];
  return blocks
    .filter((c): c is TextContent => c.type === "text")
    .map((c) => c.text)
    .join("");
}

// ============ reducer ============

export function reduce(state: ChatState, action: UiAction): ChatState {
  // 本地 UI 动作
  if (action.type === "ui_append") {
    return { ...state, items: [...state.items, action.item] };
  }
  if (action.type === "ui_reset") {
    return initialState;
  }

  const event = action;
  switch (event.type) {
    case "agent_start":
      return { ...state, running: true, error: null };

    case "agent_end":
      return { ...state, running: false };

    case "server_error":
      return { ...state, running: false, error: event.message };

    // 用户消息：由发送方直接渲染（事件流里也有，忽略避免重复）
    case "message_start":
    case "message_end": {
      const msg = event.message;
      if (msg.role === "assistant") {
        const text = messageText(msg.content);
        const id = String(msg.timestamp);
        const exists = state.items.some((i) => i.kind === "turn" && i.id === id);
        if (exists) return state;
        return {
          ...state,
          items: [
            ...state.items,
            {
              kind: "turn",
              id,
              text,
              toolCalls: msg.content
                .filter((c) => c.type === "toolCall")
                .map((c) => (c as { id: string; name: string; arguments: Record<string, unknown> }))
                .map((c) => ({ id: c.id, name: c.name, args: c.arguments })),
              running: false,
            },
          ],
        };
      }
      return state;
    }

    case "tool_execution_start": {
      const item: ToolItem = {
        kind: "tool",
        id: event.toolCallId,
        name: event.toolName,
        args: event.args,
        resultText: null,
        isError: false,
        running: true,
      };
      return { ...state, items: [...state.items, item] };
    }

    case "tool_execution_end": {
      return {
        ...state,
        items: state.items.map((i) =>
          i.kind === "tool" && i.id === event.toolCallId
            ? {
                ...i,
                running: false,
                isError: event.isError,
                resultText: event.result.content
                  .filter((c) => c.type === "text")
                  .map((c) => (c as TextContent).text)
                  .join("\n"),
              }
            : i,
        ),
      };
    }

    default:
      return state;
  }
}

/** 把恢复的历史消息（JSONL 重放）转成 UI 条目。 */
export function itemsFromHistory(messages: Message[]): ChatItem[] {
  const items: ChatItem[] = [];
  let currentUserText: string | null = null;

  const flushUser = () => {
    if (currentUserText !== null) {
      items.push({ kind: "turn", id: `user-${items.length}`, text: currentUserText, toolCalls: [], running: false });
      currentUserText = null;
    }
  };

  for (const msg of messages) {
    if (msg.role === "user") {
      flushUser();
      currentUserText = messageText(msg.content);
    } else if (msg.role === "assistant") {
      flushUser();
      const text = messageText(msg.content);
      if (text) {
        items.push({
          kind: "turn",
          id: `a-${msg.timestamp}-${items.length}`,
          text,
          toolCalls: [],
          running: false,
        });
      }
    } else if (msg.role === "toolResult") {
      flushUser();
      items.push({
        kind: "tool",
        id: msg.toolCallId,
        name: msg.toolName,
        args: {},
        resultText: messageText(msg.content),
        isError: msg.isError,
        running: false,
      });
    }
  }
  flushUser();
  return items;
}

/** 用户消息也用 turn 条目渲染（本地即时显示）。 */
export function userItem(text: string): TurnItem {
  return { kind: "turn", id: `u-${Date.now()}`, text, toolCalls: [], running: false };
}
