import type { IsoWorkflowIssue } from "../../isoWorkflow";
import { eventLabel, localizeIsoDisplayText } from "../helpers";

export function IsoEventLog({ issues }: { issues: IsoWorkflowIssue[] }) {
  const items = issues.slice(-8).reverse();
  return (
    <div className="iso-event-log">
      <div className="eyebrow">流程紀錄</div>
      {items.length ? items.map((issue, index) => (
        <div className={`event-log-item ${issue.tone}`} key={`${issue.code}-${index}`}>
          <strong>{eventLabel(issue.code)}</strong>
          <span>{localizeIsoDisplayText(issue.title)}</span>
          <small>{localizeIsoDisplayText(issue.detail)}</small>
        </div>
      )) : <span className="muted">等待流程事件</span>}
    </div>
  );
}
