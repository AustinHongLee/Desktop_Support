import { isTauri } from "@tauri-apps/api/core";
import { CircleAlert, CircleCheck, FileSearch, GitBranch, RefreshCcw, ShieldCheck, Table2 } from "lucide-react";
import { useMemo, useState, type CSSProperties, type SyntheticEvent } from "react";
import {
  listIsoWorkflowRuns,
  loadIsoWorkflowPlanFromRun,
  readIsoWorkflowRunLog,
  type IsoNodeWorkflowRunLog,
  type IsoNodeWorkflowRunSummary,
  type IsoWorkflowPlan,
} from "../../isoWorkflow";
import { compactPath, localizeIsoDisplayText, runStatusLabel } from "../helpers";
import { PilotStrip } from "./PilotStrip";

type WorkflowRunPlanPanelProps = {
  fixedRunId?: string;
  onAdoptParams?: (source: IsoWorkflowPlan["source"]) => void;
  openRunLogDrawer?: (runId?: string) => void;
};

const panelStyle: CSSProperties = {
  border: "1px solid rgba(45, 212, 191, 0.24)",
  borderRadius: 10,
  background: "linear-gradient(180deg, rgba(20, 38, 34, 0.74), rgba(8, 15, 13, 0.9))",
  overflow: "hidden",
};

const bodyStyle: CSSProperties = {
  display: "grid",
  gap: 12,
  padding: 12,
};

const rowGridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "56px minmax(120px, 1fr) minmax(120px, 1fr) minmax(100px, 0.7fr) 80px",
  gap: 8,
  alignItems: "center",
};

export function WorkflowRunPlanPanel({ fixedRunId, onAdoptParams, openRunLogDrawer }: WorkflowRunPlanPanelProps) {
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [runs, setRuns] = useState<IsoNodeWorkflowRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState(fixedRunId ?? "");
  const [projectedPlan, setProjectedPlan] = useState<IsoWorkflowPlan | null>(null);
  const [runLog, setRunLog] = useState<IsoNodeWorkflowRunLog | null>(null);

  const runOptions = useMemo(() => fixedRunId ? runs.filter((run) => run.run_id === fixedRunId) : runs, [fixedRunId, runs]);
  const sideEffects = runLog?.side_effect_summary;
  const provenance = projectedPlan?.provenance;
  const sourceRunId = provenance?.iso_run_log?.run_id || "";

  async function ensureLoaded() {
    if (loaded || busy) {
      return;
    }
    await refreshRuns(fixedRunId || selectedRunId);
  }

  async function refreshRuns(preferredRunId = selectedRunId) {
    if (!isTauri()) {
      setError("請用 Tauri 桌面版讀取節點流程結果。");
      setLoaded(true);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const payload = await listIsoWorkflowRuns();
      const nextRuns = payload.runs;
      const nextRunId = fixedRunId || preferredRunId || nextRuns[0]?.run_id || "";
      setRuns(nextRuns);
      setSelectedRunId(nextRunId);
      setLoaded(true);
      if (nextRunId) {
        await loadRunProjection(nextRunId);
      } else {
        setProjectedPlan(null);
        setRunLog(null);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setLoaded(true);
    } finally {
      setBusy(false);
    }
  }

  async function loadRunProjection(runId: string) {
    if (!runId) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const [plan, log] = await Promise.all([
        loadIsoWorkflowPlanFromRun(runId),
        readIsoWorkflowRunLog(runId),
      ]);
      setSelectedRunId(runId);
      setProjectedPlan(plan);
      setRunLog(log);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setProjectedPlan(null);
      setRunLog(null);
    } finally {
      setBusy(false);
    }
  }

  function handleToggle(event: SyntheticEvent<HTMLDetailsElement>) {
    if (event.currentTarget.open) {
      void ensureLoaded();
    }
  }

  return (
    <details className="workflow-run-plan-panel" style={panelStyle} onToggle={handleToggle}>
      <summary style={summaryStyle}>
        <span style={summaryTitleStyle}>
          <GitBranch size={15} />
          <span>節點流程結果（唯讀）</span>
        </span>
        <small>{projectedPlan ? `${projectedPlan.summary.selected} / ${projectedPlan.summary.total} 可更名` : busy ? "讀取中" : "可展開查看"}</small>
      </summary>

      <div style={bodyStyle}>
        <div style={toolbarStyle}>
          <label style={selectWrapStyle}>
            <FileSearch size={14} />
            <select
              value={selectedRunId}
              onChange={(event) => void loadRunProjection(event.target.value)}
              disabled={busy || !runOptions.length || Boolean(fixedRunId)}
            >
              {!runOptions.length ? <option value="">尚無節點流程紀錄</option> : null}
              {runOptions.map((run) => (
                <option value={run.run_id} key={run.run_id}>
                  {run.workflow_id || "節點流程"} · {runStatusLabel(run.status)} · {run.run_id}
                </option>
              ))}
            </select>
          </label>
          <button className="action-button" type="button" onClick={() => void refreshRuns(selectedRunId)} disabled={busy}>
            <RefreshCcw size={14} />
            <span>{busy ? "讀取中" : "重新整理"}</span>
          </button>
          <button className="action-button" type="button" onClick={() => projectedPlan && onAdoptParams?.(projectedPlan.source)} disabled={!projectedPlan || busy}>
            <Table2 size={14} />
            <span>以此參數重新產生草稿</span>
          </button>
        </div>

        {error ? <div style={noticeStyle("warn")}><CircleAlert size={15} />{error}</div> : null}

        {projectedPlan ? (
          <>
            <div style={metricGridStyle}>
              <Metric label="總列數" value={projectedPlan.summary.total} />
              <Metric label="通過" value={projectedPlan.summary.ready} tone="ready" />
              <Metric label="待確認" value={projectedPlan.summary.warn} tone="warn" />
              <Metric label="需處理" value={projectedPlan.summary.blocked} tone="warn" />
              <Metric label="已選" value={projectedPlan.summary.selected} tone="ready" />
            </div>

            <div style={sourceGridStyle}>
              <ReadOnlyPill label="PDF" value={compactPath(projectedPlan.source.page_folder || projectedPlan.source.combine_pdf || projectedPlan.source.work_folder || "等待來源")} />
              <ReadOnlyPill label="ISO 清單" value={compactPath(projectedPlan.source.iso_list || "等待來源")} />
              <ReadOnlyPill label="工作表" value={projectedPlan.source.sheet_name || "自動"} />
              <ReadOnlyPill label="命名格式" value={projectedPlan.source.pattern || "{serial}--{line}.pdf"} />
            </div>

            <PilotStrip items={projectedPlan.pilot_results ?? []} title="節點流程檢查" />

            <section style={sectionStyle}>
              <div style={sectionHeadStyle}>
                <strong>唯讀命名列</strong>
                <span>{projectedPlan.rows.length} 列</span>
              </div>
              <div style={tableStyle}>
                <div style={{ ...rowGridStyle, ...headerRowStyle }}>
                  <span>頁</span>
                  <span>來源檔</span>
                  <span>新檔名</span>
                  <span>流水號</span>
                  <span>狀態</span>
                </div>
                {projectedPlan.rows.slice(0, 24).map((row) => (
                  <div style={rowGridStyle} key={row.id}>
                    <span>{row.page}</span>
                    <strong title={row.source_name}>{row.source_name}</strong>
                    <span title={row.new_name}>{row.new_name || "尚未命名"}</span>
                    <span>{row.serial || "-"}</span>
                    <StatusBadge status={row.status} />
                  </div>
                ))}
                {projectedPlan.rows.length > 24 ? <div style={moreRowsStyle}>另有 {projectedPlan.rows.length - 24} 列未展開</div> : null}
              </div>
            </section>

            <section style={sectionStyle}>
              <div style={sectionHeadStyle}>
                <strong>來源證據</strong>
                <span>{runStatusLabel(provenance?.run_status || runLog?.status || "")}</span>
              </div>
              <div style={sourceGridStyle}>
                <ReadOnlyPill label="節點 run" value={selectedRunId || "-"} />
                <ReadOnlyPill label="流程" value={provenance?.workflow_id || runLog?.workflow_id || "-"} />
                <ReadOnlyPill label="圖雜湊" value={provenance?.graph_hash || runLog?.graph_hash || "-"} />
                <ReadOnlyPill label="來源 ISO 紀錄" value={sourceRunId || "-"} />
              </div>
              {sourceRunId ? (
                <button className="action-button" type="button" onClick={() => openRunLogDrawer?.(sourceRunId)}>
                  <FileSearch size={14} />
                  <span>開啟來源處理紀錄</span>
                </button>
              ) : null}
            </section>

            <section style={sectionStyle}>
              <div style={sectionHeadStyle}>
                <strong>副作用證據</strong>
                <span>紀錄</span>
              </div>
              <div style={sourceGridStyle}>
                <ReadOnlyPill label="已執行" value={String(sideEffects?.executed.length ?? 0)} />
                <ReadOnlyPill label="已阻擋" value={String(sideEffects?.blocked.length ?? 0)} />
                <ReadOnlyPill label="已略過" value={String(sideEffects?.skipped.length ?? 0)} />
                <ReadOnlyPill label="模擬" value={String(sideEffects?.simulated.length ?? 0)} />
              </div>
            </section>
          </>
        ) : loaded && !busy && !error ? (
          <div style={noticeStyle("idle")}><ShieldCheck size={15} />尚無可投影的節點流程結果。</div>
        ) : null}
      </div>
    </details>
  );
}

function Metric({ label, tone = "idle", value }: { label: string; tone?: "ready" | "warn" | "idle"; value: number }) {
  return (
    <div style={metricStyle(tone)}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ReadOnlyPill({ label, value }: { label: string; value: string }) {
  return (
    <div style={pillStyle}>
      <span>{label}</span>
      <strong title={value}>{localizeIsoDisplayText(value)}</strong>
    </div>
  );
}

function StatusBadge({ status }: { status: IsoWorkflowPlan["rows"][number]["status"] }) {
  const ready = status === "ready";
  return (
    <span style={statusBadgeStyle(ready)}>
      {ready ? <CircleCheck size={13} /> : <CircleAlert size={13} />}
      {statusLabel(status)}
    </span>
  );
}

function statusLabel(status: IsoWorkflowPlan["rows"][number]["status"]): string {
  if (status === "ready") return "通過";
  if (status === "warn") return "待確認";
  if (status === "blocked") return "需處理";
  return "待命";
}

function noticeStyle(tone: "warn" | "idle"): CSSProperties {
  return {
    display: "flex",
    alignItems: "center",
    gap: 8,
    border: `1px solid ${tone === "warn" ? "rgba(250, 204, 21, 0.32)" : "rgba(45, 212, 191, 0.22)"}`,
    borderRadius: 8,
    color: tone === "warn" ? "#fde68a" : "#b7d8ce",
    padding: "10px 12px",
  };
}

function metricStyle(tone: "ready" | "warn" | "idle"): CSSProperties {
  return {
    border: `1px solid ${tone === "ready" ? "rgba(52, 211, 153, 0.32)" : tone === "warn" ? "rgba(250, 204, 21, 0.28)" : "rgba(148, 163, 184, 0.18)"}`,
    borderRadius: 8,
    padding: "8px 10px",
    background: "rgba(5, 12, 10, 0.42)",
  };
}

function statusBadgeStyle(ready: boolean): CSSProperties {
  return {
    display: "inline-flex",
    alignItems: "center",
    gap: 5,
    color: ready ? "#86efac" : "#fde68a",
    fontWeight: 800,
  };
}

const summaryStyle: CSSProperties = {
  alignItems: "center",
  cursor: "pointer",
  display: "flex",
  justifyContent: "space-between",
  gap: 12,
  padding: "12px 14px",
};

const summaryTitleStyle: CSSProperties = {
  alignItems: "center",
  color: "#e5fff8",
  display: "inline-flex",
  fontWeight: 900,
  gap: 8,
};

const toolbarStyle: CSSProperties = {
  alignItems: "center",
  display: "grid",
  gap: 8,
  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
};

const selectWrapStyle: CSSProperties = {
  alignItems: "center",
  border: "1px solid rgba(45, 212, 191, 0.22)",
  borderRadius: 8,
  display: "grid",
  gap: 8,
  gridTemplateColumns: "18px minmax(0, 1fr)",
  minWidth: 0,
  padding: "7px 10px",
};

const metricGridStyle: CSSProperties = {
  display: "grid",
  gap: 8,
  gridTemplateColumns: "repeat(auto-fit, minmax(82px, 1fr))",
};

const sourceGridStyle: CSSProperties = {
  display: "grid",
  gap: 8,
  gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
};

const sectionStyle: CSSProperties = {
  border: "1px solid rgba(148, 163, 184, 0.14)",
  borderRadius: 8,
  display: "grid",
  gap: 10,
  padding: 10,
};

const sectionHeadStyle: CSSProperties = {
  alignItems: "center",
  color: "#c7f7eb",
  display: "flex",
  justifyContent: "space-between",
};

const pillStyle: CSSProperties = {
  border: "1px solid rgba(45, 212, 191, 0.18)",
  borderRadius: 8,
  display: "grid",
  gap: 3,
  minWidth: 0,
  padding: "8px 10px",
};

const tableStyle: CSSProperties = {
  display: "grid",
  gap: 4,
  overflowX: "auto",
};

const headerRowStyle: CSSProperties = {
  borderBottom: "1px solid rgba(148, 163, 184, 0.16)",
  color: "#a7f3d0",
  fontSize: 11,
  fontWeight: 900,
  paddingBottom: 5,
};

const moreRowsStyle: CSSProperties = {
  color: "#b7d8ce",
  padding: "8px 0 2px",
  textAlign: "center",
};
