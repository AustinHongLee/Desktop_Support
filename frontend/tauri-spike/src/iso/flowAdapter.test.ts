import { describe, expect, it } from "vitest";
import type { IsoNodeWorkflowValidationPayload } from "../isoWorkflow";
import { assertFlowRoundTrip, flowToGraphPatch, graphToFlow } from "./flowAdapter";

describe("flowAdapter", () => {
  it("round-trips the safe POC graph payload without structural issues", () => {
    expect(assertFlowRoundTrip(safePocPayload)).toEqual([]);
  });

  it("lays out topology layers with monotonically increasing x positions", () => {
    const flow = graphToFlow(safePocPayload);
    const byId = new Map(flow.nodes.map((node) => [node.id, node]));

    expect(byId.get("discover")?.position.x).toBe(0);
    expect(byId.get("split")?.position.x).toBeGreaterThan(byId.get("discover")?.position.x ?? -1);
    expect(byId.get("batch_detect")?.position.x).toBeGreaterThan(byId.get("split")?.position.x ?? -1);
    expect(byId.get("pilot")?.position.x).toBeGreaterThan(byId.get("batch_detect")?.position.x ?? -1);
  });

  it("maps guarded and disabled node flags into node data and enabled patches", () => {
    const flow = graphToFlow(safePocPayload);
    const apply = flow.nodes.find((node) => node.id === "apply_rename");
    const patch = flowToGraphPatch(flow.nodes);

    expect(apply?.data.guarded).toBe(true);
    expect(apply?.data.requiresConfirm).toBe(true);
    expect(apply?.data.enabled).toBe(false);
    expect(patch.find((item) => item.node_id === "apply_rename")).toEqual({ node_id: "apply_rename", enabled: false });
  });
});

const safePocPayload = {
  schema_version: 1,
  action: "workflow_validate",
  created_at: "2026-06-10T00:00:00",
  workflow_path: "launcher/plugins/iso_tools/workflow/workflows/iso_pdf_safe_poc.workflow.json",
  workflow_id: "iso_pdf_safe_poc",
  valid: true,
  issues: [],
  topology: ["discover", "split", "batch_detect", "pilot", "apply_rename"],
  edges: [
    { from_node: "discover", from_output: "candidates", to_node: "split", to_input: "work_folder" },
    { from_node: "split", from_output: "page_folder", to_node: "batch_detect", to_input: "page_folder" },
    { from_node: "batch_detect", from_output: "rows", to_node: "pilot", to_input: "rows" },
    { from_node: "batch_detect", from_output: "result", to_node: "pilot", to_input: "plan" },
    { from_node: "batch_detect", from_output: "rows", to_node: "apply_rename", to_input: "rows" },
  ],
  graph: {
    schema_version: 1,
    workflow_id: "iso_pdf_safe_poc",
    display_name: "ISO PDF 安全節點流程 POC",
    inputs: {},
    nodes: [
      { node_id: "discover", node_type: "iso.discover_sources", display_name: "探索來源", inputs: {}, enabled: true },
      { node_id: "split", node_type: "iso.split_pdf", display_name: "拆頁 PDF", inputs: {}, enabled: true, side_effects: ["may_write_page_pdfs"] },
      {
        node_id: "batch_detect",
        node_type: "iso.batch_detect_serials",
        display_name: "批次判讀流水號",
        inputs: {},
        enabled: true,
        params: { wait_for_completion: true },
        side_effects: ["writes_job_files", "writes_iso_run_log", "spawns_worker"],
      },
      { node_id: "pilot", node_type: "iso.pilot_report", display_name: "Pilot 檢查", inputs: {}, enabled: true },
      {
        node_id: "apply_rename",
        node_type: "iso.apply_rename",
        display_name: "套用更名",
        inputs: {},
        enabled: false,
        requires_confirm: true,
        side_effects: ["renames_files"],
      },
    ],
  },
} satisfies IsoNodeWorkflowValidationPayload;
