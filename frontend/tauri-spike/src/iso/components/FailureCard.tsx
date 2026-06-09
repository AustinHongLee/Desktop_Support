import { AlertTriangle, Copy, FileJson, PanelRightOpen } from "lucide-react";

export interface IsoFailureInfo {
  run_id?: string;
  title: string;
  summary: string;
  detail?: string;
  run_json?: string;
  events_jsonl?: string;
}

export function FailureCard({
  copied,
  exportBusy,
  failure,
  onCopy,
  onExport,
  onOpenWorkbench,
  probableCause,
}: {
  copied: boolean;
  exportBusy: boolean;
  failure: IsoFailureInfo;
  onCopy: () => void;
  onExport: () => void;
  onOpenWorkbench: () => void;
  probableCause?: string;
}) {
  return (
    <section className="iso-failure-card" aria-label="ISO 一鍵失敗交接">
      <div className="iso-failure-icon">
        <AlertTriangle size={20} />
      </div>
      <div className="iso-failure-main">
        <div>
          <div className="eyebrow">需要交接</div>
          <h3>{failure.title}</h3>
          <p>{failure.summary}</p>
        </div>
        {probableCause ? (
          <div className="iso-failure-cause">
            <span>最可能原因</span>
            <strong>{probableCause}</strong>
          </div>
        ) : null}
        {failure.run_id ? (
          <div className="iso-failure-run">
            <span>流程 ID</span>
            <strong>{failure.run_id}</strong>
          </div>
        ) : null}
        {failure.detail ? <small>{failure.detail}</small> : null}
        <div className="iso-failure-actions">
          <button className="action-button" onClick={onCopy} type="button">
            <Copy size={15} />
            <span>{copied ? "已複製" : "複製給工程師"}</span>
          </button>
          <button className="action-button" disabled={!failure.run_id || exportBusy} onClick={onExport} type="button">
            <FileJson size={15} />
            <span>{exportBusy ? "匯出中" : "匯出問題包"}</span>
          </button>
          <button className="action-button" onClick={onOpenWorkbench} type="button">
            <PanelRightOpen size={15} />
            <span>開啟工作台</span>
          </button>
        </div>
      </div>
    </section>
  );
}
