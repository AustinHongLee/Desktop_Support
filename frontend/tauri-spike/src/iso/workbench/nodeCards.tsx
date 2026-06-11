import type {
  IsoNodeWorkflowJobPayload,
  IsoNodeWorkflowRunLog,
  IsoPreviewPayload,
  IsoWorkflowPlan,
} from "../../isoWorkflow";
import { compactPath } from "../helpers";

export type NodeSummaryTone = "idle" | "ready" | "warn" | "danger" | "run";

export type NodeSummaryMetric = {
  label: string;
  tone?: NodeSummaryTone;
  value: string;
};

export type NodeCardSummary = {
  badges: Array<{ label: string; tone?: NodeSummaryTone }>;
  metrics: NodeSummaryMetric[];
  preview?: string;
  progress?: number;
  rows: Array<{ label: string; value: string }>;
  tone?: NodeSummaryTone;
};

export type NodeSummaryContext = {
  dirtyNodeIds?: string[];
  job: IsoNodeWorkflowJobPayload | null;
  plan: IsoWorkflowPlan | null;
  preview: IsoPreviewPayload | null;
  runLog: IsoNodeWorkflowRunLog | null;
  workflowInputs: Record<string, unknown>;
};

export function buildNodeCardSummaries(context: NodeSummaryContext): Record<string, NodeCardSummary> {
  const { job, plan, preview, runLog, workflowInputs } = context;
  const dirtyNodeIds = new Set(context.dirtyNodeIds ?? []);
  const rows = plan?.rows ?? [];
  const source = plan?.source;
  const threshold = Number(source?.confidence_threshold ?? workflowInputs.confidence_threshold ?? 0.7);
  const counts = rowCounts(rows, threshold);
  const pilotCounts = pilotStatusCounts(plan);
  const jobPercent = job?.progress?.percent ?? null;
  const batchJobId = shortId(job?.workflow_job_id || job?.job_id || plan?.provenance?.workflow_run_id || runLog?.run_id || "");
  const pdfSourceCount = source?.pdf_count ?? (inputValue(workflowInputs.combine_pdf) ? 1 : 0);

  return markDirtySummaries({
    pdf_source: {
      badges: [{ label: source ? "來源已解析" : "等待來源", tone: source ? "ready" : "idle" }],
      metrics: [
        { label: "PDF", value: String(pdfSourceCount), tone: pdfSourceCount ? "ready" : "idle" },
        { label: "候選", value: String(source?.iso_candidates?.length ?? 0) },
      ],
      preview: source?.combine_pdf ? compactPath(source.combine_pdf) : inputValue(workflowInputs.combine_pdf) || "尚未選擇 PDF",
      rows: [
        { label: "工作資料夾", value: compactPath(source?.work_folder || inputValue(workflowInputs.work_folder) || "未設定") },
        { label: "頁資料夾", value: compactPath(source?.page_folder || "尚未建立") },
      ],
      tone: source ? "ready" : "idle",
    },
    discover: {
      badges: statusBadges(runLog, "discover"),
      metrics: [{ label: "候選", value: String(source?.iso_candidates?.length ?? 0) }],
      preview: source?.work_folder ? compactPath(source.work_folder) : "探索來源",
      rows: [
        { label: "合併 PDF", value: compactPath(source?.combine_pdf || inputValue(workflowInputs.combine_pdf) || "未找到") },
        { label: "ISO 清單", value: compactPath(source?.iso_list || inputValue(workflowInputs.iso_list) || "未找到") },
      ],
      tone: statusTone(runLog, "discover"),
    },
    split: {
      badges: [...statusBadges(runLog, "split"), { label: "拆頁輸出", tone: "warn" }],
      metrics: [
        { label: "頁數", value: String(source?.pdf_count ?? 0), tone: source?.pdf_count ? "ready" : "idle" },
        { label: "來源", value: source?.kind || "-" },
      ],
      preview: source?.page_folder ? compactPath(source.page_folder) : "尚無拆頁結果",
      rows: [
        { label: "輸入", value: compactPath(source?.combine_pdf || inputValue(workflowInputs.combine_pdf) || "未設定") },
        { label: "輸出", value: compactPath(source?.page_folder || "尚未輸出") },
      ],
      tone: statusTone(runLog, "split"),
    },
    load_table: {
      badges: statusBadges(runLog, "load_table"),
      metrics: [
        { label: "列數", value: String(source?.record_count ?? 0), tone: source?.record_count ? "ready" : "idle" },
        { label: "欄位", value: `${source?.serial_col ?? "-"} / ${source?.line_col ?? "-"}` },
      ],
      preview: source?.iso_list ? compactPath(source.iso_list) : inputValue(workflowInputs.iso_list) || "尚未載入 ISO 清單",
      rows: [
        { label: "工作表", value: source?.sheet_name || inputValue(workflowInputs.sheet_name) || "自動" },
        { label: "樣本", value: (source?.headers ?? []).slice(0, 3).join(" · ") || "等待資料" },
      ],
      tone: statusTone(runLog, "load_table"),
    },
    roi_calib: {
      badges: [{ label: inputValue(workflowInputs.detect_serials) === "false" ? "判讀關閉" : "判讀開啟", tone: "ready" }],
      metrics: [
        { label: "門檻", value: `${Math.round(threshold * 100)}%`, tone: "ready" },
        { label: "低信心", value: String(counts.low), tone: counts.low ? "warn" : "ready" },
      ],
      preview: preview?.source_name || source?.pattern || inputValue(workflowInputs.pattern) || "ROI / 命名參數",
      rows: [
        { label: "流水號 ROI", value: regionSummary(source?.serial_region ?? workflowInputs.serial_region) },
        { label: "圖號 ROI", value: regionSummary(source?.drawing_region ?? workflowInputs.drawing_region) },
      ],
      tone: counts.low ? "warn" : "ready",
    },
    batch_detect: {
      badges: [
        ...statusBadges(runLog, "batch_detect"),
        { label: "背景處理", tone: "warn" },
      ],
      metrics: [
        { label: "總列", value: String(counts.total), tone: counts.total ? "ready" : "idle" },
        { label: "通過", value: String(counts.ready), tone: "ready" },
        { label: "低信心", value: String(counts.low), tone: counts.low ? "warn" : "ready" },
        { label: "未判讀", value: String(counts.missing), tone: counts.missing ? "warn" : "ready" },
      ],
      preview: jobPercent != null && jobPercent < 100 ? `執行中 ${jobPercent}%` : batchJobId ? `job ${batchJobId}` : "尚未判讀",
      progress: jobPercent ?? undefined,
      rows: rows.slice(0, 2).map((row) => ({ label: `P${row.page}`, value: `${row.serial || "-"} → ${row.new_name || row.source_name}` })),
      tone: jobPercent != null && jobPercent < 100 ? "run" : statusTone(runLog, "batch_detect"),
    },
    pilot: {
      badges: statusBadges(runLog, "pilot"),
      metrics: [
        { label: "通過", value: String(pilotCounts.ready), tone: "ready" },
        { label: "警示", value: String(pilotCounts.warn), tone: pilotCounts.warn ? "warn" : "ready" },
        { label: "阻擋", value: String(pilotCounts.blocked), tone: pilotCounts.blocked ? "danger" : "ready" },
      ],
      preview: `${plan?.pilot_results?.length ?? 0} 項檢查`,
      rows: (plan?.pilot_results ?? []).slice(0, 2).map((item) => ({ label: item.id, value: item.user_text || item.status })),
      tone: pilotCounts.blocked ? "danger" : pilotCounts.warn ? "warn" : "ready",
    },
    roi_dist: {
      badges: statusBadges(runLog, "roi_dist"),
      metrics: [
        { label: "高信心", value: String(counts.ready), tone: "ready" },
        { label: "低信心", value: String(counts.low), tone: counts.low ? "warn" : "ready" },
        { label: "未判讀", value: String(counts.missing), tone: counts.missing ? "warn" : "ready" },
      ],
      preview: `門檻 ${Math.round(threshold * 100)}%`,
      rows: weakestRows(rows).map((row) => ({ label: row.source_name, value: row.confidence ? `${Math.round(row.confidence * 100)}%` : "-" })),
      tone: counts.low || counts.missing ? "warn" : "ready",
    },
    export_csv: {
      badges: [{ label: "停用", tone: "idle" }, { label: "需授權", tone: "warn" }],
      metrics: [
        { label: "可匯出", value: String(counts.selected || counts.ready), tone: counts.ready ? "ready" : "idle" },
        { label: "阻擋", value: String(counts.blocked), tone: counts.blocked ? "warn" : "ready" },
      ],
      preview: "受認可匯出路徑",
      rows: [{ label: "輸出", value: ".runtime\\exports\\iso" }],
      tone: "warn",
    },
    apply_rename: {
      badges: [{ label: "停用", tone: "idle" }, { label: "需授權", tone: "warn" }],
      metrics: [
        { label: "可更名", value: String(counts.selected || counts.ready), tone: counts.ready ? "ready" : "idle" },
        { label: "需處理", value: String(counts.blocked + counts.warn), tone: counts.blocked + counts.warn ? "warn" : "ready" },
      ],
      preview: "必經確認",
      rows: rows.slice(0, 2).map((row) => ({ label: row.source_name, value: row.new_name || "-" })),
      tone: "warn",
    },
  }, dirtyNodeIds);
}

function markDirtySummaries(summaries: Record<string, NodeCardSummary>, dirtyNodeIds: Set<string>): Record<string, NodeCardSummary> {
  if (!dirtyNodeIds.size) {
    return summaries;
  }
  return Object.fromEntries(
    Object.entries(summaries).map(([nodeId, summary]) => {
      if (!dirtyNodeIds.has(nodeId)) {
        return [nodeId, summary];
      }
      return [
        nodeId,
        {
          ...summary,
          badges: [{ label: "參數已變更", tone: "warn" }, ...summary.badges.filter((badge) => badge.label !== "參數已變更")],
          preview: summary.preview ? `${summary.preview} · 待重跑` : "待重跑",
          tone: "warn",
        },
      ];
    }),
  );
}

function inputValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number") {
    return String(value);
  }
  return JSON.stringify(value);
}

function pilotStatusCounts(plan: IsoWorkflowPlan | null) {
  const summary = plan?.pilot_summary;
  return {
    ready: Number(summary?.ready ?? 0),
    warn: Number(summary?.warn ?? 0),
    blocked: Number(summary?.blocked ?? 0),
  };
}

function regionSummary(value: unknown): string {
  if (!value || typeof value !== "object") {
    return "未設定";
  }
  const region = value as Record<string, number>;
  return `${num(region.left)}, ${num(region.top)}, ${num(region.width)}, ${num(region.height)}`;
}

function rowCounts(rows: IsoWorkflowPlan["rows"], threshold: number) {
  return {
    blocked: rows.filter((row) => row.status === "blocked").length,
    low: rows.filter((row) => Number(row.confidence || 0) > 0 && Number(row.confidence || 0) < threshold).length,
    missing: rows.filter((row) => !row.serial).length,
    ready: rows.filter((row) => row.status === "ready").length,
    selected: rows.filter((row) => row.selected && row.status === "ready").length,
    total: rows.length,
    warn: rows.filter((row) => row.status === "warn").length,
  };
}

function shortId(value: string): string {
  if (!value) {
    return "";
  }
  return value.length > 14 ? value.slice(-12) : value;
}

function statusBadges(runLog: IsoNodeWorkflowRunLog | null, nodeId: string): NodeCardSummary["badges"] {
  const status = runLog?.nodes?.[nodeId]?.status;
  if (!status) {
    return [{ label: "尚未執行", tone: "idle" }];
  }
  if (status === "success") {
    return [{ label: "成功", tone: "ready" }];
  }
  if (status === "blocked") {
    return [{ label: "已阻擋", tone: "warn" }];
  }
  if (status === "failed") {
    return [{ label: "失敗", tone: "danger" }];
  }
  return [{ label: status, tone: "idle" }];
}

function statusTone(runLog: IsoNodeWorkflowRunLog | null, nodeId: string): NodeSummaryTone {
  const status = runLog?.nodes?.[nodeId]?.status;
  if (status === "success") return "ready";
  if (status === "blocked") return "warn";
  if (status === "failed") return "danger";
  return "idle";
}

function weakestRows(rows: IsoWorkflowPlan["rows"]) {
  return [...rows]
    .sort((left, right) => Number(left.confidence || 0) - Number(right.confidence || 0) || left.page - right.page)
    .slice(0, 2);
}

function num(value: number | undefined): string {
  return Number.isFinite(value) ? Number(value).toFixed(2) : "-";
}
