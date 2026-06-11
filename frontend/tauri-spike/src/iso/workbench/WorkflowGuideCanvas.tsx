import {
  AlertTriangle,
  ChevronRight,
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
  dirtyNodeIds?: string[];
  job: IsoNodeWorkflowJobPayload | null;
  onRunFrom?: (nodeId: string) => void;
  onRunNode?: (nodeId: string) => void;
  onSelectNode?: (nodeId: string) => void;
  onSelectRow?: (rowId: string) => void;
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

const PAGE_CHUNK_SIZE = 10;

export function WorkflowGuideCanvas({
  dirtyNodeIds = [],
  job,
  onRunFrom,
  onRunNode,
  onSelectNode,
  onSelectRow,
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
  const rows = plan?.rows ?? [];
  const visibleRows = rows.slice(0, visibleLimit);
  const source = plan?.source;
  const activeRow = rows.find((row) => row.id === selectedRowId) ?? rows[0] ?? null;
  const serialRegion = regionOrDefault(workflowInputs.serial_region ?? source?.serial_region, DEFAULT_SERIAL_REGION);
  const drawingRegion = regionOrDefault(workflowInputs.drawing_region ?? source?.drawing_region, DEFAULT_DRAWING_REGION);
  const threshold = numberOrDefault(workflowInputs.confidence_threshold ?? source?.confidence_threshold, 0.7);
  const pdfPath = stringValue(workflowInputs.combine_pdf ?? source?.combine_pdf);
  const workFolder = stringValue(workflowInputs.work_folder ?? source?.work_folder);
  const isoPath = stringValue(workflowInputs.iso_list ?? source?.iso_list);
  const pageFolder = stringValue(workflowInputs.page_folder ?? source?.page_folder);
  const pattern = stringValue(workflowInputs.pattern ?? source?.pattern ?? "{serial}--{line}.pdf");
  const jobRunning = Boolean(job && ["queued", "running", "cancel_requested"].includes(job.state));
  const dirty = useMemo(() => new Set(dirtyNodeIds), [dirtyNodeIds]);

  useEffect(() => {
    setVisibleLimit(PAGE_CHUNK_SIZE);
  }, [rows.length, source?.combine_pdf, source?.iso_list]);

  const selectNode = (nodeId: string) => {
    onSelectNode?.(nodeId);
  };
  const selectPage = (row: IsoPlanRow) => {
    onSelectRow?.(row.id);
    onSelectNode?.("roi_calib");
  };

  return (
    <section style={styles.shell}>
      <div style={styles.legendBar}>
        <span>流程卡片</span>
        <strong>工作區 → 清單 / PDF → 預覽 → 逐頁調校 → 判讀輸出</strong>
        <em>{rows.length ? `目前展開 ${visibleRows.length} / ${rows.length} 頁` : jobRunning ? "背景執行中" : "等待產生資料"}</em>
      </div>

      <div style={styles.sourceMap}>
        <FlowCard
          active={selectedNodeId === "pdf_source" || selectedNodeId === "discover"}
          icon={<FolderOpen size={17} />}
          nodeId="discover"
          onSelect={selectNode}
          status={source || workFolder ? "已選取" : "待選取"}
          title="選取工作區"
          tone={source || workFolder ? "ready" : "idle"}
        >
          <KeyValue label="工作區" value={compactOrEmpty(workFolder)} />
          <KeyValue label="PDF" value={compactOrEmpty(pdfPath)} />
          <KeyValue label="ISO 清單" value={compactOrEmpty(isoPath)} />
        </FlowCard>

        <ChevronRight style={styles.mainArrow} size={22} />

        <div style={styles.branchStack}>
          <BranchPanel
            active={selectedNodeId === "load_table"}
            icon={<Table2 size={17} />}
            meta={`${source?.record_count ?? 0} 列`}
            onSelect={() => selectNode("load_table")}
            title="ISO 清單"
          >
            <div style={styles.detailGrid}>
              <MiniCard dirty={dirty.has("load_table")} label="工作表" value={stringValue(workflowInputs.sheet_name ?? source?.sheet_name) || "自動"} />
              <MiniCard dirty={dirty.has("load_table")} label="流水號欄" value={stringValue(workflowInputs.serial_col ?? source?.serial_col) || "自動"} />
              <MiniCard dirty={dirty.has("load_table")} label="圖號 / 檔名欄" value={stringValue(workflowInputs.line_col ?? source?.line_col) || "自動"} />
              <MiniCard dirty={dirty.has("roi_calib")} label="命名格式" value={pattern} />
            </div>
            <PreviewList
              emptyText="等待 ISO 樣本"
              rows={isoPreviewRows(source)}
              title="ISO 預覽"
              total={source?.record_count ?? 0}
            />
          </BranchPanel>

          <BranchPanel
            active={selectedNodeId === "split"}
            icon={<FileText size={17} />}
            meta={`${source?.pdf_count ?? rows.length ?? 0} 頁`}
            onSelect={() => selectNode("split")}
            title="合併 PDF"
          >
            <FlowCard
              active={false}
              compact
              icon={<Layers3 size={15} />}
              nodeId="split"
              onSelect={selectNode}
              status={runStatus(runLog, "split")}
              title="分割工具"
              tone={source?.page_folder || pageFolder ? "ready" : "idle"}
            >
              <KeyValue label="來源 PDF" value={compactOrEmpty(pdfPath)} />
              <KeyValue label="拆頁資料夾" value={compactOrEmpty(pageFolder || source?.page_folder || "")} />
            </FlowCard>
            <PreviewList
              emptyText="等待拆頁清單"
              rows={rows.slice(0, 5).map((row) => ({ label: `P${row.page}`, value: row.source_name }))}
              title="拆頁預覽"
              total={rows.length || source?.pdf_count || 0}
            />
          </BranchPanel>
        </div>
      </div>

      <section style={styles.pageSection}>
        <div style={styles.sectionHead}>
          <div>
            <span>逐頁卡片</span>
            <strong>單頁預覽 · 手動更新</strong>
          </div>
          <div style={styles.sectionActions}>
            <button className="action-button" type="button" onClick={() => selectNode("batch_detect")} disabled={jobRunning}>
              <SearchCheck size={14} />
              <span>查看判讀</span>
            </button>
            <button className="action-button" type="button" onClick={() => onRunNode?.("batch_detect")} disabled={!rerunEnabled || jobRunning}>
              <RefreshCcw size={14} />
              <span>重跑判讀</span>
            </button>
          </div>
        </div>

        <div style={styles.pageRows}>
          {visibleRows.map((row) => (
            <PageFlow
              active={row.id === activeRow?.id}
              drawingRegion={drawingRegion}
              key={row.id}
              onRunFrom={onRunFrom}
              onSelect={() => selectPage(row)}
              preview={preview}
              previewBusy={previewBusy}
              previewError={previewError}
              rerunEnabled={rerunEnabled && !jobRunning}
              row={row}
              selectedPreview={preview?.source_path === row.source_path}
              serialRegion={serialRegion}
              threshold={threshold}
            />
          ))}
          {!visibleRows.length ? <div style={styles.emptyRows}>等待拆頁結果</div> : null}
        </div>

        {visibleLimit < rows.length ? (
          <button style={styles.moreButton} type="button" onClick={() => setVisibleLimit((current) => Math.min(rows.length, current + PAGE_CHUNK_SIZE))}>
            <MoreHorizontal size={15} />
            <span>再顯示 {Math.min(PAGE_CHUNK_SIZE, rows.length - visibleLimit)} 筆</span>
          </button>
        ) : rows.length > PAGE_CHUNK_SIZE ? (
          <span style={styles.allShown}>已顯示全部 {rows.length} 筆</span>
        ) : null}
      </section>
    </section>
  );
}

function PageFlow({
  active,
  drawingRegion,
  onRunFrom,
  onSelect,
  preview,
  previewBusy,
  previewError,
  rerunEnabled,
  row,
  selectedPreview,
  serialRegion,
  threshold,
}: {
  active: boolean;
  drawingRegion: IsoRegion;
  onRunFrom?: (nodeId: string) => void;
  onSelect: () => void;
  preview: IsoPreviewPayload | null;
  previewBusy: boolean;
  previewError: string;
  rerunEnabled: boolean;
  row: IsoPlanRow;
  selectedPreview: boolean;
  serialRegion: IsoRegion;
  threshold: number;
}) {
  const confidence = Number(row.confidence || 0);
  return (
    <article style={{ ...styles.pageFlow, borderColor: active ? "rgba(47,245,200,0.74)" : "rgba(47,245,200,0.18)" }}>
      <div style={styles.pageCard}>
        <span style={styles.pageBadge}>P{row.page}</span>
        <div style={styles.pageTitle}>
          <strong title={row.source_name}>{row.source_name}</strong>
          <em>{rowStatusLabel(row.status)}</em>
        </div>
        <KeyValue label="流水號" value={row.serial || "未判讀"} />
      </div>
      <ChevronRight style={styles.rowArrow} size={18} />
      <button style={styles.previewCard} type="button" onClick={onSelect}>
        <span style={styles.cardCaption}>
          <Eye size={14} />
          <strong>調校預覽</strong>
        </span>
        {selectedPreview && preview ? (
          <div style={styles.previewCanvas}>
            <img src={preview.page.image} alt={preview.source_name} style={styles.previewImage} />
            <RoiOverlay
              activeRoi="serial"
              drawingRegion={drawingRegion}
              editable={false}
              onChange={() => undefined}
              onSelect={() => undefined}
              serialRegion={serialRegion}
            />
          </div>
        ) : (
          <div style={styles.previewPlaceholder}>
            {active && previewBusy ? "載入預覽中" : active && previewError ? previewError : "靜態預覽待命"}
          </div>
        )}
      </button>
      <ChevronRight style={styles.rowArrow} size={18} />
      <div style={styles.roiCard}>
        <span style={styles.cardCaption}>
          <SlidersHorizontal size={14} />
          <strong>ROI 調校</strong>
        </span>
        <KeyValue label="門檻" value={`${Math.round(threshold * 100)}%`} />
        <div style={styles.cardActions}>
          <button className="action-button" type="button" onClick={onSelect}>
            <SlidersHorizontal size={13} />
            <span>開啟</span>
          </button>
          <button className="action-button" type="button" disabled={!rerunEnabled} onClick={() => onRunFrom?.("roi_calib")}>
            <SearchCheck size={13} />
            <span>判讀更新</span>
          </button>
        </div>
      </div>
      <ChevronRight style={styles.rowArrow} size={18} />
      <div style={styles.outputCard}>
        <span style={styles.cardCaption}>
          {row.status === "ready" ? <CircleCheck size={14} /> : <AlertTriangle size={14} />}
          <strong>輸出結果</strong>
        </span>
        <KeyValue label="新檔名" value={row.new_name || "尚未產生"} />
        <KeyValue label="信心" value={confidence ? `${Math.round(confidence * 100)}%` : "未判讀"} />
      </div>
    </article>
  );
}

function FlowCard({
  active,
  children,
  compact = false,
  icon,
  nodeId,
  onSelect,
  status,
  title,
  tone,
}: {
  active: boolean;
  children: ReactNode;
  compact?: boolean;
  icon: ReactNode;
  nodeId: string;
  onSelect: (nodeId: string) => void;
  status: string;
  title: string;
  tone: "idle" | "ready" | "warn";
}) {
  return (
    <button
      style={{ ...styles.flowCard, ...(compact ? styles.compactCard : {}), ...toneStyle(tone), outline: active ? "2px solid rgba(47,245,200,0.75)" : "0" }}
      type="button"
      onClick={() => onSelect(nodeId)}
    >
      <span style={styles.cardTop}>
        <span style={styles.cardIcon}>{icon}</span>
        <strong>{title}</strong>
        <em>{status}</em>
      </span>
      <span style={styles.cardBody}>{children}</span>
    </button>
  );
}

function BranchPanel({
  active,
  children,
  icon,
  meta,
  onSelect,
  title,
}: {
  active: boolean;
  children: ReactNode;
  icon: ReactNode;
  meta: string;
  onSelect: () => void;
  title: string;
}) {
  return (
    <section style={{ ...styles.branchPanel, outline: active ? "2px solid rgba(47,245,200,0.55)" : "0" }}>
      <button style={styles.branchHead} type="button" onClick={onSelect}>
        <span>{icon}</span>
        <strong>{title}</strong>
        <em>{meta}</em>
      </button>
      {children}
    </section>
  );
}

function MiniCard({ dirty, label, value }: { dirty?: boolean; label: string; value: string }) {
  return (
    <div style={{ ...styles.miniCard, borderColor: dirty ? "rgba(255,209,102,0.48)" : "rgba(255,255,255,0.08)" }}>
      <span>{label}</span>
      <strong title={value}>{value || "-"}</strong>
    </div>
  );
}

function PreviewList({
  emptyText,
  rows,
  title,
  total,
}: {
  emptyText: string;
  rows: Array<{ label: string; value: string }>;
  title: string;
  total: number;
}) {
  return (
    <div style={styles.previewList}>
      <div style={styles.previewListHead}>
        <strong>{title}</strong>
        {total > rows.length ? <em>+{total - rows.length} more</em> : null}
      </div>
      {rows.length ? rows.slice(0, 5).map((row, index) => (
        <span style={styles.previewRow} key={`${row.label}-${index}`}>
          <em>{row.label}</em>
          <strong title={row.value}>{row.value}</strong>
        </span>
      )) : <span style={styles.emptyPreviewText}>{emptyText}</span>}
    </div>
  );
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <span style={styles.keyValue}>
      <em>{label}</em>
      <strong title={value}>{value || "-"}</strong>
    </span>
  );
}

function isoPreviewRows(source: IsoWorkflowPlan["source"] | undefined): Array<{ label: string; value: string }> {
  const rows: Array<{ label: string; value: string }> = [];
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

function toneStyle(tone: "idle" | "ready" | "warn"): CSSProperties {
  if (tone === "ready") {
    return { borderColor: "rgba(47,245,200,0.36)", color: "#dffcf4" };
  }
  if (tone === "warn") {
    return { borderColor: "rgba(255,209,102,0.38)", color: "#fff4cf" };
  }
  return { borderColor: "rgba(255,255,255,0.1)", color: "rgba(220,235,228,0.68)" };
}

const styles = {
  allShown: {
    color: "rgba(220,235,228,0.58)",
    fontSize: 12,
    justifySelf: "center",
  },
  branchHead: {
    alignItems: "center",
    background: "rgba(47,245,200,0.08)",
    border: "1px solid rgba(47,245,200,0.16)",
    borderRadius: 8,
    color: "#dffcf4",
    cursor: "pointer",
    display: "grid",
    gap: 8,
    gridTemplateColumns: "auto minmax(0, 1fr) auto",
    minWidth: 0,
    padding: "9px 10px",
    textAlign: "left",
  },
  branchPanel: {
    background: "rgba(0,0,0,0.16)",
    border: "1px solid rgba(47,245,200,0.16)",
    borderRadius: 10,
    display: "grid",
    gap: 9,
    minWidth: 0,
    padding: 10,
  },
  branchStack: {
    display: "grid",
    gap: 12,
    gridTemplateColumns: "repeat(2, minmax(320px, 1fr))",
    minWidth: 0,
  },
  cardActions: {
    display: "grid",
    gap: 6,
    gridTemplateColumns: "1fr 1fr",
    minWidth: 0,
  },
  cardBody: {
    display: "grid",
    gap: 6,
    minWidth: 0,
  },
  cardCaption: {
    alignItems: "center",
    color: "#dffcf4",
    display: "flex",
    gap: 7,
    minWidth: 0,
  },
  cardIcon: {
    color: "#2ff5c8",
    display: "inline-flex",
  },
  cardTop: {
    alignItems: "center",
    display: "grid",
    gap: 7,
    gridTemplateColumns: "auto minmax(0, 1fr) auto",
    minWidth: 0,
  },
  compactCard: {
    minHeight: 0,
    padding: 9,
  },
  detailGrid: {
    display: "grid",
    gap: 8,
    gridTemplateColumns: "repeat(4, minmax(110px, 1fr))",
    minWidth: 0,
  },
  emptyPreviewText: {
    color: "rgba(220,235,228,0.58)",
    fontSize: 12,
  },
  emptyRows: {
    alignItems: "center",
    border: "1px dashed rgba(220,235,228,0.18)",
    borderRadius: 10,
    color: "rgba(220,235,228,0.62)",
    display: "flex",
    minHeight: 86,
    padding: 14,
  },
  flowCard: {
    background: "rgba(5,20,16,0.86)",
    border: "1px solid",
    borderRadius: 10,
    boxShadow: "0 14px 34px rgba(0,0,0,0.26)",
    cursor: "pointer",
    display: "grid",
    gap: 10,
    minHeight: 176,
    minWidth: 0,
    padding: 12,
    textAlign: "left",
  },
  keyValue: {
    background: "rgba(0,0,0,0.18)",
    border: "1px solid rgba(255,255,255,0.075)",
    borderRadius: 7,
    display: "grid",
    gap: 3,
    minWidth: 0,
    padding: "6px 7px",
  },
  legendBar: {
    alignItems: "center",
    background: "rgba(47,245,200,0.07)",
    border: "1px solid rgba(47,245,200,0.16)",
    borderRadius: 9,
    display: "grid",
    gap: 8,
    gridTemplateColumns: "auto minmax(0, 1fr) auto",
    minWidth: 0,
    padding: "9px 11px",
  },
  mainArrow: {
    alignSelf: "center",
    color: "rgba(47,245,200,0.58)",
    justifySelf: "center",
  },
  miniCard: {
    background: "rgba(255,255,255,0.035)",
    border: "1px solid",
    borderRadius: 8,
    display: "grid",
    gap: 4,
    minWidth: 0,
    padding: "8px 9px",
  },
  moreButton: {
    alignItems: "center",
    background: "rgba(47,245,200,0.10)",
    border: "1px solid rgba(47,245,200,0.24)",
    borderRadius: 8,
    color: "#dffcf4",
    cursor: "pointer",
    display: "inline-flex",
    fontWeight: 900,
    gap: 7,
    justifySelf: "center",
    padding: "8px 12px",
  },
  outputCard: {
    background: "rgba(5,20,16,0.74)",
    border: "1px solid rgba(47,245,200,0.18)",
    borderRadius: 9,
    display: "grid",
    gap: 8,
    minWidth: 0,
    padding: 10,
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
    height: 30,
    justifyContent: "center",
    width: 42,
  },
  pageCard: {
    background: "rgba(5,20,16,0.74)",
    border: "1px solid rgba(47,245,200,0.18)",
    borderRadius: 9,
    display: "grid",
    gap: 8,
    minWidth: 0,
    padding: 10,
  },
  pageFlow: {
    alignItems: "stretch",
    background: "rgba(0,0,0,0.13)",
    border: "1px solid",
    borderRadius: 11,
    display: "grid",
    gap: 8,
    gridTemplateColumns: "minmax(210px, 1fr) 22px minmax(230px, 1.1fr) 22px minmax(190px, 0.9fr) 22px minmax(230px, 1.1fr)",
    minWidth: 0,
    padding: 9,
  },
  pageRows: {
    display: "grid",
    gap: 9,
    minWidth: 0,
  },
  pageSection: {
    background: "rgba(0,0,0,0.16)",
    border: "1px solid rgba(47,245,200,0.16)",
    borderRadius: 10,
    display: "grid",
    gap: 10,
    minWidth: 0,
    padding: 10,
  },
  pageTitle: {
    display: "grid",
    gap: 3,
    minWidth: 0,
  },
  previewCanvas: {
    background: "rgba(0,0,0,0.22)",
    borderRadius: 7,
    maxHeight: 132,
    overflow: "hidden",
    position: "relative",
  },
  previewCard: {
    background: "rgba(5,20,16,0.74)",
    border: "1px solid rgba(47,245,200,0.18)",
    borderRadius: 9,
    color: "#dffcf4",
    cursor: "pointer",
    display: "grid",
    gap: 8,
    minWidth: 0,
    padding: 10,
    textAlign: "left",
  },
  previewImage: {
    display: "block",
    width: "100%",
  },
  previewList: {
    background: "rgba(0,0,0,0.16)",
    border: "1px solid rgba(255,255,255,0.075)",
    borderRadius: 8,
    display: "grid",
    gap: 6,
    minWidth: 0,
    padding: 9,
  },
  previewListHead: {
    alignItems: "center",
    display: "flex",
    gap: 8,
    justifyContent: "space-between",
    minWidth: 0,
  },
  previewPlaceholder: {
    alignItems: "center",
    background: "rgba(255,255,255,0.035)",
    border: "1px dashed rgba(220,235,228,0.16)",
    borderRadius: 7,
    color: "rgba(220,235,228,0.64)",
    display: "flex",
    minHeight: 94,
    padding: 10,
  },
  previewRow: {
    display: "grid",
    gap: 7,
    gridTemplateColumns: "70px minmax(0, 1fr)",
    minWidth: 0,
  },
  roiCard: {
    background: "rgba(5,20,16,0.74)",
    border: "1px solid rgba(47,245,200,0.18)",
    borderRadius: 9,
    display: "grid",
    gap: 8,
    minWidth: 0,
    padding: 10,
  },
  rowArrow: {
    alignSelf: "center",
    color: "rgba(47,245,200,0.48)",
    justifySelf: "center",
  },
  sectionActions: {
    alignItems: "center",
    display: "flex",
    flexWrap: "wrap",
    gap: 7,
    justifyContent: "flex-end",
  },
  sectionHead: {
    alignItems: "center",
    display: "flex",
    gap: 12,
    justifyContent: "space-between",
    minWidth: 0,
  },
  shell: {
    background: "rgba(3,10,8,0.72)",
    border: "1px solid rgba(47,245,200,0.22)",
    borderRadius: 10,
    display: "grid",
    gap: 12,
    minHeight: 620,
    minWidth: 0,
    overflow: "hidden",
    padding: 12,
  },
  sourceMap: {
    alignItems: "stretch",
    display: "grid",
    gap: 10,
    gridTemplateColumns: "minmax(240px, 0.58fr) 26px minmax(0, 1.9fr)",
    minWidth: 0,
  },
} satisfies Record<string, CSSProperties>;
