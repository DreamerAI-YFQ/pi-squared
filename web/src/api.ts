// 手写 SSE 客户端：fetch + ReadableStream 逐块解析（先原理后框架）。
// 与后端 streaming/sse.py 的解析器形成前后端对称：都是手写的 SSE 协议实现。
import type { AgentEvent, Message, ServerConfig, SessionSummary } from "./types";

// ============ SSE 协议说明 ============
// 帧之间用空行（\n\n）分隔，每行 "field: value"，data 可能多行拼接。
// 本文件在 sendMessage 内手写逐帧解析（fetch + ReadableStream），
// 与后端 streaming/sse.py 的解析器形成前后端对称：都是手写 SSE 实现。

// ============ API ============

async function json<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    throw new Error(`HTTP ${resp.status}: ${body || resp.statusText}`);
  }
  return resp.json() as Promise<T>;
}

export async function fetchConfig(): Promise<ServerConfig> {
  return json(await fetch("/api/config"));
}

export async function fetchSessions(): Promise<SessionSummary[]> {
  return json(await fetch("/api/sessions"));
}

export async function createSession(): Promise<{ id: string }> {
  return json(await fetch("/api/sessions", { method: "POST" }));
}

export async function fetchMessages(sessionId: string): Promise<Message[]> {
  const data = await json<{ messages: Message[] }>(await fetch(`/api/sessions/${sessionId}`));
  return data.messages;
}

/** 响应审批：批准或拒绝挂起中的工具调用。 */
export async function resolveApproval(sessionId: string, approvalId: string, approved: boolean): Promise<void> {
  const resp = await fetch(`/api/sessions/${sessionId}/approvals/${approvalId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved }),
  });
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    throw new Error(`HTTP ${resp.status}: ${body || resp.statusText}`);
  }
}

/** 把工具加入免审批列表（"记住此选择"）。 */
export async function rememberAutoApprove(toolName: string): Promise<void> {
  const data = await json<{ autoApprove: string[] }>(await fetch("/api/policy"));
  const next = Array.from(new Set([...data.autoApprove, toolName]));
  await fetch("/api/policy", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ autoApprove: next }),
  });
}

/**
 * 发送消息并以回调形式消费 SSE 事件流。
 * 用 fetch 而非 EventSource：EventSource 不支持 POST，
 * 且手写解析能直接对照后端的 SSE 编码。
 */
export async function sendMessage(
  sessionId: string,
  text: string,
  onEvent: (event: AgentEvent) => void,
): Promise<void> {
  const resp = await fetch(`/api/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!resp.ok || !resp.body) {
    const body = await resp.text().catch(() => "");
    throw new Error(`HTTP ${resp.status}: ${body || resp.statusText}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // 逐帧解析，剩余不完整部分留在 buffer
    let consumed = true;
    while (consumed) {
      consumed = false;
      const idx = buffer.indexOf("\n\n");
      if (idx === -1) break;
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const lines = frame.split("\n");
      const dataLines = lines
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).replace(/^ /, ""));
      if (dataLines.length === 0) continue;
      consumed = true;
      onEvent(JSON.parse(dataLines.join("\n")) as AgentEvent);
    }
  }
}
