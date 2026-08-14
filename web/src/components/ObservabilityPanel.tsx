import { useEffect, useState } from "react";
import { fetchObservability } from "../api";
import type { ObservabilityData, Span } from "../types";

interface Props {
  sessionId: string | null;
  refreshKey: number; // 每次消息完成后自增，触发刷新
  onClose: () => void;
}

/** 单个 span 行：名称 + 耗时条 + 关键属性，子 span 缩进递归。 */
function SpanRow({ span, totalMs, depth }: { span: Span; totalMs: number; depth: number }) {
  const duration = span.duration_ms ?? 0;
  const width = totalMs > 0 ? Math.max(2, Math.round((duration / totalMs) * 100)) : 0;
  const isError = span.attrs?.isError === true;
  const tokens = span.attrs?.tokens;

  return (
    <div className="span-node" style={{ marginLeft: depth * 16 }}>
      <div className="span-line">
        <span className={`span-name ${isError ? "error" : ""}`}>{span.name}</span>
        {tokens != null && <span className="span-tokens">{String(tokens)} tok</span>}
        <span className="span-duration">{duration} ms</span>
      </div>
      <div className="span-bar-track">
        <div className={`span-bar ${isError ? "error" : ""}`} style={{ width: `${width}%` }} />
      </div>
      {span.children.map((child, i) => (
        <SpanRow key={i} span={child} totalMs={totalMs} depth={depth + 1} />
      ))}
    </div>
  );
}

export function ObservabilityPanel({ sessionId, refreshKey, onClose }: Props) {
  const [data, setData] = useState<ObservabilityData | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    fetchObservability(sessionId)
      .then(setData)
      .catch(() => setData(null));
  }, [sessionId, refreshKey]);

  const rootMs = data?.spans?.reduce((m, s) => Math.max(m, s.duration_ms ?? 0), 0) ?? 0;

  return (
    <aside className="obs-panel">
      <div className="obs-header">
        <h3>观测</h3>
        <button className="obs-close" onClick={onClose} aria-label="关闭">
          ✕
        </button>
      </div>

      {!data ? (
        <div className="obs-empty">暂无数据</div>
      ) : (
        <>
          <div className="obs-model">{data.model}</div>
          <div className="obs-cards">
            <div className="obs-card">
              <div className="obs-value">{data.totalTokens.toLocaleString()}</div>
              <div className="obs-label">总 Tokens</div>
            </div>
            <div className="obs-card">
              <div className="obs-value">${data.totalCost.toFixed(4)}</div>
              <div className="obs-label">估算成本</div>
            </div>
            <div className="obs-card">
              <div className="obs-value">{data.llmCalls}</div>
              <div className="obs-label">LLM 调用</div>
            </div>
            <div className="obs-card">
              <div className="obs-value">{data.toolCalls}</div>
              <div className="obs-label">工具调用</div>
            </div>
          </div>
          <div className="obs-tree">
            {data.spans.length === 0 && <div className="obs-empty">还没有运行记录</div>}
            {data.spans.map((s, i) => (
              <SpanRow key={i} span={s} totalMs={rootMs} depth={0} />
            ))}
          </div>
        </>
      )}
    </aside>
  );
}
