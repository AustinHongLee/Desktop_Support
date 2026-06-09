import { invoke, isTauri } from "@tauri-apps/api/core";

export type IsoRowStatus = "ready" | "warn" | "blocked" | "idle";
export type IsoWorkflowAction =
  | "discover_sources"
  | "split_pdf"
  | "load_iso_table"
  | "plan"
  | "build_rename_plan"
  | "export_plan_csv"
  | "export_debug_bundle"
  | "pilot_report"
  | "list_run_logs"
  | "read_run_log"
  | "replay_run_log"
  | "start_batch_detect"
  | "job_status"
  | "cancel_job"
  | "apply"
  | "load_profile"
  | "save_profile"
  | "save_draft_profile"
  | "publish_profile"
  | "revert_profile";

export interface IsoRegion {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface IsoWorkflowRequest {
  action: IsoWorkflowAction;
  profile_folder?: string;
  work_folder?: string;
  combine_pdf?: string;
  page_folder?: string;
  iso_list?: string;
  sheet_name?: string;
  serial_col?: number | "";
  line_col?: number | "";
  pattern?: string;
  serial_region?: IsoRegion;
  drawing_region?: IsoRegion;
  confidence_threshold?: number;
  detect_serials?: boolean;
  export_path?: string;
  job_id?: string;
  run_id?: string;
  rows?: IsoPlanRow[];
}

export interface IsoRunLogRef {
  schema_version: number;
  run_id: string;
  run_dir: string;
  run_json: string;
  events_jsonl: string;
}

export interface IsoPreviewRequest {
  source_path: string;
  detect_serial?: boolean;
  serial_region?: IsoRegion;
  drawing_region?: IsoRegion;
}

export interface IsoPreviewPayload {
  schema_version: number;
  source_path: string;
  source_name: string;
  page: {
    width: number;
    height: number;
    image: string;
  };
  serial_crop: {
    region: Record<string, number>;
    image: string;
  };
  drawing_crop: {
    region: Record<string, number>;
    image: string;
  };
  vision: null | {
    text: string;
    confidence: number;
    message: string;
  };
}

export interface IsoPlanRow {
  id: string;
  page: number;
  source_path: string;
  source_name: string;
  serial: string;
  line_no: string;
  new_name: string;
  target_path: string;
  status: IsoRowStatus;
  selected: boolean;
  confidence: number;
  vision_message: string;
  note: string;
}

export interface IsoWorkflowIssue {
  code: string;
  tone: string;
  title: string;
  detail: string;
}

export type IsoPilotStatus = "pending" | "running" | "ready" | "warn" | "blocked" | "skipped";
export type IsoPilotFreshness = "fresh" | "stale";
export type IsoPilotView = "autopilot" | "workbench" | "engineer";

export interface IsoPilotNextAction {
  label: string;
  view: IsoPilotView;
  anchor?: string;
  row_ref?: string;
}

export interface IsoPilotItem {
  id: string;
  stage: string;
  status: IsoPilotStatus;
  user_text: string;
  engineer_detail: string;
  metrics: Record<string, unknown>;
  auto_fix: string;
  manual_hint: string;
  blocks_apply: boolean;
  issue_codes: string[];
  // schema v2 additive fields (optional so v1 run logs still parse)
  freshness?: IsoPilotFreshness;
  needs_review?: boolean;
  next_action?: IsoPilotNextAction | null;
}

export interface IsoPilotReport {
  schema_version: number;
  action: "pilot_report";
  created_at: string;
  summary: Record<IsoPilotItem["status"], number>;
  items: IsoPilotItem[];
  source?: IsoWorkflowPlan["source"];
  rows?: IsoPlanRow[];
}

export interface IsoWorkflowStep {
  label: string;
  state: string;
  meta: string;
}

export interface IsoWorkflowPlan {
  schema_version: number;
  action: "plan" | "build_rename_plan" | "batch_detect_result" | "replay_run_log";
  created_at: string;
  source: {
    kind: string;
    work_folder: string;
    combine_pdf: string;
    page_folder: string;
    pdf_count: number;
    iso_list: string;
    iso_candidates?: string[];
    sheet_name: string;
    sheet_options?: string[];
    headers?: string[];
    serial_col?: number;
    line_col?: number;
    record_count: number;
    pattern: string;
    detect_serials: boolean;
    profile?: IsoProfilePayload;
  };
  summary: {
    total: number;
    ready: number;
    warn: number;
    blocked: number;
    selected: number;
  };
  steps: IsoWorkflowStep[];
  rows: IsoPlanRow[];
  issues: IsoWorkflowIssue[];
  pilot_results?: IsoPilotItem[];
  pilot_summary?: Record<IsoPilotItem["status"], number>;
  run_log?: IsoRunLogRef;
  source_run_id?: string;
  replay_dry_run?: boolean;
  message?: string;
}

export interface IsoRunLogSummary {
  schema_version: number;
  run_id: string;
  run_type: string;
  action: string;
  status: string;
  created_at: string;
  updated_at: string;
  summary: Record<string, unknown>;
  failure?: {
    failed_stage?: string;
    user_summary?: string;
    error_message?: string;
  } | null;
  run_dir: string;
  run_json: string;
}

export interface IsoRunLogDetail {
  schema_version: number;
  action: "read_run_log";
  run: {
    run_id: string;
    action: string;
    status: string;
    created_at: string;
    updated_at: string;
    summary?: Record<string, unknown>;
    failure?: IsoRunLogSummary["failure"];
    pilot_results?: IsoPilotItem[];
    rows?: IsoPlanRow[];
    replay?: { action?: string; request?: Partial<IsoWorkflowRequest> };
  };
  events: Array<{ code?: string; tone?: string; title?: string; detail?: string; ts?: string }>;
  run_log: IsoRunLogRef;
}

export interface IsoRunLogListPayload {
  schema_version: number;
  action: "list_run_logs";
  created_at: string;
  runs: IsoRunLogSummary[];
}

export interface IsoProfilePayload {
  schema_version: number;
  action: "discover_sources" | "load_profile" | "save_profile" | "save_draft_profile" | "publish_profile" | "revert_profile";
  created_at: string;
  exists: boolean;
  profile_scope?: "published" | "draft";
  published_exists?: boolean;
  draft_exists?: boolean;
  history_count?: number;
  folder: string;
  folder_exists?: boolean;
  candidate_folders?: string[];
  serial_region: IsoRegion;
  drawing_region: IsoRegion;
  confidence_threshold: number;
  pattern: string;
  iso_list_path: string | null;
  sheet_name: string | null;
  serial_col: number | null;
  line_col: number | null;
  detected_combine_pdf: string | null;
  detected_page_folder: string | null;
  detected_page_folder_exists?: boolean;
  detected_iso_list: string | null;
  message: string;
}

export interface IsoSplitPayload {
  schema_version: number;
  action: "split_pdf";
  created_at: string;
  source: {
    kind: string;
    work_folder: string;
    combine_pdf: string;
    page_folder: string;
    pdf_count: number;
  };
  pages: Array<{
    page: number;
    source_path: string;
    source_name: string;
  }>;
  issues: IsoWorkflowIssue[];
}

export interface IsoTablePayload {
  schema_version: number;
  action: "load_iso_table";
  created_at: string;
  source: {
    work_folder: string;
    iso_list: string;
    iso_candidates?: string[];
    sheet_name: string;
    sheet_options?: string[];
    headers?: string[];
    serial_col?: number;
    line_col?: number;
    record_count: number;
    profile?: IsoProfilePayload;
  };
  sample_records: Array<{
    serial: string;
    line_no: string;
  }>;
  issues: IsoWorkflowIssue[];
}

export interface IsoExportResult {
  schema_version: number;
  action: "export_plan_csv";
  created_at: string;
  export_path: string;
  row_count: number;
  selected_count: number;
  message: string;
}

export interface IsoDebugBundleResult {
  schema_version: number;
  action: "export_debug_bundle";
  created_at: string;
  run_id: string;
  export_path: string;
  included_files: string[];
  message: string;
}

export interface IsoJobPayload {
  schema_version: number;
  action: "batch_detect_job";
  job_id: string;
  state: "queued" | "running" | "cancel_requested" | "cancelled" | "completed" | "failed";
  created_at: string;
  updated_at: string;
  progress: {
    total: number;
    done: number;
    percent: number;
  };
  rows: IsoPlanRow[];
  issues: IsoWorkflowIssue[];
  events: IsoWorkflowIssue[];
  result: IsoWorkflowPlan | null;
  error: string;
  run_id?: string;
  run_log?: IsoRunLogRef;
}

export interface IsoApplyResult {
  schema_version: number;
  action: "apply";
  created_at: string;
  renamed_count: number;
  message: string;
  rows: Array<{
    source_path: string;
    target_path: string;
    source_name: string;
    target_name: string;
  }>;
  run_log?: IsoRunLogRef;
}

export async function pickIsoCombinePdf(): Promise<string> {
  return pickPath("pick_iso_combine_pdf");
}

export async function pickIsoWorkFolder(): Promise<string> {
  return pickPath("pick_iso_work_folder");
}

export async function pickIsoListFile(): Promise<string> {
  return pickPath("pick_iso_list_file");
}

export async function pickIsoPageFolder(): Promise<string> {
  return pickPath("pick_iso_page_folder");
}

export async function runIsoPlan(request: IsoWorkflowRequest): Promise<IsoWorkflowPlan> {
  return invokeJson<IsoWorkflowPlan>("run_iso_workflow", { ...request, action: "plan" });
}

export async function buildIsoRenamePlan(request: IsoWorkflowRequest): Promise<IsoWorkflowPlan> {
  return invokeJson<IsoWorkflowPlan>("run_iso_workflow", { ...request, action: "build_rename_plan" });
}

export async function applyIsoPlan(request: IsoWorkflowRequest): Promise<IsoApplyResult> {
  return invokeJson<IsoApplyResult>("run_iso_workflow", { ...request, action: "apply" });
}

export async function discoverIsoSources(request: Partial<IsoWorkflowRequest>): Promise<IsoProfilePayload> {
  return invokeJson<IsoProfilePayload>("run_iso_workflow", { ...request, action: "discover_sources" });
}

export async function splitIsoPdf(request: Partial<IsoWorkflowRequest>): Promise<IsoSplitPayload> {
  return invokeJson<IsoSplitPayload>("run_iso_workflow", { ...request, action: "split_pdf" });
}

export async function loadIsoTable(request: Partial<IsoWorkflowRequest>): Promise<IsoTablePayload> {
  return invokeJson<IsoTablePayload>("run_iso_workflow", { ...request, action: "load_iso_table" });
}

export async function exportIsoPlanCsv(request: Partial<IsoWorkflowRequest>): Promise<IsoExportResult> {
  return invokeJson<IsoExportResult>("run_iso_workflow", { ...request, action: "export_plan_csv" });
}

export async function exportIsoDebugBundle(request: Pick<IsoWorkflowRequest, "run_id" | "export_path">): Promise<IsoDebugBundleResult> {
  return invokeJson<IsoDebugBundleResult>("run_iso_workflow", { ...request, action: "export_debug_bundle" });
}

export async function loadIsoPilotReport(request: Partial<IsoWorkflowRequest>): Promise<IsoPilotReport> {
  return invokeJson<IsoPilotReport>("run_iso_workflow", { ...request, action: "pilot_report" });
}

export async function listIsoRunLogs(): Promise<IsoRunLogListPayload> {
  return invokeJson<IsoRunLogListPayload>("run_iso_workflow", { action: "list_run_logs" });
}

export async function readIsoRunLog(runId: string): Promise<IsoRunLogDetail> {
  return invokeJson<IsoRunLogDetail>("run_iso_workflow", { action: "read_run_log", run_id: runId });
}

export async function replayIsoRunLog(runId: string): Promise<IsoWorkflowPlan> {
  return invokeJson<IsoWorkflowPlan>("run_iso_workflow", { action: "replay_run_log", run_id: runId });
}

export async function startIsoBatchDetect(request: Partial<IsoWorkflowRequest>): Promise<IsoJobPayload> {
  return invokeJson<IsoJobPayload>("run_iso_workflow", { ...request, action: "start_batch_detect" });
}

export async function loadIsoJobStatus(jobId: string): Promise<IsoJobPayload> {
  return invokeJson<IsoJobPayload>("run_iso_workflow", { action: "job_status", job_id: jobId });
}

export async function cancelIsoJob(jobId: string): Promise<IsoJobPayload> {
  return invokeJson<IsoJobPayload>("run_iso_workflow", { action: "cancel_job", job_id: jobId });
}

export async function loadIsoProfile(request: Partial<IsoWorkflowRequest>): Promise<IsoProfilePayload> {
  return invokeJson<IsoProfilePayload>("run_iso_workflow", { ...request, action: "load_profile" });
}

export async function saveIsoProfile(request: Partial<IsoWorkflowRequest>): Promise<IsoProfilePayload> {
  return invokeJson<IsoProfilePayload>("run_iso_workflow", { ...request, action: "save_profile" });
}

export async function saveIsoDraftProfile(request: Partial<IsoWorkflowRequest>): Promise<IsoProfilePayload> {
  return invokeJson<IsoProfilePayload>("run_iso_workflow", { ...request, action: "save_draft_profile" });
}

export async function publishIsoProfile(request: Partial<IsoWorkflowRequest>): Promise<IsoProfilePayload> {
  return invokeJson<IsoProfilePayload>("run_iso_workflow", { ...request, action: "publish_profile" });
}

export async function revertIsoProfile(request: Partial<IsoWorkflowRequest>): Promise<IsoProfilePayload> {
  return invokeJson<IsoProfilePayload>("run_iso_workflow", { ...request, action: "revert_profile" });
}

export async function loadIsoPreview(request: IsoPreviewRequest): Promise<IsoPreviewPayload> {
  if (!isTauri()) {
    throw new Error("請用 Tauri 桌面版預覽 PDF。");
  }
  const payload = await invoke<string>("preview_iso_pdf_page", { request: JSON.stringify(request) });
  return JSON.parse(payload) as IsoPreviewPayload;
}

async function pickPath(command: string): Promise<string> {
  if (!isTauri()) {
    throw new Error("請用 Tauri 桌面版選取本機路徑。");
  }
  return (await invoke<string | null>(command)) ?? "";
}

async function invokeJson<T>(command: string, request: Partial<IsoWorkflowRequest>): Promise<T> {
  if (!isTauri()) {
    throw new Error("請用 Tauri 桌面版執行 ISO workflow。");
  }
  const payload = await invoke<string>(command, { request: JSON.stringify(request) });
  return JSON.parse(payload) as T;
}
