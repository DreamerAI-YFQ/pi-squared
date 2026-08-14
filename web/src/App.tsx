import { useCallback, useEffect, useReducer, useState } from "react";
import { ChatView } from "./components/ChatView";
import { Composer } from "./components/Composer";
import { Sidebar } from "./components/Sidebar";
import { createSession, fetchConfig, fetchMessages, fetchSessions, sendMessage } from "./api";
import { initialState, itemsFromHistory, reduce, userItem } from "./reducer";
import type { ServerConfig, SessionSummary } from "./types";

export default function App() {
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [state, dispatch] = useReducer(reduce, initialState);

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

  const handleCreate = useCallback(async () => {
    const { id } = await createSession();
    await refreshSessions();
    setActiveId(id);
    dispatch({ type: "ui_reset" });
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
        onCreate={handleCreate}
      />
      <div className="main-col">
        <header className="topbar">
          <span className="topbar-title">
            {activeId ? sessions.find((s) => s.id === activeId)?.title ?? "会话" : "新会话"}
          </span>
        </header>
        <ChatView items={state.items} running={state.running} error={state.error} />
        <Composer running={state.running} onSend={handleSend} />
      </div>
    </div>
  );
}
