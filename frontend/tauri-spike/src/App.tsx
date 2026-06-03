import {
  AlertTriangle,
  Activity,
  Braces,
  Cpu,
  Clock3,
  Crosshair,
  FileJson,
  FolderOpen,
  GitBranch,
  Gauge,
  Network,
  PlayCircle,
  Power,
  Radio,
  RefreshCcw,
  Route,
  ScanLine,
  Server,
  ShieldAlert,
  ShieldCheck,
  TerminalSquare,
} from "lucide-react";
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

export default function App() {
  const [report, setReport] = useState<ShutdownSafetyReport | null>(null);
  const [source, setSource] = useState<"tauri" | "sample">("sample");
  const [selectedId, setSelectedId] = useState("");
  const [levelFilter, setLevelFilter] = useState<SafeToKill | "All">("All");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    setBusy(true);
    setError("");
    try {
      const result = await loadShutdownReport();
      setReport(result.report);
      setSource(result.source);
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
    void refresh();
  }, []);

  const blockers = useMemo(() => {
    const items = report?.blockers ?? [];
    const filtered = levelFilter === "All" ? items : items.filter((blocker) => blocker.safe_to_kill === levelFilter);
    return sortBlockers(filtered);
  }, [levelFilter, report]);

  const selected = blockers.find((blocker) => blocker.id === selectedId) ?? blockers[0] ?? null;
  const riskScore = getRiskScore(report);
  const guardState = getGuardState(report);

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">
            <Power size={20} />
          </div>
          <div className="brand-block">
            <div className="eyebrow">Tauri shutdown cockpit</div>
            <h1>Shutdown Safety Inspector</h1>
            <div className="report-line">{report?.scan_reason ?? "scan"} · {report?.created_at ?? "waiting for report"}</div>
          </div>
        </div>
        <div className="toolbar">
          <button className="icon-button" onClick={refresh} disabled={busy} title="Refresh report">
            <RefreshCcw size={17} />
            <span>{busy ? "Refreshing" : "Refresh"}</span>
          </button>
          <div className={`source-pill ${source}`}>{source === "tauri" ? "Live Python report" : "Browser sample"}</div>
        </div>
      </header>

      {error ? <div className="error-line">{error}</div> : null}

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
    </main>
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

function sortBlockers(items: ShutdownBlocker[]): ShutdownBlocker[] {
  return [...items].sort((left, right) => {
    const levelDelta = (LEVEL_RANK.get(left.safe_to_kill) ?? 99) - (LEVEL_RANK.get(right.safe_to_kill) ?? 99);
    return levelDelta || left.process_role.localeCompare(right.process_role) || left.pid - right.pid;
  });
}
