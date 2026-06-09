import { AlertTriangle, Braces, ChevronRight, CircleAlert, CircleCheck, ClipboardCheck, FileJson, FileSearch, FileText, FolderOpen, Layers3, PanelRightOpen, RefreshCcw, ScanLine, SearchCheck, Settings, Table2 } from "lucide-react";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import { Gate } from "../components/Gate";
import { StatusTile } from "../components/StatusTile";
import type { LegacyBridgeState } from "../hooks/useLegacyBridge";
import type { IsoPlanRow, IsoWorkflowIssue, IsoWorkflowPlan, IsoWorkflowStep } from "../isoWorkflow";
import type { IsoSortMode } from "./helpers";
import { compactPath } from "./helpers";
import { IsoEmptyPlan, IsoMetric, PathPickerRow } from "./components/IsoControls";
import { IsoPlanTable } from "./components/NamingTable";

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
  headers,
  isoList,
  issueRows,
  legacy,
  lineCol,
  openDryRun,
  openRunLogDrawer,
  pageFolder,
  pattern,
  plan,
  problemOnly,
  profileLabel,
  readyCount,
  rows,
  runLogBusy,
  searchTerm,
  selectedCount,
  selectedRow,
  serialCol,
  setAllRowsSelected,
  setDetectSerials,
  setLineCol,
  setPattern,
  setProblemOnly,
  setSearchTerm,
  setSelectedRowId,
  setSerialCol,
  setSheetName,
  setSortMode,
  sheetName,
  sheetOptions,
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
  headers: string[];
  isoList: string;
  issueRows: IsoPlanRow[];
  legacy: LegacyBridgeState;
  lineCol: number | "";
  openDryRun: () => void;
  openRunLogDrawer: () => void;
  pageFolder: string;
  pattern: string;
  plan: IsoWorkflowPlan | null;
  problemOnly: boolean;
  profileLabel: string;
  readyCount: number;
  rows: IsoPlanRow[];
  runLogBusy: boolean;
  searchTerm: string;
  selectedCount: number;
  selectedRow?: IsoPlanRow;
  serialCol: number | "";
  setAllRowsSelected: (select: boolean) => void;
  setDetectSerials: Dispatch<SetStateAction<boolean>>;
  setLineCol: Dispatch<SetStateAction<number | "">>;
  setPattern: Dispatch<SetStateAction<string>>;
  setProblemOnly: Dispatch<SetStateAction<boolean>>;
  setSearchTerm: Dispatch<SetStateAction<string>>;
  setSelectedRowId: Dispatch<SetStateAction<string>>;
  setSerialCol: Dispatch<SetStateAction<number | "">>;
  setSheetName: Dispatch<SetStateAction<string>>;
  setSortMode: Dispatch<SetStateAction<IsoSortMode>>;
  sheetName: string;
  sheetOptions: string[];
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
            <small>{workFolder ? "folder autopilot" : pageFolder ? "page folder" : combinePdf ? "combine PDF" : "waiting"}</small>
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

        <div className="iso-control-section">
          <div className="panel-heading compact">
            <div>
              <span>ISO List</span>
              <small>{plan?.source.record_count ? `${plan.source.record_count} rows` : "auto columns"}</small>
            </div>
          </div>
        </div>
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
            {headers.map((header, index) => <option value={index} key={`serial-${header}-${index}`}>{index + 1}. {header}</option>)}
          </select>
        </label>
        <label className="field-row stacked">
          <span>圖號/檔名欄</span>
          <select value={lineCol} onChange={(event) => setLineCol(event.target.value === "" ? "" : Number(event.target.value))}>
            <option value="">auto</option>
            {headers.map((header, index) => <option value={index} key={`line-${header}-${index}`}>{index + 1}. {header}</option>)}
          </select>
        </label>
        <label className="field-row stacked">
          <span>Pattern</span>
          <input value={pattern} onChange={(event) => setPattern(event.target.value)} />
        </label>
        <label className="toggle-row">
          <input type="checkbox" checked={detectSerials} onChange={(event) => setDetectSerials(event.target.checked)} />
          <span>影像判讀流水號</span>
        </label>

        <div className="iso-side-card checklist">
          <h3>Checklist</h3>
          <Gate label="PDF 來源" state={plan?.summary.total ? "ready" : workFolder || combinePdf || pageFolder ? "idle" : "warn"} />
          <Gate label="ISO List" state={plan?.source.record_count ? "ready" : isoList || workFolder ? "idle" : "warn"} />
          <Gate label="欄位對應" state={plan?.source.serial_col !== undefined && plan.source.line_col !== undefined ? "ready" : "idle"} />
          <Gate label="Profile" state={hasPublishedProfile ? "ready" : activeProfileFolderReady ? "idle" : "warn"} />
          <Gate label="問題列" state={blockedCount ? "warn" : plan ? "ready" : "idle"} />
          <Gate label="舊工作台備援" state="ready" />
        </div>
      </aside>

      <main className="iso-table-panel">
        <div className="iso-metric-strip">
          <IsoMetric label="PDFs" value={rows.length} icon={<FileText size={17} />} />
          <IsoMetric label="Ready" value={readyCount} icon={<CircleCheck size={17} />} tone="ready" />
          <IsoMetric label="Warn" value={warnCount} icon={<CircleAlert size={17} />} tone="warn" />
          <IsoMetric label="Blocked" value={blockedCount} icon={<AlertTriangle size={17} />} tone="danger" />
          <IsoMetric label="Selected" value={selectedCount} icon={<ClipboardCheck size={17} />} tone="ready" />
        </div>

        <div className="iso-flow compact" aria-label="ISO workflow steps">
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

        <div className="iso-table-toolbar">
          <div>
            <div className="eyebrow">Rename plan</div>
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

        <StatusTile icon={<FileText size={18} />} title="PDF source" value={compactPath(plan?.source.page_folder || pageFolder || combinePdf || workFolder || "waiting")} tone={plan?.summary.total ? "ready" : "warn"} />
        <StatusTile icon={<Table2 size={18} />} title="ISO List" value={compactPath(plan?.source.iso_list || isoList || "waiting")} tone={plan?.source.record_count ? "ready" : "warn"} />
        <StatusTile icon={<SearchCheck size={18} />} title="Sheet" value={plan?.source.sheet_name || sheetName || "auto"} tone="ready" />
        <StatusTile icon={<Braces size={18} />} title="Columns" value={columnSummary} tone={plan?.source.record_count ? "ready" : "warn"} />

        <div className="issue-stack">
          <h3>Issues</h3>
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
          <button className="action-button" onClick={generatePlan} disabled={busy || applyBusy}>
            <RefreshCcw size={15} />
            <span>重新產生</span>
          </button>
          <button className="action-button" onClick={batchRunning ? cancelBatchDetect : startBatchDetect} disabled={busy || batchBusy || applyBusy}>
            <ScanLine size={15} />
            <span>{batchRunning ? "取消判讀" : "批次判讀"}</span>
          </button>
          <button className="action-button" onClick={openDryRun} disabled={!selectedCount || blockedCount > 0 || warnCount > 0 || busy || applyBusy}>
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
