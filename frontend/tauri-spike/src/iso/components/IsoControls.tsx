import { AlertTriangle, CircleAlert, CircleCheck, FolderOpen, GitBranch, ScanLine, WandSparkles } from "lucide-react";
import type { ReactNode } from "react";
import { compactPath } from "../helpers";

export function PathPickerRow({ icon, label, onPick, value }: { icon: ReactNode; label: string; onPick: () => void; value: string }) {
  return (
    <div className="path-picker-row">
      <div className="path-picker-icon">{icon}</div>
      <div>
        <span>{label}</span>
        <strong title={value}>{value ? compactPath(value) : "未選擇"}</strong>
      </div>
      <button className="dock-icon-button" onClick={onPick} title={label}>
        <FolderOpen size={15} />
      </button>
    </div>
  );
}

export function TopSourceButton({ icon, label, onPick, value }: { icon: ReactNode; label: string; onPick: () => void; value: string }) {
  return (
    <button className={`top-source-button ${value ? "ready" : "idle"}`} onClick={onPick} title={value || label}>
      {icon}
      <span>{label}</span>
      <strong>{value ? compactPath(value) : "未選擇"}</strong>
    </button>
  );
}

export function IsoMetric({ icon, label, value, tone = "neutral" }: { icon: ReactNode; label: string; value: number; tone?: string }) {
  return (
    <div className={`iso-metric ${tone}`}>
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function ChecklistGate({ label, detail, state, children }: { label: string; detail: string; state: string; children?: ReactNode }) {
  return (
    <div className={`checklist-gate ${state}`}>
      <div className="checklist-gate-head">
        {state === "ready" ? <CircleCheck size={18} /> : state === "warn" ? <CircleAlert size={18} /> : state === "danger" ? <AlertTriangle size={18} /> : <ScanLine size={18} />}
        <span className="checklist-gate-label">{label}</span>
        <span className="checklist-gate-detail">{detail}</span>
      </div>
      {children}
    </div>
  );
}

export function IsoEmptyPlan({ busy, chooseWorkFolder, generatePlan }: { busy: boolean; chooseWorkFolder: () => void; generatePlan: () => void }) {
  return (
    <div className="iso-empty-plan">
      <GitBranch size={30} />
      <strong>等待命名草稿</strong>
      <span>選工作資料夾可自動找 PDF 與 ISO 清單；也可手動指定來源。</span>
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
