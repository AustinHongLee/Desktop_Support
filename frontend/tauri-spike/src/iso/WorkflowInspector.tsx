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
  listIsoWorkflowNodes,
  listIsoWorkflowRuns,
  loadIsoWorkflowJobStatus,
  loadIsoNodeWorkflow,
  readIsoWorkflowRunLog,
  runIsoNodeWorkflowSafe,
  type IsoNodeWorkflowJobPayload,
  type IsoNodeWorkflowListPayload,
  type IsoNodeWorkflowRunLog,
  type IsoNodeWorkflowRunSummary,
  type IsoNodeWorkflowValidationPayload,
} from "../isoWorkflow";
import { compactPath } from "./helpers";

const SAFE_WORKFLOW_PATH = "launcher/plugins/iso_tools/workflow/workflows/iso_pdf_safe_poc.workflow.json";

type WorkflowInspectorProps = {
  workflowInputs?: Record<string, unknown>;
};

export function WorkflowInspector({ workflowInputs = {} }: WorkflowInspectorProps) {
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [runError, setRunError] = useState("");
  const [nodeCatalog, setNodeCatalog] = useState<IsoNodeWorkflowListPayload | null>(null);
  const [graph, setGraph] = useState<IsoNodeWorkflowValidationPayload | null>(null);
  const [runs, setRuns] = useState<IsoNodeWorkflowRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [runLog, setRunLog] = useState<IsoNodeWorkflowRunLog | null>(null);
  const [safeRunConfirmOpen, setSafeRunConfirmOpen] = useState(false);
  const [safeRunBusy, setSafeRunBusy] = useState(false);
  const [cancelBusy, setCancelBusy] = useState(false);
  const [job, setJob] = useState<IsoNodeWorkflowJobPayload | null>(null);

  const specByType = useMemo(() => {
    const entries = (nodeCatalog?.nodes ?? []).map((spec) => [spec.node_type, spec] as const);
    return new Map(entries);
  }, [nodeCatalog]);
  const graphNodes = graph?.graph?.nodes ?? [];
  const selectedRun = runs.find((run) => run.run_id === selectedRunId) ?? runs[0] ?? null;
  const summary = job?.result?.side_effect_summary ?? selectedRun?.side_effect_summary ?? runLog?.side_effect_summary;
  const blockedCount = summary?.blocked?.length ?? 0;
  const executedCount = summary?.executed?.length ?? 0;
  const safeInputs = useMemo(() => compactWorkflowInputs(workflowInputs), [workflowInputs]);
  const hasPdfSource = Boolean(safeInputs.work_folder || safeInputs.combine_pdf);
  const hasIsoSource = Boolean(safeInputs.iso_list || safeInputs.work_folder);
  const safeRunReady = Boolean(graph?.valid) && hasPdfSource && hasIsoSource;
  const canRunSafe = safeRunReady && !safeRunBusy && !isWorkflowJobRunning(job);
  const sideEffectPreview = useMemo(() => buildSideEffectPreview(graphNodes, specByType), [graphNodes, specByType]);
  const terminalJob = Boolean(job && !isWorkflowJobRunning(job));

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
        setJob(next);
        setRunError(next.error || "");
        if (!isWorkflowJobRunning(next) && next.workflow_run_id) {
          await refreshRuns(next.workflow_run_id);
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

  function handleToggle(event: SyntheticEvent<HTMLDetailsElement>) {
    if (event.currentTarget.open && !loaded && !loading) {
      void refresh();
    }
  }

  async function refresh() {
    if (!isTauri()) {
      setError("請用 Tauri 桌面版讀取節點工作流。");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [nodesPayload, graphPayload, runsPayload] = await Promise.all([
        listIsoWorkflowNodes(),
        loadIsoNodeWorkflow(SAFE_WORKFLOW_PATH),
        listIsoWorkflowRuns(),
      ]);
      setNodeCatalog(nodesPayload);
      setGraph(graphPayload);
      setRuns(runsPayload.runs);
      setLoaded(true);
      const runId = selectedRunId || runsPayload.runs[0]?.run_id || "";
      if (runId) {
        await loadRunLog(runId);
      } else {
        setRunLog(null);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
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
    }
  }

  async function loadRunLog(runId: string) {
    if (!runId) {
      return;
    }
    setSelectedRunId(runId);
    try {
      setRunLog(await readIsoWorkflowRunLog(runId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setRunLog(null);
    }
  }

  function requestSafeRun() {
    if (!isTauri()) {
      setRunError("請用 Tauri 桌面版執行節點工作流。");
      return;
    }
    if (!safeRunReady) {
      setRunError(safeRunBlockReason(graph?.valid === true, hasPdfSource, hasIsoSource));
      return;
    }
    setRunError("");
    setSafeRunConfirmOpen(true);
  }

  async function confirmSafeRun() {
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
      setJob(next);
      setSafeRunConfirmOpen(false);
      if (!isWorkflowJobRunning(next) && next.workflow_run_id) {
        await refreshRuns(next.workflow_run_id);
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
      setJob(await cancelIsoWorkflowJob(jobId));
    } catch (caught) {
      setRunError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setCancelBusy(false);
    }
  }

  return (
    <details style={styles.shell} onToggle={handleToggle}>
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
            <button className="action-button" type="button" onClick={requestSafeRun} disabled={!canRunSafe}>
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

        <div style={styles.grid}>
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
            <SectionHead icon={<Route size={16} />} title="Safe POC Graph" meta={graph?.workflow_id || graph?.graph?.workflow_id || "等待"} />
            <div style={styles.topology}>
              {(graph?.topology ?? []).map((nodeId) => (
                <span style={styles.topologyStep} key={nodeId}>{nodeId}</span>
              ))}
              {loaded && !graph?.topology.length ? <EmptyLine text="尚無拓撲資料。" /> : null}
            </div>
            <div style={styles.graphNodes}>
              {graphNodes.map((node) => {
                const spec = specByType.get(node.node_type);
                const guarded = Boolean(spec?.guarded || node.requires_confirm);
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
                    <em>{nodeStatus ? statusLabel(nodeStatus) : disabled ? "停用" : statusTextForNode(node.node_type, spec?.side_effects ?? [])}</em>
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
                  </>
                ) : (
                  <EmptyLine text="沒有可讀取的紀錄。" />
                )}
              </div>
            </div>
          </section>
        </div>
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

type SideEffectPreviewItem = {
  effect: string;
  enabled: boolean;
  guarded: boolean;
  nodeId: string;
  nodeLabel: string;
};

function compactWorkflowInputs(inputs: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(inputs).filter(([, value]) => value !== undefined),
  );
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
      guarded: Boolean(spec?.guarded || node.requires_confirm),
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

function formatInputPreview(value: unknown): string {
  if (typeof value === "string") {
    return compactPath(value);
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
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
  sectionHead: {
    alignItems: "center",
    borderBottom: "1px solid rgba(255,255,255,0.08)",
    display: "flex",
    gap: 8,
    minWidth: 0,
    paddingBottom: 8,
  },
  scrollList: {
    display: "grid",
    gap: 7,
    maxHeight: 260,
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
  issueList: {
    color: "#ffd166",
    display: "flex",
    flexDirection: "column",
    fontSize: 11,
    gap: 5,
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
