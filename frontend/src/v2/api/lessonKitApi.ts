import { lessonKitMockApi } from "../mockApi";
import type {
  AIChatState, AIImageGenerationInput, AIImageGenerationResult,
  AILessonQuestionsTestResult, AIProviderStatus, ExportJob, GeneratedMaterial, LearnerProfile,
  LearnerProfileExtraction, LearnerProgressSummary, LearnerRecord,
  LessonDesignDraft, LessonPackage, LessonPackageUpdateInput, LessonSession, LessonSessionStat,
  LessonSessionSummary, MaterialLibraryItem, MaterialQuickEditAction,
  ProgressDataPoint, ProgressSignal, RecentLesson,
} from "../types";
import { backendClient } from "./backendClient";

const useLocalMock = import.meta.env.VITE_USE_LOCAL_MOCK === "true";

export interface RecordUploadInput { fileName: string; fileType: string; text: string }
export interface MaterialUpdateInput { title: string; content: GeneratedMaterial["content"]; printLayout: GeneratedMaterial["printLayout"] }
export interface MaterialCreateInput { title: string; type: string; thumbnailLabel: string; reusable?: boolean }
export interface SessionDataRecordInput { learnerId:string;lessonPackageId:string;goal:string;opportunities:number;correct:number;independent:number;promptLevel:string;signalsHighlighted:string[];teacherNotes:string }

export const lessonKitApi = {
  getAIStatus: ():Promise<AIProviderStatus> => backendClient.get("/v2/dev/ai-status"),
  testAILessonQuestions: (message:string):Promise<AILessonQuestionsTestResult> => backendClient.post("/v2/dev/test-ai-lesson-questions",{learnerId:"a102",message}),
  testAIImageGeneration: (payload:AIImageGenerationInput):Promise<AIImageGenerationResult> => backendClient.post("/v2/dev/test-image-generation",payload),

  getLearners: ():Promise<LearnerProfile[]> => useLocalMock ? lessonKitMockApi.getLearners() : backendClient.get("/v2/learners"),
  getLearnerById: async (id:string):Promise<LearnerProfile> => {
    if (!useLocalMock) return backendClient.get(`/v2/learners/${id}`);
    const learner=await lessonKitMockApi.getLearnerById(id);if(!learner)throw new Error("Learner not found");return learner;
  },
  createLearner: (payload:Omit<LearnerProfile,"id">):Promise<LearnerProfile> => useLocalMock ? lessonKitMockApi.createLearner(payload) : backendClient.post("/v2/learners",payload),
  updateLearner: (id:string,payload:Partial<Omit<LearnerProfile,"id"|"code">>):Promise<LearnerProfile> => useLocalMock ? lessonKitMockApi.updateLearner(id,payload) : backendClient.patch(`/v2/learners/${id}`,payload),
  getRecordsForLearner: (id:string):Promise<LearnerRecord[]> => useLocalMock ? lessonKitMockApi.getRecordsForLearner(id) : backendClient.get(`/v2/learners/${id}/records`),
  addRecordForLearner: (id:string,payload:RecordUploadInput):Promise<LearnerRecord> => useLocalMock ? lessonKitMockApi.addRecordForLearner(id,payload) : backendClient.post(`/v2/learners/${id}/records`,payload),
  getExtractedLearnerProfile: (id:string):Promise<LearnerProfileExtraction> => useLocalMock ? lessonKitMockApi.getExtractedLearnerProfile(id) : backendClient.get(`/v2/learners/${id}/profile-extraction`),

  getInitialLessonChat: async (learnerId:string):Promise<AIChatState> => {
    const state=useLocalMock?await lessonKitMockApi.getInitialLessonChat(learnerId):await backendClient.post<AIChatState>("/v2/lesson-chat/start",{learnerId});
    return state;
  },
  submitLessonRequest: (conversationId:string,learnerId:string,message:string,currentDraft?:LessonDesignDraft):Promise<AIChatState> => useLocalMock ? lessonKitMockApi.submitLessonRequest(conversationId,message) : backendClient.post("/v2/lesson-chat/message",{conversationId,learnerId,message,currentDraft}),
  updateAIQuestionAnswer: (conversationId:string,questionId:string,selectedOptionIds:string[],customAnswer=""):Promise<AIChatState> => useLocalMock ? lessonKitMockApi.updateAIQuestionAnswer(conversationId,questionId,selectedOptionIds,customAnswer) : backendClient.patch(`/v2/lesson-chat/${conversationId}/answers`,{questionId,selectedOptionIds,customAnswer}),
  clearLessonChat: (conversationId:string):Promise<AIChatState> => useLocalMock ? lessonKitMockApi.clearLessonChat(conversationId) : backendClient.post(`/v2/lesson-chat/${conversationId}/clear`),

  generateLessonPackageFromDraft: (draft:LessonDesignDraft):Promise<LessonPackage> => useLocalMock ? lessonKitMockApi.generateLessonPackageFromDraft(draft) : backendClient.post("/v2/lesson-packages/generate",draft),
  getLessonPackage: (id:string):Promise<LessonPackage> => useLocalMock ? lessonKitMockApi.getLessonPackage(id) : backendClient.get(`/v2/lesson-packages/${id}`),
  updateLessonPackage: (id:string,payload:LessonPackageUpdateInput):Promise<LessonPackage> => useLocalMock ? lessonKitMockApi.updateLessonPackage(id,payload) : backendClient.patch(`/v2/lesson-packages/${id}`,payload),
  getGeneratedMaterials: (id:string):Promise<GeneratedMaterial[]> => useLocalMock ? lessonKitMockApi.getGeneratedMaterials(id) : backendClient.get(`/v2/lesson-packages/${id}/materials`),
  updateGeneratedMaterial: (id:string,payload:MaterialUpdateInput):Promise<GeneratedMaterial> => useLocalMock ? lessonKitMockApi.updateGeneratedMaterial(id,payload) : backendClient.patch(`/v2/generated-materials/${id}`,payload),
  approveGeneratedMaterial: (id:string):Promise<GeneratedMaterial> => useLocalMock ? lessonKitMockApi.approveGeneratedMaterial(id) : backendClient.post(`/v2/generated-materials/${id}/approve`),
  quickEditGeneratedMaterial: (id:string,action:MaterialQuickEditAction):Promise<GeneratedMaterial> => useLocalMock ? lessonKitMockApi.quickEditGeneratedMaterial(id,action) : backendClient.post(`/v2/generated-materials/${id}/quick-edit`,{action}),
  exportLessonPackage: (id:string,format:ExportJob["format"],materialIds:string[]=[]):Promise<ExportJob> => useLocalMock ? lessonKitMockApi.exportLessonPackage(id,format) : backendClient.post(`/v2/lesson-packages/${id}/export`,{format,materialIds}),

  getSessions: ():Promise<LessonSession[]> => useLocalMock ? lessonKitMockApi.getSessions() : backendClient.get("/v2/sessions"),
  getSessionStats: ():Promise<LessonSessionStat[]> => useLocalMock ? lessonKitMockApi.getSessionStats() : backendClient.get("/v2/sessions/stats"),
  createSession: (payload:Omit<LessonSession,"id"|"updatedAt">):Promise<LessonSession> => useLocalMock ? lessonKitMockApi.createSession(payload) : backendClient.post("/v2/sessions",payload),
  duplicateSession: (id:string):Promise<LessonSession> => useLocalMock ? lessonKitMockApi.duplicateSession(id) : backendClient.post(`/v2/sessions/${id}/duplicate`),
  getSessionSummary: (id:string):Promise<LessonSessionSummary> => useLocalMock ? lessonKitMockApi.getSessionSummary(id) : backendClient.get(`/v2/sessions/${id}/summary`),

  getMaterials: ():Promise<MaterialLibraryItem[]> => useLocalMock ? lessonKitMockApi.getMaterials() : backendClient.get("/v2/materials"),
  createMaterial: (payload:MaterialCreateInput):Promise<MaterialLibraryItem> => useLocalMock ? lessonKitMockApi.createMaterial(payload) : backendClient.post("/v2/materials",payload),
  duplicateMaterial: (id:string):Promise<MaterialLibraryItem> => useLocalMock ? lessonKitMockApi.duplicateMaterial(id) : backendClient.post(`/v2/materials/${id}/duplicate`),

  getRecentLessonsForLearner: (id:string):Promise<RecentLesson[]> => useLocalMock ? lessonKitMockApi.getRecentLessonsForLearner(id) : backendClient.get(`/v2/learners/${id}/recent-lessons`),
  getProgressSummaryForLearner: (id:string):Promise<LearnerProgressSummary> => useLocalMock ? lessonKitMockApi.getProgressSummaryForLearner(id) : backendClient.get(`/v2/learners/${id}/progress-summary`),
  getProgressSignalsForLearner: (id:string):Promise<ProgressSignal[]> => useLocalMock ? lessonKitMockApi.getProgressSignalsForLearner() : backendClient.get(`/v2/learners/${id}/progress-signals`),
  getProgressDataForLearner: (id:string):Promise<ProgressDataPoint[]> => useLocalMock ? lessonKitMockApi.getProgressDataForLearner(id) : backendClient.get(`/v2/learners/${id}/progress-data`),
  saveSessionDataRecord: (payload:SessionDataRecordInput):Promise<LearnerProgressSummary> => useLocalMock ? lessonKitMockApi.saveSessionDataRecord(payload) : backendClient.post("/v2/session-data",payload),
};
