export type WorkflowPage =
  | "home" | "uploadRecords" | "reviewLearnerExisting" | "reviewLearnerNew"
  | "planWithAIChat" | "lessonPackageReady" | "reviewPrintableContent"
  | "students" | "sessions" | "materials";

export type StudioPage = WorkflowPage;
export type WorkflowStep = "learner" | "records" | "profile" | "lesson" | "outputs";

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
}

export interface LearnerRecord {
  id: string;
  learnerId: string;
  fileName: string;
  fileType: string;
  status: "ready" | "reviewed" | "processing";
  uploadedAt: string;
  extractedText: string;
}

export interface LearnerProfileExtraction {
  learner: LearnerProfile;
  records: LearnerRecord[];
  insights: string[];
  analyzedRecordCount: number;
  status: "complete";
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
  field: keyof Pick<LessonDesignDraft, "responseLevel" | "scenarios" | "selectedMaterials" | "customNotes">;
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
}

export interface TeachingStep {
  id: string;
  title: string;
  description: string;
  duration: string;
  teacherAction: string;
  learnerAction: string;
}
export interface GeneratedMaterial {
  id: string;
  packageId: string;
  type: "visual_card" | "help_card" | "token_board" | "data_sheet" | "summary_template";
  title: string;
  status: "ready" | "approved";
  content: Record<string, string | number | string[]>;
  printLayout: { pageSize: "Letter" | "A4"; orientation: "portrait" | "landscape"; color: string };
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
