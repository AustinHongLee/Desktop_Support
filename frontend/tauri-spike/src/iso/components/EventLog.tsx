import type { IsoWorkflowIssue } from "../../isoWorkflow";

export function IsoEventLog({ issues }: { issues: IsoWorkflowIssue[] }) {
  const items = issues.slice(-8).reverse();
  return (
    <div className="iso-event-log">
      <div className="eyebrow">流程紀錄</div>
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
