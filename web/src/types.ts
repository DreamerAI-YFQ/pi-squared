// 与后端 pi_agent 事件协议一一对应的 TS 类型
// （后端 events.py / types.py 序列化后的 JSON 结构）

// ============ 内容块 ============

export interface TextContent {
  type: "text";
  text: string;
}

export interface ImageContent {
  type: "image";
  data: string;
  mimeType: string;
}

export interface ToolCall {
  type: "toolCall";
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

// ============ 消息 ============

export interface Usage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface UserMessage {
  role: "user";
  content: string | (TextContent | ImageContent)[];
  timestamp: number;
}

export interface AssistantMessage {
  role: "assistant";
  content: (TextContent | ImageContent | ToolCall)[];
  stopReason: string;
  timestamp: number;
  errorMessage: string | null;
  usage: Usage | null;
}

export interface ToolResultMessage {
  role: "toolResult";
  toolCallId: string;
  toolName: string;
  content: (TextContent | ImageContent)[];
  isError: boolean;
  timestamp: number;
}

export type Message = UserMessage | AssistantMessage | ToolResultMessage;

export interface AgentToolResult {
  content: (TextContent | ImageContent)[];
  details: Record<string, unknown>;
}

// ============ Agent 事件（SSE data 载荷） ============

export type AgentEvent =
  | { type: "agent_start" }
  | { type: "agent_end"; messages: Message[] }
  | { type: "turn_start" }
  | { type: "turn_end"; message: Message; toolResults: ToolResultMessage[] }
  | { type: "message_start"; message: Message }
  | { type: "message_end"; message: Message }
  | { type: "tool_execution_start"; toolCallId: string; toolName: string; args: Record<string, unknown> }
  | { type: "tool_execution_end"; toolCallId: string; toolName: string; result: AgentToolResult; isError: boolean }
  // server 层治理事件（M2）
  | { type: "approval_request"; approvalId: string; toolName: string; args: Record<string, unknown> }
  | { type: "approval_resolved"; approvalId: string; approved: boolean; reason: string }
  | { type: "server_error"; message: string };

// ============ REST ============

export interface SessionSummary {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  workspace: string;
}

export interface ServerConfig {
  name: string;
  version: string;
  provider: string;
  workspace_root: string;
}
