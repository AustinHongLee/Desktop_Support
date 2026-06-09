import type { IsoWorkflowPlan } from "../isoWorkflow";

export type IsoMachineState =
  | "waiting"
  | "input_ready"
  | "draft_generating"
  | "draft_ready"
  | "warn"
  | "blocked"
  | "manual_review"
  | "ready_to_apply"
  | "applying"
  | "applied"
  | "failed"
  | "replaying"
  | "tuning";

export interface IsoMachineInput {
  applyBusy: boolean;
  batchBusy: boolean;
  batchRunning: boolean;
  busy: boolean;
  exportBusy: boolean;
  hasFailure: boolean;
  hasSource: boolean;
  isoView: "workbench" | "autopilot" | "engineer";
  oneClickStage: "idle" | "running" | "applying" | "review" | "done";
  plan: IsoWorkflowPlan | null;
  replaying: boolean;
  runLogBusy: boolean;
  selectedCount: number;
  blockedCount: number;
  warnCount: number;
}

export interface IsoMachineGuard {
  state: IsoMachineState;
  canApply: boolean;
  canCancelBatch: boolean;
  canGenerateDraft: boolean;
  canOpenDryRun: boolean;
  canReplay: boolean;
  canStartBatch: boolean;
  canTuneRoi: boolean;
  applyBlockReason: string;
}

export function getIsoMachine(input: IsoMachineInput): IsoMachineGuard {
  const hasDraft = Boolean(input.plan);
  const hasApplyIssues = input.blockedCount > 0 || input.warnCount > 0;
  const inBusyDraft =
    input.busy ||
    input.batchBusy ||
    input.batchRunning ||
    input.oneClickStage === "running";
  const isApplying = input.applyBusy || input.oneClickStage === "applying";

  const state = getState(input, {
    hasApplyIssues,
    hasDraft,
    inBusyDraft,
    isApplying,
  });
  const canApply =
    (state === "ready_to_apply" || state === "manual_review") &&
    input.selectedCount > 0 &&
    !hasApplyIssues &&
    !input.busy &&
    !input.applyBusy &&
    !input.batchBusy &&
    !input.batchRunning;

  return {
    state,
    canApply,
    canCancelBatch: input.batchRunning && !isApplying,
    canGenerateDraft: input.hasSource && !inBusyDraft && !isApplying,
    canOpenDryRun: canApply,
    canReplay: !inBusyDraft && !isApplying && !input.runLogBusy,
    canStartBatch: input.hasSource && !inBusyDraft && !isApplying,
    canTuneRoi: input.isoView === "engineer" && !isApplying,
    applyBlockReason: getApplyBlockReason(input, { hasDraft, inBusyDraft, isApplying }),
  };
}

function getState(
  input: IsoMachineInput,
  flags: {
    hasApplyIssues: boolean;
    hasDraft: boolean;
    inBusyDraft: boolean;
    isApplying: boolean;
  },
): IsoMachineState {
  if (flags.isApplying) return "applying";
  if (input.replaying || input.runLogBusy) return "replaying";
  if (flags.inBusyDraft) return "draft_generating";
  if (input.oneClickStage === "done") return "applied";
  if (input.hasFailure) return "failed";
  if (!input.hasSource) return "waiting";
  if (!flags.hasDraft) return "input_ready";
  if (input.blockedCount > 0) return "blocked";
  if (input.warnCount > 0) return "warn";
  if (input.isoView === "engineer") return "tuning";
  if (input.oneClickStage === "review") return "manual_review";
  if (input.selectedCount > 0) return "ready_to_apply";
  return "draft_ready";
}

function getApplyBlockReason(
  input: IsoMachineInput,
  flags: {
    hasDraft: boolean;
    inBusyDraft: boolean;
    isApplying: boolean;
  },
) {
  if (flags.isApplying) return "正在套用更名，完成前不能取消或再次套用。";
  if (flags.inBusyDraft) return "命名草稿仍在產生或批次判讀中，完成後才能套用。";
  if (!flags.hasDraft) return "尚未產生命名草稿，請先選來源並產生草稿。";
  if (input.blockedCount > 0) return `還有 ${input.blockedCount} 筆 blocked，修正前不能套用。`;
  if (input.warnCount > 0) return `還有 ${input.warnCount} 筆 warn，請逐列確認後再套用。`;
  if (input.selectedCount < 1) return "沒有勾選任何 ready 可更名列。";
  return "";
}
