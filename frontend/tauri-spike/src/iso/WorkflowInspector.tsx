import {
  Braces,
  ChevronDown,
  CircleAlert,
  CircleCheck,
  FileSearch,
  GitBranch,
  Lock,
  RefreshCcw,
  Route,
  ShieldCheck,
} from "lucide-react";
import { isTauri } from "@tauri-apps/api/core";
import type { CSSProperties, ReactNode, SyntheticEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import {
  cancelIsoWorkflowJob,
  applyIsoPlan,
  exportIsoPlanCsv,
  listIsoParityReports,
  listIsoWorkflowNodes,
  listIsoWorkflowRuns,
  loadIsoOneClickEngine,
  loadIsoPreview,
  loadIsoSwitchoverGate,
  loadIsoWorkflowJobStatus,
  loadIsoWorkflowPlanFromRun,
  loadIsoNodeWorkflow,
  readIsoWorkflowArtifact,
  readIsoWorkflowRunLog,
  runIsoWorkflowFromSafe,
  runIsoWorkflowNodeSafe,
  runIsoNodeWorkflowSafe,
  setIsoOneClickEngine,
  setIsoShadowFlag,
  type IsoNodeWorkflowArtifactPayload,
  type IsoNodeWorkflowEdge,
  type IsoNodeWorkflowInstance,
  type IsoNodeWorkflowJobPayload,
  type IsoNodeWorkflowListPayload,
  type IsoNodeWorkflowNodeRunLog,
  type IsoOneClickEnginePayload,
  type IsoNodeWorkflowRunLog,
  type IsoNodeWorkflowRunSummary,
  type IsoNodeWorkflowSpec,
  type IsoNodeWorkflowValidationPayload,
  type IsoParityReportSummary,
  type IsoPlanRow,
  type IsoPreviewPayload,
  type IsoSwitchoverGateVerdict,
  type IsoWorkflowRequest,
  type IsoWorkflowPlan,
} from "../isoWorkflow";
import { compactPath, DEFAULT_DRAWING_REGION, DEFAULT_SERIAL_REGION } from "./helpers";
import { WorkflowCanvas } from "./WorkflowCanvas";
import { WorkflowRunPlanPanel } from "./components/WorkflowRunPlanPanel";
import { NodeDetailPanel } from "./workbench/NodeDetailPanel";
import { NodeWorkbench } from "./workbench/NodeWorkbench";
import { WorkflowGuideCanvas, type IsoPageTrial } from "./workbench/WorkflowGuideCanvas";
import { buildNodeCardSummaries } from "./workbench/nodeCards";

const SAFE_WORKFLOW_PATH = "launcher/plugins/iso_tools/workflow/workflows/iso_pdf_safe_poc.workflow.json";

type WorkflowInspectorProps = {
  workflowInputs?: Record<string, unknown>;
  registerSafeRun?: (runner: () => void) => void;
  workflowJob?: IsoNodeWorkflowJobPayload | null;
  setWorkflowJob?: (job: IsoNodeWorkflowJobPayload | null) => void;
  gateVerdict?: IsoSwitchoverGateVerdict | null;
  setGateVerdict?: (verdict: IsoSwitchoverGateVerdict | null) => void;
  shadowFlagEnabled?: boolean;
  setShadowFlagEnabled?: (enabled: boolean) => void;
};

export function WorkflowInspector({
  workflowInputs = {},
  registerSafeRun,
  workflowJob,
  setWorkflowJob,
  gateVerdict,
  setGateVerdict,
  shadowFlagEnabled,
  setShadowFlagEnabled,
}: WorkflowInspectorProps) {
  const [expanded, setExpanded] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [runError, setRunError] = useState("");
  const [nodeCatalog, setNodeCatalog] = useState<IsoNodeWorkflowListPayload | null>(null);
  const [graph, setGraph] = useState<IsoNodeWorkflowValidationPayload | null>(null);
  const [runs, setRuns] = useState<IsoNodeWorkflowRunSummary[]>([]);
  const [parityReports, setParityReports] = useState<IsoParityReportSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [runLog, setRunLog] = useState<IsoNodeWorkflowRunLog | null>(null);
  const [projectedPlan, setProjectedPlan] = useState<IsoWorkflowPlan | null>(null);
  const [projectionError, setProjectionError] = useState("");
  const [nodePreview, setNodePreview] = useState<IsoPreviewPayload | null>(null);
  const [nodePreviewBusy, setNodePreviewBusy] = useState(false);
  const [nodePreviewError, setNodePreviewError] = useState("");
  const [nodePreviewReloadKey, setNodePreviewReloadKey] = useState(0);
  const [pageTrials, setPageTrials] = useState<Record<string, IsoPageTrial>>({});
  const [pageTrialBusyId, setPageTrialBusyId] = useState("");
  const [overlayInputs, setOverlayInputs] = useState<Record<string, unknown>>({});
  const [dirtyNodeIds, setDirtyNodeIds] = useState<string[]>([]);
  const [workbenchActionBusy, setWorkbenchActionBusy] = useState<"" | "apply" | "export">("");
  const [workbenchActionMessage, setWorkbenchActionMessage] = useState("");
  const [safeRunConfirmOpen, setSafeRunConfirmOpen] = useState(false);
  const [safeRunBusy, setSafeRunBusy] = useState(false);
  const [cancelBusy, setCancelBusy] = useState(false);
  const [localJob, setLocalJob] = useState<IsoNodeWorkflowJobPayload | null>(null);
  const [localGateVerdict, setLocalGateVerdict] = useState<IsoSwitchoverGateVerdict | null>(null);
  const [localShadowFlagEnabled, setLocalShadowFlagEnabled] = useState(false);
  const [projectionRunId, setProjectionRunId] = useState("");
  const [graphCopied, setGraphCopied] = useState(false);
  const [selectedCanvasNodeId, setSelectedCanvasNodeId] = useState("");
  const [selectedGuideRowId, setSelectedGuideRowId] = useState("");
  const [artifactPreview, setArtifactPreview] = useState<Record<string, ArtifactPreviewEntry>>({});
  const [shadowFlagBusy, setShadowFlagBusy] = useState(false);
  const [oneClickEngine, setOneClickEngineState] = useState<IsoOneClickEnginePayload | null>(null);
  const [engineBusy, setEngineBusy] = useState(false);
  const job = workflowJob === undefined ? localJob : workflowJob;
  const updateJob = setWorkflowJob ?? setLocalJob;
  const gate = gateVerdict === undefined ? localGateVerdict : gateVerdict;
  const updateGate = setGateVerdict ?? setLocalGateVerdict;
  const shadowFlag = shadowFlagEnabled === undefined ? localShadowFlagEnabled : shadowFlagEnabled;
  const updateShadowFlag = setShadowFlagEnabled ?? setLocalShadowFlagEnabled;

  const specByType = useMemo(() => {
    const entries = (nodeCatalog?.nodes ?? []).map((spec) => [spec.node_type, spec] as const);
    return new Map(entries);
  }, [nodeCatalog]);
  const graphNodes = graph?.graph?.nodes ?? [];
  const syntheticCanvasNodes = useMemo<IsoNodeWorkflowInstance[]>(() => [
    { node_id: "pdf_source", node_type: "ui.pdf_source", display_name: "PDF 來源", enabled: true, params: {}, side_effects: [] },
    { node_id: "roi_calib", node_type: "ui.roi_calibration", display_name: "ROI 調校", enabled: true, params: {}, side_effects: [] },
  ], []);
  const canvasDetailNodes = useMemo(
    () => graph?.graph ? [...syntheticCanvasNodes, ...graphNodes] : graphNodes,
    [graph?.graph, graphNodes, syntheticCanvasNodes],
  );
  const fallbackNodeId = graph?.graph ? "pdf_source" : graph?.topology?.find((nodeId) => graphNodes.some((node) => node.node_id === nodeId)) || graphNodes[0]?.node_id || "";
  const activeCanvasNodeId = canvasDetailNodes.some((node) => node.node_id === selectedCanvasNodeId) ? selectedCanvasNodeId : fallbackNodeId;
  const selectedCanvasNode = canvasDetailNodes.find((node) => node.node_id === activeCanvasNodeId) ?? null;
  const selectedCanvasSpec = selectedCanvasNode ? specByType.get(selectedCanvasNode.node_type) : undefined;
  const selectedCanvasLog = selectedCanvasNode ? runLog?.nodes?.[selectedCanvasNode.node_id] : undefined;
  const selectedRun = runs.find((run) => run.run_id === selectedRunId) ?? runs[0] ?? null;
  const summary = job?.result?.side_effect_summary ?? selectedRun?.side_effect_summary ?? runLog?.side_effect_summary;
  const blockedCount = summary?.blocked?.length ?? 0;
  const executedCount = summary?.executed?.length ?? 0;
  const baseInputs = useMemo(() => compactWorkflowInputs(workflowInputs), [workflowInputs]);
  const baseInputsKey = useMemo(() => stableJson(baseInputs), [baseInputs]);
  const safeInputs = useMemo(() => compactWorkflowInputs({ ...baseInputs, ...overlayInputs }), [baseInputs, overlayInputs]);
  const selectedPreviewRow = useMemo(() => {
    const rows = projectedPlan?.rows ?? [];
    return rows.find((row) => row.id === selectedGuideRowId)
      ?? rows.find((row) => row.status === "warn" || row.status === "blocked")
      ?? rows[0]
      ?? null;
  }, [projectedPlan, selectedGuideRowId]);
  const nodeSummaries = useMemo(
    () => buildNodeCardSummaries({ dirtyNodeIds, job, plan: projectedPlan, preview: nodePreview, runLog, workflowInputs: safeInputs }),
    [dirtyNodeIds, job, projectedPlan, nodePreview, runLog, safeInputs],
  );
  const hasPdfSource = Boolean(safeInputs.work_folder || safeInputs.combine_pdf);
  const hasIsoSource = Boolean(safeInputs.iso_list || safeInputs.work_folder);
  const safeRunReady = Boolean(graph?.valid) && hasPdfSource && hasIsoSource;
  const canRunSafe = safeRunReady && !safeRunBusy && !isWorkflowJobRunning(job);
  const rerunSourceRunId = runLog?.run_id || selectedRun?.run_id || "";
  const canRerun = Boolean(rerunSourceRunId) && !safeRunBusy && !isWorkflowJobRunning(job);
  const sideEffectPreview = useMemo(() => buildSideEffectPreview(graphNodes, specByType), [graphNodes, specByType]);
  const workflowSteps = useMemo(
    () => buildWorkflowSteps(graphNodes, graph?.topology ?? [], graph?.edges ?? [], specByType, runLog, job),
    [graphNodes, graph?.topology, graph?.edges, specByType, runLog, job],
  );
  const selectedStep = workflowSteps.find((step) => step.node.node_id === activeCanvasNodeId) ?? workflowSteps[0] ?? null;
  const activeArtifactKey = selectedStep && runLog?.run_id ? artifactKey(runLog.run_id, selectedStep.node.node_id) : "";
  const activeArtifactPreview = activeArtifactKey ? artifactPreview[activeArtifactKey] : undefined;
  const terminalJob = Boolean(job && !isWorkflowJobRunning(job));
  const graphJson = useMemo(() => graph?.graph ? JSON.stringify(graph.graph, null, 2) : "", [graph]);
  const oneClickEngineLabel = oneClickEngine?.flag_exists
    ? oneClickEngine.engine === "workflow"
      ? "節點路徑（驗證中）"
      : "傳統路徑"
    : "傳統路徑（未設旗標）";

  useEffect(() => {
    setOverlayInputs({});
    setDirtyNodeIds([]);
    setSelectedGuideRowId("");
    setPageTrials({});
    setPageTrialBusyId("");
  }, [baseInputsKey]);

  useEffect(() => {
    if (!selectedGuideRowId) {
      return;
    }
    const exists = projectedPlan?.rows.some((row) => row.id === selectedGuideRowId);
    if (!exists) {
      setSelectedGuideRowId("");
    }
  }, [projectedPlan?.rows, selectedGuideRowId]);

  useEffect(() => {
    if (!selectedStep || !runLog?.run_id || !isTauri()) {
      return;
    }
    const nodeLog = selectedStep.nodeLog;
    const ports = nodeLog ? artifactPortsFromLog(nodeLog) : [];
    if (!ports.length) {
      return;
    }
    const key = artifactKey(runLog.run_id, selectedStep.node.node_id);
    const cached = artifactPreview[key];
    if (cached?.loaded || cached?.loading) {
      return;
    }
    let cancelled = false;
    setArtifactPreview((previous) => ({
      ...previous,
      [key]: { loading: true, loaded: false, payloads: {}, error: "" },
    }));
    Promise.all(
      ports.map(async (port) => {
        const payload = await readIsoWorkflowArtifact(runLog.run_id, selectedStep.node.node_id, port);
        return [port, payload] as const;
      }),
    )
      .then((entries) => {
        if (cancelled) {
          return;
        }
        setArtifactPreview((previous) => ({
          ...previous,
          [key]: {
            loading: false,
            loaded: true,
            payloads: Object.fromEntries(entries),
            error: "",
          },
        }));
      })
      .catch((caught) => {
        if (cancelled) {
          return;
        }
        setArtifactPreview((previous) => ({
          ...previous,
          [key]: {
            loading: false,
            loaded: false,
            payloads: {},
            error: caught instanceof Error ? caught.message : String(caught),
          },
        }));
      });
    return () => {
      cancelled = true;
    };
  }, [runLog?.run_id, selectedStep?.node.node_id]);

  useEffect(() => {
    const needsPreview = ["pdf_source", "split", "roi_calib"].includes(activeCanvasNodeId);
    if (!needsPreview || !selectedPreviewRow?.source_path || !isTauri()) {
      setNodePreview(null);
      setNodePreviewBusy(false);
      setNodePreviewError("");
      return;
    }
    let cancelled = false;
    const serialRegion = regionOrDefault(safeInputs.serial_region ?? projectedPlan?.source.serial_region, DEFAULT_SERIAL_REGION);
    const drawingRegion = regionOrDefault(safeInputs.drawing_region ?? projectedPlan?.source.drawing_region, DEFAULT_DRAWING_REGION);
    setNodePreviewBusy(true);
    setNodePreviewError("");
    loadIsoPreview({
      source_path: selectedPreviewRow.source_path,
      detect_serial: false,
      serial_region: serialRegion,
      drawing_region: drawingRegion,
    })
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setNodePreview(payload);
      })
      .catch((caught) => {
        if (cancelled) {
          return;
        }
        setNodePreview(null);
        setNodePreviewError(caught instanceof Error ? caught.message : String(caught));
      })
      .finally(() => {
        if (!cancelled) {
          setNodePreviewBusy(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [
    activeCanvasNodeId,
    projectedPlan?.source.drawing_region,
    projectedPlan?.source.serial_region,
    nodePreviewReloadKey,
    safeInputs.drawing_region,
    safeInputs.serial_region,
    selectedPreviewRow?.source_path,
  ]);

  useEffect(() => {
    if (!job?.workflow_job_id || !isWorkflowJobRunning(job)) {
      return;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await loadIsoWorkflowJobStatus(job.workflow_job_id);
        if (cancelled) {
          return;
        }
        updateJob(next);
        setRunError(next.error || "");
        if (!isWorkflowJobRunning(next) && next.workflow_run_id) {
          await refreshRuns(next.workflow_run_id);
          setProjectionRunId(next.workflow_run_id);
          setDirtyNodeIds([]);
        }
      } catch (caught) {
        if (!cancelled) {
          setRunError(caught instanceof Error ? caught.message : String(caught));
        }
      }
    };
    const timer = window.setInterval(() => void poll(), 800);
    void poll();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [job?.workflow_job_id, job?.state]);

  useEffect(() => {
    registerSafeRun?.(() => {
      void openAndRequestSafeRun();
    });
    return () => registerSafeRun?.(() => {});
  }, [registerSafeRun, loaded, graph, workflowInputs, safeRunReady, safeRunBusy, job?.state]);

  function handleToggle(event: SyntheticEvent<HTMLDetailsElement>) {
    setExpanded(event.currentTarget.open);
    if (event.currentTarget.open && !loaded && !loading) {
      void refresh();
    }
  }

  async function refresh(): Promise<IsoNodeWorkflowValidationPayload | null> {
    if (!isTauri()) {
      setError("請用 Tauri 桌面版讀取節點工作流。");
      return null;
    }
    setLoading(true);
    setError("");
    try {
      const [nodesPayload, graphPayload, runsPayload, parityPayload, gatePayload, enginePayload] = await Promise.all([
        listIsoWorkflowNodes(),
        loadIsoNodeWorkflow(SAFE_WORKFLOW_PATH),
        listIsoWorkflowRuns(),
        listIsoParityReports(),
        loadIsoSwitchoverGate(),
        loadIsoOneClickEngine(),
      ]);
      setNodeCatalog(nodesPayload);
      setGraph(graphPayload);
      setRuns(runsPayload.runs);
      setParityReports(parityPayload.reports);
      updateGate(gatePayload);
      updateShadowFlag(Boolean(gatePayload.shadow_flag_enabled));
      setOneClickEngineState(enginePayload);
      setLoaded(true);
      const runId = selectedRunId || runsPayload.runs[0]?.run_id || "";
      if (runId) {
        await loadRunLog(runId);
      } else {
        setRunLog(null);
        setProjectedPlan(null);
        setProjectionError("");
      }
      return graphPayload;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      return null;
    } finally {
      setLoading(false);
    }
  }

  async function refreshRuns(preferredRunId = selectedRunId) {
    const runsPayload = await listIsoWorkflowRuns();
    setRuns(runsPayload.runs);
    const runId = preferredRunId || runsPayload.runs[0]?.run_id || "";
    if (runId) {
      await loadRunLog(runId);
    } else {
      setRunLog(null);
      setProjectedPlan(null);
      setProjectionError("");
    }
  }

  async function loadRunLog(runId: string) {
    if (!runId) {
      return;
    }
    setSelectedRunId(runId);
    setProjectionError("");
    try {
      const nextRunLog = await readIsoWorkflowRunLog(runId);
      setRunLog(nextRunLog);
      try {
        setProjectedPlan(await loadIsoWorkflowPlanFromRun(runId));
      } catch (caught) {
        setProjectedPlan(null);
        setProjectionError(caught instanceof Error ? caught.message : String(caught));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setRunLog(null);
      setProjectedPlan(null);
    }
  }

  async function openAndRequestSafeRun() {
    setExpanded(true);
    const nextGraph = loaded ? graph : await refresh();
    requestSafeRun(nextGraph ?? graph);
  }

  function requestSafeRun(nextGraph: IsoNodeWorkflowValidationPayload | null = graph) {
    if (!isTauri()) {
      setRunError("請用 Tauri 桌面版執行節點工作流。");
      return;
    }
    if (safeRunBusy || isWorkflowJobRunning(job)) {
      return;
    }
    const graphValid = nextGraph?.valid === true;
    if (!graphValid || !hasPdfSource || !hasIsoSource) {
      setRunError(safeRunBlockReason(graphValid, hasPdfSource, hasIsoSource));
      return;
    }
    setRunError("");
    setSafeRunConfirmOpen(true);
  }

  function handleWorkflowInputChange(nodeId: string, field: string, value: unknown) {
    setOverlayInputs((previous) => ({ ...previous, [field]: value }));
    setDirtyNodeIds((previous) => mergeUnique(previous, dirtyNodesFrom(nodeId)));
  }

  function refreshGuidePreview(rowId: string) {
    setSelectedGuideRowId(rowId);
    setSelectedCanvasNodeId("roi_calib");
    setNodePreviewReloadKey((current) => current + 1);
  }

  async function runPageTrial(rowId: string) {
    const row = projectedPlan?.rows.find((candidate) => candidate.id === rowId);
    if (!row?.source_path) {
      setNodePreviewError("找不到目前頁面的 PDF 來源。");
      return;
    }
    if (!isTauri()) {
      setNodePreviewError("請用 Tauri 桌面版判讀單頁。");
      return;
    }
    setSelectedGuideRowId(rowId);
    setSelectedCanvasNodeId("roi_calib");
    setPageTrialBusyId(rowId);
    setNodePreviewBusy(true);
    setNodePreviewError("");
    try {
      const payload = await loadIsoPreview({
        source_path: row.source_path,
        detect_serial: true,
        serial_region: regionOrDefault(safeInputs.serial_region ?? projectedPlan?.source.serial_region, DEFAULT_SERIAL_REGION),
        drawing_region: regionOrDefault(safeInputs.drawing_region ?? projectedPlan?.source.drawing_region, DEFAULT_DRAWING_REGION),
      });
      setNodePreview(payload);
      setPageTrials((previous) => ({
        ...previous,
        [rowId]: {
          confidence: payload.vision?.confidence ?? 0,
          page: row.page,
          serial: payload.vision?.text ?? "",
          sourcePath: row.source_path,
          updatedAt: new Date().toISOString(),
        },
      }));
    } catch (caught) {
      setNodePreviewError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setNodePreviewBusy(false);
      setPageTrialBusyId("");
    }
  }

  async function rerunWorkflowNode(nodeId: string) {
    const engineNodeId = rerunEngineNodeId(nodeId);
    if (!engineNodeId || !rerunSourceRunId || isWorkflowJobRunning(job)) {
      return;
    }
    setRunError("");
    try {
      const next = await runIsoWorkflowNodeSafe({
        source_run_id: rerunSourceRunId,
        node_id: engineNodeId,
        workflow_inputs: safeInputs,
      });
      updateJob(next);
      setSelectedCanvasNodeId(engineNodeId);
    } catch (caught) {
      setRunError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function rerunWorkflowFrom(nodeId: string) {
    const engineNodeId = rerunEngineNodeId(nodeId);
    if (!engineNodeId || !rerunSourceRunId || isWorkflowJobRunning(job)) {
      return;
    }
    setRunError("");
    try {
      const next = await runIsoWorkflowFromSafe({
        source_run_id: rerunSourceRunId,
        node_id: engineNodeId,
        workflow_inputs: safeInputs,
      });
      updateJob(next);
      setSelectedCanvasNodeId(engineNodeId);
    } catch (caught) {
      setRunError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function exportWorkbenchPlan() {
    if (!projectedPlan || workbenchActionBusy) {
      return;
    }
    setWorkbenchActionBusy("export");
    setRunError("");
    setWorkbenchActionMessage("");
    try {
      const result = await exportIsoPlanCsv(workbenchPlanRequest(projectedPlan, safeInputs, projectedPlan.rows));
      setWorkbenchActionMessage(result.export_path ? `已匯出命名草稿 CSV：${result.export_path}` : result.message);
    } catch (caught) {
      setRunError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setWorkbenchActionBusy("");
    }
  }

  async function applyWorkbenchPlan() {
    if (!projectedPlan || workbenchActionBusy) {
      return;
    }
    const rows = projectedPlan.rows.filter((row) => row.selected && row.status === "ready");
    if (!rows.length) {
      setRunError("沒有可套用的 ready 列。");
      return;
    }
    if (!window.confirm(`將套用更名 ${rows.length} 筆。此動作會實際改名 PDF，並寫入既有更名記錄。是否繼續？`)) {
      return;
    }
    setWorkbenchActionBusy("apply");
    setRunError("");
    setWorkbenchActionMessage("");
    try {
      const result = await applyIsoPlan(workbenchPlanRequest(projectedPlan, safeInputs, rows));
      setWorkbenchActionMessage(result.message);
      await refreshRuns(rerunSourceRunId);
    } catch (caught) {
      setRunError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setWorkbenchActionBusy("");
    }
  }

  async function confirmSafeRun() {
    if (safeRunBusy || isWorkflowJobRunning(job)) {
      return;
    }
    if (!canRunSafe) {
      setRunError(safeRunBlockReason(graph?.valid === true, hasPdfSource, hasIsoSource));
      return;
    }
    setSafeRunBusy(true);
    setRunError("");
    try {
      const next = await runIsoNodeWorkflowSafe({
        workflow_path: SAFE_WORKFLOW_PATH,
        workflow_inputs: safeInputs,
      });
      updateJob(next);
      setSafeRunConfirmOpen(false);
      if (!isWorkflowJobRunning(next) && next.workflow_run_id) {
        await refreshRuns(next.workflow_run_id);
        setProjectionRunId(next.workflow_run_id);
        setDirtyNodeIds([]);
      }
    } catch (caught) {
      setRunError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSafeRunBusy(false);
    }
  }

  async function cancelSafeRun() {
    const jobId = job?.workflow_job_id || job?.job_id;
    if (!jobId || !isWorkflowJobRunning(job)) {
      return;
    }
    setCancelBusy(true);
    setRunError("");
    try {
      updateJob(await cancelIsoWorkflowJob(jobId));
    } catch (caught) {
      setRunError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setCancelBusy(false);
    }
  }

  async function copyGraphJson() {
    if (!graphJson) {
      return;
    }
    try {
      await navigator.clipboard.writeText(graphJson);
      setGraphCopied(true);
      window.setTimeout(() => setGraphCopied(false), 1500);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function toggleShadowFlag() {
    if (shadowFlagBusy) {
      return;
    }
    setShadowFlagBusy(true);
    setError("");
    try {
      const next = await setIsoShadowFlag(!shadowFlag);
      updateShadowFlag(next.enabled);
      const gatePayload = await loadIsoSwitchoverGate();
      updateGate(gatePayload);
      updateShadowFlag(Boolean(gatePayload.shadow_flag_enabled));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setShadowFlagBusy(false);
    }
  }

  async function switchOneClickEngine(engine: "legacy" | "workflow") {
    if (engineBusy) {
      return;
    }
    setEngineBusy(true);
    setError("");
    try {
      const next = await setIsoOneClickEngine(engine);
      setOneClickEngineState(next);
      const gatePayload = await loadIsoSwitchoverGate();
      updateGate(gatePayload);
      updateShadowFlag(Boolean(gatePayload.shadow_flag_enabled));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setEngineBusy(false);
    }
  }

  function requestEnableOneClickEngine() {
    const headline = gate?.headline || "尚未讀取 gate";
    if (!window.confirm(`啟用後，一鍵命名會改走節點路徑（仍保留傳統 fallback）。\n\n目前 gate：${headline}`)) {
      return;
    }
    void switchOneClickEngine("workflow");
  }

  return (
    <details style={styles.shell} open={expanded} onToggle={handleToggle}>
      <summary style={styles.summary}>
        <span style={styles.title}>
          <GitBranch size={16} />
          <strong>進階：節點工作流</strong>
          <em style={styles.badge}>唯讀</em>
        </span>
        <span style={styles.summaryMeta}>
          <span>{nodeCatalog ? `${nodeCatalog.node_count} 節點` : "未載入"}</span>
          <span>{graph ? (graph.valid ? "圖有效" : `${graph.issues.length} 問題`) : "safe POC"}</span>
          <span>{runs.length ? `${runs.length} 紀錄` : "無紀錄"}</span>
        </span>
        <ChevronDown size={16} style={styles.chevron} />
      </summary>

      <div style={styles.body}>
        <div style={styles.toolbar}>
          <div style={styles.toolbarText}>
            <span>ISO PDF 安全流程</span>
            <small>{compactPath(SAFE_WORKFLOW_PATH)}</small>
          </div>
          <div style={styles.toolbarActions}>
            <button className="action-button" type="button" onClick={() => void refresh()} disabled={loading}>
              <RefreshCcw size={15} />
              <span>{loading ? "讀取中" : "重新整理"}</span>
            </button>
            <button className="action-button" type="button" onClick={() => requestSafeRun()} disabled={!canRunSafe}>
              <ShieldCheck size={15} />
              <span>{safeRunBusy || isWorkflowJobRunning(job) ? "執行中" : "執行安全模式"}</span>
            </button>
            <button className="action-button" type="button" onClick={() => void cancelSafeRun()} disabled={!isWorkflowJobRunning(job) || cancelBusy}>
              <CircleAlert size={15} />
              <span>{cancelBusy ? "取消中" : "取消"}</span>
            </button>
          </div>
        </div>

        {error ? (
          <div style={styles.alert}>
            <CircleAlert size={16} />
            <span>{error}</span>
          </div>
        ) : null}
        {runError ? (
          <div style={styles.alert}>
            <CircleAlert size={16} />
            <span>{runError}</span>
          </div>
        ) : null}
        {workbenchActionMessage ? (
          <div style={styles.notice}>
            <span>{workbenchActionMessage}</span>
          </div>
        ) : null}
        {!safeRunReady ? (
          <div style={styles.notice}>
            <span>{safeRunBlockReason(graph?.valid === true, hasPdfSource, hasIsoSource)}</span>
          </div>
        ) : null}

        {job ? (
          <div style={styles.jobPanel}>
            <div style={styles.jobHead}>
              <div>
                <strong>{workflowJobStateLabel(job.state)}</strong>
                <small>{job.workflow_run_id || job.workflow_job_id}</small>
              </div>
              <span>{job.progress?.percent ?? 0}%</span>
            </div>
            <div style={styles.progressTrack}>
              <span style={{ ...styles.progressFill, width: `${job.progress?.percent ?? 0}%` }} />
            </div>
            <div style={styles.jobMeta}>
              <span>節點 {job.progress?.done ?? 0} / {job.progress?.total ?? 0}</span>
              <span>目前 {job.progress?.current_node || (terminalJob ? "完成" : "等待")}</span>
              {job.result?.status ? <span>結果 {statusLabel(job.result.status)}</span> : null}
            </div>
          </div>
        ) : null}

        <NodeWorkbench
          header={(
            <div style={styles.metrics}>
              <Metric icon={<Braces size={16} />} label="型錄" value={nodeCatalog ? `${nodeCatalog.node_count}` : "-"} />
              <Metric
                icon={graph?.valid ? <CircleCheck size={16} /> : <CircleAlert size={16} />}
                label="驗證"
                value={graph ? (graph.valid ? "通過" : `${graph.issues.length}`) : "-"}
                tone={graph?.valid === false ? "warn" : "ready"}
              />
              <Metric icon={<Route size={16} />} label="拓撲" value={graph?.topology?.length ? `${graph.topology.length}` : "-"} />
              <Metric icon={<ShieldCheck size={16} />} label="副作用" value={`${executedCount} / ${blockedCount}`} tone={blockedCount ? "warn" : "ready"} />
            </div>
          )}
          canvas={(
            <WorkflowGuideCanvas
              dirtyNodeIds={dirtyNodeIds}
              job={job}
              onRefreshPreview={refreshGuidePreview}
              onRunFrom={(nodeId) => void rerunWorkflowFrom(nodeId)}
              onRunNode={(nodeId) => void rerunWorkflowNode(nodeId)}
              onRunPageTrial={(rowId) => void runPageTrial(rowId)}
              onSelectNode={setSelectedCanvasNodeId}
              onSelectRow={setSelectedGuideRowId}
              onWorkflowInputChange={handleWorkflowInputChange}
              pageTrialBusyId={pageTrialBusyId}
              pageTrials={pageTrials}
              plan={projectedPlan}
              preview={nodePreview}
              previewBusy={nodePreviewBusy}
              previewError={nodePreviewError || projectionError}
              rerunEnabled={canRerun}
              runLog={runLog}
              selectedNodeId={activeCanvasNodeId}
              selectedRowId={selectedGuideRowId}
              workflowInputs={safeInputs}
            />
          )}
          detail={(
            <NodeDetailPanel
              dirtyNodeIds={dirtyNodeIds}
              node={selectedCanvasNode}
              nodeLog={selectedCanvasLog}
              onRunFrom={(nodeId) => void rerunWorkflowFrom(nodeId)}
              onRunNode={(nodeId) => void rerunWorkflowNode(nodeId)}
              onSelectNode={setSelectedCanvasNodeId}
              onWorkflowInputChange={handleWorkflowInputChange}
              onApplyPlan={() => void applyWorkbenchPlan()}
              onExportPlan={() => void exportWorkbenchPlan()}
              plan={projectedPlan}
              preview={nodePreview}
              previewBusy={nodePreviewBusy}
              previewError={nodePreviewError || projectionError}
              rerunEnabled={canRerun}
              summary={selectedCanvasNode ? nodeSummaries[selectedCanvasNode.node_id] : undefined}
              workbenchActionBusy={workbenchActionBusy}
              workflowInputs={safeInputs}
            />
          )}
          drawerMeta={`${workflowSteps.length || graphNodes.length} 節點 · ${runs.length} 紀錄`}
          drawer={(
            <div style={styles.grid}>
          <section style={styles.sectionFlowTree}>
            <SectionHead icon={<Route size={16} />} title="流程樹" meta={selectedRun ? `${statusLabel(selectedRun.status)} · ${compactPath(selectedRun.run_id)}` : "等待紀錄"} />
            <div style={styles.flowTreeLayout}>
              <div style={styles.flowStepRail}>
                {workflowSteps.map((step) => (
                  <button
                    style={{
                      ...styles.flowStep,
                      borderColor: step.node.node_id === activeCanvasNodeId ? "rgba(47,245,200,0.78)" : step.borderColor,
                      opacity: step.disabled ? 0.56 : 1,
                    }}
                    key={step.node.node_id}
                    type="button"
                    onClick={() => setSelectedCanvasNodeId(step.node.node_id)}
                  >
                    <span style={{ ...styles.flowStepIndex, borderColor: step.borderColor, color: step.borderColor }}>
                      {step.index + 1}
                    </span>
                    <span style={styles.flowStepText}>
                      <strong>{step.displayName}</strong>
                      <code style={styles.code}>{step.node.node_type}</code>
                    </span>
                    <span style={{ ...styles.flowStepStatus, color: step.statusColor }}>{step.statusLabel}</span>
                  </button>
                ))}
                {loaded && !workflowSteps.length ? <EmptyLine text="尚無流程節點。" /> : null}
              </div>

              <div style={styles.flowStepDetail}>
                {selectedStep ? (
                  <>
                    <div style={styles.stepDetailHead}>
                      <span style={{ ...styles.flowStepIndex, borderColor: selectedStep.borderColor, color: selectedStep.borderColor }}>
                        {selectedStep.index + 1}
                      </span>
                      <div style={styles.stepDetailTitle}>
                        <strong>{selectedStep.displayName}</strong>
                        <code style={styles.code}>{selectedStep.node.node_id} · {selectedStep.node.node_type}</code>
                      </div>
                      <span style={{ ...styles.stepStatePill, color: selectedStep.statusColor, borderColor: selectedStep.statusColor }}>
                        {selectedStep.statusLabel}
                      </span>
                    </div>

                    <div style={styles.stepMetricGrid}>
                      <Metric icon={<Braces size={16} />} label="輸入" value={`${selectedStep.inputCount}`} />
                      <Metric icon={<Route size={16} />} label="輸出" value={`${selectedStep.outputCount}`} />
                      <Metric icon={<ShieldCheck size={16} />} label="副作用" value={selectedStep.effectLabel} tone={selectedStep.guarded ? "warn" : "ready"} />
                      <Metric icon={<FileSearch size={16} />} label="耗時" value={selectedStep.nodeLog ? `${selectedStep.nodeLog.duration_ms} ms` : "-"} />
                    </div>

                    <div style={styles.evidenceGrid}>
                      <EvidenceCard title="輸入" rows={stepInputRows(selectedStep)} />
                      <EvidenceCard title="輸出" rows={stepOutputRows(selectedStep)} />
                      <EvidenceCard title="收集資料" rows={stepArtifactRows(selectedStep, activeArtifactPreview)} />
                      <EvidenceCard title="副作用 / 紀錄" rows={stepSideEffectRows(selectedStep)} />
                    </div>

                    <StepArtifactPreview step={selectedStep} preview={activeArtifactPreview} />
                  </>
                ) : (
                  <EmptyLine text="選取一個節點後顯示步驟資料。" />
                )}
              </div>
            </div>
          </section>

          <section style={styles.section}>
            <SectionHead icon={<Braces size={16} />} title="節點型錄" meta={nodeCatalog ? `${nodeCatalog.node_count} 類型` : "等待"} />
            <div style={styles.scrollList}>
              {(nodeCatalog?.nodes ?? []).map((spec) => (
                <article
                  style={{ ...styles.nodeCard, borderLeftColor: nodeTone(spec.side_effects, spec.guarded) }}
                  key={spec.node_type}
                >
                  <div style={styles.nodeTitle}>
                    <strong>{spec.display_name}</strong>
                    <code style={styles.code}>{spec.node_type}</code>
                  </div>
                  <div style={styles.chipRow}>
                    <span style={styles.chip}>{spec.inputs.length} 入</span>
                    <span style={styles.chip}>{spec.outputs.length} 出</span>
                    {effectChips(spec.side_effects, spec.guarded)}
                  </div>
                </article>
              ))}
              {loaded && !nodeCatalog?.nodes.length ? <EmptyLine text="沒有節點型錄資料。" /> : null}
            </div>
          </section>

          <section style={styles.sectionWide}>
            <SectionHead icon={<Route size={16} />} title="工程 DAG" meta={graph?.workflow_id || graph?.graph?.workflow_id || "等待"} />
            <WorkflowCanvas
              payload={graph}
              runLog={runLog}
              nodeSummaries={nodeSummaries}
              selectedNodeId={activeCanvasNodeId}
              onSelectNode={setSelectedCanvasNodeId}
              onRunFrom={(nodeId) => void rerunWorkflowFrom(nodeId)}
              onRunNode={(nodeId) => void rerunWorkflowNode(nodeId)}
              rerunEnabled={canRerun}
            />
            {selectedCanvasNode ? (
              <div style={styles.canvasDetail}>
                <div style={styles.canvasDetailHead}>
                  <strong>{selectedCanvasNode.display_name || selectedCanvasSpec?.display_name || selectedCanvasNode.node_id}</strong>
                  <code style={styles.code}>{selectedCanvasNode.node_type}</code>
                  <span>{selectedCanvasLog?.status ? statusLabel(selectedCanvasLog.status) : selectedCanvasNode.enabled === false ? "停用" : "尚無紀錄"}</span>
                </div>
                <div style={styles.canvasDetailGrid}>
                  <div>
                    <small>參數</small>
                    <pre style={styles.compactPre}>{JSON.stringify(selectedCanvasNode.params ?? {}, null, 2)}</pre>
                  </div>
                  <div>
                    <small>副作用</small>
                    <div style={styles.previewList}>
                      {(selectedCanvasLog?.side_effects ?? []).length ? (selectedCanvasLog?.side_effects ?? []).map((record) => (
                        <span style={styles.previewRow} key={`${record.kind}-${record.decision}`}>
                          <em>{sideEffectLabel(record.kind)}</em>
                          <code style={styles.code}>{record.decision}</code>
                        </span>
                      )) : (
                        <span style={styles.previewRow}>
                          <em>宣告</em>
                          <code style={styles.code}>{(selectedCanvasNode.side_effects?.length ? selectedCanvasNode.side_effects : selectedCanvasSpec?.side_effects ?? []).map(sideEffectLabel).join(" / ") || "純讀"}</code>
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ) : null}
            <div style={styles.topology}>
              {(graph?.topology ?? []).map((nodeId) => (
                <span style={styles.topologyStep} key={nodeId}>{nodeId}</span>
              ))}
              {loaded && !graph?.topology.length ? <EmptyLine text="尚無拓撲資料。" /> : null}
            </div>
            <div style={styles.graphNodes}>
              {graphNodes.map((node) => {
                const spec = specByType.get(node.node_type);
                const effects = node.side_effects?.length ? node.side_effects : spec?.side_effects ?? [];
                const guarded = Boolean(spec?.guarded || node.requires_confirm || effects.some(isGuardedEffect));
                const disabled = node.enabled === false;
                const jobNode = job?.nodes?.[node.node_id] ?? job?.result?.nodes?.[node.node_id];
                const nodeStatus = typeof jobNode?.status === "string" ? jobNode.status : "";
                return (
                  <div
                    style={{ ...styles.graphNode, opacity: disabled ? 0.55 : 1, borderLeftColor: guarded ? "#ffd166" : "#2ff5c8" }}
                    key={node.node_id}
                  >
                    <span>{guarded ? <Lock size={13} /> : <CircleCheck size={13} />}</span>
                    <strong>{node.display_name || spec?.display_name || node.node_id}</strong>
                    <code style={styles.code}>{node.node_id}</code>
                    <em>{nodeStatus ? statusLabel(nodeStatus) : disabled ? "停用" : statusTextForNode(node.node_type, effects)}</em>
                  </div>
                );
              })}
            </div>
            {graph?.issues.length ? (
              <div style={styles.issueList}>
                {graph.issues.map((issue) => (
                  <span key={`${issue.code}-${issue.node_id}-${issue.edge}`}>{issue.code} · {issue.node_id || issue.edge || issue.message}</span>
                ))}
              </div>
            ) : null}
            {graphJson ? (
              <details style={styles.jsonDetails}>
                <summary style={styles.jsonSummary}>
                  <span>Graph JSON 原文</span>
                  <button className="action-button" type="button" onClick={(event) => { event.preventDefault(); void copyGraphJson(); }}>
                    <Braces size={14} />
                    <span>{graphCopied ? "已複製" : "複製"}</span>
                  </button>
                </summary>
                <pre style={styles.jsonPre}>{graphJson}</pre>
              </details>
            ) : null}
          </section>

          <section style={styles.sectionFull}>
            <SectionHead icon={<FileSearch size={16} />} title="執行紀錄" meta={runs.length ? `${runs.length} 筆` : "空"} />
            <div style={styles.runLayout}>
              <div style={styles.runList}>
                {runs.map((run) => (
                  <button
                    style={{ ...styles.runItem, borderColor: run.run_id === selectedRunId ? "rgba(47,245,200,0.55)" : "rgba(255,255,255,0.08)" }}
                    key={run.run_id}
                    type="button"
                    onClick={() => void loadRunLog(run.run_id)}
                    title={run.run_id}
                  >
                    <strong>{statusLabel(run.status)}</strong>
                    <span>{run.workflow_id || "workflow"}</span>
                    <em>{compactPath(run.run_id)}</em>
                  </button>
                ))}
                {loaded && !runs.length ? <EmptyLine text="尚無節點工作流紀錄。" /> : null}
              </div>
              <div style={styles.runDetail}>
                {selectedRun ? (
                  <>
                    <div style={styles.runDetailHead}>
                      <strong>{statusLabel(selectedRun.status)}</strong>
                      <span>{modeLabel(selectedRun.mode)}</span>
                      <em>{compactPath(selectedRun.run_dir)}</em>
                    </div>
                    <div style={styles.nodeStatusList}>
                      {Object.entries(runLog?.nodes ?? {}).map(([nodeId, node]) => (
                        <div style={styles.nodeStatus} key={nodeId}>
                          <span>{nodeId}</span>
                          <strong>{statusLabel(node.status)}</strong>
                          <em>{node.duration_ms} ms</em>
                        </div>
                      ))}
                      {runLog && !Object.keys(runLog.nodes).length ? <EmptyLine text="此紀錄沒有節點狀態。" /> : null}
                    </div>
                    <button className="action-button" type="button" onClick={() => setProjectionRunId(selectedRun.run_id)}>
                      <FileSearch size={14} />
                      <span>以投影檢視</span>
                    </button>
                  </>
                ) : (
                  <EmptyLine text="沒有可讀取的紀錄。" />
                )}
              </div>
            </div>
            {projectionRunId ? (
              <WorkflowRunPlanPanel fixedRunId={projectionRunId} />
            ) : null}
          </section>

          <section style={styles.sectionFull}>
            <SectionHead icon={<ShieldCheck size={16} />} title="換軌守門" meta={gate?.headline || (parityReports.length ? `${parityReports.length} 筆 parity` : "等待證據")} />
            <div style={styles.gateNote}>
              <span>{gate?.headline || "尚未讀取換軌 gate。"}</span>
              <code style={styles.code}>python -m launcher.plugins.iso_tools.workflow.cli gate --json</code>
              <div style={styles.engineSwitch}>
                <span>一鍵引擎：<strong>{oneClickEngineLabel}</strong></span>
                <button className="action-button" type="button" onClick={requestEnableOneClickEngine} disabled={!isTauri() || engineBusy || oneClickEngine?.engine === "workflow"}>
                  <GitBranch size={14} />
                  <span>{engineBusy ? "切換中" : "啟用節點路徑"}</span>
                </button>
                <button className="action-button" type="button" onClick={() => void switchOneClickEngine("legacy")} disabled={!isTauri() || engineBusy || Boolean(oneClickEngine?.flag_exists && oneClickEngine.engine === "legacy")}>
                  <Route size={14} />
                  <span>切回傳統</span>
                </button>
              </div>
              <button className="action-button" type="button" onClick={() => void toggleShadowFlag()} disabled={!isTauri() || shadowFlagBusy}>
                <ShieldCheck size={14} />
                <span>{!isTauri() ? "桌面版啟用" : shadowFlagBusy ? "更新中" : shadowFlag ? "關閉影子驗證" : "開啟影子驗證"}</span>
              </button>
            </div>
            {gate?.conditions?.length ? (
              <div style={styles.gateChecklist}>
                {gate.conditions.map((condition) => (
                  <div style={{ ...styles.gateCondition, borderColor: condition.met === true ? "rgba(47,245,200,0.32)" : condition.met === false ? "rgba(255,107,107,0.42)" : "rgba(255,209,102,0.32)" }} key={condition.id}>
                    <strong>{gateConditionMark(condition.met)} {condition.title}</strong>
                    <span>{condition.detail}</span>
                  </div>
                ))}
              </div>
            ) : null}
            <div style={styles.parityList}>
              {parityReports.map((report) => (
                <div style={{ ...styles.parityItem, borderColor: report.equal ? "rgba(47,245,200,0.32)" : "rgba(255,107,107,0.48)" }} key={report.report_path}>
                  <strong>{report.equal ? "equal" : "violation"}</strong>
                  <span>{report.created_at}</span>
                  <em>{report.violation_count} violation · {report.acceptable_diff_count} accepted</em>
                  <span style={styles.reportChips}>
                    <small style={styles.reportChip}>{report.trigger || "cli"}</small>
                    <small style={{ ...styles.reportChip, color: report.sample_kind === "real" ? "#7fd7ff" : "rgba(220,235,228,0.58)" }}>{report.sample_kind || "unknown"}</small>
                    {report.timing?.workflow_ms != null ? <small style={styles.reportChip}>workflow {report.timing.workflow_ms} ms</small> : null}
                  </span>
                  <code style={styles.code}>{compactPath(report.report_path)}</code>
                </div>
              ))}
              {loaded && !parityReports.length ? <EmptyLine text="尚無 parity 報告。請用 CLI 產生證據，不在 UI 直接觸發比對。" /> : null}
            </div>
          </section>
            </div>
          )}
        />
        {safeRunConfirmOpen ? (
          <div style={styles.modalBackdrop}>
            <div style={styles.modal}>
              <div style={styles.modalHead}>
                <div>
                  <strong>確認安全執行</strong>
                  <small>此介面不具備 guarded 授權能力；需要授權的動作會被後端擋下。</small>
                </div>
                <button className="action-button" type="button" onClick={() => setSafeRunConfirmOpen(false)} disabled={safeRunBusy}>
                  <span>關閉</span>
                </button>
              </div>
              <div style={styles.modalGrid}>
                <div style={styles.modalSection}>
                  <strong>輸入資料</strong>
                  <div style={styles.previewList}>
                    {inputPreviewRows(safeInputs).map(([key, value]) => (
                      <span style={styles.previewRow} key={key}>
                        <em>{inputLabel(key)}</em>
                        <code style={styles.code}>{value}</code>
                      </span>
                    ))}
                  </div>
                </div>
                <div style={styles.modalSection}>
                  <strong>副作用預告</strong>
                  <div style={styles.previewList}>
                    {sideEffectPreview.length ? sideEffectPreview.map((item) => (
                      <span style={styles.previewRow} key={`${item.nodeId}-${item.effect}`}>
                        <em>{item.nodeLabel}</em>
                        <code style={{ ...styles.code, color: item.guarded ? "#ffd166" : item.enabled ? "#7fd7ff" : "rgba(220,235,228,0.48)" }}>
                          {sideEffectLabel(item.effect)} · {item.enabled ? item.guarded ? "將被阻擋" : "自動允許" : "停用"}
                        </code>
                      </span>
                    )) : <EmptyLine text="此圖沒有宣告副作用。" />}
                  </div>
                </div>
              </div>
              <div style={styles.modalActions}>
                <button className="action-button" type="button" onClick={() => setSafeRunConfirmOpen(false)} disabled={safeRunBusy}>
                  <span>取消</span>
                </button>
                <button className="action-button" type="button" onClick={() => void confirmSafeRun()} disabled={!canRunSafe}>
                  <ShieldCheck size={15} />
                  <span>{safeRunBusy ? "送出中" : "確認執行"}</span>
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </details>
  );
}

type ArtifactPreviewEntry = {
  error: string;
  loaded: boolean;
  loading: boolean;
  payloads: Record<string, IsoNodeWorkflowArtifactPayload>;
};

type FieldRow = {
  label: string;
  value: string;
  tone?: "idle" | "ready" | "warn";
};

type WorkflowStep = {
  borderColor: string;
  disabled: boolean;
  displayName: string;
  effectLabel: string;
  effects: string[];
  guarded: boolean;
  index: number;
  inputCount: number;
  node: IsoNodeWorkflowInstance;
  nodeLog?: IsoNodeWorkflowNodeRunLog;
  outputCount: number;
  spec?: IsoNodeWorkflowSpec;
  statusColor: string;
  statusLabel: string;
};

type SideEffectPreviewItem = {
  effect: string;
  enabled: boolean;
  guarded: boolean;
  nodeId: string;
  nodeLabel: string;
};

function buildWorkflowSteps(
  nodes: IsoNodeWorkflowInstance[],
  topology: string[],
  edges: IsoNodeWorkflowEdge[],
  specByType: Map<string, IsoNodeWorkflowSpec>,
  runLog: IsoNodeWorkflowRunLog | null,
  job: IsoNodeWorkflowJobPayload | null,
): WorkflowStep[] {
  const nodeById = new Map(nodes.map((node) => [node.node_id, node] as const));
  const orderedIds = [
    ...topology.filter((nodeId) => nodeById.has(nodeId)),
    ...nodes.map((node) => node.node_id).filter((nodeId) => !topology.includes(nodeId)),
  ];
  return orderedIds.map((nodeId, index) => {
    const node = nodeById.get(nodeId)!;
    const spec = specByType.get(node.node_type);
    const nodeLog = runLog?.nodes?.[node.node_id];
    const jobNode = job?.nodes?.[node.node_id] ?? job?.result?.nodes?.[node.node_id];
    const effects = node.side_effects?.length ? node.side_effects : spec?.side_effects ?? [];
    const guarded = Boolean(spec?.guarded || node.requires_confirm || effects.some(isGuardedEffect));
    const disabled = node.enabled === false;
    const status = nodeLog?.status || (typeof jobNode?.status === "string" ? jobNode.status : "") || (disabled ? "skipped_disabled" : "");
    const tone = stepStatusTone(status, guarded, disabled);
    const incoming = edges.filter((edge) => edge.to_node === node.node_id).length;
    const outgoing = edges.filter((edge) => edge.from_node === node.node_id).length;
    return {
      borderColor: tone.color,
      disabled,
      displayName: node.display_name || spec?.display_name || node.node_id,
      effectLabel: effects.length ? effects.map(sideEffectLabel).join(" / ") : "純讀",
      effects,
      guarded,
      index,
      inputCount: Math.max(Object.keys(node.inputs ?? {}).length, spec?.inputs.length ?? 0, incoming),
      node,
      nodeLog,
      outputCount: Math.max(Object.keys(node.outputs ?? {}).length, spec?.outputs.length ?? 0, outgoing),
      spec,
      statusColor: tone.color,
      statusLabel: tone.label,
    };
  });
}

function artifactKey(runId: string, nodeId: string) {
  return `${runId}:${nodeId}`;
}

function artifactPortsFromLog(nodeLog: IsoNodeWorkflowNodeRunLog): string[] {
  return Object.entries(nodeLog.outputs ?? {})
    .filter(([, value]) => Boolean(value && typeof value === "object" && "artifact_ref" in value))
    .map(([port]) => port);
}

function stepStatusTone(status: string, guarded: boolean, disabled: boolean): { color: string; label: string } {
  if (disabled || status === "skipped_disabled") {
    return { color: "rgba(220,235,228,0.5)", label: "停用" };
  }
  if (status === "success") {
    return { color: "#2ff5c8", label: "成功" };
  }
  if (status === "running") {
    return { color: "#7fd7ff", label: "執行中" };
  }
  if (status === "blocked") {
    return { color: "#ffd166", label: "已阻擋" };
  }
  if (status === "failed") {
    return { color: "#ff9b9b", label: "失敗" };
  }
  if (status === "cancelled") {
    return { color: "#ff9b9b", label: "已取消" };
  }
  if (status === "not_run") {
    return { color: "rgba(220,235,228,0.52)", label: "未執行" };
  }
  if (guarded) {
    return { color: "#ffd166", label: "需授權" };
  }
  return { color: "#7fd7ff", label: "待執行" };
}

function stepInputRows(step: WorkflowStep): FieldRow[] {
  const rows = [
    ...Object.entries(step.node.inputs ?? {}).map(([key, value]) => ({
      label: inputLabel(key),
      value: formatInputPreview(value),
    })),
  ];
  if (step.nodeLog?.resolved_inputs_digest) {
    rows.push(
      ...Object.entries(step.nodeLog.resolved_inputs_digest).map(([key, value]) => ({
        label: `${inputLabel(key)} 解析值`,
        value: summarizeUnknown(value),
      })),
    );
  }
  return rows.length ? rows : [{ label: "輸入", value: "無" }];
}

function stepOutputRows(step: WorkflowStep): FieldRow[] {
  const declared = step.spec?.outputs.map((port) => port.name) ?? [];
  const refs = Object.entries(step.nodeLog?.outputs ?? {}).map(([key, value]) => ({
    label: outputLabel(key),
    value: outputRefSummary(value),
  }));
  const missing = declared
    .filter((port) => !refs.some((row) => row.label === outputLabel(port)))
    .map((port) => ({ label: outputLabel(port), value: "尚無輸出" }));
  return [...refs, ...missing].length ? [...refs, ...missing] : [{ label: "輸出", value: "無" }];
}

function stepArtifactRows(step: WorkflowStep, preview?: ArtifactPreviewEntry): FieldRow[] {
  if (!step.nodeLog) {
    return [{ label: "資料", value: "尚無執行紀錄" }];
  }
  if (preview?.loading) {
    return [{ label: "資料", value: "讀取中" }];
  }
  if (preview?.error) {
    return [{ label: "資料", value: preview.error, tone: "warn" }];
  }
  const payloads = preview?.payloads ?? {};
  const rows = Object.entries(payloads).flatMap(([port, artifact]) => summarizeArtifact(port, artifact.payload).slice(0, 4));
  return rows.length ? rows : artifactPortsFromLog(step.nodeLog).map((port) => ({ label: outputLabel(port), value: "可讀取" }));
}

function stepSideEffectRows(step: WorkflowStep): FieldRow[] {
  const records = step.nodeLog?.side_effects ?? [];
  if (records.length) {
    return records.map((record) => ({
      label: sideEffectLabel(record.kind),
      value: decisionLabel(record.decision),
      tone: record.decision === "executed" ? "ready" : "warn",
    }));
  }
  if (step.effects.length) {
    return step.effects.map((effect) => ({
      label: sideEffectLabel(effect),
      value: step.guarded ? "需授權" : "自動允許",
      tone: step.guarded ? "warn" : "ready",
    }));
  }
  return [{ label: "副作用", value: "無" }];
}

function EvidenceCard({ title, rows }: { title: string; rows: FieldRow[] }) {
  return (
    <div style={styles.evidenceCard}>
      <strong>{title}</strong>
      <div style={styles.evidenceRows}>
        {rows.map((row, index) => (
          <span style={styles.evidenceRow} key={`${row.label}-${index}`}>
            <em>{row.label}</em>
            <code style={{ ...styles.code, color: row.tone === "warn" ? "#ffd166" : row.tone === "ready" ? "#2ff5c8" : styles.code.color }}>
              {row.value}
            </code>
          </span>
        ))}
      </div>
    </div>
  );
}

function StepArtifactPreview({ step, preview }: { step: WorkflowStep; preview?: ArtifactPreviewEntry }) {
  const cards = artifactPreviewCards(step, preview);
  return (
    <div style={styles.artifactPreview}>
      <div style={styles.artifactPreviewHead}>
        <strong>資料預覽</strong>
        <span>{preview?.loading ? "讀取中" : preview?.error ? "讀取失敗" : cards.length ? `${cards.length} 組資料` : "尚無資料"}</span>
      </div>
      <div style={styles.artifactPreviewGrid}>
        {cards.map((card) => (
          <div style={styles.artifactCard} key={card.title}>
            <strong>{card.title}</strong>
            <div style={styles.evidenceRows}>
              {card.rows.map((row, index) => (
                <span style={styles.evidenceRow} key={`${card.title}-${row.label}-${index}`}>
                  <em>{row.label}</em>
                  <code style={styles.code}>{row.value}</code>
                </span>
              ))}
            </div>
          </div>
        ))}
        {!cards.length ? <EmptyLine text={step.nodeLog ? "此步驟沒有可展開的 artifact。" : "執行後會顯示資料。"} /> : null}
      </div>
    </div>
  );
}

function artifactPreviewCards(step: WorkflowStep, preview?: ArtifactPreviewEntry): Array<{ title: string; rows: FieldRow[] }> {
  if (preview?.loading) {
    return [{ title: step.displayName, rows: [{ label: "狀態", value: "讀取中" }] }];
  }
  if (preview?.error) {
    return [{ title: step.displayName, rows: [{ label: "錯誤", value: preview.error }] }];
  }
  return Object.entries(preview?.payloads ?? {}).map(([port, artifact]) => ({
    title: outputLabel(port),
    rows: summarizeArtifact(port, artifact.payload),
  }));
}

function summarizeArtifact(port: string, payload: unknown): FieldRow[] {
  if (Array.isArray(payload)) {
    const first = payload[0];
    return [
      { label: outputLabel(port), value: `${payload.length} 筆` },
      ...sampleRows(first),
    ];
  }
  if (payload && typeof payload === "object") {
    const objectPayload = payload as Record<string, unknown>;
    const priorityRows = priorityArtifactRows(port, objectPayload);
    const genericRows = Object.entries(objectPayload)
      .filter(([key]) => !priorityRows.some((row) => row.label === outputLabel(key) || row.label === inputLabel(key)))
      .slice(0, 6)
      .map(([key, value]) => ({ label: outputLabel(key), value: summarizeUnknown(value) }));
    return [...priorityRows, ...genericRows].slice(0, 9);
  }
  return [{ label: outputLabel(port), value: summarizeUnknown(payload) }];
}

function priorityArtifactRows(port: string, payload: Record<string, unknown>): FieldRow[] {
  const rows: FieldRow[] = [];
  const add = (label: string, value: unknown) => {
    if (value !== undefined && value !== null && value !== "") {
      rows.push({ label, value: summarizeUnknown(value) });
    }
  };
  if (port === "pages" && Array.isArray(payload)) {
    add("頁數", payload.length);
  }
  add("工作資料夾", payload.work_folder);
  add("頁面資料夾", payload.page_folder);
  add("PDF 數量", payload.pdf_count);
  add("資料來源", payload.source_kind || payload.kind);
  add("資料列數", payload.record_count);
  add("工作表", payload.sheet_name || payload.sheet);
  add("狀態", payload.status || payload.state);
  add("總列數", payload.total_rows || payload.total);
  add("通過", payload.ready || payload.pass || payload.passed);
  add("待確認", payload.review || payload.warn || payload.blocked);
  return rows;
}

function sampleRows(value: unknown): FieldRow[] {
  if (!value || typeof value !== "object") {
    return value === undefined ? [] : [{ label: "樣本", value: summarizeUnknown(value) }];
  }
  return Object.entries(value as Record<string, unknown>)
    .slice(0, 5)
    .map(([key, entry]) => ({ label: outputLabel(key), value: summarizeUnknown(entry) }));
}

function summarizeUnknown(value: unknown): string {
  if (value === undefined || value === null) {
    return "-";
  }
  if (typeof value === "string") {
    return value.includes("\\") || value.includes("/") ? compactPath(value) : value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return `${value.length} 筆`;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if ("artifact_ref" in (value as Record<string, unknown>)) {
      return outputRefSummary(value);
    }
    return entries.length ? `${entries.length} 欄位` : "{}";
  }
  return String(value);
}

function outputRefSummary(value: unknown): string {
  if (value && typeof value === "object") {
    const ref = value as Record<string, unknown>;
    if (typeof ref.artifact_ref === "string") {
      const bytes = typeof ref.bytes === "number" ? ` · ${Math.round(ref.bytes / 1024)} KB` : "";
      return `${compactPath(ref.artifact_ref)}${bytes}`;
    }
  }
  return summarizeUnknown(value);
}

function outputLabel(key: string) {
  if (key === "profile") return "設定檔";
  if (key === "candidates") return "來源候選";
  if (key === "folder") return "工作資料夾";
  if (key === "page_folder") return "頁面資料夾";
  if (key === "pages") return "頁面清單";
  if (key === "pdf_count") return "PDF 數量";
  if (key === "source_kind") return "來源類型";
  if (key === "iso_source") return "ISO 來源";
  if (key === "sample_records") return "樣本列";
  if (key === "record_count") return "資料列數";
  if (key === "rows") return "命名列";
  if (key === "result") return "命名結果";
  if (key === "job") return "工作狀態";
  if (key === "iso_run_log") return "ISO 紀錄";
  if (key === "pilot_results") return "檢查項目";
  if (key === "pilot_summary") return "檢查摘要";
  if (key === "distribution") return "信心分布";
  if (key === "csv_path") return "CSV 路徑";
  if (key === "applied") return "已套用";
  return inputLabel(key);
}

function compactWorkflowInputs(inputs: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(inputs).filter(([, value]) => value !== undefined),
  );
}

function stableJson(value: unknown): string {
  return JSON.stringify(value, (_key, entry) => {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
      return entry;
    }
    return Object.fromEntries(Object.entries(entry as Record<string, unknown>).sort(([left], [right]) => left.localeCompare(right)));
  });
}

function mergeUnique(left: string[], right: string[]): string[] {
  return [...new Set([...left, ...right])];
}

function dirtyNodesFrom(nodeId: string): string[] {
  const downstream: Record<string, string[]> = {
    pdf_source: ["pdf_source", "discover", "split", "load_table", "roi_calib", "batch_detect", "pilot", "roi_dist", "export_csv", "apply_rename"],
    discover: ["discover", "split", "load_table", "batch_detect", "pilot", "roi_dist", "export_csv", "apply_rename"],
    split: ["split", "roi_calib", "batch_detect", "pilot", "roi_dist", "export_csv", "apply_rename"],
    load_table: ["load_table", "batch_detect", "pilot", "roi_dist", "export_csv", "apply_rename"],
    roi_calib: ["roi_calib", "batch_detect", "pilot", "roi_dist", "export_csv", "apply_rename"],
    batch_detect: ["batch_detect", "pilot", "roi_dist", "export_csv", "apply_rename"],
  };
  return downstream[nodeId] ?? [nodeId];
}

function rerunEngineNodeId(nodeId: string): string {
  if (nodeId === "pdf_source") {
    return "discover";
  }
  if (nodeId === "roi_calib") {
    return "batch_detect";
  }
  return nodeId;
}

function buildSideEffectPreview(
  graphNodes: Array<{ display_name?: string; enabled?: boolean; node_id: string; node_type: string; requires_confirm?: boolean; side_effects?: string[] }>,
  specByType: Map<string, { display_name: string; guarded: boolean; side_effects: string[] }>,
): SideEffectPreviewItem[] {
  return graphNodes.flatMap((node) => {
    const spec = specByType.get(node.node_type);
    const effects = node.side_effects?.length ? node.side_effects : spec?.side_effects ?? [];
    return effects.map((effect) => ({
      effect,
      enabled: node.enabled !== false,
      guarded: Boolean(spec?.guarded || node.requires_confirm || isGuardedEffect(effect)),
      nodeId: node.node_id,
      nodeLabel: node.display_name || spec?.display_name || node.node_id,
    }));
  });
}

function inputPreviewRows(inputs: Record<string, unknown>): Array<[string, string]> {
  return Object.entries(inputs)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => [key, formatInputPreview(value)]);
}

function workbenchPlanRequest(plan: IsoWorkflowPlan, inputs: Record<string, unknown>, rows: IsoPlanRow[]): IsoWorkflowRequest {
  const source = plan.source;
  return {
    action: "apply",
    work_folder: stringInput(inputs.work_folder ?? source.work_folder),
    combine_pdf: stringInput(inputs.combine_pdf ?? source.combine_pdf),
    page_folder: stringInput(inputs.page_folder ?? source.page_folder),
    iso_list: stringInput(inputs.iso_list ?? source.iso_list),
    sheet_name: stringInput(inputs.sheet_name ?? source.sheet_name),
    serial_col: numberInput(inputs.serial_col ?? source.serial_col),
    line_col: numberInput(inputs.line_col ?? source.line_col),
    pattern: stringInput(inputs.pattern ?? source.pattern),
    serial_region: regionOrDefault(inputs.serial_region ?? source.serial_region, DEFAULT_SERIAL_REGION),
    drawing_region: regionOrDefault(inputs.drawing_region ?? source.drawing_region, DEFAULT_DRAWING_REGION),
    confidence_threshold: numberInput(inputs.confidence_threshold ?? source.confidence_threshold) || 0.7,
    detect_serials: booleanInput(inputs.detect_serials ?? source.detect_serials),
    run_id: plan.source_run_id || plan.provenance?.workflow_run_id,
    rows,
  };
}

function formatInputPreview(value: unknown): string {
  if (typeof value === "string") {
    return compactPath(value);
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function stringInput(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function numberInput(value: unknown): number | "" {
  if (value === "" || value === null || value === undefined) {
    return "";
  }
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : "";
}

function booleanInput(value: unknown): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "string") {
    return value.toLowerCase() !== "false";
  }
  return Boolean(value);
}

function regionOrDefault(value: unknown, fallback: typeof DEFAULT_SERIAL_REGION): typeof DEFAULT_SERIAL_REGION {
  if (!value || typeof value !== "object") {
    return fallback;
  }
  const region = value as Partial<typeof DEFAULT_SERIAL_REGION>;
  const next = {
    left: Number(region.left),
    top: Number(region.top),
    width: Number(region.width),
    height: Number(region.height),
  };
  return Object.values(next).every(Number.isFinite) ? next : fallback;
}

function inputLabel(key: string) {
  if (key === "work_folder") return "工作資料夾";
  if (key === "combine_pdf") return "合併 PDF";
  if (key === "iso_list") return "ISO 清單";
  if (key === "sheet_name") return "工作表";
  if (key === "serial_col") return "流水號欄";
  if (key === "line_col") return "圖號欄";
  if (key === "pattern") return "命名格式";
  if (key === "detect_serials") return "影像判讀";
  if (key === "confidence_threshold") return "信心門檻";
  if (key === "serial_region") return "流水號 ROI";
  if (key === "drawing_region") return "圖號 ROI";
  return key;
}

function isWorkflowJobRunning(job: IsoNodeWorkflowJobPayload | null): boolean {
  return Boolean(job && ["queued", "running", "cancel_requested"].includes(job.state));
}

function workflowJobStateLabel(state: string) {
  if (state === "queued") return "等待執行";
  if (state === "running") return "執行中";
  if (state === "cancel_requested") return "取消中";
  if (state === "cancelled") return "已取消";
  if (state === "completed") return "已完成";
  if (state === "completed_with_blocked") return "完成/阻擋";
  if (state === "failed") return "失敗";
  return state || "未知";
}

function safeRunBlockReason(graphValid: boolean, hasPdfSource: boolean, hasIsoSource: boolean) {
  if (!graphValid) return "請先讀取並通過 Safe POC graph 驗證。";
  if (!hasPdfSource) return "請先選擇工作資料夾或合併 PDF。";
  if (!hasIsoSource) return "請先選擇 ISO 清單或可自動探索的工作資料夾。";
  return "";
}

function SectionHead({ icon, title, meta }: { icon: ReactNode; title: string; meta: string }) {
  return (
    <div style={styles.sectionHead}>
      <span>{icon}</span>
      <strong>{title}</strong>
      <em>{meta}</em>
    </div>
  );
}

function Metric({ icon, label, value, tone = "idle" }: { icon: ReactNode; label: string; value: string; tone?: "idle" | "ready" | "warn" }) {
  const color = tone === "ready" ? "#2ff5c8" : tone === "warn" ? "#ffd166" : "rgba(220,235,228,0.68)";
  return (
    <div style={{ ...styles.metric, borderColor: tone === "idle" ? "rgba(255,255,255,0.08)" : color }}>
      <span style={{ color }}>{icon}</span>
      <small>{label}</small>
      <strong>{value}</strong>
    </div>
  );
}

function EmptyLine({ text }: { text: string }) {
  return <div style={styles.emptyLine}>{text}</div>;
}

function effectChips(effects: string[], guarded: boolean) {
  if (!effects.length) {
    return <span style={{ ...styles.effectChip, color: "#2ff5c8" }}>純讀</span>;
  }
  return effects.map((effect) => (
    <span style={{ ...styles.effectChip, color: guarded ? "#ffd166" : "#7fd7ff" }} key={effect}>
      {guarded ? <Lock size={11} /> : null}
      {sideEffectLabel(effect)}
    </span>
  ));
}

function nodeTone(effects: string[], guarded: boolean) {
  if (guarded) return "#ffd166";
  if (effects.length) return "#7fd7ff";
  return "#2ff5c8";
}

function isGuardedEffect(effect: string) {
  return ["renames_files", "writes_profile", "writes_csv"].includes(effect);
}

function statusTextForNode(nodeType: string, effects: string[]) {
  if (effects.length) {
    return effects.map(sideEffectLabel).join(" / ");
  }
  return nodeType.startsWith("iso.") ? "純讀" : "節點";
}

function sideEffectLabel(effect: string) {
  if (effect === "renames_files") return "更名";
  if (effect === "writes_profile") return "寫入設定";
  if (effect === "may_write_page_pdfs") return "拆頁輸出";
  if (effect === "writes_job_files") return "工作檔";
  if (effect === "writes_iso_run_log") return "ISO 紀錄";
  if (effect === "writes_csv") return "CSV";
  if (effect === "writes_debug_bundle") return "問題包";
  if (effect === "spawns_worker") return "背景處理";
  return effect;
}

function decisionLabel(decision: string) {
  if (decision === "executed") return "已執行";
  if (decision === "blocked_policy") return "政策阻擋";
  if (decision === "blocked_replay") return "回放阻擋";
  if (decision === "skipped_disabled") return "停用略過";
  if (decision === "skipped_dry_run") return "試算略過";
  if (decision === "skipped_not_needed") return "不需執行";
  if (decision === "simulated") return "模擬";
  return decision || "未記錄";
}

function gateConditionMark(met: boolean | null) {
  if (met === true) return "通過";
  if (met === false) return "未通過";
  return "手動";
}

function statusLabel(status: string) {
  if (status === "completed") return "完成";
  if (status === "completed_with_blocked") return "完成/阻擋";
  if (status === "success") return "成功";
  if (status === "blocked") return "已阻擋";
  if (status === "failed") return "失敗";
  if (status === "cancelled") return "已取消";
  if (status === "running") return "執行中";
  if (status === "not_run") return "未執行";
  if (status === "skipped_disabled") return "停用";
  return status || "未知";
}

function modeLabel(mode: string) {
  if (mode === "run") return "一般";
  if (mode === "dry_run") return "試算";
  if (mode === "replay") return "回放";
  return mode || "未知";
}

const styles = {
  shell: {
    border: "1px solid rgba(47,245,200,0.28)",
    borderRadius: 12,
    background: "linear-gradient(180deg, rgba(20,42,34,0.84), rgba(8,15,13,0.92))",
    boxShadow: "0 18px 46px rgba(0,0,0,0.24)",
    marginTop: 10,
    overflow: "hidden",
    minWidth: 0,
  },
  summary: {
    alignItems: "center",
    cursor: "pointer",
    display: "flex",
    gap: 12,
    justifyContent: "space-between",
    listStyle: "none",
    padding: "13px 16px",
    minWidth: 0,
  },
  title: {
    alignItems: "center",
    display: "flex",
    gap: 9,
    minWidth: 0,
  },
  badge: {
    border: "1px solid rgba(255,209,102,0.38)",
    borderRadius: 999,
    color: "#ffd166",
    fontSize: 11,
    fontStyle: "normal",
    padding: "2px 7px",
  },
  summaryMeta: {
    alignItems: "center",
    color: "rgba(220,235,228,0.66)",
    display: "flex",
    flex: "1 1 auto",
    flexWrap: "wrap",
    fontSize: 12,
    gap: 8,
    justifyContent: "flex-end",
    minWidth: 0,
  },
  chevron: {
    flex: "0 0 auto",
  },
  body: {
    borderTop: "1px solid rgba(255,255,255,0.08)",
    display: "flex",
    flexDirection: "column",
    gap: 12,
    padding: 12,
    minWidth: 0,
  },
  toolbar: {
    alignItems: "center",
    display: "flex",
    flexWrap: "wrap",
    gap: 10,
    justifyContent: "space-between",
    minWidth: 0,
  },
  toolbarText: {
    display: "flex",
    flexDirection: "column",
    gap: 3,
    minWidth: 0,
  },
  toolbarActions: {
    alignItems: "center",
    display: "flex",
    flexWrap: "wrap",
    gap: 7,
    justifyContent: "flex-end",
    minWidth: 0,
  },
  alert: {
    alignItems: "center",
    background: "rgba(255,209,102,0.09)",
    border: "1px solid rgba(255,209,102,0.28)",
    borderRadius: 10,
    color: "#ffd166",
    display: "flex",
    fontSize: 12,
    gap: 8,
    padding: "10px 12px",
  },
  notice: {
    background: "rgba(255,255,255,0.035)",
    border: "1px dashed rgba(255,255,255,0.14)",
    borderRadius: 10,
    color: "rgba(220,235,228,0.62)",
    fontSize: 12,
    padding: "9px 11px",
  },
  jobPanel: {
    background: "rgba(47,245,200,0.055)",
    border: "1px solid rgba(47,245,200,0.2)",
    borderRadius: 10,
    display: "flex",
    flexDirection: "column",
    gap: 8,
    minWidth: 0,
    padding: 10,
  },
  jobHead: {
    alignItems: "center",
    display: "flex",
    gap: 10,
    justifyContent: "space-between",
    minWidth: 0,
  },
  progressTrack: {
    background: "rgba(255,255,255,0.1)",
    borderRadius: 999,
    height: 8,
    overflow: "hidden",
    width: "100%",
  },
  progressFill: {
    background: "#2ff5c8",
    borderRadius: 999,
    display: "block",
    height: "100%",
    transition: "width 180ms ease",
  },
  jobMeta: {
    color: "rgba(220,235,228,0.66)",
    display: "flex",
    flexWrap: "wrap",
    fontSize: 12,
    gap: 9,
  },
  metrics: {
    display: "grid",
    gap: 8,
    gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
    minWidth: 0,
  },
  metric: {
    alignItems: "center",
    background: "rgba(255,255,255,0.035)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 10,
    display: "grid",
    gap: 4,
    gridTemplateColumns: "auto 1fr",
    padding: "10px 12px",
    minWidth: 0,
  },
  grid: {
    display: "grid",
    gap: 10,
    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
    minWidth: 0,
  },
  section: {
    background: "rgba(0,0,0,0.14)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 10,
    display: "flex",
    flexDirection: "column",
    gap: 8,
    minHeight: 0,
    minWidth: 0,
    padding: 10,
  },
  sectionWide: {
    background: "rgba(0,0,0,0.14)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 10,
    display: "flex",
    flexDirection: "column",
    gap: 8,
    gridColumn: "1 / -1",
    order: -1,
    minHeight: 0,
    minWidth: 0,
    padding: 10,
  },
  sectionFull: {
    background: "rgba(0,0,0,0.14)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 10,
    display: "flex",
    flexDirection: "column",
    gap: 8,
    gridColumn: "1 / -1",
    minHeight: 0,
    minWidth: 0,
    padding: 10,
  },
  sectionFlowTree: {
    background: "linear-gradient(180deg, rgba(4,24,19,0.7), rgba(0,0,0,0.12))",
    border: "1px solid rgba(47,245,200,0.22)",
    borderRadius: 10,
    display: "flex",
    flexDirection: "column",
    gap: 10,
    gridColumn: "1 / -1",
    order: -2,
    minHeight: 0,
    minWidth: 0,
    padding: 10,
  },
  sectionHead: {
    alignItems: "center",
    borderBottom: "1px solid rgba(255,255,255,0.08)",
    display: "flex",
    gap: 8,
    minWidth: 0,
    paddingBottom: 8,
  },
  flowTreeLayout: {
    display: "grid",
    gap: 10,
    gridTemplateColumns: "repeat(auto-fit, minmax(min(340px, 100%), 1fr))",
    minWidth: 0,
  },
  flowStepRail: {
    display: "grid",
    gap: 7,
    maxHeight: 540,
    minWidth: 0,
    overflow: "auto",
    paddingRight: 2,
  },
  flowStep: {
    alignItems: "center",
    background: "rgba(255,255,255,0.035)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 10,
    color: "inherit",
    cursor: "pointer",
    display: "grid",
    gap: 9,
    gridTemplateColumns: "32px minmax(0, 1fr) auto",
    minHeight: 58,
    minWidth: 0,
    padding: "8px 10px",
    textAlign: "left",
  },
  flowStepIndex: {
    alignItems: "center",
    border: "1px solid rgba(47,245,200,0.4)",
    borderRadius: 999,
    display: "inline-flex",
    fontSize: 12,
    fontWeight: 900,
    height: 28,
    justifyContent: "center",
    minWidth: 28,
  },
  flowStepText: {
    display: "flex",
    flexDirection: "column",
    gap: 3,
    minWidth: 0,
  },
  flowStepStatus: {
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 999,
    fontSize: 11,
    fontWeight: 800,
    padding: "3px 7px",
    whiteSpace: "nowrap",
  },
  flowStepDetail: {
    background: "rgba(0,0,0,0.13)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 10,
    display: "flex",
    flexDirection: "column",
    gap: 10,
    minHeight: 220,
    minWidth: 0,
    padding: 10,
  },
  stepDetailHead: {
    alignItems: "center",
    display: "grid",
    gap: 10,
    gridTemplateColumns: "auto minmax(0, 1fr) auto",
    minWidth: 0,
  },
  stepDetailTitle: {
    display: "flex",
    flexDirection: "column",
    gap: 3,
    minWidth: 0,
  },
  stepStatePill: {
    border: "1px solid rgba(47,245,200,0.4)",
    borderRadius: 999,
    fontSize: 12,
    fontWeight: 900,
    padding: "4px 9px",
    whiteSpace: "nowrap",
  },
  stepMetricGrid: {
    display: "grid",
    gap: 8,
    gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
    minWidth: 0,
  },
  evidenceGrid: {
    display: "grid",
    gap: 8,
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    minWidth: 0,
  },
  evidenceCard: {
    background: "rgba(255,255,255,0.035)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 8,
    display: "flex",
    flexDirection: "column",
    gap: 7,
    minWidth: 0,
    padding: "9px 10px",
  },
  evidenceRows: {
    display: "grid",
    gap: 5,
    minWidth: 0,
  },
  evidenceRow: {
    display: "grid",
    gap: 4,
    gridTemplateColumns: "minmax(72px, 0.32fr) minmax(0, 1fr)",
    minWidth: 0,
  },
  artifactPreview: {
    background: "rgba(47,245,200,0.045)",
    border: "1px solid rgba(47,245,200,0.16)",
    borderRadius: 8,
    display: "flex",
    flexDirection: "column",
    gap: 8,
    minWidth: 0,
    padding: 10,
  },
  artifactPreviewHead: {
    alignItems: "center",
    display: "flex",
    gap: 8,
    justifyContent: "space-between",
    minWidth: 0,
  },
  artifactPreviewGrid: {
    display: "grid",
    gap: 8,
    gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
    minWidth: 0,
  },
  artifactCard: {
    background: "rgba(0,0,0,0.16)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 8,
    display: "flex",
    flexDirection: "column",
    gap: 7,
    minWidth: 0,
    padding: "9px 10px",
  },
  scrollList: {
    display: "grid",
    gap: 7,
    maxHeight: 420,
    overflow: "auto",
    paddingRight: 2,
  },
  nodeCard: {
    background: "rgba(255,255,255,0.035)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderLeft: "3px solid #2ff5c8",
    borderRadius: 10,
    display: "flex",
    flexDirection: "column",
    gap: 7,
    minWidth: 0,
    padding: "9px 10px",
  },
  nodeTitle: {
    display: "flex",
    flexDirection: "column",
    gap: 3,
    minWidth: 0,
  },
  chipRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 5,
  },
  chip: {
    background: "rgba(255,255,255,0.055)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 999,
    color: "rgba(220,235,228,0.72)",
    fontSize: 11,
    padding: "2px 7px",
  },
  effectChip: {
    alignItems: "center",
    background: "rgba(255,255,255,0.055)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 999,
    display: "inline-flex",
    fontSize: 11,
    gap: 4,
    padding: "2px 7px",
  },
  canvasDetail: {
    background: "rgba(255,255,255,0.035)",
    border: "1px solid rgba(47,245,200,0.18)",
    borderRadius: 8,
    display: "flex",
    flexDirection: "column",
    gap: 8,
    padding: 10,
  },
  canvasDetailGrid: {
    display: "grid",
    gap: 10,
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    minWidth: 0,
  },
  canvasDetailHead: {
    alignItems: "center",
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    minWidth: 0,
  },
  compactPre: {
    background: "rgba(0,0,0,0.22)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 7,
    color: "rgba(220,235,228,0.78)",
    fontSize: 11,
    lineHeight: 1.45,
    margin: "5px 0 0",
    maxHeight: 120,
    overflow: "auto",
    padding: 8,
    whiteSpace: "pre-wrap",
  },
  topology: {
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
    minWidth: 0,
  },
  topologyStep: {
    background: "rgba(47,245,200,0.09)",
    border: "1px solid rgba(47,245,200,0.22)",
    borderRadius: 999,
    color: "#2ff5c8",
    fontSize: 11,
    padding: "4px 8px",
  },
  graphNodes: {
    display: "grid",
    gap: 7,
    gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))",
    minWidth: 0,
  },
  graphNode: {
    background: "rgba(255,255,255,0.035)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderLeft: "3px solid #2ff5c8",
    borderRadius: 10,
    display: "grid",
    gap: 3,
    gridTemplateColumns: "auto 1fr",
    minWidth: 0,
    padding: "8px 9px",
  },
  gateNote: {
    background: "rgba(255,209,102,0.08)",
    border: "1px solid rgba(255,209,102,0.22)",
    borderRadius: 8,
    color: "rgba(255,244,207,0.9)",
    alignItems: "center",
    display: "flex",
    flexWrap: "wrap",
    gap: 7,
    justifyContent: "space-between",
    padding: 10,
  },
  engineSwitch: {
    alignItems: "center",
    display: "flex",
    flexWrap: "wrap",
    gap: 7,
  },
  gateChecklist: {
    display: "grid",
    gap: 7,
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    minWidth: 0,
  },
  gateCondition: {
    background: "rgba(255,255,255,0.035)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 8,
    display: "grid",
    gap: 5,
    minWidth: 0,
    padding: "8px 10px",
  },
  issueList: {
    color: "#ffd166",
    display: "flex",
    flexDirection: "column",
    fontSize: 11,
    gap: 5,
  },
  jsonDetails: {
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 10,
    marginTop: 10,
    overflow: "hidden",
  },
  jsonSummary: {
    alignItems: "center",
    cursor: "pointer",
    display: "flex",
    gap: 10,
    justifyContent: "space-between",
    padding: "8px 10px",
  },
  jsonPre: {
    background: "rgba(0,0,0,0.2)",
    color: "rgba(220,235,228,0.86)",
    fontSize: 11,
    lineHeight: 1.55,
    margin: 0,
    maxHeight: 360,
    overflow: "auto",
    padding: 10,
    whiteSpace: "pre-wrap",
  },
  parityItem: {
    background: "rgba(255,255,255,0.035)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 8,
    display: "grid",
    gap: 4,
    minWidth: 0,
    padding: "8px 10px",
  },
  reportChips: {
    display: "flex",
    flexWrap: "wrap",
    gap: 5,
  },
  reportChip: {
    background: "rgba(255,255,255,0.055)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 999,
    color: "rgba(220,235,228,0.72)",
    fontSize: 11,
    fontWeight: 800,
    padding: "2px 7px",
  },
  parityList: {
    display: "grid",
    gap: 7,
    minWidth: 0,
  },
  runLayout: {
    display: "grid",
    gap: 10,
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    minWidth: 0,
  },
  modalBackdrop: {
    alignItems: "center",
    background: "rgba(0,0,0,0.52)",
    bottom: 0,
    display: "flex",
    justifyContent: "center",
    left: 0,
    padding: 14,
    position: "fixed",
    right: 0,
    top: 0,
    zIndex: 30,
  },
  modal: {
    background: "linear-gradient(180deg, rgba(21,39,34,0.98), rgba(8,14,12,0.98))",
    border: "1px solid rgba(47,245,200,0.32)",
    borderRadius: 12,
    boxShadow: "0 24px 80px rgba(0,0,0,0.5)",
    display: "flex",
    flexDirection: "column",
    gap: 12,
    maxHeight: "86vh",
    maxWidth: 760,
    minWidth: 0,
    overflow: "auto",
    padding: 14,
    width: "min(760px, calc(100vw - 28px))",
  },
  modalHead: {
    alignItems: "flex-start",
    borderBottom: "1px solid rgba(255,255,255,0.08)",
    display: "flex",
    gap: 12,
    justifyContent: "space-between",
    minWidth: 0,
    paddingBottom: 10,
  },
  modalGrid: {
    display: "grid",
    gap: 10,
    gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
    minWidth: 0,
  },
  modalSection: {
    background: "rgba(255,255,255,0.035)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 10,
    display: "flex",
    flexDirection: "column",
    gap: 8,
    minWidth: 0,
    padding: 10,
  },
  previewList: {
    display: "grid",
    gap: 6,
    minWidth: 0,
  },
  previewRow: {
    display: "grid",
    gap: 4,
    minWidth: 0,
  },
  modalActions: {
    alignItems: "center",
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    justifyContent: "flex-end",
  },
  runList: {
    display: "grid",
    gap: 7,
    maxHeight: 260,
    minWidth: 0,
    overflow: "auto",
    paddingRight: 2,
  },
  runItem: {
    background: "rgba(255,255,255,0.035)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 10,
    color: "inherit",
    cursor: "pointer",
    display: "grid",
    gap: 3,
    minWidth: 0,
    padding: "8px 9px",
    textAlign: "left",
  },
  runDetail: {
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 10,
    minHeight: 120,
    minWidth: 0,
    padding: 10,
  },
  runDetailHead: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    minWidth: 0,
    paddingBottom: 8,
  },
  nodeStatusList: {
    display: "grid",
    gap: 6,
  },
  nodeStatus: {
    alignItems: "center",
    background: "rgba(255,255,255,0.035)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 8,
    display: "grid",
    gap: 7,
    gridTemplateColumns: "minmax(0, 1fr) auto auto",
    minWidth: 0,
    padding: "7px 8px",
  },
  emptyLine: {
    color: "rgba(220,235,228,0.56)",
    fontSize: 12,
    padding: "8px 0",
  },
  code: {
    color: "rgba(220,235,228,0.62)",
    fontSize: 11,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
} satisfies Record<string, CSSProperties>;
