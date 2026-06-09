import { Braces, CircleAlert, ClipboardCheck, FileJson, FileSearch, FileText, FolderOpen, Layers3, PanelRightOpen, RefreshCcw, ScanLine, SearchCheck, Settings, ShieldCheck, Table2 } from "lucide-react";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import { Gate } from "../components/Gate";
import { StatusTile } from "../components/StatusTile";
import type { LegacyBridgeState } from "../hooks/useLegacyBridge";
import type { IsoJobPayload, IsoWorkflowPlan } from "../isoWorkflow";
import { PathPickerRow } from "./components/IsoControls";

export function EngineerView({
  activeProfileFolderReady,
  applyBusy,
  batchBusy,
  batchJob,
  batchRunning,
  busy,
  cancelBatchDetect,
  chooseCombinePdf,
  chooseIsoList,
  choosePageFolder,
  chooseWorkFolder,
  columnSummary,
  combinePdf,
  confidenceThreshold,
  detectSerials,
  exportBusy,
  exportRenameCsv,
  generatePlan,
  hasDraftProfile,
  hasPublishedProfile,
  headers,
  isoList,
  legacy,
  lineCol,
  canCancelBatch,
  canGenerateDraft,
  canStartBatch,
  openRunLogDrawer,
  pageFolder,
  pattern,
  plan,
  profileBusy,
  profileHistoryCount,
  profileLabel,
  publishProfileToOneClick,
  revertPublishedProfile,
  rowCount,
  runLogBusy,
  selectedCount,
  setConfidenceThreshold,
  setDetectSerials,
  setLineCol,
  setPattern,
  setSerialCol,
  setSheetName,
  sheetName,
  sheetOptions,
  startBatchDetect,
  serialCol,
  visualPanel,
  issueCount,
  workFolder,
}: {
  activeProfileFolderReady: boolean;
  applyBusy: boolean;
  batchBusy: boolean;
  batchJob: IsoJobPayload | null;
  batchRunning: boolean;
  busy: boolean;
  cancelBatchDetect: () => void;
  chooseCombinePdf: () => void;
  chooseIsoList: () => void;
  choosePageFolder: () => void;
  chooseWorkFolder: () => void;
  columnSummary: string;
  combinePdf: string;
  confidenceThreshold: number;
  detectSerials: boolean;
  exportBusy: boolean;
  exportRenameCsv: () => void;
  generatePlan: () => void;
  hasDraftProfile: boolean;
  hasPublishedProfile: boolean;
  headers: string[];
  isoList: string;
  legacy: LegacyBridgeState;
  lineCol: number | "";
  canCancelBatch: boolean;
  canGenerateDraft: boolean;
  canStartBatch: boolean;
  openRunLogDrawer: () => void;
  pageFolder: string;
  pattern: string;
  plan: IsoWorkflowPlan | null;
  profileBusy: boolean;
  profileHistoryCount: number;
  profileLabel: string;
  publishProfileToOneClick: () => void;
  revertPublishedProfile: () => void;
  rowCount: number;
  runLogBusy: boolean;
  selectedCount: number;
  setConfidenceThreshold: Dispatch<SetStateAction<number>>;
  setDetectSerials: Dispatch<SetStateAction<boolean>>;
  setLineCol: Dispatch<SetStateAction<number | "">>;
  setPattern: Dispatch<SetStateAction<string>>;
  setSerialCol: Dispatch<SetStateAction<number | "">>;
  setSheetName: Dispatch<SetStateAction<string>>;
  sheetName: string;
  sheetOptions: string[];
  startBatchDetect: () => void;
  serialCol: number | "";
  visualPanel: ReactNode;
  issueCount: number;
  workFolder: string;
}) {
  return (
    <div className="iso-engineer-grid">
      <aside className="iso-engineer-panel">
        <div className="panel-heading compact">
          <div>
            <span>Sources</span>
            <small>{profileLabel}</small>
          </div>
        </div>
        <PathPickerRow icon={<FolderOpen size={16} />} label="工作資料夾" value={workFolder} onPick={chooseWorkFolder} />
        <PathPickerRow icon={<FileText size={16} />} label="Combine PDF" value={combinePdf} onPick={chooseCombinePdf} />
        <PathPickerRow icon={<Layers3 size={16} />} label="Page folder" value={pageFolder} onPick={choosePageFolder} />
        <PathPickerRow icon={<Table2 size={16} />} label="ISO List" value={isoList} onPick={chooseIsoList} />
        <div className={`profile-chip ${hasPublishedProfile ? "ready" : "idle"}`}>
          <Settings size={14} />
          <span>Profile</span>
          <strong>{profileLabel}</strong>
        </div>
        <div className="engineer-section">
          <div className="eyebrow">Quality gates</div>
          <Gate label="PDF 來源" state={plan?.summary.total ? "ready" : workFolder || combinePdf || pageFolder ? "idle" : "warn"} />
          <Gate label="ISO List" state={plan?.source.record_count ? "ready" : isoList || workFolder ? "idle" : "warn"} />
          <Gate label="欄位對應" state={plan?.source.serial_col !== undefined && plan.source.line_col !== undefined ? "ready" : "idle"} />
          <Gate label="Profile" state={hasPublishedProfile ? "ready" : activeProfileFolderReady ? "idle" : "warn"} />
        </div>
      </aside>

      <main className="iso-engineer-panel wide">
        <div className="engineer-section">
          <div className="panel-heading compact">
            <div>
              <span>ISO List mapping</span>
              <small>{plan?.source.record_count ? `${plan.source.record_count} rows` : "auto columns"}</small>
            </div>
          </div>
          <div className="engineer-form-grid">
            <label className="field-row stacked">
              <span>Sheet</span>
              {sheetOptions.length ? (
                <select value={sheetName} onChange={(event) => { setSheetName(event.target.value); setSerialCol(""); setLineCol(""); }}>
                  {sheetOptions.map((sheet) => <option value={sheet} key={sheet}>{sheet}</option>)}
                </select>
              ) : (
                <input value={sheetName} onChange={(event) => setSheetName(event.target.value)} placeholder="auto" />
              )}
            </label>
            <label className="field-row stacked">
              <span>流水號欄</span>
              <select value={serialCol} onChange={(event) => setSerialCol(event.target.value === "" ? "" : Number(event.target.value))}>
                <option value="">auto</option>
                {headers.map((header, index) => <option value={index} key={`engineer-serial-${header}-${index}`}>{index + 1}. {header}</option>)}
              </select>
            </label>
            <label className="field-row stacked">
              <span>圖號/檔名欄</span>
              <select value={lineCol} onChange={(event) => setLineCol(event.target.value === "" ? "" : Number(event.target.value))}>
                <option value="">auto</option>
                {headers.map((header, index) => <option value={index} key={`engineer-line-${header}-${index}`}>{index + 1}. {header}</option>)}
              </select>
            </label>
            <label className="field-row stacked span-2">
              <span>Pattern</span>
              <input value={pattern} onChange={(event) => setPattern(event.target.value)} />
            </label>
            <label className="field-row stacked">
              <span>Confidence</span>
              <input
                max="0.99"
                min="0.1"
                onChange={(event) => setConfidenceThreshold(Number(event.target.value))}
                step="0.01"
                type="range"
                value={confidenceThreshold}
              />
            </label>
          </div>
          <div className="engineer-inline-controls">
            <label className="toggle-row">
              <input type="checkbox" checked={detectSerials} onChange={(event) => setDetectSerials(event.target.checked)} />
              <span>影像判讀流水號</span>
            </label>
            <StatusTile icon={<Braces size={18} />} title="Columns" value={columnSummary} tone={plan?.source.record_count ? "ready" : "warn"} />
            <StatusTile icon={<SearchCheck size={18} />} title="Threshold" value={`${Math.round(confidenceThreshold * 100)}%`} tone="ready" />
          </div>
          <div className="engineer-actions profile-actions">
            <button className="action-button" onClick={publishProfileToOneClick} disabled={profileBusy || !activeProfileFolderReady}>
              <ShieldCheck size={15} />
              <span>{profileBusy ? "處理中" : hasDraftProfile ? "發布草稿到一鍵" : "發布到一鍵"}</span>
            </button>
            <button className="action-button" onClick={revertPublishedProfile} disabled={profileBusy || !hasPublishedProfile || profileHistoryCount < 1}>
              <RefreshCcw size={15} />
              <span>回復上一版</span>
            </button>
            <StatusTile
              icon={<Settings size={18} />}
              title="Profile"
              value={`${hasPublishedProfile ? "published" : "not published"}${hasDraftProfile ? " · draft" : ""}${profileHistoryCount ? ` · ${profileHistoryCount} old` : ""}`}
              tone={hasPublishedProfile ? "ready" : hasDraftProfile ? "warn" : "warn"}
            />
          </div>
        </div>

        <div className="engineer-section">
          <div className="panel-heading compact">
            <div>
              <span>Job protocol</span>
              <small>{batchJob?.job_id || "idle"}</small>
            </div>
          </div>
          <div className="engineer-job-grid">
            <StatusTile icon={<ScanLine size={18} />} title="Batch" value={batchJob ? `${batchJob.state} · ${batchJob.progress.percent}%` : "idle"} tone={batchRunning ? "ready" : batchJob?.state === "failed" ? "danger" : "warn"} />
            <StatusTile icon={<ClipboardCheck size={18} />} title="Selected" value={`${selectedCount} / ${rowCount}`} tone={selectedCount ? "ready" : "warn"} />
            <StatusTile icon={<CircleAlert size={18} />} title="Issues" value={String(issueCount)} tone={issueCount ? "warn" : "ready"} />
          </div>
          <div className="engineer-actions">
            <button className="action-button" onClick={generatePlan} disabled={!canGenerateDraft}>
              <RefreshCcw size={15} />
              <span>{busy ? "產生中" : "重新產生"}</span>
            </button>
            <button className="action-button" onClick={batchRunning ? cancelBatchDetect : startBatchDetect} disabled={batchRunning ? !canCancelBatch : !canStartBatch}>
              <ScanLine size={15} />
              <span>{batchRunning ? "取消判讀" : "批次判讀"}</span>
            </button>
            <button className="action-button" onClick={exportRenameCsv} disabled={!plan || busy || exportBusy}>
              <FileJson size={15} />
              <span>{exportBusy ? "匯出中" : "匯出 CSV"}</span>
            </button>
            <button className="action-button" onClick={() => void openRunLogDrawer()} disabled={runLogBusy}>
              <FileSearch size={15} />
              <span>{runLogBusy ? "讀取中" : "處理紀錄"}</span>
            </button>
          </div>
        </div>
      </main>

      <aside className="iso-engineer-panel">
        {visualPanel}
        <div className="legacy-fallback-card">
          <div>
            <div className="eyebrow">Legacy fallback</div>
            <h3>舊 ISO 工作台</h3>
          </div>
          <StatusTile icon={<PanelRightOpen size={18} />} title="Bridge" value={legacy.busy ? "opening" : "available"} tone="ready" />
          <button className="launch-button" onClick={legacy.launch} disabled={legacy.busy}>
            <PanelRightOpen size={18} />
            <span>{legacy.busy ? "開啟中" : "開啟舊工作台"}</span>
          </button>
        </div>
      </aside>
    </div>
  );
}
