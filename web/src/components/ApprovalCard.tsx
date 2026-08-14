import { useState } from "react";
import { rememberAutoApprove, resolveApproval } from "../api";
import type { ApprovalItem } from "../reducer";

interface Props {
  sessionId: string | null;
  item: ApprovalItem;
}

export function ApprovalCard({ sessionId, item }: Props) {
  const [remember, setRemember] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const respond = async (approved: boolean) => {
    if (!sessionId || submitting) return;
    setSubmitting(true);
    try {
      await resolveApproval(sessionId, item.id, approved);
      if (approved && remember) {
        await rememberAutoApprove(item.toolName);
      }
    } catch {
      // 后端会发 approval_resolved 事件（超时/已处理），UI 状态由事件驱动收敛
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={`approval-card ${item.status}`}>
      <div className="approval-title">
        {item.status === "pending" ? "需要审批" : item.status === "approved" ? "已批准" : "已拒绝"}
        <span className="approval-tool">{item.toolName}</span>
      </div>
      <pre className="approval-args">{JSON.stringify(item.args, null, 2)}</pre>
      {item.status === "pending" ? (
        <>
          <label className="approval-remember">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
            />
            批准并记住（{item.toolName} 以后免审批）
          </label>
          <div className="approval-actions">
            <button className="approve" disabled={submitting} onClick={() => respond(true)}>
              批准
            </button>
            <button className="deny" disabled={submitting} onClick={() => respond(false)}>
              拒绝
            </button>
          </div>
        </>
      ) : (
        item.reason && <div className="approval-reason">{item.reason}</div>
      )}
    </div>
  );
}
