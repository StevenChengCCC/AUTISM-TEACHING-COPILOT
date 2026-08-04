import type { LessonPackage, TeachingStep } from "./types";

export interface ClassroomRunSheetStep {
  id: string;
  title: string;
  duration: string;
  teacherScript: string | null;
  teacherAction: string;
  expectedLearnerResponse: string;
  waitTime: string;
  promptAction: string;
  reinforcementAction: string;
  errorCorrectionAction: string;
  dataToRecord: string[];
  transitionCue: string;
  breakOption: string | null;
}

export interface ClassroomRunSheet {
  learnerCode: string;
  goal: string;
  totalDuration: string;
  communicationModes: string[];
  successCriterion: string;
  beforeClassChecklist: string[];
  materialsNeeded: string[];
  materialsSource: "teacher_edit" | "included_materials";
  steps: ClassroomRunSheetStep[];
  dataReminder: string[];
  closeout: string[];
  teacherJudgmentNote: string;
}

const genericPrepNoise = new Set([
  "check margins",
  "check print margins",
  "review wording",
  "review at actual size",
  "review at actual size before printing",
]);

const clean = (value: unknown): string =>
  String(value ?? "")
    .trim()
    .replace(/\s+/g, " ");

const key = (value: unknown): string =>
  clean(value).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

const dedupe = (values: unknown[]): string[] => {
  const seen = new Set<string>();
  return values.map(clean).filter((value) => {
    const normalized = key(value);
    if (!value || !normalized || seen.has(normalized)) return false;
    seen.add(normalized);
    return true;
  });
};

const safeCode = (value: string): string =>
  value.trim().replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "Learner";

const successCriterion = (lessonPackage: LessonPackage): string => {
  const packageValue = clean(lessonPackage.successCriterion);
  if (packageValue && !packageValue.toLowerCase().includes("teacher-defined criterion required")) {
    return packageValue;
  }
  const criterion = lessonPackage.lessonSpec?.goal.successCriterion;
  if (criterion?.requiredSuccessfulOpportunities && criterion.totalOpportunities) {
    const maximum = criterion.maximumPromptLevel
      ? ` at or below ${criterion.maximumPromptLevel}`
      : "";
    return `${criterion.requiredSuccessfulOpportunities} successful opportunities out of ${criterion.totalOpportunities}${maximum}`;
  }
  return "Use the current teacher-approved criterion and record the observed result.";
};

const mapStep = (step: TeachingStep): ClassroomRunSheetStep => ({
  id: step.id,
  title: clean(step.title),
  duration: clean(step.duration),
  teacherScript: clean(step.teacherScript) || null,
  teacherAction: clean(step.teacherAction),
  expectedLearnerResponse: clean(step.expectedLearnerResponse) || clean(step.learnerAction),
  waitTime: clean(step.waitTime),
  promptAction: clean(step.promptAction),
  reinforcementAction: clean(step.reinforcementAction),
  errorCorrectionAction: clean(step.errorCorrectionAction),
  dataToRecord: dedupe(step.dataToRecord ?? []),
  transitionCue: clean(step.transitionCue),
  breakOption: clean(step.breakOption) || null,
});

export function buildClassroomRunSheet(
  lessonPackage: LessonPackage,
  learnerCode: string,
): ClassroomRunSheet {
  const documentContent = lessonPackage.documentContent ?? {};
  const editedMaterials = documentContent.materialsNeeded;
  let materialsNeeded: string[];
  let materialsSource: ClassroomRunSheet["materialsSource"];
  if (typeof editedMaterials === "string" && editedMaterials.trim()) {
    materialsNeeded = [editedMaterials.trim()];
    materialsSource = "teacher_edit";
  } else if (Array.isArray(editedMaterials) && dedupe(editedMaterials).length) {
    materialsNeeded = dedupe(editedMaterials);
    materialsSource = "teacher_edit";
  } else {
    materialsNeeded = dedupe(lessonPackage.materials.map((item) => item.title));
    materialsSource = "included_materials";
  }

  const preparation = dedupe([
    ...(lessonPackage.preparationChecklist ?? []),
    ...lessonPackage.materials.flatMap(
      (item) => item.specification?.printPreparation ?? [],
    ),
  ]).filter((item) => !genericPrepNoise.has(key(item)));

  const spec = lessonPackage.lessonSpec;
  const editedData = documentContent.dataCollectionPlan;
  const dataReminder =
    typeof editedData === "string" && editedData.trim()
      ? [editedData.trim()]
      : spec
        ? dedupe([
            spec.dataPlan.measures.length
              ? `Record: ${spec.dataPlan.measures.join("; ")}`
              : "",
            spec.dataPlan.trialDefinition
              ? `Count a trial when: ${spec.dataPlan.trialDefinition}`
              : "",
            spec.dataPlan.independenceDefinition
              ? `Independent means: ${spec.dataPlan.independenceDefinition}`
              : "",
            spec.dataPlan.promptLevels.length
              ? `Prompt levels: ${spec.dataPlan.promptLevels.join(", ")}`
              : "",
          ])
        : dedupe([
            lessonPackage.observableResponse ?? "",
            lessonPackage.successCriterion ?? "",
          ]);

  const hasBreak = Boolean(
    spec?.transitionPlan.breakRequest ||
      spec?.transitionPlan.returnSupport ||
      lessonPackage.teachingFlow.some((step) => step.breakOption),
  );
  const hasPromptData = Boolean(
    spec?.dataPlan.promptLevels.length ||
      lessonPackage.teachingFlow.some((step) => step.dataToRecord?.length),
  );
  const closeout = [
    "Record each trial outcome and mark invalid opportunities so they are excluded from numeric results.",
    ...(hasBreak
      ? ["Record break request, break delivery, and return when applicable."]
      : []),
    ...(hasPromptData
      ? ["Record the prompt level used for each valid opportunity."]
      : []),
    "Preserve observations in the teacher's own words; do not replace them with generated conclusions.",
    "Open Sessions and complete the existing session outcome flow before closing the lesson.",
  ];

  return {
    learnerCode: safeCode(learnerCode),
    goal: clean(documentContent.goal) || clean(lessonPackage.goal),
    totalDuration: clean(lessonPackage.duration),
    communicationModes: dedupe(
      spec?.communicationPlan.acceptedModes.length
        ? spec.communicationPlan.acceptedModes
        : spec?.goal.acceptedResponseModes.length
          ? spec.goal.acceptedResponseModes
          : String(lessonPackage.responseModality ?? "").split(/[,;\n]/),
    ),
    successCriterion: successCriterion(lessonPackage),
    beforeClassChecklist: preparation,
    materialsNeeded,
    materialsSource,
    steps: lessonPackage.teachingFlow.map(mapStep),
    dataReminder,
    closeout,
    teacherJudgmentNote:
      "Teacher judgment overrides this guide. Pause, adapt, or stop when the learner's communication, regulation, access, or safety needs require it.",
  };
}
