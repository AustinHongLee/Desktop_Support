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
import { useMemo, useState } from "react";
import {
  listIsoWorkflowNodes,
  listIsoWorkflowRuns,
  loadIsoNodeWorkflow,
  readIsoWorkflowRunLog,
  type IsoNodeWorkflowListPayload,
  type IsoNodeWorkflowRunLog,
  type IsoNodeWorkflowRunSummary,
  type IsoNodeWorkflowValidationPayload,
} from "../isoWorkflow";
import { compactPath } from "./helpers";

const SAFE_WORKFLOW_PATH = "launcher/plugins/iso_tools/workflow/workflows/iso_pdf_safe_poc.workflow.json";

export function WorkflowInspector() {
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [nodeCatalog, setNodeCatalog] = useState<IsoNodeWorkflowListPayload | null>(null);
  const [graph, setGraph] = useState<IsoNodeWorkflowValidationPayload | null>(null);
  const [runs, setRuns] = useState<IsoNodeWorkflowRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [runLog, setRunLog] = useState<IsoNodeWorkflowRunLog | null>(null);

  const specByType = useMemo(() => {
    const entries = (nodeCatalog?.nodes ?? []).map((spec) => [spec.node_type, spec] as const);
    return new Map(entries);
  }, [nodeCatalog]);
  const graphNodes = graph?.graph?.nodes ?? [];
  const selectedRun = runs.find((run) => run.run_id === selectedRunId) ?? runs[0] ?? null;
  const summary = selectedRun?.side_effect_summary ?? runLog?.side_effect_summary;
  const blockedCount = summary?.blocked?.length ?? 0;
  const executedCount = summary?.executed?.length ?? 0;

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
          <button className="action-button" type="button" onClick={() => void refresh()} disabled={loading}>
            <RefreshCcw size={15} />
            <span>{loading ? "讀取中" : "重新整理"}</span>
          </button>
        </div>

        {error ? (
          <div style={styles.alert}>
            <CircleAlert size={16} />
            <span>{error}</span>
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
                return (
                  <div
                    style={{ ...styles.graphNode, opacity: disabled ? 0.55 : 1, borderLeftColor: guarded ? "#ffd166" : "#2ff5c8" }}
                    key={node.node_id}
                  >
                    <span>{guarded ? <Lock size={13} /> : <CircleCheck size={13} />}</span>
                    <strong>{node.display_name || spec?.display_name || node.node_id}</strong>
                    <code style={styles.code}>{node.node_id}</code>
                    <em>{disabled ? "停用" : statusTextForNode(node.node_type, spec?.side_effects ?? [])}</em>
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
      </div>
    </details>
  );
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
