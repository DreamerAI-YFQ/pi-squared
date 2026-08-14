import { useState } from "react";

interface Props {
  running: boolean;
  onSend: (text: string) => void;
}

export function Composer({ running, onSend }: Props) {
  const [text, setText] = useState("");

  const submit = () => {
    const t = text.trim();
    if (!t || running) return;
    onSend(t);
    setText("");
  };

  return (
    <footer className="composer">
      <div className="composer-box">
        <textarea
          value={text}
          placeholder="描述任务，例如：创建 hello.py 并运行它…"
          rows={1}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button className="send" onClick={submit} disabled={running || !text.trim()}>
          {running ? "…" : "↑"}
        </button>
      </div>
      <div className="composer-hint">Enter 发送 · Shift+Enter 换行</div>
    </footer>
  );
}
