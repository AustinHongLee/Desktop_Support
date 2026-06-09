import { CircleAlert, CircleCheck, ScanLine } from "lucide-react";
import type { IsoPlanRow } from "../../isoWorkflow";

export function RoiSamplePanel({ rows, threshold }: { rows: IsoPlanRow[]; threshold: number }) {
  const total = rows.length;
  const ready = rows.filter((row) => row.confidence >= threshold).length;
  const low = rows.filter((row) => row.confidence > 0 && row.confidence < threshold).length;
  const missing = rows.filter((row) => !row.confidence).length;
  const weakestRows = [...rows]
    .sort((left, right) => (left.confidence || 0) - (right.confidence || 0) || left.page - right.page)
    .slice(0, 5);

  return (
    <div className="roi-sample-panel">
      <div className="panel-heading compact">
        <div>
          <span>多頁採樣</span>
          <small>{total ? `${total} rows · threshold ${Math.round(threshold * 100)}%` : "waiting"}</small>
        </div>
      </div>
      <div className="roi-sample-bars" aria-label="ROI confidence distribution">
        <SampleBar label="高信心" count={ready} total={total} tone="ready" />
        <SampleBar label="低信心" count={low} total={total} tone="warn" />
        <SampleBar label="未判讀" count={missing} total={total} tone="idle" />
      </div>
      <div className="roi-sample-list">
        {weakestRows.length ? weakestRows.map((row) => (
          <div className="roi-sample-row" key={row.id}>
            {row.confidence >= threshold ? <CircleCheck size={14} /> : row.confidence > 0 ? <CircleAlert size={14} /> : <ScanLine size={14} />}
            <strong>{row.page}</strong>
            <span title={row.source_name}>{row.source_name}</span>
            <code>{row.confidence ? `${Math.round(row.confidence * 100)}%` : "-"}</code>
          </div>
        )) : (
          <div className="roi-sample-empty">等待批次判讀資料</div>
        )}
      </div>
    </div>
  );
}

function SampleBar({ count, label, tone, total }: { count: number; label: string; tone: "ready" | "warn" | "idle"; total: number }) {
  const percent = total ? Math.round((count / total) * 100) : 0;
  return (
    <div className={`roi-sample-bar ${tone}`}>
      <div>
        <span>{label}</span>
        <strong>{count}</strong>
      </div>
      <div className="roi-sample-track">
        <span style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
