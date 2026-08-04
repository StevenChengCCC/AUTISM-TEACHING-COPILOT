import type {
  PatchSessionRunDraftInput,
  SessionRunDraft,
  SessionRunDraftTrial,
  SessionTrialOutcome,
  SessionUseSnapshot,
} from "./types";

export type AutosavePhase = "loading" | "idle" | "saving" | "saved" | "failed" | "conflict";
export type RecorderResultPath = "independent" | "prompted" | "not_observed" | "break_honored" | "invalid";

export const resultPathLabels: Record<RecorderResultPath, string> = {
  independent: "Independent",
  prompted: "Prompted",
  not_observed: "Not observed / unsuccessful",
  break_honored: "Break or stop honored",
  invalid: "Invalid opportunity",
};

export function autosaveLabel(phase: AutosavePhase, lastSavedAt?: string): string {
  if (phase === "loading") return "Loading saved observations…";
  if (phase === "saving") return "Saving…";
  if (phase === "conflict") return "Conflict — local input is preserved";
  if (phase === "failed") return "Failed to save — local input is preserved";
  if (phase === "saved" && lastSavedAt) return `Saved ${new Date(lastSavedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  return "Ready to record";
}

export function resultPathForOutcome(outcome: SessionTrialOutcome | null): RecorderResultPath | null {
  if (outcome === "independent_success") return "independent";
  if (outcome === "prompted_success") return "prompted";
  if (outcome === "break_honored") return "break_honored";
  if (outcome === "cancelled") return "invalid";
  if (outcome === "incorrect" || outcome === "no_response" || outcome === "not_observed_unsuccessful") return "not_observed";
  return null;
}

export function applyRecorderResult(
  trial: SessionRunDraftTrial,
  path: RecorderResultPath,
  acceptedModes: string[] = [],
): SessionRunDraftTrial {
  const soleMode = acceptedModes.length === 1 ? acceptedModes[0] : null;
  const common = {
    ...trial,
    valid: true,
    responseMode: null,
    promptLevel: null,
    latencySeconds: null,
    breakRequested: null,
    breakDelivered: null,
    returnedAfterBreak: null,
  };
  if (path === "independent") return {
    ...common,
    outcome: "independent_success",
    responseMode: soleMode as SessionRunDraftTrial["responseMode"],
  };
  if (path === "prompted") return {
    ...common,
    outcome: "prompted_success",
    responseMode: soleMode as SessionRunDraftTrial["responseMode"],
  };
  if (path === "not_observed") return { ...common, outcome: "not_observed_unsuccessful" };
  if (path === "break_honored") return {
    ...common,
    outcome: "break_honored",
    breakDelivered: true,
  };
  return {
    ...common,
    valid: false,
    outcome: "cancelled",
    note: "",
  };
}

export function applyDraftOutcome(
  trial: SessionRunDraftTrial,
  outcome: SessionTrialOutcome | null,
): SessionRunDraftTrial {
  if (outcome === null) return { ...trial, outcome: null, valid: null };
  return applyRecorderResult(
    trial,
    resultPathForOutcome(outcome) ?? "not_observed",
  );
}

export function draftPatch(
  draft: SessionRunDraft,
  idempotencyKey: string,
  status: "in_progress" | "ready_for_closeout" = draft.status === "ready_for_closeout" ? "ready_for_closeout" : "in_progress",
): PatchSessionRunDraftInput {
  return {
    expectedVersion: draft.version,
    idempotencyKey,
    status,
    trials: draft.trials,
    generalization: draft.generalization,
    helpfulMaterialIds: draft.helpfulMaterialIds,
    unhelpfulMaterialIds: draft.unhelpfulMaterialIds,
    observations: draft.observations,
    activeTrialNumber: draft.activeTrialNumber,
  };
}

export function trialRequirementReasons(
  trial: SessionRunDraftTrial,
  acceptedModes: string[],
): string[] {
  const reasons: string[] = [];
  if (!trial.outcome) return ["select an observed result"];
  if (!trial.contextId) reasons.push("choose the practiced context");
  if (trial.outcome === "independent_success" && acceptedModes.length > 1 && !trial.responseMode)
    reasons.push("choose the observed response mode");
  if (trial.outcome === "prompted_success") {
    if (!trial.responseMode) reasons.push("choose the observed response mode");
    if (!trial.promptLevel || trial.promptLevel === "independent") reasons.push("choose the prompt used");
  }
  if (trial.outcome === "break_honored") {
    if (trial.breakRequested === null) reasons.push("confirm whether a break or stop was requested");
    if (trial.breakDelivered !== true) reasons.push("confirm that the break or stop was honored");
    if (trial.returnedAfterBreak === null) reasons.push("record return status");
    if (trial.breakRequested === false && !trial.note.trim()) reasons.push("briefly describe the honored stop");
  }
  if (trial.outcome === "cancelled" && !trial.note.trim()) reasons.push("add a concise validity reason");
  return reasons;
}

export function incompleteTrialDetails(
  draft: SessionRunDraft,
  acceptedModes: string[],
): Array<{ opportunityNumber: number; reasons: string[] }> {
  return draft.trials
    .map((trial) => ({
      opportunityNumber: trial.opportunityNumber,
      reasons: trialRequirementReasons(trial, acceptedModes),
    }))
    .filter((item) => item.reasons.length > 0);
}

export function incompleteOpportunityNumbers(draft: SessionRunDraft): number[] {
  return incompleteTrialDetails(draft, ["speech", "AAC"]).map((item) => item.opportunityNumber);
}

export function rawTrialCounts(draft: SessionRunDraft): { valid: number; invalid: number; recorded: number; remaining: number } {
  const recorded = draft.trials.filter((trial) => trial.outcome !== null).length;
  return {
    valid: draft.trials.filter((trial) => trial.valid === true).length,
    invalid: draft.trials.filter((trial) => trial.valid === false).length,
    recorded,
    remaining: draft.trials.length - recorded,
  };
}

export function codingDefinitions(snapshot: SessionUseSnapshot): string[] {
  return [
    `Independent: ${snapshot.independenceDefinition}`,
    ...snapshot.promptLevelDefinitions.map((value) => `Prompt: ${value}`),
  ];
}

export const materialCooccurrenceNotice =
  "Material selections record what was present during the opportunity. They do not show that a material caused the result.";
