import type { ToolItem, TurnItem } from "../reducer";

interface Props {
  items: (ToolItem | TurnItem)[];
  running: boolean;
  error: string | null;
}

/** 判断是否是用户条目：历史恢复时 user- 前缀，发送时 u- 前缀。 */
function isUser(item: TurnItem): boolean {
  return item.id.startsWith("user-") || item.id.startsWith("u-");
}

export function ChatView({ items, running, error }: Props) {
  return (
    <main className="chat">
      <div className="messages">
        {items.length === 0 && (
          <div className="placeholder">
            <div className="placeholder-logo">π²</div>
            <p>给 Agent 一个任务，它会用工具在你的工作区里完成。</p>
          </div>
        )}
        {items.map((item, i) =>
          item.kind === "tool" ? (
            <ToolCard key={`${item.id}-${i}`} item={item} />
          ) : (
            <Bubble key={item.id} item={item} />
          ),
        )}
        {running && (
          <div className="running-indicator">
            <span />
            <span />
            <span />
          </div>
        )}
        {error && <div className="error-banner">{error}</div>}
      </div>
    </main>
  );
}

function Bubble({ item }: { item: TurnItem }) {
  const user = isUser(item);
  return (
    <div className={`bubble-row ${user ? "user" : "assistant"}`}>
      <div className={`bubble ${user ? "user" : "assistant"}`}>
        <div className="bubble-text">{item.text}</div>
      </div>
    </div>
  );
}

function ToolCard({ item }: { item: ToolItem }) {
  const status = item.running ? "running" : item.isError ? "error" : "done";
  return (
    <div className={`tool-card ${status}`}>
      <div className="tool-head">
        <span className="tool-status-dot" />
        <span className="tool-name">{item.name}</span>
        <span className="tool-args">{JSON.stringify(item.args)}</span>
      </div>
      {item.resultText && <pre className="tool-result">{item.resultText}</pre>}
    </div>
  );
}
