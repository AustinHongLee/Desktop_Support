import { describe, expect, it } from "vitest";
import type { IsoNodeWorkflowValidationPayload } from "../isoWorkflow";
import { assertFlowRoundTrip, buildWorkbenchGraph, flowToGraphPatch, graphToFlow } from "./flowAdapter";

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
    const exportCsv = flow.nodes.find((node) => node.id === "export_csv");
    const patch = flowToGraphPatch(flow.nodes);

    expect(apply?.data.guarded).toBe(true);
    expect(apply?.data.requiresConfirm).toBe(true);
    expect(apply?.data.enabled).toBe(false);
    expect(exportCsv?.data.guarded).toBe(true);
    expect(exportCsv?.data.requiresConfirm).toBe(true);
    expect(exportCsv?.data.enabled).toBe(false);
    expect(patch.find((item) => item.node_id === "apply_rename")).toEqual({ node_id: "apply_rename", enabled: false });
    expect(patch.find((item) => item.node_id === "export_csv")).toEqual({ node_id: "export_csv", enabled: false });
  });

  it("builds the workbench presentation graph with synthetic nodes and port wiring", () => {
    const flow = buildWorkbenchGraph(safePocPayload);
    const byId = new Map(flow.nodes.map((node) => [node.id, node]));
    const edgeIds = new Set(flow.edges.map((edge) => edge.id));

    expect(byId.get("pdf_source")?.data.outputPorts.map((port) => port.name)).toEqual(["combine_pdf", "work_folder", "page_folder_hint"]);
    expect(byId.get("roi_calib")?.data.outputPorts.map((port) => port.name)).toContain("confidence_threshold");
    expect(byId.get("batch_detect")?.data.inputPorts.map((port) => port.name)).toEqual([
      "pages",
      "iso_rows",
      "serial_region",
      "drawing_region",
      "confidence_threshold",
      "detect_serials",
      "pattern",
    ]);

    expect(edgeIds).toContain("pdf_source:combine_pdf->split:combine_pdf");
    expect(edgeIds).toContain("split:pages->batch_detect:pages");
    expect(edgeIds).toContain("load_table:iso_rows->batch_detect:iso_rows");
    expect(edgeIds).toContain("roi_calib:serial_region->batch_detect:serial_region");
    expect(edgeIds).toContain("batch_detect:rows->pilot:rows");
    expect(edgeIds).toContain("batch_detect:rows->apply_rename:rows");
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
  topology: ["discover", "split", "load_table", "batch_detect", "pilot", "roi_dist", "export_csv", "apply_rename"],
  edges: [
    { from_node: "discover", from_output: "candidates", to_node: "split", to_input: "work_folder" },
    { from_node: "split", from_output: "page_folder", to_node: "batch_detect", to_input: "page_folder" },
    { from_node: "batch_detect", from_output: "rows", to_node: "pilot", to_input: "rows" },
    { from_node: "batch_detect", from_output: "result", to_node: "pilot", to_input: "plan" },
    { from_node: "batch_detect", from_output: "rows", to_node: "roi_dist", to_input: "rows" },
    { from_node: "batch_detect", from_output: "rows", to_node: "export_csv", to_input: "rows" },
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
      { node_id: "load_table", node_type: "iso.load_iso_table", display_name: "載入 ISO List", inputs: {}, enabled: true },
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
      { node_id: "roi_dist", node_type: "iso.roi_distribution", display_name: "ROI 信心分布", inputs: {}, enabled: true },
      {
        node_id: "export_csv",
        node_type: "iso.export_plan_csv",
        display_name: "匯出命名草稿 CSV",
        inputs: {},
        enabled: false,
        requires_confirm: true,
        side_effects: ["writes_csv"],
      },
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
