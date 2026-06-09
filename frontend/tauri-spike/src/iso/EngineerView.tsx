import { CircleAlert, FileJson, FileSearch, FileText, FolderOpen, Layers3, PanelRightOpen, RefreshCcw, ScanLine, Settings, ShieldCheck, Table2 } from "lucide-react";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import { Gate } from "../components/Gate";
import { StatusTile } from "../components/StatusTile";
import type { LegacyBridgeState } from "../hooks/useLegacyBridge";
import type { IsoPilotItem, IsoPlanRow, IsoRoiDistribution, IsoWorkflowPlan } from "../isoWorkflow";
import { PathPickerRow } from "./components/IsoControls";
import { PilotListPanel } from "./components/PilotListPanel";
import { RoiSamplePanel } from "./components/RoiSamplePanel";

export function EngineerView({
  activeProfileFolderReady,
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
  pilotItems,
  plan,
  profileBusy,
  profileHistoryCount,
  profileLabel,
  publishProfileToOneClick,
  revertPublishedProfile,
  roiDistribution,
  roiDistributionBusy,
  roiDistributionError,
  rows,
  rowCount,
  runLogBusy,
  selectedCount,
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
  onPilotAutoFix,
  onPilotJump,
}: {
  activeProfileFolderReady: boolean;
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
  pilotItems: IsoPilotItem[];
  plan: IsoWorkflowPlan | null;
  profileBusy: boolean;
  profileHistoryCount: number;
  profileLabel: string;
  publishProfileToOneClick: () => void;
  revertPublishedProfile: () => void;
  roiDistribution: IsoRoiDistribution | null;
  roiDistributionBusy: boolean;
  roiDistributionError: string;
  rows: IsoPlanRow[];
  rowCount: number;
  runLogBusy: boolean;
  selectedCount: number;
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
  onPilotAutoFix?: (item: IsoPilotItem) => void;
  onPilotJump?: (item: IsoPilotItem) => void;
}) {
  const hasStaleDraft = pilotItems.some((item) => item.freshness === "stale");

  return (
    <div className="iso-engineer-grid">
      <aside className="iso-engineer-panel">
        <div className="panel-heading compact">
          <div>
            <span>來源</span>
            <small>{profileLabel}</small>
          </div>
        </div>
        <PathPickerRow icon={<FolderOpen size={16} />} label="工作資料夾" value={workFolder} onPick={chooseWorkFolder} />
        <PathPickerRow icon={<FileText size={16} />} label="合併 PDF" value={combinePdf} onPick={chooseCombinePdf} />
        <PathPickerRow icon={<Layers3 size={16} />} label="拆頁資料夾" value={pageFolder} onPick={choosePageFolder} />
        <PathPickerRow icon={<Table2 size={16} />} label="ISO 清單" value={isoList} onPick={chooseIsoList} />
        <div className={`profile-chip ${hasPublishedProfile ? "ready" : "idle"}`}>
          <Settings size={14} />
          <span>設定檔</span>
          <strong>{profileLabel}</strong>
        </div>
        <div className="engineer-section">
          <div className="eyebrow">品質檢查</div>
          <Gate label="PDF 來源" state={plan?.summary.total ? "ready" : workFolder || combinePdf || pageFolder ? "idle" : "warn"} />
          <Gate label="ISO 清單" state={plan?.source.record_count ? "ready" : isoList || workFolder ? "idle" : "warn"} />
          <Gate label="欄位對應" state={plan?.source.serial_col !== undefined && plan.source.line_col !== undefined ? "ready" : "idle"} />
          <Gate label="設定檔" state={hasPublishedProfile ? "ready" : activeProfileFolderReady ? "idle" : "warn"} />
        </div>
      </aside>

      <main className="iso-engineer-main">
        {hasStaleDraft ? (
          <div className="engineer-stale-banner">
            <CircleAlert size={17} />
            <div>
              <strong>草稿已過期，請重生</strong>
              <span>調校參數已變更，先重新產生命名草稿再回工作台套用。</span>
            </div>
            <button className="action-button" onClick={generatePlan} disabled={!canGenerateDraft}>
              <RefreshCcw size={15} />
              <span>{busy ? "產生中" : "重新產生草稿"}</span>
            </button>
          </div>
        ) : null}

        <div className="engineer-tuning-strip">
          <div className="engineer-tuning-head">
            <div className="panel-heading compact">
              <div>
                <span>調校設定</span>
                <small>{plan?.source.record_count ? `${plan.source.record_count} 筆資料` : "自動欄位"}</small>
              </div>
            </div>
            <div className="engineer-actions profile-actions">
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
              <button className="action-button" onClick={publishProfileToOneClick} disabled={profileBusy || !activeProfileFolderReady}>
                <ShieldCheck size={15} />
                <span>{profileBusy ? "處理中" : hasDraftProfile ? "發布草稿到一鍵" : "發布到一鍵"}</span>
              </button>
              <button className="action-button" onClick={revertPublishedProfile} disabled={profileBusy || !hasPublishedProfile || profileHistoryCount < 1}>
                <RefreshCcw size={15} />
                <span>回復上一版</span>
              </button>
            </div>
          </div>
          <div className="engineer-form-grid">
            <label className="field-row stacked">
              <span>工作表</span>
              {sheetOptions.length ? (
                <select value={sheetName} onChange={(event) => { setSheetName(event.target.value); setSerialCol(""); setLineCol(""); }}>
                  {sheetOptions.map((sheet) => <option value={sheet} key={sheet}>{sheet}</option>)}
                </select>
              ) : (
                <input value={sheetName} onChange={(event) => setSheetName(event.target.value)} placeholder="自動" />
              )}
            </label>
            <label className="field-row stacked">
              <span>流水號欄</span>
              <select value={serialCol} onChange={(event) => setSerialCol(event.target.value === "" ? "" : Number(event.target.value))}>
                <option value="">自動</option>
                {headers.map((header, index) => <option value={index} key={`engineer-serial-${header}-${index}`}>{index + 1}. {header}</option>)}
              </select>
            </label>
            <label className="field-row stacked">
              <span>圖號/檔名欄</span>
              <select value={lineCol} onChange={(event) => setLineCol(event.target.value === "" ? "" : Number(event.target.value))}>
                <option value="">自動</option>
                {headers.map((header, index) => <option value={index} key={`engineer-line-${header}-${index}`}>{index + 1}. {header}</option>)}
              </select>
            </label>
            <label className="field-row stacked span-2">
              <span>命名格式</span>
              <input value={pattern} onChange={(event) => setPattern(event.target.value)} />
            </label>
          </div>
          <div className="engineer-tuning-meta">
            <span className="engineer-meta-chip">欄位 <strong>{columnSummary}</strong></span>
            <span className="engineer-meta-chip">設定檔 <strong>{hasPublishedProfile ? "已發布" : hasDraftProfile ? "草稿" : "未發布"}</strong></span>
            <span className="engineer-meta-chip">已選 <strong>{selectedCount} / {rowCount}</strong></span>
            <span className={`engineer-meta-chip ${issueCount ? "warn" : "ready"}`}>問題 <strong>{issueCount}</strong></span>
          </div>
        </div>

        <div className="engineer-preview-stage">
          {visualPanel}
        </div>
      </main>

      <aside className="iso-engineer-panel engineer-diagnostics-panel">
        <PilotListPanel items={pilotItems} onAutoFix={onPilotAutoFix} onJump={onPilotJump} showEngineerDetail />
        <RoiSamplePanel
          distribution={roiDistribution}
          error={roiDistributionError}
          loading={roiDistributionBusy}
          rows={rows}
          threshold={confidenceThreshold}
        />
        <div className="legacy-fallback-card">
          <div>
            <div className="eyebrow">舊版備援</div>
            <h3>舊 ISO 工作台</h3>
          </div>
          <StatusTile icon={<PanelRightOpen size={18} />} title="橋接狀態" value={legacy.busy ? "開啟中" : "可使用"} tone="ready" />
          <button className="launch-button" onClick={legacy.launch} disabled={legacy.busy}>
            <PanelRightOpen size={18} />
            <span>{legacy.busy ? "開啟中" : "開啟舊工作台"}</span>
          </button>
        </div>
      </aside>
    </div>
  );
}
