import type {
  IsoPilotItem,
  IsoPilotNextAction,
  IsoPlanRow,
  IsoRegion,
  IsoRowStatus,
  IsoRunLogSummary,
  IsoWorkflowPlan,
} from "../isoWorkflow";

export type IsoSortMode = "page" | "status" | "confidence" | "filename";

export const DEFAULT_SERIAL_REGION: IsoRegion = { left: 0.62, top: 0, width: 0.38, height: 0.24 };
export const DEFAULT_DRAWING_REGION: IsoRegion = { left: 0.5, top: 0.66, width: 0.5, height: 0.34 };

const ISO_STATUS_ORDER: Record<IsoRowStatus, number> = {
  blocked: 0,
  warn: 1,
  ready: 2,
  idle: 3,
};

export function compactPath(path: string): string {
  const parts = path.replace(/\//g, "\\").split("\\").filter(Boolean);
  if (parts.length <= 3) {
    return path;
  }
  return `...\\${parts.slice(-3).join("\\")}`;
}

export function filterIsoRows(rows: IsoPlanRow[], searchTerm: string, problemOnly: boolean): IsoPlanRow[] {
  const terms = searchTerm.toLowerCase().split(/\s+/).filter(Boolean);
  return rows.filter((row) => {
    if (problemOnly && row.status !== "blocked" && row.status !== "warn") {
      return false;
    }
    if (!terms.length) {
      return true;
    }
    const text = [
      row.source_name,
      row.serial,
      row.line_no,
      row.new_name,
      row.status,
      isoIssueKind(row),
      row.note,
      row.vision_message,
    ].join(" ").toLowerCase();
    return terms.every((term) => text.includes(term));
  });
}

export function sortIsoRows(rows: IsoPlanRow[], sortMode: IsoSortMode): IsoPlanRow[] {
  const copy = [...rows];
  if (sortMode === "status") {
    return copy.sort((a, b) => ISO_STATUS_ORDER[a.status] - ISO_STATUS_ORDER[b.status] || a.page - b.page);
  }
  if (sortMode === "confidence") {
    return copy.sort((a, b) => (a.confidence || 0) - (b.confidence || 0) || a.page - b.page);
  }
  if (sortMode === "filename") {
    return copy.sort((a, b) => (a.new_name || a.source_name).localeCompare(b.new_name || b.source_name) || a.page - b.page);
  }
  return copy.sort((a, b) => a.page - b.page);
}

export function isoIssueKind(row: IsoPlanRow): string {
  const note = `${row.note} ${row.vision_message}`.toLowerCase();
  if (row.vision_message.includes("manual")) {
    return "manual-corrected";
  }
  if (!row.serial.trim()) {
    return "missing-serial";
  }
  if (!row.line_no.trim()) {
    return "missing-line";
  }
  if (note.includes("重複") || note.includes("duplicate")) {
    return "duplicate";
  }
  if (row.confidence > 0 && row.confidence < 0.7) {
    return "low-confidence";
  }
  if (row.status === "blocked") {
    return "blocked-issue";
  }
  if (row.status === "warn") {
    return "review-issue";
  }
  return "normal";
}

export function isoIssueLabel(row: IsoPlanRow): string {
  const kind = isoIssueKind(row);
  if (kind === "manual-corrected") return "手動修正";
  if (kind === "missing-serial") return "缺流水號";
  if (kind === "missing-line") return "缺 ISO 對應";
  if (kind === "duplicate") return "重複";
  if (kind === "low-confidence") return "低信心";
  if (kind === "blocked-issue") return "需處理";
  if (kind === "review-issue") return "待確認";
  return row.status === "ready" ? "通過" : row.status === "warn" ? "待確認" : row.status === "blocked" ? "需處理" : "未變更";
}

export function normalizeIsoRows(rows: IsoPlanRow[]): IsoPlanRow[] {
  const nameCounts = new Map<string, number>();
  for (const row of rows) {
    const key = row.new_name.trim().toLowerCase();
    if (key) {
      nameCounts.set(key, (nameCounts.get(key) ?? 0) + 1);
    }
  }
  return rows.map((row) => {
    const newName = row.new_name.trim();
    const nameProblem = filenameProblem(newName);
    let status: IsoPlanRow["status"] = "ready";
    let note = row.note === "manual edit" ? "" : row.note;
    if (!newName) {
      status = "blocked";
      note = "缺少命名";
    } else if (nameProblem) {
      status = "blocked";
      note = nameProblem;
    } else if ((nameCounts.get(newName.toLowerCase()) ?? 0) > 1) {
      status = "blocked";
      note = `目標檔名重複：${newName}`;
    } else if (newName === row.source_name) {
      status = "idle";
      note = "檔名已相同";
    } else if (!row.line_no.trim()) {
      status = "blocked";
      note = "缺少圖號/檔名";
    } else if (row.note) {
      status = row.status === "blocked" ? "warn" : row.status;
      note = row.note;
    }
    return {
      ...row,
      note,
      selected: status !== "blocked" && Boolean(newName && newName !== row.source_name && row.selected),
      status,
      target_path: targetPathFor(row.source_path, newName),
    };
  });
}

export function summarizeIsoRows(rows: IsoPlanRow[]): IsoWorkflowPlan["summary"] {
  return {
    total: rows.length,
    ready: rows.filter((row) => row.status === "ready").length,
    warn: rows.filter((row) => row.status === "warn").length,
    blocked: rows.filter((row) => row.status === "blocked").length,
    selected: rows.filter((row) => row.selected && row.status === "ready").length,
  };
}

export function formatIsoFilename(pattern: string, serial: string, line: string): string {
  const cleanSerial = serial.trim();
  const cleanLine = basenameWithoutPdf(line);
  if (!cleanSerial || !cleanLine) {
    return "";
  }
  const name = (pattern || "{serial}--{line}.pdf").split("{serial}").join(cleanSerial).split("{line}").join(cleanLine);
  return /\.[^\\/.\s]+$/.test(name) ? name : `${name}.pdf`;
}

export function createIsoRunId(): string {
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+$/, "").replace("T", "-");
  const suffix = Math.random().toString(16).slice(2, 8).padEnd(6, "0");
  return `iso-${stamp}-${suffix}`;
}

export function normalizeRegion(region: IsoRegion): IsoRegion {
  const width = clamp(region.width, 0.05, 1);
  const height = clamp(region.height, 0.05, 1);
  const left = clamp(region.left, 0, 1 - width);
  const top = clamp(region.top, 0, 1 - height);
  return { left, top, width, height };
}

export function parentPath(path: string): string {
  const normalized = path.replace(/\//g, "\\");
  const index = normalized.lastIndexOf("\\");
  return index >= 0 ? normalized.slice(0, index) : "";
}

export function formatRunTime(value: string): string {
  if (!value) {
    return "時間未知";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

export function runStatusLabel(status: string): string {
  if (status === "completed") return "已完成";
  if (status === "cancelled") return "已取消";
  if (status === "failed") return "失敗";
  if (status === "running") return "執行中";
  if (status === "queued") return "等待中";
  return status || "未知";
}

export function runActionLabel(action: string): string {
  if (action === "start_batch_detect") return "一鍵批次判讀";
  if (action === "plan") return "命名草稿";
  if (action === "build_rename_plan") return "命名草稿";
  if (action === "apply") return "套用更名";
  if (action === "replay_run_log") return "回放試算";
  return action || "ISO 流程";
}

export function runSummaryText(run: IsoRunLogSummary): string {
  const summary = run.summary || {};
  const total = numberFromSummary(summary.total);
  const ready = numberFromSummary(summary.ready);
  const warn = numberFromSummary(summary.warn);
  const blocked = numberFromSummary(summary.blocked);
  if (total || ready || warn || blocked) {
    return `${total || ready + warn + blocked} 頁 · ${ready} 可用 · ${warn + blocked} 待處理`;
  }
  if (run.failure?.failed_stage) {
    return failedStageLabel(run.failure.failed_stage);
  }
  if (run.action === "start_batch_detect") return "批次判讀紀錄";
  if (run.action === "plan" || run.action === "build_rename_plan") return "草稿產生紀錄";
  if (run.action === "apply") return "更名套用紀錄";
  return run.run_type === "iso" ? "ISO 流程紀錄" : "流程紀錄";
}

export function shortRunId(runId: string): string {
  if (!runId) {
    return "";
  }
  const parts = runId.split("-");
  if (parts.length >= 4) {
    return `${parts[0]}-${parts[1]}-${parts[2]}...`;
  }
  return runId.length > 18 ? `${runId.slice(0, 18)}...` : runId;
}

export function pilotLabel(id: string, stage: string): string {
  const labels: Record<string, string> = {
    P01: "來源",
    P02: "PDF 檢查",
    P03: "拆頁",
    P04: "ISO 清單",
    P05: "欄位對應",
    P06: "流水號判讀",
    P07: "ISO 對應",
    P08: "重複流水號",
    P09: "缺流水號",
    P10: "命名格式",
    P11: "命名草稿",
    P12: "可否套用",
    P13: "ROI 品質",
    P14: "設定檔一致",
    P15: "草稿新鮮度",
    roi_confidence: "ROI 品質",
    profile_consistency: "設定檔一致",
    draft_freshness: "草稿新鮮度",
  };
  return labels[id] ? `${id} ${labels[id]}` : stage || id;
}

export function pilotHint(item: IsoPilotItem): string {
  if (item.status === "ready") {
    return "這一步已通過";
  }
  if (item.status === "skipped") {
    return "本次不用檢查";
  }
  if (item.status === "running") {
    return "正在處理";
  }
  return localizeIsoDisplayText(item.manual_hint || item.user_text || item.stage);
}

export function pilotStatusLabel(status: IsoPilotItem["status"]): string {
  if (status === "ready") return "通過";
  if (status === "warn") return "待確認";
  if (status === "blocked") return "需處理";
  if (status === "skipped") return "略過";
  if (status === "running") return "執行中";
  return "等待";
}

export type IsoPilotTone = "ready" | "warn" | "danger" | "run" | "idle";

// Map a pilot item (status + schema-v2 freshness/needs_review) to a single CSS tone.
export function pilotTone(item: IsoPilotItem): IsoPilotTone {
  if (item.status === "blocked") return "danger";
  if (item.status === "warn" || item.freshness === "stale" || item.needs_review) return "warn";
  if (item.status === "running") return "run";
  if (item.status === "ready") return "ready";
  return "idle"; // pending / skipped
}

// Extra badge text for the orthogonal freshness / needs_review flags ("" when none).
export function pilotFreshnessLabel(item: IsoPilotItem): string {
  if (item.freshness === "stale") return "已過期";
  if (item.needs_review) return "未確認";
  return "";
}

// Stage -> where to take the user. Frozen P01-P12 stages plus forward-looking
// P13-P17 stages, so this keeps working once those items land on the backend.
const PILOT_LOCATION_BY_STAGE: Record<string, IsoPilotNextAction> = {
  input: { view: "workbench", anchor: "source", label: "檢查來源" },
  pdf_source: { view: "workbench", anchor: "source", label: "檢查 PDF 來源" },
  split: { view: "workbench", anchor: "source", label: "重新拆頁" },
  iso_list: { view: "engineer", anchor: "mapping", label: "到調校檢查 ISO 清單 / 工作表" },
  mapping: { view: "engineer", anchor: "mapping", label: "到調校選欄位對應" },
  serial_detection: { view: "engineer", anchor: "roi", label: "到調校調整 ROI / 門檻" },
  roi_confidence: { view: "engineer", anchor: "roi", label: "到調校檢查判讀品質" },
  iso_correction: { view: "workbench", anchor: "row", label: "到工作台修圖號對應" },
  duplicates: { view: "workbench", anchor: "row", label: "到工作台處理重複檔名" },
  missing_serial: { view: "workbench", anchor: "row", label: "到工作台補流水號" },
  naming_pattern: { view: "engineer", anchor: "pattern", label: "到調校檢查命名格式" },
  profile_consistency: { view: "engineer", anchor: "profile", label: "到調校檢查設定檔" },
  draft_freshness: { view: "workbench", anchor: "dryrun", label: "重新產生草稿" },
  rename_draft: { view: "workbench", anchor: "dryrun", label: "重新產生草稿" },
  apply_readiness: { view: "workbench", anchor: "dryrun", label: "到工作台試算 / 套用" },
  export_log: { view: "engineer", anchor: "runlog", label: "到調校匯出紀錄" },
  apply_safety: { view: "workbench", anchor: "dryrun", label: "到工作台確認套用安全" },
};

// Use the backend-provided next_action when present, otherwise derive from stage.
export function pilotLocation(item: IsoPilotItem): IsoPilotNextAction {
  if (item.next_action) {
    return item.next_action;
  }
  return PILOT_LOCATION_BY_STAGE[item.stage] ?? { view: "workbench", anchor: "row", label: "到工作台處理" };
}

function pilotUrgency(item: IsoPilotItem): number {
  if (item.status === "blocked") return 3;
  if (item.status === "warn") return 2;
  if (item.freshness === "stale" || item.needs_review) return 1;
  return 0;
}

// The single most urgent actionable pilot item (blocked > warn > stale/needs_review).
export function pilotNextStep(
  items: IsoPilotItem[],
): { item: IsoPilotItem; text: string; action: IsoPilotNextAction } | null {
  let best: IsoPilotItem | null = null;
  let bestScore = 0;
  for (const item of items) {
    const score = pilotUrgency(item);
    if (score > bestScore) {
      best = item;
      bestScore = score;
    }
  }
  if (!best) {
    return null;
  }
  return {
    item: best,
    text: localizeIsoDisplayText(best.user_text || best.manual_hint || best.stage),
    action: pilotLocation(best),
  };
}

export function localizeIsoDisplayText(value: string): string {
  if (!value) {
    return "";
  }
  const replacements: Array<[RegExp, string]> = [
    [/\bISO List\b/g, "ISO 清單"],
    [/\bProfile\b/g, "設定檔"],
    [/\bPilot List\b/g, "檢查清單"],
    [/\bPilot\b/g, "檢查"],
    [/\bRun ID\b/g, "流程 ID"],
    [/\brun log\b/gi, "流程紀錄"],
    [/\breplay\b/gi, "回放"],
    [/\bmanual corrected\b/gi, "手動修正"],
    [/\bmanual confirmed\b/gi, "手動確認"],
    [/\bconfidence_threshold\b/g, "信心門檻"],
    [/\bserial_region\b/g, "流水號 ROI"],
    [/\bdrawing_region\b/g, "圖號 ROI"],
    [/\bserial_col\b/g, "流水號欄"],
    [/\bline_col\b/g, "圖號欄"],
    [/\bsheet_name\b/g, "工作表"],
    [/\bpattern\b/g, "命名格式"],
    [/\bchanged\b/g, "已變更"],
    [/\blocal\b/g, "本機"],
    [/\bconfidence\b/gi, "信心"],
    [/\bthreshold\b/gi, "門檻"],
    [/\bavailable\b/gi, "可使用"],
    [/\bwaiting\b/gi, "等待"],
    [/\bready\b/gi, "通過"],
    [/\bwarn\b/gi, "待確認"],
    [/\bblocked\b/gi, "需處理"],
    [/\bidle\b/gi, "待命"],
    [/\bmissing\b/gi, "缺少"],
    [/\bpages\b/gi, "頁"],
    [/\bpage\b/gi, "頁"],
    [/\brows\b/gi, "筆"],
    [/\brow\b/gi, "列"],
  ];
  return replacements.reduce((text, [pattern, replacement]) => text.replace(pattern, replacement), value);
}

export function eventLabel(code: string): string {
  const normalized = code.toUpperCase();
  const labels: Record<string, string> = {
    RUN_STARTED: "流程開始",
    RUN_COMPLETED: "流程完成",
    RUN_FAILED: "流程失敗",
    RUN_CANCELLED: "流程取消",
    JOB_STARTED: "工作建立",
    JOB_RUNNING: "批次開始",
    ROW_DONE: "完成一頁",
    CANCELLED: "已取消",
    IDLE: "待命",
    SYS: "系統",
    EVENT: "事件",
  };
  return labels[normalized] || code || "事件";
}

export function pilotSummaryText(blockedPilot: number, warnPilot: number): string {
  if (!blockedPilot && !warnPilot) {
    return "沒有待處理";
  }
  const parts = [];
  if (blockedPilot) {
    parts.push(`${blockedPilot} 個需處理`);
  }
  if (warnPilot) {
    parts.push(`${warnPilot} 個待確認`);
  }
  return parts.join(" · ");
}

export function failedStageLabel(stage: string): string {
  const labels: Record<string, string> = {
    iso_parse: "ISO 清單讀取失敗",
    pdf_source: "PDF 來源失敗",
    serial_detection: "流水號判讀失敗",
    naming_draft: "命名草稿失敗",
    apply: "套用更名失敗",
    profile: "設定檔讀寫失敗",
    failed: "流程失敗",
  };
  return labels[stage] || stage || "流程失敗";
}

function filenameProblem(name: string): string {
  const base = name.trim();
  if (!base) {
    return "缺少命名";
  }
  if (/[<>:"/\\|?*\x00-\x1F]/.test(base)) {
    return "檔名含有 Windows 不允許字元";
  }
  if (/[ .]$/.test(base)) {
    return "檔名結尾不可是空白或句點";
  }
  const stem = base.replace(/\.[^.]*$/, "").toUpperCase();
  if (/^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/.test(stem)) {
    return "檔名是 Windows 保留名稱";
  }
  return "";
}

function basenameWithoutPdf(value: string): string {
  return value.trim().replace(/\.pdf$/i, "");
}

export function targetPathFor(sourcePath: string, newName: string): string {
  if (!newName) {
    return sourcePath;
  }
  const normalized = sourcePath.replace(/\//g, "\\");
  const index = normalized.lastIndexOf("\\");
  return index >= 0 ? `${normalized.slice(0, index + 1)}${newName}` : newName;
}

function numberFromSummary(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
