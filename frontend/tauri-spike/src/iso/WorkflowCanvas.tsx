import { Background, Controls, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Lock, ShieldCheck } from "lucide-react";
import type { CSSProperties } from "react";
import { useMemo } from "react";
import type { IsoNodeWorkflowRunLog, IsoNodeWorkflowValidationPayload } from "../isoWorkflow";
import { buildWorkbenchGraph, type FlowNodeData } from "./flowAdapter";
import type { NodeCardSummary } from "./workbench/nodeCards";

type CanvasNodeData = FlowNodeData & Record<string, unknown> & {
  decision: string;
  nodeId: string;
  onRunFrom?: (nodeId: string) => void;
  onRunNode?: (nodeId: string) => void;
  rerunEnabled: boolean;
  selected: boolean;
  summary?: NodeCardSummary;
  status: string;
};

type CanvasNode = Node<CanvasNodeData, "isoNode">;

type WorkflowCanvasProps = {
  payload: IsoNodeWorkflowValidationPayload | null;
  runLog: IsoNodeWorkflowRunLog | null;
  nodeSummaries?: Record<string, NodeCardSummary>;
  selectedNodeId?: string;
  onSelectNode?: (nodeId: string) => void;
  onRunFrom?: (nodeId: string) => void;
  onRunNode?: (nodeId: string) => void;
  rerunEnabled?: boolean;
};

const guardedTitle = "guarded：需 CLI 三因子授權（--allow + --confirm + enabled）";

export function WorkflowCanvas({ payload, runLog, nodeSummaries = {}, selectedNodeId = "", onSelectNode, onRunFrom, onRunNode, rerunEnabled = false }: WorkflowCanvasProps) {
  const flow = useMemo(() => {
    if (!payload?.graph) {
      return { nodes: [] as CanvasNode[], edges: [] as Edge[] };
    }
    const projected = buildWorkbenchGraph(payload);
    const nodes: CanvasNode[] = projected.nodes.map((node) => {
      const logNode = runLog?.nodes?.[node.id];
      return {
        id: node.id,
        type: "isoNode",
        position: node.position,
        data: {
          ...node.data,
          decision: firstDecision(logNode?.side_effects ?? []),
          nodeId: node.id,
          onRunFrom,
          onRunNode,
          rerunEnabled,
          selected: selectedNodeId === node.id,
          summary: nodeSummaries[node.id],
          status: logNode?.status ?? "",
        },
      };
    });
    const edges: Edge[] = projected.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle,
      targetHandle: edge.targetHandle,
      markerEnd: { type: MarkerType.ArrowClosed },
      type: "smoothstep",
      style: { stroke: "rgba(47,245,200,0.24)", strokeWidth: 1.15 },
    }));
    return { nodes, edges };
  }, [payload, runLog, nodeSummaries, onRunFrom, onRunNode, rerunEnabled, selectedNodeId]);

  if (!payload?.graph) {
    return <div style={styles.empty}>尚未載入 graph。</div>;
  }
  if ((payload.graph.nodes ?? []).length > 60) {
    return <div style={styles.empty}>節點超過 60 個，保留 JSON 檢視。</div>;
  }

  return (
    <div style={styles.canvasShell}>
      <ReactFlow<CanvasNode, Edge>
        nodes={flow.nodes}
        edges={flow.edges}
        nodeTypes={{ isoNode: IsoNode }}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        nodesConnectable={false}
        nodesDraggable
        edgesFocusable={false}
        deleteKeyCode={null}
        onNodeClick={(_event, node) => onSelectNode?.(node.id)}
      >
        <Background color="rgba(47,245,200,0.12)" gap={18} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

function IsoNode({ data, selected }: NodeProps<CanvasNode>) {
  const disabled = !data.enabled;
  const guarded = data.guarded;
  const tone = disabled ? "disabled" : guarded ? "guarded" : data.sideEffects.length ? "auto" : "read";
  const dirty = data.summary?.badges.some((badge) => badge.label === "參數已變更") ?? false;
  const active = data.selected || selected;
  const inputPorts = data.inputPorts ?? [];
  const outputPorts = data.outputPorts ?? [];
  return (
    <div style={{ ...styles.node, ...nodeToneStyle(tone), ...(dirty ? styles.dirtyNode : {}), outline: active ? "2px solid rgba(47,245,200,0.75)" : "0" }}>
      {inputPorts.map((port, index) => (
        <Handle
          id={port.name}
          key={`in-${port.name}`}
          type="target"
          position={Position.Left}
          style={{ ...styles.handle, top: portTop(index, inputPorts.length), left: -4 }}
        />
      ))}
      {outputPorts.map((port, index) => (
        <Handle
          id={port.name}
          key={`out-${port.name}`}
          type="source"
          position={Position.Right}
          style={{ ...styles.handle, top: portTop(index, outputPorts.length), right: -4 }}
        />
      ))}
      <div style={styles.nodeHead}>
        <span style={styles.stepBadge}>{stepNumber(data.nodeId)}</span>
        <span style={styles.nodeTitle}>
          <strong style={styles.nodeName}>{data.displayName}</strong>
          <em style={styles.nodeHint}>{stageHint(data.nodeId)}</em>
        </span>
        <span style={styles.nodeIcon}>{guarded ? <Lock size={13} /> : <ShieldCheck size={13} />}</span>
      </div>
      <NodeSummary summary={data.summary} />
      <div style={styles.nodeChips}>
        {disabled ? <span style={styles.disabledChip}>停用</span> : null}
        {guarded ? <span style={styles.guardedChip} title={guardedTitle}>需授權</span> : data.sideEffects.length ? <span style={styles.autoChip}>自動允許</span> : <span style={styles.readChip}>純讀</span>}
        {data.status ? <span style={styles.statusChip}>{statusLabel(data.status)}</span> : null}
        {data.decision ? <span style={styles.statusChip}>{decisionLabel(data.decision)}</span> : null}
      </div>
      {active ? <div style={styles.nodeActions}>
        <button disabled={!data.rerunEnabled || data.nodeType.startsWith("ui.")} onClick={(event) => { event.stopPropagation(); data.onRunNode?.(data.nodeId); }} style={styles.nodeActionButton} type="button">
          重跑此節點
        </button>
        <button disabled={!data.rerunEnabled} onClick={(event) => { event.stopPropagation(); data.onRunFrom?.(data.nodeId); }} style={styles.nodeActionButton} type="button">
          重跑下游
        </button>
      </div> : null}
    </div>
  );
}

function NodeSummary({ summary }: { summary?: NodeCardSummary }) {
  if (!summary) {
    return (
      <div style={styles.summaryBox}>
        <span style={styles.summaryPreview}>尚未執行</span>
      </div>
    );
  }
  const metrics = summary.metrics.slice(0, 2);
  return (
    <div style={styles.summaryBox}>
      <div style={styles.summaryBadges}>
        {summary.badges.slice(0, 3).map((badge) => (
          <span style={{ ...styles.summaryBadge, borderColor: toneColor(badge.tone), color: toneColor(badge.tone) }} key={`${badge.label}-${badge.tone ?? "idle"}`}>
            {badge.label}
          </span>
        ))}
      </div>
      {summary.preview ? <span style={styles.summaryPreview} title={summary.preview}>{summary.preview}</span> : null}
      {metrics.length ? (
        <div style={styles.summaryMetrics}>
          {metrics.map((metric) => (
            <span style={styles.summaryMetric} key={`${metric.label}-${metric.value}`}>
              <em>{metric.label}</em>
              <strong style={{ color: toneColor(metric.tone) }}>{metric.value}</strong>
            </span>
          ))}
        </div>
      ) : null}
      {typeof summary.progress === "number" ? (
        <div style={styles.summaryProgressTrack}>
          <span style={{ ...styles.summaryProgressFill, width: `${Math.max(0, Math.min(100, summary.progress))}%` }} />
        </div>
      ) : null}
    </div>
  );
}

function portTop(index: number, count: number): string {
  const start = count > 4 ? 76 : 92;
  return `${start + index * 18}px`;
}

function firstDecision(records: Array<{ decision?: string }>): string {
  return records.map((record) => record.decision || "").find(Boolean) || "";
}

function statusLabel(status: string) {
  if (status === "success") return "成功";
  if (status === "blocked") return "已阻擋";
  if (status === "failed") return "失敗";
  if (status === "skipped_disabled") return "停用";
  if (status === "not_run") return "未執行";
  return status;
}

function decisionLabel(decision: string) {
  if (decision === "executed") return "已執行";
  if (decision === "blocked_policy") return "政策阻擋";
  if (decision === "blocked_replay") return "回放阻擋";
  if (decision === "skipped_disabled") return "停用略過";
  if (decision === "skipped_dry_run") return "試算略過";
  if (decision === "simulated") return "模擬";
  return decision;
}

function stepNumber(nodeId: string): string {
  const order: Record<string, string> = {
    pdf_source: "1",
    discover: "2",
    split: "3",
    load_table: "4",
    roi_calib: "5",
    batch_detect: "6",
    pilot: "7",
    roi_dist: "8",
    export_csv: "9",
    apply_rename: "10",
  };
  return order[nodeId] ?? "";
}

function stageHint(nodeId: string): string {
  const hints: Record<string, string> = {
    pdf_source: "選擇 PDF / 資料夾",
    discover: "探索工作區",
    split: "拆成單頁",
    load_table: "讀取 ISO 清單",
    roi_calib: "調整 ROI / 門檻",
    batch_detect: "批次判讀",
    pilot: "檢查問題",
    roi_dist: "信心統計",
    export_csv: "匯出草稿",
    apply_rename: "套用前確認",
  };
  return hints[nodeId] ?? "節點";
}

function nodeToneStyle(tone: "auto" | "disabled" | "guarded" | "read") {
  if (tone === "disabled") {
    return { background: "rgba(18,22,20,0.92)", borderColor: "rgba(220,235,228,0.14)", color: "rgba(220,235,228,0.58)" };
  }
  if (tone === "guarded") {
    return { background: "rgba(60,24,26,0.86)", borderColor: "rgba(255,107,107,0.52)", color: "#ffe7e7" };
  }
  if (tone === "auto") {
    return { background: "rgba(54,43,18,0.84)", borderColor: "rgba(255,209,102,0.42)", color: "#fff4cf" };
  }
  return { background: "rgba(14,42,35,0.86)", borderColor: "rgba(47,245,200,0.42)", color: "#dffcf4" };
}

function toneColor(tone: NodeCardSummary["tone"]): string {
  if (tone === "danger") return "#ff9b9b";
  if (tone === "warn") return "#ffd166";
  if (tone === "ready") return "#2ff5c8";
  if (tone === "run") return "#7fd7ff";
  return "rgba(220,235,228,0.62)";
}

const styles = {
  autoChip: {
    border: "1px solid rgba(255,209,102,0.35)",
    borderRadius: 999,
    color: "#ffd166",
    fontSize: 10,
    padding: "2px 6px",
  },
  canvasShell: {
    border: "1px solid rgba(47,245,200,0.22)",
    borderRadius: 8,
    height: "clamp(680px, 72vh, 900px)",
    marginBottom: 10,
    minHeight: 620,
    overflow: "hidden",
    background: "rgba(3,10,8,0.74)",
    width: "100%",
  },
  disabledChip: {
    border: "1px solid rgba(220,235,228,0.22)",
    borderRadius: 999,
    color: "rgba(220,235,228,0.62)",
    fontSize: 10,
    padding: "2px 6px",
  },
  empty: {
    border: "1px dashed rgba(220,235,228,0.2)",
    borderRadius: 8,
    color: "rgba(220,235,228,0.62)",
    padding: 16,
  },
  guardedChip: {
    border: "1px solid rgba(255,107,107,0.48)",
    borderRadius: 999,
    color: "#ff9b9b",
    fontSize: 10,
    padding: "2px 6px",
  },
  handle: {
    background: "#2ff5c8",
    border: "0",
    height: 8,
    width: 8,
  },
  node: {
    border: "1px solid",
    borderRadius: 8,
    boxShadow: "0 14px 30px rgba(0,0,0,0.28)",
    minHeight: 192,
    padding: 11,
    position: "relative",
    width: 250,
  },
  nodeChips: {
    display: "flex",
    flexWrap: "wrap",
    gap: 5,
    marginTop: 8,
  },
  nodeActionButton: {
    background: "rgba(47,245,200,0.10)",
    border: "1px solid rgba(47,245,200,0.24)",
    borderRadius: 7,
    color: "#dffcf4",
    cursor: "pointer",
    fontSize: 10,
    fontWeight: 800,
    padding: "5px 7px",
  },
  nodeActions: {
    display: "grid",
    gap: 5,
    gridTemplateColumns: "1fr 1fr",
    marginTop: 8,
  },
  nodeHead: {
    alignItems: "center",
    display: "flex",
    gap: 7,
    justifyContent: "space-between",
    minWidth: 0,
  },
  nodeIcon: {
    display: "inline-flex",
    opacity: 0.78,
  },
  nodeHint: {
    color: "rgba(220,235,228,0.58)",
    fontSize: 10,
    fontStyle: "normal",
    fontWeight: 800,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  nodeName: {
    color: "inherit",
    fontSize: 14,
    lineHeight: 1.15,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  nodeTitle: {
    display: "grid",
    flex: 1,
    gap: 3,
    minWidth: 0,
  },
  portGrid: {
    display: "grid",
    gap: 10,
    gridTemplateColumns: "1fr 1fr",
    marginTop: 8,
    minHeight: 54,
    minWidth: 0,
  },
  portLabel: {
    background: "rgba(0,0,0,0.18)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 6,
    color: "rgba(220,235,228,0.72)",
    display: "block",
    fontSize: 10,
    lineHeight: 1.25,
    overflow: "hidden",
    padding: "3px 5px",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  portList: {
    display: "grid",
    gap: 4,
    minWidth: 0,
  },
  readChip: {
    border: "1px solid rgba(47,245,200,0.32)",
    borderRadius: 999,
    color: "#2ff5c8",
    fontSize: 10,
    padding: "2px 6px",
  },
  statusChip: {
    border: "1px solid rgba(127,215,255,0.28)",
    borderRadius: 999,
    color: "#7fd7ff",
    fontSize: 10,
    padding: "2px 6px",
  },
  dirtyNode: {
    borderColor: "rgba(255,209,102,0.78)",
    boxShadow: "0 0 0 1px rgba(255,209,102,0.18), 0 14px 30px rgba(0,0,0,0.28)",
  },
  summaryBadge: {
    border: "1px solid",
    borderRadius: 999,
    fontSize: 10,
    fontWeight: 800,
    padding: "2px 6px",
    whiteSpace: "nowrap",
  },
  summaryBadges: {
    display: "flex",
    flexWrap: "wrap",
    gap: 4,
  },
  summaryBox: {
    background: "rgba(0,0,0,0.16)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 8,
    display: "grid",
    gap: 5,
    marginTop: 8,
    minWidth: 0,
    padding: 7,
  },
  summaryMetric: {
    background: "rgba(255,255,255,0.035)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 7,
    display: "grid",
    gap: 2,
    minWidth: 0,
    padding: "5px 6px",
  },
  summaryMetrics: {
    display: "grid",
    gap: 5,
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    minWidth: 0,
  },
  summaryPreview: {
    color: "rgba(220,235,228,0.82)",
    fontSize: 11,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  summaryProgressFill: {
    background: "#2ff5c8",
    borderRadius: 999,
    display: "block",
    height: "100%",
  },
  summaryProgressTrack: {
    background: "rgba(255,255,255,0.14)",
    borderRadius: 999,
    height: 5,
    overflow: "hidden",
  },
  summaryRows: {
    display: "grid",
    gap: 4,
    minWidth: 0,
  },
  stepBadge: {
    alignItems: "center",
    background: "rgba(47,245,200,0.10)",
    border: "1px solid rgba(47,245,200,0.42)",
    borderRadius: 999,
    color: "#2ff5c8",
    display: "inline-flex",
    flex: "0 0 auto",
    fontSize: 12,
    fontWeight: 950,
    height: 26,
    justifyContent: "center",
    width: 26,
  },
} satisfies Record<string, CSSProperties>;
