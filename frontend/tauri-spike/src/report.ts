import { invoke, isTauri } from "@tauri-apps/api/core";

export type SafeToKill = "Safe" | "Caution" | "Dangerous" | "Unknown";

export interface FileRelationship {
  relation: string;
  source: string;
  target: string;
  job_id?: string;
  component?: string;
  note?: string;
}

export interface ShutdownBlocker {
  id: string;
  pid: number;
  process_name: string;
  parent_pid: number;
  command_summary: string;
  command_line: string;
  executable_path: string;
  started_at: string;
  job_id: string;
  component: string;
  process_role: string;
  safe_to_kill: SafeToKill;
  reasons: string[];
  lock_files: string[];
  temp_dirs: string[];
  input_files: string[];
  output_files: string[];
  log_files: string[];
  relationships: FileRelationship[];
  child_pids: number[];
  parent_process: string;
  kill_consequence: string[];
  suggested_actions: string[];
  project_owned: boolean;
  command_line_contains_project_root: boolean;
  can_automatically_stop: boolean;
}

export interface ShutdownSafetyReport {
  schema_version: number;
  project_root: string;
  scan_reason: string;
  created_at: string;
  blocker_count: number;
  blockers: ShutdownBlocker[];
  stale_locks_removed: string[];
  report_path: string;
}

export async function loadShutdownReport(): Promise<{ report: ShutdownSafetyReport; source: "tauri" | "sample" }> {
  if (isTauriRuntime()) {
    const payload = await invoke<string>("scan_shutdown_safety");
    return { report: normalizeReport(JSON.parse(payload)), source: "tauri" };
  }

  const response = await fetch("/sample-shutdown-report.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Sample report failed: ${response.status}`);
  }
  return { report: normalizeReport(await response.json()), source: "sample" };
}

export function normalizeReport(value: unknown): ShutdownSafetyReport {
  const payload = value as Partial<ShutdownSafetyReport>;
  const blockers = Array.isArray(payload.blockers) ? payload.blockers.map(normalizeBlocker) : [];
  return {
    schema_version: Number(payload.schema_version ?? 1),
    project_root: String(payload.project_root ?? ""),
    scan_reason: String(payload.scan_reason ?? ""),
    created_at: String(payload.created_at ?? ""),
    blocker_count: Number(payload.blocker_count ?? blockers.length),
    blockers,
    stale_locks_removed: toStrings(payload.stale_locks_removed),
    report_path: String(payload.report_path ?? ""),
  };
}

function normalizeBlocker(value: unknown): ShutdownBlocker {
  const payload = value as Partial<ShutdownBlocker>;
  return {
    id: String(payload.id ?? `process:${payload.pid ?? ""}`),
    pid: Number(payload.pid ?? 0),
    process_name: String(payload.process_name ?? ""),
    parent_pid: Number(payload.parent_pid ?? 0),
    command_summary: String(payload.command_summary ?? ""),
    command_line: String(payload.command_line ?? ""),
    executable_path: String(payload.executable_path ?? ""),
    started_at: String(payload.started_at ?? ""),
    job_id: String(payload.job_id ?? ""),
    component: String(payload.component ?? ""),
    process_role: String(payload.process_role ?? "Unknown but project-owned"),
    safe_to_kill: safeLevel(payload.safe_to_kill),
    reasons: toStrings(payload.reasons),
    lock_files: toStrings(payload.lock_files),
    temp_dirs: toStrings(payload.temp_dirs),
    input_files: toStrings(payload.input_files),
    output_files: toStrings(payload.output_files),
    log_files: toStrings(payload.log_files),
    relationships: Array.isArray(payload.relationships) ? payload.relationships.map(normalizeRelationship) : [],
    child_pids: Array.isArray(payload.child_pids) ? payload.child_pids.map((item) => Number(item)).filter(Number.isFinite) : [],
    parent_process: String(payload.parent_process ?? ""),
    kill_consequence: toStrings(payload.kill_consequence),
    suggested_actions: toStrings(payload.suggested_actions),
    project_owned: Boolean(payload.project_owned ?? true),
    command_line_contains_project_root: Boolean(payload.command_line_contains_project_root ?? false),
    can_automatically_stop: Boolean(payload.can_automatically_stop ?? false),
  };
}

function normalizeRelationship(value: unknown): FileRelationship {
  const payload = value as Partial<FileRelationship>;
  return {
    relation: String(payload.relation ?? "depends_on"),
    source: String(payload.source ?? ""),
    target: String(payload.target ?? ""),
    job_id: String(payload.job_id ?? ""),
    component: String(payload.component ?? ""),
    note: String(payload.note ?? ""),
  };
}

function safeLevel(value: unknown): SafeToKill {
  return value === "Safe" || value === "Caution" || value === "Dangerous" || value === "Unknown" ? value : "Unknown";
}

function toStrings(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => String(item)).filter(Boolean);
}

function isTauriRuntime(): boolean {
  return isTauri();
}
