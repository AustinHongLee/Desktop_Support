import {
  AlertTriangle,
  Activity,
  Bot,
  Boxes,
  Braces,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  ClipboardCheck,
  Cpu,
  Clock3,
  Crosshair,
  FileText,
  FileJson,
  FileSearch,
  FolderOpen,
  GripVertical,
  GitBranch,
  Gauge,
  HardDrive,
  Home,
  Layers3,
  Maximize2,
  Minimize2,
  Network,
  PanelRightOpen,
  PlayCircle,
  Power,
  Radio,
  RefreshCcw,
  Route,
  ScanLine,
  SearchCheck,
  Server,
  Settings,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Table2,
  TerminalSquare,
  Trash2,
  WandSparkles,
  Workflow,
} from "lucide-react";
import { isTauri } from "@tauri-apps/api/core";
import { currentMonitor, getCurrentWindow, LogicalSize, PhysicalPosition } from "@tauri-apps/api/window";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  applyIsoPlan,
  cancelIsoJob,
  exportIsoDebugBundle,
  exportIsoPlanCsv,
  loadIsoJobStatus,
  loadIsoProfile,
  loadIsoPreview,
  listIsoRunLogs,
  pickIsoCombinePdf,
  pickIsoListFile,
  pickIsoPageFolder,
  pickIsoWorkFolder,
  publishIsoProfile,
  readIsoRunLog,
  replayIsoRunLog,
  revertIsoProfile,
  runIsoPlan,
  saveIsoDraftProfile,
  startIsoBatchDetect,
  type IsoJobPayload,
  type IsoPlanRow,
  type IsoProfilePayload,
  type IsoPreviewPayload,
  type IsoRegion,
  type IsoRunLogDetail,
  type IsoRunLogRef,
  type IsoRunLogSummary,
  type IsoWorkflowRequest,
  type IsoWorkflowPlan,
} from "./isoWorkflow";
import { StatusTile } from "./components/StatusTile";
import { IsoEventLog } from "./iso/components/EventLog";
import { FailureCard, type IsoFailureInfo } from "./iso/components/FailureCard";
import { ChecklistGate, IsoEmptyPlan, IsoMetric, PathPickerRow, TopSourceButton } from "./iso/components/IsoControls";
import { IsoDryRunDialog, IsoResultDialog } from "./iso/components/IsoDialogs";
import { IsoVisualPanel } from "./iso/components/IsoVisualPanel";
import { IsoPlanTable } from "./iso/components/NamingTable";
import { RunLogDrawer } from "./iso/components/RunLogDrawer";
import {
  compactPath,
  createIsoRunId,
  DEFAULT_DRAWING_REGION,
  DEFAULT_SERIAL_REGION,
  filterIsoRows,
  formatIsoFilename,
  normalizeIsoRows,
  normalizeRegion,
  parentPath,
  sortIsoRows,
  summarizeIsoRows,
  targetPathFor,
  type IsoSortMode,
} from "./iso/helpers";
import { openLegacyWorkbench, type LegacyWorkbench } from "./legacy";
import { loadShutdownReport, type SafeToKill, type ShutdownBlocker, type ShutdownSafetyReport } from "./report";

const LEVEL_ORDER: SafeToKill[] = ["Dangerous", "Unknown", "Caution", "Safe"];
const LEVEL_RANK = new Map(LEVEL_ORDER.map((level, index) => [level, index]));
const LEVEL_SCORE: Record<SafeToKill, number> = {
  Safe: 18,
  Caution: 54,
  Dangerous: 96,
  Unknown: 72,
};
type AppMode = "command" | "iso" | "shutdown" | "cleanup" | "locks";
type SurfaceMode = "dock" | "cockpit";
type DockEdge = "top" | "bottom" | "left" | "right";

const DOCK_EDGE_STORAGE_KEY = "desktop-support.dock.edge";
const DOCK_OFFSET_STORAGE_KEY = "desktop-support.dock.offset";
const DOCK_SNAP_DELAY_MS = 620;

const NAV_ITEMS: Array<{ mode: AppMode; label: string }> = [
  { mode: "command", label: "Command" },
  { mode: "iso", label: "ISO PDF" },
  { mode: "shutdown", label: "Shutdown" },
  { mode: "cleanup", label: "Cleanup" },
  { mode: "locks", label: "Locks" },
];

const MODE_META: Record<AppMode, { eyebrow: string; title: string; line: string }> = {
  command: {
    eyebrow: "Desktop support command center",
    title: "桌面輔助系統",
    line: "tools · runtime · jobs · safety cockpit",
  },
  iso: {
    eyebrow: "Tauri ISO workbench",
    title: "ISO PDF 拆頁命名",
    line: "split · plan · review · apply",
  },
  shutdown: {
    eyebrow: "Tauri shutdown cockpit",
    title: "Shutdown Safety Inspector",
    line: "scan · process guard · dependency graph",
  },
  cleanup: {
    eyebrow: "Safe cleanup command deck",
    title: "安全清除工作台",
    line: "scan · quarantine · restore · verify",
  },
  locks: {
    eyebrow: "File relationship radar",
    title: "檔案關係與鎖定雷達",
    line: "producer · reader · lock · output graph",
  },
};

const COMMAND_TOOLS = [
  { mode: "iso" as AppMode, title: "ISO PDF 拆頁命名", status: "New", detail: "Tauri workbench · split · plan · apply", tone: "ready" },
  { mode: "shutdown" as AppMode, title: "Shutdown Safety Inspector", status: "Live", detail: "Process tree · lock files · safe-to-kill policy", tone: "ready" },
  { mode: "cleanup" as AppMode, title: "安全清除工作台", status: "Bridge", detail: "Opens the existing cleanup workbench", tone: "ready" },
  { mode: "locks" as AppMode, title: "檔案關係排查", status: "Bridge", detail: "Opens the existing lock checker", tone: "ready" },
];

const COMMAND_FEED = [
  { code: "SYS", title: "Tauri shell ready", detail: "React cockpit can host multiple workbenches", tone: "ready" },
  { code: "ISO", title: "New ISO workbench online", detail: "新版已可產生命名草稿並套用勾選更名", tone: "ready" },
  { code: "PWR", title: "Shutdown backend connected", detail: "Native shell calls Python scanner through Rust command", tone: "ready" },
  { code: "NEXT", title: "React data panel pending", detail: "下一步才是把 ISO rename plan 搬進新版資料表", tone: "idle" },
];

const ISO_STEPS = [
  { label: "來源", state: "idle", meta: "select PDF" },
  { label: "拆頁", state: "idle", meta: "waiting" },
  { label: "ISO", state: "idle", meta: "select list" },
  { label: "草稿", state: "idle", meta: "dry-run plan" },
  { label: "確認", state: "idle", meta: "review rows" },
  { label: "更名", state: "idle", meta: "manual apply" },
];

const ISO_ISSUES = [
  { code: "NEW", title: "新版 ISO 工作台待命", detail: "選擇 PDF 與 ISO List 後可產生命名草稿", tone: "ready" },
  { code: "SAFE", title: "套用前先 dry-run", detail: "只會更名已勾選且通過檢查的 PDF", tone: "ready" },
  { code: "LEGACY", title: "舊工作台保留", detail: "工程師模式仍可叫出既有 PyQt workflow", tone: "ready" },
];

export default function App() {
  const [surface, setSurface] = useState<SurfaceMode>(() => initialSurface());
  const [dockCollapsed, setDockCollapsed] = useState(() => initialSurface() === "dock");
  const [mode, setMode] = useState<AppMode>("command");
  const [report, setReport] = useState<ShutdownSafetyReport | null>(null);
  const [source, setSource] = useState<"tauri" | "sample">("sample");
  const [selectedId, setSelectedId] = useState("");
  const [levelFilter, setLevelFilter] = useState<SafeToKill | "All">("All");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reportLoaded, setReportLoaded] = useState(false);
  const [dockEdge, setDockEdge] = useState<DockEdge>(() => initialDockEdge());
  const [dockOffset, setDockOffset] = useState(() => initialDockOffset());
  const surfaceRef = useRef(surface);
  const dockCollapsedRef = useRef(dockCollapsed);
  const dockDragSnapArmedRef = useRef(false);
  const dockDragSnapTimerRef = useRef<number | undefined>(undefined);
  const dockDragDisarmTimerRef = useRef<number | undefined>(undefined);

  async function refresh() {
    setBusy(true);
    setError("");
    try {
      const result = await loadShutdownReport();
      setReport(result.report);
      setSource(result.source);
      setReportLoaded(true);
      setSelectedId((current) => {
        if (current && result.report.blockers.some((blocker) => blocker.id === current)) {
          return current;
        }
        return sortBlockers(result.report.blockers)[0]?.id ?? "";
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!reportLoaded && surface === "cockpit" && mode === "shutdown") {
      void refresh();
    }
  }, [mode, reportLoaded, surface]);

  useEffect(() => {
    void applyWindowSurface(surface, dockCollapsed, dockEdge, dockOffset);
  }, [dockCollapsed, dockEdge, dockOffset, surface]);

  useEffect(() => {
    surfaceRef.current = surface;
    dockCollapsedRef.current = dockCollapsed;
  }, [dockCollapsed, surface]);

  useEffect(() => {
    if (!isTauri()) {
      return;
    }

    let unlisten: (() => void) | undefined;
    void getCurrentWindow().onCloseRequested((event) => {
      event.preventDefault();
      void getCurrentWindow().hide().catch(() => {
        setSurface("dock");
        setDockCollapsed(true);
      });
    }).then((handler) => {
      unlisten = handler;
    });

    return () => {
      unlisten?.();
    };
  }, []);

  useEffect(() => {
    function handleSurfaceEvent(event: Event) {
      const detail = (event as CustomEvent<{ surface?: SurfaceMode; collapsed?: boolean; mode?: AppMode; refresh?: boolean; quitReason?: string }>).detail;
      if (detail?.surface === "cockpit") {
        if (isAppMode(detail.mode)) {
          setMode(detail.mode);
        }
        setSurface("cockpit");
        setDockCollapsed(false);
        if (detail.refresh) {
          setReportLoaded(false);
        }
        if (detail.quitReason === "blocked") {
          setError("Quit paused: review Shutdown Safety blockers before exiting.");
        } else if (detail.quitReason === "scan_failed") {
          setError("Quit paused: Shutdown Safety scan failed. Review the cockpit before exiting.");
        }
        return;
      }
      if (detail?.surface === "dock") {
        setSurface("dock");
        setDockCollapsed(detail.collapsed ?? true);
      }
    }

    window.addEventListener("desktop-support:set-surface", handleSurfaceEvent);
    return () => {
      window.removeEventListener("desktop-support:set-surface", handleSurfaceEvent);
    };
  }, []);

  useEffect(() => {
    if (!isTauri()) {
      return;
    }

    let unlisten: (() => void) | undefined;
    void getCurrentWindow().onMoved(() => {
      if (!dockDragSnapArmedRef.current || surfaceRef.current !== "dock") {
        return;
      }

      if (dockDragSnapTimerRef.current !== undefined) {
        window.clearTimeout(dockDragSnapTimerRef.current);
      }
      dockDragSnapTimerRef.current = window.setTimeout(() => {
        dockDragSnapTimerRef.current = undefined;
        if (!dockDragSnapArmedRef.current || surfaceRef.current !== "dock") {
          return;
        }
        dockDragSnapArmedRef.current = false;
        if (dockDragDisarmTimerRef.current !== undefined) {
          window.clearTimeout(dockDragDisarmTimerRef.current);
          dockDragDisarmTimerRef.current = undefined;
        }
        void snapDraggedDockToNearestEdge(dockCollapsedRef.current).then((placement) => {
          if (!placement) {
            return;
          }
          setDockEdge(placement.edge);
          setDockOffset(placement.offset);
          saveDockPlacement(placement.edge, placement.offset);
        });
      }, DOCK_SNAP_DELAY_MS);
    }).then((handler) => {
      unlisten = handler;
    });

    return () => {
      if (dockDragSnapTimerRef.current !== undefined) {
        window.clearTimeout(dockDragSnapTimerRef.current);
      }
      if (dockDragDisarmTimerRef.current !== undefined) {
        window.clearTimeout(dockDragDisarmTimerRef.current);
        dockDragDisarmTimerRef.current = undefined;
      }
      unlisten?.();
    };
  }, []);

  const blockers = useMemo(() => {
    const items = report?.blockers ?? [];
    const filtered = levelFilter === "All" ? items : items.filter((blocker) => blocker.safe_to_kill === levelFilter);
    return sortBlockers(filtered);
  }, [levelFilter, report]);

  const selected = blockers.find((blocker) => blocker.id === selectedId) ?? blockers[0] ?? null;
  const riskScore = getRiskScore(report);
  const guardState = getGuardState(report);
  const meta = MODE_META[mode];

  function openCockpit(nextMode: AppMode = "command") {
    setMode(nextMode);
    setDockCollapsed(false);
    setSurface("cockpit");
  }

  function collapseToDock() {
    setSurface("dock");
    setDockCollapsed(true);
  }

  function beginDockDrag() {
    if (!isTauri()) {
      return;
    }
    dockDragSnapArmedRef.current = true;
    if (dockDragSnapTimerRef.current !== undefined) {
      window.clearTimeout(dockDragSnapTimerRef.current);
      dockDragSnapTimerRef.current = undefined;
    }
    if (dockDragDisarmTimerRef.current !== undefined) {
      window.clearTimeout(dockDragDisarmTimerRef.current);
    }
    dockDragDisarmTimerRef.current = window.setTimeout(() => {
      dockDragSnapArmedRef.current = false;
      dockDragDisarmTimerRef.current = undefined;
    }, 10000);
    void startWindowDrag();
  }

  if (surface === "dock") {
    return (
      <DockShell
        busy={busy}
        collapsed={dockCollapsed}
        dockEdge={dockEdge}
        guardState={guardState}
        onDockDragStart={beginDockDrag}
        openCockpit={openCockpit}
        refresh={refresh}
        report={report}
        setCollapsed={setDockCollapsed}
        source={source}
      />
    );
  }

  return (
    <main className={`shell mode-${mode}`}>
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">
            {modeIcon(mode, 20)}
          </div>
          <div className="brand-block">
            <div className="eyebrow">{meta.eyebrow}</div>
            <h1>{meta.title}</h1>
            <div className="report-line">
              {mode === "shutdown" ? `${report?.scan_reason ?? "scan"} · ${report?.created_at ?? "waiting for report"}` : meta.line}
            </div>
          </div>
        </div>
        <div className="toolbar">
          <div className="mode-switch" aria-label="Workbench mode">
            {NAV_ITEMS.map((item) => (
              <button className={mode === item.mode ? "active" : ""} key={item.mode} onClick={() => setMode(item.mode)}>
                {modeIcon(item.mode, 15)}
                <span>{item.label}</span>
              </button>
            ))}
          </div>
          {mode === "shutdown" ? (
            <>
              <button className="icon-button" onClick={refresh} disabled={busy} title="Refresh report">
                <RefreshCcw size={17} />
                <span>{busy ? "Refreshing" : "Refresh"}</span>
              </button>
              <div className={`source-pill ${source}`}>{source === "tauri" ? "Live Python report" : "Browser sample"}</div>
            </>
          ) : (
            <div className={`source-pill ${mode === "command" || mode === "iso" ? "tauri" : "bridge"}`}>
              {mode === "command" ? "Tauri shell" : mode === "iso" ? "New ISO workbench" : "Legacy bridge"}
            </div>
          )}
          <button className="icon-button" onClick={collapseToDock} title="Collapse to desktop dock">
            <Minimize2 size={16} />
            <span>Dock</span>
          </button>
        </div>
      </header>

      {error ? <div className="error-line">{error}</div> : null}

      <div className="content-scroll">
        {mode === "command" ? (
          <CommandCenter setMode={setMode} report={report} source={source} />
        ) : mode === "iso" ? (
          <IsoPdfAutopilot />
        ) : mode === "cleanup" ? (
          <SafeCleanupCockpit />
        ) : mode === "locks" ? (
          <FileLockCockpit />
        ) : (
          <ShutdownCockpit
            blockers={blockers}
            levelFilter={levelFilter}
            report={report}
            riskScore={riskScore}
            guardState={guardState}
            selected={selected}
            setLevelFilter={setLevelFilter}
            setSelectedId={setSelectedId}
            source={source}
          />
        )}
      </div>
    </main>
  );
}

function DockShell({
  busy,
  collapsed,
  dockEdge,
  guardState,
  onDockDragStart,
  openCockpit,
  refresh,
  report,
  setCollapsed,
  source,
}: {
  busy: boolean;
  collapsed: boolean;
  dockEdge: DockEdge;
  guardState: "safe" | "caution" | "danger";
  onDockDragStart: () => void;
  openCockpit: (mode?: AppMode) => void;
  refresh: () => Promise<void>;
  report: ShutdownSafetyReport | null;
  setCollapsed: (collapsed: boolean) => void;
  source: "tauri" | "sample";
}) {
  const blockerCount = report?.blockers.length ?? 0;
  const dangerCount = countLevel(report, "Dangerous");
  const cautionCount = countLevel(report, "Caution");
  const guardLabel = report ? (guardState === "danger" ? "Hold" : guardState === "caution" ? "Review" : "Clear") : "Idle";
  const contextText = report?.project_root ? compactPath(report.project_root) : "等待目前專案狀態";

  if (collapsed) {
    return (
      <main className={`dock-shell collapsed ${guardState} edge-${dockEdge}`}>
        <button
          className="dock-tail"
          onClick={() => setCollapsed(false)}
          onMouseDown={(event) => {
            if (event.altKey) {
              onDockDragStart();
              return;
            }
            setCollapsed(false);
          }}
          title="展開桌面輔助工具列"
        >
          <span
            className="dock-tail-grip"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
            }}
            onMouseDown={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onDockDragStart();
            }}
            title="拖曳位置"
          >
            <GripVertical size={15} />
            <span className="dock-tail-dot" />
          </span>
          <span className="dock-tail-label">工具</span>
          <strong>{blockerCount ? blockerCount : "OK"}</strong>
        </button>
      </main>
    );
  }

  return (
    <main className={`dock-shell expanded ${guardState} edge-${dockEdge}`}>
      <section className="dock-panel">
        <header className="dock-head">
          <div
            className="dock-drag-handle"
            onMouseDown={(event) => {
              event.preventDefault();
              onDockDragStart();
            }}
            title="拖曳位置"
          >
            <GripVertical size={16} />
          </div>
          <div className="dock-title">
            <span>Desktop Support</span>
            <strong>{guardLabel}</strong>
          </div>
          <button className="dock-icon-button" onClick={() => setCollapsed(true)} title="收合">
            <Minimize2 size={15} />
          </button>
        </header>

        <div className={`dock-status ${guardState}`}>
          <div>
            <span>Runtime guard</span>
            <strong>{report ? `${blockerCount} blockers` : "not scanned"}</strong>
          </div>
          <div className="dock-risk-dots">
            <span className="danger">{dangerCount}</span>
            <span className="warn">{cautionCount}</span>
            <span className="ready">{countLevel(report, "Safe")}</span>
          </div>
        </div>

        <div className="dock-action-grid" aria-label="Dock actions">
          <DockAction icon={<Home size={17} />} label="Command" onClick={() => openCockpit("command")} />
          <DockAction icon={<FileText size={17} />} label="ISO PDF" onClick={() => openCockpit("iso")} />
          <DockAction icon={<Power size={17} />} label="Safety" onClick={() => openCockpit("shutdown")} />
          <DockAction icon={<Trash2 size={17} />} label="Cleanup" onClick={() => openCockpit("cleanup")} />
          <DockAction icon={<FileSearch size={17} />} label="Locks" onClick={() => openCockpit("locks")} />
          <DockAction icon={<Maximize2 size={17} />} label="Cockpit" onClick={() => openCockpit("command")} />
        </div>

        <div className="dock-context">
          <span>{source === "tauri" ? "Live" : "Sample"}</span>
          <strong>{contextText}</strong>
        </div>

        <footer className="dock-foot">
          <button className="dock-secondary" onClick={refresh} disabled={busy}>
            <RefreshCcw size={14} />
            <span>{busy ? "Scan" : "Refresh"}</span>
          </button>
          <button className="dock-primary" onClick={() => openCockpit("shutdown")}>
            <ShieldCheck size={14} />
            <span>Inspect</span>
          </button>
        </footer>
      </section>
    </main>
  );
}

function DockAction({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button className="dock-action" onClick={onClick} title={label}>
      {icon}
      <span>{label}</span>
    </button>
  );
}

function ShutdownCockpit({
  blockers,
  guardState,
  levelFilter,
  report,
  riskScore,
  selected,
  setLevelFilter,
  setSelectedId,
  source,
}: {
  blockers: ShutdownBlocker[];
  guardState: "safe" | "caution" | "danger";
  levelFilter: SafeToKill | "All";
  report: ShutdownSafetyReport | null;
  riskScore: number;
  selected: ShutdownBlocker | null;
  setLevelFilter: (level: SafeToKill | "All") => void;
  setSelectedId: (id: string) => void;
  source: "tauri" | "sample";
}) {
  return (
    <>
      <section className="status-deck" aria-label="Report summary">
        <div className={`risk-core ${guardState}`}>
          <div className="risk-ring" style={{ "--risk": `${riskScore}%` } as React.CSSProperties}>
            <div>
              <span>Risk</span>
              <strong>{riskScore}</strong>
            </div>
          </div>
          <div className="risk-copy">
            <div className="eyebrow">Guard state</div>
            <h2>{guardState === "danger" ? "Hold shutdown" : guardState === "caution" ? "Manual review" : "Clear path"}</h2>
            <p>{report?.blockers.length ?? 0} blocker signals in current runtime scan</p>
          </div>
        </div>
        <div className="metric-grid">
          <Metric label="Blockers" value={report?.blockers.length ?? 0} icon={<Activity size={18} />} />
          <Metric label="Dangerous" value={countLevel(report, "Dangerous")} icon={<ShieldAlert size={18} />} tone="danger" />
          <Metric label="Caution" value={countLevel(report, "Caution")} icon={<AlertTriangle size={18} />} tone="caution" />
          <Metric label="Unknown" value={countLevel(report, "Unknown")} icon={<Braces size={18} />} tone="unknown" />
          <Metric label="Safe" value={countLevel(report, "Safe")} icon={<ShieldCheck size={18} />} tone="safe" />
        </div>
        <div className="signal-grid" aria-label="Runtime channels">
          <Signal icon={<Server size={16} />} label="Process tree" value={String(report?.blockers.length ?? 0)} />
          <Signal icon={<Radio size={16} />} label="Runtime locks" value={String(report?.blockers.reduce((total, blocker) => total + blocker.lock_files.length, 0) ?? 0)} />
          <Signal icon={<Network size={16} />} label="Graph edges" value={String(report?.blockers.reduce((total, blocker) => total + blocker.relationships.length, 0) ?? 0)} />
          <Signal icon={<Gauge size={16} />} label="Safe policy" value="armed" />
          <Signal icon={<ScanLine size={16} />} label="Scan mode" value={source} />
        </div>
      </section>

      <section className="workspace">
        <aside className="left-panel">
          <div className="panel-heading">
            <div>
              <span>Process queue</span>
              <small>{blockers.length} shown</small>
            </div>
            <select value={levelFilter} onChange={(event) => setLevelFilter(event.target.value as SafeToKill | "All")}>
              <option value="All">All levels</option>
              {LEVEL_ORDER.map((level) => (
                <option value={level} key={level}>
                  {level}
                </option>
              ))}
            </select>
          </div>
          <div className="blocker-list">
            {blockers.map((blocker) => (
              <button
                key={blocker.id}
                className={`blocker-row ${blocker.safe_to_kill.toLowerCase()} ${selected?.id === blocker.id ? "active" : ""}`}
                onClick={() => setSelectedId(blocker.id)}
              >
                <span className={`level-dot ${blocker.safe_to_kill.toLowerCase()}`} />
                <span className="row-main">
                  <span className="row-title">
                    <Cpu size={14} />
                    {blocker.process_name || "process"}
                  </span>
                  <span className="row-subtitle">
                    PID {blocker.pid} · {blocker.process_role}
                  </span>
                </span>
                <span className={`level-badge ${blocker.safe_to_kill.toLowerCase()}`}>{blocker.safe_to_kill}</span>
              </button>
            ))}
            {!blockers.length ? <div className="empty-state">No blockers in this report.</div> : null}
          </div>
        </aside>

        <section className="detail-panel">
          {selected ? <BlockerDetail blocker={selected} report={report} /> : <div className="empty-detail">Select a blocker.</div>}
        </section>
      </section>
    </>
  );
}

function CommandCenter({
  report,
  setMode,
  source,
}: {
  report: ShutdownSafetyReport | null;
  setMode: (mode: AppMode) => void;
  source: "tauri" | "sample";
}) {
  const liveBlockers = report?.blockers.length ?? 0;
  return (
    <section className="command-board">
      <div className="command-hero">
        <div>
          <div className="eyebrow">Mission control</div>
          <h2>所有工作流集中到一個桌面控制台</h2>
          <p>從 PDF 命名、關機防護、安全清除到檔案關係排查，統一用同一套 cockpit 操作。</p>
        </div>
        <div className="command-core">
          <span>System pulse</span>
          <strong>{source === "tauri" ? "LIVE" : "SIM"}</strong>
        </div>
      </div>

      <div className="command-metrics">
        <CommandMetric icon={<Workflow size={18} />} label="Workbenches" value="5" />
        <CommandMetric icon={<Shield size={18} />} label="Live blockers" value={String(liveBlockers)} />
        <CommandMetric icon={<Boxes size={18} />} label="Runtime lanes" value="4" />
        <CommandMetric icon={<Bot size={18} />} label="Automation" value="armed" />
      </div>

      <div className="command-grid">
        <section className="tool-matrix">
          <div className="section-heading">
            <div>
              <div className="eyebrow">Tool matrix</div>
              <h2>工作台入口</h2>
            </div>
          </div>
          <div className="tool-card-grid">
            {COMMAND_TOOLS.map((tool) => (
              <button className={`tool-card ${tool.tone}`} key={tool.mode} onClick={() => setMode(tool.mode)}>
                <div className="tool-card-icon">{modeIcon(tool.mode, 20)}</div>
                <div>
                  <span>{tool.status}</span>
                  <strong>{tool.title}</strong>
                  <p>{tool.detail}</p>
                </div>
                <ChevronRight size={17} />
              </button>
            ))}
          </div>
        </section>

        <aside className="ops-panel">
          <h3>Operations feed</h3>
          {COMMAND_FEED.map((item) => (
            <div className={`ops-feed-item ${item.tone}`} key={`${item.code}-${item.title}`}>
              <span>{item.code}</span>
              <div>
                <strong>{item.title}</strong>
                <p>{item.detail}</p>
              </div>
            </div>
          ))}
        </aside>
      </div>
    </section>
  );
}

function CommandMetric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="command-metric">
      <div className="metric-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SafeCleanupCockpit() {
  const bridge = useLegacyBridge("cleanup");

  return (
    <section className="feature-board cleanup-board">
      <div className="feature-hero">
        <div>
          <div className="eyebrow">Quarantine-first cleanup</div>
          <h2>安全清除工作台</h2>
          <p>先評估風險，再移入隔離區；每個動作都保留 rollback 路徑與證據。</p>
        </div>
        <div className="feature-hero-actions">
          <button className="launch-button" onClick={bridge.launch} disabled={bridge.busy}>
            <Trash2 size={18} />
            <span>{bridge.busy ? "開啟中" : "開啟工作台"}</span>
          </button>
          <BridgeStatus error={bridge.error} message={bridge.message} />
        </div>
      </div>

      <div className="feature-grid">
        <section className="cleanup-stack">
          <CleanupLane title="低風險暫存" count="128" tone="ready" detail="可隔離，保留 7 天復原" />
          <CleanupLane title="需要確認" count="16" tone="warn" detail="可能關聯快取、模型或輸出資料" />
          <CleanupLane title="阻擋項目" count="3" tone="danger" detail="檔案鎖定、profile handle 或工作中 job" />
        </section>
        <section className="cleanup-radar">
          <div className="radar-dial">
            <Sparkles size={28} />
            <strong>72</strong>
            <span>cleanup confidence</span>
          </div>
          <div className="cleanup-checks">
            <Gate label="Quarantine manifest" state="ready" />
            <Gate label="Restore path verified" state="ready" />
            <Gate label="File locks pending" state="warn" />
            <Gate label="System folders excluded" state="ready" />
          </div>
        </section>
        <aside className="cleanup-detail">
          <h3>Selected suggestion</h3>
          <KeyValue label="Layer" value="Project runtime temp" />
          <KeyValue label="Action" value="Move to quarantine" />
          <KeyValue label="Consequence" value="Job can rebuild cache on next launch" />
          <KeyValue label="Rollback" value="Available through manifest" />
        </aside>
      </div>
    </section>
  );
}

function CleanupLane({ count, detail, title, tone }: { count: string; detail: string; title: string; tone: string }) {
  return (
    <div className={`cleanup-lane ${tone}`}>
      <div>
        <span>{title}</span>
        <strong>{count}</strong>
      </div>
      <p>{detail}</p>
    </div>
  );
}

function FileLockCockpit() {
  const bridge = useLegacyBridge("locks");

  return (
    <section className="feature-board lock-board">
      <div className="feature-hero">
        <div>
          <div className="eyebrow">Relationship graph</div>
          <h2>檔案關係與鎖定雷達</h2>
          <p>用 producer / reader / temp / output 關係看懂誰咬著檔案，誰會被連帶影響。</p>
        </div>
        <div className="feature-hero-actions">
          <button className="launch-button" onClick={bridge.launch} disabled={bridge.busy}>
            <FileSearch size={18} />
            <span>{bridge.busy ? "開啟中" : "開啟檢查器"}</span>
          </button>
          <BridgeStatus error={bridge.error} message={bridge.message} />
        </div>
      </div>

      <div className="lock-grid">
        <aside className="lock-source-list">
          <StatusTile icon={<HardDrive size={18} />} title="Output" value="exports/isometric/P005.pdf" tone="warn" />
          <StatusTile icon={<Cpu size={18} />} title="Holder" value="python.exe · PID 3188" tone="warn" />
          <StatusTile icon={<FolderOpen size={18} />} title="Temp" value=".runtime/temp/iso_pages" tone="ready" />
          <StatusTile icon={<Settings size={18} />} title="Component" value="iso.naming.autopilot" tone="ready" />
        </aside>
        <section className="graph-canvas">
          <div className="graph-node producer">ISO List</div>
          <div className="graph-node worker">Detector</div>
          <div className="graph-node temp">Temp pages</div>
          <div className="graph-node output">Renamed PDF</div>
          <div className="graph-link link-a" />
          <div className="graph-link link-b" />
          <div className="graph-link link-c" />
        </section>
        <aside className="lock-findings">
          <h3>Findings</h3>
          <div className="issue-card warn">
            <CircleAlert size={16} />
            <div>
              <strong>stdout pipe active</strong>
              <span>worker process still streaming OCR logs</span>
            </div>
          </div>
          <div className="issue-card ready">
            <CircleCheck size={16} />
            <div>
              <strong>project-owned process</strong>
              <span>command line contains project root</span>
            </div>
          </div>
          <div className="issue-card danger">
            <AlertTriangle size={16} />
            <div>
              <strong>output incomplete</strong>
              <span>rename plan has not been applied yet</span>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}

function Metric({ label, value, icon, tone = "neutral" }: { label: string; value: number; icon: React.ReactNode; tone?: string }) {
  return (
    <div className={`metric ${tone}`}>
      <div className="metric-icon">{icon}</div>
      <div>
        <div className="metric-value">{value}</div>
        <div className="metric-label">{label}</div>
      </div>
    </div>
  );
}

function Signal({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="signal">
      <div className="signal-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function BlockerDetail({ blocker, report }: { blocker: ShutdownBlocker; report: ShutdownSafetyReport | null }) {
  return (
    <div className="detail-grid">
      <div className={`detail-header ${blocker.safe_to_kill.toLowerCase()}`}>
        <div className="target-reticle" aria-hidden="true">
          <Crosshair size={34} />
        </div>
        <div>
          <div className="eyebrow">Selected process</div>
          <h2>{blocker.process_name || "process"}</h2>
          <p>{blocker.process_role} · PID {blocker.pid}</p>
        </div>
        <span className={`large-level ${blocker.safe_to_kill.toLowerCase()}`}>{blocker.safe_to_kill}</span>
      </div>

      <div className="info-strip">
        <Info icon={<TerminalSquare size={16} />} label="PID" value={String(blocker.pid)} />
        <Info icon={<GitBranch size={16} />} label="Parent" value={blocker.parent_process || String(blocker.parent_pid || "")} />
        <Info icon={<Clock3 size={16} />} label="Started" value={blocker.started_at || "Unknown"} />
        <Info icon={<FileJson size={16} />} label="Report" value={report?.report_path || "Not written"} />
      </div>

      <Section title="Identity">
        <KeyValue label="Role" value={blocker.process_role} />
        <KeyValue label="Job" value={blocker.job_id || "No job metadata"} />
        <KeyValue label="Component" value={blocker.component || "Unknown"} />
        <KeyValue label="Executable" value={blocker.executable_path || "Unknown"} mono />
      </Section>

      <Section title="Why it is listed">
        <PillList values={blocker.reasons} />
      </Section>

      <Section title="Consequence if stopped">
        <ul className="plain-list">{blocker.kill_consequence.map((item) => <li key={item}>{item}</li>)}</ul>
      </Section>

      <Section title="Files and runtime">
        <PathGroup icon={<FolderOpen size={15} />} label="Locks" values={blocker.lock_files} />
        <PathGroup icon={<FolderOpen size={15} />} label="Temp dirs" values={blocker.temp_dirs} />
        <PathGroup icon={<FolderOpen size={15} />} label="Inputs" values={blocker.input_files} />
        <PathGroup icon={<FolderOpen size={15} />} label="Outputs" values={blocker.output_files} />
        <PathGroup icon={<FolderOpen size={15} />} label="Logs" values={blocker.log_files} />
      </Section>

      <Section title="Dependency graph">
        {blocker.relationships.length ? (
          <div className="graph-list">
            {blocker.relationships.map((edge, index) => (
              <div className="graph-edge" key={`${edge.source}-${edge.target}-${index}`}>
                <span>{edge.source || "unknown"}</span>
                <strong><Route size={14} />{edge.relation}</strong>
                <span>{edge.target || "unknown"}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="muted">No relationship graph edges in this report.</div>
        )}
      </Section>

      <Section title="Available actions">
        <div className="action-grid">
          {blocker.suggested_actions.map((action) => (
            <button className="action-button" key={action}>
              <PlayCircle size={15} />
              <span>{action}</span>
            </button>
          ))}
        </div>
      </Section>

      <Section title="Command line">
        <pre className="command-block">{blocker.command_line || blocker.command_summary}</pre>
      </Section>
    </div>
  );
}

function IsoPdfAutopilot() {
  const legacy = useLegacyBridge("iso");
  const [isoView, setIsoView] = useState<"workbench" | "autopilot" | "engineer">("autopilot");
  const [workFolder, setWorkFolder] = useState("");
  const [combinePdf, setCombinePdf] = useState("");
  const [pageFolder, setPageFolder] = useState("");
  const [isoList, setIsoList] = useState("");
  const [sheetName, setSheetName] = useState("");
  const [serialCol, setSerialCol] = useState<number | "">("");
  const [lineCol, setLineCol] = useState<number | "">("");
  const [pattern, setPattern] = useState("{serial}--{line}.pdf");
  const [detectSerials, setDetectSerials] = useState(false);
  const [plan, setPlan] = useState<IsoWorkflowPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [applyBusy, setApplyBusy] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);
  const [batchJob, setBatchJob] = useState<IsoJobPayload | null>(null);
  const [batchBusy, setBatchBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [problemOnly, setProblemOnly] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [sortMode, setSortMode] = useState<IsoSortMode>("page");
  const [selectedRowId, setSelectedRowId] = useState("");
  const [preview, setPreview] = useState<IsoPreviewPayload | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [profile, setProfile] = useState<IsoProfilePayload | null>(null);
  const [profileBusy, setProfileBusy] = useState(false);
  const [serialRegion, setSerialRegion] = useState<IsoRegion>(DEFAULT_SERIAL_REGION);
  const [drawingRegion, setDrawingRegion] = useState<IsoRegion>(DEFAULT_DRAWING_REGION);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.7);
  const [activeRoi, setActiveRoi] = useState<"serial" | "drawing">("serial");
  const [dryRunOpen, setDryRunOpen] = useState(false);
  const [resultOpen, setResultOpen] = useState(false);
  const [oneClickStage, setOneClickStage] = useState<"idle" | "running" | "applying" | "review" | "done">("idle");
  const [recordPath, setRecordPath] = useState("");
  const [activeIsoRunId, setActiveIsoRunId] = useState("");
  const [oneClickRunLog, setOneClickRunLog] = useState<IsoRunLogRef | null>(null);
  const [runLogOpen, setRunLogOpen] = useState(false);
  const [runLogs, setRunLogs] = useState<IsoRunLogSummary[]>([]);
  const [runLogDetail, setRunLogDetail] = useState<IsoRunLogDetail | null>(null);
  const [runLogBusy, setRunLogBusy] = useState(false);
  const [isoFailure, setIsoFailure] = useState<IsoFailureInfo | null>(null);
  const [failureCopied, setFailureCopied] = useState(false);
  const [debugBundleBusy, setDebugBundleBusy] = useState(false);
  const [runStartedAt, setRunStartedAt] = useState<number | null>(null);
  const [nowTs, setNowTs] = useState(() => Date.now());
  const oneClickActiveRef = useRef(false);
  const terminalRef = useRef<HTMLDivElement | null>(null);
  const previewCacheRef = useRef(new Map<string, IsoPreviewPayload>());

  function requestPayload(rows?: IsoPlanRow[], overrides: Partial<IsoWorkflowRequest> = {}) {
    return {
      action: rows ? "apply" as const : "plan" as const,
      profile_folder: activeProfileFolder(),
      work_folder: workFolder,
      combine_pdf: combinePdf,
      page_folder: pageFolder,
      iso_list: isoList,
      sheet_name: sheetName,
      serial_col: serialCol,
      line_col: lineCol,
      pattern,
      serial_region: serialRegion,
      drawing_region: drawingRegion,
      confidence_threshold: confidenceThreshold,
      detect_serials: detectSerials,
      run_id: overrides.run_id || activeIsoRunId || undefined,
      rows,
    };
  }

  function activeProfileFolder(overrides: Partial<IsoWorkflowRequest> = {}) {
    return (
      overrides.profile_folder ||
      overrides.work_folder ||
      workFolder ||
      overrides.page_folder ||
      pageFolder ||
      parentPath(overrides.combine_pdf || combinePdf) ||
      parentPath(overrides.iso_list || isoList)
    );
  }

  function applyProfile(result: IsoProfilePayload, options: { syncPageFolder?: boolean } = {}) {
    if (result.detected_combine_pdf) {
      setCombinePdf(result.detected_combine_pdf);
      setWorkFolder(parentPath(result.detected_combine_pdf));
    }
    if (options.syncPageFolder && result.detected_page_folder_exists && result.detected_page_folder) {
      setPageFolder(result.detected_page_folder);
    }
    if (result.detected_iso_list) {
      setIsoList(result.detected_iso_list);
    }
    if (!result.exists) {
      return;
    }
    setPattern(result.pattern || "{serial}--{line}.pdf");
    setIsoList(result.iso_list_path || result.detected_iso_list || "");
    setSheetName(result.sheet_name || "");
    setSerialCol(result.serial_col ?? "");
    setLineCol(result.line_col ?? "");
    setSerialRegion(result.serial_region || DEFAULT_SERIAL_REGION);
    setDrawingRegion(result.drawing_region || DEFAULT_DRAWING_REGION);
    setConfidenceThreshold(result.confidence_threshold ?? 0.7);
  }

  async function restoreProfile(request: Partial<IsoWorkflowRequest>, options: { syncPageFolder?: boolean } = {}) {
    if (!isTauri()) {
      return null;
    }
    setProfileBusy(true);
    try {
      const result = await loadIsoProfile({ ...request, profile_folder: activeProfileFolder(request) });
      setProfile(result);
      applyProfile(result, options);
      return result;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      return null;
    } finally {
      setProfileBusy(false);
    }
  }

  function sourceLoadMessage(result: IsoProfilePayload | null, fallback: string) {
    if (!result) {
      return fallback;
    }
    const parts: string[] = [];
    if (result.detected_combine_pdf) {
      parts.push(`PDF ${compactPath(result.detected_combine_pdf)}`);
    }
    if (result.detected_iso_list) {
      parts.push(`ISO ${compactPath(result.detected_iso_list)}`);
    }
    if (result.published_exists ?? result.exists) {
      parts.push(`Profile ${compactPath(result.folder)}`);
    } else if (result.draft_exists) {
      parts.push("Profile draft");
    }
    return parts.length ? `已自動載入：${parts.join(" · ")}` : fallback;
  }

  function registerRunLog(ref?: IsoRunLogRef | null, fallbackRunId = "") {
    if (ref) {
      setOneClickRunLog(ref);
      setActiveIsoRunId(ref.run_id);
      return ref.run_id;
    }
    if (fallbackRunId) {
      setActiveIsoRunId(fallbackRunId);
      return fallbackRunId;
    }
    return activeIsoRunId;
  }

  function setOneClickFailure(title: string, caught: unknown, runId = activeIsoRunId, runLog = oneClickRunLog) {
    const detail = caught instanceof Error ? caught.message : String(caught || "");
    const knownRunId = runLog?.run_id || runId || activeIsoRunId;
    setFailureCopied(false);
    setIsoFailure({
      run_id: knownRunId || undefined,
      title,
      summary: detail || "ISO 一鍵命名沒有完成，請把此 Run ID 交給工程師檢查。",
      detail: runLog?.run_json ? `run log: ${compactPath(runLog.run_json)}` : "",
      run_json: runLog?.run_json,
      events_jsonl: runLog?.events_jsonl,
    });
  }

  async function copyFailureForEngineer() {
    if (!isoFailure) {
      return;
    }
    const text = [
      "ISO 一鍵命名失敗摘要",
      `Run ID: ${isoFailure.run_id || "未取得"}`,
      `原因: ${isoFailure.summary}`,
      isoFailure.run_json ? `Run log: ${isoFailure.run_json}` : "",
      isoFailure.events_jsonl ? `Events: ${isoFailure.events_jsonl}` : "",
      workFolder ? `工作資料夾: ${workFolder}` : "",
      combinePdf ? `Combine PDF: ${combinePdf}` : "",
      pageFolder ? `Page folder: ${pageFolder}` : "",
      isoList ? `ISO List: ${isoList}` : "",
    ].filter(Boolean).join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setFailureCopied(true);
      setMessage("已複製 ISO 失敗摘要。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function exportFailureBundle() {
    if (!isoFailure?.run_id) {
      setError("缺少 run_id，無法匯出問題包。");
      return;
    }
    setDebugBundleBusy(true);
    setError("");
    try {
      const result = await exportIsoDebugBundle({ run_id: isoFailure.run_id });
      setMessage(result.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setDebugBundleBusy(false);
    }
  }

  async function openRunLogDrawer(runId = activeIsoRunId) {
    if (!isTauri()) {
      setError("請用 Tauri 桌面版讀取處理紀錄。");
      return;
    }
    setRunLogOpen(true);
    await refreshRunLogs(runId);
  }

  async function refreshRunLogs(preferredRunId = runLogDetail?.run.run_id || activeIsoRunId) {
    setRunLogBusy(true);
    setError("");
    try {
      const payload = await listIsoRunLogs();
      setRunLogs(payload.runs);
      const nextRunId = preferredRunId || payload.runs[0]?.run_id || "";
      if (nextRunId) {
        await loadRunLogDetail(nextRunId);
      } else {
        setRunLogDetail(null);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRunLogBusy(false);
    }
  }

  async function loadRunLogDetail(runId: string) {
    if (!runId) {
      return;
    }
    setRunLogBusy(true);
    setError("");
    try {
      const detail = await readIsoRunLog(runId);
      setRunLogDetail(detail);
      setActiveIsoRunId(runId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRunLogBusy(false);
    }
  }

  async function replayRunLog(runId: string) {
    if (!runId) {
      return;
    }
    setRunLogBusy(true);
    setError("");
    try {
      const replay = await replayIsoRunLog(runId);
      setPlan(replay);
      setWorkFolder(replay.source.work_folder || workFolder);
      setCombinePdf(replay.source.combine_pdf || combinePdf);
      setPageFolder(replay.source.page_folder || pageFolder);
      setIsoList(replay.source.iso_list || isoList);
      setSheetName(replay.source.sheet_name || sheetName);
      setSerialCol(replay.source.serial_col ?? serialCol);
      setLineCol(replay.source.line_col ?? lineCol);
      setSelectedRowId(replay.rows[0]?.id ?? "");
      setResultOpen(false);
      setDryRunOpen(false);
      setProblemOnly(false);
      setIsoView("workbench");
      setRunLogOpen(false);
      setMessage(replay.message || `已 replay：${runId}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRunLogBusy(false);
    }
  }

  function openFailureWorkbench() {
    const firstProblem = plan?.rows.find((row) => row.status === "blocked" || row.status === "warn");
    if (firstProblem) {
      setSelectedRowId(firstProblem.id);
      setProblemOnly(true);
    }
    setIsoView("workbench");
  }

  async function chooseWorkFolder() {
    try {
      const path = await pickIsoWorkFolder();
      if (path) {
        setWorkFolder(path);
        setCombinePdf("");
        setPageFolder("");
        setPlan(null);
        setIsoFailure(null);
        const restored = await restoreProfile({ work_folder: path }, { syncPageFolder: true });
        setMessage(sourceLoadMessage(restored, "已選工作資料夾，可直接產生命名草稿。"));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function chooseCombinePdf() {
    try {
      const path = await pickIsoCombinePdf();
      if (path) {
        setCombinePdf(path);
        setPageFolder("");
        const folder = parentPath(path);
        setWorkFolder(folder);
        setPlan(null);
        setIsoFailure(null);
        const restored = await restoreProfile({ work_folder: folder, combine_pdf: path }, { syncPageFolder: true });
        setMessage(sourceLoadMessage(restored, "已選 Combine PDF，可直接產生命名草稿。"));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function choosePageFolder() {
    try {
      const path = await pickIsoPageFolder();
      if (path) {
        setPageFolder(path);
        setCombinePdf("");
        setWorkFolder(path);
        setPlan(null);
        setIsoFailure(null);
        const restored = await restoreProfile({ work_folder: path, page_folder: path });
        setMessage(sourceLoadMessage(restored, "已選 Page folder，可直接產生命名草稿。"));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function chooseIsoList() {
    try {
      const path = await pickIsoListFile();
      if (path) {
        setIsoList(path);
        setPlan(null);
        setIsoFailure(null);
        setProfile((current) => current ? { ...current, iso_list_path: path } : current);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  async function generatePlan() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await runIsoPlan(requestPayload());
      setPlan(result);
      setIsoList(result.source.iso_list || isoList);
      setPageFolder(result.source.page_folder || pageFolder);
      setSheetName(result.source.sheet_name || sheetName);
      setSerialCol(result.source.serial_col ?? "");
      setLineCol(result.source.line_col ?? "");
      setSelectedRowId(result.rows[0]?.id ?? "");
      setResultOpen(true);
      let profileNote = "";
      try {
        const savedProfile = await saveIsoDraftProfile({
          profile_folder:
            result.source.profile?.folder ||
            result.source.work_folder ||
            result.source.page_folder ||
            parentPath(result.source.combine_pdf) ||
            activeProfileFolder(),
          work_folder: result.source.work_folder || workFolder,
          combine_pdf: result.source.combine_pdf || combinePdf,
          page_folder: result.source.page_folder || pageFolder,
          iso_list: result.source.iso_list || isoList,
          sheet_name: result.source.sheet_name || sheetName,
          serial_col: result.source.serial_col ?? serialCol,
          line_col: result.source.line_col ?? lineCol,
          pattern: result.source.pattern || pattern,
          confidence_threshold: confidenceThreshold,
          serial_region: serialRegion,
          drawing_region: drawingRegion,
        });
        setProfile(savedProfile);
        profileNote = " Profile 草稿已保存（未發布到一鍵）。";
      } catch (caught) {
        profileNote = ` Profile 草稿保存失敗：${caught instanceof Error ? caught.message : String(caught)}`;
      }
      setMessage(`已產生命名草稿：${result.summary.selected} / ${result.summary.total} 可套用。${profileNote}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function publishProfileToOneClick() {
    if (!isTauri()) {
      setError("請用 Tauri 桌面版發布 Profile。");
      return;
    }
    const folder = activeProfileFolder();
    if (!folder) {
      setError("請先選擇工作資料夾或來源檔案，才能發布 Profile。");
      return;
    }
    setProfileBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await publishIsoProfile({
        profile_folder: folder,
        work_folder: workFolder,
        combine_pdf: combinePdf,
        page_folder: pageFolder,
        iso_list: isoList,
        sheet_name: sheetName,
        serial_col: serialCol,
        line_col: lineCol,
        pattern,
        confidence_threshold: confidenceThreshold,
        serial_region: serialRegion,
        drawing_region: drawingRegion,
      });
      setProfile(result);
      applyProfile(result);
      setMessage(`已發布 Profile 到一鍵：${compactPath(result.folder)}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setProfileBusy(false);
    }
  }

  async function revertPublishedProfile() {
    if (!isTauri()) {
      setError("請用 Tauri 桌面版回復 Profile。");
      return;
    }
    const folder = activeProfileFolder();
    if (!folder) {
      setError("請先選擇工作資料夾或來源檔案，才能回復 Profile。");
      return;
    }
    setProfileBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await revertIsoProfile({
        profile_folder: folder,
        work_folder: workFolder,
        combine_pdf: combinePdf,
        page_folder: pageFolder,
        iso_list: isoList,
      });
      setProfile(result);
      applyProfile(result);
      setMessage(`已回復上一版 Profile：${compactPath(result.folder)}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setProfileBusy(false);
    }
  }

  function openDryRun() {
    if (!plan) {
      return;
    }
    if (blockedCount) {
      setError(`還有 ${blockedCount} 筆 blocked，修正前不能套用。`);
      chooseProblemRow();
      return;
    }
    if (warnCount) {
      setError(`還有 ${warnCount} 筆 warn，請逐列確認後再套用。`);
      chooseProblemRow();
      return;
    }
    const selected = plan.rows.filter((row) => row.selected && row.status === "ready");
    if (!selected.length) {
      setError("沒有可套用的 ready 列；請先勾選 ready 列。");
      return;
    }
    setDryRunOpen(true);
  }

  async function applySelectedRows() {
    if (!plan) {
      return;
    }
    if (blockedCount || warnCount) {
      setError(blockedCount ? `還有 ${blockedCount} 筆 blocked，修正前不能套用。` : `還有 ${warnCount} 筆 warn，請逐列確認後再套用。`);
      chooseProblemRow();
      return;
    }
    const selected = plan.rows.filter((row) => row.selected && row.status === "ready");
    if (!selected.length) {
      setError("沒有勾選任何 ready 可更名列。");
      return;
    }
    setApplyBusy(true);
    setError("");
    setMessage("");
    try {
      let recPath = "";
      let recordWarning = "";
      try {
        const rec = await exportIsoPlanCsv({
          ...requestPayload(plan.rows),
          work_folder: plan.source.work_folder || workFolder,
          combine_pdf: plan.source.combine_pdf || combinePdf,
          page_folder: plan.source.page_folder || pageFolder,
          iso_list: plan.source.iso_list || isoList,
          sheet_name: plan.source.sheet_name || sheetName,
          serial_col: plan.source.serial_col ?? serialCol,
          line_col: plan.source.line_col ?? lineCol,
          pattern: plan.source.pattern || pattern,
        });
        recPath = rec.export_path;
        setRecordPath(recPath);
      } catch (recordError) {
        recordWarning = `更名記錄寫入失敗:${recordError instanceof Error ? recordError.message : String(recordError)} `;
      }
      const result = await applyIsoPlan(requestPayload(selected));
      const renamedIds = new Set(selected.map((row) => row.id));
      updatePlanRows((rows) => rows.filter((row) => !renamedIds.has(row.id)));
      setSelectedRowId(plan.rows.find((row) => !renamedIds.has(row.id))?.id ?? "");
      setDryRunOpen(false);
      setResultOpen(false);
      setMessage(`${recordWarning}${result.message}${recPath ? ` 記錄已存:${recPath}` : ""} 已從清單移除 ${selected.length} 列;要重新掃描可按「重新產生」。`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setApplyBusy(false);
    }
  }

  async function runOneClick() {
    setError("");
    if (oneClickStage === "done") {
      setPlan(null);
      setOneClickStage("idle");
      setRecordPath("");
      setActiveIsoRunId("");
      setOneClickRunLog(null);
      setIsoFailure(null);
      setMessage("");
      return;
    }
    if (oneClickStage === "running" && batchRunning && batchJob) {
      await cancelBatchDetect();
      setMessage("正在取消一鍵命名…");
      return;
    }
    if (!workFolder && !combinePdf && !pageFolder) {
      await chooseWorkFolder();
      return;
    }
    if (oneClickStage === "review" && plan) {
      const blockedRows = plan.rows.filter((row) => row.status === "blocked");
      const warnRows = plan.rows.filter((row) => row.status === "warn");
      const canApplyRows = plan.rows.filter((row) => row.selected && row.status === "ready");
      if (blockedRows.length || warnRows.length) {
        setSelectedRowId(blockedRows[0]?.id ?? warnRows[0]?.id ?? "");
        setProblemOnly(true);
        setIsoView("workbench");
        setMessage(blockedRows.length ? `還有 ${blockedRows.length} 個 blocked 列,先在工作台修正後再更名。` : `還有 ${warnRows.length} 個 warn 列,逐列確認後才能更名。`);
        return;
      }
      if (!canApplyRows.length) {
        setMessage("沒有 ready 且勾選的列可更名。");
        return;
      }
      await autoApplyWithRecord(plan);
      return;
    }
    setOneClickStage("running");
    setMessage("");
    setRecordPath("");
    setPlan(null);
    setRunStartedAt(Date.now());
    const runId = createIsoRunId();
    setActiveIsoRunId(runId);
    setOneClickRunLog(null);
    setIsoFailure(null);
    setFailureCopied(false);
    oneClickActiveRef.current = true;
    try {
      const job = await startIsoBatchDetect({ ...requestPayload(undefined, { run_id: runId }), detect_serials: true });
      registerRunLog(job.run_log, runId);
      setBatchJob(job);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setOneClickFailure("一鍵命名啟動失敗", caught, runId);
      setOneClickStage("idle");
      oneClickActiveRef.current = false;
    }
  }

  async function autoApplyWithRecord(currentPlan: IsoWorkflowPlan) {
    const blockedRows = currentPlan.rows.filter((row) => row.status === "blocked");
    const warnRows = currentPlan.rows.filter((row) => row.status === "warn");
    if (blockedRows.length || warnRows.length) {
      setSelectedRowId(blockedRows[0]?.id ?? warnRows[0]?.id ?? "");
      setProblemOnly(true);
      setOneClickStage("review");
      setMessage(blockedRows.length ? `還有 ${blockedRows.length} 個 blocked 列,先修正後才能完成一鍵更名。` : `還有 ${warnRows.length} 個 warn 列,逐列確認後才能完成一鍵更名。`);
      return;
    }
    const applyRows = currentPlan.rows.filter((row) => row.selected && row.status === "ready");
    if (!applyRows.length) {
      setOneClickStage("done");
      setMessage("沒有需要更名的檔案。");
      return;
    }
    setApplyBusy(true);
    setOneClickStage("applying");
    setError("");
    let recPath = "";
    let recordWarning = "";
    try {
      try {
        const rec = await exportIsoPlanCsv({
          ...requestPayload(currentPlan.rows),
          work_folder: currentPlan.source.work_folder || workFolder,
          combine_pdf: currentPlan.source.combine_pdf || combinePdf,
          page_folder: currentPlan.source.page_folder || pageFolder,
          iso_list: currentPlan.source.iso_list || isoList,
          sheet_name: currentPlan.source.sheet_name || sheetName,
          serial_col: currentPlan.source.serial_col ?? serialCol,
          line_col: currentPlan.source.line_col ?? lineCol,
          pattern: currentPlan.source.pattern || pattern,
        });
        recPath = rec.export_path;
        setRecordPath(recPath);
      } catch (recErr) {
        recordWarning = `更名記錄寫入失敗:${recErr instanceof Error ? recErr.message : String(recErr)} `;
      }
      const result = await applyIsoPlan(requestPayload(applyRows));
      registerRunLog(result.run_log);
      const renamedIds = new Set(applyRows.map((row) => row.id));
      updatePlanRows((rows) => rows.filter((row) => !renamedIds.has(row.id)));
      setSelectedRowId(currentPlan.rows.find((row) => !renamedIds.has(row.id))?.id ?? "");
      setOneClickStage("done");
      setMessage(`${recordWarning}${result.message}${recPath ? ` 記錄已存:${recPath}` : ""}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setOneClickFailure("套用更名失敗", caught);
      setOneClickStage("review");
    } finally {
      setApplyBusy(false);
    }
  }

  function resetRoi(region: "serial" | "drawing" = activeRoi) {
    if (region === "serial") {
      setSerialRegion(DEFAULT_SERIAL_REGION);
      return;
    }
    setDrawingRegion(DEFAULT_DRAWING_REGION);
  }

  function updateActiveRoi(field: keyof IsoRegion, value: number) {
    const setter = activeRoi === "serial" ? setSerialRegion : setDrawingRegion;
    setter((current) => normalizeRegion({ ...current, [field]: value }));
  }

  async function exportRenameCsv() {
    if (!plan) {
      setError("尚未產生命名草稿，無法匯出 CSV。");
      return;
    }
    setExportBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await exportIsoPlanCsv({
        ...requestPayload(plan.rows),
        work_folder: plan.source.work_folder || workFolder,
        combine_pdf: plan.source.combine_pdf || combinePdf,
        page_folder: plan.source.page_folder || pageFolder,
        iso_list: plan.source.iso_list || isoList,
        sheet_name: plan.source.sheet_name || sheetName,
        serial_col: plan.source.serial_col ?? serialCol,
        line_col: plan.source.line_col ?? lineCol,
        pattern: plan.source.pattern || pattern,
      });
      setMessage(result.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setExportBusy(false);
    }
  }

  async function startBatchDetect() {
    setBatchBusy(true);
    setError("");
    setMessage("");
    try {
      const job = await startIsoBatchDetect({ ...requestPayload(), detect_serials: true });
      setBatchJob(job);
      setMessage(`批次判讀已啟動：${job.job_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBatchBusy(false);
    }
  }

  async function cancelBatchDetect() {
    if (!batchJob) {
      return;
    }
    setBatchBusy(true);
    try {
      const job = await cancelIsoJob(batchJob.job_id);
      setBatchJob(job);
      setMessage("已送出取消批次判讀。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBatchBusy(false);
    }
  }

  function toggleRow(rowId: string) {
    updatePlanRows((rows) => rows.map((row) => row.id === rowId && row.status !== "blocked" ? { ...row, selected: !row.selected } : row));
  }

  function setAllRowsSelected(select: boolean) {
    updatePlanRows((rows) => rows.map((row) => (row.status === "blocked" ? row : { ...row, selected: select })));
  }

  function updateRow(rowId: string, field: "serial" | "line_no" | "new_name", value: string) {
    updatePlanRows((rows) => rows.map((row) => {
      if (row.id !== rowId) {
        return row;
      }
      const next = { ...row, [field]: value, note: "manual corrected", vision_message: "manual corrected" };
      if (field === "serial" || field === "line_no") {
        next.new_name = formatIsoFilename(pattern, field === "serial" ? value : next.serial, field === "line_no" ? value : next.line_no);
      }
      next.target_path = targetPathFor(next.source_path, next.new_name);
      next.selected = Boolean(next.new_name && next.new_name !== next.source_name);
      return next;
    }));
  }

  function updatePlanRows(mutator: (rows: IsoPlanRow[]) => IsoPlanRow[]) {
    setPlan((current) => {
      if (!current) {
        return current;
      }
      const rows = normalizeIsoRows(mutator(current.rows));
      return { ...current, rows, summary: summarizeIsoRows(rows) };
    });
  }

  function chooseProblemRow() {
    const allRows = plan?.rows ?? [];
    const problems = allRows.filter((row) => row.status === "blocked" || row.status === "warn");
    if (!problems.length) {
      return;
    }
    const currentIndex = allRows.findIndex((row) => row.id === selectedRowId);
    const next = problems.find((row) => allRows.findIndex((candidate) => candidate.id === row.id) > currentIndex) ?? problems[0];
    setSelectedRowId(next.id);
    setProblemOnly(true);
  }

  function adoptPreviewVision() {
    if (!selectedRow || !preview?.vision?.text) {
      return;
    }
    updateRow(selectedRow.id, "serial", preview.vision.text);
  }

  function confirmSelectedRow() {
    if (!selectedRow) {
      return;
    }
    updatePlanRows((rows) => rows.map((row) => row.id === selectedRow.id ? { ...row, status: "ready", note: "", vision_message: row.vision_message.includes("manual") ? "manual confirmed" : "", selected: row.new_name !== row.source_name } : row));
  }

  const rows = plan?.rows ?? [];
  const selectedCount = rows.filter((row) => row.selected && row.status === "ready").length;
  const blockedCount = rows.filter((row) => row.status === "blocked").length;
  const warnCount = rows.filter((row) => row.status === "warn").length;
  const readyCount = rows.filter((row) => row.status === "ready").length;
  const issueRows = rows.filter((row) => row.status === "blocked" || row.status === "warn");
  const visibleRows = useMemo(() => sortIsoRows(filterIsoRows(rows, searchTerm, problemOnly), sortMode), [rows, searchTerm, problemOnly, sortMode]);
  const selectedRow = rows.find((row) => row.id === selectedRowId) ?? rows[0];
  const columnSummary = plan?.source.headers && plan.source.serial_col !== undefined && plan.source.line_col !== undefined
    ? `${plan.source.headers[plan.source.serial_col] ?? `col ${plan.source.serial_col + 1}`} -> ${plan.source.headers[plan.source.line_col] ?? `col ${plan.source.line_col + 1}`}`
    : "auto";
  const headers = plan?.source.headers ?? [];
  const sheetOptions = plan?.source.sheet_options ?? (sheetName ? [sheetName] : []);
  const hasPublishedProfile = profile?.published_exists ?? (profile?.profile_scope === "draft" ? false : profile?.exists);
  const hasDraftProfile = profile?.draft_exists ?? (profile?.profile_scope === "draft" && profile.exists);
  const profileHistoryCount = profile?.history_count ?? 0;
  const profileLabel = profileBusy
    ? "loading"
    : profile?.profile_scope === "draft"
      ? "draft saved"
      : hasPublishedProfile
        ? compactPath(profile?.folder || "")
        : activeProfileFolder() ? "default profile" : "waiting";
  const batchRunning = batchJob?.state === "queued" || batchJob?.state === "running" || batchJob?.state === "cancel_requested";
  const workflowEvents = [...(batchJob?.events ?? []), ...(plan?.issues ?? [])];
  const hasOneClickSource = Boolean(workFolder || combinePdf || pageFolder);
  const elapsedSec = runStartedAt ? Math.max(0, Math.round((nowTs - runStartedAt) / 1000)) : 0;
  const oneClickRunning = oneClickStage === "running";
  const oneClickApplying = oneClickStage === "applying";
  const detectDone = batchJob?.progress?.done ?? (plan ? plan.summary.total : 0);
  const detectTotal = batchJob?.progress?.total ?? plan?.summary.total ?? 0;
  const oneClickBusy = busy || batchBusy || applyBusy;
  const oneClickButton = (() => {
    if (oneClickRunning) return { icon: <ScanLine size={20} />, label: `取消判讀 ${detectDone}/${detectTotal || "?"} · ${elapsedSec}s`, hint: "正在讀取 worker 真實事件;按一下可取消" };
    if (applyBusy) return { icon: <ClipboardCheck size={20} />, label: "更名中…", hint: "正在寫入更名記錄" };
    if (oneClickStage === "done") return { icon: <RefreshCcw size={20} />, label: "完成 · 再處理一批", hint: recordPath ? `記錄:${compactPath(recordPath)}` : "按一下清空,重新開始" };
    if (!hasOneClickSource) return { icon: <FolderOpen size={20} />, label: "選擇工作資料夾", hint: "選好後再按一次開始一鍵命名" };
    if (oneClickStage === "review" && !selectedCount && blockedCount) return { icon: <AlertTriangle size={20} />, label: `前往工作台修正 ${blockedCount} 筆`, hint: "blocked 列不會自動更名,先修正檔名或 ISO 對應" };
    if (oneClickStage === "review") return { icon: <ClipboardCheck size={20} />, label: `我已確認,更名 ${selectedCount} 筆`, hint: warnCount ? `${warnCount} 個待確認:點清單列,在右側採用或改值` : "全部已確認,可更名" };
    return { icon: <WandSparkles size={20} />, label: "開始一鍵命名", hint: "全綠會直接更名到底,不再跳確認" };
  })();
  const pipelineStages: Array<{ key: string; label: string; icon: React.ReactNode; state: string; detail: string; seconds: number | null }> = [
    { key: "source", label: "來源", icon: <FolderOpen size={18} />, state: hasOneClickSource ? "done" : "idle", detail: hasOneClickSource ? compactPath(workFolder || combinePdf || pageFolder) : "選資料夾", seconds: null },
    { key: "split", label: "拆頁", icon: <Layers3 size={18} />, state: detectTotal ? "done" : oneClickRunning ? "run" : "idle", detail: detectTotal ? `${detectTotal} 頁` : "等待", seconds: null },
    { key: "detect", label: "判讀流水號", icon: <ScanLine size={18} />, state: oneClickRunning ? "run" : plan ? "done" : "idle", detail: oneClickRunning ? `${detectDone}/${detectTotal}` : plan ? `${readyCount} 已讀` : "等待", seconds: oneClickRunning ? elapsedSec : null },
    { key: "match", label: "對 ISO", icon: <Table2 size={18} />, state: plan?.source.record_count ? "done" : "idle", detail: plan?.source.record_count ? `${plan.source.record_count} 列` : "等待", seconds: null },
    { key: "name", label: "命名", icon: <WandSparkles size={18} />, state: plan ? (blockedCount ? "warn" : "done") : "idle", detail: plan ? `${plan.summary.total} 檔` : "等待", seconds: null },
    { key: "apply", label: "更名", icon: <ClipboardCheck size={18} />, state: oneClickStage === "done" ? "done" : oneClickApplying ? "run" : "idle", detail: oneClickStage === "done" ? "完成" : oneClickApplying ? "寫入中" : "等待", seconds: oneClickApplying ? elapsedSec : null },
  ];
  const echoLines = ([...(batchJob?.events ?? []), ...(plan?.issues ?? [])] as unknown as Array<{ code?: string; tone?: string; title?: string; detail?: string }>).slice(-80);

  useEffect(() => {
    let cancelled = false;
    if (!selectedRow?.source_path) {
      setPreview(null);
      setPreviewError("");
      setPreviewBusy(false);
      return;
    }
    if (!isTauri()) {
      setPreview(null);
      setPreviewError("桌面版會顯示 PDF 預覽與裁切圖。");
      setPreviewBusy(false);
      return;
    }
    const cacheKey = `${selectedRow.source_path}|${detectSerials}|${JSON.stringify(serialRegion)}|${JSON.stringify(drawingRegion)}`;
    const cached = previewCacheRef.current.get(cacheKey);
    if (cached) {
      setPreview(cached);
      setPreviewError("");
      setPreviewBusy(false);
      return;
    }
    setPreviewBusy(true);
    setPreviewError("");
    loadIsoPreview({
      source_path: selectedRow.source_path,
      detect_serial: detectSerials,
      serial_region: serialRegion,
      drawing_region: drawingRegion,
    })
      .then((payload) => {
        if (!cancelled) {
          setPreview(payload);
          previewCacheRef.current.set(cacheKey, payload);
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          setPreview(null);
          setPreviewError(caught instanceof Error ? caught.message : String(caught));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setPreviewBusy(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRow?.source_path, detectSerials, serialRegion, drawingRegion]);

  useEffect(() => {
    if (!batchJob || !batchRunning) {
      return;
    }
    let cancelled = false;
    const timer = window.setInterval(() => {
      void loadIsoJobStatus(batchJob.job_id)
        .then((job) => {
          if (cancelled) {
            return;
          }
          setBatchJob(job);
          registerRunLog(job.run_log, job.run_id || activeIsoRunId);
          if (job.result && (job.state === "completed" || job.state === "cancelled")) {
            setPlan(job.result);
            if (oneClickActiveRef.current) {
              oneClickActiveRef.current = false;
              if (job.state === "cancelled") {
                setOneClickStage("idle");
                setMessage("已取消一鍵命名,保留已完成列。");
              } else {
                const problems = job.result.rows.filter((row) => row.status === "warn" || row.status === "blocked");
                setSelectedRowId(problems[0]?.id ?? job.result.rows[0]?.id ?? "");
                if (problems.length) {
                  setOneClickStage("review");
                  setMessage(`有 ${problems.length} 個待確認值,處理後按一次即可更名。`);
                } else {
                  void autoApplyWithRecord(job.result);
                }
              }
            } else {
              setSelectedRowId(job.result.rows[0]?.id ?? "");
              setResultOpen(true);
              setMessage(job.state === "completed" ? "批次判讀完成，命名草稿已更新。" : "批次判讀已取消，保留已完成列。");
            }
          }
          if (job.error) {
            setError(job.error);
            setOneClickFailure("一鍵命名沒有完成", job.error, job.run_id || activeIsoRunId, job.run_log || oneClickRunLog);
            if (oneClickActiveRef.current) {
              oneClickActiveRef.current = false;
              setOneClickStage("idle");
            }
          }
        })
        .catch((caught) => {
          if (!cancelled) {
            setError(caught instanceof Error ? caught.message : String(caught));
            if (oneClickActiveRef.current) {
              setOneClickFailure("讀取一鍵進度失敗", caught);
            }
          }
        });
    }, 350);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [batchJob?.job_id, batchRunning, activeIsoRunId, oneClickRunLog]);

  useEffect(() => {
    if (oneClickStage !== "running" && oneClickStage !== "applying") {
      return;
    }
    const id = window.setInterval(() => setNowTs(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [oneClickStage]);

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [batchJob?.events?.length, oneClickStage]);

  const visualPanel = (
    <IsoVisualPanel
      activeRoi={activeRoi}
      busy={previewBusy}
      drawingRegion={drawingRegion}
      error={previewError}
      preview={preview}
      resetRoi={resetRoi}
      row={selectedRow}
      serialRegion={serialRegion}
      setActiveRoi={setActiveRoi}
      adoptPreviewVision={adoptPreviewVision}
      confirmSelectedRow={confirmSelectedRow}
      nextProblem={chooseProblemRow}
      updateActiveRoi={updateActiveRoi}
    />
  );

  return (
    <section className="iso-board iso-workbench">
      <div className="iso-workbench-top">
        <div>
          <div className="eyebrow">Tauri ISO workbench</div>
          <h2>ISO PDF 拆頁命名工作臺</h2>
          {isoView !== "autopilot" ? (
            <div className="iso-source-strip">
              <TopSourceButton icon={<FolderOpen size={15} />} label="工作資料夾" value={workFolder} onPick={chooseWorkFolder} />
              <TopSourceButton icon={<FileText size={15} />} label="Combine PDF" value={combinePdf} onPick={chooseCombinePdf} />
              <TopSourceButton icon={<Layers3 size={15} />} label="Page folder" value={pageFolder} onPick={choosePageFolder} />
              <TopSourceButton icon={<Table2 size={15} />} label="ISO List" value={isoList} onPick={chooseIsoList} />
            </div>
          ) : null}
        </div>
        <div className="iso-top-actions">
          <div className="mode-switch" role="tablist" aria-label="ISO 工作模式">
            <button className={isoView === "autopilot" ? "active" : ""} onClick={() => setIsoView("autopilot")} title="一鍵導引:選來源 → 產生草稿 → 套用">
              <WandSparkles size={15} />
              <span>一鍵</span>
            </button>
            <button className={isoView === "workbench" ? "active" : ""} onClick={() => setIsoView("workbench")} title="工作台:逐列校對命名表與預覽">
              <Table2 size={15} />
              <span>工作台</span>
            </button>
            <button className={isoView === "engineer" ? "active" : ""} onClick={() => setIsoView("engineer")} title="調校:ROI、欄位對應、信心門檻、Profile">
              <Settings size={15} />
              <span>調校</span>
            </button>
          </div>
          {isoView !== "autopilot" ? (
            <button className="icon-button" onClick={legacy.launch} disabled={legacy.busy} title="暫時開啟舊版工作台(轉移完成後移除)">
              <PanelRightOpen size={16} />
              <span>{legacy.busy ? "開啟中" : "舊版"}</span>
            </button>
          ) : null}
        </div>
      </div>

      <BridgeStatus error={error || legacy.error} message={message || legacy.message} />
      {batchJob && isoView !== "autopilot" ? (
        <div className={`batch-progress ${batchJob.state}`}>
          <div>
            <strong>{batchJob.state}</strong>
            <span>{batchJob.progress.done} / {batchJob.progress.total} pages</span>
          </div>
          <div className="batch-progress-bar">
            <span style={{ width: `${batchJob.progress.percent}%` }} />
          </div>
        </div>
      ) : null}

      {isoView === "autopilot" ? (
        <div className="iso-autopilot-grid one-click-grid">
          <main className="iso-autopilot-main">
            <div className="one-click-head">
              <div className="eyebrow">一鍵命名</div>
              <h2>選資料夾,其餘交給它</h2>
              <p>自動拆頁、判讀流水號、對 ISO List、命名、更名。全綠就一路到底;只有出現低自信值才會停下來請你確認。</p>
            </div>

            <div className="pipeline">
              {pipelineStages.map((stage, index) => (
                <Fragment key={stage.key}>
                  <div className={`pipeline-card ${stage.state}`}>
                    <div className="pipeline-card-top">
                      {stage.icon}
                      {stage.seconds != null ? <em>{stage.seconds}s</em> : stage.state === "done" ? <CircleCheck size={14} /> : null}
                    </div>
                    <strong>{stage.label}</strong>
                    <span>{stage.detail}</span>
                  </div>
                  {index < pipelineStages.length - 1 ? <ChevronRight className="pipeline-arrow" size={18} /> : null}
                </Fragment>
              ))}
            </div>

            {oneClickStage === "review" ? (
              <div className="one-click-checklist">
                <ChecklistGate label="流水號判讀" detail={warnCount ? `${readyCount} 已確認 · ${warnCount} 待確認` : `${readyCount} 已確認`} state={warnCount ? "warn" : "ready"}>
                  {warnCount ? (
                    <div className="checklist-problem-rows">
                      {issueRows.filter((row) => row.status === "warn").map((row) => (
                        <button className={`checklist-problem-row ${selectedRow?.id === row.id ? "selected" : ""}`} key={row.id} onClick={() => { setSelectedRowId(row.id); setIsoView("workbench"); }}>
                          <span className="mono">{String(row.page).padStart(3, "0")}</span>
                          <span className="checklist-problem-detail">{row.note || row.vision_message || "需確認"}</span>
                          <ChevronRight size={14} />
                        </button>
                      ))}
                    </div>
                  ) : null}
                </ChecklistGate>
                {blockedCount ? <ChecklistGate label="命名衝突" detail={`${blockedCount} 個無法更名,請到工作台處理`} state="danger" /> : null}
              </div>
            ) : null}

            {isoFailure ? (
              <FailureCard
                copied={failureCopied}
                exportBusy={debugBundleBusy}
                failure={isoFailure}
                onCopy={copyFailureForEngineer}
                onExport={exportFailureBundle}
                onOpenWorkbench={openFailureWorkbench}
              />
            ) : null}

            <button className="one-click-button" onClick={runOneClick} disabled={oneClickBusy}>
              {oneClickButton.icon}
              <span>{oneClickButton.label}</span>
            </button>
            <div className="one-click-hint">{oneClickButton.hint}</div>

            <div className="one-click-terminal">
              <div className="terminal-head">
                <TerminalSquare size={14} />
                <span>流程紀錄</span>
                <em>{oneClickRunning || oneClickApplying ? `${elapsedSec}s` : oneClickStage === "done" ? "done" : "idle"}</em>
              </div>
              <div className="terminal-body" ref={terminalRef}>
                {echoLines.length ? echoLines.map((line, index) => (
                  <div className={`terminal-line ${line.tone || ""}`} key={`${line.code}-${index}`}>
                    <span className="terminal-code">{line.code || "LOG"}</span>
                    <span>{line.title}{line.detail ? ` · ${line.detail}` : ""}</span>
                  </div>
                )) : <div className="terminal-line idle"><span className="terminal-code">SYS</span><span>等待一鍵命名啟動…</span></div>}
                {oneClickRunning || oneClickApplying ? <div className="terminal-cursor">_</div> : null}
              </div>
            </div>
          </main>
        </div>
      ) : isoView === "engineer" ? (
        <div className="iso-engineer-grid">
          <aside className="iso-engineer-panel">
            <div className="panel-heading compact">
              <div>
                <span>Sources</span>
                <small>{profileLabel}</small>
              </div>
            </div>
            <PathPickerRow icon={<FolderOpen size={16} />} label="工作資料夾" value={workFolder} onPick={chooseWorkFolder} />
            <PathPickerRow icon={<FileText size={16} />} label="Combine PDF" value={combinePdf} onPick={chooseCombinePdf} />
            <PathPickerRow icon={<Layers3 size={16} />} label="Page folder" value={pageFolder} onPick={choosePageFolder} />
            <PathPickerRow icon={<Table2 size={16} />} label="ISO List" value={isoList} onPick={chooseIsoList} />
            <div className={`profile-chip ${hasPublishedProfile ? "ready" : "idle"}`}>
              <Settings size={14} />
              <span>Profile</span>
              <strong>{profileLabel}</strong>
            </div>
            <div className="engineer-section">
              <div className="eyebrow">Quality gates</div>
              <Gate label="PDF 來源" state={plan?.summary.total ? "ready" : workFolder || combinePdf || pageFolder ? "idle" : "warn"} />
              <Gate label="ISO List" state={plan?.source.record_count ? "ready" : isoList || workFolder ? "idle" : "warn"} />
              <Gate label="欄位對應" state={plan?.source.serial_col !== undefined && plan.source.line_col !== undefined ? "ready" : "idle"} />
              <Gate label="Profile" state={hasPublishedProfile ? "ready" : activeProfileFolder() ? "idle" : "warn"} />
            </div>
          </aside>

          <main className="iso-engineer-panel wide">
            <div className="engineer-section">
              <div className="panel-heading compact">
                <div>
                  <span>ISO List mapping</span>
                  <small>{plan?.source.record_count ? `${plan.source.record_count} rows` : "auto columns"}</small>
                </div>
              </div>
              <div className="engineer-form-grid">
                <label className="field-row stacked">
                  <span>Sheet</span>
                  {sheetOptions.length ? (
                    <select value={sheetName} onChange={(event) => { setSheetName(event.target.value); setSerialCol(""); setLineCol(""); }}>
                      {sheetOptions.map((sheet) => <option value={sheet} key={sheet}>{sheet}</option>)}
                    </select>
                  ) : (
                    <input value={sheetName} onChange={(event) => setSheetName(event.target.value)} placeholder="auto" />
                  )}
                </label>
                <label className="field-row stacked">
                  <span>流水號欄</span>
                  <select value={serialCol} onChange={(event) => setSerialCol(event.target.value === "" ? "" : Number(event.target.value))}>
                    <option value="">auto</option>
                    {headers.map((header, index) => <option value={index} key={`engineer-serial-${header}-${index}`}>{index + 1}. {header}</option>)}
                  </select>
                </label>
                <label className="field-row stacked">
                  <span>圖號/檔名欄</span>
                  <select value={lineCol} onChange={(event) => setLineCol(event.target.value === "" ? "" : Number(event.target.value))}>
                    <option value="">auto</option>
                    {headers.map((header, index) => <option value={index} key={`engineer-line-${header}-${index}`}>{index + 1}. {header}</option>)}
                  </select>
                </label>
                <label className="field-row stacked span-2">
                  <span>Pattern</span>
                  <input value={pattern} onChange={(event) => setPattern(event.target.value)} />
                </label>
                <label className="field-row stacked">
                  <span>Confidence</span>
                  <input
                    max="0.99"
                    min="0.1"
                    onChange={(event) => setConfidenceThreshold(Number(event.target.value))}
                    step="0.01"
                    type="range"
                    value={confidenceThreshold}
                  />
                </label>
              </div>
              <div className="engineer-inline-controls">
                <label className="toggle-row">
                  <input type="checkbox" checked={detectSerials} onChange={(event) => setDetectSerials(event.target.checked)} />
                  <span>影像判讀流水號</span>
                </label>
                <StatusTile icon={<Braces size={18} />} title="Columns" value={columnSummary} tone={plan?.source.record_count ? "ready" : "warn"} />
                <StatusTile icon={<SearchCheck size={18} />} title="Threshold" value={`${Math.round(confidenceThreshold * 100)}%`} tone="ready" />
              </div>
              <div className="engineer-actions profile-actions">
                <button className="action-button" onClick={publishProfileToOneClick} disabled={profileBusy || !activeProfileFolder()}>
                  <ShieldCheck size={15} />
                  <span>{profileBusy ? "處理中" : hasDraftProfile ? "發布草稿到一鍵" : "發布到一鍵"}</span>
                </button>
                <button className="action-button" onClick={revertPublishedProfile} disabled={profileBusy || !hasPublishedProfile || profileHistoryCount < 1}>
                  <RefreshCcw size={15} />
                  <span>回復上一版</span>
                </button>
                <StatusTile
                  icon={<Settings size={18} />}
                  title="Profile"
                  value={`${hasPublishedProfile ? "published" : "not published"}${hasDraftProfile ? " · draft" : ""}${profileHistoryCount ? ` · ${profileHistoryCount} old` : ""}`}
                  tone={hasPublishedProfile ? "ready" : hasDraftProfile ? "warn" : "warn"}
                />
              </div>
            </div>

            <div className="engineer-section">
              <div className="panel-heading compact">
                <div>
                  <span>Job protocol</span>
                  <small>{batchJob?.job_id || "idle"}</small>
                </div>
              </div>
              <div className="engineer-job-grid">
                <StatusTile icon={<ScanLine size={18} />} title="Batch" value={batchJob ? `${batchJob.state} · ${batchJob.progress.percent}%` : "idle"} tone={batchRunning ? "ready" : batchJob?.state === "failed" ? "danger" : "warn"} />
                <StatusTile icon={<ClipboardCheck size={18} />} title="Selected" value={`${selectedCount} / ${rows.length}`} tone={selectedCount ? "ready" : "warn"} />
                <StatusTile icon={<CircleAlert size={18} />} title="Issues" value={String(issueRows.length)} tone={issueRows.length ? "warn" : "ready"} />
              </div>
              <div className="engineer-actions">
                <button className="action-button" onClick={generatePlan} disabled={busy || applyBusy}>
                  <RefreshCcw size={15} />
                  <span>{busy ? "產生中" : "重新產生"}</span>
                </button>
                <button className="action-button" onClick={batchRunning ? cancelBatchDetect : startBatchDetect} disabled={busy || batchBusy || applyBusy}>
                  <ScanLine size={15} />
                  <span>{batchRunning ? "取消判讀" : "批次判讀"}</span>
                </button>
                <button className="action-button" onClick={exportRenameCsv} disabled={!plan || busy || exportBusy}>
                  <FileJson size={15} />
                  <span>{exportBusy ? "匯出中" : "匯出 CSV"}</span>
                </button>
                <button className="action-button" onClick={() => void openRunLogDrawer()} disabled={runLogBusy}>
                  <FileSearch size={15} />
                  <span>{runLogBusy ? "讀取中" : "處理紀錄"}</span>
                </button>
              </div>
            </div>
          </main>

          <aside className="iso-engineer-panel">
            {visualPanel}
            <div className="legacy-fallback-card">
              <div>
                <div className="eyebrow">Legacy fallback</div>
                <h3>舊 ISO 工作台</h3>
              </div>
              <StatusTile icon={<PanelRightOpen size={18} />} title="Bridge" value={legacy.busy ? "opening" : "available"} tone="ready" />
              <button className="launch-button" onClick={legacy.launch} disabled={legacy.busy}>
                <PanelRightOpen size={18} />
                <span>{legacy.busy ? "開啟中" : "開啟舊工作台"}</span>
              </button>
            </div>
          </aside>
        </div>
      ) : (
      <div className="iso-workbench-grid">
        <aside className="iso-left-panel">
          <div className="panel-heading compact">
            <div>
              <span>來源</span>
              <small>{workFolder ? "folder autopilot" : pageFolder ? "page folder" : combinePdf ? "combine PDF" : "waiting"}</small>
            </div>
          </div>
          <PathPickerRow icon={<FolderOpen size={16} />} label="工作資料夾" value={workFolder} onPick={chooseWorkFolder} />
          <PathPickerRow icon={<FileText size={16} />} label="Combine PDF" value={combinePdf} onPick={chooseCombinePdf} />
          <PathPickerRow icon={<Layers3 size={16} />} label="Page folder" value={pageFolder} onPick={choosePageFolder} />
          <PathPickerRow icon={<Table2 size={16} />} label="ISO List" value={isoList} onPick={chooseIsoList} />
          <div className={`profile-chip ${hasPublishedProfile ? "ready" : "idle"}`}>
            <Settings size={14} />
            <span>Profile</span>
            <strong>{profileLabel}</strong>
          </div>

          <div className="iso-control-section">
            <div className="panel-heading compact">
              <div>
                <span>ISO List</span>
                <small>{plan?.source.record_count ? `${plan.source.record_count} rows` : "auto columns"}</small>
              </div>
            </div>
          </div>
          <label className="field-row stacked">
            <span>Sheet</span>
            {sheetOptions.length ? (
              <select value={sheetName} onChange={(event) => { setSheetName(event.target.value); setSerialCol(""); setLineCol(""); }}>
                {sheetOptions.map((sheet) => <option value={sheet} key={sheet}>{sheet}</option>)}
              </select>
            ) : (
              <input value={sheetName} onChange={(event) => setSheetName(event.target.value)} placeholder="auto" />
            )}
          </label>
          <label className="field-row stacked">
            <span>流水號欄</span>
            <select value={serialCol} onChange={(event) => setSerialCol(event.target.value === "" ? "" : Number(event.target.value))}>
              <option value="">auto</option>
              {headers.map((header, index) => <option value={index} key={`serial-${header}-${index}`}>{index + 1}. {header}</option>)}
            </select>
          </label>
          <label className="field-row stacked">
            <span>圖號/檔名欄</span>
            <select value={lineCol} onChange={(event) => setLineCol(event.target.value === "" ? "" : Number(event.target.value))}>
              <option value="">auto</option>
              {headers.map((header, index) => <option value={index} key={`line-${header}-${index}`}>{index + 1}. {header}</option>)}
            </select>
          </label>
          <label className="field-row stacked">
            <span>Pattern</span>
            <input value={pattern} onChange={(event) => setPattern(event.target.value)} />
          </label>
          <label className="toggle-row">
            <input type="checkbox" checked={detectSerials} onChange={(event) => setDetectSerials(event.target.checked)} />
            <span>影像判讀流水號</span>
          </label>

          <div className="iso-side-card checklist">
            <h3>Checklist</h3>
            <Gate label="PDF 來源" state={plan?.summary.total ? "ready" : workFolder || combinePdf || pageFolder ? "idle" : "warn"} />
            <Gate label="ISO List" state={plan?.source.record_count ? "ready" : isoList || workFolder ? "idle" : "warn"} />
            <Gate label="欄位對應" state={plan?.source.serial_col !== undefined && plan.source.line_col !== undefined ? "ready" : "idle"} />
            <Gate label="Profile" state={hasPublishedProfile ? "ready" : activeProfileFolder() ? "idle" : "warn"} />
            <Gate label="問題列" state={blockedCount ? "warn" : plan ? "ready" : "idle"} />
            <Gate label="舊工作台備援" state="ready" />
          </div>
        </aside>

        <main className="iso-table-panel">
          <div className="iso-metric-strip">
            <IsoMetric label="PDFs" value={rows.length} icon={<FileText size={17} />} />
            <IsoMetric label="Ready" value={readyCount} icon={<CircleCheck size={17} />} tone="ready" />
            <IsoMetric label="Warn" value={warnCount} icon={<CircleAlert size={17} />} tone="warn" />
            <IsoMetric label="Blocked" value={blockedCount} icon={<AlertTriangle size={17} />} tone="danger" />
            <IsoMetric label="Selected" value={selectedCount} icon={<ClipboardCheck size={17} />} tone="ready" />
          </div>

          <div className="iso-flow compact" aria-label="ISO workflow steps">
            {(plan?.steps ?? ISO_STEPS).map((step, index) => (
              <div className={`iso-step ${step.state}`} key={`${step.label}-${index}`}>
                <div className="step-index">{String(index + 1).padStart(2, "0")}</div>
                <div>
                  <strong>{step.label}</strong>
                  <span>{step.meta}</span>
                </div>
                {index < (plan?.steps.length ?? ISO_STEPS.length) - 1 ? <ChevronRight size={16} /> : null}
              </div>
            ))}
          </div>

          <div className="iso-table-toolbar">
            <div>
              <div className="eyebrow">Rename plan</div>
              <h2>命名草稿</h2>
            </div>
            <label className="table-search">
              <FileSearch size={15} />
              <input value={searchTerm} onChange={(event) => setSearchTerm(event.target.value)} placeholder="搜尋 old/new/流水號/圖號/狀態" />
            </label>
            <label className="table-sort">
              <span>排序</span>
              <select value={sortMode} onChange={(event) => setSortMode(event.target.value as IsoSortMode)}>
                <option value="page">頁序</option>
                <option value="status">狀態</option>
                <option value="confidence">信心</option>
                <option value="filename">檔名</option>
              </select>
            </label>
            <label className="toggle-row table-toggle">
              <input type="checkbox" checked={problemOnly} onChange={(event) => setProblemOnly(event.target.checked)} />
              <span>只看問題列</span>
            </label>
          </div>

          {plan ? (
            <IsoPlanTable
              rows={visibleRows}
              selectedRowId={selectedRow?.id ?? ""}
              toggleRow={toggleRow}
              toggleAll={setAllRowsSelected}
              updateRow={updateRow}
              selectRow={setSelectedRowId}
            />
          ) : <IsoEmptyPlan generatePlan={generatePlan} chooseWorkFolder={chooseWorkFolder} busy={busy} />}
        </main>

        <aside className="iso-inspector">
          {visualPanel}

          <div className="iso-side-card selected-row-card">
            <h3>目前列</h3>
            {selectedRow ? (
              <>
                <strong>{selectedRow.source_name}</strong>
                <span>{selectedRow.new_name || "尚無命名"}</span>
                <small>{selectedRow.note || selectedRow.vision_message || selectedRow.status}</small>
              </>
            ) : (
              <span>尚未選擇列</span>
            )}
          </div>

          <StatusTile icon={<FileText size={18} />} title="PDF source" value={compactPath(plan?.source.page_folder || pageFolder || combinePdf || workFolder || "waiting")} tone={plan?.summary.total ? "ready" : "warn"} />
          <StatusTile icon={<Table2 size={18} />} title="ISO List" value={compactPath(plan?.source.iso_list || isoList || "waiting")} tone={plan?.source.record_count ? "ready" : "warn"} />
          <StatusTile icon={<SearchCheck size={18} />} title="Sheet" value={plan?.source.sheet_name || sheetName || "auto"} tone="ready" />
          <StatusTile icon={<Braces size={18} />} title="Columns" value={columnSummary} tone={plan?.source.record_count ? "ready" : "warn"} />

          <div className="issue-stack">
            <h3>Issues</h3>
            {(issueRows.length ? issueRows.map((row) => ({ code: row.status.toUpperCase(), tone: row.status, title: row.source_name, detail: row.note || row.new_name || row.source_path })) : plan?.issues.length ? plan.issues : ISO_ISSUES).map((issue, index) => (
              <div className={`issue-card ${issue.tone}`} key={`${issue.code}-${index}`}>
                {issue.tone === "ready" ? <CircleCheck size={16} /> : issue.tone === "warn" ? <CircleAlert size={16} /> : <AlertTriangle size={16} />}
                <div>
                  <strong>{issue.code} · {issue.title}</strong>
                  <span>{issue.detail}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="iso-actions">
            <button className="action-button" onClick={generatePlan} disabled={busy || applyBusy}>
              <RefreshCcw size={15} />
              <span>重新產生</span>
            </button>
            <button className="action-button" onClick={batchRunning ? cancelBatchDetect : startBatchDetect} disabled={busy || batchBusy || applyBusy}>
              <ScanLine size={15} />
              <span>{batchRunning ? "取消判讀" : "批次判讀"}</span>
            </button>
            <button className="action-button" onClick={openDryRun} disabled={!selectedCount || blockedCount > 0 || warnCount > 0 || busy || applyBusy}>
              <ClipboardCheck size={15} />
              <span>套用更名</span>
            </button>
            <button className="action-button" onClick={exportRenameCsv} disabled={!plan || busy || exportBusy}>
              <FileJson size={15} />
              <span>匯出 CSV</span>
            </button>
            <button className="action-button" onClick={() => void openRunLogDrawer()} disabled={runLogBusy}>
              <FileSearch size={15} />
              <span>{runLogBusy ? "讀取中" : "處理紀錄"}</span>
            </button>
            <button className="action-button" onClick={legacy.launch} disabled={legacy.busy}>
              <PanelRightOpen size={15} />
              <span>{legacy.busy ? "開啟中" : "舊版"}</span>
            </button>
          </div>
        </aside>
      </div>
      )}
      {dryRunOpen && plan ? (
        <IsoDryRunDialog
          applyBusy={applyBusy}
          exportBusy={exportBusy}
          onApply={applySelectedRows}
          onClose={() => setDryRunOpen(false)}
          onExport={exportRenameCsv}
          rows={plan.rows.filter((row) => row.selected && row.status === "ready")}
          summary={plan.summary}
        />
      ) : null}
      {runLogOpen ? (
        <RunLogDrawer
          busy={runLogBusy}
          detail={runLogDetail}
          onClose={() => setRunLogOpen(false)}
          onRefresh={() => void refreshRunLogs()}
          onReplay={(runId) => void replayRunLog(runId)}
          onSelect={(runId) => void loadRunLogDetail(runId)}
          runs={runLogs}
        />
      ) : null}
      <IsoEventLog issues={workflowEvents} />
      {resultOpen && plan ? (
        <IsoResultDialog
          onClose={() => setResultOpen(false)}
          onDryRun={openDryRun}
          onExport={exportRenameCsv}
          plan={plan}
        />
      ) : null}
    </section>
  );
}

function useLegacyBridge(workbench: LegacyWorkbench): {
  busy: boolean;
  error: string;
  launch: () => Promise<void>;
  message: string;
} {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function launch() {
    setBusy(true);
    setMessage("");
    setError("");
    try {
      await openLegacyWorkbench(workbench);
      setMessage("已送出開啟請求");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  return { busy, error, launch, message };
}

function BridgeStatus({ error, message }: { error: string; message: string }) {
  if (!error && !message) {
    return null;
  }
  return <div className={`bridge-status ${error ? "error" : "ready"}`}>{error || message}</div>;
}

function Gate({ label, state }: { label: string; state: string }) {
  return (
    <div className={`gate ${state}`}>
      {state === "ready" ? <CircleCheck size={15} /> : state === "warn" ? <CircleAlert size={15} /> : <ScanLine size={15} />}
      <span>{label}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="detail-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function Info({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="info-item">
      {icon}
      <div>
        <span>{label}</span>
        <strong>{value || "Unknown"}</strong>
      </div>
    </div>
  );
}

function KeyValue({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="key-value">
      <span>{label}</span>
      <strong className={mono ? "mono" : ""}>{value}</strong>
    </div>
  );
}

function PillList({ values }: { values: string[] }) {
  if (!values.length) {
    return <div className="muted">No reasons were recorded.</div>;
  }
  return (
    <div className="pill-list">
      {values.map((value) => (
        <span key={value}>{value}</span>
      ))}
    </div>
  );
}

function PathGroup({ icon, label, values }: { icon: React.ReactNode; label: string; values: string[] }) {
  return (
    <div className="path-group">
      <div className="path-label">
        {icon}
        <span>{label}</span>
      </div>
      {values.length ? values.map((value) => <code key={value}>{value}</code>) : <span className="muted">None</span>}
    </div>
  );
}

function countLevel(report: ShutdownSafetyReport | null, level: SafeToKill): number {
  return report?.blockers.filter((blocker) => blocker.safe_to_kill === level).length ?? 0;
}

function getRiskScore(report: ShutdownSafetyReport | null): number {
  const blockers = report?.blockers ?? [];
  if (!blockers.length) {
    return 0;
  }
  return Math.max(...blockers.map((blocker) => LEVEL_SCORE[blocker.safe_to_kill]));
}

function getGuardState(report: ShutdownSafetyReport | null): "safe" | "caution" | "danger" {
  const score = getRiskScore(report);
  if (score >= 90) {
    return "danger";
  }
  if (score >= 50) {
    return "caution";
  }
  return "safe";
}

function modeIcon(mode: AppMode, size: number): React.ReactNode {
  switch (mode) {
    case "command":
      return <Home size={size} />;
    case "iso":
      return <FileText size={size} />;
    case "shutdown":
      return <Power size={size} />;
    case "cleanup":
      return <Trash2 size={size} />;
    case "locks":
      return <FileSearch size={size} />;
  }
}

function sortBlockers(items: ShutdownBlocker[]): ShutdownBlocker[] {
  return [...items].sort((left, right) => {
    const levelDelta = (LEVEL_RANK.get(left.safe_to_kill) ?? 99) - (LEVEL_RANK.get(right.safe_to_kill) ?? 99);
    return levelDelta || left.process_role.localeCompare(right.process_role) || left.pid - right.pid;
  });
}

function initialSurface(): SurfaceMode {
  const requested = new URLSearchParams(window.location.search).get("surface");
  if (requested === "dock" || requested === "cockpit") {
    return requested;
  }
  return isTauri() ? "dock" : "cockpit";
}

function isAppMode(value: unknown): value is AppMode {
  return value === "command" || value === "iso" || value === "shutdown" || value === "cleanup" || value === "locks";
}

async function applyWindowSurface(surface: SurfaceMode, dockCollapsed: boolean, dockEdge: DockEdge, dockOffset: number): Promise<void> {
  if (!isTauri()) {
    return;
  }

  const appWindow = getCurrentWindow();
  if (surface === "dock") {
    const { width, height } = dockSizeForEdge(dockEdge, dockCollapsed);
    await safeWindowCall(appWindow.setSizeConstraints(null));
    await safeWindowCall(appWindow.setMinSize(null));
    await safeWindowCall(appWindow.setMaxSize(null));
    await safeWindowCall(appWindow.setResizable(false));
    await safeWindowCall(appWindow.setDecorations(false));
    await safeWindowCall(appWindow.setAlwaysOnBottom(false));
    await safeWindowCall(appWindow.setAlwaysOnTop(true));
    await safeWindowCall(appWindow.setSkipTaskbar(dockCollapsed));
    await safeWindowCall(appWindow.setShadow(!dockCollapsed));
    await snapDockToEdge(width, height, dockEdge, dockOffset);
    await safeWindowCall(appWindow.show());
    if (!dockCollapsed) {
      await safeWindowCall(appWindow.setFocus());
    }
    return;
  }

  await safeWindowCall(appWindow.setSkipTaskbar(false));
  await safeWindowCall(appWindow.setAlwaysOnTop(false));
  await safeWindowCall(appWindow.setResizable(true));
  await safeWindowCall(appWindow.setDecorations(true));
  await safeWindowCall(appWindow.setSizeConstraints({ minWidth: 960, minHeight: 620 }));
  await safeWindowCall(appWindow.setSize(new LogicalSize(1180, 760)));
  await safeWindowCall(appWindow.center());
  await safeWindowCall(appWindow.setFocus());
}

async function snapDockToEdge(width: number, height: number, edge: DockEdge, offset: number): Promise<void> {
  const appWindow = getCurrentWindow();
  const scale = await appWindow.scaleFactor().catch(() => 1);
  const monitor = await currentMonitor().catch(() => undefined);
  await safeWindowCall(appWindow.setSize(new LogicalSize(width, height)));

  if (!monitor) {
    return;
  }

  const actualSize = await appWindow.outerSize().catch(() => undefined);
  const size = actualSize ?? {
    width: Math.round(width * scale),
    height: Math.round(height * scale),
  };
  const placement = dockPlacementForEdge(monitor.workArea, edge, size, offset);
  await safeWindowCall(appWindow.setPosition(new PhysicalPosition(placement.x, placement.y)));
}

async function snapDraggedDockToNearestEdge(collapsed: boolean): Promise<{ edge: DockEdge; offset: number } | null> {
  if (!isTauri()) {
    return null;
  }

  const appWindow = getCurrentWindow();
  const scale = await appWindow.scaleFactor().catch(() => 1);
  const monitor = await currentMonitor().catch(() => undefined);
  const position = await appWindow.outerPosition().catch(() => undefined);
  const size = await appWindow.outerSize().catch(() => undefined);
  if (!monitor || !position || !size) {
    return null;
  }

  const center = {
    x: position.x + Math.round(size.width / 2),
    y: position.y + Math.round(size.height / 2),
  };
  const edge = nearestDockEdge(monitor.workArea, center.x, center.y);
  const logicalSize = dockSizeForEdge(edge, collapsed);
  const snapSize = {
    width: Math.round(logicalSize.width * scale),
    height: Math.round(logicalSize.height * scale),
  };
  return {
    edge,
    offset: dockOffsetFromPoint(monitor.workArea, edge, center.x, center.y, snapSize),
  };
}

function dockSizeForEdge(edge: DockEdge, collapsed: boolean): { width: number; height: number } {
  if (!collapsed) {
    return { width: 392, height: 438 };
  }
  return edge === "top" || edge === "bottom" ? { width: 168, height: 28 } : { width: 28, height: 168 };
}

function dockPlacementForEdge(
  area: { position: { x: number; y: number }; size: { width: number; height: number } },
  edge: DockEdge,
  dockSize: { width: number; height: number },
  offset: number,
): { x: number; y: number } {
  const workX = area.position.x;
  const workY = area.position.y;
  const workWidth = area.size.width;
  const workHeight = area.size.height;
  const maxX = workX + Math.max(0, workWidth - dockSize.width);
  const maxY = workY + Math.max(0, workHeight - dockSize.height);
  const clampedOffset = clamp(offset, 0, 1);

  if (edge === "top" || edge === "bottom") {
    return {
      x: clamp(workX + Math.round(Math.max(0, workWidth - dockSize.width) * clampedOffset), workX, maxX),
      y: edge === "top" ? workY : maxY,
    };
  }

  return {
    x: edge === "left" ? workX : maxX,
    y: clamp(workY + Math.round(Math.max(0, workHeight - dockSize.height) * clampedOffset), workY, maxY),
  };
}

function nearestDockEdge(
  area: { position: { x: number; y: number }; size: { width: number; height: number } },
  pointX: number,
  pointY: number,
): DockEdge {
  const distances: Record<DockEdge, number> = {
    top: Math.abs(pointY - area.position.y),
    bottom: Math.abs(pointY - (area.position.y + area.size.height)),
    left: Math.abs(pointX - area.position.x),
    right: Math.abs(pointX - (area.position.x + area.size.width)),
  };
  return (Object.entries(distances).sort((left, right) => left[1] - right[1])[0]?.[0] as DockEdge | undefined) ?? "right";
}

function dockOffsetFromPoint(
  area: { position: { x: number; y: number }; size: { width: number; height: number } },
  edge: DockEdge,
  pointX: number,
  pointY: number,
  dockSize: { width: number; height: number },
): number {
  if (edge === "top" || edge === "bottom") {
    const available = Math.max(1, area.size.width - dockSize.width);
    return clamp((pointX - area.position.x - dockSize.width / 2) / available, 0, 1);
  }

  const available = Math.max(1, area.size.height - dockSize.height);
  return clamp((pointY - area.position.y - dockSize.height / 2) / available, 0, 1);
}

function initialDockEdge(): DockEdge {
  const saved = window.localStorage.getItem(DOCK_EDGE_STORAGE_KEY);
  return saved === "top" || saved === "bottom" || saved === "left" || saved === "right" ? saved : "right";
}

function initialDockOffset(): number {
  const saved = Number(window.localStorage.getItem(DOCK_OFFSET_STORAGE_KEY));
  return Number.isFinite(saved) ? clamp(saved, 0, 1) : 0.42;
}

function saveDockPlacement(edge: DockEdge, offset: number): void {
  window.localStorage.setItem(DOCK_EDGE_STORAGE_KEY, edge);
  window.localStorage.setItem(DOCK_OFFSET_STORAGE_KEY, String(clamp(offset, 0, 1)));
}

function clamp(value: number, min: number, max: number): number {
  if (Number.isNaN(value)) {
    return min;
  }
  return Math.min(Math.max(value, min), max);
}

async function safeWindowCall(action: Promise<unknown>): Promise<void> {
  try {
    await action;
  } catch (caught) {
    console.warn("Tauri window call failed", caught);
  }
}

async function startWindowDrag(): Promise<void> {
  if (!isTauri()) {
    return;
  }
  await getCurrentWindow().startDragging().catch(() => undefined);
}
