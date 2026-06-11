import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  AlertTriangle,
  CircleCheck,
  Eye,
  FileText,
  FolderOpen,
  Layers3,
  MoreHorizontal,
  RefreshCcw,
  SearchCheck,
  SlidersHorizontal,
  Table2,
} from "lucide-react";
import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import type { IsoNodeWorkflowJobPayload, IsoNodeWorkflowRunLog, IsoPlanRow, IsoPreviewPayload, IsoRegion, IsoWorkflowPlan } from "../../isoWorkflow";
import { compactPath, DEFAULT_DRAWING_REGION, DEFAULT_SERIAL_REGION } from "../helpers";
import { RoiOverlay } from "../components/RoiOverlay";

type WorkflowGuideCanvasProps = {
  dataOriginLabel?: string;
  dirtyNodeIds?: string[];
  job: IsoNodeWorkflowJobPayload | null;
  onRefreshPreview?: (rowId: string) => void;
  onRunFrom?: (nodeId: string) => void;
  onRunNode?: (nodeId: string) => void;
  onRunPageTrial?: (rowId: string) => void;
  onSelectNode?: (nodeId: string) => void;
  onSelectRow?: (rowId: string) => void;
  onWorkflowInputChange?: (nodeId: string, field: string, value: unknown) => void;
  pageTrialBusyId?: string;
  pageTrials?: Record<string, IsoPageTrial>;
  plan: IsoWorkflowPlan | null;
  preview: IsoPreviewPayload | null;
  previewBusy?: boolean;
  previewError?: string;
  rerunEnabled?: boolean;
  runLog: IsoNodeWorkflowRunLog | null;
  selectedNodeId?: string;
  selectedRowId?: string;
  workflowInputs: Record<string, unknown>;
};

export type IsoPageTrial = {
  confidence: number;
  page: number;
  serial: string;
  sourcePath: string;
  updatedAt: string;
};

type WorkflowNodeKind =
  | "source"
  | "config"
  | "listPreview"
  | "page"
  | "roi"
  | "result"
  | "output"
  | "summary"
  | "action"
  | "more";

type WorkflowNodeSize = "S" | "M" | "L" | "XL";

type GuideEdgeKind = "source" | "table" | "pdf" | "params" | "rows" | "result" | "action";

type GuideEdgeOptions = {
  animated?: boolean;
  dirty?: boolean;
  kind: GuideEdgeKind;
};

type GuideNodeData = {
  active: boolean;
  dirty: boolean;
  drawingRegion: IsoRegion;
  guarded?: boolean;
  icon: ReactNode;
  kind: WorkflowNodeKind;
  meta?: string;
  nodeId: string;
  notice?: { text: string; tone: "idle" | "ready" | "warn" | "danger"; title?: string };
  onLoadMore?: () => void;
  onRefreshPreview?: (rowId: string) => void;
  onRunFrom?: (nodeId: string) => void;
  onRunNode?: (nodeId: string) => void;
  onRunPageTrial?: (rowId: string) => void;
  onSelectNode?: (nodeId: string) => void;
  onSelectRow?: (rowId: string) => void;
  onWorkflowInputChange?: (nodeId: string, field: string, value: unknown) => void;
  pageCount?: number;
  pageTrial?: IsoPageTrial;
  pageTrialBusy?: boolean;
  preview: IsoPreviewPayload | null;
  previewBusy: boolean;
  previewError: string;
  portIn: string;
  portOut: string;
  rows: Array<{ label: string; tone?: "idle" | "ready" | "warn" | "danger"; value: string }>;
  row?: IsoPlanRow;
  rowCount?: number;
  selectedPreview: boolean;
  serialRegion: IsoRegion;
  size: WorkflowNodeSize;
  subtitle: string;
  threshold: number;
  title: string;
  tone: "idle" | "ready" | "warn" | "danger";
  visibleCount?: number;
};

type GuideNode = Node<GuideNodeData, "guideNode">;

const PAGE_CHUNK_SIZE = 10;
const DEFAULT_VIEWPORT = { x: 86, y: 54, zoom: 0.58 };
const GUIDE_LAYOUT = {
  actionX: 3540,
  branchX: 360,
  configX: 720,
  mergeX: 3180,
  outputX: 2820,
  pageX: 1060,
  resultX: 2460,
  roiX: 1840,
  sourceX: 0,
  isoY: 30,
  pdfY: 430,
  rowGapY: 430,
  rowStartY: 300,
  sourceY: 270,
} as const;

export function WorkflowGuideCanvas({
  dataOriginLabel = "",
  dirtyNodeIds = [],
  job,
  onRefreshPreview,
  onRunFrom,
  onRunNode,
  onRunPageTrial,
  onSelectNode,
  onSelectRow,
  onWorkflowInputChange,
  pageTrialBusyId = "",
  pageTrials = {},
  plan,
  preview,
  previewBusy = false,
  previewError = "",
  rerunEnabled = false,
  runLog,
  selectedNodeId = "pdf_source",
  selectedRowId = "",
  workflowInputs,
}: WorkflowGuideCanvasProps) {
  const [visibleLimit, setVisibleLimit] = useState(PAGE_CHUNK_SIZE);
  const [viewResetKey, setViewResetKey] = useState(0);
  const rows = plan?.rows ?? [];
  const source = plan?.source;
  const visibleRows = rows.slice(0, visibleLimit);
  const serialRegion = regionOrDefault(workflowInputs.serial_region ?? source?.serial_region, DEFAULT_SERIAL_REGION);
  const drawingRegion = regionOrDefault(workflowInputs.drawing_region ?? source?.drawing_region, DEFAULT_DRAWING_REGION);
  const threshold = numberOrDefault(workflowInputs.confidence_threshold ?? source?.confidence_threshold, 0.7);
  const pdfPath = stringValue(workflowInputs.combine_pdf ?? source?.combine_pdf);
  const workFolder = stringValue(workflowInputs.work_folder ?? source?.work_folder);
  const isoPath = stringValue(workflowInputs.iso_list ?? source?.iso_list);
  const pageFolder = stringValue(workflowInputs.page_folder ?? source?.page_folder);
  const pattern = stringValue(workflowInputs.pattern ?? source?.pattern ?? "{serial}--{line}.pdf");
  const dirty = useMemo(() => new Set(dirtyNodeIds), [dirtyNodeIds]);
  const jobRunning = Boolean(job && ["queued", "running", "cancel_requested"].includes(job.state));

  useEffect(() => {
    setVisibleLimit(PAGE_CHUNK_SIZE);
  }, [rows.length, source?.combine_pdf, source?.iso_list]);

  const graph = useMemo(() => buildGuideGraph({
    dirty,
    drawingRegion,
    isoPath,
    jobRunning,
    onLoadMore: () => setVisibleLimit((current) => Math.min(rows.length, current + PAGE_CHUNK_SIZE)),
    onRefreshPreview,
    onRunFrom,
    onRunNode,
    onRunPageTrial,
    onSelectNode,
    onSelectRow,
    onWorkflowInputChange,
    pageTrialBusyId,
    pageTrials,
    pageFolder,
    pattern,
    pdfPath,
    plan,
    preview,
    previewBusy,
    previewError,
    rerunEnabled,
    rows,
    runLog,
    selectedNodeId,
    selectedRowId,
    serialRegion,
    source,
    threshold,
    visibleLimit,
    visibleRows,
    workflowInputs,
    workFolder,
  }), [
    dirty,
    drawingRegion,
    isoPath,
    jobRunning,
    onRefreshPreview,
    onRunFrom,
    onRunNode,
    onRunPageTrial,
    onSelectNode,
    onSelectRow,
    onWorkflowInputChange,
    pageTrialBusyId,
    pageTrials,
    pageFolder,
    pattern,
    pdfPath,
    plan,
    preview,
    previewBusy,
    previewError,
    rerunEnabled,
    rows,
    runLog,
    selectedNodeId,
    selectedRowId,
    serialRegion,
    source,
    threshold,
    visibleLimit,
    visibleRows,
    workflowInputs,
    workFolder,
  ]);

  return (
    <section style={styles.shell}>
      <div style={styles.toolbar}>
        <div style={styles.toolbarText}>
          <span>ComfyUI 風格節點畫布</span>
          <strong>工作區分叉 · ISO / PDF 匯流 · 每頁 ROI · 判讀輸出</strong>
          <div style={styles.flowLegend}>
            <span style={styles.lanePill}>來源</span>
            <span style={styles.lanePill}>設定</span>
            <span style={styles.lanePill}>處理</span>
            <span style={styles.lanePill}>結果</span>
            <span style={styles.lanePill}>輸出</span>
          </div>
          <div style={styles.edgeLegend}>
            <span style={styles.edgeLegendItem}><i style={{ ...styles.edgeDot, background: edgeColor("table") }} />表格</span>
            <span style={styles.edgeLegendItem}><i style={{ ...styles.edgeDot, background: edgeColor("pdf") }} />PDF / 頁面</span>
            <span style={styles.edgeLegendItem}><i style={{ ...styles.edgeDot, background: edgeColor("params") }} />參數</span>
            <span style={styles.edgeLegendItem}><i style={{ ...styles.edgeDot, background: edgeColor("result") }} />結果</span>
            <span style={styles.edgeLegendItem}><i style={{ ...styles.edgeDot, background: edgeColor("action") }} />動作</span>
          </div>
        </div>
        <div style={styles.toolbarActions}>
          {dataOriginLabel ? <span style={styles.toolbarPill}>{dataOriginLabel}</span> : null}
          <span style={styles.toolbarPill}>{visibleRows.length || 0} / {rows.length || 0} 頁</span>
          <button className="action-button" type="button" onClick={() => setViewResetKey((current) => current + 1)}>
            <RefreshCcw size={14} />
            <span>重置視圖</span>
          </button>
          <button className="action-button" type="button" onClick={() => onRunNode?.("batch_detect")} disabled={!rerunEnabled || jobRunning}>
            <RefreshCcw size={14} />
            <span>重跑判讀</span>
          </button>
        </div>
      </div>
      <div style={styles.canvasShell}>
        <ReactFlow<GuideNode, Edge>
          key={viewResetKey}
          nodes={graph.nodes}
          edges={graph.edges}
          nodeTypes={{ guideNode: GuideNodeCard }}
          defaultViewport={DEFAULT_VIEWPORT}
          nodesConnectable={false}
          nodesDraggable
          edgesFocusable={false}
          onlyRenderVisibleElements
          deleteKeyCode={null}
          onNodeClick={(_event, node) => {
            node.data.onSelectNode?.(node.data.nodeId);
            if (node.data.row) {
              node.data.onSelectRow?.(node.data.row.id);
            }
          }}
        >
          <Background color="rgba(47,245,200,0.12)" gap={22} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </section>
  );
}

function GuideNodeCard({ data, selected }: NodeProps<GuideNode>) {
  const active = data.active || selected;
  const cardTone = cardToneStyle(data.tone, data.dirty, data.guarded);
  const width = nodeWidth(data.size);
  return (
    <article style={{ ...styles.node, ...cardTone, outline: active ? "2px solid rgba(47,245,200,0.78)" : "0", width }}>
      <Handle type="target" position={Position.Left} style={styles.handle} />
      <Handle type="source" position={Position.Right} style={styles.handle} />
      <span style={styles.portLabelLeft}>{data.portIn}</span>
      <span style={styles.portLabelRight}>{data.portOut}</span>
      <NodeHeader data={data} />
      {data.kind === "source" ? <SourceBody data={data} /> : null}
      {data.kind === "config" ? <ConfigBody data={data} /> : null}
      {data.kind === "listPreview" ? <PreviewRows data={data} /> : null}
      {data.kind === "page" ? <PageBody data={data} /> : null}
      {data.kind === "roi" ? <RoiBody data={data} /> : null}
      {data.kind === "result" ? <ResultBody data={data} /> : null}
      {data.kind === "output" ? <OutputBody data={data} /> : null}
      {data.kind === "summary" ? <SummaryBody data={data} /> : null}
      {data.kind === "action" ? <ActionBody data={data} /> : null}
      {data.kind === "more" ? <MoreBody data={data} /> : null}
    </article>
  );
}

function NodeHeader({ data }: { data: GuideNodeData }) {
  return (
    <div style={styles.nodeHeader}>
      <span style={{ ...styles.nodeIcon, color: toneColor(data.tone) }}>{data.icon}</span>
      <div style={styles.nodeTitle}>
        <strong>{data.title}</strong>
        <small style={styles.nodeSubtitle}>{data.subtitle}</small>
        {data.meta ? <em>{data.meta}</em> : null}
      </div>
      <span style={{ ...styles.statusPill, borderColor: toneColor(data.tone), color: toneColor(data.tone) }}>
        {data.guarded ? "需確認" : data.dirty ? "待重跑" : statusToneLabel(data.tone)}
      </span>
    </div>
  );
}

function SourceBody({ data }: { data: GuideNodeData }) {
  return (
    <div style={styles.nodeBody}>
      <Notice notice={data.notice} />
      <KeyRows rows={data.rows} />
    </div>
  );
}

function ConfigBody({ data }: { data: GuideNodeData }) {
  return (
    <div style={styles.nodeBody}>
      <Notice notice={data.notice} />
      <KeyRows rows={data.rows} />
    </div>
  );
}

function PreviewRows({ data }: { data: GuideNodeData }) {
  return (
    <div style={styles.nodeBody}>
      <Notice notice={data.notice} />
      <KeyRows rows={data.rows} />
      {data.rowCount && data.rowCount > data.rows.length ? <span style={styles.moreHint}>尚有 {data.rowCount - data.rows.length} 筆</span> : null}
    </div>
  );
}

function PageBody({ data }: { data: GuideNodeData }) {
  const row = data.row;
  return (
    <div style={styles.nodeBody}>
      <div style={styles.pageBadgeRow}>
        <span style={styles.pageBadge}>P{row?.page ?? "-"}</span>
        <strong title={row?.source_name}>{row?.source_name ?? "等待拆頁"}</strong>
      </div>
      <KeyRows rows={data.rows} />
      <button className="action-button nodrag" type="button" onClick={(event) => {
        event.stopPropagation();
        if (row) {
          data.onSelectRow?.(row.id);
        }
        data.onSelectNode?.("roi_calib");
      }}>
        <Eye size={13} />
        <span>載入此頁</span>
      </button>
    </div>
  );
}

function RoiBody({ data }: { data: GuideNodeData }) {
  const [activeRoi, setActiveRoi] = useState<"drawing" | "serial">("serial");
  const row = data.row;
  const region = activeRoi === "serial" ? data.serialRegion : data.drawingRegion;
  const selected = data.selectedPreview ? data.preview : null;
  const lowConfidence = Boolean(row?.confidence && row.confidence < data.threshold);
  const trial = data.pageTrial;
  const setRegion = (next: IsoRegion) => {
    data.onWorkflowInputChange?.("roi_calib", activeRoi === "serial" ? "serial_region" : "drawing_region", next);
  };
  const updateField = (field: keyof IsoRegion, value: number) => setRegion({ ...region, [field]: clampRegion(value) });
  return (
    <div style={styles.roiBody}>
      <div style={styles.roiStatusBar}>
        <span>頁 {row?.page ?? "-"} / {data.pageCount || "-"}</span>
        <strong title={row?.source_name}>{row?.source_name ?? "等待頁面"}</strong>
        <em style={{ ...styles.roiStateChip, color: toneColor(lowConfidence ? "warn" : trial ? "ready" : "idle"), borderColor: toneColor(lowConfidence ? "warn" : trial ? "ready" : "idle") }}>
          {lowConfidence ? "低信心" : trial ? "已有試判" : "待試判"}
        </em>
      </div>
      <div
        className="nodrag"
        style={styles.roiPreview}
        onPointerDown={(event) => event.stopPropagation()}
      >
        {selected ? (
          <div style={styles.previewCanvas}>
            <img src={data.preview?.page.image} alt={data.preview?.source_name ?? row?.source_name ?? "PDF preview"} style={styles.previewImage} />
            <RoiOverlay
              activeRoi={activeRoi}
              drawingRegion={data.drawingRegion}
              editable
              onChange={(target, next) => data.onWorkflowInputChange?.("roi_calib", target === "serial" ? "serial_region" : "drawing_region", next)}
              onSelect={setActiveRoi}
              serialRegion={data.serialRegion}
            />
          </div>
        ) : (
          <div style={styles.previewEmpty}>
            {data.previewBusy ? "載入預覽中" : data.previewError || "點頁面節點載入預覽"}
          </div>
        )}
      </div>
      <div style={styles.roiControls} className="nodrag" onPointerDown={(event) => event.stopPropagation()}>
        <div style={styles.segmented}>
          <button style={activeRoi === "serial" ? styles.segmentActive : styles.segment} type="button" onClick={() => setActiveRoi("serial")}>流水號 ROI</button>
          <button style={activeRoi === "drawing" ? styles.segmentActive : styles.segment} type="button" onClick={() => setActiveRoi("drawing")}>圖號 ROI</button>
        </div>
        {(["left", "top", "width", "height"] as Array<keyof IsoRegion>).map((field) => (
          <label style={styles.sliderRow} key={field}>
            <span>{regionFieldLabel(field)}</span>
            <input
              type="range"
              min={field === "width" || field === "height" ? 0.05 : 0}
              max={field === "left" || field === "top" ? 0.95 : 1}
              step={0.01}
              value={region[field]}
              onChange={(event) => updateField(field, Number(event.target.value))}
            />
            <strong>{region[field].toFixed(2)}</strong>
          </label>
        ))}
        <label style={styles.sliderRow}>
          <span>信心門檻</span>
          <input
            type="range"
            min={0.1}
            max={0.99}
            step={0.01}
            value={data.threshold}
            onChange={(event) => data.onWorkflowInputChange?.("roi_calib", "confidence_threshold", Number(event.target.value))}
          />
          <strong>{Math.round(data.threshold * 100)}%</strong>
        </label>
        <div style={styles.roiTrialBox}>
          <SearchCheck size={13} />
          <strong>試判</strong>
          <span>{data.pageTrialBusy ? "判讀中" : trial ? `${trial.serial || "未取得"} (${Math.round(trial.confidence * 100)}%)` : "尚未執行"}</span>
        </div>
        <div style={styles.cropGrid}>
          <Crop title="流水號裁切" image={selected ? data.preview?.serial_crop.image : ""} />
          <Crop title="圖號裁切" image={selected ? data.preview?.drawing_crop.image : ""} />
        </div>
        <button
          className="action-button"
          type="button"
          onClick={() => data.onWorkflowInputChange?.("roi_calib", activeRoi === "serial" ? "serial_region" : "drawing_region", activeRoi === "serial" ? DEFAULT_SERIAL_REGION : DEFAULT_DRAWING_REGION)}
        >
          <RefreshCcw size={13} />
          <span>重設目前 ROI</span>
        </button>
        <div style={styles.actionGrid}>
          <button className="action-button" type="button" disabled={!row || !data.onRefreshPreview} title="只重新整理本頁預覽與裁切，不執行文字判讀。" onClick={() => {
            if (row) {
              data.onRefreshPreview?.(row.id);
            }
          }}>
            <Eye size={13} />
            <span>只更新預覽</span>
          </button>
          <button className="action-button" type="button" disabled={!row || data.pageTrialBusy || !data.onRunPageTrial} title="只對目前頁做一次判讀，結果先留在畫面上，不改批次結果。" onClick={() => {
            if (row) {
              data.onRunPageTrial?.(row.id);
            }
          }}>
            <SearchCheck size={13} />
            <span>判讀此頁</span>
          </button>
          <button className="action-button" type="button" disabled={!row || !data.onRunFrom} title={`用目前 ROI 與門檻重跑下游，會重新處理 ${data.pageCount ?? 0} 頁。`} onClick={() => data.onRunFrom?.("batch_detect")}>
            <RefreshCcw size={13} />
            <span>重跑下游</span>
          </button>
        </div>
      </div>
    </div>
  );
}

function ResultBody({ data }: { data: GuideNodeData }) {
  const row = data.row;
  const trial = data.pageTrial;
  const trialDiffers = Boolean(trial && row && trial.serial && trial.serial !== row.serial);
  return (
    <div style={styles.nodeBody}>
      <Notice notice={data.notice} />
      <KeyRows rows={data.rows} />
      {trial ? (
        <div style={trialDiffers ? styles.trialWarnBox : styles.trialReadyBox}>
          <SearchCheck size={14} />
          <strong>頁 {trial.page} 試判：{trial.serial || "未取得"}</strong>
          <span>{trialDiffers ? "建議重跑下游" : "與批次一致"}</span>
        </div>
      ) : null}
      {data.selectedPreview && data.preview?.vision ? (
        <div style={styles.visionBox}>
          <SearchCheck size={14} />
          <strong>{data.preview.vision.text || "未取得"}</strong>
          <span>{Math.round(data.preview.vision.confidence * 100)}%</span>
        </div>
      ) : null}
    </div>
  );
}

function OutputBody({ data }: { data: GuideNodeData }) {
  return (
    <div style={styles.nodeBody}>
      <Notice notice={data.notice} />
      <KeyRows rows={data.rows} />
    </div>
  );
}

function SummaryBody({ data }: { data: GuideNodeData }) {
  return (
    <div style={styles.nodeBody}>
      <Notice notice={data.notice} />
      <KeyRows rows={data.rows} />
    </div>
  );
}

function ActionBody({ data }: { data: GuideNodeData }) {
  return (
    <div style={styles.nodeBody}>
      <Notice notice={data.notice} />
      <KeyRows rows={data.rows} />
      <button className="action-button nodrag" type="button" onClick={(event) => {
        event.stopPropagation();
        data.onRunNode?.(data.nodeId);
      }}>
        <SearchCheck size={13} />
        <span>{data.nodeId === "export_csv" ? "匯出草稿" : "預覽更名"}</span>
      </button>
    </div>
  );
}

function MoreBody({ data }: { data: GuideNodeData }) {
  return (
    <div style={styles.nodeBody}>
      <span style={styles.moreHint}>先顯示 {data.visibleCount ?? 0} / {data.rowCount ?? 0} 頁</span>
      <button className="action-button nodrag" type="button" onClick={(event) => {
        event.stopPropagation();
        data.onLoadMore?.();
      }}>
        <MoreHorizontal size={13} />
        <span>再展開 10 頁</span>
      </button>
    </div>
  );
}

function KeyRows({ rows }: { rows: GuideNodeData["rows"] }) {
  return (
    <div style={styles.keyRows}>
      {rows.map((row, index) => (
        <span style={styles.keyRow} key={`${row.label}-${index}`}>
          <em>{row.label}</em>
          <strong style={{ color: row.tone ? toneColor(row.tone) : undefined }} title={row.value}>{row.value || "-"}</strong>
        </span>
      ))}
      {!rows.length ? <span style={styles.muted}>等待資料</span> : null}
    </div>
  );
}

function Notice({ notice }: { notice?: GuideNodeData["notice"] }) {
  if (!notice) {
    return null;
  }
  return (
    <span style={{ ...styles.notice, borderColor: toneColor(notice.tone), color: toneColor(notice.tone) }} title={notice.title}>
      {notice.text}
    </span>
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

type BuildGuideGraphArgs = Pick<
  WorkflowGuideCanvasProps,
  "onRefreshPreview" | "onRunFrom" | "onRunNode" | "onRunPageTrial" | "onSelectNode" | "onSelectRow" | "onWorkflowInputChange" | "pageTrialBusyId" | "pageTrials" | "plan" | "preview" | "previewBusy" | "previewError" | "rerunEnabled" | "runLog" | "selectedNodeId" | "selectedRowId" | "workflowInputs"
> & {
  dirty: Set<string>;
  drawingRegion: IsoRegion;
  isoPath: string;
  jobRunning: boolean;
  onLoadMore: () => void;
  pageFolder: string;
  pattern: string;
  pdfPath: string;
  rows: IsoPlanRow[];
  serialRegion: IsoRegion;
  source: IsoWorkflowPlan["source"] | undefined;
  threshold: number;
  visibleLimit: number;
  visibleRows: IsoPlanRow[];
  workFolder: string;
};

function buildGuideGraph(args: BuildGuideGraphArgs): { edges: Edge[]; nodes: GuideNode[] } {
  const nodes: GuideNode[] = [];
  const edges: Edge[] = [];
  const addNode = (node: Omit<GuideNode, "type">) => {
    nodes.push({ ...node, type: "guideNode" });
  };
  const addEdge = (source: string, target: string, options: GuideEdgeOptions) => {
    const edgeTone = edgeToneStyle(options.kind, options.dirty);
    edges.push({
      id: `${source}->${target}`,
      source,
      target,
      animated: Boolean(options.animated),
      markerEnd: { type: MarkerType.ArrowClosed, color: edgeTone.stroke },
      type: "smoothstep",
      style: edgeTone,
    });
  };

  const common = (nodeId: string, kind: WorkflowNodeKind, title: string, icon: ReactNode, tone: GuideNodeData["tone"], rows: GuideNodeData["rows"] = []): GuideNodeData => ({
    active: args.selectedNodeId === nodeId,
    dirty: args.dirty.has(nodeId),
    drawingRegion: args.drawingRegion,
    icon,
    kind,
    nodeId,
    onLoadMore: args.onLoadMore,
    onRefreshPreview: args.onRefreshPreview,
    onRunFrom: args.rerunEnabled && !args.jobRunning ? args.onRunFrom : undefined,
    onRunNode: args.rerunEnabled && !args.jobRunning ? args.onRunNode : undefined,
    onRunPageTrial: args.jobRunning ? undefined : args.onRunPageTrial,
    onSelectNode: args.onSelectNode,
    onSelectRow: args.onSelectRow,
    onWorkflowInputChange: args.onWorkflowInputChange,
    pageCount: args.rows.length || args.source?.pdf_count || 0,
    preview: args.preview,
    previewBusy: Boolean(args.previewBusy),
    previewError: args.previewError || "",
    portIn: portLabel(kind, "in"),
    portOut: portLabel(kind, "out"),
    rows,
    selectedPreview: false,
    serialRegion: args.serialRegion,
    size: nodeSize(kind),
    subtitle: nodeSubtitle(title, kind),
    threshold: args.threshold,
    title,
    tone,
  });

  addNode({
    id: "source",
    position: { x: GUIDE_LAYOUT.sourceX, y: GUIDE_LAYOUT.sourceY },
    data: {
      ...common("discover", "source", "選取工作區", <FolderOpen size={17} />, args.workFolder || args.pdfPath || args.isoPath ? "ready" : "idle", sourceReadinessRows(args)),
      meta: "流程入口",
      notice: args.workFolder || args.pdfPath || args.isoPath
        ? { text: "來源已連到下游節點", tone: "ready", title: "工作區會同時餵給 ISO 清單與合併 PDF 分支。" }
        : { text: "從這裡開始：點選此卡設定工作資料夾", tone: "warn", title: "選好工作資料夾後，ISO 清單與 PDF 分支會依序亮起。" },
      portIn: "使用者選擇",
      portOut: "來源路徑",
    },
  });

  addNode({
    id: "iso_list",
    position: { x: GUIDE_LAYOUT.branchX, y: GUIDE_LAYOUT.isoY },
    data: {
      ...common("load_table", "config", "ISO 清單", <Table2 size={17} />, args.isoPath || args.source?.iso_list ? "ready" : "idle", [
        { label: "檔案", value: compactOrEmpty(args.isoPath || args.source?.iso_list || "") },
        { label: "資料列", value: args.source?.record_count ? `${args.source.record_count} 列` : "等待載入", tone: args.source?.record_count ? "ready" : "idle" },
      ]),
      notice: args.isoPath || args.source?.iso_list
        ? undefined
        : { text: "等待工作區提供 ISO 清單", tone: "idle" },
      portIn: "清單檔",
      portOut: "表格資料",
    },
  });
  addNode({
    id: "sheet",
    position: { x: GUIDE_LAYOUT.configX, y: GUIDE_LAYOUT.isoY },
    data: {
      ...common("load_table", "config", "工作表", <Table2 size={17} />, args.source?.sheet_name ? "ready" : "idle", [
        { label: "名稱", value: stringValue(args.workflowInputs.sheet_name ?? args.source?.sheet_name) || "自動" },
        { label: "候選", value: String(args.source?.sheet_options?.length ?? 0) },
      ]),
      notice: args.source?.sheet_options?.length ? undefined : { text: "載入清單後可確認工作表", tone: "idle" },
      portIn: "表格資料",
      portOut: "工作表",
    },
  });
  addNode({
    id: "columns",
    position: { x: GUIDE_LAYOUT.configX + 300, y: GUIDE_LAYOUT.isoY },
    data: {
      ...common("load_table", "config", "欄位設定", <SlidersHorizontal size={17} />, args.source?.serial_col || args.source?.line_col ? "ready" : "idle", [
        { label: "流水號欄", value: stringValue(args.workflowInputs.serial_col ?? args.source?.serial_col) || "自動" },
        { label: "圖號欄", value: stringValue(args.workflowInputs.line_col ?? args.source?.line_col) || "自動" },
      ]),
      notice: args.source?.serial_col || args.source?.line_col
        ? undefined
        : { text: "欄位會先自動猜測，必要時再修正", tone: "idle" },
      portIn: "工作表",
      portOut: "欄位對應",
    },
  });
  addNode({
    id: "pattern",
    position: { x: GUIDE_LAYOUT.configX + 600, y: GUIDE_LAYOUT.isoY },
    data: {
      ...common("roi_calib", "config", "命名格式", <FileText size={17} />, args.pattern ? "ready" : "idle", [
        { label: "格式", value: args.pattern },
        { label: "示例", value: sampleNameFromPattern(args.pattern) },
      ]),
      portIn: "欄位對應",
      portOut: "命名規則",
    },
  });
  addNode({
    id: "iso_preview",
    position: { x: GUIDE_LAYOUT.pageX, y: GUIDE_LAYOUT.isoY + 185 },
    data: {
      ...common("load_table", "listPreview", "ISO 預覽", <Eye size={17} />, args.source?.record_count ? "ready" : "idle", isoPreviewRows(args.source)),
      notice: args.source?.record_count ? undefined : { text: "載入後會列出前幾筆清單欄位", tone: "idle" },
      portIn: "命名規則",
      portOut: "ISO 候選",
      rowCount: args.source?.record_count ?? 0,
    },
  });

  addNode({
    id: "combine_pdf",
    position: { x: GUIDE_LAYOUT.branchX, y: GUIDE_LAYOUT.pdfY },
    data: {
      ...common("split", "config", "合併 PDF", <FileText size={17} />, args.pdfPath || args.source?.combine_pdf ? "ready" : "idle", [
        { label: "檔案", value: compactOrEmpty(args.pdfPath || args.source?.combine_pdf || "") },
        { label: "頁數", value: args.source?.pdf_count || args.rows.length ? `${args.source?.pdf_count ?? args.rows.length} 頁` : "等待載入", tone: args.source?.pdf_count || args.rows.length ? "ready" : "idle" },
      ]),
      notice: args.pdfPath || args.source?.combine_pdf
        ? undefined
        : { text: "等待工作區提供合併 PDF", tone: "idle" },
      portIn: "PDF 檔",
      portOut: "合併頁面",
    },
  });
  addNode({
    id: "split",
    position: { x: GUIDE_LAYOUT.configX, y: GUIDE_LAYOUT.pdfY },
    data: {
      ...common("split", "config", "分割工具", <Layers3 size={17} />, args.source?.page_folder || args.pageFolder ? "ready" : "idle", [
        { label: "輸出", value: compactOrEmpty(args.pageFolder || args.source?.page_folder || "") },
        { label: "狀態", value: runStatus(args.runLog, "split") },
      ]),
      notice: args.source?.page_folder || args.pageFolder
        ? { text: "拆頁檔可沿用或重新產生", tone: "ready" }
        : { text: "會寫入單頁 PDF 到拆頁資料夾", tone: "warn" },
      portIn: "合併頁面",
      portOut: "單頁 PDF",
    },
  });
  addNode({
    id: "split_preview",
    position: { x: GUIDE_LAYOUT.pageX, y: GUIDE_LAYOUT.pdfY },
    data: {
      ...common("split", "listPreview", "拆頁預覽", <Eye size={17} />, args.rows.length ? "ready" : "idle", args.rows.slice(0, 5).map((row) => ({ label: `P${row.page}`, value: row.source_name }))),
      notice: args.rows.length ? undefined : { text: "分割完成後會列出前幾頁", tone: "idle" },
      portIn: "單頁 PDF",
      portOut: "頁面卡",
      rowCount: args.rows.length || args.source?.pdf_count || 0,
    },
  });

  addEdge("source", "iso_list", { kind: "source" });
  addEdge("iso_list", "sheet", { kind: "table" });
  addEdge("sheet", "columns", { kind: "table" });
  addEdge("columns", "pattern", { kind: "params" });
  addEdge("pattern", "iso_preview", { kind: "params" });
  addEdge("source", "combine_pdf", { kind: "source" });
  addEdge("combine_pdf", "split", { kind: "pdf" });
  addEdge("split", "split_preview", { kind: "pdf" });

  if (!args.visibleRows.length) {
    addNode({
      id: "page_waiting",
      position: { x: GUIDE_LAYOUT.pageX + 390, y: GUIDE_LAYOUT.pdfY },
      data: {
        ...common("split", "page", "P001 頁面", <FileText size={17} />, "idle", [
          { label: "來源", value: "等待拆頁" },
          { label: "狀態", value: "準備顯示前 10 頁", tone: "idle" },
        ]),
        notice: { text: "合併 PDF 分割後，這裡會展開頁面卡", tone: "idle" },
      },
    });
    addNode({
      id: "roi_waiting",
      position: { x: GUIDE_LAYOUT.roiX, y: GUIDE_LAYOUT.pdfY - 120 },
      data: {
        ...common(
          "roi_calib",
          "roi",
          "P001 ROI 調校",
          <SlidersHorizontal size={17} />,
          "idle",
          roiStateRows(args.serialRegion, args.drawingRegion, false),
        ),
        notice: { text: "載入頁面後可框流水號與圖號", tone: "idle" },
      },
    });
    addNode({
      id: "result_waiting",
      position: { x: GUIDE_LAYOUT.resultX, y: GUIDE_LAYOUT.pdfY },
      data: {
        ...common("batch_detect", "result", "P001 判讀結果", <SearchCheck size={17} />, "idle", [
          { label: "流水號", value: "待判讀", tone: "idle" },
          { label: "信心", value: "等待 ROI", tone: "idle" },
        ]),
        notice: { text: "只在按下判讀或重跑時執行", tone: "warn" },
      },
    });
    addNode({
      id: "output_waiting",
      position: { x: GUIDE_LAYOUT.outputX, y: GUIDE_LAYOUT.pdfY },
      data: {
        ...common("batch_detect", "output", "P001 命名合成", <FileText size={17} />, "idle", [
          { label: "ISO 圖號", value: "等待清單", tone: "idle" },
          { label: "新檔名", value: "等待判讀", tone: "idle" },
        ]),
        notice: { text: "ISO 清單與判讀結果會在這裡合流", tone: "idle" },
      },
    });
    addEdge("split_preview", "page_waiting", { kind: "pdf" });
    addEdge("page_waiting", "roi_waiting", { kind: "pdf" });
    addEdge("roi_waiting", "result_waiting", { kind: "params", dirty: args.dirty.has("roi_calib") });
    addEdge("result_waiting", "output_waiting", { kind: "rows" });
  }

  args.visibleRows.forEach((row, index) => {
    const y = GUIDE_LAYOUT.rowStartY + index * GUIDE_LAYOUT.rowGapY;
    const pageId = `page_${row.page}`;
    const roiId = `roi_${row.page}`;
    const resultId = `result_${row.page}`;
    const outputId = `output_${row.page}`;
    const selectedPreview = args.preview?.source_path === row.source_path;
    const lowConfidence = Number(row.confidence || 0) > 0 && Number(row.confidence || 0) < args.threshold;
    const rowTone = row.status === "blocked" ? "danger" : row.status === "warn" || lowConfidence ? "warn" : row.status === "ready" ? "ready" : "idle";
    const commonRow = (nodeId: string, kind: WorkflowNodeKind, title: string, icon: ReactNode, tone: GuideNodeData["tone"], rows: GuideNodeData["rows"]): GuideNodeData => ({
      ...common(nodeId, kind, title, icon, tone, rows),
      active: args.selectedRowId === row.id || args.selectedNodeId === nodeId,
      dirty: args.dirty.has(nodeId) || args.dirty.has("roi_calib"),
      pageTrial: args.pageTrials?.[row.id],
      pageTrialBusy: args.pageTrialBusyId === row.id,
      row,
      selectedPreview,
    });

    addNode({
      id: pageId,
      position: { x: GUIDE_LAYOUT.pageX + 390, y },
      data: commonRow("split", "page", `P${row.page} 頁面`, <FileText size={17} />, rowTone, [
        { label: "來源", value: row.source_name },
        { label: "狀態", value: rowStatusLabel(row.status), tone: rowTone },
      ]),
    });
    addNode({
      id: roiId,
      position: { x: GUIDE_LAYOUT.roiX, y: y - 110 },
      data: commonRow("roi_calib", "roi", `P${row.page} ROI 調校`, <SlidersHorizontal size={17} />, args.dirty.has("roi_calib") ? "warn" : selectedPreview ? "ready" : "idle", [
        ...roiStateRows(args.serialRegion, args.drawingRegion, selectedPreview),
      ]),
    });
    addNode({
      id: resultId,
      position: { x: GUIDE_LAYOUT.resultX, y },
      data: {
        ...commonRow("batch_detect", "result", `P${row.page} 判讀結果`, <SearchCheck size={17} />, rowTone, [
          { label: "流水號", value: row.serial || "未判讀", tone: row.serial ? "ready" : "warn" },
          { label: "信心", value: row.confidence ? `${Math.round(row.confidence * 100)}%` : "未判讀", tone: lowConfidence ? "warn" : row.confidence ? "ready" : "idle" },
          { label: "訊息", value: row.vision_message || "-" },
        ]),
        notice: trialNotice(args.pageTrials?.[row.id], row),
      },
    });
    addNode({
      id: outputId,
      position: { x: GUIDE_LAYOUT.outputX, y },
      data: commonRow("batch_detect", "output", `P${row.page} 命名合成`, <FileText size={17} />, rowTone, [
        { label: "ISO 圖號", value: row.line_no || "-" },
        { label: "新檔名", value: row.new_name || "尚未產生" },
      ]),
    });
    addEdge("split_preview", pageId, { kind: "pdf" });
    addEdge(pageId, roiId, { kind: "pdf", animated: args.selectedRowId === row.id });
    addEdge(roiId, resultId, { kind: "params", animated: args.jobRunning, dirty: args.dirty.has("roi_calib") });
    addEdge(resultId, outputId, { kind: "rows", animated: args.jobRunning });
    addEdge("iso_preview", outputId, { kind: "table" });
  });

  const summaryX = GUIDE_LAYOUT.mergeX;
  const summaryY = GUIDE_LAYOUT.sourceY + 50;
  addNode({
    id: "pilot",
    position: { x: summaryX, y: summaryY },
    data: {
      ...common("pilot", "summary", "結果表 / Pilot", <CircleCheck size={17} />, args.plan?.summary.blocked ? "danger" : args.plan?.summary.warn ? "warn" : args.plan?.summary.total ? "ready" : "idle", [
        { label: "可更名", value: String(args.plan?.summary.ready ?? 0), tone: "ready" },
        { label: "待確認", value: String(args.plan?.summary.warn ?? 0), tone: args.plan?.summary.warn ? "warn" : "idle" },
        { label: "阻擋", value: String(args.plan?.summary.blocked ?? 0), tone: args.plan?.summary.blocked ? "danger" : "idle" },
        { label: "檢查", value: `${args.plan?.pilot_results?.length ?? 0} 項` },
      ]),
      notice: args.plan?.summary.total ? undefined : { text: "命名列生成後會跑 P01-P15 檢查", tone: "idle" },
    },
  });
  addNode({
    id: "export_csv",
    position: { x: GUIDE_LAYOUT.actionX, y: GUIDE_LAYOUT.sourceY - 80 },
    data: {
      ...common("export_csv", "action", "匯出 CSV", <FileText size={17} />, "warn", [
        { label: "權限", value: "需確認", tone: "warn" },
        { label: "列數", value: String(args.plan?.summary.selected ?? 0) },
      ]),
      guarded: true,
      notice: { text: "鎖定：只會開啟既有匯出確認", tone: "warn", title: "這張卡不會繞過受控流程；點擊後仍走既有確認與審計路徑。" },
      portIn: "命名列",
      portOut: "CSV 檔",
    },
  });
  addNode({
    id: "apply_rename",
    position: { x: GUIDE_LAYOUT.actionX, y: GUIDE_LAYOUT.sourceY + 220 },
    data: {
      ...common("apply_rename", "action", "套用更名", <AlertTriangle size={17} />, "warn", [
        { label: "權限", value: "需確認", tone: "warn" },
        { label: "可更名", value: String(args.plan?.summary.ready ?? 0), tone: args.plan?.summary.ready ? "ready" : "idle" },
        { label: "阻擋", value: String(args.plan?.summary.blocked ?? 0), tone: args.plan?.summary.blocked ? "danger" : "idle" },
      ]),
      guarded: true,
      notice: { text: "鎖定：需預覽並確認才會套用", tone: "warn", title: "更名仍走既有確認對話框；阻擋列不會被直接套用。" },
      portIn: "命名列",
      portOut: "更名結果",
    },
  });
  if (args.visibleRows.length) {
    for (const row of args.visibleRows) {
      addEdge(`output_${row.page}`, "pilot", { kind: "result" });
    }
  } else {
    addEdge("output_waiting", "pilot", { kind: "result" });
  }
  addEdge("pilot", "export_csv", { kind: "action" });
  addEdge("pilot", "apply_rename", { kind: "action" });

  if (args.visibleLimit < args.rows.length) {
    addNode({
      id: "load_more",
      position: { x: GUIDE_LAYOUT.pageX + 390, y: GUIDE_LAYOUT.rowStartY + args.visibleRows.length * GUIDE_LAYOUT.rowGapY },
      data: {
        ...common("split", "more", "更多頁面", <MoreHorizontal size={17} />, "idle", []),
        rowCount: args.rows.length,
        visibleCount: args.visibleRows.length,
      },
    });
    addEdge("split_preview", "load_more", { kind: "pdf" });
  }

  return { edges, nodes };
}

function nodeWidth(size: WorkflowNodeSize): number {
  if (size === "XL") return 560;
  if (size === "L") return 340;
  if (size === "S") return 230;
  return 290;
}

function nodeSize(kind: WorkflowNodeKind): WorkflowNodeSize {
  if (kind === "roi") return "XL";
  if (kind === "listPreview" || kind === "summary") return "L";
  if (kind === "config") return "S";
  return "M";
}

function nodeSubtitle(title: string, kind: WorkflowNodeKind): string {
  if (title === "選取工作區") return "流程從這裡收集來源";
  if (title === "ISO 清單") return "讀取清單與列數";
  if (title === "工作表") return "選擇資料表分頁";
  if (title === "欄位設定") return "指定流水號與圖號";
  if (title === "命名格式") return "定義輸出檔名";
  if (title === "合併 PDF") return "提供原始圖面";
  if (title === "分割工具") return "拆成單頁 PDF";
  if (title.includes("ROI")) return "框出要判讀的區域";
  if (title.includes("判讀")) return "影像判讀與信心值";
  if (title.includes("命名")) return "合成新檔名";
  if (kind === "listPreview") return "抽樣檢查資料";
  if (kind === "summary") return "匯總檢查結果";
  if (kind === "action") return "需要授權才執行";
  if (kind === "more") return "延遲展開避免一次載入過多";
  return "節點處理步驟";
}

function portLabel(kind: WorkflowNodeKind, side: "in" | "out"): string {
  if (kind === "source") return side === "in" ? "選擇" : "來源";
  if (kind === "config") return side === "in" ? "資料" : "設定";
  if (kind === "listPreview") return side === "in" ? "資料" : "預覽";
  if (kind === "page") return side === "in" ? "PDF" : "頁面";
  if (kind === "roi") return side === "in" ? "頁面" : "ROI";
  if (kind === "result") return side === "in" ? "ROI" : "判讀";
  if (kind === "output") return side === "in" ? "判讀" : "檔名";
  if (kind === "summary") return side === "in" ? "結果" : "彙整";
  if (kind === "action") return side === "in" ? "彙整" : "檔案";
  return side === "in" ? "輸入" : "輸出";
}

function cardToneStyle(tone: GuideNodeData["tone"], dirty: boolean, guarded = false): CSSProperties {
  if (guarded) {
    return {
      background: "linear-gradient(180deg, rgba(28,32,31,0.96), rgba(8,11,10,0.96))",
      borderColor: "rgba(220,235,228,0.34)",
      boxShadow: "0 0 0 1px rgba(220,235,228,0.06), 0 18px 40px rgba(0,0,0,0.38)",
    };
  }
  if (dirty) {
    return {
      background: "linear-gradient(180deg, rgba(54,43,13,0.96), rgba(15,12,5,0.96))",
      borderColor: "rgba(255,209,102,0.82)",
      borderStyle: "dashed",
      boxShadow: "0 0 0 1px rgba(255,209,102,0.12), 0 18px 40px rgba(0,0,0,0.38)",
    };
  }
  if (tone === "danger") {
    return {
      background: "linear-gradient(180deg, rgba(46,18,18,0.96), rgba(14,7,7,0.96))",
      borderColor: "rgba(255,155,155,0.72)",
      boxShadow: "0 0 0 1px rgba(255,155,155,0.10), 0 18px 40px rgba(0,0,0,0.38)",
    };
  }
  if (tone === "warn") {
    return {
      background: "linear-gradient(180deg, rgba(48,38,12,0.96), rgba(14,12,5,0.96))",
      borderColor: "rgba(255,209,102,0.62)",
      boxShadow: "0 0 0 1px rgba(255,209,102,0.08), 0 18px 40px rgba(0,0,0,0.38)",
    };
  }
  if (tone === "ready") {
    return {
      background: "linear-gradient(180deg, rgba(12,47,39,0.96), rgba(5,18,15,0.96))",
      borderColor: "rgba(47,245,200,0.60)",
      boxShadow: "0 0 0 1px rgba(47,245,200,0.08), 0 18px 40px rgba(0,0,0,0.38)",
    };
  }
  return {
    background: "linear-gradient(180deg, rgba(16,29,26,0.96), rgba(5,14,12,0.96))",
    borderColor: "rgba(220,235,228,0.22)",
    boxShadow: "0 16px 36px rgba(0,0,0,0.34)",
  };
}

function edgeToneStyle(kind: GuideEdgeKind, dirty = false): CSSProperties {
  const color = dirty ? "#ffd166" : edgeColor(kind);
  return {
    opacity: dirty ? 0.95 : 0.76,
    stroke: color,
    strokeDasharray: dirty ? "7 7" : undefined,
    strokeWidth: dirty ? 2.4 : 2,
  };
}

function edgeColor(kind: GuideEdgeKind): string {
  if (kind === "pdf") return "#59b7ff";
  if (kind === "table") return "#2ff5c8";
  if (kind === "params") return "#9aa6b2";
  if (kind === "rows") return "#ffd166";
  if (kind === "result") return "#c084fc";
  if (kind === "action") return "#ff9b9b";
  return "rgba(220,235,228,0.62)";
}

function sourceReadinessRows(args: BuildGuideGraphArgs): GuideNodeData["rows"] {
  return [
    { label: "工作資料夾", value: compactOrEmpty(args.workFolder), tone: args.workFolder ? "ready" : "warn" },
    { label: "合併 PDF", value: readinessText(Boolean(args.pdfPath || args.source?.combine_pdf)), tone: args.pdfPath || args.source?.combine_pdf ? "ready" : "warn" },
    { label: "ISO 清單", value: readinessText(Boolean(args.isoPath || args.source?.iso_list)), tone: args.isoPath || args.source?.iso_list ? "ready" : "warn" },
    { label: "拆頁資料夾", value: args.pageFolder || args.source?.page_folder ? "已建立" : "尚未建立", tone: args.pageFolder || args.source?.page_folder ? "ready" : "idle" },
  ];
}

function readinessText(ready: boolean): string {
  return ready ? "已找到" : "待選擇";
}

function sampleNameFromPattern(pattern: string): string {
  return pattern
    .replace(/\{serial\}/g, "A123")
    .replace(/\{line\}/g, "PIPE-01")
    .replace(/\{file_basename\}/g, "圖面001")
    .replace(/\{page\}/g, "001");
}

function roiStateRows(serialRegion: IsoRegion, drawingRegion: IsoRegion, selectedPreview: boolean): GuideNodeData["rows"] {
  return [
    { label: "預覽", value: selectedPreview ? "已載入" : "點頁面載入", tone: selectedPreview ? "ready" : "idle" },
    { label: "流水號 ROI", value: regionConfigured(serialRegion, DEFAULT_SERIAL_REGION) ? "已調校" : "預設區域", tone: regionConfigured(serialRegion, DEFAULT_SERIAL_REGION) ? "ready" : "idle" },
    { label: "圖號 ROI", value: regionConfigured(drawingRegion, DEFAULT_DRAWING_REGION) ? "已調校" : "預設區域", tone: regionConfigured(drawingRegion, DEFAULT_DRAWING_REGION) ? "ready" : "idle" },
  ];
}

function trialNotice(trial: IsoPageTrial | undefined, row: IsoPlanRow): GuideNodeData["notice"] | undefined {
  if (!trial) {
    return undefined;
  }
  if (trial.serial && trial.serial !== row.serial) {
    return {
      text: `頁 ${trial.page} 有新試判，與上次批次結果不同，建議重跑下游。`,
      tone: "warn",
    };
  }
  return {
    text: "本頁試判與批次結果一致。",
    tone: "ready",
  };
}

function regionConfigured(region: IsoRegion, fallback: IsoRegion): boolean {
  return (
    Math.abs(region.left - fallback.left) > 0.005 ||
    Math.abs(region.top - fallback.top) > 0.005 ||
    Math.abs(region.width - fallback.width) > 0.005 ||
    Math.abs(region.height - fallback.height) > 0.005
  );
}

function isoPreviewRows(source: IsoWorkflowPlan["source"] | undefined): GuideNodeData["rows"] {
  const rows: GuideNodeData["rows"] = [];
  if (source?.headers?.length) {
    rows.push(...source.headers.slice(0, 4).map((header, index) => ({ label: `欄 ${index + 1}`, value: header })));
  }
  if (source?.sheet_options?.length) {
    rows.push(...source.sheet_options.slice(0, 2).map((sheet) => ({ label: "工作表", value: sheet })));
  }
  if (!rows.length && source?.iso_candidates?.length) {
    rows.push(...source.iso_candidates.slice(0, 3).map((path) => ({ label: "候選", value: compactPath(path) })));
  }
  return rows;
}

function runStatus(runLog: IsoNodeWorkflowRunLog | null, nodeId: string): string {
  const status = runLog?.nodes?.[nodeId]?.status;
  if (status === "success") return "完成";
  if (status === "failed") return "失敗";
  if (status === "blocked") return "阻擋";
  return "待命";
}

function rowStatusLabel(status: IsoPlanRow["status"]): string {
  if (status === "ready") return "通過";
  if (status === "warn") return "待確認";
  if (status === "blocked") return "阻擋";
  return status || "待命";
}

function statusToneLabel(tone: GuideNodeData["tone"]): string {
  if (tone === "ready") return "完成";
  if (tone === "warn") return "注意";
  if (tone === "danger") return "阻擋";
  return "待命";
}

function toneColor(tone: GuideNodeData["tone"]): string {
  if (tone === "danger") return "#ff9b9b";
  if (tone === "warn") return "#ffd166";
  if (tone === "ready") return "#2ff5c8";
  return "rgba(220,235,228,0.58)";
}

function compactOrEmpty(value: string): string {
  return value ? compactPath(value) : "未選擇";
}

function stringValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  return typeof value === "string" ? value : String(value);
}

function numberOrDefault(value: unknown, fallback: number): number {
  const numeric = typeof value === "number" ? value : typeof value === "string" && value !== "" ? Number(value) : NaN;
  return Number.isFinite(numeric) ? numeric : fallback;
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

function regionFieldLabel(field: keyof IsoRegion): string {
  if (field === "left") return "左距";
  if (field === "top") return "上距";
  if (field === "width") return "寬度";
  return "高度";
}

function clampRegion(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(1, Math.max(0, value));
}

const styles = {
  actionGrid: {
    display: "grid",
    gap: 6,
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
    minWidth: 0,
  },
  canvasShell: {
    background: "rgba(3,10,8,0.82)",
    border: "1px solid rgba(47,245,200,0.18)",
    borderRadius: 10,
    height: "clamp(720px, 74vh, 980px)",
    minHeight: 680,
    overflow: "hidden",
    width: "100%",
  },
  crop: {
    background: "rgba(255,255,255,0.035)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 7,
    display: "grid",
    gap: 5,
    minHeight: 70,
    minWidth: 0,
    overflow: "hidden",
    padding: 6,
  },
  cropGrid: {
    display: "grid",
    gap: 6,
    gridTemplateColumns: "1fr 1fr",
    minWidth: 0,
  },
  edgeDot: {
    borderRadius: 999,
    display: "inline-block",
    height: 7,
    width: 18,
  },
  edgeLegend: {
    alignItems: "center",
    display: "flex",
    flexWrap: "wrap",
    gap: 7,
    marginTop: 3,
    minWidth: 0,
  },
  edgeLegendItem: {
    alignItems: "center",
    color: "rgba(220,252,244,0.58)",
    display: "inline-flex",
    fontSize: 10,
    fontWeight: 900,
    gap: 5,
    whiteSpace: "nowrap",
  },
  handle: {
    background: "#2ff5c8",
    border: "0",
    height: 9,
    zIndex: 5,
    width: 9,
  },
  flowLegend: {
    alignItems: "center",
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
    marginTop: 4,
    minWidth: 0,
  },
  keyRow: {
    background: "rgba(0,0,0,0.18)",
    border: "1px solid rgba(255,255,255,0.075)",
    borderRadius: 7,
    display: "grid",
    gap: 3,
    minWidth: 0,
    padding: "6px 7px",
  },
  keyRows: {
    display: "grid",
    gap: 6,
    minWidth: 0,
  },
  lanePill: {
    background: "rgba(47,245,200,0.07)",
    border: "1px solid rgba(47,245,200,0.18)",
    borderRadius: 999,
    color: "rgba(220,252,244,0.70)",
    fontSize: 11,
    fontWeight: 900,
    padding: "3px 7px",
  },
  moreHint: {
    color: "rgba(220,235,228,0.62)",
    fontSize: 12,
    fontWeight: 800,
  },
  muted: {
    color: "rgba(220,235,228,0.58)",
    fontSize: 12,
  },
  node: {
    border: "1px solid",
    borderRadius: 8,
    color: "#dffcf4",
    display: "grid",
    gap: 9,
    minHeight: 145,
    padding: 10,
    position: "relative",
  },
  nodeBody: {
    display: "grid",
    gap: 8,
    minWidth: 0,
  },
  notice: {
    background: "rgba(255,255,255,0.035)",
    border: "1px solid",
    borderRadius: 7,
    display: "block",
    fontSize: 11,
    fontWeight: 900,
    lineHeight: 1.35,
    padding: "6px 7px",
  },
  nodeHeader: {
    alignItems: "center",
    borderBottom: "1px solid rgba(255,255,255,0.08)",
    display: "grid",
    gap: 8,
    gridTemplateColumns: "auto minmax(0, 1fr) auto",
    minWidth: 0,
    paddingBottom: 8,
  },
  nodeIcon: {
    display: "inline-flex",
  },
  nodeTitle: {
    display: "grid",
    gap: 2,
    minWidth: 0,
  },
  nodeSubtitle: {
    color: "rgba(220,235,228,0.58)",
    fontSize: 10,
    fontWeight: 850,
    lineHeight: 1.2,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  pageBadge: {
    alignItems: "center",
    background: "rgba(47,245,200,0.10)",
    border: "1px solid rgba(47,245,200,0.38)",
    borderRadius: 999,
    color: "#2ff5c8",
    display: "inline-flex",
    fontSize: 12,
    fontWeight: 950,
    height: 28,
    justifyContent: "center",
    width: 42,
  },
  pageBadgeRow: {
    alignItems: "center",
    display: "grid",
    gap: 8,
    gridTemplateColumns: "auto minmax(0, 1fr)",
    minWidth: 0,
  },
  portLabelLeft: {
    background: "rgba(3,10,8,0.94)",
    border: "1px solid rgba(47,245,200,0.22)",
    borderRadius: 999,
    color: "rgba(220,252,244,0.72)",
    fontSize: 10,
    fontWeight: 900,
    left: -34,
    lineHeight: 1,
    padding: "4px 6px",
    pointerEvents: "none",
    position: "absolute",
    top: "50%",
    transform: "translateY(-50%)",
    whiteSpace: "nowrap",
    zIndex: 4,
  },
  portLabelRight: {
    background: "rgba(3,10,8,0.94)",
    border: "1px solid rgba(47,245,200,0.22)",
    borderRadius: 999,
    color: "rgba(220,252,244,0.72)",
    fontSize: 10,
    fontWeight: 900,
    lineHeight: 1,
    padding: "4px 6px",
    pointerEvents: "none",
    position: "absolute",
    right: -34,
    top: "50%",
    transform: "translateY(-50%)",
    whiteSpace: "nowrap",
    zIndex: 4,
  },
  previewCanvas: {
    background: "rgba(0,0,0,0.22)",
    borderRadius: 7,
    maxHeight: 210,
    overflow: "hidden",
    position: "relative",
  },
  previewEmpty: {
    alignItems: "center",
    background: "rgba(255,255,255,0.035)",
    border: "1px dashed rgba(220,235,228,0.16)",
    borderRadius: 7,
    color: "rgba(220,235,228,0.64)",
    display: "flex",
    justifyContent: "center",
    minHeight: 180,
    padding: 10,
  },
  previewImage: {
    display: "block",
    width: "100%",
  },
  roiBody: {
    display: "grid",
    gap: 8,
    gridTemplateColumns: "minmax(0, 1.15fr) minmax(220px, 0.85fr)",
    minWidth: 0,
  },
  roiControls: {
    display: "grid",
    gap: 7,
    minWidth: 0,
  },
  roiPreview: {
    minWidth: 0,
  },
  roiStateChip: {
    border: "1px solid",
    borderRadius: 999,
    fontSize: 10,
    fontStyle: "normal",
    fontWeight: 950,
    padding: "3px 7px",
    whiteSpace: "nowrap",
  },
  roiStatusBar: {
    alignItems: "center",
    background: "rgba(255,255,255,0.035)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 7,
    display: "grid",
    gap: 7,
    gridColumn: "1 / -1",
    gridTemplateColumns: "auto minmax(0, 1fr) auto",
    minWidth: 0,
    padding: "7px 8px",
  },
  roiTrialBox: {
    alignItems: "center",
    background: "rgba(47,245,200,0.07)",
    border: "1px solid rgba(47,245,200,0.18)",
    borderRadius: 7,
    color: "#dffcf4",
    display: "grid",
    fontSize: 11,
    fontWeight: 900,
    gap: 7,
    gridTemplateColumns: "auto auto minmax(0, 1fr)",
    minWidth: 0,
    padding: "7px 8px",
  },
  segment: {
    background: "rgba(255,255,255,0.035)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 7,
    color: "rgba(220,235,228,0.68)",
    cursor: "pointer",
    fontWeight: 900,
    padding: "6px 8px",
  },
  segmentActive: {
    background: "rgba(47,245,200,0.16)",
    border: "1px solid rgba(47,245,200,0.28)",
    borderRadius: 7,
    color: "#2ff5c8",
    cursor: "pointer",
    fontWeight: 900,
    padding: "6px 8px",
  },
  segmented: {
    display: "grid",
    gap: 6,
    gridTemplateColumns: "1fr 1fr",
  },
  shell: {
    background: "rgba(3,10,8,0.72)",
    border: "1px solid rgba(47,245,200,0.22)",
    borderRadius: 10,
    display: "grid",
    gap: 10,
    minWidth: 0,
    padding: 10,
  },
  sliderRow: {
    alignItems: "center",
    color: "rgba(220,235,228,0.72)",
    display: "grid",
    fontSize: 11,
    fontWeight: 900,
    gap: 7,
    gridTemplateColumns: "48px minmax(0, 1fr) 40px",
    minWidth: 0,
  },
  statusPill: {
    border: "1px solid",
    borderRadius: 999,
    fontSize: 11,
    fontWeight: 950,
    padding: "3px 7px",
    whiteSpace: "nowrap",
  },
  toolbar: {
    alignItems: "center",
    background: "rgba(47,245,200,0.07)",
    border: "1px solid rgba(47,245,200,0.16)",
    borderRadius: 9,
    display: "flex",
    gap: 12,
    justifyContent: "space-between",
    minWidth: 0,
    padding: "9px 11px",
  },
  toolbarActions: {
    alignItems: "center",
    display: "flex",
    flexWrap: "wrap",
    gap: 7,
    justifyContent: "flex-end",
  },
  toolbarPill: {
    border: "1px solid rgba(47,245,200,0.22)",
    borderRadius: 999,
    color: "#2ff5c8",
    fontSize: 12,
    fontWeight: 900,
    padding: "5px 9px",
  },
  toolbarText: {
    display: "grid",
    gap: 2,
    minWidth: 0,
  },
  trialReadyBox: {
    alignItems: "center",
    background: "rgba(47,245,200,0.07)",
    border: "1px solid rgba(47,245,200,0.20)",
    borderRadius: 8,
    color: "#2ff5c8",
    display: "grid",
    gap: 7,
    gridTemplateColumns: "auto minmax(0, 1fr) auto",
    minWidth: 0,
    padding: 8,
  },
  trialWarnBox: {
    alignItems: "center",
    background: "rgba(255,209,102,0.08)",
    border: "1px solid rgba(255,209,102,0.24)",
    borderRadius: 8,
    color: "#ffd166",
    display: "grid",
    gap: 7,
    gridTemplateColumns: "auto minmax(0, 1fr) auto",
    minWidth: 0,
    padding: 8,
  },
  visionBox: {
    alignItems: "center",
    background: "rgba(255,209,102,0.08)",
    border: "1px solid rgba(255,209,102,0.22)",
    borderRadius: 8,
    color: "#ffd166",
    display: "grid",
    gap: 7,
    gridTemplateColumns: "auto minmax(0, 1fr) auto",
    minWidth: 0,
    padding: 8,
  },
} satisfies Record<string, CSSProperties>;
