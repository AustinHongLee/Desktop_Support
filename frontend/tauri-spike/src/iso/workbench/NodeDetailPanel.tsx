import { AlertTriangle, CircleCheck, Lock, Play, RotateCcw } from "lucide-react";
import { useState, type CSSProperties, type ReactNode } from "react";
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
import { LiveCrop } from "./LiveCrop";
import type { NodeCardSummary } from "./nodeCards";

type DetailAction = {
  disabled?: boolean;
  label: string;
  onClick?: () => void;
  tone?: "primary" | "warn";
};

type NodeDetailPanelProps = {
  dirtyNodeIds?: string[];
  node: IsoNodeWorkflowInstance | null;
  nodeLog?: IsoNodeWorkflowNodeRunLog;
  onSelectNode?: (nodeId: string) => void;
  onRunFrom?: (nodeId: string) => void;
  onRunNode?: (nodeId: string) => void;
  onWorkflowInputChange?: (nodeId: string, field: string, value: unknown) => void;
  onApplyPlan?: () => void;
  onExportPlan?: () => void;
  plan: IsoWorkflowPlan | null;
  preview: IsoPreviewPayload | null;
  previewBusy?: boolean;
  previewError?: string;
  rerunEnabled?: boolean;
  summary?: NodeCardSummary;
  workbenchActionBusy?: "" | "apply" | "export";
  workflowInputs?: Record<string, unknown>;
};

export function NodeDetailPanel({
  dirtyNodeIds = [],
  node,
  nodeLog,
  onSelectNode,
  onRunFrom,
  onRunNode,
  onWorkflowInputChange,
  onApplyPlan,
  onExportPlan,
  plan,
  preview,
  previewBusy = false,
  previewError = "",
  rerunEnabled = false,
  summary,
  workbenchActionBusy = "",
  workflowInputs = {},
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
      {dirtyNodeIds?.includes(node.node_id) ? (
        <div style={styles.dirtyNotice}>
          <AlertTriangle size={14} />
          <span>參數已變更，按執行或重跑後才會更新結果。</span>
        </div>
      ) : null}
      {summary ? <SummaryBlock summary={summary} /> : null}
      <ActionRow
        actions={[
          { label: "重跑此節點", disabled: !rerunEnabled || node.node_type.startsWith("ui."), onClick: () => onRunNode?.(node.node_id) },
          { label: "重跑下游", disabled: !rerunEnabled, onClick: () => onRunFrom?.(node.node_id), tone: "primary" },
        ]}
      />
      {renderNodeDetail({ node, onApplyPlan, onExportPlan, onSelectNode, onWorkflowInputChange, plan, preview, previewBusy, previewError, workbenchActionBusy, workflowInputs })}
      <LogBlock nodeLog={nodeLog} />
    </div>
  );
}

function renderNodeDetail({
  node,
  onApplyPlan,
  onExportPlan,
  onSelectNode,
  onWorkflowInputChange,
  plan,
  preview,
  previewBusy,
  previewError,
  workbenchActionBusy,
  workflowInputs,
}: Pick<NodeDetailPanelProps, "node" | "onApplyPlan" | "onExportPlan" | "onSelectNode" | "onWorkflowInputChange" | "plan" | "preview" | "previewBusy" | "previewError" | "workbenchActionBusy" | "workflowInputs"> & { node: IsoNodeWorkflowInstance }) {
  if (node.node_id === "pdf_source" || node.node_id === "discover") {
    return <SourceDetail onChange={onWorkflowInputChange} plan={plan} workflowInputs={workflowInputs ?? {}} />;
  }
  if (node.node_id === "split") {
    return <SplitDetail plan={plan} />;
  }
  if (node.node_id === "load_table") {
    return <IsoListDetail onChange={onWorkflowInputChange} plan={plan} workflowInputs={workflowInputs ?? {}} />;
  }
  if (node.node_id === "roi_calib") {
    return <RoiDetail onChange={onWorkflowInputChange} plan={plan} preview={preview} previewBusy={previewBusy} previewError={previewError} workflowInputs={workflowInputs ?? {}} />;
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
    return <GuardedActionDetail action="export" busy={workbenchActionBusy === "export"} onAction={onExportPlan} plan={plan} />;
  }
  if (node.node_id === "apply_rename") {
    return <GuardedActionDetail action="apply" busy={workbenchActionBusy === "apply"} onAction={onApplyPlan} plan={plan} />;
  }
  return <GenericDetail node={node} />;
}

function SourceDetail({
  onChange,
  plan,
  workflowInputs,
}: {
  onChange?: NodeDetailPanelProps["onWorkflowInputChange"];
  plan: IsoWorkflowPlan | null;
  workflowInputs: Record<string, unknown>;
}) {
  const source = plan?.source;
  return (
    <div style={styles.section}>
      <EditorGrid>
        <TextEditor label="工作資料夾" value={stringValue(workflowInputs.work_folder ?? source?.work_folder)} onChange={(value) => onChange?.("pdf_source", "work_folder", value)} />
        <TextEditor label="合併 PDF" value={stringValue(workflowInputs.combine_pdf ?? source?.combine_pdf)} onChange={(value) => onChange?.("pdf_source", "combine_pdf", value)} />
      </EditorGrid>
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

function IsoListDetail({
  onChange,
  plan,
  workflowInputs,
}: {
  onChange?: NodeDetailPanelProps["onWorkflowInputChange"];
  plan: IsoWorkflowPlan | null;
  workflowInputs: Record<string, unknown>;
}) {
  const source = plan?.source;
  return (
    <div style={styles.section}>
      <EditorGrid>
        <TextEditor label="ISO 清單" value={stringValue(workflowInputs.iso_list ?? source?.iso_list)} onChange={(value) => onChange?.("load_table", "iso_list", value)} />
        <TextEditor label="工作表" value={stringValue(workflowInputs.sheet_name ?? source?.sheet_name)} onChange={(value) => onChange?.("load_table", "sheet_name", value)} />
        <NumberEditor label="流水號欄" value={numberOrEmpty(workflowInputs.serial_col ?? source?.serial_col)} onChange={(value) => onChange?.("load_table", "serial_col", value)} />
        <NumberEditor label="圖號欄" value={numberOrEmpty(workflowInputs.line_col ?? source?.line_col)} onChange={(value) => onChange?.("load_table", "line_col", value)} />
      </EditorGrid>
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
  onChange,
  plan,
  preview,
  previewBusy,
  previewError,
  workflowInputs,
}: {
  onChange?: NodeDetailPanelProps["onWorkflowInputChange"];
  plan: IsoWorkflowPlan | null;
  preview: IsoPreviewPayload | null;
  previewBusy?: boolean;
  previewError?: string;
  workflowInputs: Record<string, unknown>;
}) {
  const [activeRoi, setActiveRoi] = useState<"serial" | "drawing">("serial");
  const source = plan?.source;
  const serialRegion = regionOrDefault(workflowInputs.serial_region ?? source?.serial_region, DEFAULT_SERIAL_REGION);
  const drawingRegion = regionOrDefault(workflowInputs.drawing_region ?? source?.drawing_region, DEFAULT_DRAWING_REGION);
  const threshold = numberOrDefault(workflowInputs.confidence_threshold ?? source?.confidence_threshold, 0.7);
  const pattern = stringValue(workflowInputs.pattern ?? source?.pattern ?? "{serial}--{line}.pdf");
  const detectSerials = booleanValue(workflowInputs.detect_serials ?? source?.detect_serials ?? true);
  const updateRegion = (target: "serial" | "drawing", region: IsoRegion) => {
    onChange?.("roi_calib", target === "serial" ? "serial_region" : "drawing_region", region);
  };
  return (
    <div style={styles.section}>
      <EditorGrid>
        <TextEditor label="命名格式" value={pattern} onChange={(value) => onChange?.("roi_calib", "pattern", value)} />
        <ToggleEditor label="影像判讀流水號" checked={detectSerials} onChange={(value) => onChange?.("roi_calib", "detect_serials", value)} />
        <SliderEditor label="信心門檻" value={threshold} onChange={(value) => onChange?.("roi_calib", "confidence_threshold", value)} />
      </EditorGrid>
      <div style={styles.previewFrame}>
        {preview ? (
          <div style={styles.previewCanvas}>
            <img src={preview.page.image} alt={preview.source_name} style={styles.previewImage} />
            <RoiOverlay
              activeRoi={activeRoi}
              drawingRegion={drawingRegion}
              editable
              onChange={updateRegion}
              onSelect={setActiveRoi}
              serialRegion={serialRegion}
            />
          </div>
        ) : (
          <div style={styles.emptyPreview}>{previewBusy ? "載入預覽中" : previewError || "尚無 PDF 預覽"}</div>
        )}
      </div>
      <div style={styles.cropGrid}>
        <Crop title="流水號裁切">
          <LiveCrop image={preview?.page.image} region={serialRegion} />
        </Crop>
        <Crop title="圖號裁切">
          <LiveCrop image={preview?.page.image} region={drawingRegion} />
        </Crop>
      </div>
      <RegionEditor activeRoi={activeRoi} drawingRegion={drawingRegion} onChange={updateRegion} serialRegion={serialRegion} />
      <DetailGrid rows={[
        ["信心門檻", `${Math.round(threshold * 100)}%`],
        ["影像判讀", detectSerials ? "開啟" : "關閉"],
        ["命名格式", pattern],
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

function GuardedActionDetail({
  action,
  busy,
  onAction,
  plan,
}: {
  action: "apply" | "export";
  busy?: boolean;
  onAction?: () => void;
  plan: IsoWorkflowPlan | null;
}) {
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
      <ActionRow actions={[{ label: busy ? "處理中" : action === "export" ? "匯出草稿 CSV" : "開啟套用確認", disabled: busy || !plan || (action === "apply" && !readyRows.length), onClick: onAction, tone: "primary" }]} />
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

function EditorGrid({ children }: { children: ReactNode }) {
  return <div style={styles.editorGrid}>{children}</div>;
}

function TextEditor({ label, onChange, value }: { label: string; onChange: (value: string) => void; value: string }) {
  return (
    <label style={styles.editorField}>
      <span>{label}</span>
      <input style={styles.textInput} type="text" value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function NumberEditor({ label, onChange, value }: { label: string; onChange: (value: number | "") => void; value: number | "" }) {
  return (
    <label style={styles.editorField}>
      <span>{label}</span>
      <input
        style={styles.textInput}
        type="number"
        value={value}
        onChange={(event) => onChange(event.target.value === "" ? "" : Number(event.target.value))}
      />
    </label>
  );
}

function ToggleEditor({ checked, label, onChange }: { checked: boolean; label: string; onChange: (value: boolean) => void }) {
  return (
    <label style={{ ...styles.editorField, ...styles.toggleField }}>
      <span>{label}</span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}

function SliderEditor({ label, onChange, value }: { label: string; onChange: (value: number) => void; value: number }) {
  return (
    <label style={styles.editorField}>
      <span>{label} {Math.round(value * 100)}%</span>
      <input
        type="range"
        min={0.1}
        max={0.99}
        step={0.01}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function RegionEditor({
  activeRoi,
  drawingRegion,
  onChange,
  serialRegion,
}: {
  activeRoi: "serial" | "drawing";
  drawingRegion: IsoRegion;
  onChange: (target: "serial" | "drawing", region: IsoRegion) => void;
  serialRegion: IsoRegion;
}) {
  const region = activeRoi === "serial" ? serialRegion : drawingRegion;
  const targetLabel = activeRoi === "serial" ? "流水號 ROI" : "圖號 ROI";
  const updateField = (field: keyof IsoRegion, value: number) => onChange(activeRoi, { ...region, [field]: clampRegionNumber(value) });
  return (
    <div style={styles.regionEditor}>
      <strong>{targetLabel}</strong>
      <div style={styles.regionGrid}>
        {(["left", "top", "width", "height"] as const).map((field) => (
          <label style={styles.editorField} key={field}>
            <span>{field.toUpperCase()}</span>
            <input
              style={styles.textInput}
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={Number(region[field]).toFixed(2)}
              onChange={(event) => updateField(field, Number(event.target.value))}
            />
          </label>
        ))}
      </div>
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

function Crop({ children, image, title }: { children?: ReactNode; image?: string; title: string }) {
  return (
    <div style={styles.crop}>
      <span>{title}</span>
      {children ?? (image ? <img src={image} alt={title} /> : <div />)}
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

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function numberOrDefault(value: unknown, fallback: number): number {
  const numeric = typeof value === "number" ? value : typeof value === "string" && value !== "" ? Number(value) : NaN;
  return Number.isFinite(numeric) ? numeric : fallback;
}

function numberOrEmpty(value: unknown): number | "" {
  const numeric = typeof value === "number" ? value : typeof value === "string" && value !== "" ? Number(value) : NaN;
  return Number.isFinite(numeric) ? numeric : "";
}

function booleanValue(value: unknown): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "string") {
    return value.toLowerCase() !== "false";
  }
  return Boolean(value);
}

function regionOrDefault(value: unknown, fallback: IsoRegion): IsoRegion {
  if (!value || typeof value !== "object") {
    return fallback;
  }
  const region = value as Partial<IsoRegion>;
  const next = {
    left: Number(region.left),
    top: Number(region.top),
    width: Number(region.width),
    height: Number(region.height),
  };
  return Object.values(next).every(Number.isFinite) ? next : fallback;
}

function clampRegionNumber(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(1, Math.max(0, value));
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
  dirtyNotice: {
    alignItems: "center",
    background: "rgba(255,209,102,0.08)",
    border: "1px solid rgba(255,209,102,0.28)",
    borderRadius: 8,
    color: "#ffd166",
    display: "flex",
    gap: 7,
    padding: "8px 10px",
  },
  editorField: {
    color: "rgba(220,235,228,0.72)",
    display: "grid",
    fontSize: 11,
    fontWeight: 800,
    gap: 5,
    minWidth: 0,
  },
  editorGrid: {
    display: "grid",
    gap: 8,
    gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
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
  regionEditor: {
    background: "rgba(0,0,0,0.14)",
    border: "1px solid rgba(47,245,200,0.12)",
    borderRadius: 8,
    display: "grid",
    gap: 8,
    minWidth: 0,
    padding: 9,
  },
  regionGrid: {
    display: "grid",
    gap: 7,
    gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
    minWidth: 0,
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
  textInput: {
    background: "rgba(0,0,0,0.28)",
    border: "1px solid rgba(255,255,255,0.12)",
    borderRadius: 7,
    color: "#dffcf4",
    font: "inherit",
    minWidth: 0,
    padding: "7px 8px",
  },
  summaryBlock: {
    display: "grid",
    gap: 8,
  },
  toggleField: {
    alignContent: "space-between",
    gridTemplateColumns: "minmax(0, 1fr) auto",
  },
} satisfies Record<string, CSSProperties>;
