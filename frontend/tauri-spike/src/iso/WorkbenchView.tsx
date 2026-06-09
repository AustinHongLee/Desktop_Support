import { AlertTriangle, Braces, ChevronRight, CircleAlert, CircleCheck, ClipboardCheck, FileJson, FileSearch, FileText, FolderOpen, Layers3, PanelRightOpen, RefreshCcw, ScanLine, SearchCheck, Settings, Table2 } from "lucide-react";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import { StatusTile } from "../components/StatusTile";
import type { LegacyBridgeState } from "../hooks/useLegacyBridge";
import type { IsoPilotItem, IsoPlanRow, IsoWorkflowIssue, IsoWorkflowPlan, IsoWorkflowStep } from "../isoWorkflow";
import type { IsoSortMode } from "./helpers";
import { compactPath } from "./helpers";
import { IsoEmptyPlan, IsoMetric, PathPickerRow } from "./components/IsoControls";
import { IsoPlanTable } from "./components/NamingTable";
import { PilotStrip } from "./components/PilotStrip";

export function WorkbenchView({
  activeProfileFolderReady,
  applyBusy,
  batchBusy,
  batchRunning,
  blockedCount,
  busy,
  cancelBatchDetect,
  chooseCombinePdf,
  chooseIsoList,
  choosePageFolder,
  chooseWorkFolder,
  columnSummary,
  combinePdf,
  defaultIssues,
  defaultSteps,
  detectSerials,
  exportBusy,
  exportRenameCsv,
  generatePlan,
  hasPublishedProfile,
  isoList,
  issueRows,
  legacy,
  canCancelBatch,
  canGenerateDraft,
  canOpenDryRun,
  canStartBatch,
  openEngineerView,
  openDryRun,
  openRunLogDrawer,
  onPilotJump,
  pageFolder,
  pattern,
  pilotItems,
  plan,
  problemOnly,
  profileLabel,
  readyCount,
  rows,
  runLogBusy,
  searchTerm,
  selectedCount,
  selectedRow,
  setAllRowsSelected,
  setProblemOnly,
  setSearchTerm,
  setSelectedRowId,
  setSortMode,
  sheetName,
  sortMode,
  startBatchDetect,
  toggleRow,
  updateRow,
  visibleRows,
  visualPanel,
  warnCount,
  workFolder,
}: {
  activeProfileFolderReady: boolean;
  applyBusy: boolean;
  batchBusy: boolean;
  batchRunning: boolean;
  blockedCount: number;
  busy: boolean;
  cancelBatchDetect: () => void;
  chooseCombinePdf: () => void;
  chooseIsoList: () => void;
  choosePageFolder: () => void;
  chooseWorkFolder: () => void;
  columnSummary: string;
  combinePdf: string;
  defaultIssues: IsoWorkflowIssue[];
  defaultSteps: IsoWorkflowStep[];
  detectSerials: boolean;
  exportBusy: boolean;
  exportRenameCsv: () => void;
  generatePlan: () => void;
  hasPublishedProfile: boolean;
  isoList: string;
  issueRows: IsoPlanRow[];
  legacy: LegacyBridgeState;
  canCancelBatch: boolean;
  canGenerateDraft: boolean;
  canOpenDryRun: boolean;
  canStartBatch: boolean;
  openEngineerView: () => void;
  openDryRun: () => void;
  openRunLogDrawer: () => void;
  pageFolder: string;
  pattern: string;
  pilotItems: IsoPilotItem[];
  onPilotJump: (item: IsoPilotItem) => void;
  plan: IsoWorkflowPlan | null;
  problemOnly: boolean;
  profileLabel: string;
  readyCount: number;
  rows: IsoPlanRow[];
  runLogBusy: boolean;
  searchTerm: string;
  selectedCount: number;
  selectedRow?: IsoPlanRow;
  setAllRowsSelected: (select: boolean) => void;
  setProblemOnly: Dispatch<SetStateAction<boolean>>;
  setSearchTerm: Dispatch<SetStateAction<string>>;
  setSelectedRowId: Dispatch<SetStateAction<string>>;
  setSortMode: Dispatch<SetStateAction<IsoSortMode>>;
  sheetName: string;
  sortMode: IsoSortMode;
  startBatchDetect: () => void;
  toggleRow: (rowId: string) => void;
  updateRow: (rowId: string, field: "serial" | "line_no" | "new_name", value: string) => void;
  visibleRows: IsoPlanRow[];
  visualPanel: ReactNode;
  warnCount: number;
  workFolder: string;
}) {
  const issueCards = issueRows.length
    ? issueRows.map((row) => ({ code: row.status.toUpperCase(), tone: row.status, title: row.source_name, detail: row.note || row.new_name || row.source_path }))
    : plan?.issues.length ? plan.issues : defaultIssues;

  return (
    <div className="iso-workbench-grid">
      <aside className="iso-left-panel">
        <div className="panel-heading compact">
          <div>
            <span>來源</span>
            <small>{workFolder ? "資料夾一鍵" : pageFolder ? "拆頁資料夾" : combinePdf ? "合併 PDF" : "等待來源"}</small>
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

        <div className="workbench-config-summary">
          <div className="panel-heading compact">
            <div>
              <span>調校摘要</span>
              <small>只讀 · 到調校修改</small>
            </div>
            <button className="mini-text-button" onClick={openEngineerView} type="button">
              <Settings size={13} />
              <span>調校設定</span>
            </button>
          </div>
          <ReadOnlySetting label="ISO 清單" value={plan?.source.record_count ? `${plan.source.record_count} 筆` : compactPath(isoList || "等待來源")} />
          <ReadOnlySetting label="工作表" value={plan?.source.sheet_name || sheetName || "自動"} />
          <ReadOnlySetting label="欄位對應" value={columnSummary} />
          <ReadOnlySetting label="命名格式" value={plan?.source.pattern || pattern} />
          <ReadOnlySetting label="影像判讀" value={detectSerials ? "預設開啟" : "已關閉"} tone={detectSerials ? "ready" : "warn"} />
        </div>

      </aside>

      <main className="iso-table-panel">
        <PilotStrip items={pilotItems} onJump={onPilotJump} />
        <div className="iso-metric-strip">
          <IsoMetric label="PDF" value={rows.length} icon={<FileText size={17} />} />
          <IsoMetric label="通過" value={readyCount} icon={<CircleCheck size={17} />} tone="ready" />
          <IsoMetric label="待確認" value={warnCount} icon={<CircleAlert size={17} />} tone="warn" />
          <IsoMetric label="需處理" value={blockedCount} icon={<AlertTriangle size={17} />} tone="danger" />
          <IsoMetric label="已選" value={selectedCount} icon={<ClipboardCheck size={17} />} tone="ready" />
        </div>

        <div className="iso-flow compact" aria-label="ISO 工作流程步驟">
          {(plan?.steps ?? defaultSteps).map((step, index) => (
            <div className={`iso-step ${step.state}`} key={`${step.label}-${index}`}>
              <div className="step-index">{String(index + 1).padStart(2, "0")}</div>
              <div>
                <strong>{step.label}</strong>
                <span>{step.meta}</span>
              </div>
              {index < (plan?.steps.length ?? defaultSteps.length) - 1 ? <ChevronRight size={16} /> : null}
            </div>
          ))}
        </div>

        <div className={`workbench-apply-strip ${canOpenDryRun ? "ready" : "idle"}`}>
          <div>
            <strong>{selectedCount} 筆可套用</strong>
            <span>{blockedCount ? `${blockedCount} 筆需處理` : warnCount ? `${warnCount} 筆待確認` : plan ? "可先試算再更名" : "等待命名草稿"}</span>
          </div>
          <button className="action-button" onClick={openDryRun} disabled={!canOpenDryRun}>
            <ClipboardCheck size={15} />
            <span>試算 / 套用</span>
          </button>
          <button className="action-button" onClick={exportRenameCsv} disabled={!plan || busy || exportBusy}>
            <FileJson size={15} />
            <span>匯出 CSV</span>
          </button>
        </div>

        <section className="workbench-table-stack">
          <div className="iso-table-toolbar">
            <div>
              <div className="eyebrow">命名計畫</div>
              <h2>命名草稿</h2>
            </div>
            <label className="table-search">
              <FileSearch size={15} />
              <input value={searchTerm} onChange={(event) => setSearchTerm(event.target.value)} placeholder="搜尋 old/new/流水號/圖號/狀態" />
            </label>
            <label className="table-sort">
              <span>排序</span>
              <select value={sortMode} onChange={(event) => setSortMode(event.target.value as IsoSortMode)}>
                <option value="page">頁序</option>
                <option value="status">狀態</option>
                <option value="confidence">信心</option>
                <option value="filename">檔名</option>
              </select>
            </label>
            <label className="toggle-row table-toggle">
              <input type="checkbox" checked={problemOnly} onChange={(event) => setProblemOnly(event.target.checked)} />
              <span>只看問題列</span>
            </label>
          </div>

          {plan ? (
            <IsoPlanTable
              rows={visibleRows}
              selectedRowId={selectedRow?.id ?? ""}
              toggleRow={toggleRow}
              toggleAll={setAllRowsSelected}
              updateRow={updateRow}
              selectRow={setSelectedRowId}
            />
          ) : <IsoEmptyPlan generatePlan={generatePlan} chooseWorkFolder={chooseWorkFolder} busy={busy} />}
        </section>
      </main>

      <aside className="iso-inspector">
        {visualPanel}

        <div className="iso-side-card selected-row-card">
          <h3>目前列</h3>
          {selectedRow ? (
            <>
              <strong>{selectedRow.source_name}</strong>
              <span>{selectedRow.new_name || "尚無命名"}</span>
              <small>{selectedRow.note || selectedRow.vision_message || selectedRow.status}</small>
            </>
          ) : (
            <span>尚未選擇列</span>
          )}
        </div>

        <StatusTile icon={<FileText size={18} />} title="PDF 來源" value={compactPath(plan?.source.page_folder || pageFolder || combinePdf || workFolder || "等待來源")} tone={plan?.summary.total ? "ready" : "warn"} />
        <StatusTile icon={<Table2 size={18} />} title="ISO 清單" value={compactPath(plan?.source.iso_list || isoList || "等待來源")} tone={plan?.source.record_count ? "ready" : "warn"} />
        <StatusTile icon={<SearchCheck size={18} />} title="工作表" value={plan?.source.sheet_name || sheetName || "自動"} tone="ready" />
        <StatusTile icon={<Braces size={18} />} title="欄位" value={columnSummary} tone={plan?.source.record_count ? "ready" : "warn"} />

        <div className="issue-stack">
          <h3>問題</h3>
          {issueCards.map((issue, index) => (
            <div className={`issue-card ${issue.tone}`} key={`${issue.code}-${index}`}>
              {issue.tone === "ready" ? <CircleCheck size={16} /> : issue.tone === "warn" ? <CircleAlert size={16} /> : <AlertTriangle size={16} />}
              <div>
                <strong>{issue.code} · {issue.title}</strong>
                <span>{issue.detail}</span>
              </div>
            </div>
          ))}
        </div>

        <div className="iso-actions">
          <button className="action-button" onClick={generatePlan} disabled={!canGenerateDraft}>
            <RefreshCcw size={15} />
            <span>重新產生</span>
          </button>
          <button className="action-button" onClick={batchRunning ? cancelBatchDetect : startBatchDetect} disabled={batchRunning ? !canCancelBatch : !canStartBatch}>
            <ScanLine size={15} />
            <span>{batchRunning ? "取消判讀" : "批次判讀"}</span>
          </button>
          <button className="action-button" onClick={openDryRun} disabled={!canOpenDryRun}>
            <ClipboardCheck size={15} />
            <span>套用更名</span>
          </button>
          <button className="action-button" onClick={exportRenameCsv} disabled={!plan || busy || exportBusy}>
            <FileJson size={15} />
            <span>匯出 CSV</span>
          </button>
          <button className="action-button" onClick={() => void openRunLogDrawer()} disabled={runLogBusy}>
            <FileSearch size={15} />
            <span>{runLogBusy ? "讀取中" : "處理紀錄"}</span>
          </button>
          <button className="action-button" onClick={legacy.launch} disabled={legacy.busy}>
            <PanelRightOpen size={15} />
            <span>{legacy.busy ? "開啟中" : "舊版"}</span>
          </button>
        </div>
      </aside>
    </div>
  );
}

function ReadOnlySetting({ label, tone = "idle", value }: { label: string; tone?: "ready" | "warn" | "idle"; value: string }) {
  return (
    <div className={`readonly-setting ${tone}`}>
      <span>{label}</span>
      <strong title={value}>{value}</strong>
    </div>
  );
}
