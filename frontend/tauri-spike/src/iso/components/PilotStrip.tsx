import { AlertTriangle, ChevronRight, Circle, CircleAlert, CircleCheck, ScanLine } from "lucide-react";
import type { ReactNode } from "react";
import type { IsoPilotItem } from "../../isoWorkflow";
import {
  pilotFreshnessLabel,
  pilotLabel,
  pilotNextStep,
  pilotStatusLabel,
  pilotTone,
  type IsoPilotTone,
} from "../helpers";

function toneIcon(tone: IsoPilotTone): ReactNode {
  if (tone === "ready") return <CircleCheck size={14} />;
  if (tone === "warn") return <CircleAlert size={14} />;
  if (tone === "danger") return <AlertTriangle size={14} />;
  if (tone === "run") return <ScanLine size={14} />;
  return <Circle size={14} />;
}

/**
 * Compact Pilot summary / progress strip.
 *
 * Reads the live `plan.pilot_results` (already attached by the backend on every
 * plan / batch job result). Click a node — or the "下一步" button — to jump to the
 * matching view / row via `onJump`. Used by Workbench (and a slimmed Autopilot).
 */
export function PilotStrip({
  items,
  onJump,
  title = "流程檢查",
}: {
  items: IsoPilotItem[];
  onJump?: (item: IsoPilotItem) => void;
  title?: string;
}) {
  if (!items.length) {
    return null;
  }
  const next = pilotNextStep(items);
  const blocked = items.filter((item) => item.status === "blocked").length;
  const warn = items.filter((item) => item.status === "warn").length;
  const stale = items.filter((item) => item.freshness === "stale").length;

  return (
    <div className="pilot-strip">
      <div className="pilot-strip-head">
        <span className="pilot-strip-title">{title}</span>
        <span className="pilot-strip-counts">
          {blocked ? `${blocked} 需處理` : warn ? `${warn} 待確認` : stale ? `${stale} 已過期` : "全部通過"}
        </span>
      </div>

      <div className="pilot-strip-track" role="list">
        {items.map((item) => {
          const tone = pilotTone(item);
          const badge = pilotFreshnessLabel(item);
          return (
            <button
              type="button"
              role="listitem"
              key={item.id}
              className={`pilot-node ${tone}`}
              title={`${item.id} ${item.stage} · ${pilotStatusLabel(item.status)}${item.user_text ? ` · ${item.user_text}` : ""}`}
              onClick={() => onJump?.(item)}
            >
              {toneIcon(tone)}
              <strong>{pilotLabel(item.id, item.stage)}</strong>
              {badge ? <em className="pilot-node-badge">{badge}</em> : null}
            </button>
          );
        })}
      </div>

      {next ? (
        <button type="button" className="pilot-next-step" onClick={() => onJump?.(next.item)}>
          <span className="pilot-next-label">下一步</span>
          <span className="pilot-next-text">{next.text}</span>
          <span className="pilot-next-cta">
            {next.action.label}
            <ChevronRight size={14} />
          </span>
        </button>
      ) : null}
    </div>
  );
}
