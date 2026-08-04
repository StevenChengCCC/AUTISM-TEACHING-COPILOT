import { mockLearners } from "./data/mockLearners";
import {
  createEmptyChat,
  createQuestionsFromTeacherRequest,
} from "./data/mockLessonDraft";
import { createMockPackage } from "./data/mockLessonPackage";
import { mockMaterials } from "./data/mockMaterials";
import { mockRecentLessons } from "./data/mockRecentLessons";
import { mockRecords } from "./data/mockRecords";
import { mockSessions, mockSessionStats } from "./data/mockSessions";
import type {
  AIChatState,
  AIQuestion,
  CompleteSessionInput,
  ExportJob,
  GeneratedMaterial,
  GoalProgressMetric,
  GoalProgressSeries,
  GoalProgressSeriesOption,
  HandoffExportDownload,
  LearnerProfile,
  LearnerProfileExtraction,
  LearnerProgressSummary,
  LessonDesignDraft,
  LessonPackage,
  LessonPackageUpdateInput,
  LessonSession,
  LessonSessionSummary,
  MaterialLibraryItem,
  MaterialQuickEditAction,
  NextSessionMaterialImpactPlan,
  NextSessionRecommendation,
  ProgressDataPoint,
  ProgressSignal,
  SessionCompletionTemplate,
  SessionOutcome,
  SessionRunState,
  StartSessionInput,
  PatchSessionRunDraftInput,
  ReviewNextSessionRecommendationInput,
  UpdateNextSessionPlanInput,
  TeacherHandoffExportInput,
} from "./types";

const chats = new Map<string, AIChatState>();
const packages = new Map<string, LessonPackage>();
const copy = <T>(value: T): T => structuredClone(value);
const pause = async <T>(value: T): Promise<T> => Promise.resolve(copy(value));
const mockContextKey = (trial: SessionOutcome["trials"][number]): string =>
  [
    trial.contextId,
    trial.contextLabel,
    trial.contextDimension ?? "",
    trial.contextSetting ?? "",
    trial.transitionFrom ?? "",
    trial.transitionTo ?? "",
  ].join("|");
const learners = copy(mockLearners);
const records = copy(mockRecords);
const sessions = copy(mockSessions);
const materials = copy(mockMaterials);
const nextSessionRecommendations = new Map<string, NextSessionRecommendation>();
const nextSessionPlans = new Map<string, NextSessionMaterialImpactPlan>();
const progressData: ProgressDataPoint[] = [];
const exportJobs: ExportJob[] = [];
const sessionOutcomes = new Map<string, SessionOutcome>();
const sessionRuns = new Map<string, SessionRunState>();

function applyQuestionToDraft(chat: AIChatState, question: AIQuestion) {
  const values = question.selectedOptionIds
    .map(
      (id) =>
        question.options.find(
          (item) => item.id === id && item.source === "ai_generated",
        )?.value,
    )
    .filter((value): value is string => Boolean(value));
  const custom = question.customAnswer.trim();
  if (question.field === "responseLevel")
    chat.draft.responseLevel = custom || values[0] || "";
  if (question.field === "scenarios")
    chat.draft.scenarios = [...values, ...(custom ? [custom] : [])];
  if (question.field === "selectedMaterials")
    chat.draft.selectedMaterials = [...values, ...(custom ? [custom] : [])];
  if (question.field === "customNotes") chat.draft.customNotes = custom;
}

function isAnswered(question: AIQuestion) {
  if (!question.required) return true;
  return (
    question.selectedOptionIds.length > 0 ||
    question.customAnswer.trim().length > 0
  );
}

export const lessonKitMockApi = {
  getLearners: () => pause(learners),
  getLearnerById: (id: string) =>
    pause(learners.find((learner) => learner.id === id) ?? null),
  createLearner: async (payload: Omit<LearnerProfile, "id">) => {
    const learner = { ...payload, id: `learner-local-${learners.length + 1}` };
    learners.push(learner);
    return pause(learner);
  },
  updateLearner: async (id: string, payload: Partial<LearnerProfile>) => {
    const index = learners.findIndex((item) => item.id === id);
    if (index < 0) throw new Error("Learner not found");
    learners[index] = { ...learners[index], ...payload };
    return pause(learners[index]);
  },
  getRecordsForLearner: (learnerId: string) =>
    pause(records.filter((record) => record.learnerId === learnerId)),
  addRecordForLearner: async (
    learnerId: string,
    payload: { fileName: string; fileType: string; text: string },
  ) => {
    const record = {
      id: `record-local-${records.length + 1}`,
      learnerId,
      fileName: payload.fileName,
      fileType: payload.fileType,
      status: "ready" as const,
      uploadedAt: "Just now",
      extractedText: payload.text,
    };
    records.push(record);
    return pause(record);
  },
  getExtractedLearnerProfile: async (
    learnerId: string,
  ): Promise<LearnerProfileExtraction> => {
    const learner = learners.find((item) => item.id === learnerId);
    if (!learner) throw new Error("Learner not found");
    const learnerRecords = records.filter(
      (record) => record.learnerId === learnerId,
    );
    return pause({
      learner,
      records: learnerRecords,
      insights: [
        "Use visual supports",
        "Keep activities short",
        "Add multiple examples",
      ],
      analyzedRecordCount: learnerRecords.length,
      status: "complete",
    });
  },
  getInitialLessonChat: async (learnerId: string) => {
    const key = `conversation-${learnerId}`;
    const chat = createEmptyChat(learnerId);
    chats.set(key, chat);
    return pause(chat);
  },
  /** Future backend equivalent: POST /api/v2/lesson-chat returning AIChatState. */
  submitLessonRequest: async (conversationId: string, content: string) => {
    const chat = chats.get(conversationId);
    if (!chat) throw new Error("Conversation not found");
    const cleanContent = content.trim();
    if (!cleanContent) return pause(chat);
    const sequence = chat.messages.length + 1;
    chat.messages.push({
      id: `message-${sequence}`,
      role: "teacher",
      content: cleanContent,
      createdAt: "Just now",
    });
    if (chat.questions.length === 0) {
      const generated = createQuestionsFromTeacherRequest(
        chat.learnerId,
        cleanContent,
      );
      chat.questions = generated.questions;
      chat.draft = generated.draft;
      chat.messages.push({
        id: `message-${sequence + 1}`,
        role: "assistant",
        content:
          "Great. I’ll ask a few quick questions so we can generate the right teaching materials.",
        createdAt: "Just now",
      });
    } else {
      chat.draft.customNotes = [chat.draft.customNotes, cleanContent]
        .filter(Boolean)
        .join(" ");
      chat.messages.push({
        id: `message-${sequence + 1}`,
        role: "assistant",
        content:
          "Thanks. I’ve kept your lesson choices and added that note to the draft.",
        createdAt: "Just now",
      });
    }
    chat.canGenerate =
      chat.questions.length > 0 && chat.questions.every(isAnswered);
    return pause(chat);
  },
  updateAIQuestionAnswer: async (
    conversationId: string,
    questionId: string,
    selectedOptionIds: string[],
    customAnswer = "",
  ) => {
    const chat = chats.get(conversationId);
    if (!chat) throw new Error("Conversation not found");
    const question = chat.questions.find((item) => item.id === questionId);
    if (!question) throw new Error("Question not found");
    const customId = `custom-${question.id}`;
    question.options = question.options.filter(
      (option) => option.id !== customId,
    );
    const baseIds = selectedOptionIds.filter((id) => id !== customId);
    question.selectedOptionIds =
      question.inputType === "single_select"
        ? baseIds.slice(-1)
        : baseIds.slice(0, question.maxSelections);
    question.customAnswer = customAnswer;
    if (customAnswer.trim()) {
      question.options.push({
        id: customId,
        label: customAnswer.trim(),
        value: customAnswer.trim(),
        description: "Added by the teacher",
        icon: "✎",
        recommended: false,
        source: "teacher_custom",
      });
      question.selectedOptionIds =
        question.inputType === "single_select"
          ? [customId]
          : [...question.selectedOptionIds, customId];
    }
    applyQuestionToDraft(chat, question);
    chat.canGenerate = chat.questions.every(isAnswered);
    return pause(chat);
  },
  clearLessonChat: async (conversationId: string) => {
    const chat = chats.get(conversationId);
    if (!chat) throw new Error("Conversation not found");
    chat.messages = [];
    return pause(chat);
  },
  previewPackageContentPlan: async (conversationId: string) => {
    const chat = chats.get(conversationId);
    if (!chat) throw new Error("Conversation not found");
    chat.draft.packageContentPlan = {
      id: `content-plan-${chat.draft.id}`,
      lessonSpecId: `lesson-spec-${chat.draft.id}`,
      lessonSpecRevision: 1,
      schemaVersion: 1,
      teacherSelectedCore: chat.draft.selectedMaterials.map((label, index) => ({
        materialRequestId: `mock-${index}`,
        materialType: label.toLowerCase().replace(/\s+/g, "_"),
        reason: "Teacher selected this core material.",
        decisionIds: [],
        profileFactorIds: [],
      })),
      requiredCompanions: [
        {
          materialType: "teacher_cue_card",
          reasonRequired: "Keeps prompting and return guidance visible.",
          dependsOnMaterialTypes: [],
          goalRequirement: "Teacher implementation fidelity",
          profileFactorIds: [],
          canTeacherRemove: true,
          removalWarning: "Review package completeness before removing.",
          included: true,
        },
      ],
      optionalEnrichments: [
        {
          materialType: "summary_template",
          reasonSuggested: "Adds a post-lesson summary.",
          profileFactorIds: [],
          defaultIncluded: true,
          estimatedPages: 2,
        },
      ],
      excludedMaterials: [],
      estimatedArtifactCount: chat.draft.selectedMaterials.length + 2,
      estimatedPageCount: chat.draft.selectedMaterials.length + 3,
      unresolvedDependencies: [],
    };
    chat.draft.version = (chat.draft.version ?? 1) + 1;
    return pause(chat);
  },
  adjustPackageContentPlan: async (
    conversationId: string,
    payload: {
      action: "set_optional" | "set_companion" | "add_material";
      materialType: string;
      included: boolean;
      expectedDraftVersion: number;
    },
  ) => {
    const chat = chats.get(conversationId);
    const plan = chat?.draft.packageContentPlan;
    if (!chat || !plan) throw new Error("Package preview not found");
    if (payload.action === "set_optional") {
      const item = plan.optionalEnrichments.find(
        (value) => value.materialType === payload.materialType,
      );
      if (item) item.defaultIncluded = payload.included;
    }
    if (payload.action === "set_companion") {
      const item = plan.requiredCompanions.find(
        (value) => value.materialType === payload.materialType,
      );
      if (item) {
        if (!item.canTeacherRemove && !payload.included)
          throw new Error(item.removalWarning ?? "Required material");
        item.included = payload.included;
      }
    }
    if (
      payload.action === "add_material" &&
      !plan.optionalEnrichments.some(
        (value) => value.materialType === payload.materialType,
      )
    )
      plan.optionalEnrichments.push({
        materialType: payload.materialType,
        reasonSuggested: "Teacher added this supported material.",
        profileFactorIds: [],
        defaultIncluded: true,
        estimatedPages: 1,
      });
    const included =
      plan.teacherSelectedCore.length +
      plan.requiredCompanions.filter((value) => value.included).length +
      plan.optionalEnrichments.filter((value) => value.defaultIncluded).length;
    plan.estimatedArtifactCount = included;
    chat.draft.version = (chat.draft.version ?? 1) + 1;
    return pause(chat);
  },
  generateLessonPackageFromDraft: async (draft: LessonDesignDraft) => {
    const lessonPackage = createMockPackage(draft);
    packages.set(lessonPackage.id, lessonPackage);
    return pause(lessonPackage);
  },
  getLessonPackage: async (packageId: string) => {
    const value = packages.get(packageId);
    if (!value) throw new Error("Package not found");
    return pause(value);
  },
  updateLessonPackage: async (
    packageId: string,
    payload: LessonPackageUpdateInput,
  ) => {
    const value = packages.get(packageId);
    if (!value) throw new Error("Package not found");
    const updated = {
      ...value,
      ...payload,
      materials: value.materials,
      safetyReview: value.safetyReview,
      standardsChecks: value.standardsChecks,
    };
    packages.set(packageId, updated);
    return pause(updated);
  },
  approveLessonPackage: async (packageId: string): Promise<LessonPackage> => {
    const value = packages.get(packageId);
    if (!value) throw new Error("Package not found");
    const updated = {
      ...value,
      status: "approved" as const,
      version: (value.version ?? 1) + 1,
    };
    packages.set(packageId, updated);
    return pause(updated);
  },
  getGeneratedMaterials: async (packageId: string) =>
    pause(packages.get(packageId)?.materials ?? []),
  updateGeneratedMaterial: async (
    materialId: string,
    payload: {
      title: string;
      content: GeneratedMaterial["content"];
      printLayout: GeneratedMaterial["printLayout"];
    },
  ) => updateLocalMaterial(materialId, (item) => ({ ...item, ...payload })),
  reviewGeneratedMaterial: async (materialId: string) =>
    updateLocalMaterial(materialId, (item) =>
      item.materialSpec
        ? {
            ...item,
            status: "teacher_review_needed",
            materialSpec: {
              ...item.materialSpec,
              approval: {
                ...item.materialSpec.approval,
                status: "reviewed",
                reviewedRevision: item.materialSpec.revision,
                approvedRevision: null,
              },
            },
          }
        : item,
    ),
  approveGeneratedMaterial: async (materialId: string) =>
    updateLocalMaterial(materialId, (item) => ({
      ...item,
      status: "approved",
    })),
  quickEditGeneratedMaterial: async (
    materialId: string,
    action: MaterialQuickEditAction,
  ) =>
    updateLocalMaterial(materialId, (item) => {
      const content = { ...item.content };
      if (action === "simplify_wording") content.instruction = "Ask for help.";
      if (action === "regenerate_artwork")
        content.artwork = "Updated classroom artwork";
      if (action === "adjust_reward") content.reward = "Choice activity";
      return { ...item, content };
    }),
  reviewMaterialVisual: async (
    materialId: string,
    visualId: string,
    action: "approve" | "reject",
  ) =>
    updateLocalMaterial(materialId, (item) => ({
      ...item,
      visualAssetPlan: item.visualAssetPlan
        ? {
            ...item.visualAssetPlan,
            visualItems: item.visualAssetPlan.visualItems.map((visual) =>
              visual.id === visualId
                ? {
                    ...visual,
                    reviewStatus:
                      action === "approve" ? "approved" : "rejected",
                    status: action === "approve" ? "ready" : "failed",
                  }
                : visual,
            ),
          }
        : item.visualAssetPlan,
    })),
  useMaterialVisualFallback: async (materialId: string, visualId: string) =>
    updateLocalMaterial(materialId, (item) => ({
      ...item,
      visualAssetPlan: item.visualAssetPlan
        ? {
            ...item.visualAssetPlan,
            visualItems: item.visualAssetPlan.visualItems.map((visual) =>
              visual.id === visualId
                ? {
                    ...visual,
                    assetId: visual.fallbackAssetId,
                    status: "ready",
                    reviewStatus: "unreviewed",
                  }
                : visual,
            ),
          }
        : item.visualAssetPlan,
    })),
  exportLessonPackage: async (
    packageId: string,
    format: ExportJob["format"],
  ): Promise<ExportJob> => {
    const job: ExportJob = {
      exportId: `export-${packageId}-${format}`,
      learnerId: "a102",
      packageId,
      status: "completed",
      format,
      progressPercent: 100,
      requestedAt: new Date().toISOString(),
      completedAt: new Date().toISOString(),
      fileName: "teacher-handoff.zip",
      fileSizeBytes: 1024,
      downloadUrl: null,
      message: "Local mock export is ready.",
      manifest: [
        "handoff-summary.pdf",
        "progress-data.csv",
        "handoff-data.json",
        "README.txt",
      ],
      downloadCount: 0,
      version: 1,
    };
    exportJobs.unshift(job);
    return pause(job);
  },
  createHandoffExport: async (
    learnerId: string,
    payload: TeacherHandoffExportInput,
  ): Promise<ExportJob> => {
    const job: ExportJob = {
      exportId: `handoff-local-${exportJobs.length + 1}`,
      learnerId,
      packageId: payload.packageIds[0] ?? null,
      status: "completed",
      format: "zip",
      progressPercent: 100,
      requestedAt: new Date().toISOString(),
      completedAt: new Date().toISOString(),
      fileName: "teacher-handoff.zip",
      fileSizeBytes: 1024,
      message: "Local mock handoff is ready.",
      manifest: [
        "handoff-summary.pdf",
        "progress-data.csv",
        "handoff-data.json",
        "README.txt",
      ],
      downloadCount: 0,
      version: 1,
    };
    exportJobs.unshift(job);
    return pause(job);
  },
  getHandoffExports: (learnerId?: string): Promise<ExportJob[]> =>
    pause(
      exportJobs.filter((job) => !learnerId || job.learnerId === learnerId),
    ),
  retryHandoffExport: async (id: string): Promise<ExportJob> => {
    const source = exportJobs.find((job) => job.exportId === id);
    if (!source) throw new Error("Export not found");
    const job = {
      ...source,
      exportId: `handoff-local-${exportJobs.length + 1}`,
      status: "completed" as const,
      requestedAt: new Date().toISOString(),
    };
    exportJobs.unshift(job);
    return pause(job);
  },
  getHandoffExportDownload: async (
    id: string,
  ): Promise<HandoffExportDownload> => {
    const job = exportJobs.find((item) => item.exportId === id);
    if (!job) throw new Error("Export not found");
    return pause({
      exportId: id,
      downloadUrl:
        "data:text/plain;charset=utf-8,Local%20mock%20teacher%20handoff",
      expiresAt: new Date(Date.now() + 300000).toISOString(),
    });
  },
  deleteHandoffExport: async (id: string): Promise<ExportJob> => {
    const job = exportJobs.find((item) => item.exportId === id);
    if (!job) throw new Error("Export not found");
    job.status = "deleted";
    return pause(job);
  },
  getSessions: () => pause(sessions),
  getSessionStats: () =>
    pause(
      mockSessionStats.map((stat) => ({
        ...stat,
        count: sessions.filter((item) => item.status === stat.status).length,
      })),
    ),
  createSession: async (payload: Omit<LessonSession, "id" | "updatedAt">) => {
    const session = {
      ...payload,
      id: `session-local-${sessions.length + 1}`,
      updatedAt: "Just now",
    };
    sessions.push(session);
    return pause(session);
  },
  duplicateSession: async (id: string) => {
    const source = sessions.find((item) => item.id === id);
    if (!source) throw new Error("Session not found");
    const duplicate = {
      ...source,
      id: `session-local-${sessions.length + 1}`,
      status: "draft" as const,
      updatedAt: "Just now",
    };
    sessions.push(duplicate);
    return pause(duplicate);
  },
  startSession: async (id: string, payload: StartSessionInput): Promise<SessionRunState> => {
    const existing = sessionRuns.get(id);
    if (existing) return pause(existing);
    const session = sessions.find((item) => item.id === id);
    if (!session?.lessonPackageId) throw new Error("Session is not linked to a lesson package");
    const contexts = [
      { id: "sorting-table", label: "Sorting at the table", setting: "classroom" },
      { id: "cleanup", label: "Sorting during cleanup", setting: "classroom" },
    ].filter((item) => payload.contextIds.includes(item.id));
    const startedAt = new Date().toISOString();
    const run: SessionRunState = {
      snapshot: {
        id: `use-${id}`, sessionId: id, learnerId: session.learnerId,
        goalId: session.goalId ?? `goal-${id}`, goalRevision: session.goalRevision ?? 1,
        goalComparisonKey: `mock-${id}`,
        operationalizedGoal: session.operationalizedGoal || session.goal,
        lessonSpecId: session.lessonSpecId ?? `spec-${id}`, lessonSpecRevision: session.goalRevision ?? 1,
        packageId: session.lessonPackageId, packageRevision: session.lessonPackageRevision ?? 1,
        materialRevisions: { "sort-cards": 1, "data-sheet": 1 },
        materialLabels: { "sort-cards": "Sorting Cards", "data-sheet": "Goal Data Sheet" },
        visualPlanRevisions: [], pdfArtifact: null,
        teacherConfirmedContexts: contexts,
        acceptedResponseModes: [], promptLevelDefinitions: [], independenceDefinition: "",
        dataMeasures: ["Outcome", "Prompt level", "Response mode", "Latency"],
        plannedOpportunities: 5, startedAt, startedByTeacher: payload.startedByTeacher,
        idempotencyKey: payload.idempotencyKey,
      },
      draft: {
        id: `run-draft-${id}`, sessionId: id, snapshotId: `use-${id}`,
        status: "in_progress",
        trials: Array.from({ length: 5 }, (_, index) => ({
          trialId: `${id}-trial-${index + 1}`, opportunityNumber: index + 1,
          contextId: null, contextLabel: null, valid: null, outcome: null,
          responseMode: null, promptLevel: null, latencySeconds: null,
          breakRequested: null, breakDelivered: null, returnedAfterBreak: null,
          materialIdsUsed: [], note: "",
        })),
        generalization: { status: null, people: [], settings: [], materials: [] },
        helpfulMaterialIds: [], unhelpfulMaterialIds: [],
        observations: { engagementLevel: null, regulationLevel: null, teacherNotes: "", rawCountsConfirmed: false },
        activeTrialNumber: 1, lastSavedAt: startedAt, version: 1,
      },
      packageChanged: false, packageChangeWarning: null,
    };
    session.status = "in_progress"; session.startedAt = startedAt;
    session.sessionUseSnapshotId = run.snapshot.id; session.draftStatus = "in_progress"; session.draftVersion = 1;
    sessionRuns.set(id, run);
    return pause(run);
  },
  getSessionRun: async (id: string): Promise<SessionRunState> => {
    const run = sessionRuns.get(id);
    if (!run) throw new Error("This session has not been started");
    return pause(run);
  },
  patchSessionRunDraft: async (id: string, payload: PatchSessionRunDraftInput): Promise<SessionRunState> => {
    const run = sessionRuns.get(id);
    if (!run) throw new Error("This session has not been started");
    if (run.draft.version !== payload.expectedVersion) throw new Error("Draft version conflict");
    run.draft = {
      ...run.draft,
      ...(payload.status ? { status: payload.status } : {}),
      ...(payload.trials ? { trials: payload.trials } : {}),
      ...(payload.generalization ? { generalization: payload.generalization } : {}),
      ...(payload.helpfulMaterialIds ? { helpfulMaterialIds: payload.helpfulMaterialIds } : {}),
      ...(payload.unhelpfulMaterialIds ? { unhelpfulMaterialIds: payload.unhelpfulMaterialIds } : {}),
      ...(payload.observations ? { observations: payload.observations } : {}),
      ...(payload.activeTrialNumber ? { activeTrialNumber: payload.activeTrialNumber } : {}),
      lastSavedAt: new Date().toISOString(), version: run.draft.version + 1,
    };
    return pause(run);
  },
  completeSessionRunDraft: async (
    id: string,
    payload: { expectedVersion: number; idempotencyKey: string },
  ): Promise<SessionOutcome> => {
    const run = sessionRuns.get(id);
    if (!run || run.draft.version !== payload.expectedVersion) throw new Error("Draft version conflict");
    if (run.draft.generalization.status === null)
      throw new Error("Choose a generalization status before completion");
    const trials = run.draft.trials.map((item) => {
      if (item.contextId === null || item.valid === null || item.outcome === null)
        throw new Error(`Opportunity ${item.opportunityNumber} is incomplete`);
      return {
        ...item, contextId: item.contextId, contextLabel: item.contextLabel ?? item.contextId,
        valid: item.valid, outcome: item.outcome, responseMode: item.responseMode ?? "none",
        promptLevel: item.promptLevel, breakRequested: Boolean(item.breakRequested),
        breakDelivered: Boolean(item.breakDelivered),
      };
    });
    const outcome = await lessonKitMockApi.completeSession(id, {
      expectedLessonPackageId: run.snapshot.packageId,
      expectedLessonSpecId: run.snapshot.lessonSpecId,
      expectedGoalId: run.snapshot.goalId,
      startedAt: run.snapshot.startedAt, completedAt: new Date().toISOString(), trials,
      generalization: {
        ...run.draft.generalization,
        status: run.draft.generalization.status,
      },
      helpfulMaterialIds: run.draft.helpfulMaterialIds,
      unhelpfulMaterialIds: run.draft.unhelpfulMaterialIds,
      observations: run.draft.observations,
    });
    run.draft.status = "completed"; run.draft.version += 1;
    return outcome;
  },
  getSessionSummary: async (id: string): Promise<LessonSessionSummary> => {
    const session = sessions.find((item) => item.id === id);
    if (!session) throw new Error("Session not found");
    return pause({
      ...session,
      overview:
        "Progress includes independence, prompting, participation, engagement, and regulation.",
      highlights: ["Small wins matter."],
      nextSteps: ["Continue gradual prompt fading."],
    });
  },
  getSessionCompletionTemplate: async (
    id: string,
  ): Promise<SessionCompletionTemplate> => {
    const session = sessions.find((item) => item.id === id);
    if (!session?.lessonPackageId || !session.lessonSpecId || !session.goalId)
      throw new Error("Session is not linked to a lesson package");
    return pause({
      sessionId: id,
      learnerId: session.learnerId,
      lessonPackageId: session.lessonPackageId,
      lessonPackageRevision: session.lessonPackageRevision ?? 1,
      lessonSpecId: session.lessonSpecId,
      goalId: session.goalId,
      goalRevision: session.goalRevision ?? 1,
      operationalizedGoal: session.operationalizedGoal || session.goal,
      plannedOpportunities: 5,
      contexts: [
        {
          id: "sorting-table",
          label: "Sorting at the table",
          setting: "classroom",
        },
        {
          id: "cleanup",
          label: "Sorting during cleanup",
          setting: "classroom",
        },
      ],
      materialIds: ["sort-cards", "data-sheet"],
      materialLabels: {
        "sort-cards": "Sorting Cards",
        "data-sheet": "Goal Data Sheet",
      },
      dataSheetColumns: [
        "Opportunity",
        "Context",
        "Outcome",
        "Prompt level",
        "Response mode",
        "Latency",
      ],
    });
  },
  completeSession: async (
    id: string,
    payload: CompleteSessionInput,
  ): Promise<SessionOutcome> => {
    const template = await lessonKitMockApi.getSessionCompletionTemplate(id);
    const valid = payload.trials.filter((trial) => trial.valid);
    const successful = valid.filter(
      (trial) =>
        trial.outcome === "independent_success" ||
        trial.outcome === "prompted_success",
    );
    const used = [...new Set(valid.flatMap((trial) => trial.materialIdsUsed))];
    const latencies = valid.flatMap((trial) =>
      trial.latencySeconds === null ? [] : [trial.latencySeconds],
    );
    const sorted = [...latencies].sort((a, b) => a - b);
    const middle = Math.floor(sorted.length / 2);
    const median = sorted.length
      ? sorted.length % 2
        ? sorted[middle]
        : (sorted[middle - 1] + sorted[middle]) / 2
      : null;
    const counts = Object.fromEntries(
      ["independent", "gesture", "visual", "model", "brief_verbal", "other"]
        .map((level) => [
          level,
          valid.filter((trial) => trial.promptLevel === level).length,
        ])
        .filter(([, count]) => count),
    );
    const outcome: SessionOutcome = {
      id: `outcome-${id}`,
      sessionId: id,
      learnerId: template.learnerId,
      lessonPackageId: template.lessonPackageId,
      lessonPackageRevision: template.lessonPackageRevision,
      lessonSpecId: template.lessonSpecId,
      goalId: template.goalId,
      goalRevision: template.goalRevision,
      operationalizedGoal: template.operationalizedGoal,
      startedAt: payload.startedAt,
      completedAt: payload.completedAt,
      opportunities: {
        planned: template.plannedOpportunities,
        valid: valid.length,
        cancelled: payload.trials.filter(
          (trial) => trial.outcome === "cancelled",
        ).length,
      },
      responses: {
        independentSuccessful: valid.filter(
          (trial) => trial.outcome === "independent_success",
        ).length,
        promptedSuccessful: valid.filter(
          (trial) => trial.outcome === "prompted_success",
        ).length,
        incorrect: valid.filter((trial) => trial.outcome === "incorrect")
          .length,
        noResponse: valid.filter((trial) => trial.outcome === "no_response")
          .length,
        notObservedOrUnsuccessful: valid.filter(
          (trial) => trial.outcome === "not_observed_unsuccessful",
        ).length,
        speechSuccessful: successful.filter(
          (trial) => trial.responseMode === "speech",
        ).length,
        aacSuccessful: successful.filter(
          (trial) => trial.responseMode === "AAC",
        ).length,
        pointingSuccessful: successful.filter(
          (trial) => trial.responseMode === "pointing",
        ).length,
        otherSuccessful: successful.filter(
          (trial) => trial.responseMode === "other",
        ).length,
        breakOrStopHonored: valid.filter(
          (trial) => trial.outcome === "break_honored",
        ).length,
      },
      prompting: {
        promptLevelCounts: counts,
        averagePromptLevel: null,
        lowestPromptLevel: null,
        highestPromptLevel: null,
      },
      latency: {
        recordedTrialCount: latencies.length,
        averageSeconds: latencies.length
          ? latencies.reduce((a, b) => a + b, 0) / latencies.length
          : null,
        medianSeconds: median,
      },
      generalization: {
        contextsAttempted: [
          ...new Set(valid.map((trial) => trial.contextLabel)),
        ],
        contextsSuccessful: [
          ...new Set(successful.map((trial) => trial.contextLabel)),
        ],
        ...payload.generalization,
      },
      breakAndReturn: {
        breakRequests: valid.filter((trial) => trial.breakRequested).length,
        breaksDelivered: valid.filter((trial) => trial.breakDelivered).length,
        returnedAfterBreak: valid.filter(
          (trial) => trial.returnedAfterBreak === true,
        ).length,
      },
      materials: {
        usedMaterialIds: used,
        unusedMaterialIds: template.materialIds.filter(
          (material) => !used.includes(material),
        ),
        helpfulMaterialIds: payload.helpfulMaterialIds,
        unhelpfulMaterialIds: payload.unhelpfulMaterialIds,
      },
      observations: payload.observations,
      trials: payload.trials,
      createdAt: new Date().toISOString(),
      version: 1,
    };
    sessionOutcomes.set(id, outcome);
    const session = sessions.find((item) => item.id === id);
    if (session) {
      session.status = "completed";
      session.completedAt = payload.completedAt;
      session.updatedAt = "Just now";
    }
    return pause(outcome);
  },
  getSessionOutcome: async (id: string): Promise<SessionOutcome> => {
    const outcome = sessionOutcomes.get(id);
    if (!outcome) throw new Error("Session outcome not found");
    return pause(outcome);
  },
  getGoalProgressSeriesOptions: async (
    learnerId: string,
  ): Promise<GoalProgressSeriesOption[]> => {
    const values = [...sessionOutcomes.values()].filter(
      (item) => item.learnerId === learnerId,
    );
    return pause(
      values
        .map((item) => ({
          goalId: item.goalId,
          goalRevision: item.goalRevision,
          operationalizedGoal: item.operationalizedGoal,
          sessionCount: values.filter(
            (value) =>
              value.goalId === item.goalId &&
              value.goalRevision === item.goalRevision,
          ).length,
          latestCompletedAt: item.completedAt,
        }))
        .filter(
          (item, index, all) =>
            all.findIndex(
              (value) =>
                value.goalId === item.goalId &&
                value.goalRevision === item.goalRevision,
            ) === index,
        ),
    );
  },
  getGoalProgressSeries: async (
    learnerId: string,
    metric: GoalProgressMetric,
    goalId?: string,
    goalRevision?: number,
    contextKey?: string,
  ): Promise<GoalProgressSeries> => {
    const values = [...sessionOutcomes.values()]
      .filter(
        (item) =>
          item.learnerId === learnerId &&
          (!goalId || item.goalId === goalId) &&
          (!goalRevision || item.goalRevision === goalRevision),
      )
      .sort((a, b) => a.completedAt.localeCompare(b.completedAt));
    const reference = values[values.length - 1];
    const contextRecords = values.flatMap((item) =>
      item.trials
        .filter((trial) => trial.valid)
        .map((trial) => ({ item, trial, key: mockContextKey(trial) })),
    );
    const contextSummaries = [
      ...new Set(contextRecords.map((record) => record.key)),
    ]
      .map((key) => {
        const records = contextRecords.filter((record) => record.key === key);
        const trials = records.map((record) => record.trial);
        const first = trials[0];
        const sessionIds = [
          ...new Set(records.map((record) => record.item.sessionId)),
        ];
        const latencies = trials.flatMap((trial) =>
          trial.latencySeconds === null ? [] : [trial.latencySeconds],
        );
        const reasons: string[] = [];
        if (sessionIds.length < 2)
          reasons.push("Fewer than two sessions include this context.");
        if (trials.length < 3)
          reasons.push(
            "Fewer than three valid opportunities were recorded in this context.",
          );
        if (latencies.length / trials.length < 0.5)
          reasons.push(
            `Response latency was recorded for only ${latencies.length} of ${trials.length} opportunities.`,
          );
        const independent = trials.filter(
          (trial) => trial.outcome === "independent_success",
        ).length;
        const promptValues = {
          independent: 0,
          gesture: 1,
          visual: 2,
          model: 3,
          brief_verbal: 4,
          other: 5,
        };
        const observedDates = records
          .map((record) => record.item.completedAt)
          .sort();
        return {
          contextKey: key,
          contextId: first.contextId,
          contextLabel: first.contextLabel,
          contextDimension: first.contextDimension ?? null,
          contextSetting: first.contextSetting ?? "",
          transitionFrom: first.transitionFrom ?? "",
          transitionTo: first.transitionTo ?? "",
          sessionCount: sessionIds.length,
          validOpportunityCount: trials.length,
          independentSuccessfulCount: independent,
          promptedSuccessfulCount: trials.filter(
            (trial) => trial.outcome === "prompted_success",
          ).length,
          independentSuccessRate:
            Math.round((independent / trials.length) * 1000) / 10,
          averagePromptLevel:
            Math.round(
              (trials.reduce(
                (total, trial) => total + promptValues[trial.promptLevel ?? "independent"],
                0,
              ) /
                trials.length) *
                100,
            ) / 100,
          averageLatencySeconds: latencies.length
            ? Math.round(
                (latencies.reduce((a, b) => a + b, 0) / latencies.length) * 100,
              ) / 100
            : null,
          firstObservedAt: observedDates[0],
          lastObservedAt: observedDates[observedDates.length - 1],
          confidence: reasons.length ? ("low" as const) : ("normal" as const),
          confidenceReasons: reasons,
          evidenceSessionIds: sessionIds,
          filterEligible: sessionIds.length >= 2 && trials.length >= 3,
        };
      })
      .sort((a, b) => b.independentSuccessRate - a.independentSuccessRate);
    const pointRecords = values
      .map((item) => ({
        item,
        trials: item.trials.filter(
          (trial) =>
            trial.valid &&
            (!contextKey || mockContextKey(trial) === contextKey),
        ),
      }))
      .filter((record) => record.trials.length > 0);
    const points = pointRecords.map(({ item, trials }) => {
      const valid = trials.length;
      let numerator = trials.filter(
        (trial) => trial.outcome === "independent_success",
      ).length;
      let value = valid ? (numerator / valid) * 100 : 0;
      if (metric === "prompt_independence_display_score") {
        const mapping = {
          independent: 100,
          gesture: 75,
          visual: 75,
          model: 50,
          brief_verbal: 25,
          other: 0,
        };
        const scores = trials.map((trial) => mapping[trial.promptLevel ?? "independent"]);
        numerator = scores.length;
        value = scores.length
          ? scores.reduce((a, b) => a + b, 0) / scores.length
          : 0;
      }
      if (metric === "average_response_latency") {
        const latencies = trials.flatMap((trial) =>
          trial.latencySeconds === null ? [] : [trial.latencySeconds],
        );
        numerator = latencies.length;
        value = latencies.length
          ? latencies.reduce((a, b) => a + b, 0) / latencies.length
          : 0;
      }
      if (metric === "generalization_context_count") {
        numerator = new Set(trials.map(mockContextKey)).size;
        value = numerator;
      }
      if (metric === "return_after_break_rate") {
        numerator = trials.filter(
          (trial) => trial.returnedAfterBreak === true,
        ).length;
        const delivered = trials.filter((trial) => trial.breakDelivered).length;
        value = delivered ? (numerator / delivered) * 100 : 0;
      }
      return {
        sessionId: item.sessionId,
        completedAt: item.completedAt,
        goalId: item.goalId,
        goalRevision: item.goalRevision,
        metric,
        value: Math.round(value * 10) / 10,
        validOpportunityCount: valid,
        numeratorCount: numerator,
        confidence: valid >= 3 ? ("normal" as const) : ("low" as const),
        confidenceReason:
          valid >= 3
            ? null
            : "Fewer than three valid opportunities were recorded.",
        lessonPackageId: item.lessonPackageId,
        lessonPackageRevision: item.lessonPackageRevision,
        contextsAttempted: [
          ...new Set(trials.map((trial) => trial.contextLabel)),
        ],
        annotation: null,
        details: {
          operationalizedGoal: item.operationalizedGoal,
          independentSuccessfulCount: trials.filter(
            (trial) => trial.outcome === "independent_success",
          ).length,
          promptedSuccessfulCount: trials.filter(
            (trial) => trial.outcome === "prompted_success",
          ).length,
          responseModeCounts: {
            speech: trials.filter(
              (trial) =>
                trial.responseMode === "speech" &&
                trial.outcome.endsWith("success"),
            ).length,
            AAC: trials.filter(
              (trial) =>
                trial.responseMode === "AAC" &&
                trial.outcome.endsWith("success"),
            ).length,
            pointing: trials.filter(
              (trial) =>
                trial.responseMode === "pointing" &&
                trial.outcome.endsWith("success"),
            ).length,
            other: trials.filter(
              (trial) =>
                trial.responseMode === "other" &&
                trial.outcome.endsWith("success"),
            ).length,
          },
          promptLevelCounts: item.prompting.promptLevelCounts,
          averagePromptLevel: item.prompting.averagePromptLevel,
          averageLatencySeconds: item.latency.averageSeconds,
          breakRequestCount: item.breakAndReturn.breakRequests,
          breaksDeliveredCount: item.breakAndReturn.breaksDelivered,
          returnedAfterBreakCount: item.breakAndReturn.returnedAfterBreak,
          materialIdsUsed: [
            ...new Set(trials.flatMap((trial) => trial.materialIdsUsed)),
          ],
          teacherNotes: item.observations.teacherNotes,
        },
      };
    });
    const materialRecords = values.flatMap((item) =>
      item.trials
        .filter((trial) => trial.valid)
        .flatMap((trial) =>
          trial.materialIdsUsed.map((materialId) => ({
            item,
            trial,
            materialId,
          })),
        ),
    );
    const materialUsageSummaries = [
      ...new Set(materialRecords.map((record) => record.materialId)),
    ].map((materialId) => {
      const records = materialRecords.filter(
        (record) => record.materialId === materialId,
      );
      const trials = records.map((record) => record.trial);
      const sessionIds = [
        ...new Set(records.map((record) => record.item.sessionId)),
      ];
      const grouped = [...new Set(trials.map((trial) => trial.contextLabel))];
      const independentContexts = grouped.filter((label) =>
        trials.some(
          (trial) =>
            trial.contextLabel === label &&
            trial.outcome === "independent_success",
        ),
      );
      const lessonPackage = packages.get(
        records[records.length - 1].item.lessonPackageId,
      );
      return {
        materialId,
        materialLabel:
          lessonPackage?.materials.find(
            (material) => material.id === materialId,
          )?.title ?? materialId,
        sessionCount: sessionIds.length,
        validOpportunityCount: trials.length,
        independentSuccessfulCount: trials.filter(
          (trial) => trial.outcome === "independent_success",
        ).length,
        promptedSuccessfulCount: trials.filter(
          (trial) => trial.outcome === "prompted_success",
        ).length,
        unsuccessfulOpportunityCount: trials.filter(
          (trial) =>
            trial.outcome === "incorrect" || trial.outcome === "no_response",
        ).length,
        contextsWithIndependentResponses: independentContexts,
        contextsWithoutIndependentResponses: grouped.filter(
          (label) => !independentContexts.includes(label),
        ),
        evidenceSessionIds: sessionIds,
      };
    });
    const trend =
      points.length === 0
        ? "no_data"
        : points.length === 1
          ? "insufficient_data"
          : points.length === 2
            ? "comparison_only"
            : "variable";
    const evidence =
      points.length === 0
        ? ["No completed sessions are available for this goal."]
        : points.length === 1
          ? [
              "One observation is available. More sessions are needed to show a trend.",
            ]
          : points.length === 2
            ? [
                "Two observations are available. This shows a comparison but not a stable trend.",
              ]
            : [
                "Review repeated observations; the local mock does not classify a directional trend.",
              ];
    return pause({
      learnerId,
      goalId: reference?.goalId ?? goalId ?? "",
      goalRevision: reference?.goalRevision ?? goalRevision ?? 1,
      operationalizedGoal: reference?.operationalizedGoal ?? "",
      metric,
      points,
      trend,
      trendEvidence: evidence,
      latestValue: points[points.length - 1]?.value ?? null,
      sessionCount: points.length,
      confidence:
        points.length >= 3 &&
        points.every((point) => point.confidence === "normal")
          ? ("normal" as const)
          : ("low" as const),
      confidenceReasons:
        points.length >= 3 &&
        points.every((point) => point.confidence === "normal")
          ? []
          : [
              "More normal-confidence observations are needed before identifying a stable pattern.",
            ],
      activeContextKey: contextKey ?? null,
      contextSummaries,
      materialUsageSummaries,
    });
  },
  getNextSessionRecommendations: async (
    learnerId: string,
    goalId: string,
    goalRevision: number,
  ): Promise<NextSessionRecommendation[]> =>
    pause(
      [...nextSessionRecommendations.values()].filter(
        (item) =>
          item.learnerId === learnerId &&
          item.goalId === goalId &&
          item.goalRevision === goalRevision,
      ),
    ),
  generateNextSessionRecommendations: async (
    learnerId: string,
    goalId: string,
    goalRevision: number,
  ): Promise<NextSessionRecommendation[]> => {
    const outcomes = [...sessionOutcomes.values()]
      .filter(
        (item) =>
          item.learnerId === learnerId &&
          item.goalId === goalId &&
          item.goalRevision === goalRevision,
      )
      .sort((a, b) => a.completedAt.localeCompare(b.completedAt));
    if (!outcomes.length) return pause([]);
    const evidence = outcomes.map((item) => ({
      sessionId: item.sessionId,
      description: `${item.responses.independentSuccessful} of ${item.opportunities.valid} valid opportunities were independent.`,
      metricPath: "responses.independentSuccessful/opportunities.valid",
      observedValue: item.opportunities.valid
        ? Math.round(
            (item.responses.independentSuccessful / item.opportunities.valid) *
              1000,
          ) / 10
        : 0,
      contextId: null,
      contextLabel: null,
    }));
    const id = `mock-recommendation-${learnerId}-${goalId}-${outcomes.map((item) => item.sessionId).join("-")}`;
    const existing = nextSessionRecommendations.get(id);
    if (existing) return pause([existing]);
    const recommendation: NextSessionRecommendation = {
      id,
      learnerId,
      goalId,
      goalRevision,
      type: outcomes.length < 3 ? "collect_more_data" : "reuse",
      title:
        outcomes.length < 3
          ? "Preserve the current plan while collecting more observations"
          : "Review the current plan using recorded evidence",
      recommendation:
        outcomes.length < 3
          ? "More observations may be useful before changing the current lesson plan."
          : "The teacher may consider keeping the current plan while reviewing the recorded session evidence.",
      evidence,
      confidence: outcomes.length < 3 ? "low" : "medium",
      confidenceReason: `${outcomes.length} completed session(s) are available in the local demonstration.`,
      teacherReviewRequired: true,
      affectedLessonSpecPaths: [],
      affectedMaterialIds: [],
      affectedMaterialTypes: [],
      status: "pending",
      teacherEditedText: null,
      ruleId: "local-review-only-v1",
      evidenceFingerprint: outcomes.map((item) => item.sessionId).join("|"),
      createdAt: new Date().toISOString(),
      reviewedAt: null,
      reviewHistory: [],
      version: 1,
    };
    nextSessionRecommendations.set(id, recommendation);
    return pause([recommendation]);
  },
  reviewNextSessionRecommendation: async (
    recommendationId: string,
    payload: ReviewNextSessionRecommendationInput,
  ): Promise<NextSessionRecommendation> => {
    const current = nextSessionRecommendations.get(recommendationId);
    if (!current) throw new Error("Next-session recommendation not found");
    if (current.version !== payload.expectedVersion)
      throw new Error(
        "The recommendation changed. Refresh before reviewing it.",
      );
    const reviewedAt = new Date().toISOString();
    const updated: NextSessionRecommendation = {
      ...current,
      status: payload.action,
      teacherEditedText:
        payload.action === "edited" ? (payload.teacherEditedText ?? "") : null,
      reviewedAt,
      reviewHistory: [
        ...current.reviewHistory,
        {
          actorType: "teacher",
          action: payload.action,
          teacherText:
            payload.action === "edited"
              ? (payload.teacherEditedText ?? "")
              : null,
          reviewedAt,
        },
      ],
      version: current.version + 1,
    };
    nextSessionRecommendations.set(recommendationId, updated);
    return pause(updated);
  },
  createNextSessionPlan: async (
    packageId: string,
    expectedPackageRevision: number,
  ): Promise<NextSessionMaterialImpactPlan> => {
    const lessonPackage = packages.get(packageId);
    if (!lessonPackage?.lessonSpec)
      throw new Error("A typed prior lesson package is required.");
    if ((lessonPackage.version ?? 1) !== expectedPackageRevision)
      throw new Error("The prior package changed. Refresh before planning.");
    const id = `mock-next-session-plan-${packageId}-${expectedPackageRevision}`;
    const existing = nextSessionPlans.get(id);
    if (existing) return pause(existing);
    const accepted = [...nextSessionRecommendations.values()].filter(
      (item) =>
        item.learnerId === lessonPackage.learnerId &&
        ["accepted", "edited"].includes(item.status),
    );
    const proposed = {
      ...copy(lessonPackage.lessonSpec),
      id: `${lessonPackage.lessonSpec.id}-next`,
      revision: lessonPackage.lessonSpec.revision + 1,
      teacherEdits: [
        ...lessonPackage.lessonSpec.teacherEdits,
        ...accepted.map((item) => item.teacherEditedText ?? item.recommendation),
      ],
    };
    const checks = [
      "goal",
      "response_modes",
      "reinforcement",
      "contexts",
      "access",
      "profile_revision",
      "visual_constraints",
      "approval",
      "semantic_content",
    ].map((dimension) => ({
      dimension: dimension as NextSessionMaterialImpactPlan["reusableMaterials"][number]["compatibilityChecks"][number]["dimension"],
      passed: true,
      detail: `${dimension.replace(/_/g, " ")} remains compatible in the local preview.`,
    }));
    const plan: NextSessionMaterialImpactPlan = {
      id,
      learnerId: lessonPackage.learnerId,
      previousPackageId: packageId,
      previousPackageRevision: expectedPackageRevision,
      proposedLessonSpecId: proposed.id,
      proposedLessonSpecRevision: {
        id: `${id}-lesson-spec`,
        previousLessonSpecId: lessonPackage.lessonSpec.id,
        previousLessonSpecRevision: lessonPackage.lessonSpec.revision,
        lessonSpec: proposed,
        acceptedRecommendationIds: accepted.map((item) => item.id),
        teacherEditedRecommendationContent: Object.fromEntries(
          accepted
            .filter((item) => item.status === "edited")
            .map((item) => [item.id, item.teacherEditedText ?? ""]),
        ),
        changedFields: accepted.length ? ["/teacherEdits"] : [],
        unchangedFields: ["/goal", "/communicationPlan", "/accessPlan"],
        proposedGoalId: accepted[0]?.goalId ?? lessonPackage.lessonSpec.id,
        proposedGoalRevision: proposed.revision,
        goalSeriesBoundary: "continue",
        profileRevision: proposed.profileRevision,
        fieldProvenance: accepted.map((item) => ({
          fieldPath: "/teacherEdits",
          recommendationId: item.id,
          recommendationStatus: item.status as "accepted" | "edited",
          sourceContent: item.teacherEditedText ?? item.recommendation,
          appliedValue: item.teacherEditedText ?? item.recommendation,
          changed: true,
        })),
      },
      reusableMaterials: lessonPackage.materials.map((item) => ({
        materialId: item.id,
        materialRevision: item.materialSpec?.revision ?? item.version ?? 1,
        materialType: item.type,
        title: item.title,
        reasonReusable: "The semantic and approval boundary is unchanged in this local preview.",
        recommendationIds: [],
        compatibilityChecks: checks,
      })),
      materialsToRevise: [],
      newMaterialsRequired: [],
      materialsToRemove: [],
      blockingIssues: [],
      overrides: [],
      status: "proposed",
      createdPackageId: null,
      createdAt: new Date().toISOString(),
      version: 1,
    };
    nextSessionPlans.set(id, plan);
    return pause(plan);
  },
  getNextSessionPlan: async (planId: string) => {
    const plan = nextSessionPlans.get(planId);
    if (!plan) throw new Error("Next-session impact plan not found");
    return pause(plan);
  },
  updateNextSessionPlan: async (
    planId: string,
    payload: UpdateNextSessionPlanInput,
  ): Promise<NextSessionMaterialImpactPlan> => {
    const plan = nextSessionPlans.get(planId);
    if (!plan) throw new Error("Next-session impact plan not found");
    if (plan.version !== payload.expectedVersion)
      throw new Error("The impact preview changed. Refresh before editing it.");
    let reusable = [...plan.reusableMaterials];
    let revise = [...plan.materialsToRevise];
    let additions = [...plan.newMaterialsRequired];
    if (payload.action === "force_regenerate") {
      const source = reusable.find((item) => item.materialId === payload.materialId);
      if (!source) throw new Error("Select a reusable material.");
      reusable = reusable.filter((item) => item.materialId !== source.materialId);
      revise.push({
        materialId: source.materialId,
        materialRevision: source.materialRevision,
        materialType: source.materialType,
        title: source.title,
        affectedFields: [],
        reason: `Teacher requested regeneration: ${payload.reason}`,
        recommendationIds: source.recommendationIds,
        compatibilityChecks: source.compatibilityChecks,
        safeToKeepExisting: true,
      });
    } else if (payload.action === "keep_existing") {
      const source = revise.find((item) => item.materialId === payload.materialId);
      if (!source?.safeToKeepExisting)
        throw new Error("This material cannot be kept across the semantic boundary.");
      revise = revise.filter((item) => item.materialId !== source.materialId);
      reusable.push({
        materialId: source.materialId,
        materialRevision: source.materialRevision,
        materialType: source.materialType,
        title: source.title,
        reasonReusable: `Teacher kept this compatible revision: ${payload.reason}`,
        recommendationIds: source.recommendationIds,
        compatibilityChecks: source.compatibilityChecks,
      });
    } else {
      additions = additions.filter((item) => item.materialType !== payload.materialType);
    }
    const updated: NextSessionMaterialImpactPlan = {
      ...plan,
      reusableMaterials: reusable,
      materialsToRevise: revise,
      newMaterialsRequired: additions,
      overrides: [
        ...plan.overrides,
        {
          action: payload.action,
          materialId: payload.materialId ?? null,
          materialType: payload.materialType ?? null,
          reason: payload.reason,
          createdAt: new Date().toISOString(),
          actorType: "teacher",
        },
      ],
      version: plan.version + 1,
    };
    nextSessionPlans.set(planId, updated);
    return pause(updated);
  },
  createNextSessionPackage: async (
    planId: string,
    expectedPlanVersion: number,
  ): Promise<LessonPackage> => {
    const plan = nextSessionPlans.get(planId);
    if (!plan) throw new Error("Next-session impact plan not found");
    if (plan.version !== expectedPlanVersion)
      throw new Error("The impact preview changed. Refresh before creating the kit.");
    if (plan.createdPackageId) {
      const existing = packages.get(plan.createdPackageId);
      if (existing) return pause(existing);
    }
    const source = packages.get(plan.previousPackageId);
    if (!source) throw new Error("Prior lesson package not found");
    const id = `${source.id}-next`;
    const reviseIds = new Set(plan.materialsToRevise.map((item) => item.materialId));
    const materials = source.materials.map((item) => ({
      ...copy(item),
      id: `${item.id}-next`,
      packageId: id,
      status: reviseIds.has(item.id) ? ("teacher_review_needed" as const) : item.status,
      version: 1,
    }));
    const created: LessonPackage = {
      ...copy(source),
      id,
      draftId: `next-${source.draftId}`,
      materials,
      lessonSpec: plan.proposedLessonSpecRevision.lessonSpec,
      status: "teacher_review_needed",
      version: 1,
      documentContent: {
        ...source.documentContent,
        previousPackageId: source.id,
        nextSessionImpactPlanId: plan.id,
      },
    };
    packages.set(id, created);
    nextSessionPlans.set(planId, {
      ...plan,
      status: "package_created",
      createdPackageId: id,
      version: plan.version + 1,
    });
    return pause(created);
  },
  regenerateNextSessionMaterial: async (
    packageId: string,
    materialId: string,
    expectedMaterialVersion: number,
  ) => {
    const lessonPackage = packages.get(packageId);
    const material = lessonPackage?.materials.find((item) => item.id === materialId);
    if (!material || (material.version ?? 1) !== expectedMaterialVersion)
      throw new Error("The selected material changed. Refresh before regenerating it.");
    return updateLocalMaterial(materialId, (item) => ({
      ...item,
      status: "teacher_review_needed",
      version: (item.version ?? 1) + 1,
      materialSpec: item.materialSpec
        ? {
            ...item.materialSpec,
            revision: item.materialSpec.revision + 1,
            approval: {
              status: "not_reviewed",
              reviewedRevision: null,
              approvedRevision: null,
            },
          }
        : item.materialSpec,
    }));
  },
  regenerateNextSessionScenario: async (
    packageId: string,
    materialId: string,
    _scenarioId: string,
    _teacherInstruction: string,
    expectedMaterialVersion: number,
  ) => lessonKitMockApi.regenerateNextSessionMaterial(
    packageId,
    materialId,
    expectedMaterialVersion,
  ),
  getRecentLessonsForLearner: (learnerId: string) =>
    pause(mockRecentLessons.filter((lesson) => lesson.learnerId === learnerId)),
  getMaterials: () => pause(materials),
  createMaterial: async (payload: {
    title: string;
    type: string;
    thumbnailLabel: string;
    reusable?: boolean;
  }) => {
    const item: MaterialLibraryItem = {
      ...payload,
      id: `material-local-${materials.length + 1}`,
      source: "template",
      reusable: payload.reusable ?? true,
      createdAt: "Just now",
    };
    materials.push(item);
    return pause(item);
  },
  duplicateMaterial: async (id: string) => {
    const source = materials.find((item) => item.id === id);
    if (!source) throw new Error("Material not found");
    const item = {
      ...source,
      id: `material-local-${materials.length + 1}`,
      title: `${source.title} Copy`,
      createdAt: "Just now",
    };
    materials.push(item);
    return pause(item);
  },
  getProgressSummaryForLearner: (
    learnerId: string,
  ): Promise<LearnerProgressSummary> =>
    pause({
      learnerId,
      currentGoal: "Asking for Help",
      accuracyPercent: 58,
      independencePercent: 42,
      sessionsPracticed: 4,
      currentPromptLevel: "Level 2",
      trend: "Slow, uneven growth",
      message: "Plateau does not mean no progress.",
    }),
  getProgressSignalsForLearner: (): Promise<ProgressSignal[]> =>
    pause([
      {
        id: "engagement",
        type: "engagement",
        label: "Engagement",
        description: "Participation is growing.",
        status: "improving",
      },
      {
        id: "prompt",
        type: "prompt_fading",
        label: "Prompt Fading",
        description: "Moving toward lighter prompts.",
        status: "emerging",
      },
      {
        id: "generalization",
        type: "generalization",
        label: "Generalization Attempts",
        description: "Trying the skill in new routines.",
        status: "emerging",
      },
      {
        id: "regulation",
        type: "regulation_recovery",
        label: "Regulation / Recovery",
        description: "Returns after a short break.",
        status: "stable",
      },
      {
        id: "participation",
        type: "participation",
        label: "Participation",
        description: "Joins supported opportunities.",
        status: "stable",
      },
    ]),
  getProgressDataForLearner: (learnerId: string) =>
    pause(progressData.filter((point) => point.learnerId === learnerId)),
  saveSessionDataRecord: async (payload: {
    learnerId: string;
    goal: string;
    opportunities: number;
    correct: number;
    independent: number;
    promptLevel: string;
    signalsHighlighted: string[];
    teacherNotes: string;
  }) => {
    progressData.push({
      id: `progress-local-${progressData.length + 1}`,
      learnerId: payload.learnerId,
      sessionDate: "Today",
      goal: payload.goal,
      opportunities: payload.opportunities,
      accuracyPercent: Math.round(
        (payload.correct / payload.opportunities) * 100,
      ),
      independencePercent: Math.round(
        (payload.independent / payload.opportunities) * 100,
      ),
      promptLevel: payload.promptLevel,
      signalsHighlighted: payload.signalsHighlighted,
      teacherNotes: payload.teacherNotes,
    });
    return lessonKitMockApi.getProgressSummaryForLearner(payload.learnerId);
  },
};

async function updateLocalMaterial(
  materialId: string,
  update: (item: GeneratedMaterial) => GeneratedMaterial,
): Promise<GeneratedMaterial> {
  for (const [id, lessonPackage] of packages) {
    const index = lessonPackage.materials.findIndex(
      (item) => item.id === materialId,
    );
    if (index >= 0) {
      lessonPackage.materials[index] = update(lessonPackage.materials[index]);
      packages.set(id, lessonPackage);
      return pause(lessonPackage.materials[index]);
    }
  }
  throw new Error("Generated material not found");
}
