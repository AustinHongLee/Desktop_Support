import { Background, Controls, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Lock, ShieldCheck } from "lucide-react";
import type { CSSProperties } from "react";
import { useMemo } from "react";
import type { IsoNodeWorkflowRunLog, IsoNodeWorkflowValidationPayload } from "../isoWorkflow";
import { buildWorkbenchGraph, type FlowNodeData, type FlowPort } from "./flowAdapter";

type CanvasNodeData = FlowNodeData & Record<string, unknown> & {
  decision: string;
  selected: boolean;
  status: string;
};

type CanvasNode = Node<CanvasNodeData, "isoNode">;

type WorkflowCanvasProps = {
  payload: IsoNodeWorkflowValidationPayload | null;
  runLog: IsoNodeWorkflowRunLog | null;
  selectedNodeId?: string;
  onSelectNode?: (nodeId: string) => void;
};

const guardedTitle = "guarded：需 CLI 三因子授權（--allow + --confirm + enabled）";

export function WorkflowCanvas({ payload, runLog, selectedNodeId = "", onSelectNode }: WorkflowCanvasProps) {
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
          selected: selectedNodeId === node.id,
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
      style: { stroke: "rgba(47,245,200,0.36)", strokeWidth: 1.4 },
    }));
    return { nodes, edges };
  }, [payload, runLog, selectedNodeId]);

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
  const inputPorts = data.inputPorts ?? [];
  const outputPorts = data.outputPorts ?? [];
  return (
    <div style={{ ...styles.node, ...nodeToneStyle(tone), outline: data.selected || selected ? "2px solid rgba(47,245,200,0.75)" : "0" }}>
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
        <span style={styles.nodeIcon}>{guarded ? <Lock size={13} /> : <ShieldCheck size={13} />}</span>
        <strong>{data.displayName}</strong>
      </div>
      <code style={styles.nodeType}>{data.nodeType}</code>
      <div style={styles.portGrid}>
        <PortList ports={inputPorts} align="left" />
        <PortList ports={outputPorts} align="right" />
      </div>
      <div style={styles.nodeChips}>
        {disabled ? <span style={styles.disabledChip}>停用</span> : null}
        {guarded ? <span style={styles.guardedChip} title={guardedTitle}>需授權</span> : data.sideEffects.length ? <span style={styles.autoChip}>自動允許</span> : <span style={styles.readChip}>純讀</span>}
        {data.status ? <span style={styles.statusChip}>{statusLabel(data.status)}</span> : null}
        {data.decision ? <span style={styles.statusChip}>{decisionLabel(data.decision)}</span> : null}
      </div>
    </div>
  );
}

function PortList({ align, ports }: { align: "left" | "right"; ports: FlowPort[] }) {
  if (!ports.length) {
    return <div style={styles.portList} />;
  }
  return (
    <div style={{ ...styles.portList, textAlign: align }}>
      {ports.map((port) => (
        <span style={styles.portLabel} key={port.name}>{port.label}</span>
      ))}
    </div>
  );
}

function portTop(index: number, count: number): string {
  const start = count > 4 ? 58 : 66;
  return `${start + index * 20}px`;
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
    height: "clamp(620px, 70vh, 860px)",
    marginBottom: 10,
    minHeight: 560,
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
    minHeight: 150,
    padding: 10,
    position: "relative",
    width: 260,
  },
  nodeChips: {
    display: "flex",
    flexWrap: "wrap",
    gap: 5,
    marginTop: 8,
  },
  nodeHead: {
    alignItems: "center",
    display: "flex",
    gap: 7,
    minWidth: 0,
  },
  nodeIcon: {
    display: "inline-flex",
  },
  nodeType: {
    color: "rgba(220,235,228,0.64)",
    display: "block",
    fontSize: 10,
    marginTop: 6,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  portGrid: {
    display: "grid",
    gap: 10,
    gridTemplateColumns: "1fr 1fr",
    marginTop: 10,
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
} satisfies Record<string, CSSProperties>;
