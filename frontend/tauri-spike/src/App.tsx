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
import { useEffect, useMemo, useRef, useState } from "react";
import {
  applyIsoPlan,
  cancelIsoJob,
  exportIsoPlanCsv,
  loadIsoJobStatus,
  loadIsoProfile,
  loadIsoPreview,
  pickIsoCombinePdf,
  pickIsoListFile,
  pickIsoPageFolder,
  pickIsoWorkFolder,
  runIsoPlan,
  saveIsoProfile,
  startIsoBatchDetect,
  type IsoJobPayload,
  type IsoPlanRow,
  type IsoProfilePayload,
  type IsoPreviewPayload,
  type IsoRegion,
  type IsoWorkflowIssue,
  type IsoWorkflowRequest,
  type IsoWorkflowPlan,
} from "./isoWorkflow";
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
type IsoWorkbenchView = "workbench" | "autopilot" | "engineer";

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

const DEFAULT_SERIAL_REGION: IsoRegion = { left: 0.62, top: 0, width: 0.38, height: 0.24 };
const DEFAULT_DRAWING_REGION: IsoRegion = { left: 0.5, top: 0.66, width: 0.5, height: 0.34 };

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
  const focusExpandArmedRef = useRef(false);

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
    if (!reportLoaded && (surface === "cockpit" || !dockCollapsed)) {
      void refresh();
    }
  }, [dockCollapsed, reportLoaded, surface]);

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
    const armFocusExpand = window.setTimeout(() => {
      focusExpandArmedRef.current = true;
    }, 900);

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
      window.clearTimeout(armFocusExpand);
      unlisten?.();
    };
  }, []);

  useEffect(() => {
    function handleSurfaceEvent(event: Event) {
      const detail = (event as CustomEvent<{ surface?: SurfaceMode; collapsed?: boolean }>).detail;
      if (detail?.surface === "cockpit") {
        setSurface("cockpit");
        setDockCollapsed(false);
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

  useEffect(() => {
    if (!isTauri()) {
      return;
    }

    let unlisten: (() => void) | undefined;
    void getCurrentWindow().onFocusChanged(({ payload: focused }) => {
      if (focused && focusExpandArmedRef.current && surfaceRef.current === "dock" && dockCollapsedRef.current) {
        window.setTimeout(() => {
          if (!dockDragSnapArmedRef.current && surfaceRef.current === "dock" && dockCollapsedRef.current) {
            setDockCollapsed(false);
          }
        }, 80);
      }
    }).then((handler) => {
      unlisten = handler;
    });

    return () => {
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
    if (!reportLoaded) {
      void refresh();
    }
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
  const [isoView, setIsoView] = useState<IsoWorkbenchView>("workbench");
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
  const previewCacheRef = useRef(new Map<string, IsoPreviewPayload>());

  function requestPayload(rows?: IsoPlanRow[]) {
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
    if (result.exists) {
      parts.push(`Profile ${compactPath(result.folder)}`);
    }
    return parts.length ? `已自動載入：${parts.join(" · ")}` : fallback;
  }

  async function chooseWorkFolder() {
    try {
      const path = await pickIsoWorkFolder();
      if (path) {
        setWorkFolder(path);
        setCombinePdf("");
        setPageFolder("");
        setPlan(null);
        const restored = await restoreProfile({ work_folder: path });
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
        const savedProfile = await saveIsoProfile({
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
        profileNote = " Profile 已保存。";
      } catch (caught) {
        profileNote = ` Profile 保存失敗：${caught instanceof Error ? caught.message : String(caught)}`;
      }
      setMessage(`已產生命名草稿：${result.summary.selected} / ${result.summary.total} 可套用。${profileNote}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  function openDryRun() {
    if (!plan) {
      return;
    }
    const selected = plan.rows.filter((row) => row.selected && row.status !== "blocked");
    if (!selected.length) {
      setError("沒有可套用的列；請先勾選 ready/warn 列或修正 blocked 列。");
      return;
    }
    setDryRunOpen(true);
  }

  async function applySelectedRows() {
    if (!plan) {
      return;
    }
    const selected = plan.rows.filter((row) => row.selected && row.status !== "blocked");
    setApplyBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await applyIsoPlan(requestPayload(selected));
      setDryRunOpen(false);
      setMessage(result.message);
      await generatePlan();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
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

  function updateRow(rowId: string, field: "serial" | "line_no" | "new_name", value: string) {
    updatePlanRows((rows) => rows.map((row) => {
      if (row.id !== rowId) {
        return row;
      }
      const next = { ...row, [field]: value, note: "manual edit" };
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
    const first = plan?.rows.find((row) => row.status === "blocked" || row.status === "warn");
    if (first) {
      setSelectedRowId(first.id);
      setProblemOnly(true);
    }
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
    updatePlanRows((rows) => rows.map((row) => row.id === selectedRow.id ? { ...row, status: "ready", note: "", vision_message: "", selected: row.new_name !== row.source_name } : row));
  }

  const rows = plan?.rows ?? [];
  const selectedCount = rows.filter((row) => row.selected && row.status !== "blocked").length;
  const blockedCount = rows.filter((row) => row.status === "blocked").length;
  const warnCount = rows.filter((row) => row.status === "warn").length;
  const readyCount = rows.filter((row) => row.status === "ready").length;
  const issueRows = rows.filter((row) => row.status === "blocked" || row.status === "warn");
  const visibleRows = useMemo(() => filterIsoRows(rows, searchTerm, problemOnly), [rows, searchTerm, problemOnly]);
  const selectedRow = rows.find((row) => row.id === selectedRowId) ?? rows[0];
  const columnSummary = plan?.source.headers && plan.source.serial_col !== undefined && plan.source.line_col !== undefined
    ? `${plan.source.headers[plan.source.serial_col] ?? `col ${plan.source.serial_col + 1}`} -> ${plan.source.headers[plan.source.line_col] ?? `col ${plan.source.line_col + 1}`}`
    : "auto";
  const headers = plan?.source.headers ?? [];
  const sheetOptions = plan?.source.sheet_options ?? (sheetName ? [sheetName] : []);
  const profileLabel = profileBusy ? "loading" : profile?.exists ? compactPath(profile.folder) : activeProfileFolder() ? "default profile" : "waiting";
  const batchRunning = batchJob?.state === "queued" || batchJob?.state === "running" || batchJob?.state === "cancel_requested";
  const workflowEvents = [...(batchJob?.events ?? []), ...(plan?.issues ?? [])];

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
          if (job.result && (job.state === "completed" || job.state === "cancelled")) {
            setPlan(job.result);
            setSelectedRowId(job.result.rows[0]?.id ?? "");
            setResultOpen(true);
            setMessage(job.state === "completed" ? "批次判讀完成，命名草稿已更新。" : "批次判讀已取消，保留已完成列。");
          }
          if (job.error) {
            setError(job.error);
          }
        })
        .catch((caught) => {
          if (!cancelled) {
            setError(caught instanceof Error ? caught.message : String(caught));
          }
        });
    }, 900);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [batchJob?.job_id, batchRunning]);

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
          <div className="iso-view-switch" role="tablist" aria-label="ISO view">
            {([
              ["workbench", "工作臺", Workflow],
              ["autopilot", "Autopilot", Bot],
              ["engineer", "Engineer", Settings],
            ] as const).map(([view, label, Icon]) => (
              <button
                aria-selected={isoView === view}
                className={isoView === view ? "active" : ""}
                key={view}
                onClick={() => setIsoView(view)}
                role="tab"
              >
                <Icon size={14} />
                <span>{label}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="iso-top-actions">
          <button className="action-button" onClick={chooseProblemRow} disabled={!issueRows.length}>
            <CircleAlert size={15} />
            <span>問題列 {issueRows.length}</span>
          </button>
          <button className="action-button" onClick={() => setResultOpen(true)} disabled={!plan}>
            <Gauge size={15} />
            <span>結果</span>
          </button>
          <button className="launch-button" onClick={generatePlan} disabled={busy || applyBusy}>
            <WandSparkles size={18} />
            <span>{busy ? "產生中" : "產生命名草稿"}</span>
          </button>
          <button className="action-button" onClick={batchRunning ? cancelBatchDetect : startBatchDetect} disabled={busy || batchBusy || applyBusy}>
            <ScanLine size={15} />
            <span>{batchRunning ? `取消判讀 ${batchJob?.progress.percent ?? 0}%` : "批次判讀"}</span>
          </button>
          <button className="launch-button" onClick={openDryRun} disabled={!selectedCount || busy || applyBusy}>
            <ClipboardCheck size={18} />
            <span>{applyBusy ? "套用中" : `套用 ${selectedCount} 筆`}</span>
          </button>
          <button className="action-button" onClick={exportRenameCsv} disabled={!plan || busy || exportBusy}>
            <FileJson size={15} />
            <span>{exportBusy ? "匯出中" : "匯出 CSV"}</span>
          </button>
          <button className="icon-button" onClick={() => setIsoView("engineer")}>
            <Settings size={16} />
            <span>Engineer</span>
          </button>
        </div>
      </div>

      <BridgeStatus error={error || legacy.error} message={message || legacy.message} />
      {batchJob ? (
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
        <div className="iso-autopilot-grid">
          <main className="iso-autopilot-main">
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

            <div className="autopilot-command-grid">
              <button className="autopilot-run-card primary" onClick={generatePlan} disabled={busy || applyBusy}>
                <WandSparkles size={24} />
                <span>{busy ? "產生中" : "產生命名草稿"}</span>
                <strong>{plan ? `${plan.summary.ready} ready` : "plan"}</strong>
              </button>
              <button className="autopilot-run-card" onClick={batchRunning ? cancelBatchDetect : startBatchDetect} disabled={busy || batchBusy || applyBusy}>
                <ScanLine size={24} />
                <span>{batchRunning ? "取消判讀" : "批次判讀"}</span>
                <strong>{batchJob ? `${batchJob.progress.percent}%` : "vision"}</strong>
              </button>
              <button className="autopilot-run-card" onClick={() => setResultOpen(true)} disabled={!plan}>
                <Gauge size={24} />
                <span>結果</span>
                <strong>{issueRows.length ? `${issueRows.length} issues` : plan ? "ready" : "waiting"}</strong>
              </button>
              <button className="autopilot-run-card" onClick={openDryRun} disabled={!selectedCount || busy || applyBusy}>
                <ClipboardCheck size={24} />
                <span>{applyBusy ? "套用中" : "dry-run"}</span>
                <strong>{selectedCount} rows</strong>
              </button>
            </div>

            <div className="autopilot-status-grid">
              <StatusTile icon={<FolderOpen size={18} />} title="Work folder" value={compactPath(workFolder || parentPath(combinePdf) || pageFolder || "waiting")} tone={workFolder || combinePdf || pageFolder ? "ready" : "warn"} />
              <StatusTile icon={<FileText size={18} />} title="Combine PDF" value={compactPath(combinePdf || plan?.source.combine_pdf || "waiting")} tone={combinePdf || plan?.source.combine_pdf ? "ready" : "warn"} />
              <StatusTile icon={<Layers3 size={18} />} title="Pages" value={compactPath(pageFolder || plan?.source.page_folder || "waiting")} tone={pageFolder || plan?.source.page_folder ? "ready" : "warn"} />
              <StatusTile icon={<Table2 size={18} />} title="ISO List" value={compactPath(isoList || plan?.source.iso_list || "waiting")} tone={isoList || plan?.source.iso_list ? "ready" : "warn"} />
            </div>

            {plan ? (
              <div className="autopilot-result-strip">
                {(issueRows.length ? issueRows.slice(0, 5) : plan.rows.slice(0, 5)).map((row) => (
                  <button className={`autopilot-row-card ${row.status} ${selectedRow?.id === row.id ? "selected" : ""}`} key={row.id} onClick={() => setSelectedRowId(row.id)}>
                    <span>{String(row.page).padStart(3, "0")}</span>
                    <strong>{row.source_name}</strong>
                    <small>{row.note || row.new_name || row.status}</small>
                  </button>
                ))}
              </div>
            ) : (
              <IsoEmptyPlan generatePlan={generatePlan} chooseWorkFolder={chooseWorkFolder} busy={busy} />
            )}
          </main>

          <aside className="iso-autopilot-side">
            {visualPanel}
            <div className="iso-actions">
              <button className="action-button" onClick={exportRenameCsv} disabled={!plan || busy || exportBusy}>
                <FileJson size={15} />
                <span>{exportBusy ? "匯出中" : "匯出 CSV"}</span>
              </button>
              <button className="action-button" onClick={() => setIsoView("engineer")}>
                <Settings size={15} />
                <span>Engineer</span>
              </button>
            </div>
          </aside>
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
            <div className={`profile-chip ${profile?.exists ? "ready" : "idle"}`}>
              <Settings size={14} />
              <span>Profile</span>
              <strong>{profileLabel}</strong>
            </div>
            <div className="engineer-section">
              <div className="eyebrow">Quality gates</div>
              <Gate label="PDF 來源" state={plan?.summary.total ? "ready" : workFolder || combinePdf || pageFolder ? "idle" : "warn"} />
              <Gate label="ISO List" state={plan?.source.record_count ? "ready" : isoList || workFolder ? "idle" : "warn"} />
              <Gate label="欄位對應" state={plan?.source.serial_col !== undefined && plan.source.line_col !== undefined ? "ready" : "idle"} />
              <Gate label="Profile" state={profile?.exists ? "ready" : activeProfileFolder() ? "idle" : "warn"} />
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
          <div className={`profile-chip ${profile?.exists ? "ready" : "idle"}`}>
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
            <Gate label="Profile" state={profile?.exists ? "ready" : activeProfileFolder() ? "idle" : "warn"} />
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
            <button className="action-button" onClick={openDryRun} disabled={!selectedCount || busy || applyBusy}>
              <ClipboardCheck size={15} />
              <span>套用更名</span>
            </button>
            <button className="action-button" onClick={exportRenameCsv} disabled={!plan || busy || exportBusy}>
              <FileJson size={15} />
              <span>匯出 CSV</span>
            </button>
            <button className="action-button" onClick={() => setIsoView("engineer")}>
              <Settings size={15} />
              <span>工程模式</span>
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
          rows={plan.rows.filter((row) => row.selected && row.status !== "blocked")}
          summary={plan.summary}
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

function PathPickerRow({ icon, label, onPick, value }: { icon: React.ReactNode; label: string; onPick: () => void; value: string }) {
  return (
    <div className="path-picker-row">
      <div className="path-picker-icon">{icon}</div>
      <div>
        <span>{label}</span>
        <strong title={value}>{value ? compactPath(value) : "not selected"}</strong>
      </div>
      <button className="dock-icon-button" onClick={onPick} title={label}>
        <FolderOpen size={15} />
      </button>
    </div>
  );
}

function IsoMetric({ icon, label, value, tone = "neutral" }: { icon: React.ReactNode; label: string; value: number; tone?: string }) {
  return (
    <div className={`iso-metric ${tone}`}>
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function IsoPlanTable({
  rows,
  selectedRowId,
  selectRow,
  toggleRow,
  updateRow,
}: {
  rows: IsoPlanRow[];
  selectedRowId: string;
  selectRow: (rowId: string) => void;
  toggleRow: (rowId: string) => void;
  updateRow: (rowId: string, field: "serial" | "line_no" | "new_name", value: string) => void;
}) {
  return (
    <div className="iso-table live">
      <div className="iso-table-head">
        <span>Use</span>
        <span>Page</span>
        <span>Old file</span>
        <span>Serial</span>
        <span>Line / drawing</span>
        <span>Conf</span>
        <span>Status</span>
        <span>New filename</span>
      </div>
      {rows.map((row) => (
        <div className={`iso-table-row ${row.status} ${selectedRowId === row.id ? "selected" : ""}`} key={row.id} onClick={() => selectRow(row.id)}>
          <label className="row-check">
            <input type="checkbox" checked={row.selected} disabled={row.status === "blocked"} onChange={() => toggleRow(row.id)} onClick={(event) => event.stopPropagation()} />
          </label>
          <span>{String(row.page).padStart(3, "0")}</span>
          <strong title={row.source_path}>{row.source_name}</strong>
          <input className="table-cell-input serial" value={row.serial} onChange={(event) => updateRow(row.id, "serial", event.target.value)} onClick={(event) => event.stopPropagation()} />
          <input className="table-cell-input" value={row.line_no} onChange={(event) => updateRow(row.id, "line_no", event.target.value)} onClick={(event) => event.stopPropagation()} />
          <span className={`confidence-chip ${row.confidence >= 0.8 ? "ready" : row.confidence > 0 ? "warn" : "idle"}`}>{row.confidence ? `${Math.round(row.confidence * 100)}%` : "-"}</span>
          <span className={`plan-state ${row.status}`}>{row.status}</span>
          <input className="table-cell-input mono" value={row.new_name} title={row.note || row.target_path} onChange={(event) => updateRow(row.id, "new_name", event.target.value)} onClick={(event) => event.stopPropagation()} />
        </div>
      ))}
    </div>
  );
}

function IsoDryRunDialog({
  applyBusy,
  exportBusy,
  onApply,
  onClose,
  onExport,
  rows,
  summary,
}: {
  applyBusy: boolean;
  exportBusy: boolean;
  onApply: () => void;
  onClose: () => void;
  onExport: () => void;
  rows: IsoPlanRow[];
  summary: IsoWorkflowPlan["summary"];
}) {
  const blockedOrWarn = summary.blocked + summary.warn;
  return (
    <div className="modal-backdrop" role="presentation">
      <div className="dry-run-dialog" role="dialog" aria-modal="true" aria-label="更名前 dry-run">
        <div className="dry-run-head">
          <div>
            <div className="eyebrow">Dry-run rename plan</div>
            <h2>更名前確認</h2>
          </div>
          <button className="dock-icon-button" onClick={onClose} title="關閉">
            <Minimize2 size={15} />
          </button>
        </div>

        <div className="dry-run-metrics">
          <IsoMetric label="Will rename" value={rows.length} icon={<ClipboardCheck size={17} />} tone="ready" />
          <IsoMetric label="Warn" value={summary.warn} icon={<CircleAlert size={17} />} tone="warn" />
          <IsoMetric label="Blocked" value={summary.blocked} icon={<AlertTriangle size={17} />} tone="danger" />
        </div>

        <div className={`dry-run-warning ${blockedOrWarn ? "warn" : "ready"}`}>
          {blockedOrWarn ? `${blockedOrWarn} 筆需要注意；blocked 不會套用。` : "所有勾選列皆可套用。"}
        </div>

        <div className="dry-run-table">
          <div className="dry-run-table-head">
            <span>Page</span>
            <span>Old</span>
            <span>New</span>
            <span>Status</span>
          </div>
          {rows.slice(0, 80).map((row) => (
            <div className={`dry-run-row ${row.status}`} key={row.id}>
              <span>{row.page}</span>
              <strong title={row.source_name}>{row.source_name}</strong>
              <code title={row.new_name}>{row.new_name}</code>
              <span>{row.status}</span>
            </div>
          ))}
        </div>

        <div className="dry-run-actions">
          <button className="action-button" onClick={onExport} disabled={exportBusy}>
            <FileJson size={15} />
            <span>{exportBusy ? "匯出中" : "匯出 CSV"}</span>
          </button>
          <button className="action-button" onClick={onClose} disabled={applyBusy}>
            <Minimize2 size={15} />
            <span>返回校對</span>
          </button>
          <button className="launch-button" onClick={onApply} disabled={!rows.length || applyBusy}>
            <ClipboardCheck size={18} />
            <span>{applyBusy ? "套用中" : `確認套用 ${rows.length} 筆`}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

function IsoResultDialog({
  onClose,
  onDryRun,
  onExport,
  plan,
}: {
  onClose: () => void;
  onDryRun: () => void;
  onExport: () => void;
  plan: IsoWorkflowPlan;
}) {
  const issueRows = plan.rows.filter((row) => row.status === "warn" || row.status === "blocked");
  return (
    <div className="modal-backdrop" role="presentation">
      <div className="result-dialog" role="dialog" aria-modal="true" aria-label="ISO 結果">
        <div className="dry-run-head">
          <div>
            <div className="eyebrow">ISO result</div>
            <h2>命名草稿結果</h2>
          </div>
          <button className="dock-icon-button" onClick={onClose} title="關閉">
            <Minimize2 size={15} />
          </button>
        </div>
        <div className="dry-run-metrics">
          <IsoMetric label="Total" value={plan.summary.total} icon={<FileText size={17} />} />
          <IsoMetric label="Ready" value={plan.summary.ready} icon={<CircleCheck size={17} />} tone="ready" />
          <IsoMetric label="Issues" value={issueRows.length} icon={<CircleAlert size={17} />} tone={issueRows.length ? "warn" : "ready"} />
        </div>
        <div className="result-issue-list">
          {(issueRows.length ? issueRows : plan.rows.slice(0, 5)).map((row) => (
            <div className={`issue-card ${row.status}`} key={row.id}>
              {row.status === "ready" ? <CircleCheck size={16} /> : row.status === "warn" ? <CircleAlert size={16} /> : <AlertTriangle size={16} />}
              <div>
                <strong>{row.source_name}</strong>
                <span>{row.note || row.new_name || row.status}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="dry-run-actions">
          <button className="action-button" onClick={onExport}>
            <FileJson size={15} />
            <span>匯出 CSV</span>
          </button>
          <button className="launch-button" onClick={onDryRun} disabled={!plan.summary.selected}>
            <ClipboardCheck size={18} />
            <span>開啟 dry-run</span>
          </button>
        </div>
      </div>
    </div>
  );
}

function IsoEventLog({ issues }: { issues: IsoWorkflowIssue[] }) {
  const items = issues.slice(-8).reverse();
  return (
    <div className="iso-event-log">
      <div className="eyebrow">Event log</div>
      {items.length ? items.map((issue, index) => (
        <div className={`event-log-item ${issue.tone}`} key={`${issue.code}-${index}`}>
          <strong>{issue.code}</strong>
          <span>{issue.title}</span>
          <small>{issue.detail}</small>
        </div>
      )) : <span className="muted">等待 workflow 事件</span>}
    </div>
  );
}

function IsoEmptyPlan({ busy, chooseWorkFolder, generatePlan }: { busy: boolean; chooseWorkFolder: () => void; generatePlan: () => void }) {
  return (
    <div className="iso-empty-plan">
      <GitBranch size={30} />
      <strong>等待命名草稿</strong>
      <span>選工作資料夾可自動找 PDF 與 ISO List；也可手動指定來源。</span>
      <div className="bridge-actions">
        <button className="action-button" onClick={chooseWorkFolder} disabled={busy}>
          <FolderOpen size={16} />
          <span>選工作資料夾</span>
        </button>
        <button className="launch-button" onClick={generatePlan} disabled={busy}>
          <WandSparkles size={18} />
          <span>{busy ? "產生中" : "產生命名草稿"}</span>
        </button>
      </div>
    </div>
  );
}

function IsoVisualPanel({
  activeRoi,
  adoptPreviewVision,
  busy,
  confirmSelectedRow,
  drawingRegion,
  error,
  nextProblem,
  preview,
  resetRoi,
  row,
  serialRegion,
  setActiveRoi,
  updateActiveRoi,
}: {
  activeRoi: "serial" | "drawing";
  adoptPreviewVision: () => void;
  busy: boolean;
  confirmSelectedRow: () => void;
  drawingRegion: IsoRegion;
  error: string;
  nextProblem: () => void;
  preview: IsoPreviewPayload | null;
  resetRoi: (region?: "serial" | "drawing") => void;
  row?: IsoPlanRow;
  serialRegion: IsoRegion;
  setActiveRoi: (region: "serial" | "drawing") => void;
  updateActiveRoi: (field: keyof IsoRegion, value: number) => void;
}) {
  const activeRegion = activeRoi === "serial" ? serialRegion : drawingRegion;
  return (
    <div className="iso-visual-panel">
      <div className="panel-heading compact">
        <div>
          <span>PDF visual check</span>
          <small>{row?.source_name ?? "no page selected"}</small>
        </div>
      </div>

      <div className={`pdf-page-frame ${preview ? "ready" : ""}`}>
        {preview ? (
          <div className="pdf-page-canvas">
            <img src={preview.page.image} alt={`PDF preview ${preview.source_name}`} />
            <RoiBox active={activeRoi === "serial"} region={serialRegion} tone="serial" />
            <RoiBox active={activeRoi === "drawing"} region={drawingRegion} tone="drawing" />
          </div>
        ) : (
          <div className="pdf-preview-empty">
            <FileSearch size={26} />
            <span>{busy ? "載入 PDF 預覽中" : error || "選擇命名列後顯示 PDF 預覽"}</span>
          </div>
        )}
      </div>

      <div className="roi-panel">
        <div className="segmented mini">
          <button className={activeRoi === "serial" ? "active" : ""} onClick={() => setActiveRoi("serial")}>流水號 ROI</button>
          <button className={activeRoi === "drawing" ? "active" : ""} onClick={() => setActiveRoi("drawing")}>圖號 ROI</button>
        </div>
        <div className="roi-controls">
          {(["left", "top", "width", "height"] as Array<keyof IsoRegion>).map((field) => (
            <label className="roi-slider" key={field}>
              <span>{field}</span>
              <input
                max={field === "left" || field === "top" ? 0.95 : 1}
                min={field === "width" || field === "height" ? 0.05 : 0}
                onChange={(event) => updateActiveRoi(field, Number(event.target.value))}
                step="0.01"
                type="range"
                value={activeRegion[field]}
              />
              <strong>{activeRegion[field].toFixed(2)}</strong>
            </label>
          ))}
        </div>
        <button className="action-button" onClick={() => resetRoi()}>
          <RefreshCcw size={14} />
          <span>重設目前 ROI</span>
        </button>
      </div>

      <div className="pdf-crop-grid">
        <PreviewCrop title="右上流水號" image={preview?.serial_crop.image} />
        <PreviewCrop title="右下圖號" image={preview?.drawing_crop.image} />
      </div>

      <div className="vision-readout">
        <SearchCheck size={15} />
        <div>
          <strong>{preview?.vision?.text ? `判讀：${preview.vision.text}` : "判讀：待確認"}</strong>
          <span>
            {preview?.vision
              ? `confidence ${Math.round(preview.vision.confidence * 100)}% · ${preview.vision.message || "no message"}`
              : busy
                ? "rendering"
                : error || "可用裁切圖人工確認流水號與圖號"}
          </span>
        </div>
      </div>
      <div className="row-review-actions">
        <button className="action-button" onClick={adoptPreviewVision} disabled={!preview?.vision?.text}>
          <SearchCheck size={14} />
          <span>採用判讀值</span>
        </button>
        <button className="action-button" onClick={confirmSelectedRow} disabled={!row}>
          <CircleCheck size={14} />
          <span>確認此列</span>
        </button>
        <button className="action-button" onClick={nextProblem}>
          <CircleAlert size={14} />
          <span>下一問題</span>
        </button>
      </div>
    </div>
  );
}

function RoiBox({ active, region, tone }: { active: boolean; region: IsoRegion; tone: "serial" | "drawing" }) {
  return (
    <div
      className={`roi-box ${tone} ${active ? "active" : ""}`}
      style={{
        left: `${region.left * 100}%`,
        top: `${region.top * 100}%`,
        width: `${region.width * 100}%`,
        height: `${region.height * 100}%`,
      }}
    />
  );
}

function PreviewCrop({ image, title }: { image?: string; title: string }) {
  return (
    <div className="preview-crop">
      <span>{title}</span>
      {image ? <img src={image} alt={title} /> : <div />}
    </div>
  );
}

function filterIsoRows(rows: IsoPlanRow[], searchTerm: string, problemOnly: boolean): IsoPlanRow[] {
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
      row.note,
      row.vision_message,
    ].join(" ").toLowerCase();
    return terms.every((term) => text.includes(term));
  });
}

function normalizeIsoRows(rows: IsoPlanRow[]): IsoPlanRow[] {
  const nameCounts = new Map<string, number>();
  for (const row of rows) {
    const key = row.new_name.trim().toLowerCase();
    if (key) {
      nameCounts.set(key, (nameCounts.get(key) ?? 0) + 1);
    }
  }
  return rows.map((row) => {
    const newName = row.new_name.trim();
    let status: IsoPlanRow["status"] = "ready";
    let note = row.note === "manual edit" ? "" : row.note;
    if (!newName) {
      status = "blocked";
      note = "缺少命名";
    } else if ((nameCounts.get(newName.toLowerCase()) ?? 0) > 1) {
      status = "blocked";
      note = `目標檔名重複：${newName}`;
    } else if (newName === row.source_name) {
      status = "idle";
      note = "檔名已相同";
    } else if (!row.line_no.trim()) {
      status = "warn";
      note = "缺少圖號/檔名，請人工確認";
    } else if (row.note || row.vision_message) {
      status = row.status === "blocked" ? "warn" : row.status;
      note = row.note || row.vision_message;
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

function summarizeIsoRows(rows: IsoPlanRow[]): IsoWorkflowPlan["summary"] {
  return {
    total: rows.length,
    ready: rows.filter((row) => row.status === "ready").length,
    warn: rows.filter((row) => row.status === "warn").length,
    blocked: rows.filter((row) => row.status === "blocked").length,
    selected: rows.filter((row) => row.selected && row.status !== "blocked").length,
  };
}

function formatIsoFilename(pattern: string, serial: string, line: string): string {
  const cleanSerial = serial.trim();
  const cleanLine = basenameWithoutPdf(line);
  if (!cleanSerial || !cleanLine) {
    return "";
  }
  const name = (pattern || "{serial}--{line}.pdf").split("{serial}").join(cleanSerial).split("{line}").join(cleanLine);
  return /\.[^\\/.\s]+$/.test(name) ? name : `${name}.pdf`;
}

function normalizeRegion(region: IsoRegion): IsoRegion {
  const width = clamp(region.width, 0.05, 1);
  const height = clamp(region.height, 0.05, 1);
  const left = clamp(region.left, 0, 1 - width);
  const top = clamp(region.top, 0, 1 - height);
  return { left, top, width, height };
}

function basenameWithoutPdf(value: string): string {
  return value.trim().replace(/\.pdf$/i, "");
}

function targetPathFor(sourcePath: string, newName: string): string {
  if (!newName) {
    return sourcePath;
  }
  const normalized = sourcePath.replace(/\//g, "\\");
  const index = normalized.lastIndexOf("\\");
  return index >= 0 ? `${normalized.slice(0, index + 1)}${newName}` : newName;
}

function parentPath(path: string): string {
  const normalized = path.replace(/\//g, "\\");
  const index = normalized.lastIndexOf("\\");
  return index >= 0 ? normalized.slice(0, index) : "";
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

function StatusTile({ icon, title, value, tone }: { icon: React.ReactNode; title: string; value: string; tone: string }) {
  return (
    <div className={`status-tile ${tone}`}>
      <div className="status-icon">{icon}</div>
      <div>
        <span>{title}</span>
        <strong>{value}</strong>
      </div>
    </div>
  );
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

function compactPath(path: string): string {
  const parts = path.replace(/\//g, "\\").split("\\").filter(Boolean);
  if (parts.length <= 3) {
    return path;
  }
  return `...\\${parts.slice(-3).join("\\")}`;
}
