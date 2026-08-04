import { lessonKitMockApi } from "../mockApi";
import type {
  AIChatState,
  AIImageGenerationInput,
  AIImageGenerationResult,
  GenerationJob,
  AILessonQuestionsTestResult,
  AIProviderStatus,
  ExportJob,
  GeneratedMaterial,
  LearnerProfile,
  LearnerProfileExtraction,
  LearnerProgressSummary,
  LearnerRecord,
  LessonDesignDraft,
  LessonPackage,
  LessonPackageUpdateInput,
  LessonSession,
  LessonSessionStat,
  LessonPackageVersion,
  LessonPackageVersionComparison,
  LessonSectionEditPreview,
  PrintableLessonKitArtifact,
  PrintableLessonKitInput,
  PackagePrintReadiness,
  PrintPresetCatalog,
  LessonSessionSummary,
  MaterialLibraryItem,
  MaterialQuickEditAction,
  ProgressDataPoint,
  ProgressSignal,
  RecentLesson,
  RecordDeletionResult,
  CompleteSessionInput,
  SessionCompletionTemplate,
  SessionOutcome,
  SessionRunState,
  StartSessionInput,
  PatchSessionRunDraftInput,
  GoalProgressMetric,
  GoalProgressSeries,
  GoalProgressSeriesOption,
  NextSessionRecommendation,
  NextSessionMaterialImpactPlan,
  ReviewNextSessionRecommendationInput,
  UpdateNextSessionPlanInput,
  RecordUploadIntent,
  TeacherHandoffExportInput,
  HandoffExportDownload,
} from "../types";
import { backendClient } from "./backendClient";

const useLocalMock = import.meta.env.VITE_USE_LOCAL_MOCK === "true";
const pendingChatStarts = new Map<string, Promise<AIChatState>>();

export interface RecordUploadInput {
  fileName: string;
  fileType: string;
  text: string;
}
export interface MaterialUpdateInput {
  title: string;
  content: GeneratedMaterial["content"];
  printLayout: GeneratedMaterial["printLayout"];
}
export interface MaterialCreateInput {
  title: string;
  type: string;
  thumbnailLabel: string;
  reusable?: boolean;
}
export interface SessionDataRecordInput {
  learnerId: string;
  lessonPackageId: string;
  goal: string;
  opportunities: number;
  correct: number;
  independent: number;
  promptLevel: string;
  signalsHighlighted: string[];
  teacherNotes: string;
}

export const lessonKitApi = {
  resetSyntheticN482Fixture: (): Promise<{
    fixtureId: string;
    label: string;
    synthetic: true;
    learnerId: string;
    packageId: string;
    packageRevision: number;
    lessonSpecRevision: number;
    sessionId: string;
    resetAt: string;
  }> => backendClient.post("/v2/dev/fixtures/n482/reset"),
  getAIStatus: (): Promise<AIProviderStatus> =>
    backendClient.get("/v2/dev/ai-status"),
  testAILessonQuestions: (
    message: string,
  ): Promise<AILessonQuestionsTestResult> =>
    backendClient.post("/v2/dev/test-ai-lesson-questions", {
      learnerId: "a102",
      message,
    }),
  testAIImageGeneration: (
    payload: AIImageGenerationInput,
  ): Promise<AIImageGenerationResult> =>
    backendClient.post("/v2/dev/test-image-generation", payload),

  getLearners: (): Promise<LearnerProfile[]> =>
    useLocalMock
      ? lessonKitMockApi.getLearners()
      : backendClient.get("/v2/learners"),
  getLearnerById: async (id: string): Promise<LearnerProfile> => {
    if (!useLocalMock) return backendClient.get(`/v2/learners/${id}`);
    const learner = await lessonKitMockApi.getLearnerById(id);
    if (!learner) throw new Error("Learner not found");
    return learner;
  },
  createLearner: (
    payload: Omit<LearnerProfile, "id">,
  ): Promise<LearnerProfile> =>
    useLocalMock
      ? lessonKitMockApi.createLearner(payload)
      : backendClient.post("/v2/learners", payload),
  updateLearner: (
    id: string,
    payload: Partial<Omit<LearnerProfile, "id">> & { expectedVersion?: number },
  ): Promise<LearnerProfile> =>
    useLocalMock
      ? lessonKitMockApi.updateLearner(id, payload)
      : backendClient.patch(`/v2/learners/${id}`, payload),
  confirmLearnerProfile: async (
    id: string,
    expectedVersion: number,
  ): Promise<LearnerProfile> =>
    useLocalMock
      ? lessonKitMockApi.updateLearner(id, { profileReviewStatus: "confirmed" })
      : backendClient.post(`/v2/learners/${id}/profile/confirm`, {
          expectedVersion,
        }),
  reviewProfileFactor: (
    id: string,
    factorId: string,
    payload: {
      decision: "confirm" | "edit" | "reject";
      editedValue?: string;
      expectedVersion: number;
    },
  ): Promise<LearnerProfile> =>
    useLocalMock
      ? lessonKitMockApi.getLearnerById(id).then((learner) => {
          if (!learner) throw new Error("Learner not found");
          return learner;
        })
      : backendClient.patch(
          `/v2/learners/${id}/profile-factors/${factorId}`,
          payload,
        ),
  getRecordsForLearner: (id: string): Promise<LearnerRecord[]> =>
    useLocalMock
      ? lessonKitMockApi.getRecordsForLearner(id)
      : backendClient.get(`/v2/learners/${id}/records`),
  addRecordForLearner: (
    id: string,
    payload: RecordUploadInput,
  ): Promise<LearnerRecord> =>
    useLocalMock
      ? lessonKitMockApi.addRecordForLearner(id, payload)
      : backendClient.post(`/v2/learners/${id}/records`, payload),
  requestRecordUpload: async (
    id: string,
    file: File,
  ): Promise<RecordUploadIntent> => {
    if (useLocalMock) {
      const record = await lessonKitMockApi.addRecordForLearner(id, {
        fileName: file.name,
        fileType: file.name.split(".").pop()?.toUpperCase() || "TXT",
        text: "Local mock upload awaiting teacher review.",
      });
      return {
        record,
        uploadUrl: "mock://local-upload",
        method: "PUT",
        requiredHeaders: { "Content-Type": file.type || "text/plain" },
        expiresAt: new Date(Date.now() + 300000).toISOString(),
      };
    }
    return backendClient.post(`/v2/learners/${id}/records/upload-intent`, {
      fileName: file.name,
      contentType: file.type || contentTypeForFile(file.name),
      sizeBytes: file.size,
    });
  },
  uploadRecordObject: (
    intent: RecordUploadIntent,
    file: File,
    onProgress?: (percent: number) => void,
  ): Promise<void> =>
    useLocalMock
      ? Promise.resolve(onProgress?.(100))
      : backendClient.putFile(
          intent.uploadUrl,
          file,
          intent.requiredHeaders,
          onProgress,
        ),
  completeRecordUpload: async (
    learnerId: string,
    recordId: string,
  ): Promise<LearnerRecord> => {
    if (useLocalMock) {
      const items = await lessonKitMockApi.getRecordsForLearner(learnerId);
      return (
        items.find((item) => item.id === recordId) ??
        Promise.reject(new Error("Record not found"))
      );
    }
    return backendClient.post(
      `/v2/learners/${learnerId}/records/${recordId}/complete`,
      {},
    );
  },
  correctRecordText: (
    learnerId: string,
    recordId: string,
    correctedText: string,
    expectedVersion?: number,
  ): Promise<LearnerRecord> =>
    useLocalMock
      ? lessonKitMockApi.addRecordForLearner(learnerId, {
          fileName: "Teacher correction.txt",
          fileType: "TXT",
          text: correctedText,
        })
      : backendClient.patch(
          `/v2/learners/${learnerId}/records/${recordId}/extracted-text`,
          { correctedText, expectedVersion },
        ),
  deleteLearnerRecord: async (
    learnerId: string,
    recordId: string,
  ): Promise<RecordDeletionResult> => {
    if (useLocalMock)
      return {
        recordId,
        status: "deleted",
        retryable: false,
        message: "Local mock record removed.",
      };
    return backendClient.del(`/v2/learners/${learnerId}/records/${recordId}`);
  },
  getExtractedLearnerProfile: (
    id: string,
  ): Promise<LearnerProfileExtraction> =>
    useLocalMock
      ? lessonKitMockApi.getExtractedLearnerProfile(id)
      : backendClient.get(`/v2/learners/${id}/profile-extraction`),

  getInitialLessonChat: async (
    learnerId: string,
    resumeExisting = false,
  ): Promise<AIChatState> => {
    const key = `${learnerId}:${resumeExisting}`;
    const pending = pendingChatStarts.get(key);
    if (pending) return pending;
    const request = useLocalMock
      ? lessonKitMockApi.getInitialLessonChat(learnerId)
      : backendClient.post<AIChatState>("/v2/lesson-chat/start", {
          learnerId,
          resumeExisting,
        });
    pendingChatStarts.set(key, request);
    try {
      return await request;
    } finally {
      if (pendingChatStarts.get(key) === request) pendingChatStarts.delete(key);
    }
  },
  submitLessonRequest: (
    conversationId: string,
    learnerId: string,
    message: string,
    currentDraft?: LessonDesignDraft,
    signal?: AbortSignal,
  ): Promise<AIChatState> =>
    useLocalMock
      ? lessonKitMockApi.submitLessonRequest(conversationId, message)
      : backendClient.post(
          "/v2/lesson-chat/message",
          { conversationId, learnerId, message, currentDraft },
          { signal },
        ),
  getLessonChat: (conversationId: string): Promise<AIChatState> =>
    backendClient.get(`/v2/lesson-chat/${conversationId}`),
  updateAIQuestionAnswer: (
    conversationId: string,
    questionId: string,
    selectedOptionIds: string[],
    customAnswer = "",
    expectedDraftVersion?: number,
    saveUnsupportedForFuture = false,
  ): Promise<AIChatState> =>
    useLocalMock
      ? lessonKitMockApi.updateAIQuestionAnswer(
          conversationId,
          questionId,
          selectedOptionIds,
          customAnswer,
        )
      : backendClient.patch(`/v2/lesson-chat/${conversationId}/answers`, {
          questionId,
          selectedOptionIds,
          customAnswer,
          expectedDraftVersion,
          saveUnsupportedForFuture,
        }),
  refreshLessonRecommendations: (
    conversationId: string,
    expectedDraftVersion: number,
  ): Promise<AIChatState> =>
    backendClient.post(
      `/v2/lesson-chat/${conversationId}/refresh-recommendations`,
      { expectedDraftVersion },
    ),
  previewPackageContentPlan: (
    conversationId: string,
    expectedDraftVersion: number,
  ): Promise<AIChatState> =>
    useLocalMock
      ? lessonKitMockApi.previewPackageContentPlan(conversationId)
      : backendClient.post(`/v2/lesson-chat/${conversationId}/content-plan`, {
          expectedDraftVersion,
        }),
  adjustPackageContentPlan: (
    conversationId: string,
    payload: {
      action: "set_optional" | "set_companion" | "add_material";
      materialType: string;
      included: boolean;
      expectedDraftVersion: number;
    },
  ): Promise<AIChatState> =>
    useLocalMock
      ? lessonKitMockApi.adjustPackageContentPlan(conversationId, payload)
      : backendClient.patch(
          `/v2/lesson-chat/${conversationId}/content-plan`,
          payload,
        ),
  clearLessonChat: (conversationId: string): Promise<AIChatState> =>
    useLocalMock
      ? lessonKitMockApi.clearLessonChat(conversationId)
      : backendClient.post(`/v2/lesson-chat/${conversationId}/clear`),
  cancelLessonRequest: (conversationId: string): Promise<AIChatState> =>
    useLocalMock
      ? lessonKitMockApi.clearLessonChat(conversationId)
      : backendClient.post(`/v2/lesson-chat/${conversationId}/cancel`),

  generateLessonPackageFromDraft: (
    draft: LessonDesignDraft,
    signal?: AbortSignal,
  ): Promise<LessonPackage> =>
    useLocalMock
      ? lessonKitMockApi.generateLessonPackageFromDraft(draft)
      : backendClient.post("/v2/lesson-packages/generate", draft, { signal }),
  getLessonPackage: (id: string): Promise<LessonPackage> =>
    useLocalMock
      ? lessonKitMockApi.getLessonPackage(id)
      : backendClient.get(`/v2/lesson-packages/${id}`),
  getPackagePrintReadiness: (id: string): Promise<PackagePrintReadiness> =>
    backendClient.get(`/v2/lesson-packages/${id}/print-readiness`),
  getPrintPresetCatalog: (
    id: string,
    pageSize: "Letter" | "A4",
    textProfile: "standard" | "large" = "standard",
  ): Promise<PrintPresetCatalog> =>
    backendClient.get(
      `/v2/lesson-packages/${id}/print-presets?pageSize=${pageSize}&textProfile=${textProfile}`,
    ),
  getPackageGenerationJob: (id: string): Promise<GenerationJob> =>
    backendClient.get(`/v2/lesson-packages/${id}/generation-job`),
  retryGenerationJob: (id: string): Promise<GenerationJob> =>
    backendClient.post(`/v2/generation-jobs/${id}/retry`),
  retryGenerationVisual: (
    id: string,
    visualId: string,
  ): Promise<GenerationJob> =>
    backendClient.post(`/v2/generation-jobs/${id}/visuals/${visualId}/retry`),
  getLessonPackages: (learnerId?: string): Promise<LessonPackage[]> =>
    useLocalMock
      ? Promise.resolve([])
      : backendClient.get(
          `/v2/lesson-packages${learnerId ? `?learnerId=${encodeURIComponent(learnerId)}` : ""}`,
        ),
  updateLessonPackage: (
    id: string,
    payload: LessonPackageUpdateInput,
  ): Promise<LessonPackage> =>
    useLocalMock
      ? lessonKitMockApi.updateLessonPackage(id, payload)
      : backendClient.patch(`/v2/lesson-packages/${id}`, payload),
  approveLessonPackage: (
    id: string,
    expectedVersion: number,
    reason = "",
  ): Promise<LessonPackage> =>
    useLocalMock
      ? lessonKitMockApi.approveLessonPackage(id)
      : backendClient.post(`/v2/lesson-packages/${id}/approve`, {
          expectedVersion,
          reason,
        }),
  rejectLessonPackage: (
    id: string,
    expectedVersion: number,
    reason = "",
  ): Promise<LessonPackage> =>
    backendClient.post(`/v2/lesson-packages/${id}/reject`, {
      expectedVersion,
      reason,
    }),
  regenerateLessonPackageSection: (
    id: string,
    section: string,
    expectedVersion: number,
    teacherInstructions = "",
  ): Promise<LessonPackage> =>
    backendClient.post(`/v2/lesson-packages/${id}/regenerate-section`, {
      section,
      expectedVersion,
      teacherInstructions,
    }),
  previewLessonSectionEdit: (
    id: string,
    payload: {
      sectionId: string;
      sectionLabel: string;
      currentText: string;
      instruction: string;
      expectedVersion: number;
    },
  ): Promise<LessonSectionEditPreview> =>
    backendClient.post(
      `/v2/lesson-packages/${id}/section-edit-preview`,
      payload,
    ),
  getLessonPackageVersions: (id: string): Promise<LessonPackageVersion[]> =>
    backendClient.get(`/v2/lesson-packages/${id}/versions`),
  compareLessonPackageVersions: (
    id: string,
    fromVersion: number,
    toVersion: number,
  ): Promise<LessonPackageVersionComparison> =>
    backendClient.get(
      `/v2/lesson-packages/${id}/versions/compare?fromVersion=${fromVersion}&toVersion=${toVersion}`,
    ),
  restoreLessonPackageVersion: (
    id: string,
    version: number,
    expectedVersion: number,
  ): Promise<LessonPackage> =>
    backendClient.post(
      `/v2/lesson-packages/${id}/versions/${version}/restore`,
      { expectedVersion, reason: "Teacher restore" },
    ),
  getGeneratedMaterials: (id: string): Promise<GeneratedMaterial[]> =>
    useLocalMock
      ? lessonKitMockApi.getGeneratedMaterials(id)
      : backendClient.get(`/v2/lesson-packages/${id}/materials`),
  updateGeneratedMaterial: (
    id: string,
    payload: MaterialUpdateInput,
  ): Promise<GeneratedMaterial> =>
    useLocalMock
      ? lessonKitMockApi.updateGeneratedMaterial(id, payload)
      : backendClient.patch(`/v2/generated-materials/${id}`, payload),
  reviewGeneratedMaterial: (id: string): Promise<GeneratedMaterial> =>
    useLocalMock
      ? lessonKitMockApi.reviewGeneratedMaterial(id)
      : backendClient.post(`/v2/generated-materials/${id}/review`),
  approveGeneratedMaterial: (id: string): Promise<GeneratedMaterial> =>
    useLocalMock
      ? lessonKitMockApi.approveGeneratedMaterial(id)
      : backendClient.post(`/v2/generated-materials/${id}/approve`),
  quickEditGeneratedMaterial: (
    id: string,
    action: MaterialQuickEditAction,
  ): Promise<GeneratedMaterial> =>
    useLocalMock
      ? lessonKitMockApi.quickEditGeneratedMaterial(id, action)
      : backendClient.post(`/v2/generated-materials/${id}/quick-edit`, {
          action,
        }),
  generateGeneratedMaterialImage: (id: string): Promise<GeneratedMaterial> =>
    useLocalMock
      ? lessonKitMockApi.quickEditGeneratedMaterial(id, "regenerate_artwork")
      : backendClient.post(`/v2/generated-materials/${id}/generate-image`, {}),
  regenerateMaterialVisual: (
    id: string,
    visualId: string,
  ): Promise<GeneratedMaterial> =>
    useLocalMock
      ? lessonKitMockApi.reviewMaterialVisual(id, visualId, "approve")
      : backendClient.post(
          `/v2/generated-materials/${id}/visuals/${visualId}/regenerate`,
          {},
        ),
  useMaterialVisualFallback: (
    id: string,
    visualId: string,
  ): Promise<GeneratedMaterial> =>
    useLocalMock
      ? lessonKitMockApi.useMaterialVisualFallback(id, visualId)
      : backendClient.post(
          `/v2/generated-materials/${id}/visuals/${visualId}/fallback`,
          {},
        ),
  replaceMaterialVisual: (
    id: string,
    visualId: string,
    assetId: string,
  ): Promise<GeneratedMaterial> =>
    backendClient.patch(
      `/v2/generated-materials/${id}/visuals/${visualId}/asset`,
      { assetId },
    ),
  reviewMaterialVisual: (
    id: string,
    visualId: string,
    action: "approve" | "reject",
  ): Promise<GeneratedMaterial> =>
    useLocalMock
      ? lessonKitMockApi.reviewMaterialVisual(id, visualId, action)
      : backendClient.post(
          `/v2/generated-materials/${id}/visuals/${visualId}/review`,
          { action },
        ),
  exportLessonPackage: (
    id: string,
    format: ExportJob["format"],
    materialIds: string[] = [],
  ): Promise<ExportJob> =>
    useLocalMock
      ? lessonKitMockApi.exportLessonPackage(id, format)
      : backendClient.post(`/v2/lesson-packages/${id}/export`, {
          format,
          materialIds,
          reviewedConfirmation: true,
        }),
  createPrintableLessonKit: (
    id: string,
    payload: PrintableLessonKitInput,
  ): Promise<ExportJob> =>
    backendClient.post(`/v2/lesson-packages/${id}/printable-kit`, payload),
  createPrintableLessonKitArtifact: (
    id: string,
    payload: PrintableLessonKitInput,
  ): Promise<PrintableLessonKitArtifact> =>
    backendClient.post(`/v2/lesson-packages/${id}/pdf-artifacts`, payload),
  getPrintableLessonKitDownload: (id: string): Promise<HandoffExportDownload> =>
    backendClient.post(`/v2/printable-lesson-kits/${id}/download`),
  createHandoffExport: (
    learnerId: string,
    payload: TeacherHandoffExportInput,
  ): Promise<ExportJob> =>
    useLocalMock
      ? lessonKitMockApi.createHandoffExport(learnerId, payload)
      : backendClient.post(
          `/v2/learners/${learnerId}/handoff-exports`,
          payload,
        ),
  getHandoffExports: (learnerId?: string): Promise<ExportJob[]> =>
    useLocalMock
      ? lessonKitMockApi.getHandoffExports(learnerId)
      : backendClient.get(
          `/v2/handoff-exports${learnerId ? `?learnerId=${encodeURIComponent(learnerId)}` : ""}`,
        ),
  getHandoffExport: (id: string): Promise<ExportJob> =>
    backendClient.get(`/v2/handoff-exports/${id}`),
  retryHandoffExport: (id: string): Promise<ExportJob> =>
    useLocalMock
      ? lessonKitMockApi.retryHandoffExport(id)
      : backendClient.post(`/v2/handoff-exports/${id}/retry`),
  getHandoffExportDownload: (id: string): Promise<HandoffExportDownload> =>
    useLocalMock
      ? lessonKitMockApi.getHandoffExportDownload(id)
      : backendClient.post(`/v2/handoff-exports/${id}/download`),
  deleteHandoffExport: (id: string): Promise<ExportJob> =>
    useLocalMock
      ? lessonKitMockApi.deleteHandoffExport(id)
      : backendClient.del(`/v2/handoff-exports/${id}`),

  getSessions: (): Promise<LessonSession[]> =>
    useLocalMock
      ? lessonKitMockApi.getSessions()
      : backendClient.get("/v2/sessions"),
  getSessionStats: (): Promise<LessonSessionStat[]> =>
    useLocalMock
      ? lessonKitMockApi.getSessionStats()
      : backendClient.get("/v2/sessions/stats"),
  createSession: (
    payload: Omit<LessonSession, "id" | "updatedAt">,
  ): Promise<LessonSession> =>
    useLocalMock
      ? lessonKitMockApi.createSession(payload)
      : backendClient.post("/v2/sessions", payload),
  duplicateSession: (id: string): Promise<LessonSession> =>
    useLocalMock
      ? lessonKitMockApi.duplicateSession(id)
      : backendClient.post(`/v2/sessions/${id}/duplicate`),
  startSession: (id: string, payload: StartSessionInput): Promise<SessionRunState> =>
    useLocalMock
      ? lessonKitMockApi.startSession(id, payload)
      : backendClient.post(`/v2/sessions/${id}/start`, payload),
  getSessionRun: (id: string): Promise<SessionRunState> =>
    useLocalMock
      ? lessonKitMockApi.getSessionRun(id)
      : backendClient.get(`/v2/sessions/${id}/run`),
  patchSessionRunDraft: (
    id: string,
    payload: PatchSessionRunDraftInput,
  ): Promise<SessionRunState> =>
    useLocalMock
      ? lessonKitMockApi.patchSessionRunDraft(id, payload)
      : backendClient.patch(`/v2/sessions/${id}/run-draft`, payload),
  completeSessionRunDraft: (
    id: string,
    payload: { expectedVersion: number; idempotencyKey: string },
  ): Promise<SessionOutcome> =>
    useLocalMock
      ? lessonKitMockApi.completeSessionRunDraft(id, payload)
      : backendClient.post(`/v2/sessions/${id}/run-draft/complete`, payload),
  getSessionSummary: (id: string): Promise<LessonSessionSummary> =>
    useLocalMock
      ? lessonKitMockApi.getSessionSummary(id)
      : backendClient.get(`/v2/sessions/${id}/summary`),
  getSessionCompletionTemplate: (
    id: string,
  ): Promise<SessionCompletionTemplate> =>
    useLocalMock
      ? lessonKitMockApi.getSessionCompletionTemplate(id)
      : backendClient.get(`/v2/sessions/${id}/completion-template`),
  completeSession: (
    id: string,
    payload: CompleteSessionInput,
  ): Promise<SessionOutcome> =>
    useLocalMock
      ? lessonKitMockApi.completeSession(id, payload)
      : backendClient.post(`/v2/sessions/${id}/complete`, payload),
  getSessionOutcome: (id: string): Promise<SessionOutcome> =>
    useLocalMock
      ? lessonKitMockApi.getSessionOutcome(id)
      : backendClient.get(`/v2/sessions/${id}/outcome`),
  getGoalProgressSeriesOptions: (
    learnerId: string,
  ): Promise<GoalProgressSeriesOption[]> =>
    useLocalMock
      ? lessonKitMockApi.getGoalProgressSeriesOptions(learnerId)
      : backendClient.get(`/v2/learners/${learnerId}/progress-series-options`),
  getGoalProgressSeries: (
    learnerId: string,
    metric: GoalProgressMetric,
    goalId?: string,
    goalRevision?: number,
    contextKey?: string,
  ): Promise<GoalProgressSeries> =>
    useLocalMock
      ? lessonKitMockApi.getGoalProgressSeries(
          learnerId,
          metric,
          goalId,
          goalRevision,
          contextKey,
        )
      : backendClient.get(
          `/v2/learners/${learnerId}/progress-series?metric=${encodeURIComponent(metric)}${goalId ? `&goalId=${encodeURIComponent(goalId)}` : ""}${goalRevision ? `&goalRevision=${goalRevision}` : ""}${contextKey ? `&contextKey=${encodeURIComponent(contextKey)}` : ""}`,
        ),
  getNextSessionRecommendations: (
    learnerId: string,
    goalId: string,
    goalRevision: number,
  ): Promise<NextSessionRecommendation[]> =>
    useLocalMock
      ? lessonKitMockApi.getNextSessionRecommendations(
          learnerId,
          goalId,
          goalRevision,
        )
      : backendClient.get(
          `/v2/learners/${learnerId}/next-session-recommendations?goalId=${encodeURIComponent(goalId)}&goalRevision=${goalRevision}`,
        ),
  generateNextSessionRecommendations: (
    learnerId: string,
    goalId: string,
    goalRevision: number,
  ): Promise<NextSessionRecommendation[]> =>
    useLocalMock
      ? lessonKitMockApi.generateNextSessionRecommendations(
          learnerId,
          goalId,
          goalRevision,
        )
      : backendClient.post(
          `/v2/learners/${learnerId}/next-session-recommendations/generate`,
          { goalId, goalRevision },
        ),
  reviewNextSessionRecommendation: (
    recommendationId: string,
    payload: ReviewNextSessionRecommendationInput,
  ): Promise<NextSessionRecommendation> =>
    useLocalMock
      ? lessonKitMockApi.reviewNextSessionRecommendation(
          recommendationId,
          payload,
        )
      : backendClient.patch(
          `/v2/next-session-recommendations/${recommendationId}`,
          payload,
        ),
  createNextSessionPlan: (
    packageId: string,
    expectedPackageRevision: number,
  ): Promise<NextSessionMaterialImpactPlan> =>
    useLocalMock
      ? lessonKitMockApi.createNextSessionPlan(
          packageId,
          expectedPackageRevision,
        )
      : backendClient.post(`/v2/lesson-packages/${packageId}/next-session-plan`, {
          expectedPackageRevision,
        }),
  getNextSessionPlan: (
    planId: string,
  ): Promise<NextSessionMaterialImpactPlan> =>
    useLocalMock
      ? lessonKitMockApi.getNextSessionPlan(planId)
      : backendClient.get(`/v2/next-session-plans/${planId}`),
  updateNextSessionPlan: (
    planId: string,
    payload: UpdateNextSessionPlanInput,
  ): Promise<NextSessionMaterialImpactPlan> =>
    useLocalMock
      ? lessonKitMockApi.updateNextSessionPlan(planId, payload)
      : backendClient.patch(`/v2/next-session-plans/${planId}`, payload),
  createNextSessionPackage: (
    planId: string,
    expectedPlanVersion: number,
  ): Promise<LessonPackage> =>
    useLocalMock
      ? lessonKitMockApi.createNextSessionPackage(planId, expectedPlanVersion)
      : backendClient.post(`/v2/next-session-plans/${planId}/create-package`, {
          expectedPlanVersion,
        }),
  regenerateNextSessionMaterial: (
    packageId: string,
    materialId: string,
    expectedMaterialVersion: number,
  ): Promise<GeneratedMaterial> =>
    useLocalMock
      ? lessonKitMockApi.regenerateNextSessionMaterial(
          packageId,
          materialId,
          expectedMaterialVersion,
        )
      : backendClient.post(
          `/v2/lesson-packages/${packageId}/materials/${materialId}/regenerate`,
          { expectedMaterialVersion },
        ),
  regenerateNextSessionScenario: (
    packageId: string,
    materialId: string,
    scenarioId: string,
    teacherInstruction: string,
    expectedMaterialVersion: number,
  ): Promise<GeneratedMaterial> =>
    useLocalMock
      ? lessonKitMockApi.regenerateNextSessionScenario(
          packageId,
          materialId,
          scenarioId,
          teacherInstruction,
          expectedMaterialVersion,
        )
      : backendClient.post(
          `/v2/lesson-packages/${packageId}/materials/${materialId}/regenerate-scenario`,
          { scenarioId, teacherInstruction, expectedMaterialVersion },
        ),

  getMaterials: (): Promise<MaterialLibraryItem[]> =>
    useLocalMock
      ? lessonKitMockApi.getMaterials()
      : backendClient.get("/v2/materials"),
  createMaterial: (
    payload: MaterialCreateInput,
  ): Promise<MaterialLibraryItem> =>
    useLocalMock
      ? lessonKitMockApi.createMaterial(payload)
      : backendClient.post("/v2/materials", payload),
  duplicateMaterial: (id: string): Promise<MaterialLibraryItem> =>
    useLocalMock
      ? lessonKitMockApi.duplicateMaterial(id)
      : backendClient.post(`/v2/materials/${id}/duplicate`),

  getRecentLessonsForLearner: (id: string): Promise<RecentLesson[]> =>
    useLocalMock
      ? lessonKitMockApi.getRecentLessonsForLearner(id)
      : backendClient.get(`/v2/learners/${id}/recent-lessons`),
  getProgressSummaryForLearner: (
    id: string,
  ): Promise<LearnerProgressSummary> =>
    useLocalMock
      ? lessonKitMockApi.getProgressSummaryForLearner(id)
      : backendClient.get(`/v2/learners/${id}/progress-summary`),
  getProgressSignalsForLearner: (id: string): Promise<ProgressSignal[]> =>
    useLocalMock
      ? lessonKitMockApi.getProgressSignalsForLearner()
      : backendClient.get(`/v2/learners/${id}/progress-signals`),
  getProgressDataForLearner: (id: string): Promise<ProgressDataPoint[]> =>
    useLocalMock
      ? lessonKitMockApi.getProgressDataForLearner(id)
      : backendClient.get(`/v2/learners/${id}/progress-data`),
  saveSessionDataRecord: (
    payload: SessionDataRecordInput,
  ): Promise<LearnerProgressSummary> =>
    useLocalMock
      ? lessonKitMockApi.saveSessionDataRecord(payload)
      : backendClient.post("/v2/session-data", payload),
};

function contentTypeForFile(fileName: string): string {
  const extension = fileName.toLowerCase().split(".").pop();
  if (extension === "pdf") return "application/pdf";
  if (extension === "docx")
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  return "text/plain";
}
