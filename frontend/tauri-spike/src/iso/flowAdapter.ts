import type { IsoNodeWorkflowEdge, IsoNodeWorkflowInstance, IsoNodeWorkflowValidationPayload } from "../isoWorkflow";

export interface FlowNodeData {
  nodeType: string;
  displayName: string;
  enabled: boolean;
  guarded: boolean;
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
        guarded: requiresConfirm || sideEffects.some((effect) => ["renames_files", "writes_profile", "writes_csv"].includes(effect)),
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
