import {
  AlertTriangle,
  Braces,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  ClipboardCheck,
  FileJson,
  FileSearch,
  FileText,
  FolderOpen,
  GitBranch,
  Layers3,
  PanelRightOpen,
  RefreshCcw,
  ScanLine,
  SearchCheck,
  Settings,
  ShieldCheck,
  Table2,
  TerminalSquare,
  WandSparkles,
} from "lucide-react";
import { isTauri } from "@tauri-apps/api/core";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { BridgeStatus } from "../components/BridgeStatus";
import { Gate } from "../components/Gate";
import { StatusTile } from "../components/StatusTile";
import { AutopilotView } from "./AutopilotView";
import { EngineerView } from "./EngineerView";
import {
  applyIsoPlan,
  cancelIsoJob,
  exportIsoDebugBundle,
  exportIsoPlanCsv,
  loadIsoJobStatus,
  loadIsoProfile,
  loadIsoPreview,
  listIsoRunLogs,
  pickIsoCombinePdf,
  pickIsoListFile,
  pickIsoPageFolder,
  pickIsoWorkFolder,
  publishIsoProfile,
  readIsoRunLog,
  replayIsoRunLog,
  revertIsoProfile,
  runIsoPlan,
  saveIsoDraftProfile,
  startIsoBatchDetect,
  type IsoJobPayload,
  type IsoPlanRow,
  type IsoProfilePayload,
  type IsoPreviewPayload,
  type IsoRegion,
  type IsoRunLogDetail,
  type IsoRunLogRef,
  type IsoRunLogSummary,
  type IsoWorkflowRequest,
  type IsoWorkflowPlan,
} from "../isoWorkflow";
import { useLegacyBridge } from "../hooks/useLegacyBridge";
import { FailureCard, type IsoFailureInfo } from "./components/FailureCard";
import { IsoEventLog } from "./components/EventLog";
import { ChecklistGate, IsoEmptyPlan, IsoMetric, PathPickerRow, TopSourceButton } from "./components/IsoControls";
import { IsoDryRunDialog, IsoResultDialog } from "./components/IsoDialogs";
import { IsoVisualPanel } from "./components/IsoVisualPanel";
import { IsoPlanTable } from "./components/NamingTable";
import { RunLogDrawer } from "./components/RunLogDrawer";
import {
  compactPath,
  createIsoRunId,
  DEFAULT_DRAWING_REGION,
  DEFAULT_SERIAL_REGION,
  filterIsoRows,
  formatIsoFilename,
  normalizeIsoRows,
  normalizeRegion,
  parentPath,
  sortIsoRows,
  summarizeIsoRows,
  targetPathFor,
  type IsoSortMode,
} from "./helpers";

const ISO_STEPS = [
  { label: "來源", state: "idle", meta: "select PDF" },
  { label: "拆頁", state: "idle", meta: "waiting" },
  { label: "ISO", state: "idle", meta: "select list" },
  { label: "草稿", state: "idle", meta: "dry-run plan" },
  { label: "確認", state: "idle", meta: "review rows" },
  { label: "更名", state: "idle", meta: "manual apply" },
];

const ISO_ISSUES = [
  { code: "NEW", title: "新版 ISO 工作台待命", detail: "選擇 PDF 與 ISO List 後可產生命名草稿", tone: "ready" },
  { code: "SAFE", title: "套用前先 dry-run", detail: "只會更名已勾選且通過檢查的 PDF", tone: "ready" },
  { code: "LEGACY", title: "舊工作台保留", detail: "工程師模式仍可叫出既有 PyQt workflow", tone: "ready" },
];

export function IsoBoard() {
  const legacy = useLegacyBridge("iso");
  const [isoView, setIsoView] = useState<"workbench" | "autopilot" | "engineer">("autopilot");
  const [workFolder, setWorkFolder] = useState("");
  const [combinePdf, setCombinePdf] = useState("");
  const [pageFolder, setPageFolder] = useState("");
  const [isoList, setIsoList] = useState("");
  const [sheetName, setSheetName] = useState("");
  const [serialCol, setSerialCol] = useState<number | "">("");
  const [lineCol, setLineCol] = useState<number | "">("");
  const [pattern, setPattern] = useState("{serial}--{line}.pdf");
  const [detectSerials, setDetectSerials] = useState(false);
  const [plan, setPlan] = useState<IsoWorkflowPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [applyBusy, setApplyBusy] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);
  const [batchJob, setBatchJob] = useState<IsoJobPayload | null>(null);
  const [batchBusy, setBatchBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [problemOnly, setProblemOnly] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [sortMode, setSortMode] = useState<IsoSortMode>("page");
  const [selectedRowId, setSelectedRowId] = useState("");
  const [preview, setPreview] = useState<IsoPreviewPayload | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [profile, setProfile] = useState<IsoProfilePayload | null>(null);
  const [profileBusy, setProfileBusy] = useState(false);
  const [serialRegion, setSerialRegion] = useState<IsoRegion>(DEFAULT_SERIAL_REGION);
  const [drawingRegion, setDrawingRegion] = useState<IsoRegion>(DEFAULT_DRAWING_REGION);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.7);
  const [activeRoi, setActiveRoi] = useState<"serial" | "drawing">("serial");
  const [dryRunOpen, setDryRunOpen] = useState(false);
  const [resultOpen, setResultOpen] = useState(false);
  const [oneClickStage, setOneClickStage] = useState<"idle" | "running" | "applying" | "review" | "done">("idle");
  const [recordPath, setRecordPath] = useState("");
  const [activeIsoRunId, setActiveIsoRunId] = useState("");
  const [oneClickRunLog, setOneClickRunLog] = useState<IsoRunLogRef | null>(null);
  const [runLogOpen, setRunLogOpen] = useState(false);
  const [runLogs, setRunLogs] = useState<IsoRunLogSummary[]>([]);
  const [runLogDetail, setRunLogDetail] = useState<IsoRunLogDetail | null>(null);
  const [runLogBusy, setRunLogBusy] = useState(false);
  const [isoFailure, setIsoFailure] = useState<IsoFailureInfo | null>(null);
  const [failureCopied, setFailureCopied] = useState(false);
  const [debugBundleBusy, setDebugBundleBusy] = useState(false);
  const [runStartedAt, setRunStartedAt] = useState<number | null>(null);
  const [nowTs, setNowTs] = useState(() => Date.now());
  const oneClickActiveRef = useRef(false);
  const terminalRef = useRef<HTMLDivElement | null>(null);
  const previewCacheRef = useRef(new Map<string, IsoPreviewPayload>());

  function requestPayload(rows?: IsoPlanRow[], overrides: Partial<IsoWorkflowRequest> = {}) {
    return {
      action: rows ? "apply" as const : "plan" as const,
      profile_folder: activeProfileFolder(),
      work_folder: workFolder,
      combine_pdf: combinePdf,
      page_folder: pageFolder,
      iso_list: isoList,
      sheet_name: sheetName,
      serial_col: serialCol,
      line_col: lineCol,
      pattern,
      serial_region: serialRegion,
      drawing_region: drawingRegion,
      confidence_threshold: confidenceThreshold,
      detect_serials: detectSerials,
      run_id: overrides.run_id || activeIsoRunId || undefined,
      rows,
    };
  }

  function activeProfileFolder(overrides: Partial<IsoWorkflowRequest> = {}) {
    return (
      overrides.profile_folder ||
      overrides.work_folder ||
      workFolder ||
      overrides.page_folder ||
      pageFolder ||
      parentPath(overrides.combine_pdf || combinePdf) ||
      parentPath(overrides.iso_list || isoList)
    );
  }

  function applyProfile(result: IsoProfilePayload, options: { syncPageFolder?: boolean } = {}) {
    if (result.detected_combine_pdf) {
      setCombinePdf(result.detected_combine_pdf);
      setWorkFolder(parentPath(result.detected_combine_pdf));
    }
    if (options.syncPageFolder && result.detected_page_folder_exists && result.detected_page_folder) {
      setPageFolder(result.detected_page_folder);
    }
    if (result.detected_iso_list) {
      setIsoList(result.detected_iso_list);
    }
    if (!result.exists) {
      return;
    }
    setPattern(result.pattern || "{serial}--{line}.pdf");
    setIsoList(result.iso_list_path || result.detected_iso_list || "");
    setSheetName(result.sheet_name || "");
    setSerialCol(result.serial_col ?? "");
    setLineCol(result.line_col ?? "");
    setSerialRegion(result.serial_region || DEFAULT_SERIAL_REGION);
    setDrawingRegion(result.drawing_region || DEFAULT_DRAWING_REGION);
    setConfidenceThreshold(result.confidence_threshold ?? 0.7);
  }

  async function restoreProfile(request: Partial<IsoWorkflowRequest>, options: { syncPageFolder?: boolean } = {}) {
    if (!isTauri()) {
      return null;
    }
    setProfileBusy(true);
    try {
      const result = await loadIsoProfile({ ...request, profile_folder: activeProfileFolder(request) });
      setProfile(result);
      applyProfile(result, options);
      return result;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      return null;
    } finally {
      setProfileBusy(false);
    }
  }

  function sourceLoadMessage(result: IsoProfilePayload | null, fallback: string) {
    if (!result) {
      return fallback;
    }
    const parts: string[] = [];
    if (result.detected_combine_pdf) {
      parts.push(`PDF ${compactPath(result.detected_combine_pdf)}`);
    }
    if (result.detected_iso_list) {
      parts.push(`ISO ${compactPath(result.detected_iso_list)}`);
    }
    if (result.published_exists ?? result.exists) {
      parts.push(`Profile ${compactPath(result.folder)}`);
    } else if (result.draft_exists) {
      parts.push("Profile draft");
    }
    return parts.length ? `已自動載入：${parts.join(" · ")}` : fallback;
  }

  function registerRunLog(ref?: IsoRunLogRef | null, fallbackRunId = "") {
    if (ref) {
      setOneClickRunLog(ref);
      setActiveIsoRunId(ref.run_id);
      return ref.run_id;
    }
    if (fallbackRunId) {
      setActiveIsoRunId(fallbackRunId);
      return fallbackRunId;
    }
    return activeIsoRunId;
  }

  function setOneClickFailure(title: string, caught: unknown, runId = activeIsoRunId, runLog = oneClickRunLog) {
    const detail = caught instanceof Error ? caught.message : String(caught || "");
    const knownRunId = runLog?.run_id || runId || activeIsoRunId;
    setFailureCopied(false);
    setIsoFailure({
      run_id: knownRunId || undefined,
      title,
      summary: detail || "ISO 一鍵命名沒有完成，請把此 Run ID 交給工程師檢查。",
      detail: runLog?.run_json ? `run log: ${compactPath(runLog.run_json)}` : "",
      run_json: runLog?.run_json,
      events_jsonl: runLog?.events_jsonl,
    });
  }

  async function copyFailureForEngineer() {
    if (!isoFailure) {
      return;
    }
    const text = [
      "ISO 一鍵命名失敗摘要",
      `Run ID: ${isoFailure.run_id || "未取得"}`,
      `原因: ${isoFailure.summary}`,
      isoFailure.run_json ? `Run log: ${isoFailure.run_json}` : "",
      isoFailure.events_jsonl ? `Events: ${isoFailure.events_jsonl}` : "",
      workFolder ? `工作資料夾: ${workFolder}` : "",
      combinePdf ? `Combine PDF: ${combinePdf}` : "",
      pageFolder ? `Page folder: ${pageFolder}` : "",
      isoList ? `ISO List: ${isoList}` : "",
    ].filter(Boolean).join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setFailureCopied(true);
      setMessage("已複製 ISO 失敗摘要。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function exportFailureBundle() {
    if (!isoFailure?.run_id) {
      setError("缺少 run_id，無法匯出問題包。");
      return;
    }
    setDebugBundleBusy(true);
    setError("");
    try {
      const result = await exportIsoDebugBundle({ run_id: isoFailure.run_id });
      setMessage(result.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setDebugBundleBusy(false);
    }
  }

  async function openRunLogDrawer(runId = activeIsoRunId) {
    if (!isTauri()) {
      setError("請用 Tauri 桌面版讀取處理紀錄。");
      return;
    }
    setRunLogOpen(true);
    await refreshRunLogs(runId);
  }

  async function refreshRunLogs(preferredRunId = runLogDetail?.run.run_id || activeIsoRunId) {
    setRunLogBusy(true);
    setError("");
    try {
      const payload = await listIsoRunLogs();
      setRunLogs(payload.runs);
      const nextRunId = preferredRunId || payload.runs[0]?.run_id || "";
      if (nextRunId) {
        await loadRunLogDetail(nextRunId);
      } else {
        setRunLogDetail(null);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRunLogBusy(false);
    }
  }

  async function loadRunLogDetail(runId: string) {
    if (!runId) {
      return;
    }
    setRunLogBusy(true);
    setError("");
    try {
      const detail = await readIsoRunLog(runId);
      setRunLogDetail(detail);
      setActiveIsoRunId(runId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRunLogBusy(false);
    }
  }

  async function replayRunLog(runId: string) {
    if (!runId) {
      return;
    }
    setRunLogBusy(true);
    setError("");
    try {
      const replay = await replayIsoRunLog(runId);
      setPlan(replay);
      setWorkFolder(replay.source.work_folder || workFolder);
      setCombinePdf(replay.source.combine_pdf || combinePdf);
      setPageFolder(replay.source.page_folder || pageFolder);
      setIsoList(replay.source.iso_list || isoList);
      setSheetName(replay.source.sheet_name || sheetName);
      setSerialCol(replay.source.serial_col ?? serialCol);
      setLineCol(replay.source.line_col ?? lineCol);
      setSelectedRowId(replay.rows[0]?.id ?? "");
      setResultOpen(false);
      setDryRunOpen(false);
      setProblemOnly(false);
      setIsoView("workbench");
      setRunLogOpen(false);
      setMessage(replay.message || `已 replay：${runId}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRunLogBusy(false);
    }
  }

  function openFailureWorkbench() {
    const firstProblem = plan?.rows.find((row) => row.status === "blocked" || row.status === "warn");
    if (firstProblem) {
      setSelectedRowId(firstProblem.id);
      setProblemOnly(true);
    }
    setIsoView("workbench");
  }

  async function chooseWorkFolder() {
    try {
      const path = await pickIsoWorkFolder();
      if (path) {
        setWorkFolder(path);
        setCombinePdf("");
        setPageFolder("");
        setPlan(null);
        setIsoFailure(null);
        const restored = await restoreProfile({ work_folder: path }, { syncPageFolder: true });
        setMessage(sourceLoadMessage(restored, "已選工作資料夾，可直接產生命名草稿。"));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function chooseCombinePdf() {
    try {
      const path = await pickIsoCombinePdf();
      if (path) {
        setCombinePdf(path);
        setPageFolder("");
        const folder = parentPath(path);
        setWorkFolder(folder);
        setPlan(null);
        setIsoFailure(null);
        const restored = await restoreProfile({ work_folder: folder, combine_pdf: path }, { syncPageFolder: true });
        setMessage(sourceLoadMessage(restored, "已選 Combine PDF，可直接產生命名草稿。"));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function choosePageFolder() {
    try {
      const path = await pickIsoPageFolder();
      if (path) {
        setPageFolder(path);
        setCombinePdf("");
        setWorkFolder(path);
        setPlan(null);
        setIsoFailure(null);
        const restored = await restoreProfile({ work_folder: path, page_folder: path });
        setMessage(sourceLoadMessage(restored, "已選 Page folder，可直接產生命名草稿。"));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function chooseIsoList() {
    try {
      const path = await pickIsoListFile();
      if (path) {
        setIsoList(path);
        setPlan(null);
        setIsoFailure(null);
        setProfile((current) => current ? { ...current, iso_list_path: path } : current);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function generatePlan() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await runIsoPlan(requestPayload());
      setPlan(result);
      setIsoList(result.source.iso_list || isoList);
      setPageFolder(result.source.page_folder || pageFolder);
      setSheetName(result.source.sheet_name || sheetName);
      setSerialCol(result.source.serial_col ?? "");
      setLineCol(result.source.line_col ?? "");
      setSelectedRowId(result.rows[0]?.id ?? "");
      setResultOpen(true);
      let profileNote = "";
      try {
        const savedProfile = await saveIsoDraftProfile({
          profile_folder:
            result.source.profile?.folder ||
            result.source.work_folder ||
            result.source.page_folder ||
            parentPath(result.source.combine_pdf) ||
            activeProfileFolder(),
          work_folder: result.source.work_folder || workFolder,
          combine_pdf: result.source.combine_pdf || combinePdf,
          page_folder: result.source.page_folder || pageFolder,
          iso_list: result.source.iso_list || isoList,
          sheet_name: result.source.sheet_name || sheetName,
          serial_col: result.source.serial_col ?? serialCol,
          line_col: result.source.line_col ?? lineCol,
          pattern: result.source.pattern || pattern,
          confidence_threshold: confidenceThreshold,
          serial_region: serialRegion,
          drawing_region: drawingRegion,
        });
        setProfile(savedProfile);
        profileNote = " Profile 草稿已保存（未發布到一鍵）。";
      } catch (caught) {
        profileNote = ` Profile 草稿保存失敗：${caught instanceof Error ? caught.message : String(caught)}`;
      }
      setMessage(`已產生命名草稿：${result.summary.selected} / ${result.summary.total} 可套用。${profileNote}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function publishProfileToOneClick() {
    if (!isTauri()) {
      setError("請用 Tauri 桌面版發布 Profile。");
      return;
    }
    const folder = activeProfileFolder();
    if (!folder) {
      setError("請先選擇工作資料夾或來源檔案，才能發布 Profile。");
      return;
    }
    setProfileBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await publishIsoProfile({
        profile_folder: folder,
        work_folder: workFolder,
        combine_pdf: combinePdf,
        page_folder: pageFolder,
        iso_list: isoList,
        sheet_name: sheetName,
        serial_col: serialCol,
        line_col: lineCol,
        pattern,
        confidence_threshold: confidenceThreshold,
        serial_region: serialRegion,
        drawing_region: drawingRegion,
      });
      setProfile(result);
      applyProfile(result);
      setMessage(`已發布 Profile 到一鍵：${compactPath(result.folder)}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setProfileBusy(false);
    }
  }

  async function revertPublishedProfile() {
    if (!isTauri()) {
      setError("請用 Tauri 桌面版回復 Profile。");
      return;
    }
    const folder = activeProfileFolder();
    if (!folder) {
      setError("請先選擇工作資料夾或來源檔案，才能回復 Profile。");
      return;
    }
    setProfileBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await revertIsoProfile({
        profile_folder: folder,
        work_folder: workFolder,
        combine_pdf: combinePdf,
        page_folder: pageFolder,
        iso_list: isoList,
      });
      setProfile(result);
      applyProfile(result);
      setMessage(`已回復上一版 Profile：${compactPath(result.folder)}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setProfileBusy(false);
    }
  }

  function openDryRun() {
    if (!plan) {
      return;
    }
    if (blockedCount) {
      setError(`還有 ${blockedCount} 筆 blocked，修正前不能套用。`);
      chooseProblemRow();
      return;
    }
    if (warnCount) {
      setError(`還有 ${warnCount} 筆 warn，請逐列確認後再套用。`);
      chooseProblemRow();
      return;
    }
    const selected = plan.rows.filter((row) => row.selected && row.status === "ready");
    if (!selected.length) {
      setError("沒有可套用的 ready 列；請先勾選 ready 列。");
      return;
    }
    setDryRunOpen(true);
  }

  async function applySelectedRows() {
    if (!plan) {
      return;
    }
    if (blockedCount || warnCount) {
      setError(blockedCount ? `還有 ${blockedCount} 筆 blocked，修正前不能套用。` : `還有 ${warnCount} 筆 warn，請逐列確認後再套用。`);
      chooseProblemRow();
      return;
    }
    const selected = plan.rows.filter((row) => row.selected && row.status === "ready");
    if (!selected.length) {
      setError("沒有勾選任何 ready 可更名列。");
      return;
    }
    setApplyBusy(true);
    setError("");
    setMessage("");
    try {
      let recPath = "";
      let recordWarning = "";
      try {
        const rec = await exportIsoPlanCsv({
          ...requestPayload(plan.rows),
          work_folder: plan.source.work_folder || workFolder,
          combine_pdf: plan.source.combine_pdf || combinePdf,
          page_folder: plan.source.page_folder || pageFolder,
          iso_list: plan.source.iso_list || isoList,
          sheet_name: plan.source.sheet_name || sheetName,
          serial_col: plan.source.serial_col ?? serialCol,
          line_col: plan.source.line_col ?? lineCol,
          pattern: plan.source.pattern || pattern,
        });
        recPath = rec.export_path;
        setRecordPath(recPath);
      } catch (recordError) {
        recordWarning = `更名記錄寫入失敗:${recordError instanceof Error ? recordError.message : String(recordError)} `;
      }
      const result = await applyIsoPlan(requestPayload(selected));
      const renamedIds = new Set(selected.map((row) => row.id));
      updatePlanRows((rows) => rows.filter((row) => !renamedIds.has(row.id)));
      setSelectedRowId(plan.rows.find((row) => !renamedIds.has(row.id))?.id ?? "");
      setDryRunOpen(false);
      setResultOpen(false);
      setMessage(`${recordWarning}${result.message}${recPath ? ` 記錄已存:${recPath}` : ""} 已從清單移除 ${selected.length} 列;要重新掃描可按「重新產生」。`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setApplyBusy(false);
    }
  }

  async function runOneClick() {
    setError("");
    if (oneClickStage === "done") {
      setPlan(null);
      setOneClickStage("idle");
      setRecordPath("");
      setActiveIsoRunId("");
      setOneClickRunLog(null);
      setIsoFailure(null);
      setMessage("");
      return;
    }
    if (oneClickStage === "running" && batchRunning && batchJob) {
      await cancelBatchDetect();
      setMessage("正在取消一鍵命名…");
      return;
    }
    if (!workFolder && !combinePdf && !pageFolder) {
      await chooseWorkFolder();
      return;
    }
    if (oneClickStage === "review" && plan) {
      const blockedRows = plan.rows.filter((row) => row.status === "blocked");
      const warnRows = plan.rows.filter((row) => row.status === "warn");
      const canApplyRows = plan.rows.filter((row) => row.selected && row.status === "ready");
      if (blockedRows.length || warnRows.length) {
        setSelectedRowId(blockedRows[0]?.id ?? warnRows[0]?.id ?? "");
        setProblemOnly(true);
        setIsoView("workbench");
        setMessage(blockedRows.length ? `還有 ${blockedRows.length} 個 blocked 列,先在工作台修正後再更名。` : `還有 ${warnRows.length} 個 warn 列,逐列確認後才能更名。`);
        return;
      }
      if (!canApplyRows.length) {
        setMessage("沒有 ready 且勾選的列可更名。");
        return;
      }
      await autoApplyWithRecord(plan);
      return;
    }
    setOneClickStage("running");
    setMessage("");
    setRecordPath("");
    setPlan(null);
    setRunStartedAt(Date.now());
    const runId = createIsoRunId();
    setActiveIsoRunId(runId);
    setOneClickRunLog(null);
    setIsoFailure(null);
    setFailureCopied(false);
    oneClickActiveRef.current = true;
    try {
      const job = await startIsoBatchDetect({ ...requestPayload(undefined, { run_id: runId }), detect_serials: true });
      registerRunLog(job.run_log, runId);
      setBatchJob(job);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setOneClickFailure("一鍵命名啟動失敗", caught, runId);
      setOneClickStage("idle");
      oneClickActiveRef.current = false;
    }
  }

  async function autoApplyWithRecord(currentPlan: IsoWorkflowPlan) {
    const blockedRows = currentPlan.rows.filter((row) => row.status === "blocked");
    const warnRows = currentPlan.rows.filter((row) => row.status === "warn");
    if (blockedRows.length || warnRows.length) {
      setSelectedRowId(blockedRows[0]?.id ?? warnRows[0]?.id ?? "");
      setProblemOnly(true);
      setOneClickStage("review");
      setMessage(blockedRows.length ? `還有 ${blockedRows.length} 個 blocked 列,先修正後才能完成一鍵更名。` : `還有 ${warnRows.length} 個 warn 列,逐列確認後才能完成一鍵更名。`);
      return;
    }
    const applyRows = currentPlan.rows.filter((row) => row.selected && row.status === "ready");
    if (!applyRows.length) {
      setOneClickStage("done");
      setMessage("沒有需要更名的檔案。");
      return;
    }
    setApplyBusy(true);
    setOneClickStage("applying");
    setError("");
    let recPath = "";
    let recordWarning = "";
    try {
      try {
        const rec = await exportIsoPlanCsv({
          ...requestPayload(currentPlan.rows),
          work_folder: currentPlan.source.work_folder || workFolder,
          combine_pdf: currentPlan.source.combine_pdf || combinePdf,
          page_folder: currentPlan.source.page_folder || pageFolder,
          iso_list: currentPlan.source.iso_list || isoList,
          sheet_name: currentPlan.source.sheet_name || sheetName,
          serial_col: currentPlan.source.serial_col ?? serialCol,
          line_col: currentPlan.source.line_col ?? lineCol,
          pattern: currentPlan.source.pattern || pattern,
        });
        recPath = rec.export_path;
        setRecordPath(recPath);
      } catch (recErr) {
        recordWarning = `更名記錄寫入失敗:${recErr instanceof Error ? recErr.message : String(recErr)} `;
      }
      const result = await applyIsoPlan(requestPayload(applyRows));
      registerRunLog(result.run_log);
      const renamedIds = new Set(applyRows.map((row) => row.id));
      updatePlanRows((rows) => rows.filter((row) => !renamedIds.has(row.id)));
      setSelectedRowId(currentPlan.rows.find((row) => !renamedIds.has(row.id))?.id ?? "");
      setOneClickStage("done");
      setMessage(`${recordWarning}${result.message}${recPath ? ` 記錄已存:${recPath}` : ""}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setOneClickFailure("套用更名失敗", caught);
      setOneClickStage("review");
    } finally {
      setApplyBusy(false);
    }
  }

  function resetRoi(region: "serial" | "drawing" = activeRoi) {
    if (region === "serial") {
      setSerialRegion(DEFAULT_SERIAL_REGION);
      return;
    }
    setDrawingRegion(DEFAULT_DRAWING_REGION);
  }

  function updateActiveRoi(field: keyof IsoRegion, value: number) {
    const setter = activeRoi === "serial" ? setSerialRegion : setDrawingRegion;
    setter((current) => normalizeRegion({ ...current, [field]: value }));
  }

  async function exportRenameCsv() {
    if (!plan) {
      setError("尚未產生命名草稿，無法匯出 CSV。");
      return;
    }
    setExportBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await exportIsoPlanCsv({
        ...requestPayload(plan.rows),
        work_folder: plan.source.work_folder || workFolder,
        combine_pdf: plan.source.combine_pdf || combinePdf,
        page_folder: plan.source.page_folder || pageFolder,
        iso_list: plan.source.iso_list || isoList,
        sheet_name: plan.source.sheet_name || sheetName,
        serial_col: plan.source.serial_col ?? serialCol,
        line_col: plan.source.line_col ?? lineCol,
        pattern: plan.source.pattern || pattern,
      });
      setMessage(result.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setExportBusy(false);
    }
  }

  async function startBatchDetect() {
    setBatchBusy(true);
    setError("");
    setMessage("");
    try {
      const job = await startIsoBatchDetect({ ...requestPayload(), detect_serials: true });
      setBatchJob(job);
      setMessage(`批次判讀已啟動：${job.job_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBatchBusy(false);
    }
  }

  async function cancelBatchDetect() {
    if (!batchJob) {
      return;
    }
    setBatchBusy(true);
    try {
      const job = await cancelIsoJob(batchJob.job_id);
      setBatchJob(job);
      setMessage("已送出取消批次判讀。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBatchBusy(false);
    }
  }

  function toggleRow(rowId: string) {
    updatePlanRows((rows) => rows.map((row) => row.id === rowId && row.status !== "blocked" ? { ...row, selected: !row.selected } : row));
  }

  function setAllRowsSelected(select: boolean) {
    updatePlanRows((rows) => rows.map((row) => (row.status === "blocked" ? row : { ...row, selected: select })));
  }

  function updateRow(rowId: string, field: "serial" | "line_no" | "new_name", value: string) {
    updatePlanRows((rows) => rows.map((row) => {
      if (row.id !== rowId) {
        return row;
      }
      const next = { ...row, [field]: value, note: "manual corrected", vision_message: "manual corrected" };
      if (field === "serial" || field === "line_no") {
        next.new_name = formatIsoFilename(pattern, field === "serial" ? value : next.serial, field === "line_no" ? value : next.line_no);
      }
      next.target_path = targetPathFor(next.source_path, next.new_name);
      next.selected = Boolean(next.new_name && next.new_name !== next.source_name);
      return next;
    }));
  }

  function updatePlanRows(mutator: (rows: IsoPlanRow[]) => IsoPlanRow[]) {
    setPlan((current) => {
      if (!current) {
        return current;
      }
      const rows = normalizeIsoRows(mutator(current.rows));
      return { ...current, rows, summary: summarizeIsoRows(rows) };
    });
  }

  function chooseProblemRow() {
    const allRows = plan?.rows ?? [];
    const problems = allRows.filter((row) => row.status === "blocked" || row.status === "warn");
    if (!problems.length) {
      return;
    }
    const currentIndex = allRows.findIndex((row) => row.id === selectedRowId);
    const next = problems.find((row) => allRows.findIndex((candidate) => candidate.id === row.id) > currentIndex) ?? problems[0];
    setSelectedRowId(next.id);
    setProblemOnly(true);
  }

  function adoptPreviewVision() {
    if (!selectedRow || !preview?.vision?.text) {
      return;
    }
    updateRow(selectedRow.id, "serial", preview.vision.text);
  }

  function confirmSelectedRow() {
    if (!selectedRow) {
      return;
    }
    updatePlanRows((rows) => rows.map((row) => row.id === selectedRow.id ? { ...row, status: "ready", note: "", vision_message: row.vision_message.includes("manual") ? "manual confirmed" : "", selected: row.new_name !== row.source_name } : row));
  }

  const rows = plan?.rows ?? [];
  const selectedCount = rows.filter((row) => row.selected && row.status === "ready").length;
  const blockedCount = rows.filter((row) => row.status === "blocked").length;
  const warnCount = rows.filter((row) => row.status === "warn").length;
  const readyCount = rows.filter((row) => row.status === "ready").length;
  const issueRows = rows.filter((row) => row.status === "blocked" || row.status === "warn");
  const visibleRows = useMemo(() => sortIsoRows(filterIsoRows(rows, searchTerm, problemOnly), sortMode), [rows, searchTerm, problemOnly, sortMode]);
  const selectedRow = rows.find((row) => row.id === selectedRowId) ?? rows[0];
  const columnSummary = plan?.source.headers && plan.source.serial_col !== undefined && plan.source.line_col !== undefined
    ? `${plan.source.headers[plan.source.serial_col] ?? `col ${plan.source.serial_col + 1}`} -> ${plan.source.headers[plan.source.line_col] ?? `col ${plan.source.line_col + 1}`}`
    : "auto";
  const headers = plan?.source.headers ?? [];
  const sheetOptions = plan?.source.sheet_options ?? (sheetName ? [sheetName] : []);
  const hasPublishedProfile = profile?.published_exists ?? (profile?.profile_scope === "draft" ? false : profile?.exists);
  const hasDraftProfile = profile?.draft_exists ?? (profile?.profile_scope === "draft" && profile.exists);
  const profileHistoryCount = profile?.history_count ?? 0;
  const profileLabel = profileBusy
    ? "loading"
    : profile?.profile_scope === "draft"
      ? "draft saved"
      : hasPublishedProfile
        ? compactPath(profile?.folder || "")
        : activeProfileFolder() ? "default profile" : "waiting";
  const batchRunning = batchJob?.state === "queued" || batchJob?.state === "running" || batchJob?.state === "cancel_requested";
  const workflowEvents = [...(batchJob?.events ?? []), ...(plan?.issues ?? [])];
  const hasOneClickSource = Boolean(workFolder || combinePdf || pageFolder);
  const elapsedSec = runStartedAt ? Math.max(0, Math.round((nowTs - runStartedAt) / 1000)) : 0;
  const oneClickRunning = oneClickStage === "running";
  const oneClickApplying = oneClickStage === "applying";
  const detectDone = batchJob?.progress?.done ?? (plan ? plan.summary.total : 0);
  const detectTotal = batchJob?.progress?.total ?? plan?.summary.total ?? 0;
  const oneClickBusy = busy || batchBusy || applyBusy;
  const oneClickButton = (() => {
    if (oneClickRunning) return { icon: <ScanLine size={20} />, label: `取消判讀 ${detectDone}/${detectTotal || "?"} · ${elapsedSec}s`, hint: "正在讀取 worker 真實事件;按一下可取消" };
    if (applyBusy) return { icon: <ClipboardCheck size={20} />, label: "更名中…", hint: "正在寫入更名記錄" };
    if (oneClickStage === "done") return { icon: <RefreshCcw size={20} />, label: "完成 · 再處理一批", hint: recordPath ? `記錄:${compactPath(recordPath)}` : "按一下清空,重新開始" };
    if (!hasOneClickSource) return { icon: <FolderOpen size={20} />, label: "選擇工作資料夾", hint: "選好後再按一次開始一鍵命名" };
    if (oneClickStage === "review" && !selectedCount && blockedCount) return { icon: <AlertTriangle size={20} />, label: `前往工作台修正 ${blockedCount} 筆`, hint: "blocked 列不會自動更名,先修正檔名或 ISO 對應" };
    if (oneClickStage === "review") return { icon: <ClipboardCheck size={20} />, label: `我已確認,更名 ${selectedCount} 筆`, hint: warnCount ? `${warnCount} 個待確認:點清單列,在右側採用或改值` : "全部已確認,可更名" };
    return { icon: <WandSparkles size={20} />, label: "開始一鍵命名", hint: "全綠會直接更名到底,不再跳確認" };
  })();
  const pipelineStages: Array<{ key: string; label: string; icon: React.ReactNode; state: string; detail: string; seconds: number | null }> = [
    { key: "source", label: "來源", icon: <FolderOpen size={18} />, state: hasOneClickSource ? "done" : "idle", detail: hasOneClickSource ? compactPath(workFolder || combinePdf || pageFolder) : "選資料夾", seconds: null },
    { key: "split", label: "拆頁", icon: <Layers3 size={18} />, state: detectTotal ? "done" : oneClickRunning ? "run" : "idle", detail: detectTotal ? `${detectTotal} 頁` : "等待", seconds: null },
    { key: "detect", label: "判讀流水號", icon: <ScanLine size={18} />, state: oneClickRunning ? "run" : plan ? "done" : "idle", detail: oneClickRunning ? `${detectDone}/${detectTotal}` : plan ? `${readyCount} 已讀` : "等待", seconds: oneClickRunning ? elapsedSec : null },
    { key: "match", label: "對 ISO", icon: <Table2 size={18} />, state: plan?.source.record_count ? "done" : "idle", detail: plan?.source.record_count ? `${plan.source.record_count} 列` : "等待", seconds: null },
    { key: "name", label: "命名", icon: <WandSparkles size={18} />, state: plan ? (blockedCount ? "warn" : "done") : "idle", detail: plan ? `${plan.summary.total} 檔` : "等待", seconds: null },
    { key: "apply", label: "更名", icon: <ClipboardCheck size={18} />, state: oneClickStage === "done" ? "done" : oneClickApplying ? "run" : "idle", detail: oneClickStage === "done" ? "完成" : oneClickApplying ? "寫入中" : "等待", seconds: oneClickApplying ? elapsedSec : null },
  ];
  const echoLines = ([...(batchJob?.events ?? []), ...(plan?.issues ?? [])] as unknown as Array<{ code?: string; tone?: string; title?: string; detail?: string }>).slice(-80);

  useEffect(() => {
    let cancelled = false;
    if (!selectedRow?.source_path) {
      setPreview(null);
      setPreviewError("");
      setPreviewBusy(false);
      return;
    }
    if (!isTauri()) {
      setPreview(null);
      setPreviewError("桌面版會顯示 PDF 預覽與裁切圖。");
      setPreviewBusy(false);
      return;
    }
    const cacheKey = `${selectedRow.source_path}|${detectSerials}|${JSON.stringify(serialRegion)}|${JSON.stringify(drawingRegion)}`;
    const cached = previewCacheRef.current.get(cacheKey);
    if (cached) {
      setPreview(cached);
      setPreviewError("");
      setPreviewBusy(false);
      return;
    }
    setPreviewBusy(true);
    setPreviewError("");
    loadIsoPreview({
      source_path: selectedRow.source_path,
      detect_serial: detectSerials,
      serial_region: serialRegion,
      drawing_region: drawingRegion,
    })
      .then((payload) => {
        if (!cancelled) {
          setPreview(payload);
          previewCacheRef.current.set(cacheKey, payload);
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          setPreview(null);
          setPreviewError(caught instanceof Error ? caught.message : String(caught));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setPreviewBusy(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRow?.source_path, detectSerials, serialRegion, drawingRegion]);

  useEffect(() => {
    if (!batchJob || !batchRunning) {
      return;
    }
    let cancelled = false;
    const timer = window.setInterval(() => {
      void loadIsoJobStatus(batchJob.job_id)
        .then((job) => {
          if (cancelled) {
            return;
          }
          setBatchJob(job);
          registerRunLog(job.run_log, job.run_id || activeIsoRunId);
          if (job.result && (job.state === "completed" || job.state === "cancelled")) {
            setPlan(job.result);
            if (oneClickActiveRef.current) {
              oneClickActiveRef.current = false;
              if (job.state === "cancelled") {
                setOneClickStage("idle");
                setMessage("已取消一鍵命名,保留已完成列。");
              } else {
                const problems = job.result.rows.filter((row) => row.status === "warn" || row.status === "blocked");
                setSelectedRowId(problems[0]?.id ?? job.result.rows[0]?.id ?? "");
                if (problems.length) {
                  setOneClickStage("review");
                  setMessage(`有 ${problems.length} 個待確認值,處理後按一次即可更名。`);
                } else {
                  void autoApplyWithRecord(job.result);
                }
              }
            } else {
              setSelectedRowId(job.result.rows[0]?.id ?? "");
              setResultOpen(true);
              setMessage(job.state === "completed" ? "批次判讀完成，命名草稿已更新。" : "批次判讀已取消，保留已完成列。");
            }
          }
          if (job.error) {
            setError(job.error);
            setOneClickFailure("一鍵命名沒有完成", job.error, job.run_id || activeIsoRunId, job.run_log || oneClickRunLog);
            if (oneClickActiveRef.current) {
              oneClickActiveRef.current = false;
              setOneClickStage("idle");
            }
          }
        })
        .catch((caught) => {
          if (!cancelled) {
            setError(caught instanceof Error ? caught.message : String(caught));
            if (oneClickActiveRef.current) {
              setOneClickFailure("讀取一鍵進度失敗", caught);
            }
          }
        });
    }, 350);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [batchJob?.job_id, batchRunning, activeIsoRunId, oneClickRunLog]);

  useEffect(() => {
    if (oneClickStage !== "running" && oneClickStage !== "applying") {
      return;
    }
    const id = window.setInterval(() => setNowTs(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [oneClickStage]);

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [batchJob?.events?.length, oneClickStage]);

  const visualPanel = (
    <IsoVisualPanel
      activeRoi={activeRoi}
      busy={previewBusy}
      drawingRegion={drawingRegion}
      error={previewError}
      preview={preview}
      resetRoi={resetRoi}
      row={selectedRow}
      serialRegion={serialRegion}
      setActiveRoi={setActiveRoi}
      adoptPreviewVision={adoptPreviewVision}
      confirmSelectedRow={confirmSelectedRow}
      nextProblem={chooseProblemRow}
      updateActiveRoi={updateActiveRoi}
    />
  );

  return (
    <section className="iso-board iso-workbench">
      <div className="iso-workbench-top">
        <div>
          <div className="eyebrow">Tauri ISO workbench</div>
          <h2>ISO PDF 拆頁命名工作臺</h2>
          {isoView !== "autopilot" ? (
            <div className="iso-source-strip">
              <TopSourceButton icon={<FolderOpen size={15} />} label="工作資料夾" value={workFolder} onPick={chooseWorkFolder} />
              <TopSourceButton icon={<FileText size={15} />} label="Combine PDF" value={combinePdf} onPick={chooseCombinePdf} />
              <TopSourceButton icon={<Layers3 size={15} />} label="Page folder" value={pageFolder} onPick={choosePageFolder} />
              <TopSourceButton icon={<Table2 size={15} />} label="ISO List" value={isoList} onPick={chooseIsoList} />
            </div>
          ) : null}
        </div>
        <div className="iso-top-actions">
          <div className="mode-switch" role="tablist" aria-label="ISO 工作模式">
            <button className={isoView === "autopilot" ? "active" : ""} onClick={() => setIsoView("autopilot")} title="一鍵導引:選來源 → 產生草稿 → 套用">
              <WandSparkles size={15} />
              <span>一鍵</span>
            </button>
            <button className={isoView === "workbench" ? "active" : ""} onClick={() => setIsoView("workbench")} title="工作台:逐列校對命名表與預覽">
              <Table2 size={15} />
              <span>工作台</span>
            </button>
            <button className={isoView === "engineer" ? "active" : ""} onClick={() => setIsoView("engineer")} title="調校:ROI、欄位對應、信心門檻、Profile">
              <Settings size={15} />
              <span>調校</span>
            </button>
          </div>
          {isoView !== "autopilot" ? (
            <button className="icon-button" onClick={legacy.launch} disabled={legacy.busy} title="暫時開啟舊版工作台(轉移完成後移除)">
              <PanelRightOpen size={16} />
              <span>{legacy.busy ? "開啟中" : "舊版"}</span>
            </button>
          ) : null}
        </div>
      </div>

      <BridgeStatus error={error || legacy.error} message={message || legacy.message} />
      {batchJob && isoView !== "autopilot" ? (
        <div className={`batch-progress ${batchJob.state}`}>
          <div>
            <strong>{batchJob.state}</strong>
            <span>{batchJob.progress.done} / {batchJob.progress.total} pages</span>
          </div>
          <div className="batch-progress-bar">
            <span style={{ width: `${batchJob.progress.percent}%` }} />
          </div>
        </div>
      ) : null}

      {isoView === "autopilot" ? (
        <AutopilotView
          blockedCount={blockedCount}
          copyFailureForEngineer={copyFailureForEngineer}
          debugBundleBusy={debugBundleBusy}
          echoLines={echoLines}
          elapsedSec={elapsedSec}
          exportFailureBundle={exportFailureBundle}
          failureCopied={failureCopied}
          isoFailure={isoFailure}
          issueRows={issueRows}
          oneClickApplying={oneClickApplying}
          oneClickBusy={oneClickBusy}
          oneClickButton={oneClickButton}
          oneClickRunning={oneClickRunning}
          oneClickStage={oneClickStage}
          openFailureWorkbench={openFailureWorkbench}
          openWorkbenchRow={(rowId) => {
            setSelectedRowId(rowId);
            setIsoView("workbench");
          }}
          pipelineStages={pipelineStages}
          readyCount={readyCount}
          runOneClick={runOneClick}
          selectedRowId={selectedRow?.id}
          terminalRef={terminalRef}
          warnCount={warnCount}
        />
      ) : isoView === "engineer" ? (
        <EngineerView
          activeProfileFolderReady={Boolean(activeProfileFolder())}
          applyBusy={applyBusy}
          batchBusy={batchBusy}
          batchJob={batchJob}
          batchRunning={batchRunning}
          busy={busy}
          cancelBatchDetect={cancelBatchDetect}
          chooseCombinePdf={chooseCombinePdf}
          chooseIsoList={chooseIsoList}
          choosePageFolder={choosePageFolder}
          chooseWorkFolder={chooseWorkFolder}
          columnSummary={columnSummary}
          combinePdf={combinePdf}
          confidenceThreshold={confidenceThreshold}
          detectSerials={detectSerials}
          exportBusy={exportBusy}
          exportRenameCsv={exportRenameCsv}
          generatePlan={generatePlan}
          hasDraftProfile={Boolean(hasDraftProfile)}
          hasPublishedProfile={Boolean(hasPublishedProfile)}
          headers={headers}
          issueCount={issueRows.length}
          isoList={isoList}
          legacy={legacy}
          lineCol={lineCol}
          openRunLogDrawer={openRunLogDrawer}
          pageFolder={pageFolder}
          pattern={pattern}
          plan={plan}
          profileBusy={profileBusy}
          profileHistoryCount={profileHistoryCount}
          profileLabel={profileLabel}
          publishProfileToOneClick={publishProfileToOneClick}
          revertPublishedProfile={revertPublishedProfile}
          rowCount={rows.length}
          runLogBusy={runLogBusy}
          selectedCount={selectedCount}
          serialCol={serialCol}
          setConfidenceThreshold={setConfidenceThreshold}
          setDetectSerials={setDetectSerials}
          setLineCol={setLineCol}
          setPattern={setPattern}
          setSerialCol={setSerialCol}
          setSheetName={setSheetName}
          sheetName={sheetName}
          sheetOptions={sheetOptions}
          startBatchDetect={startBatchDetect}
          visualPanel={visualPanel}
          workFolder={workFolder}
        />
      ) : (
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
            <Gate label="Profile" state={hasPublishedProfile ? "ready" : activeProfileFolder() ? "idle" : "warn"} />
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
            {(plan?.steps ?? ISO_STEPS).map((step, index) => (
              <div className={`iso-step ${step.state}`} key={`${step.label}-${index}`}>
                <div className="step-index">{String(index + 1).padStart(2, "0")}</div>
                <div>
                  <strong>{step.label}</strong>
                  <span>{step.meta}</span>
                </div>
                {index < (plan?.steps.length ?? ISO_STEPS.length) - 1 ? <ChevronRight size={16} /> : null}
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
            {(issueRows.length ? issueRows.map((row) => ({ code: row.status.toUpperCase(), tone: row.status, title: row.source_name, detail: row.note || row.new_name || row.source_path })) : plan?.issues.length ? plan.issues : ISO_ISSUES).map((issue, index) => (
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
      )}
      {dryRunOpen && plan ? (
        <IsoDryRunDialog
          applyBusy={applyBusy}
          exportBusy={exportBusy}
          onApply={applySelectedRows}
          onClose={() => setDryRunOpen(false)}
          onExport={exportRenameCsv}
          rows={plan.rows.filter((row) => row.selected && row.status === "ready")}
          summary={plan.summary}
        />
      ) : null}
      {runLogOpen ? (
        <RunLogDrawer
          busy={runLogBusy}
          detail={runLogDetail}
          onClose={() => setRunLogOpen(false)}
          onRefresh={() => void refreshRunLogs()}
          onReplay={(runId) => void replayRunLog(runId)}
          onSelect={(runId) => void loadRunLogDetail(runId)}
          runs={runLogs}
        />
      ) : null}
      <IsoEventLog issues={workflowEvents} />
      {resultOpen && plan ? (
        <IsoResultDialog
          onClose={() => setResultOpen(false)}
          onDryRun={openDryRun}
          onExport={exportRenameCsv}
          plan={plan}
        />
      ) : null}
    </section>
  );
}
