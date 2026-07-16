export type WorkflowPage =
  | "home" | "uploadRecords" | "reviewLearnerExisting" | "reviewLearnerNew"
  | "planWithAIChat" | "lessonPackageReady" | "reviewPrintableContent"
  | "modifyLessonContent"
  | "students" | "sessions" | "materials";

export type StudioPage = WorkflowPage | "developerAI";
export type WorkflowStep = "learner" | "records" | "profile" | "lesson" | "outputs";

export type GenerationStatus =
  | "ready"
  | "provider_failure"
  | "invalid_output"
  | "retry_required"
  | "local_mock";

export interface GenerationMetadata {
  status: GenerationStatus;
  provider: string;
  model: string;
  skillId: string;
  skillVersion: string;
  promptTemplateVersion: string;
  inputSchemaVersion: string;
  outputSchemaVersion: string;
  evaluatorVersion: string;
  generatedAt: string;
  outputSource: "provider" | "local_mock" | "mock_fallback";
  teacherReviewRequired: boolean;
}

export interface LearnerProfile {
  id: string;
  code: string;
  age: number;
  avatar: string;
  tags: string[];
  interests: string[];
  supportNeeds: string[];
  reinforcementPreferences: string[];
  communicationMode: string;
  attentionProfile: string;
  notes: string;
  strengths?: string[];
  sensoryPreferences?: string[];
  knownChallenges?: string[];
  promptingPreferences?: string[];
  currentGoals?: string[];
  readingLevel?: string;
  activityDurationPreference?: string;
  responseOptions?: string[];
  receptiveSupports?: string[];
  expressiveSupports?: string[];
  environmentalConsiderations?: string[];
  effectiveSupports?: string[];
  ineffectiveSupports?: string[];
  independenceProfile?: string;
  masteredSkills?: string[];
  emergingSkills?: string[];
  generalizationProfile?: string;
  breakPreferences?: string[];
  classroomBarriers?: string[];
  profileSignals?: ProfileSignal[];
  unknownFields?: string[];
  profileReviewStatus?: "draft" | "reviewed" | "confirmed";
  version?: number;
}

export interface ProfileSignal {
  id: string;
  category: string;
  label: string;
  summary: string;
  confidence: number;
  status: "suggested" | "confirmed" | "rejected";
  evidence: string;
  evidenceType:
    | "documented_fact"
    | "teacher_report"
    | "caregiver_report"
    | "observation"
    | "interpretation"
    | "contradiction"
    | "outdated_evidence"
    | "unknown";
  sourceRecordId?: string | null;
  sourceLocation?: string | null;
  evidenceDate?: string | null;
  contradictionState: "none" | "conflicting" | "resolved" | "outdated";
  suggestedProfileValue: string;
  teacherReviewState: "pending" | "confirmed" | "edited" | "rejected" | "unknown";
  evidenceFingerprint: string;
}

export interface LearnerRecord {
  id: string;
  learnerId: string;
  fileName: string;
  fileType: string;
  status:
    | "upload_pending"
    | "uploaded"
    | "validating"
    | "parsing"
    | "needs_ocr"
    | "needs_review"
    | "ready"
    | "reviewed"
    | "failed"
    | "deleted"
    | "processing";
  uploadedAt: string;
  extractedText: string;
  teacherCorrectedText?: string | null;
  effectiveText?: string;
  malwareScanStatus?: "not_configured" | "pending" | "clean" | "blocked" | "failed";
  parsingMessage?: string;
  deletionStatus?: "active" | "pending" | "failed" | "deleted";
  objectSizeBytes?: number | null;
  version?: number;
}

export interface RecordUploadIntent {
  record: LearnerRecord;
  uploadUrl: string;
  method: "PUT";
  requiredHeaders: Record<string, string>;
  expiresAt: string;
}

export interface RecordDeletionResult {
  recordId: string;
  status: "deleted" | "deletion_failed";
  retryable: boolean;
  message: string;
}

export interface LearnerProfileExtraction {
  learner: LearnerProfile;
  records: LearnerRecord[];
  insights: string[];
  analyzedRecordCount: number;
  status: "complete";
  profileSignals?: ProfileSignal[];
  unknownFields?: string[];
  generationStatus?: GenerationStatus | null;
  generationMetadata?: GenerationMetadata | null;
}

export interface LessonDesignDraft {
  id: string;
  learnerId: string;
  goalText: string;
  responseLevel: string;
  scenarios: string[];
  selectedMaterials: string[];
  theme: string;
  duration: string;
  customNotes: string;
  baseline?: string;
  observableResponse?: string;
  opportunities?: number;
  promptingStart?: string;
  promptingLimits?: string;
  reinforcementPlan?: string;
  errorCorrection?: string;
  dataCollection?: string;
  generalizationPlan?: string;
  teacherConstraints?: string;
  version?: number;
}

export interface AIMessage {
  id: string;
  role: "teacher" | "assistant";
  content: string;
  createdAt: string;
}

export type AIQuestionInputType = "single_select" | "multi_select" | "free_text" | "hybrid";
export interface AIQuestionOption {
  id: string;
  label: string;
  value: string;
  description: string;
  icon: string;
  recommended: boolean;
  source: "ai_generated" | "teacher_custom";
}
export interface AIQuestion {
  id: string;
  prompt: string;
  helperText: string;
  field: keyof Pick<
    LessonDesignDraft,
    | "goalText"
    | "baseline"
    | "responseLevel"
    | "scenarios"
    | "opportunities"
    | "duration"
    | "promptingStart"
    | "promptingLimits"
    | "reinforcementPlan"
    | "errorCorrection"
    | "selectedMaterials"
    | "dataCollection"
    | "generalizationPlan"
    | "teacherConstraints"
    | "customNotes"
  >;
  inputType: AIQuestionInputType;
  options: AIQuestionOption[];
  selectedOptionIds: string[];
  allowCustomAnswer: boolean;
  customAnswer: string;
  required: boolean;
  maxSelections?: number;
}
export interface AIChatState {
  conversationId: string;
  learnerId: string;
  messages: AIMessage[];
  questions: AIQuestion[];
  draft: LessonDesignDraft;
  canGenerate: boolean;
  generationStatus?: GenerationStatus | null;
  generationMetadata?: GenerationMetadata | null;
}

export interface TeachingStep {
  id: string;
  title: string;
  description: string;
  duration: string;
  teacherAction: string;
  learnerAction: string;
  phase?: string;
  teacherScript?: string | null;
  expectedLearnerResponse?: string;
  waitTime?: string;
  promptAction?: string;
  reinforcementAction?: string;
  errorCorrectionAction?: string;
  dataToRecord?: string[];
  transitionCue?: string;
  breakOption?: string | null;
}
export interface GeneratedMaterial {
  id: string;
  packageId: string;
  type:
    | "visual_card"
    | "choice_board"
    | "first_then_board"
    | "help_card"
    | "break_card"
    | "token_board"
    | "sorting_page"
    | "matching_page"
    | "scenario_cards"
    | "teacher_cue_card"
    | "data_sheet"
    | "session_summary"
    | "summary_template"
    | "handoff_note";
  title: string;
  status:
    | "generated"
    | "ready"
    | "validation_failed"
    | "safety_review_needed"
    | "teacher_review_needed"
    | "approved"
    | "rejected"
    | "superseded";
  content: Record<string, unknown>;
  printLayout: { pageSize: "Letter" | "A4"; orientation: "portrait" | "landscape"; color: string };
  generationStatus?: GenerationStatus | null;
  generationMetadata?: GenerationMetadata | null;
  specification?: MaterialSpecification | null;
  version?: number;
}
export interface MaterialSpecification {
  type: GeneratedMaterial["type"];
  purpose: string;
  audience: "learner" | "teacher" | "shared";
  pageSize: "Letter" | "A4";
  orientation: "portrait" | "landscape";
  margins: string;
  textLimit: string;
  imageNeed: "required" | "optional" | "none";
  contrastGuidance: string;
  printPreparation: string[];
  editableFields: string[];
  altText?: string | null;
  [key: string]: unknown;
}
export interface LessonPackage {
  id: string;
  learnerId: string;
  draftId: string;
  goal: string;
  duration: string;
  theme: string;
  lessonBrief: string;
  teachingFlow: TeachingStep[];
  materials: GeneratedMaterial[];
  summaryTemplate: string;
  safetyReview?: SafetyReview | null;
  standardsChecks?: StandardsCheck[];
  documentContent?: Record<string, unknown>;
  aiProvider?: string | null;
  fallbackUsed?: boolean | null;
  generationStatus?: GenerationStatus | null;
  generationMetadata?: GenerationMetadata | null;
  status?: "generated" | "validation_failed" | "safety_review_needed" | "teacher_review_needed" | "approved" | "rejected" | "superseded";
  targetSkill?: string;
  observableResponse?: string;
  baseline?: string;
  objective?: string;
  successCriterion?: string;
  responseModality?: string;
  preparationChecklist?: string[];
  promptingPlan?: Record<string, unknown> | null;
  reinforcementPlan?: Record<string, unknown> | null;
  errorCorrectionPlan?: Record<string, unknown> | null;
  generalizationPlan?: Record<string, unknown> | null;
  dataSheetSpecification?: Record<string, unknown> | null;
  teacherAdaptation?: Record<string, unknown> | null;
  version?: number;
}
export interface LessonPackageUpdateInput {
  lessonBrief?: string;
  summaryTemplate?: string;
  teachingFlow?: TeachingStep[];
  documentContent?: Record<string, unknown>;
  expectedVersion?: number;
}
export interface SafetyReview {
  status: "pass" | "needs_review" | "blocked";
  riskLevel: "low" | "medium" | "high";
  issues: string[];
  recommendedEdits: string[];
  appliedEdits: string[];
}
export interface StandardsCheck {
  id: string;
  skillId: string;
  label: string;
  description: string;
  severity: "low" | "medium" | "high";
  status: "pass" | "needs_review" | "blocked" | "not_applicable";
  recommendation: string;
  version?: string;
  evidenceLocation?: string;
  explanation?: string;
  recommendedEdit?: string;
}

export interface LessonPackageVersion {
  packageId: string;
  version: number;
  status: string;
  snapshot: LessonPackage;
}

export interface LessonPackageVersionComparison {
  packageId: string;
  fromVersion: number;
  toVersion: number;
  changedFields: string[];
  fromSnapshot: LessonPackage;
  toSnapshot: LessonPackage;
}
export interface LessonSession {
  id: string;
  learnerId: string;
  goal: string;
  status: "planned" | "in_progress" | "completed" | "draft";
  updatedAt: string;
}
export interface LessonSessionStat {
  status: LessonSession["status"];
  label: string;
  count: number;
  helperText: string;
}
export interface LessonSessionSummary extends LessonSession {
  overview: string;
  highlights: string[];
  nextSteps: string[];
}
export interface RecentLesson {
  id: string;
  learnerId: string;
  title: string;
  date: string;
}
export interface MaterialLibraryItem {
  id: string;
  title: string;
  type: string;
  thumbnailLabel: string;
  source: "generated" | "template";
  reusable: boolean;
  createdAt: string;
}
export interface LearnerProgressSummary {
  learnerId: string;
  currentGoal: string;
  accuracyPercent: number;
  independencePercent: number;
  sessionsPracticed: number;
  currentPromptLevel: string;
  trend: string;
  message: string;
}
export interface ProgressSignal {
  id: string;
  type: string;
  label: string;
  description: string;
  status: "improving" | "stable" | "emerging" | "needs_support";
}
export interface ProgressDataPoint {
  id: string;
  learnerId: string;
  sessionDate: string;
  goal: string;
  opportunities: number;
  accuracyPercent: number;
  independencePercent: number;
  promptLevel: string;
  signalsHighlighted: string[];
  teacherNotes: string;
}
export interface ExportJob {
  exportId: string;
  learnerId: string;
  packageId?: string | null;
  status: "pending" | "processing" | "completed" | "failed" | "expired" | "deleted";
  format: "pdf" | "docx" | "pptx" | "zip";
  progressPercent: number;
  requestedAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
  expiresAt?: string | null;
  fileName: string;
  fileSizeBytes?: number | null;
  downloadUrl?: string | null;
  errorCode?: string | null;
  message: string;
  manifest: string[];
  downloadCount: number;
  lastDownloadedAt?: string | null;
  version: number;
}

export interface HandoffSectionSelection {
  learnerOverview: boolean;
  teachingStrategies: boolean;
  activeGoals: boolean;
  progress: boolean;
  recentSessions: boolean;
  lessonPackages: boolean;
  approvedMaterials: boolean;
  transitionNotes: boolean;
}

export interface TeacherHandoffExportInput {
  sections: HandoffSectionSelection;
  dateRange: { startDate?: string | null; endDate?: string | null };
  sessionIds: string[];
  packageIds: string[];
  materialIds: string[];
  transitionNotes: string;
  includePrintableMaterials: boolean;
  pageSize: "Letter" | "A4";
  orientation: "portrait";
  reviewedConfirmation: true;
}

export interface HandoffExportDownload {
  exportId: string;
  downloadUrl: string;
  expiresAt: string;
}
export type MaterialQuickEditAction = "simplify_wording" | "regenerate_artwork" | "adjust_reward";

export interface AIProviderStatus {
  provider: string;
  textModel: string;
  imageModel: string;
  hasApiKey: boolean;
}

export interface AILessonQuestionsTestResult {
  provider: string;
  model: string;
  fallbackUsed: boolean;
  questions: AIQuestion[];
  draft: LessonDesignDraft;
}

export interface AIImageGenerationInput {
  learnerId: string;
  materialType: string;
  prompt: string;
  style?: string;
  size?: string;
}

export interface AIImageGenerationResult {
  imageId: string;
  status: "ready" | "mock";
  provider: "mock" | "openai";
  model: string;
  imageUrl?: string | null;
  imageBase64?: string | null;
  promptUsed: string;
  fallbackUsed: boolean;
}
