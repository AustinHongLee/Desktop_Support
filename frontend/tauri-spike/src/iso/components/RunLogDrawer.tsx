import { AlertTriangle, CircleAlert, FileJson, FileSearch, GitBranch, Minimize2, RefreshCcw } from "lucide-react";
import { StatusTile } from "../../components/StatusTile";
import type { IsoRunLogDetail, IsoRunLogSummary } from "../../isoWorkflow";
import {
  eventLabel,
  failedStageLabel,
  formatRunTime,
  localizeIsoDisplayText,
  pilotHint,
  pilotLabel,
  pilotStatusLabel,
  pilotSummaryText,
  runActionLabel,
  runStatusLabel,
  runSummaryText,
  shortRunId,
} from "../helpers";

export function RunLogDrawer({
  busy,
  detail,
  onClose,
  onRefresh,
  onReplay,
  onSelect,
  runs,
}: {
  busy: boolean;
  detail: IsoRunLogDetail | null;
  onClose: () => void;
  onRefresh: () => void;
  onReplay: (runId: string) => void;
  onSelect: (runId: string) => void;
  runs: IsoRunLogSummary[];
}) {
  const selectedRunId = detail?.run.run_id ?? "";
  const pilotItems = detail?.run.pilot_results ?? [];
  const blockedPilot = pilotItems.filter((item) => item.status === "blocked").length;
  const warnPilot = pilotItems.filter((item) => item.status === "warn").length;
  return (
    <div className="run-log-drawer" role="dialog" aria-modal="true" aria-label="ISO 處理紀錄">
      <div className="run-log-shell">
        <div className="run-log-head">
          <div>
            <div className="eyebrow">ISO 執行紀錄</div>
            <h2>最近處理紀錄</h2>
          </div>
          <div className="run-log-actions">
            <button className="dock-icon-button" onClick={onRefresh} disabled={busy} title="重新整理">
              <RefreshCcw size={15} />
            </button>
            <button className="dock-icon-button" onClick={onClose} title="關閉">
              <Minimize2 size={15} />
            </button>
          </div>
        </div>

        <div className="run-log-grid">
          <aside className="run-log-list">
            {runs.length ? runs.map((run) => (
              <button className={`run-log-item ${run.status} ${run.run_id === selectedRunId ? "selected" : ""}`} key={run.run_id} onClick={() => onSelect(run.run_id)} title={run.run_id}>
                <span>{runStatusLabel(run.status)}</span>
                <strong>{runActionLabel(run.action)}</strong>
                <small>{runSummaryText(run)} · {formatRunTime(run.updated_at || run.created_at)}</small>
                <em>{shortRunId(run.run_id)}</em>
              </button>
            )) : (
              <div className="run-log-empty">
                <FileSearch size={22} />
                <span>{busy ? "讀取中" : "尚無 ISO 處理紀錄"}</span>
              </div>
            )}
          </aside>

          <main className="run-log-detail">
            {detail ? (
              <>
                <div className="run-log-summary">
                  <StatusTile icon={<GitBranch size={18} />} title="本次流程" value={`${runActionLabel(detail.run.action)} · ${runStatusLabel(detail.run.status)}`} tone={detail.run.status === "failed" ? "danger" : detail.run.status === "completed" ? "ready" : "warn"} />
                  <StatusTile icon={<CircleAlert size={18} />} title="檢查結果" value={pilotSummaryText(blockedPilot, warnPilot)} tone={blockedPilot ? "danger" : warnPilot ? "warn" : "ready"} />
                  <StatusTile icon={<FileJson size={18} />} title="過程紀錄" value={`${detail.events.length} 筆`} tone={detail.events.length ? "ready" : "warn"} />
                </div>

                {detail.run.failure ? (
                  <div className="run-log-failure">
                    <AlertTriangle size={18} />
                    <div>
                      <strong>{failedStageLabel(detail.run.failure.failed_stage || "failed")}</strong>
                      <span>{localizeIsoDisplayText(detail.run.failure.user_summary || detail.run.failure.error_message || "")}</span>
                    </div>
                  </div>
                ) : null}

                <div className="pilot-mini-list">
                  {(pilotItems.length ? pilotItems : []).map((item) => (
                    <div className={`pilot-mini-item ${item.status}`} key={item.id} title={`${item.id} ${localizeIsoDisplayText(item.stage)}: ${localizeIsoDisplayText(item.engineer_detail)}`}>
                      <strong>{pilotLabel(item.id, item.stage)}</strong>
                      <span>{pilotHint(item)}</span>
                      <em>{pilotStatusLabel(item.status)}</em>
                    </div>
                  ))}
                </div>

                <div className="run-event-list">
                  {detail.events.slice(-18).reverse().map((event, index) => (
                    <div className={`event-log-item ${event.tone || "ready"}`} key={`${event.code || "event"}-${index}`}>
                      <strong>{eventLabel(event.code || "EVENT")}</strong>
                      <span>{localizeIsoDisplayText(event.title || formatRunTime(event.ts || ""))}</span>
                      <small>{localizeIsoDisplayText(event.detail || "")}</small>
                    </div>
                  ))}
                </div>

                <div className="run-log-footer">
                  <button className="launch-button" onClick={() => onReplay(detail.run.run_id)} disabled={busy}>
                    <RefreshCcw size={18} />
                    <span>{busy ? "回放中" : "回放試算"}</span>
                  </button>
                  <small title={detail.run.run_id}>流程 ID: {shortRunId(detail.run.run_id)}</small>
                </div>
              </>
            ) : (
              <div className="run-log-empty large">
                <FileSearch size={28} />
                <span>{busy ? "讀取中" : "選擇一筆流程紀錄"}</span>
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
