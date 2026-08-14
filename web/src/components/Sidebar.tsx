import type { SessionSummary } from "../types";

interface Props {
  sessions: SessionSummary[];
  activeId: string | null;
  provider: string;
  onSelect: (id: string) => void;
  onCreate: () => void;
}

export function Sidebar({ sessions, activeId, provider, onSelect, onCreate }: Props) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span className="brand">
          Pi<sup>2</sup>
        </span>
        <button className="new-session" onClick={onCreate} title="新建会话">
          ＋
        </button>
      </div>

      <div className="session-list">
        {sessions.length === 0 && <div className="empty">暂无会话</div>}
        {sessions.map((s) => (
          <button
            key={s.id}
            className={`session-item ${s.id === activeId ? "active" : ""}`}
            onClick={() => onSelect(s.id)}
          >
            <div className="session-title">{s.title}</div>
            <div className="session-meta">{new Date(s.updatedAt).toLocaleString()}</div>
          </button>
        ))}
      </div>

      <div className="sidebar-footer">
        <span className={`provider-badge provider-${provider}`}>
          {provider === "deepseek" ? "DeepSeek" : "Faux（演示）"}
        </span>
      </div>
    </aside>
  );
}
