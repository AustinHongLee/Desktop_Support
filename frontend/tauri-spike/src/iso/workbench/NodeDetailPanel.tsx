import { AlertTriangle, CircleCheck, FileJson, Lock, Play, RotateCcw } from "lucide-react";
import type { CSSProperties } from "react";
import type {
  IsoNodeWorkflowInstance,
  IsoNodeWorkflowNodeRunLog,
  IsoPreviewPayload,
  IsoRegion,
  IsoWorkflowPlan,
} from "../../isoWorkflow";
import { compactPath, DEFAULT_DRAWING_REGION, DEFAULT_SERIAL_REGION } from "../helpers";
import { PilotListPanel } from "../components/PilotListPanel";
import { RoiOverlay } from "../components/RoiOverlay";
import { RoiSamplePanel } from "../components/RoiSamplePanel";
import type { NodeCardSummary } from "./nodeCards";

type DetailAction = {
  disabled?: boolean;
  label: string;
  onClick?: () => void;
  tone?: "primary" | "warn";
};

type NodeDetailPanelProps = {
  node: IsoNodeWorkflowInstance | null;
  nodeLog?: IsoNodeWorkflowNodeRunLog;
  onSelectNode?: (nodeId: string) => void;
  plan: IsoWorkflowPlan | null;
  preview: IsoPreviewPayload | null;
  previewBusy?: boolean;
  previewError?: string;
  summary?: NodeCardSummary;
};

export function NodeDetailPanel({
  node,
  nodeLog,
  onSelectNode,
  plan,
  preview,
  previewBusy = false,
  previewError = "",
  summary,
}: NodeDetailPanelProps) {
  if (!node) {
    return <EmptyDetail />;
  }
  const title = node.display_name || node.node_id;
  return (
    <div style={styles.shell}>
      <div style={styles.head}>
        <div>
          <strong>{title}</strong>
          <code>{node.node_id} · {node.node_type}</code>
        </div>
        <span style={statusPillStyle(nodeLog?.status)}>{statusLabel(nodeLog?.status, node.enabled === false)}</span>
      </div>
      {summary ? <SummaryBlock summary={summary} /> : null}
      {renderNodeDetail({ node, onSelectNode, plan, preview, previewBusy, previewError })}
      <LogBlock nodeLog={nodeLog} />
    </div>
  );
}

function renderNodeDetail({
  node,
  onSelectNode,
  plan,
  preview,
  previewBusy,
  previewError,
}: Pick<NodeDetailPanelProps, "node" | "onSelectNode" | "plan" | "preview" | "previewBusy" | "previewError"> & { node: IsoNodeWorkflowInstance }) {
  if (node.node_id === "pdf_source" || node.node_id === "discover") {
    return <SourceDetail plan={plan} />;
  }
  if (node.node_id === "split") {
    return <SplitDetail plan={plan} />;
  }
  if (node.node_id === "load_table") {
    return <IsoListDetail plan={plan} />;
  }
  if (node.node_id === "roi_calib") {
    return <RoiDetail plan={plan} preview={preview} previewBusy={previewBusy} previewError={previewError} />;
  }
  if (node.node_id === "batch_detect") {
    return <BatchDetail plan={plan} actions={[{ label: "重跑此節點", disabled: true }, { label: "重跑下游", disabled: true }]} />;
  }
  if (node.node_id === "pilot") {
    return <PilotDetail plan={plan} />;
  }
  if (node.node_id === "roi_dist") {
    const threshold = Number(plan?.source.confidence_threshold ?? 0.7);
    return (
      <div style={styles.section}>
        <RoiSamplePanel distribution={null} rows={plan?.rows ?? []} threshold={threshold} />
        <button className="action-button" type="button" onClick={() => onSelectNode?.("roi_calib")}>
          <RotateCcw size={14} />
          <span>跳回 ROI 調校</span>
        </button>
      </div>
    );
  }
  if (node.node_id === "export_csv") {
    return <GuardedActionDetail action="export" plan={plan} />;
  }
  if (node.node_id === "apply_rename") {
    return <GuardedActionDetail action="apply" plan={plan} />;
  }
  return <GenericDetail node={node} />;
}

function SourceDetail({ plan }: { plan: IsoWorkflowPlan | null }) {
  const source = plan?.source;
  return (
    <div style={styles.section}>
      <DetailGrid rows={[
        ["合併 PDF", compactPath(source?.combine_pdf || "未選擇")],
        ["工作資料夾", compactPath(source?.work_folder || "未選擇")],
        ["頁面資料夾", compactPath(source?.page_folder || "尚未建立")],
        ["PDF 數量", String(source?.pdf_count ?? 0)],
      ]} />
    </div>
  );
}

function SplitDetail({ plan }: { plan: IsoWorkflowPlan | null }) {
  const source = plan?.source;
  const samples = plan?.rows.slice(0, 8) ?? [];
  return (
    <div style={styles.section}>
      <DetailGrid rows={[
        ["拆頁資料夾", compactPath(source?.page_folder || "尚未輸出")],
        ["頁數", String(source?.pdf_count ?? samples.length)],
        ["來源", source?.kind || "-"],
      ]} />
      <SampleRows rows={samples.map((row) => [String(row.page), row.source_name])} />
    </div>
  );
}

function IsoListDetail({ plan }: { plan: IsoWorkflowPlan | null }) {
  const source = plan?.source;
  return (
    <div style={styles.section}>
      <DetailGrid rows={[
        ["ISO 清單", compactPath(source?.iso_list || "未選擇")],
        ["工作表", source?.sheet_name || "自動"],
        ["資料列", String(source?.record_count ?? 0)],
        ["流水號欄", String(source?.serial_col ?? "-")],
        ["圖號欄", String(source?.line_col ?? "-")],
      ]} />
      <SampleRows rows={(source?.headers ?? []).slice(0, 8).map((header, index) => [`欄 ${index + 1}`, header])} />
    </div>
  );
}

function RoiDetail({
  plan,
  preview,
  previewBusy,
  previewError,
}: {
  plan: IsoWorkflowPlan | null;
  preview: IsoPreviewPayload | null;
  previewBusy?: boolean;
  previewError?: string;
}) {
  const source = plan?.source;
  const serialRegion = source?.serial_region ?? DEFAULT_SERIAL_REGION;
  const drawingRegion = source?.drawing_region ?? DEFAULT_DRAWING_REGION;
  return (
    <div style={styles.section}>
      <div style={styles.previewFrame}>
        {preview ? (
          <div style={styles.previewCanvas}>
            <img src={preview.page.image} alt={preview.source_name} style={styles.previewImage} />
            <RoiOverlay
              activeRoi="serial"
              drawingRegion={drawingRegion}
              editable={false}
              onChange={() => {}}
              onSelect={() => {}}
              serialRegion={serialRegion}
            />
          </div>
        ) : (
          <div style={styles.emptyPreview}>{previewBusy ? "載入預覽中" : previewError || "尚無 PDF 預覽"}</div>
        )}
      </div>
      <div style={styles.cropGrid}>
        <Crop title="流水號裁切" image={preview?.serial_crop.image} />
        <Crop title="圖號裁切" image={preview?.drawing_crop.image} />
      </div>
      <DetailGrid rows={[
        ["信心門檻", `${Math.round(Number(source?.confidence_threshold ?? 0.7) * 100)}%`],
        ["影像判讀", source?.detect_serials === false ? "關閉" : "開啟"],
        ["命名格式", source?.pattern || "{serial}--{line}.pdf"],
        ["流水號 ROI", regionSummary(serialRegion)],
        ["圖號 ROI", regionSummary(drawingRegion)],
      ]} />
    </div>
  );
}

function BatchDetail({ actions, plan }: { actions: DetailAction[]; plan: IsoWorkflowPlan | null }) {
  const rows = plan?.rows ?? [];
  const threshold = Number(plan?.source.confidence_threshold ?? 0.7);
  const low = rows.filter((row) => row.confidence > 0 && row.confidence < threshold).length;
  const missing = rows.filter((row) => !row.serial).length;
  return (
    <div style={styles.section}>
      <DetailGrid rows={[
        ["總列", String(rows.length)],
        ["通過", String(plan?.summary.ready ?? 0)],
        ["低信心", String(low)],
        ["未判讀", String(missing)],
      ]} />
      <SampleRows rows={rows.slice(0, 8).map((row) => [`P${row.page}`, `${row.serial || "-"} → ${row.new_name || row.source_name}`])} />
      <ActionRow actions={actions} />
    </div>
  );
}

function PilotDetail({ plan }: { plan: IsoWorkflowPlan | null }) {
  return (
    <div style={styles.section}>
      <PilotListPanel items={plan?.pilot_results ?? []} showEngineerDetail />
    </div>
  );
}

function GuardedActionDetail({ action, plan }: { action: "apply" | "export"; plan: IsoWorkflowPlan | null }) {
  const rows = plan?.rows ?? [];
  const readyRows = rows.filter((row) => row.status === "ready" && row.selected);
  const blocked = rows.filter((row) => row.status === "blocked" || row.status === "warn");
  return (
    <div style={styles.section}>
      <div style={styles.guardBox}>
        <Lock size={16} />
        <div>
          <strong>{action === "export" ? "匯出草稿 CSV" : "套用更名"}</strong>
          <span>引擎節點維持停用 · guarded；操作會走既有確認與審計路徑。</span>
        </div>
      </div>
      <DetailGrid rows={[
        ["可處理", String(readyRows.length || plan?.summary.ready || 0)],
        ["需確認", String(blocked.length)],
        ["來源 run", plan?.source_run_id || plan?.provenance?.workflow_run_id || "-"],
      ]} />
      <SampleRows rows={(readyRows.length ? readyRows : rows).slice(0, 6).map((row) => [row.source_name, row.new_name || "-"])} />
      <ActionRow actions={[{ label: action === "export" ? "匯出草稿 CSV" : "開啟套用確認", disabled: true, tone: "primary" }]} />
    </div>
  );
}

function GenericDetail({ node }: { node: IsoNodeWorkflowInstance }) {
  return (
    <div style={styles.section}>
      <DetailGrid rows={Object.entries(node.params ?? {}).map(([key, value]) => [key, String(value)])} />
    </div>
  );
}

function SummaryBlock({ summary }: { summary: NodeCardSummary }) {
  return (
    <div style={styles.summaryBlock}>
      <div style={styles.metricGrid}>
        {summary.metrics.map((metric) => (
          <div style={metricStyle(metric.tone)} key={`${metric.label}-${metric.value}`}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </div>
        ))}
      </div>
      {summary.preview ? <span style={styles.previewText}>{summary.preview}</span> : null}
    </div>
  );
}

function LogBlock({ nodeLog }: { nodeLog?: IsoNodeWorkflowNodeRunLog }) {
  if (!nodeLog) {
    return null;
  }
  return (
    <div style={styles.section}>
      <DetailGrid rows={[
        ["耗時", `${nodeLog.duration_ms} ms`],
        ["輸出", `${Object.keys(nodeLog.outputs ?? {}).length} ports`],
        ["副作用", `${nodeLog.side_effects?.length ?? 0} 筆`],
      ]} />
      {nodeLog.error?.message ? (
        <div style={styles.errorLine}>
          <AlertTriangle size={14} />
          <span>{nodeLog.error.message}</span>
        </div>
      ) : null}
    </div>
  );
}

function DetailGrid({ rows }: { rows: Array<[string, string]> }) {
  return (
    <div style={styles.detailGrid}>
      {rows.length ? rows.map(([label, value]) => (
        <div style={styles.detailCell} key={`${label}-${value}`}>
          <span>{label}</span>
          <strong title={value}>{value}</strong>
        </div>
      )) : <span style={styles.muted}>尚無資料</span>}
    </div>
  );
}

function SampleRows({ rows }: { rows: Array<[string, string]> }) {
  if (!rows.length) {
    return <span style={styles.muted}>尚無樣本</span>;
  }
  return (
    <div style={styles.sampleRows}>
      {rows.map(([label, value], index) => (
        <div style={styles.sampleRow} key={`${label}-${index}`}>
          <span>{label}</span>
          <strong title={value}>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function ActionRow({ actions }: { actions: DetailAction[] }) {
  return (
    <div style={styles.actionRow}>
      {actions.map((action) => (
        <button className={action.tone === "primary" ? "launch-button" : "action-button"} disabled={action.disabled} key={action.label} onClick={action.onClick} type="button">
          {action.tone === "warn" ? <AlertTriangle size={14} /> : action.tone === "primary" ? <Play size={14} /> : <RotateCcw size={14} />}
          <span>{action.label}</span>
        </button>
      ))}
    </div>
  );
}

function Crop({ image, title }: { image?: string; title: string }) {
  return (
    <div style={styles.crop}>
      <span>{title}</span>
      {image ? <img src={image} alt={title} /> : <div />}
    </div>
  );
}

function EmptyDetail() {
  return (
    <div style={styles.empty}>
      <CircleCheck size={18} />
      <span>選取節點後顯示資料、預覽與操作。</span>
    </div>
  );
}

function metricStyle(tone: NodeCardSummary["tone"]): CSSProperties {
  const color = tone === "danger" ? "#ff9b9b" : tone === "warn" ? "#ffd166" : tone === "ready" ? "#2ff5c8" : "#b7d8ce";
  return {
    border: `1px solid ${color}55`,
    borderRadius: 8,
    display: "grid",
    gap: 3,
    minWidth: 0,
    padding: "7px 8px",
  };
}

function regionSummary(region: IsoRegion): string {
  return `${region.left.toFixed(2)}, ${region.top.toFixed(2)}, ${region.width.toFixed(2)}, ${region.height.toFixed(2)}`;
}

function statusLabel(status: string | undefined, disabled: boolean) {
  if (disabled) return "停用";
  if (status === "success") return "成功";
  if (status === "blocked") return "已阻擋";
  if (status === "failed") return "失敗";
  if (status === "running") return "執行中";
  return "待命";
}

function statusPillStyle(status: string | undefined): CSSProperties {
  const tone = status === "success" ? "#2ff5c8" : status === "failed" ? "#ff9b9b" : status === "blocked" ? "#ffd166" : "#b7d8ce";
  return {
    border: `1px solid ${tone}66`,
    borderRadius: 999,
    color: tone,
    fontSize: 12,
    fontWeight: 900,
    padding: "4px 8px",
    whiteSpace: "nowrap",
  };
}

const styles = {
  actionRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  crop: {
    background: "rgba(255,255,255,0.04)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 8,
    display: "grid",
    gap: 6,
    minHeight: 78,
    minWidth: 0,
    overflow: "hidden",
    padding: 8,
  },
  cropGrid: {
    display: "grid",
    gap: 8,
    gridTemplateColumns: "1fr 1fr",
    minWidth: 0,
  },
  detailCell: {
    background: "rgba(255,255,255,0.035)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 8,
    display: "grid",
    gap: 3,
    minWidth: 0,
    padding: "7px 8px",
  },
  detailGrid: {
    display: "grid",
    gap: 7,
    gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
    minWidth: 0,
  },
  empty: {
    alignItems: "center",
    color: "#b7d8ce",
    display: "flex",
    gap: 8,
    minHeight: 120,
  },
  emptyPreview: {
    alignItems: "center",
    color: "#b7d8ce",
    display: "flex",
    justifyContent: "center",
    minHeight: 180,
  },
  errorLine: {
    alignItems: "center",
    color: "#ffd166",
    display: "flex",
    gap: 7,
  },
  guardBox: {
    alignItems: "flex-start",
    background: "rgba(255,209,102,0.08)",
    border: "1px solid rgba(255,209,102,0.22)",
    borderRadius: 8,
    display: "flex",
    gap: 8,
    padding: 10,
  },
  head: {
    alignItems: "flex-start",
    borderBottom: "1px solid rgba(255,255,255,0.08)",
    display: "flex",
    gap: 10,
    justifyContent: "space-between",
    minWidth: 0,
    paddingBottom: 8,
  },
  metricGrid: {
    display: "grid",
    gap: 7,
    gridTemplateColumns: "repeat(auto-fit, minmax(86px, 1fr))",
  },
  muted: {
    color: "rgba(220,235,228,0.58)",
    fontSize: 12,
  },
  previewCanvas: {
    position: "relative",
  },
  previewFrame: {
    background: "rgba(0,0,0,0.22)",
    border: "1px solid rgba(47,245,200,0.16)",
    borderRadius: 8,
    minHeight: 180,
    overflow: "hidden",
  },
  previewImage: {
    display: "block",
    width: "100%",
  },
  previewText: {
    color: "#c7f7eb",
    fontSize: 12,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  sampleRow: {
    display: "grid",
    gap: 8,
    gridTemplateColumns: "80px minmax(0, 1fr)",
    minWidth: 0,
  },
  sampleRows: {
    display: "grid",
    gap: 5,
  },
  section: {
    background: "rgba(255,255,255,0.028)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 10,
    display: "grid",
    gap: 10,
    minWidth: 0,
    padding: 10,
  },
  shell: {
    display: "grid",
    gap: 10,
    minWidth: 0,
  },
  summaryBlock: {
    display: "grid",
    gap: 8,
  },
} satisfies Record<string, CSSProperties>;
