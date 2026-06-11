import type { IsoNodeWorkflowEdge, IsoNodeWorkflowInstance, IsoNodeWorkflowValidationPayload } from "../isoWorkflow";

export interface FlowPort {
  name: string;
  label: string;
}

export interface FlowNodeData {
  nodeType: string;
  displayName: string;
  enabled: boolean;
  guarded: boolean;
  inputPorts: FlowPort[];
  outputPorts: FlowPort[];
  requiresConfirm: boolean;
  sideEffects: string[];
  params: Record<string, unknown>;
}

export interface FlowNode {
  id: string;
  position: { x: number; y: number };
  data: FlowNodeData;
  type: "isoNode";
}

export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle: string;
  targetHandle: string;
}

const GUARDED_EFFECTS = ["renames_files", "writes_profile", "writes_csv"];

export function graphToFlow(payload: IsoNodeWorkflowValidationPayload): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const graphNodes = payload.graph?.nodes ?? [];
  const edges = payload.edges ?? [];
  const layers = computeLayers(graphNodes, edges, payload.topology ?? []);
  const layerCounts = new Map<number, number>();
  const nodes = graphNodes.map((node) => {
    const layer = layers.get(node.node_id) ?? 0;
    const indexInLayer = layerCounts.get(layer) ?? 0;
    layerCounts.set(layer, indexInLayer + 1);
    const sideEffects = [...(node.side_effects ?? [])];
    const requiresConfirm = Boolean(node.requires_confirm);
    return {
      id: node.node_id,
      position: { x: layer * 280, y: indexInLayer * 120 },
      data: {
        nodeType: node.node_type,
        displayName: node.display_name || node.node_id,
        enabled: node.enabled !== false,
        guarded: requiresConfirm || sideEffects.some((effect) => GUARDED_EFFECTS.includes(effect)),
        inputPorts: portSpecsForNode(node).inputs,
        outputPorts: portSpecsForNode(node).outputs,
        requiresConfirm,
        sideEffects,
        params: { ...(node.params ?? {}) },
      },
      type: "isoNode" as const,
    };
  });
  return {
    nodes,
    edges: edges.map((edge) => ({
      id: `${edge.from_node}:${edge.from_output}->${edge.to_node}:${edge.to_input}`,
      source: edge.from_node,
      target: edge.to_node,
      sourceHandle: edge.from_output,
      targetHandle: edge.to_input,
    })),
  };
}

export function buildWorkbenchGraph(payload: IsoNodeWorkflowValidationPayload): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const engineNodes = payload.graph?.nodes ?? [];
  const nodeById = new Map(engineNodes.map((node) => [node.node_id, node] as const));
  const nodes: FlowNode[] = [
    syntheticNode("pdf_source", "ui.pdf_source", "PDF 來源", { x: 0, y: 350 }, [], ["combine_pdf", "work_folder", "page_folder_hint"]),
    ...engineNodes.map((node) => flowNodeForWorkbench(node, workbenchPosition(node))),
    syntheticNode(
      "roi_calib",
      "ui.roi_calibration",
      "ROI 調校",
      { x: 420, y: 690 },
      ["page_sample"],
      ["serial_region", "drawing_region", "confidence_threshold", "detect_serials", "pattern"],
    ),
  ];
  const edges = [
    edge("pdf_source", "work_folder", "discover", "work_folder", nodeById),
    edge("pdf_source", "combine_pdf", "split", "combine_pdf", nodeById),
    edge("pdf_source", "work_folder", "split", "work_folder", nodeById),
    edge("pdf_source", "page_folder_hint", "split", "page_folder", nodeById),
    edge("pdf_source", "work_folder", "load_table", "work_folder", nodeById),
    edge("split", "pages", "roi_calib", "page_sample", nodeById, true),
    edge("split", "pages", "batch_detect", "pages", nodeById),
    edge("load_table", "iso_rows", "batch_detect", "iso_rows", nodeById),
    edge("roi_calib", "serial_region", "batch_detect", "serial_region", nodeById, true),
    edge("roi_calib", "drawing_region", "batch_detect", "drawing_region", nodeById, true),
    edge("roi_calib", "confidence_threshold", "batch_detect", "confidence_threshold", nodeById, true),
    edge("roi_calib", "detect_serials", "batch_detect", "detect_serials", nodeById, true),
    edge("roi_calib", "pattern", "batch_detect", "pattern", nodeById, true),
    edge("batch_detect", "rows", "pilot", "rows", nodeById),
    edge("batch_detect", "rows", "roi_dist", "rows", nodeById),
    edge("roi_calib", "confidence_threshold", "roi_dist", "confidence_threshold", nodeById, true),
    edge("batch_detect", "rows", "export_csv", "rows", nodeById),
    edge("batch_detect", "rows", "apply_rename", "rows", nodeById),
  ].filter((item): item is FlowEdge => Boolean(item));
  return { nodes, edges };
}

export function flowToGraphPatch(nodes: FlowNode[]): Array<{ node_id: string; enabled: boolean }> {
  return nodes.map((node) => ({ node_id: node.id, enabled: node.data.enabled }));
}

export function assertFlowRoundTrip(payload: IsoNodeWorkflowValidationPayload): string[] {
  const issues: string[] = [];
  const sourceNodes = payload.graph?.nodes ?? [];
  const flow = graphToFlow(payload);
  if (flow.nodes.length !== sourceNodes.length) {
    issues.push(`node count mismatch: ${flow.nodes.length} != ${sourceNodes.length}`);
  }
  const ids = new Set(flow.nodes.map((node) => node.id));
  for (const edge of flow.edges) {
    if (!ids.has(edge.source)) {
      issues.push(`edge source missing: ${edge.id}`);
    }
    if (!ids.has(edge.target)) {
      issues.push(`edge target missing: ${edge.id}`);
    }
  }
  const patchById = new Map(flowToGraphPatch(flow.nodes).map((item) => [item.node_id, item.enabled]));
  for (const node of sourceNodes) {
    if (patchById.get(node.node_id) !== (node.enabled !== false)) {
      issues.push(`enabled patch mismatch: ${node.node_id}`);
    }
  }
  return issues;
}

function flowNodeForWorkbench(node: IsoNodeWorkflowInstance, position: { x: number; y: number }): FlowNode {
  const sideEffects = [...(node.side_effects ?? [])];
  const requiresConfirm = Boolean(node.requires_confirm);
  const ports = portSpecsForNode(node);
  return {
    id: node.node_id,
    position,
    data: {
      nodeType: node.node_type,
      displayName: node.display_name || node.node_id,
      enabled: node.enabled !== false,
      guarded: requiresConfirm || sideEffects.some((effect) => GUARDED_EFFECTS.includes(effect)),
      inputPorts: ports.inputs,
      outputPorts: ports.outputs,
      requiresConfirm,
      sideEffects,
      params: { ...(node.params ?? {}) },
    },
    type: "isoNode",
  };
}

function syntheticNode(
  id: string,
  nodeType: string,
  displayName: string,
  position: { x: number; y: number },
  inputs: string[],
  outputs: string[],
): FlowNode {
  return {
    id,
    position,
    data: {
      nodeType,
      displayName,
      enabled: true,
      guarded: false,
      inputPorts: inputs.map(port),
      outputPorts: outputs.map(port),
      requiresConfirm: false,
      sideEffects: [],
      params: {},
    },
    type: "isoNode",
  };
}

function workbenchPosition(node: IsoNodeWorkflowInstance): { x: number; y: number } {
  const positions: Record<string, { x: number; y: number }> = {
    discover: { x: 420, y: 30 },
    split: { x: 420, y: 250 },
    load_table: { x: 420, y: 470 },
    batch_detect: { x: 840, y: 350 },
    pilot: { x: 1260, y: 30 },
    roi_dist: { x: 1260, y: 250 },
    export_csv: { x: 1260, y: 470 },
    apply_rename: { x: 1260, y: 690 },
  };
  return positions[node.node_id] ?? { x: 840, y: 690 };
}

function edge(
  source: string,
  sourcePort: string,
  target: string,
  targetPort: string,
  nodeById: Map<string, IsoNodeWorkflowInstance>,
  targetSynthetic = false,
): FlowEdge | null {
  if (!nodeById.has(source) && source !== "pdf_source" && source !== "roi_calib") {
    return null;
  }
  if (!nodeById.has(target) && !(targetSynthetic && target === "roi_calib")) {
    return null;
  }
  return {
    id: `${source}:${sourcePort}->${target}:${targetPort}`,
    source,
    sourceHandle: sourcePort,
    target,
    targetHandle: targetPort,
  };
}

function portSpecsForNode(node: IsoNodeWorkflowInstance): { inputs: FlowPort[]; outputs: FlowPort[] } {
  const known = KNOWN_NODE_PORTS[node.node_type] ?? { inputs: Object.keys(node.inputs ?? {}), outputs: Object.keys(node.outputs ?? {}) };
  return {
    inputs: known.inputs.map(port),
    outputs: known.outputs.map(port),
  };
}

function port(name: string): FlowPort {
  return { name, label: PORT_LABELS[name] ?? name };
}

function computeLayers(nodes: IsoNodeWorkflowInstance[], edges: IsoNodeWorkflowEdge[], topology: string[]): Map<string, number> {
  const layerByNode = new Map<string, number>();
  const incoming = new Map<string, IsoNodeWorkflowEdge[]>();
  for (const edge of edges) {
    const list = incoming.get(edge.to_node) ?? [];
    list.push(edge);
    incoming.set(edge.to_node, list);
  }
  const order = topology.length ? topology : nodes.map((node) => node.node_id);
  for (const nodeId of order) {
    const parents = incoming.get(nodeId) ?? [];
    const layer = parents.reduce((max, edge) => Math.max(max, (layerByNode.get(edge.from_node) ?? 0) + 1), 0);
    layerByNode.set(nodeId, layer);
  }
  return layerByNode;
}

const KNOWN_NODE_PORTS: Record<string, { inputs: string[]; outputs: string[] }> = {
  "iso.discover_sources": {
    inputs: ["work_folder"],
    outputs: ["profile", "candidates", "folder"],
  },
  "iso.split_pdf": {
    inputs: ["combine_pdf", "work_folder", "page_folder"],
    outputs: ["page_folder", "pages", "pdf_count", "source_kind"],
  },
  "iso.load_iso_table": {
    inputs: ["work_folder", "iso_list", "sheet_name", "serial_col", "line_col"],
    outputs: ["iso_rows", "iso_source", "sample_records", "record_count"],
  },
  "iso.batch_detect_serials": {
    inputs: ["pages", "iso_rows", "serial_region", "drawing_region", "confidence_threshold", "detect_serials", "pattern"],
    outputs: ["rows", "job", "iso_run_log"],
  },
  "iso.pilot_report": {
    inputs: ["rows"],
    outputs: ["pilot_results", "pilot_summary"],
  },
  "iso.roi_distribution": {
    inputs: ["rows", "confidence_threshold"],
    outputs: ["distribution"],
  },
  "iso.export_plan_csv": {
    inputs: ["rows"],
    outputs: ["csv_path"],
  },
  "iso.apply_rename": {
    inputs: ["rows"],
    outputs: ["rename_result"],
  },
};

const PORT_LABELS: Record<string, string> = {
  candidates: "候選",
  combine_pdf: "合併 PDF",
  confidence_threshold: "門檻",
  csv_path: "CSV",
  detect_serials: "判讀",
  drawing_region: "圖號 ROI",
  folder: "資料夾",
  iso_rows: "ISO rows",
  iso_run_log: "ISO log",
  iso_source: "ISO 來源",
  job: "job",
  page_folder: "頁資料夾",
  page_folder_hint: "頁資料夾",
  page_sample: "頁樣本",
  pages: "pages",
  pattern: "格式",
  pdf_count: "頁數",
  pilot_results: "P01-P15",
  pilot_summary: "摘要",
  profile: "設定",
  record_count: "列數",
  rename_result: "更名結果",
  rows: "rows",
  sample_records: "樣本列",
  serial_region: "流水號 ROI",
  sheet_name: "工作表",
  source_kind: "來源",
  work_folder: "工作資料夾",
};
