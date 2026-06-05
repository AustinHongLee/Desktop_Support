import { invoke, isTauri } from "@tauri-apps/api/core";

export type IsoRowStatus = "ready" | "warn" | "blocked" | "idle";
export type IsoWorkflowAction =
  | "discover_sources"
  | "split_pdf"
  | "load_iso_table"
  | "plan"
  | "build_rename_plan"
  | "export_plan_csv"
  | "apply"
  | "load_profile"
  | "save_profile";

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
  rows?: IsoPlanRow[];
}

export interface IsoPreviewRequest {
  source_path: string;
  detect_serial?: boolean;
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

export interface IsoWorkflowStep {
  label: string;
  state: string;
  meta: string;
}

export interface IsoWorkflowPlan {
  schema_version: number;
  action: "plan" | "build_rename_plan";
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
}

export interface IsoProfilePayload {
  schema_version: number;
  action: "discover_sources" | "load_profile" | "save_profile";
  created_at: string;
  exists: boolean;
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

export async function loadIsoProfile(request: Partial<IsoWorkflowRequest>): Promise<IsoProfilePayload> {
  return invokeJson<IsoProfilePayload>("run_iso_workflow", { ...request, action: "load_profile" });
}

export async function saveIsoProfile(request: Partial<IsoWorkflowRequest>): Promise<IsoProfilePayload> {
  return invokeJson<IsoProfilePayload>("run_iso_workflow", { ...request, action: "save_profile" });
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
