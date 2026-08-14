import { useState } from "react";

interface Props {
  onCreate: (workspace: string | null) => void;
  onClose: () => void;
}

/** 新建会话弹窗：可指定本机项目目录作为 workspace（M4）。 */
export function NewSessionDialog({ onCreate, onClose }: Props) {
  const [workspace, setWorkspace] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const trimmed = workspace.trim();
    onCreate(trimmed === "" ? null : trimmed);
  };

  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h3>新建会话</h3>
        <label className="dialog-label">
          工作区目录（可选）
        </label>
        <input
          className="dialog-input"
          value={workspace}
          onChange={(e) => {
            setWorkspace(e.target.value);
            setError(null);
          }}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="例如 D:\code\my-project（留空使用隔离工作区）"
          spellCheck={false}
        />
        <p className="dialog-hint">
          指定后，智能体只在该目录内读写（越界直接拦截），写操作仍需逐条审批。
        </p>
        {error && <p className="dialog-error">{error}</p>}
        <div className="dialog-actions">
          <button className="dialog-secondary" onClick={onClose}>
            取消
          </button>
          <button className="dialog-primary" onClick={submit}>
            创建
          </button>
        </div>
      </div>
    </div>
  );
}
