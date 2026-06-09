import { AlertTriangle, CircleAlert, CircleCheck, ClipboardCheck, FileJson, FileText, Minimize2 } from "lucide-react";
import type { IsoPlanRow, IsoWorkflowPlan } from "../../isoWorkflow";
import { IsoMetric } from "./IsoControls";

export function IsoDryRunDialog({
  applyBusy,
  applyBlockReason,
  canApply,
  exportBusy,
  onApply,
  onClose,
  onExport,
  rows,
  summary,
}: {
  applyBusy: boolean;
  applyBlockReason: string;
  canApply: boolean;
  exportBusy: boolean;
  onApply: () => void;
  onClose: () => void;
  onExport: () => void;
  rows: IsoPlanRow[];
  summary: IsoWorkflowPlan["summary"];
}) {
  const blockedOrWarn = summary.blocked + summary.warn;
  return (
    <div className="modal-backdrop" role="presentation">
      <div className="dry-run-dialog" role="dialog" aria-modal="true" aria-label="更名前 dry-run">
        <div className="dry-run-head">
          <div>
            <div className="eyebrow">Dry-run rename plan</div>
            <h2>更名前確認</h2>
          </div>
          <button className="dock-icon-button" onClick={onClose} title="關閉">
            <Minimize2 size={15} />
          </button>
        </div>

        <div className="dry-run-metrics">
          <IsoMetric label="Will rename" value={rows.length} icon={<ClipboardCheck size={17} />} tone="ready" />
          <IsoMetric label="Warn" value={summary.warn} icon={<CircleAlert size={17} />} tone="warn" />
          <IsoMetric label="Blocked" value={summary.blocked} icon={<AlertTriangle size={17} />} tone="danger" />
        </div>

        <div className={`dry-run-warning ${blockedOrWarn || !canApply ? "warn" : "ready"}`}>
          {blockedOrWarn ? `${blockedOrWarn} 筆需要注意；blocked 不會套用。` : canApply ? "所有勾選列皆可套用。" : applyBlockReason}
        </div>

        <div className="dry-run-table">
          <div className="dry-run-table-head">
            <span>Page</span>
            <span>Old</span>
            <span>New</span>
            <span>Status</span>
          </div>
          {rows.slice(0, 80).map((row) => (
            <div className={`dry-run-row ${row.status}`} key={row.id}>
              <span>{row.page}</span>
              <strong title={row.source_name}>{row.source_name}</strong>
              <code title={row.new_name}>{row.new_name}</code>
              <span>{row.status}</span>
            </div>
          ))}
        </div>

        <div className="dry-run-actions">
          <button className="action-button" onClick={onExport} disabled={exportBusy}>
            <FileJson size={15} />
            <span>{exportBusy ? "匯出中" : "匯出 CSV"}</span>
          </button>
          <button className="action-button" onClick={onClose} disabled={applyBusy}>
            <Minimize2 size={15} />
            <span>返回校對</span>
          </button>
          <button className="launch-button" onClick={onApply} disabled={!canApply || applyBusy}>
            <ClipboardCheck size={18} />
            <span>{applyBusy ? "套用中" : `確認套用 ${rows.length} 筆`}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

export function IsoResultDialog({
  canOpenDryRun,
  onClose,
  onDryRun,
  onExport,
  plan,
}: {
  onClose: () => void;
  canOpenDryRun: boolean;
  onDryRun: () => void;
  onExport: () => void;
  plan: IsoWorkflowPlan;
}) {
  const issueRows = plan.rows.filter((row) => row.status === "warn" || row.status === "blocked");
  const selectedReady = plan.rows.filter((row) => row.selected && row.status === "ready").length;
  return (
    <div className="modal-backdrop" role="presentation">
      <div className="result-dialog" role="dialog" aria-modal="true" aria-label="ISO 結果">
        <div className="dry-run-head">
          <div>
            <div className="eyebrow">ISO result</div>
            <h2>命名草稿結果</h2>
          </div>
          <button className="dock-icon-button" onClick={onClose} title="關閉">
            <Minimize2 size={15} />
          </button>
        </div>
        <div className="dry-run-metrics">
          <IsoMetric label="Total" value={plan.summary.total} icon={<FileText size={17} />} />
          <IsoMetric label="Ready" value={plan.summary.ready} icon={<CircleCheck size={17} />} tone="ready" />
          <IsoMetric label="Issues" value={issueRows.length} icon={<CircleAlert size={17} />} tone={issueRows.length ? "warn" : "ready"} />
        </div>
        <div className="result-issue-list">
          {(issueRows.length ? issueRows : plan.rows.slice(0, 5)).map((row) => (
            <div className={`issue-card ${row.status}`} key={row.id}>
              {row.status === "ready" ? <CircleCheck size={16} /> : row.status === "warn" ? <CircleAlert size={16} /> : <AlertTriangle size={16} />}
              <div>
                <strong>{row.source_name}</strong>
                <span>{row.note || row.new_name || row.status}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="dry-run-actions">
          <button className="action-button" onClick={onExport}>
            <FileJson size={15} />
            <span>匯出 CSV</span>
          </button>
          <button className="launch-button" onClick={onDryRun} disabled={!canOpenDryRun}>
            <ClipboardCheck size={18} />
            <span>開啟 dry-run</span>
          </button>
        </div>
      </div>
    </div>
  );
}
