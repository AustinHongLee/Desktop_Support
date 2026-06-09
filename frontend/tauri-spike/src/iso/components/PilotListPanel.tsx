import { AlertTriangle, Circle, CircleAlert, CircleCheck, PanelRightOpen, ScanLine, WandSparkles } from "lucide-react";
import type { ReactNode } from "react";
import type { IsoPilotItem } from "../../isoWorkflow";
import {
  localizeIsoDisplayText,
  pilotFreshnessLabel,
  pilotLabel,
  pilotLocation,
  pilotStatusLabel,
  pilotTone,
  type IsoPilotTone,
} from "../helpers";

function toneIcon(tone: IsoPilotTone): ReactNode {
  if (tone === "ready") return <CircleCheck size={15} />;
  if (tone === "warn") return <CircleAlert size={15} />;
  if (tone === "danger") return <AlertTriangle size={15} />;
  if (tone === "run") return <ScanLine size={15} />;
  return <Circle size={15} />;
}

function renderMetrics(metrics: Record<string, unknown>): string {
  const entries = Object.entries(metrics ?? {});
  if (!entries.length) {
    return "";
  }
  return entries
    .map(([key, value]) => `${localizeIsoDisplayText(key)}=${localizeIsoDisplayText(typeof value === "object" ? JSON.stringify(value) : String(value))}`)
    .join(" · ");
}

/**
 * Full check list for the Engineer / 調校 view.
 *
 * Each item is collapsible (engineer_detail + metrics inside). `auto_fix` and the
 * derived jump location become action buttons. `showEngineerDetail` lets the
 * caller hide the diagnostic text outside developer mode.
 */
export function PilotListPanel({
  items,
  onJump,
  onAutoFix,
  showEngineerDetail = true,
}: {
  items: IsoPilotItem[];
  onJump?: (item: IsoPilotItem) => void;
  onAutoFix?: (item: IsoPilotItem) => void;
  showEngineerDetail?: boolean;
}) {
  return (
    <div className="pilot-list-panel">
      <div className="panel-heading compact">
        <div>
          <span>檢查清單</span>
          <small>{items.length ? `${items.length} 項檢查` : "尚無檢查資料"}</small>
        </div>
      </div>

      {items.length ? (
        <div className="pilot-list">
          {items.map((item) => {
            const tone = pilotTone(item);
            const badge = pilotFreshnessLabel(item);
            const location = pilotLocation(item);
            const metricsText = renderMetrics(item.metrics);
            return (
              <details className={`pilot-list-item ${tone}`} key={item.id}>
                <summary>
                  <span className="pilot-list-icon">{toneIcon(tone)}</span>
                  <strong>{pilotLabel(item.id, item.stage)}</strong>
                  <span className="pilot-list-user">{localizeIsoDisplayText(item.user_text)}</span>
                  {badge ? <em className="pilot-node-badge">{badge}</em> : null}
                  <span className={`pilot-list-status ${tone}`}>{pilotStatusLabel(item.status)}</span>
                </summary>
                <div className="pilot-list-body">
                  {showEngineerDetail && item.engineer_detail ? (
                    <code className="pilot-list-detail">{localizeIsoDisplayText(item.engineer_detail)}</code>
                  ) : null}
                  {metricsText ? <span className="pilot-list-metrics">{metricsText}</span> : null}
                  {item.issue_codes.length ? (
                    <span className="pilot-list-codes">代碼：{item.issue_codes.join(", ")}</span>
                  ) : null}
                  <div className="pilot-list-actions">
                    {item.auto_fix && onAutoFix ? (
                      <button type="button" className="action-button" title={item.auto_fix} onClick={() => onAutoFix(item)}>
                        <WandSparkles size={14} />
                        <span>自動修復</span>
                      </button>
                    ) : null}
                    {onJump ? (
                      <button type="button" className="action-button" onClick={() => onJump(item)}>
                        <PanelRightOpen size={14} />
                        <span>{location.label}</span>
                      </button>
                    ) : null}
                  </div>
                  {item.manual_hint ? <span className="pilot-list-hint">{localizeIsoDisplayText(item.manual_hint)}</span> : null}
                </div>
              </details>
            );
          })}
        </div>
      ) : (
        <div className="pilot-list-empty">產生草稿或執行一次後顯示完整檢查清單。</div>
      )}
    </div>
  );
}
