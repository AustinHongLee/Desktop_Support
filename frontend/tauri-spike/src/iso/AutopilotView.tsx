import { ChevronRight, CircleCheck, TerminalSquare } from "lucide-react";
import { Fragment, type ReactNode, type Ref } from "react";
import type { IsoPlanRow } from "../isoWorkflow";
import { FailureCard, type IsoFailureInfo } from "./components/FailureCard";
import { ChecklistGate } from "./components/IsoControls";

export interface PipelineStage {
  key: string;
  label: string;
  icon: ReactNode;
  state: string;
  detail: string;
  seconds: number | null;
}

export interface OneClickButtonModel {
  icon: ReactNode;
  label: string;
  hint: string;
}

export interface EchoLine {
  code?: string;
  tone?: string;
  title?: string;
  detail?: string;
}

export function AutopilotView({
  blockedCount,
  copyFailureForEngineer,
  debugBundleBusy,
  echoLines,
  elapsedSec,
  exportFailureBundle,
  failureCopied,
  isoFailure,
  issueRows,
  oneClickApplying,
  oneClickBusy,
  oneClickButton,
  oneClickRunning,
  oneClickStage,
  openFailureWorkbench,
  openWorkbenchRow,
  pipelineStages,
  readyCount,
  runOneClick,
  selectedRowId,
  terminalRef,
  warnCount,
}: {
  blockedCount: number;
  copyFailureForEngineer: () => void;
  debugBundleBusy: boolean;
  echoLines: EchoLine[];
  elapsedSec: number;
  exportFailureBundle: () => void;
  failureCopied: boolean;
  isoFailure: IsoFailureInfo | null;
  issueRows: IsoPlanRow[];
  oneClickApplying: boolean;
  oneClickBusy: boolean;
  oneClickButton: OneClickButtonModel;
  oneClickRunning: boolean;
  oneClickStage: "idle" | "running" | "applying" | "review" | "done";
  openFailureWorkbench: () => void;
  openWorkbenchRow: (rowId: string) => void;
  pipelineStages: PipelineStage[];
  readyCount: number;
  runOneClick: () => void;
  selectedRowId?: string;
  terminalRef: Ref<HTMLDivElement>;
  warnCount: number;
}) {
  return (
    <div className="iso-autopilot-grid one-click-grid">
      <main className="iso-autopilot-main">
        <div className="one-click-head">
          <div className="eyebrow">一鍵命名</div>
          <h2>選資料夾,其餘交給它</h2>
          <p>自動拆頁、判讀流水號、對 ISO List、命名、更名。全綠就一路到底;只有出現低自信值才會停下來請你確認。</p>
        </div>

        <div className="pipeline">
          {pipelineStages.map((stage, index) => (
            <Fragment key={stage.key}>
              <div className={`pipeline-card ${stage.state}`}>
                <div className="pipeline-card-top">
                  {stage.icon}
                  {stage.seconds != null ? <em>{stage.seconds}s</em> : stage.state === "done" ? <CircleCheck size={14} /> : null}
                </div>
                <strong>{stage.label}</strong>
                <span>{stage.detail}</span>
              </div>
              {index < pipelineStages.length - 1 ? <ChevronRight className="pipeline-arrow" size={18} /> : null}
            </Fragment>
          ))}
        </div>

        {oneClickStage === "review" ? (
          <div className="one-click-checklist">
            <ChecklistGate label="流水號判讀" detail={warnCount ? `${readyCount} 已確認 · ${warnCount} 待確認` : `${readyCount} 已確認`} state={warnCount ? "warn" : "ready"}>
              {warnCount ? (
                <div className="checklist-problem-rows">
                  {issueRows.filter((row) => row.status === "warn").map((row) => (
                    <button className={`checklist-problem-row ${selectedRowId === row.id ? "selected" : ""}`} key={row.id} onClick={() => openWorkbenchRow(row.id)}>
                      <span className="mono">{String(row.page).padStart(3, "0")}</span>
                      <span className="checklist-problem-detail">{row.note || row.vision_message || "需確認"}</span>
                      <ChevronRight size={14} />
                    </button>
                  ))}
                </div>
              ) : null}
            </ChecklistGate>
            {blockedCount ? <ChecklistGate label="命名衝突" detail={`${blockedCount} 個無法更名,請到工作台處理`} state="danger" /> : null}
          </div>
        ) : null}

        {isoFailure ? (
          <FailureCard
            copied={failureCopied}
            exportBusy={debugBundleBusy}
            failure={isoFailure}
            onCopy={copyFailureForEngineer}
            onExport={exportFailureBundle}
            onOpenWorkbench={openFailureWorkbench}
          />
        ) : null}

        <button className="one-click-button" onClick={runOneClick} disabled={oneClickBusy}>
          {oneClickButton.icon}
          <span>{oneClickButton.label}</span>
        </button>
        <div className="one-click-hint">{oneClickButton.hint}</div>

        <div className="one-click-terminal">
          <div className="terminal-head">
            <TerminalSquare size={14} />
            <span>流程紀錄</span>
            <em>{oneClickRunning || oneClickApplying ? `${elapsedSec}s` : oneClickStage === "done" ? "done" : "idle"}</em>
          </div>
          <div className="terminal-body" ref={terminalRef}>
            {echoLines.length ? echoLines.map((line, index) => (
              <div className={`terminal-line ${line.tone || ""}`} key={`${line.code}-${index}`}>
                <span className="terminal-code">{line.code || "LOG"}</span>
                <span>{line.title}{line.detail ? ` · ${line.detail}` : ""}</span>
              </div>
            )) : <div className="terminal-line idle"><span className="terminal-code">SYS</span><span>等待一鍵命名啟動…</span></div>}
            {oneClickRunning || oneClickApplying ? <div className="terminal-cursor">_</div> : null}
          </div>
        </div>
      </main>
    </div>
  );
}
