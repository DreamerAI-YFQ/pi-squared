import { useCallback, useEffect, useReducer, useState } from "react";
import { ChatView } from "./components/ChatView";
import { Composer } from "./components/Composer";
import { NewSessionDialog } from "./components/NewSessionDialog";
import { ObservabilityPanel } from "./components/ObservabilityPanel";
import { Sidebar } from "./components/Sidebar";
import { createSession, fetchConfig, fetchMessages, fetchSessions, sendMessage } from "./api";
import { initialState, itemsFromHistory, reduce, userItem } from "./reducer";
import type { ServerConfig, SessionSummary } from "./types";

export default function App() {
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [state, dispatch] = useReducer(reduce, initialState);
  const [obsOpen, setObsOpen] = useState(false);
  const [obsRefresh, setObsRefresh] = useState(0);
  const [newDialogOpen, setNewDialogOpen] = useState(false);

  const refreshSessions = useCallback(async () => {
    setSessions(await fetchSessions());
  }, []);

  useEffect(() => {
    fetchConfig().then(setConfig).catch(() => setConfig(null));
    refreshSessions().catch(() => {});
  }, [refreshSessions]);

  const openSession = useCallback(async (id: string) => {
    setActiveId(id);
    const messages = await fetchMessages(id);
    dispatch({ type: "ui_reset" });
    for (const item of itemsFromHistory(messages)) {
      dispatch({ type: "ui_append", item });
    }
  }, []);

  const handleCreate = useCallback(async (workspace: string | null) => {
    try {
      const { id } = await createSession(workspace);
      await refreshSessions();
      setActiveId(id);
      dispatch({ type: "ui_reset" });
    } catch (exc) {
      dispatch({ type: "server_error", message: String(exc) });
    } finally {
      setNewDialogOpen(false);
    }
  }, [refreshSessions]);

  const handleSend = useCallback(
    async (text: string) => {
      let sessionId = activeId;
      if (!sessionId) {
        const { id } = await createSession();
        sessionId = id;
        setActiveId(id);
      }
      dispatch({ type: "ui_append", item: userItem(text) });
      try {
        await sendMessage(sessionId, text, (event) => dispatch(event));
      } catch (exc) {
        dispatch({ type: "server_error", message: String(exc) });
      }
      setObsRefresh((k) => k + 1); // 消息完成后刷新观测面板
      refreshSessions().catch(() => {});
    },
    [activeId, refreshSessions],
  );

  return (
    <div className="app">
      <Sidebar
        sessions={sessions}
        activeId={activeId}
        provider={config?.provider ?? ""}
        onSelect={(id) => openSession(id).catch(() => {})}
        onCreate={() => setNewDialogOpen(true)}
      />
      <div className={`main-col ${obsOpen ? "with-obs" : ""}`}>
        <header className="topbar">
          <div className="topbar-left">
            <span className="topbar-title">
              {activeId ? sessions.find((s) => s.id === activeId)?.title ?? "会话" : "新会话"}
            </span>
            {activeId && (
              <span className="topbar-ws" title={sessions.find((s) => s.id === activeId)?.workspace}>
                {sessions.find((s) => s.id === activeId)?.workspace}
              </span>
            )}
          </div>
          <button
            className={`obs-toggle ${obsOpen ? "active" : ""}`}
            onClick={() => setObsOpen((v) => !v)}
            title="观测面板（span 树 / 成本）"
          >
            观测
          </button>
        </header>
        <ChatView sessionId={activeId} items={state.items} running={state.running} error={state.error} />
        <Composer running={state.running} onSend={handleSend} />
      </div>
      {obsOpen && (
        <ObservabilityPanel sessionId={activeId} refreshKey={obsRefresh} onClose={() => setObsOpen(false)} />
      )}
      {newDialogOpen && (
        <NewSessionDialog onCreate={(ws) => handleCreate(ws)} onClose={() => setNewDialogOpen(false)} />
      )}
    </div>
  );
}
