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
import { BridgeStatus } from "./components/BridgeStatus";
import { Gate } from "./components/Gate";
import { StatusTile } from "./components/StatusTile";
import { useLegacyBridge } from "./hooks/useLegacyBridge";
import { IsoBoard } from "./iso/IsoBoard";
import { compactPath } from "./iso/helpers";
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
          <IsoBoard />
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
