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
import { currentMonitor, getCurrentWindow, LogicalPosition, LogicalSize } from "@tauri-apps/api/window";
import { useEffect, useMemo, useState } from "react";
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
    eyebrow: "Tauri ISO autopilot",
    title: "ISO PDF 拆頁命名",
    line: "source → split → detect → rename plan",
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
  { mode: "iso" as AppMode, title: "ISO PDF 拆頁命名", status: "Concept", detail: "Autopilot flow · rename plan · ROI review", tone: "warn" },
  { mode: "shutdown" as AppMode, title: "Shutdown Safety Inspector", status: "Live", detail: "Process tree · lock files · safe-to-kill policy", tone: "ready" },
  { mode: "cleanup" as AppMode, title: "安全清除工作台", status: "Prototype", detail: "Quarantine-first cleanup · restore trail", tone: "ready" },
  { mode: "locks" as AppMode, title: "檔案關係排查", status: "Prototype", detail: "Dependency graph · lock holder · provenance", tone: "warn" },
];

const COMMAND_FEED = [
  { code: "SYS", title: "Tauri shell ready", detail: "React cockpit can host multiple workbenches", tone: "ready" },
  { code: "ISO", title: "Autopilot concept online", detail: "拆頁、判讀、命名、review queue 已有視覺稿", tone: "warn" },
  { code: "PWR", title: "Shutdown backend connected", detail: "Native shell calls Python scanner through Rust command", tone: "ready" },
  { code: "NEXT", title: "Pipeline bridge pending", detail: "下一步把 ISO Python workflow 接到 Tauri command", tone: "idle" },
];

const ISO_STEPS = [
  { label: "來源", state: "ready", meta: "combine.pdf · 24 pages" },
  { label: "拆頁", state: "ready", meta: "24 single-page PDFs" },
  { label: "ISO", state: "ready", meta: "ISO List · 64 rows" },
  { label: "判讀", state: "warn", meta: "3 rows need review" },
  { label: "命名", state: "ready", meta: "21 ready · 3 held" },
  { label: "更名", state: "idle", meta: "dry-run pending" },
];

const ISO_ROWS = [
  { page: "P001", serial: "1037", confidence: "96", status: "Ready", oldName: "combine_p001.pdf", newName: "1037--2-S11-P-20911-003.pdf" },
  { page: "P002", serial: "1038", confidence: "94", status: "Ready", oldName: "combine_p002.pdf", newName: "1038--2-S11-P-20911-004.pdf" },
  { page: "P003", serial: "1040", confidence: "71", status: "Review", oldName: "combine_p003.pdf", newName: "1040--candidate-match.pdf" },
  { page: "P004", serial: "1041", confidence: "88", status: "Ready", oldName: "combine_p004.pdf", newName: "1041--2-S11-P-20911-006.pdf" },
  { page: "P005", serial: "?", confidence: "42", status: "Hold", oldName: "combine_p005.pdf", newName: "needs-manual-confirm.pdf" },
];

const ISO_ISSUES = [
  { code: "W002", title: "ISO List 無此流水號", detail: "P003 · 1040 有視覺結果但 list 無完全匹配", tone: "warn" },
  { code: "W005", title: "OCR / CV 不一致", detail: "P005 · OCR=1037, CV=103", tone: "danger" },
  { code: "I003", title: "自動找到 ISO List", detail: "同層資料夾命中 iso_list_2026.xlsx", tone: "ready" },
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
    void applyWindowSurface(surface, dockCollapsed);
  }, [dockCollapsed, surface]);

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

  if (surface === "dock") {
    return (
      <DockShell
        busy={busy}
        collapsed={dockCollapsed}
        guardState={guardState}
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
            <div className={`source-pill ${mode === "command" ? "tauri" : "sample"}`}>
              {mode === "command" ? "Tauri shell" : "Concept preview"}
            </div>
          )}
          <button className="icon-button" onClick={collapseToDock} title="Collapse to desktop dock">
            <Minimize2 size={16} />
            <span>Dock</span>
          </button>
        </div>
      </header>

      {error ? <div className="error-line">{error}</div> : null}

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
    </main>
  );
}

function DockShell({
  busy,
  collapsed,
  guardState,
  openCockpit,
  refresh,
  report,
  setCollapsed,
  source,
}: {
  busy: boolean;
  collapsed: boolean;
  guardState: "safe" | "caution" | "danger";
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
      <main className={`dock-shell collapsed ${guardState}`}>
        <button
          className="dock-tail"
          onClick={() => setCollapsed(false)}
          onMouseDown={(event) => {
            if (event.altKey) {
              void startWindowDrag();
            }
          }}
          title="展開桌面輔助工具列"
        >
          <span className="dock-tail-dot" />
          <span>工具</span>
          <strong>{blockerCount ? blockerCount : "OK"}</strong>
        </button>
      </main>
    );
  }

  return (
    <main className={`dock-shell expanded ${guardState}`} onMouseLeave={() => setCollapsed(true)}>
      <section className="dock-panel">
        <header
          className="dock-head"
          onMouseDown={(event) => {
            if (event.altKey) {
              void startWindowDrag();
            }
          }}
        >
          <div className="dock-drag-handle" title="Alt + drag">
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
  return (
    <section className="feature-board cleanup-board">
      <div className="feature-hero">
        <div>
          <div className="eyebrow">Quarantine-first cleanup</div>
          <h2>安全清除工作台</h2>
          <p>先評估風險，再移入隔離區；每個動作都保留 rollback 路徑與證據。</p>
        </div>
        <button className="launch-button">
          <Trash2 size={18} />
          <span>開始掃描</span>
        </button>
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
  return (
    <section className="feature-board lock-board">
      <div className="feature-hero">
        <div>
          <div className="eyebrow">Relationship graph</div>
          <h2>檔案關係與鎖定雷達</h2>
          <p>用 producer / reader / temp / output 關係看懂誰咬著檔案，誰會被連帶影響。</p>
        </div>
        <button className="launch-button">
          <FileSearch size={18} />
          <span>掃描檔案關係</span>
        </button>
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
  return (
    <section className="iso-board">
      <div className="iso-hero">
        <div className="iso-copy">
          <div className="eyebrow">Autopilot sequence</div>
          <h2>ISO PDF 拆頁命名</h2>
          <p>24 頁待處理 · 21 筆可直接更名 · 3 筆需要人工確認</p>
        </div>
        <div className="iso-command">
          <button className="launch-button">
            <WandSparkles size={18} />
            <span>開始一鍵命名</span>
          </button>
          <button className="icon-button">
            <PanelRightOpen size={16} />
            <span>工程師模式</span>
          </button>
        </div>
      </div>

      <div className="iso-flow" aria-label="ISO workflow steps">
        {ISO_STEPS.map((step, index) => (
          <div className={`iso-step ${step.state}`} key={step.label}>
            <div className="step-index">{String(index + 1).padStart(2, "0")}</div>
            <div>
              <strong>{step.label}</strong>
              <span>{step.meta}</span>
            </div>
            {index < ISO_STEPS.length - 1 ? <ChevronRight size={16} /> : null}
          </div>
        ))}
      </div>

      <div className="iso-grid">
        <aside className="iso-side">
          <StatusTile icon={<FileText size={18} />} title="合併 PDF" value="PIPING_ISO_2026.pdf" tone="ready" />
          <StatusTile icon={<Layers3 size={18} />} title="拆頁輸出" value=".runtime/temp/iso_pages" tone="ready" />
          <StatusTile icon={<Table2 size={18} />} title="ISO List" value="iso_list_2026.xlsx · Sheet ISO" tone="ready" />
          <StatusTile icon={<SearchCheck size={18} />} title="判讀 ROI" value="右下角圖框 · profile matched" tone="warn" />

          <div className="iso-side-card">
            <h3>Quality gates</h3>
            <Gate label="PDF 可讀" state="ready" />
            <Gate label="ISO 欄位已套用" state="ready" />
            <Gate label="命名衝突檢查" state="warn" />
            <Gate label="檔案鎖定檢查" state="idle" />
          </div>
        </aside>

        <section className="iso-main">
          <div className="iso-main-header">
            <div>
              <div className="eyebrow">Rename plan</div>
              <h2>命名草稿雷達</h2>
            </div>
            <div className="iso-score">
              <span>Match</span>
              <strong>87%</strong>
            </div>
          </div>

          <div className="iso-table">
            <div className="iso-table-head">
              <span>Page</span>
              <span>Serial</span>
              <span>Confidence</span>
              <span>Status</span>
              <span>New filename</span>
            </div>
            {ISO_ROWS.map((row) => (
              <div className={`iso-table-row ${row.status.toLowerCase()}`} key={row.page}>
                <span>{row.page}</span>
                <strong>{row.serial}</strong>
                <span className="confidence-bar" style={{ "--confidence": `${row.confidence}%` } as React.CSSProperties}>
                  {row.confidence}%
                </span>
                <span className={`plan-state ${row.status.toLowerCase()}`}>{row.status}</span>
                <code>{row.newName}</code>
              </div>
            ))}
          </div>
        </section>

        <aside className="iso-preview">
          <div className="preview-sheet">
            <div className="sheet-grid" />
            <div className="sheet-titleblock">
              <Crosshair size={34} />
              <span>ROI</span>
            </div>
            <div className="sheet-tag">P005</div>
          </div>

          <div className="issue-stack">
            <h3>Review queue</h3>
            {ISO_ISSUES.map((issue) => (
              <div className={`issue-card ${issue.tone}`} key={issue.code}>
                {issue.tone === "ready" ? <CircleCheck size={16} /> : issue.tone === "warn" ? <CircleAlert size={16} /> : <AlertTriangle size={16} />}
                <div>
                  <strong>{issue.code} · {issue.title}</strong>
                  <span>{issue.detail}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="iso-actions">
            <button className="action-button">
              <ClipboardCheck size={15} />
              <span>開啟更名確認</span>
            </button>
            <button className="action-button">
              <FolderOpen size={15} />
              <span>開啟輸出資料夾</span>
            </button>
          </div>
        </aside>
      </div>
    </section>
  );
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

async function applyWindowSurface(surface: SurfaceMode, dockCollapsed: boolean): Promise<void> {
  if (!isTauri()) {
    return;
  }

  const appWindow = getCurrentWindow();
  try {
    if (surface === "dock") {
      const width = dockCollapsed ? 28 : 392;
      const height = dockCollapsed ? 168 : 438;
      await appWindow.setSizeConstraints(null);
      await appWindow.setResizable(false);
      await appWindow.setDecorations(false);
      await appWindow.setAlwaysOnBottom(false);
      await appWindow.setAlwaysOnTop(true);
      await appWindow.setSkipTaskbar(true);
      await appWindow.setShadow(!dockCollapsed).catch(() => undefined);
      await appWindow.setSize(new LogicalSize(width, height));
      await moveWindowToRightEdge(width, height);
      await appWindow.show();
      return;
    }

    await appWindow.setSkipTaskbar(false);
    await appWindow.setAlwaysOnTop(false);
    await appWindow.setResizable(true);
    await appWindow.setDecorations(true);
    await appWindow.setSizeConstraints({ minWidth: 960, minHeight: 620 });
    await appWindow.setSize(new LogicalSize(1180, 760));
    await appWindow.center();
    await appWindow.setFocus();
  } catch (caught) {
    console.warn("Could not apply Tauri window surface", caught);
  }
}

async function moveWindowToRightEdge(width: number, height: number): Promise<void> {
  const monitor = await currentMonitor();
  if (!monitor) {
    return;
  }

  const scale = monitor.scaleFactor || 1;
  const workX = monitor.workArea.position.x / scale;
  const workY = monitor.workArea.position.y / scale;
  const workWidth = monitor.workArea.size.width / scale;
  const workHeight = monitor.workArea.size.height / scale;
  const x = Math.round(workX + workWidth - width - 4);
  const y = Math.round(workY + Math.max(0, workHeight - height) * 0.42);
  await getCurrentWindow().setPosition(new LogicalPosition(x, y));
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
