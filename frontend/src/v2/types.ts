export type WorkflowPage =
  | "home"
  | "uploadRecords"
  | "reviewLearnerExisting"
  | "reviewLearnerNew"
  | "planWithAIChat"
  | "lessonPackageReady"
  | "reviewPrintableContent"
  | "modifyLessonContent"
  | "students"
  | "sessions"
  | "materials";

export type StudioPage = WorkflowPage | "developerAI";
export type WorkflowStep =
  | "learner"
  | "records"
  | "profile"
  | "lesson"
  | "outputs";

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

export type GenerationWorkStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "failed"
  | "fallback"
  | "skipped";
export interface GenerationStageState {
  stage: string;
  status: GenerationWorkStatus;
  attempts: number;
  message: string;
  failureCategory?: string | null;
  recoverable: boolean;
  updatedAt?: string | null;
}
export interface GenerationVisualState {
  visualId: string;
  semanticKey: string;
  required: boolean;
  status: GenerationWorkStatus;
  attempts: number;
  failureCategory?: string | null;
  recoverable: boolean;
}
export interface GenerationArtifactState {
  artifactId: string;
  materialType: string;
  required: boolean;
  status: GenerationWorkStatus;
  attempts: number;
  failureCategory?: string | null;
  recoverable: boolean;
  visuals: GenerationVisualState[];
}
export interface GenerationJob {
  jobId: string;
  learnerId: string;
  draftId: string;
  lessonSpecId: string;
  lessonSpecRevision: number;
  packageContentPlanRevision: number;
  packageId?: string | null;
  requestedArtifactIds: string[];
  artifacts: GenerationArtifactState[];
  stages: GenerationStageState[];
  status:
    | "pending"
    | "in_progress"
    | "partially_complete"
    | "completed"
    | "failed";
  attempts: number;
  provider: string;
  model: string;
  failureCategory?: string | null;
  recoverable: boolean;
  lastUpdatedAt: string;
  completedAt?: string | null;
  cost: {
    estimatedTokens: number;
    estimatedVisualCount: number;
    actualVisualCount: number;
    estimatedCost: number;
    actualCost?: number | null;
    currency: "USD";
  };
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
  normalizedProfile?: CanonicalLearnerProfile | null;
  profileSignals?: ProfileSignal[];
  unknownFields?: string[];
  profileReviewStatus?: "draft" | "reviewed" | "confirmed";
  version?: number;
}

export type ProfileFactorCategory =
  | "communication"
  | "receptive_language"
  | "learning_strength"
  | "attention"
  | "sensory"
  | "visual_access"
  | "motor_access"
  | "current_interest"
  | "historical_interest"
  | "reinforcement"
  | "transition"
  | "regulation"
  | "prompting"
  | "error_correction"
  | "generalization"
  | "language"
  | "safety"
  | "prohibited_item"
  | "unresolved_assumption"
  | "other";
export type ProfileFactorStatus =
  | "confirmed_current"
  | "teacher_confirmed"
  | "teacher_edited"
  | "historical"
  | "unconfirmed"
  | "not_approved"
  | "not_meaningful"
  | "omitted"
  | "derived"
  | "rejected";
export interface ProfileFactor {
  id: string;
  category: ProfileFactorCategory;
  label: string;
  value: string;
  status: ProfileFactorStatus;
  confidence: number;
  sourceEvidence: string;
  sourceRecordId?: string | null;
  instructionalImplication: string;
  generationConstraints: string[];
  teacherReviewed: boolean;
}
export interface CanonicalLearnerProfile {
  learnerId: string;
  age: number;
  factors: ProfileFactor[];
  confirmedFactorIds: string[];
  unconfirmedFactorIds: string[];
  historicalFactorIds: string[];
  excludedFactorIds: string[];
  blockingIssues: string[];
  summary: {
    communication: string;
    supports: string[];
    currentInterests: string[];
    learningFormat: string;
    keyTeachingNotes: string[];
  };
}

export interface InstructionalConstraintSnapshot {
  learnerId: string;
  profileRevision: string;
  generatedAt: string;
  communication: {
    acceptedModes: string[];
    responseOptions: string[];
    processingTimeSeconds: number | null;
    accessRequirements: string[];
    invalidRequirements: string[];
  };
  instruction: {
    effectiveSupports: string[];
    ineffectiveSupports: string[];
    promptHierarchy: string[];
    prohibitedPrompting: string[];
    errorCorrection: string[];
    activityDurationMinutes: number | null;
    visibleEndpointRequired: boolean;
  };
  visualAndSensoryAccess: {
    maximumPrimaryChoices: number | null;
    layoutRequirements: string[];
    preferredOrganizingFeatures: string[];
    prohibitedVisualFeatures: string[];
    prohibitedAudioFeatures: string[];
    motorAccessAlternatives: string[];
  };
  engagement: {
    currentInterests: string[];
    historicalInterests: string[];
    effectiveReinforcers: string[];
    notApprovedReinforcers: string[];
    notMeaningfulReinforcers: string[];
  };
  transitionsAndBreaks: {
    difficultTransitions: string[];
    transitionWarnings: string[];
    firstThenRequired: boolean;
    breakRequestOptions: string[];
    breakDurationMinutes: number | null;
    returnSupports: string[];
  };
  generalization: {
    required: boolean;
    contexts: string[];
    people: string[];
    materials: string[];
  };
  safetyConstraints: string[];
  unresolvedAssumptions: string[];
  excludedItems: string[];
  profileFactorIds: string[];
}

export interface LessonSpecFieldResolution {
  fieldPath: string;
  source:
    | "teacher_authored"
    | "teacher_selected"
    | "ai_recommended"
    | "profile_derived"
    | "explicit_default"
    | "legacy_adapter";
  reason: string;
  requiresTeacherConfirmation: boolean;
}
export interface LessonSpec {
  id: string;
  schemaVersion: 1;
  revision: number;
  learnerId: string;
  profileRevision: string;
  teacherRequest: string;
  teacherEdits: string[];
  goal: {
    displayText: string;
    observableBehavior: string;
    conditions: string;
    acceptedResponseModes: string[];
    independenceDefinition: string;
    successCriterion: {
      requiredSuccessfulOpportunities: number | null;
      totalOpportunities: number | null;
      maximumPromptLevel: string;
      requiredContexts: number;
    } | null;
  };
  duration: { totalMinutes: number; maximumActivityBlockMinutes: number };
  contexts: Array<{
    id: string;
    label: string;
    setting: string;
    transitionFrom: string;
    transitionTo: string;
    generalizationDimension: "activity" | "person" | "setting" | "material";
  }>;
  communicationPlan: {
    acceptedModes: string[];
    processingTimeSeconds: number | null;
    responseValidationRules: string[];
  };
  promptingPlan: {
    sequence: string[];
    prohibitedPrompts: string[];
    fadeRule: string;
    waitTimeSeconds: number | null;
    teacherOverride: string;
  };
  errorCorrectionPlan: { strategies: string[] };
  reinforcementPlan: {
    tokenCount: number | null;
    tokenTheme: string;
    earnedReward: string;
    rewardDurationMinutes: number | null;
    specificPraise: string;
    excludedReinforcers: string[];
  };
  transitionPlan: {
    warning: string;
    firstThenRequired: boolean;
    breakRequest: string;
    breakDurationMinutes: number | null;
    returnSupport: string;
  };
  accessPlan: {
    maximumPrimaryVisualChoices: number | null;
    layoutRequirements: string[];
    prohibitedVisualFeatures: string[];
    prohibitedAudioFeatures: string[];
    motorAccessAlternatives: string[];
  };
  generalizationPlan: {
    required: boolean;
    contexts: LessonSpec["contexts"];
    dimensions: Array<"activity" | "person" | "setting" | "material">;
  };
  dataPlan: {
    measures: string[];
    trialDefinition: string;
    independenceDefinition: string;
    promptLevels: string[];
  };
  materialRequests: Array<{
    requestId: string;
    materialType: string;
    displayLabel: string;
    instructionalPurpose: string;
    required: boolean;
    supported: boolean;
    unsupportedReason: string | null;
    profileFactorIds: string[];
    origin: "newly_generated" | "library_reused" | "future_unsupported";
    libraryMaterialId: string | null;
    libraryMaterialVersion: number | null;
    configuration: Array<{
      key: string;
      value: string | number | boolean | null;
    }>;
  }>;
  safetyConstraints: string[];
  personalizationThemes: string[];
  unresolvedAssumptions: Array<{
    text: string;
    blocking: boolean;
    profileFactorId: string | null;
  }>;
  profileFactorIds: string[];
  decisionIds: string[];
  provenance: {
    teacherAuthoredFields: string[];
    teacherSelectedFields: string[];
    aiRecommendedFields: string[];
    derivedFields: string[];
    defaultedFields: string[];
    fieldResolutions: LessonSpecFieldResolution[];
  };
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
  teacherReviewState:
    | "pending"
    | "confirmed"
    | "edited"
    | "rejected"
    | "unknown";
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
  malwareScanStatus?:
    | "not_configured"
    | "pending"
    | "clean"
    | "blocked"
    | "failed";
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
  instructionalConstraintSnapshot?: InstructionalConstraintSnapshot | null;
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
  profileRevision?: string;
  instructionalConstraintSnapshot?: InstructionalConstraintSnapshot | null;
  profileStale?: boolean;
  profileStaleMessage?: string;
  teacherRequest?: string;
  decisions?: TeacherDecision[];
  structuredChanges?: StructuredTeacherChange[];
  supplementalSuggestions?: AIQuestion[];
  packageContentPlan?: PackageContentPlan | null;
  version?: number;
}

export type TeacherDecisionField =
  | "goal"
  | "practice_contexts"
  | "material_requests";
export interface TeacherDecision {
  id: string;
  field: TeacherDecisionField;
  source:
    | "ai_recommended"
    | "teacher_selected"
    | "teacher_authored"
    | "teacher_edited";
  optionIds: string[];
  profileFactorIds: string[];
  value: Record<string, unknown>;
  reason: string;
  affects: string[];
  assumptions: string[];
  confirmedAt: string;
  confirmedBy: "teacher";
  revision: number;
}
export interface StructuredTeacherChange {
  id: string;
  changeType:
    | "goal_clarification"
    | "context_change"
    | "material_change"
    | "duration_change"
    | "reinforcement_change"
    | "prompting_change"
    | "general_note";
  originalMessage: string;
  value: string;
  createdAt: string;
}

export interface AIMessage {
  id: string;
  role: "teacher" | "assistant";
  content: string;
  createdAt: string;
}

export type AIQuestionInputType =
  | "single_select"
  | "multi_select"
  | "free_text"
  | "hybrid";
export interface AIQuestionOption {
  id: string;
  label: string;
  value: string;
  description: string;
  icon: string;
  recommended: boolean;
  source: "ai_generated" | "teacher_custom";
  decisionField?: TeacherDecisionField | null;
  reason?: string;
  profileFactorIds?: string[];
  affects?: string[];
  assumptions?: string[];
  suggestionStatus?:
    | "recommended"
    | "optional"
    | "requires_confirmation"
    | "blocked";
  supported?: boolean;
  unsupportedReason?: string | null;
  savedForFuture?: boolean;
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

export interface PackageCoreMaterial {
  materialRequestId: string;
  materialType: string;
  reason: string;
  decisionIds: string[];
  profileFactorIds: string[];
}
export interface PackageRequiredCompanion {
  materialType: string;
  reasonRequired: string;
  dependsOnMaterialTypes: string[];
  goalRequirement: string;
  profileFactorIds: string[];
  canTeacherRemove: boolean;
  removalWarning?: string | null;
  included: boolean;
}
export interface PackageOptionalEnrichment {
  materialType: string;
  reasonSuggested: string;
  profileFactorIds: string[];
  defaultIncluded: boolean;
  estimatedPages: number;
}
export interface PackageExcludedMaterial {
  materialType: string;
  reasonExcluded: string;
  profileFactorIds: string[];
}
export interface PackageContentPlan {
  id: string;
  lessonSpecId: string;
  lessonSpecRevision: number;
  schemaVersion: 1;
  teacherSelectedCore: PackageCoreMaterial[];
  requiredCompanions: PackageRequiredCompanion[];
  optionalEnrichments: PackageOptionalEnrichment[];
  excludedMaterials: PackageExcludedMaterial[];
  estimatedArtifactCount: number;
  estimatedPageCount: number;
  unresolvedDependencies: string[];
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
    | "blue_line_activity"
    | "visual_timer"
    | "quantity_cards"
    | "number_cards"
    | "visual_card"
    | "choice_board"
    | "first_then_board"
    | "help_card"
    | "break_card"
    | "token_board"
    | "sorting_page"
    | "matching_page"
    | "scenario_cards"
    | "sequence_cards"
    | "social_narrative"
    | "core_word_board"
    | "visual_schedule"
    | "task_analysis_cards"
    | "emotion_scale"
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
  printLayout: {
    pageSize: "Letter" | "A4";
    orientation: "portrait" | "landscape";
    color: string;
  };
  generationStatus?: GenerationStatus | null;
  generationMetadata?: GenerationMetadata | null;
  materialSchemaVersion?: 0 | 1;
  materialSpec?: MaterialSpec | null;
  visualAssetPlan?: VisualAssetPlan | null;
  specification?: MaterialSpecification | null;
  version?: number;
}
export type VisualAssetRole =
  | "task_item"
  | "scenario"
  | "choice"
  | "first"
  | "then"
  | "token"
  | "reward"
  | "communication_symbol"
  | "timer_state"
  | "example"
  | "teacher_reference"
  | "decorative";
export type VisualGenerationMethod =
  | "deterministic_svg"
  | "icon_library"
  | "approved_asset"
  | "ai_generated"
  | "teacher_uploaded";
export interface VisualAssetPlanItem {
  id: string;
  role: VisualAssetRole;
  semanticKey: string;
  instructionalPurpose: string;
  required: boolean;
  generationMethod: VisualGenerationMethod;
  prompt?: string | null;
  negativePrompt?: string | null;
  altText: string;
  visibleLabel: string;
  profileFactorIds: string[];
  designConstraints: Record<string, unknown>;
  status: "planned" | "generating" | "ready" | "failed" | "needs_review";
  assetId?: string | null;
  fallbackAssetId?: string | null;
  reviewStatus: "unreviewed" | "approved" | "rejected";
}
export interface VisualAssetPlan {
  materialId: string;
  materialRevision: number;
  schemaVersion: 1;
  visualItems: VisualAssetPlanItem[];
  minimumRequiredVisuals: number;
  maximumAllowedVisuals?: number | null;
  duplicatePolicy: string;
  textInImageAllowed: false;
}
export interface MaterialValidationIssue {
  fieldPath: string;
  code: string;
  message: string;
  remediation: string;
}
export interface MaterialValidationResult {
  status: "pending" | "passed" | "failed";
  issues: MaterialValidationIssue[];
}
export interface StructuredSafetyIssue {
  id: string;
  scope: "package" | "material";
  materialId?: string | null;
  category:
    | "access"
    | "coercion"
    | "prompting"
    | "reinforcement"
    | "emotional_safety"
    | "privacy"
    | "unsupported_assumption"
    | "semantic_inconsistency"
    | "other";
  severity: "warning" | "blocking";
  message: string;
  profileFactorIds: string[];
  lessonSpecPath: string;
  materialSpecPath: string;
  suggestedCorrection: string;
  detectedAtRevision: number;
  resolvedAtRevision?: number | null;
  resolutionSource?: "teacher_edit" | "ai_repair" | "regeneration" | null;
}
export interface MaterialSafetyValidationResult {
  status: "pending" | "passed" | "failed";
  issues: StructuredSafetyIssue[];
}
export interface MaterialDesignConstraints {
  pageSize: "Letter" | "A4";
  orientation: "portrait" | "landscape";
  maximumPrimaryChoices?: number | null;
  layoutRequirements: string[];
  prohibitedVisualFeatures: string[];
  prohibitedAudioFeatures: string[];
  motorAccessRequirements: string[];
  minimumTouchTarget?: string | null;
}
export interface MaterialSpecBase<TType extends string, TContent> {
  id: string;
  schemaVersion: 1;
  revision: number;
  packageId: string;
  lessonSpecId: string;
  lessonSpecRevision: number;
  learnerId: string;
  artifactType: TType;
  title: string;
  instructionalPurpose: string;
  profileFactorIds: string[];
  decisionIds: string[];
  sourceMaterialId?: string | null;
  content: TContent;
  designConstraints: MaterialDesignConstraints;
  visualAssetRequests: Array<{
    id: string;
    purpose: string;
    description: string;
    altText: string;
    status: "not_requested" | "requested" | "ready" | "failed";
  }>;
  teacherEditableFields: string[];
  repairAttempts: number;
  repairStatus: "not_needed" | "repaired" | "exhausted";
  semanticValidation: MaterialValidationResult;
  safetyValidation: MaterialSafetyValidationResult;
  approval: {
    status: "not_reviewed" | "reviewed" | "approved" | "rejected";
    reviewedRevision?: number | null;
    approvedRevision?: number | null;
  };
}
export type PersonalizedInstructionalActivitySpec = MaterialSpecBase<
  "personalized_instructional_activity",
  {
    taskName: string;
    instructionalObjective: string;
    learnerAction: string;
    teacherSetup: string[];
    requiredComponents: string[];
    responseMethod: string[];
    numberOfTrialsOrItems: number;
    completionCriterion: string;
    answerKeyOrExpectedSequence: string[];
    generalizationExtension: string;
    motorAccessRequirements: string[];
    visualAccessRequirements: string[];
  }
>;
export type CommunicationCardSpec = MaterialSpecBase<
  "communication_card",
  {
    exactCommunicationPhrase: string;
    acceptedCommunicationModes: string[];
    cardPurpose: string;
    symbolDescription: string;
    alternateText: string;
    touchTargetRequirement: string;
    prohibitedImagery: string[];
    teacherResponseAfterUse: string;
  }
>;
export type FirstThenBoardSpec = MaterialSpecBase<
  "first_then_board",
  {
    firstTask: string;
    thenOutcome: string;
    exactDisplayText: string;
    firstSymbolDescription: string;
    thenSymbolDescription: string;
    completionCriterion: string;
    context: string;
    returnOrTransitionInstruction: string;
  }
>;
export type TokenBoardSpec = MaterialSpecBase<
  "token_board",
  {
    exactTokenCount: number;
    tokenSymbolOrTheme: string;
    earnedReward: string;
    rewardDurationMinutes?: number | null;
    picturedRewardDescription: string;
    specificPraise: string;
    deliveryInstructions: string;
    prohibitedRewardSubstitutions: string[];
  }
>;
export type VisualTimerSpec = MaterialSpecBase<
  "visual_timer",
  {
    durationMinutes: number;
    startLabel: string;
    endLabel: string;
    displayFormat: string;
    teacherInstruction: string;
    audioAllowed: boolean;
    returnToTaskCue: string;
  }
>;
export interface ScenarioCardItem {
  id: string;
  context: string;
  triggerOrTransition: string;
  learnerOpportunity: string;
  expectedResponse: string;
  acceptedModalities: string[];
  promptSequence: string[];
  consequenceOrReinforcement: string;
  generalizationDimension: "activity" | "person" | "setting" | "material";
  visualCue: string;
  teacherWording: string;
  waitTimeSeconds: number;
  breakOutcome: string;
  returnSupport: string;
  generalizationLabel: string;
}
export type ScenarioCardsSpec = MaterialSpecBase<
  "scenario_cards",
  { scenarios: ScenarioCardItem[] }
>;
export type ChoiceBoardSpec = MaterialSpecBase<
  "choice_board",
  {
    promptOrQuestion: string;
    choices: Array<{ id: string; label: string; visualDescription: string }>;
    responseMethod: string[];
    teacherActionAfterSelection: string;
  }
>;
export type RegulationScaleSpec = MaterialSpecBase<
  "regulation_scale",
  {
    levels: Array<{
      order: number;
      label: string;
      observableIndicators: string[];
      matchingSupportOption: string;
    }>;
    nonjudgmentalLanguage: string;
  }
>;
export type GoalSpecificDataSheetSpec = MaterialSpecBase<
  "goal_specific_data_sheet",
  {
    operationalizedTargetBehavior: string;
    trialDefinition: string;
    exactColumns: string[];
    responseCoding: string[];
    promptLevelDefinitions: string[];
    independenceRule: string;
    summaryCalculationsOrTotals: string[];
  }
>;
export type LessonSummarySpec = MaterialSpecBase<
  "lesson_summary",
  {
    goal: string;
    observableTarget: string;
    contextsPracticed: string[];
    responseModesUsed: string[];
    opportunityTotal: number;
    successfulOpportunityTotal: number;
    independenceSummary: string;
    promptsUsed: string[];
    reinforcementDelivered: string;
    regulationAndBreakNotes: string;
    nextStep: string;
    reportingFields: string[];
  }
>;
export type MaterialSpec =
  | PersonalizedInstructionalActivitySpec
  | CommunicationCardSpec
  | FirstThenBoardSpec
  | TokenBoardSpec
  | VisualTimerSpec
  | ScenarioCardsSpec
  | ChoiceBoardSpec
  | RegulationScaleSpec
  | GoalSpecificDataSheetSpec
  | LessonSummarySpec;
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
  requiredContent?: string[];
  professionalRules?: string[];
  teacherDirections?: string[];
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
  qualityScore?: LessonPackageQualityScore | null;
  documentContent?: Record<string, unknown>;
  aiProvider?: string | null;
  fallbackUsed?: boolean | null;
  generationStatus?: GenerationStatus | null;
  generationMetadata?: GenerationMetadata | null;
  profileRevision?: string;
  instructionalConstraintSnapshot?: InstructionalConstraintSnapshot | null;
  teacherDecisions?: TeacherDecision[];
  staleOutputs?: string[];
  lessonSpec?: LessonSpec | null;
  packageContentPlan?: PackageContentPlan | null;
  validationPolicy?: "legacy_compatibility" | "strict_v1";
  validationStatus?: "pending" | "passed" | "failed";
  validatedRevision?: number | null;
  validatedLessonSpecRevision?: number | null;
  status?:
    | "generated"
    | "validation_failed"
    | "safety_review_needed"
    | "teacher_review_needed"
    | "approved"
    | "rejected"
    | "superseded";
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
  structuredIssues: StructuredSafetyIssue[];
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

export interface QualityScoreItem {
  id: string;
  label: string;
  score: 0 | 1 | 2;
  maxScore: 2;
  status: "pass" | "needs_review" | "blocked";
  explanation: string;
  evidence: string[];
  issues: string[];
  recommendedEdits: string[];
  critical: boolean;
}

export interface LessonPackageQualityScore {
  totalScore: number;
  maxScore: 16;
  percentage: number;
  overallStatus: "pass" | "needs_review" | "blocked";
  items: QualityScoreItem[];
  evaluatorVersion: string;
  teacherReviewRequired: boolean;
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
  lessonPackageId?: string | null;
  lessonPackageRevision?: number | null;
  lessonSpecId?: string | null;
  goalId?: string | null;
  goalRevision?: number | null;
  operationalizedGoal?: string;
  startedAt?: string | null;
  completedAt?: string | null;
  sessionUseSnapshotId?: string | null;
  draftStatus?: SessionRunDraftStatus | null;
  draftVersion?: number | null;
  version?: number;
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
export type SessionTrialOutcome =
  | "independent_success"
  | "prompted_success"
  | "incorrect"
  | "no_response"
  | "not_observed_unsuccessful"
  | "break_honored"
  | "cancelled";
export type SessionResponseMode =
  | "speech"
  | "AAC"
  | "pointing"
  | "other"
  | "none";
export type SessionPromptLevel =
  | "independent"
  | "gesture"
  | "visual"
  | "model"
  | "brief_verbal"
  | "other";
export interface SessionUseContext {
  id: string;
  label: string;
  setting: string;
  generalizationDimension?: "activity" | "person" | "setting" | "material";
  transitionFrom?: string;
  transitionTo?: string;
}
export interface SessionUseSnapshot {
  id: string;
  sessionId: string;
  learnerId: string;
  goalId: string;
  goalRevision: number;
  goalComparisonKey: string;
  operationalizedGoal: string;
  lessonSpecId: string;
  lessonSpecRevision: number;
  packageId: string;
  packageRevision: number;
  materialRevisions: Record<string, number>;
  materialLabels: Record<string, string>;
  visualPlanRevisions: Array<{ planId: string; materialId: string; revision: number }>;
  pdfArtifact?: {
    exportId: string;
    manifestVersion: number;
    rendererVersion: string;
    printPreset: PrintPreset;
    pageSize: "LETTER" | "A4";
    textProfile: PrintTextProfile;
    sha256: string;
  } | null;
  teacherConfirmedContexts: SessionUseContext[];
  acceptedResponseModes: string[];
  promptLevelDefinitions: string[];
  independenceDefinition: string;
  dataMeasures: string[];
  plannedOpportunities: number;
  startedAt: string;
  startedByTeacher: string;
  idempotencyKey: string;
}
export interface SessionRunDraftTrial {
  trialId: string;
  opportunityNumber: number;
  contextId: string | null;
  contextLabel: string | null;
  valid: boolean | null;
  outcome: SessionTrialOutcome | null;
  responseMode: SessionResponseMode | null;
  promptLevel: SessionPromptLevel | null;
  latencySeconds: number | null;
  breakRequested: boolean | null;
  breakDelivered: boolean | null;
  returnedAfterBreak: boolean | null;
  materialIdsUsed: string[];
  note: string;
}
export type SessionRunDraftStatus =
  | "in_progress"
  | "ready_for_closeout"
  | "completed"
  | "discarded";
export interface SessionRunDraft {
  id: string;
  sessionId: string;
  snapshotId: string;
  status: SessionRunDraftStatus;
  trials: SessionRunDraftTrial[];
  generalization: { status: "observed" | "not_observed" | "not_attempted" | null; people: string[]; settings: string[]; materials: string[] };
  helpfulMaterialIds: string[];
  unhelpfulMaterialIds: string[];
  observations: {
    engagementLevel: number | null;
    regulationLevel: number | null;
    teacherNotes: string;
    rawCountsConfirmed: boolean;
  };
  activeTrialNumber: number;
  lastSavedAt: string;
  version: number;
}
export interface SessionRunState {
  snapshot: SessionUseSnapshot;
  draft: SessionRunDraft;
  packageChanged: boolean;
  packageChangeWarning: string | null;
}
export interface StartSessionInput {
  idempotencyKey: string;
  startedByTeacher: string;
  expectedPackageRevision: number;
  contextIds: string[];
  pdfExportId?: string | null;
  printPreset?: PrintPreset | null;
}
export interface PatchSessionRunDraftInput {
  expectedVersion: number;
  idempotencyKey: string;
  status?: "in_progress" | "ready_for_closeout";
  trials?: SessionRunDraftTrial[];
  generalization?: SessionRunDraft["generalization"];
  helpfulMaterialIds?: string[];
  unhelpfulMaterialIds?: string[];
  observations?: SessionRunDraft["observations"];
  activeTrialNumber?: number;
}
export interface SessionTrialObservation {
  trialId: string;
  opportunityNumber: number;
  contextId: string;
  contextLabel: string;
  valid: boolean;
  contextDimension?: "activity" | "person" | "setting" | "material" | null;
  contextSetting?: string;
  transitionFrom?: string;
  transitionTo?: string;
  outcome: SessionTrialOutcome;
  responseMode: SessionResponseMode;
  promptLevel: SessionPromptLevel | null;
  latencySeconds: number | null;
  breakRequested: boolean;
  breakDelivered: boolean;
  returnedAfterBreak: boolean | null;
  materialIdsUsed: string[];
  note: string;
}
export interface SessionCompletionTemplate {
  sessionId: string;
  learnerId: string;
  lessonPackageId: string;
  lessonPackageRevision: number;
  lessonSpecId: string;
  goalId: string;
  goalRevision: number;
  operationalizedGoal: string;
  plannedOpportunities: number;
  contexts: Array<{ id: string; label: string; setting: string }>;
  materialIds: string[];
  materialLabels: Record<string, string>;
  dataSheetColumns: string[];
}
export interface CompleteSessionInput {
  expectedLessonPackageId: string;
  expectedLessonSpecId: string;
  expectedGoalId: string;
  startedAt: string;
  completedAt: string;
  trials: SessionTrialObservation[];
  generalization: {
    status: "observed" | "not_observed" | "not_attempted";
    people: string[];
    settings: string[];
    materials: string[];
  };
  helpfulMaterialIds: string[];
  unhelpfulMaterialIds: string[];
  observations: {
    engagementLevel: number | null;
    regulationLevel: number | null;
    teacherNotes: string;
    rawCountsConfirmed: boolean;
  };
}
export interface SessionOutcome {
  id: string;
  sessionId: string;
  learnerId: string;
  lessonPackageId: string;
  lessonPackageRevision: number;
  lessonSpecId: string;
  goalId: string;
  goalRevision: number;
  operationalizedGoal: string;
  startedAt: string;
  completedAt: string;
  opportunities: { planned: number; valid: number; cancelled: number };
  responses: {
    independentSuccessful: number;
    promptedSuccessful: number;
    incorrect: number;
    noResponse: number;
    notObservedOrUnsuccessful: number;
    speechSuccessful: number;
    aacSuccessful: number;
    pointingSuccessful: number;
    otherSuccessful: number;
    breakOrStopHonored: number;
  };
  prompting: {
    promptLevelCounts: Record<string, number>;
    averagePromptLevel: number | null;
    lowestPromptLevel: SessionPromptLevel | null;
    highestPromptLevel: SessionPromptLevel | null;
  };
  latency: {
    recordedTrialCount: number;
    averageSeconds: number | null;
    medianSeconds: number | null;
  };
  generalization: {
    status: "observed" | "not_observed" | "not_attempted";
    contextsAttempted: string[];
    contextsSuccessful: string[];
    people: string[];
    settings: string[];
    materials: string[];
  };
  breakAndReturn: {
    breakRequests: number;
    breaksDelivered: number;
    returnedAfterBreak: number;
  };
  materials: {
    usedMaterialIds: string[];
    unusedMaterialIds: string[];
    helpfulMaterialIds: string[];
    unhelpfulMaterialIds: string[];
  };
  observations: {
    engagementLevel: number | null;
    regulationLevel: number | null;
    teacherNotes: string;
    rawCountsConfirmed: boolean;
  };
  trials: SessionTrialObservation[];
  createdAt: string;
  version: number;
}
export type GoalProgressMetric =
  | "independent_success_rate"
  | "prompt_independence_display_score"
  | "average_response_latency"
  | "generalization_context_count"
  | "return_after_break_rate";
export interface GoalProgressPointDetails {
  operationalizedGoal: string;
  independentSuccessfulCount?: number;
  promptedSuccessfulCount: number;
  responseModeCounts: Record<string, number>;
  promptLevelCounts: Record<string, number>;
  averagePromptLevel: number | null;
  averageLatencySeconds: number | null;
  breakRequestCount: number;
  breaksDeliveredCount: number;
  returnedAfterBreakCount: number;
  materialIdsUsed: string[];
  teacherNotes: string;
}
export interface GoalProgressPoint {
  sessionId: string;
  completedAt: string;
  goalId: string;
  goalRevision: number;
  metric: GoalProgressMetric;
  value: number;
  validOpportunityCount: number;
  numeratorCount: number;
  confidence: "normal" | "low";
  confidenceReason: string | null;
  lessonPackageId: string;
  lessonPackageRevision: number;
  contextsAttempted: string[];
  annotation: string | null;
  details: GoalProgressPointDetails;
}
export interface GoalContextSummary {
  contextKey: string;
  contextId: string;
  contextLabel: string;
  contextDimension: "activity" | "person" | "setting" | "material" | null;
  contextSetting: string;
  transitionFrom: string;
  transitionTo: string;
  sessionCount: number;
  validOpportunityCount: number;
  independentSuccessfulCount: number;
  promptedSuccessfulCount: number;
  independentSuccessRate: number;
  averagePromptLevel: number | null;
  averageLatencySeconds: number | null;
  firstObservedAt: string;
  lastObservedAt: string;
  confidence: "normal" | "low";
  confidenceReasons: string[];
  evidenceSessionIds: string[];
  filterEligible: boolean;
}
export interface GoalMaterialUsageSummary {
  materialId: string;
  materialLabel: string;
  sessionCount: number;
  validOpportunityCount: number;
  independentSuccessfulCount: number;
  promptedSuccessfulCount: number;
  unsuccessfulOpportunityCount: number;
  contextsWithIndependentResponses: string[];
  contextsWithoutIndependentResponses: string[];
  evidenceSessionIds: string[];
}
export interface GoalProgressSeries {
  learnerId: string;
  goalId: string;
  goalRevision: number;
  operationalizedGoal: string;
  metric: GoalProgressMetric;
  points: GoalProgressPoint[];
  trend:
    | "no_data"
    | "insufficient_data"
    | "comparison_only"
    | "variable"
    | "improving"
    | "declining"
    | "steady";
  trendEvidence: string[];
  latestValue: number | null;
  sessionCount: number;
  confidence: "normal" | "low";
  confidenceReasons: string[];
  activeContextKey: string | null;
  contextSummaries: GoalContextSummary[];
  materialUsageSummaries: GoalMaterialUsageSummary[];
}
export interface GoalProgressSeriesOption {
  goalId: string;
  goalRevision: number;
  operationalizedGoal: string;
  sessionCount: number;
  latestCompletedAt: string;
}
export type NextSessionRecommendationType =
  | "reuse"
  | "modify_material"
  | "change_context"
  | "prompt_fading"
  | "increase_support"
  | "add_generalization"
  | "adjust_duration"
  | "collect_more_data"
  | "teacher_question";
export type NextSessionRecommendationStatus =
  | "pending"
  | "accepted"
  | "edited"
  | "rejected";
export interface RecommendationEvidence {
  sessionId: string;
  description: string;
  metricPath: string;
  observedValue: number | string | boolean | null;
  contextId: string | null;
  contextLabel: string | null;
}
export interface RecommendationReviewEvent {
  actorType: "teacher";
  action: "accepted" | "edited" | "rejected";
  teacherText: string | null;
  reviewedAt: string;
}
export interface NextSessionRecommendation {
  id: string;
  learnerId: string;
  goalId: string;
  goalRevision: number;
  type: NextSessionRecommendationType;
  title: string;
  recommendation: string;
  evidence: RecommendationEvidence[];
  confidence: "low" | "medium" | "high";
  confidenceReason: string;
  teacherReviewRequired: true;
  affectedLessonSpecPaths: string[];
  affectedMaterialIds: string[];
  affectedMaterialTypes: string[];
  status: NextSessionRecommendationStatus;
  teacherEditedText: string | null;
  ruleId: string;
  evidenceFingerprint: string;
  createdAt: string;
  reviewedAt: string | null;
  reviewHistory: RecommendationReviewEvent[];
  version: number;
}
export interface ReviewNextSessionRecommendationInput {
  action: "accepted" | "edited" | "rejected";
  teacherEditedText?: string;
  expectedVersion: number;
}
export interface RecommendationFieldProvenance {
  fieldPath: string;
  recommendationId: string;
  recommendationStatus: "accepted" | "edited";
  sourceContent: string;
  appliedValue: unknown;
  changed: boolean;
}
export interface ProposedLessonSpecRevision {
  id: string;
  previousLessonSpecId: string;
  previousLessonSpecRevision: number;
  lessonSpec: LessonSpec;
  acceptedRecommendationIds: string[];
  teacherEditedRecommendationContent: Record<string, string>;
  changedFields: string[];
  unchangedFields: string[];
  proposedGoalId: string;
  proposedGoalRevision: number;
  goalSeriesBoundary: "continue" | "new";
  profileRevision: string;
  fieldProvenance: RecommendationFieldProvenance[];
}
export interface MaterialCompatibilityCheck {
  dimension:
    | "goal"
    | "response_modes"
    | "reinforcement"
    | "contexts"
    | "access"
    | "profile_revision"
    | "visual_constraints"
    | "approval"
    | "semantic_content";
  passed: boolean;
  detail: string;
}
export interface ReusableMaterialImpact {
  materialId: string;
  materialRevision: number;
  materialType: string;
  title: string;
  reasonReusable: string;
  recommendationIds: string[];
  compatibilityChecks: MaterialCompatibilityCheck[];
}
export interface MaterialRevisionImpact {
  materialId: string;
  materialRevision: number;
  materialType: string;
  title: string;
  affectedFields: string[];
  reason: string;
  recommendationIds: string[];
  compatibilityChecks: MaterialCompatibilityCheck[];
  safeToKeepExisting: boolean;
}
export interface NewMaterialImpact {
  materialType: string;
  reason: string;
  recommendationIds: string[];
  required: boolean;
}
export interface RemovedMaterialImpact {
  materialId: string;
  materialType: string;
  title: string;
  reason: string;
  recommendationIds: string[];
}
export interface NextSessionMaterialImpactPlan {
  id: string;
  learnerId: string;
  previousPackageId: string;
  previousPackageRevision: number;
  proposedLessonSpecId: string;
  proposedLessonSpecRevision: ProposedLessonSpecRevision;
  reusableMaterials: ReusableMaterialImpact[];
  materialsToRevise: MaterialRevisionImpact[];
  newMaterialsRequired: NewMaterialImpact[];
  materialsToRemove: RemovedMaterialImpact[];
  blockingIssues: string[];
  overrides: Array<{
    action: "force_regenerate" | "keep_existing" | "reject_new";
    materialId: string | null;
    materialType: string | null;
    reason: string;
    createdAt: string;
    actorType: "teacher";
  }>;
  status: "proposed" | "package_created";
  createdPackageId: string | null;
  createdAt: string;
  version: number;
}
export interface UpdateNextSessionPlanInput {
  action: "force_regenerate" | "keep_existing" | "reject_new";
  materialId?: string;
  materialType?: string;
  reason: string;
  expectedVersion: number;
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
  configuration?: Record<string, unknown>;
  compatibleGoalTerms?: string[];
  compatibleProfileFactorIds?: string[];
  version?: number;
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
  status:
    | "pending"
    | "processing"
    | "completed"
    | "failed"
    | "expired"
    | "deleted";
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
  printPackageManifest?: PrintPackageManifest | null;
  pageCount?: number | null;
  artifactSha256?: string | null;
  downloadCount: number;
  lastDownloadedAt?: string | null;
  version: number;
}

export type PrintPackageSectionType =
  | "cover"
  | "personalization_summary"
  | "teacher_brief"
  | "lesson_flow"
  | "instructional_material"
  | "functional_support"
  | "data_collection"
  | "lesson_summary"
  | "appendix";

export interface PrintPackageManifestSection {
  sectionType: PrintPackageSectionType;
  title: string;
  materialIds: string[];
  required: boolean;
  pageBreakBefore: boolean;
  includedReason: string;
}

export type PrintPreset =
  | "complete_kit"
  | "teacher_desk"
  | "classroom_materials"
  | "data_and_closeout";

export type PrintTextProfile = "standard" | "large";

export interface PrintPresetInventoryEntry {
  entryType: "section" | "material";
  entryId: string;
  title: string;
  reason: string;
  materialType?: string | null;
  revision?: number | null;
}

export interface PrintPresetPreview {
  printPreset: PrintPreset;
  displayName: string;
  description: string;
  isDefault: boolean;
  includedEntries: PrintPresetInventoryEntry[];
  excludedEntries: PrintPresetInventoryEntry[];
  estimatedPageCount: number;
  available: boolean;
  unavailableReason?: string | null;
}

export interface PrintPresetCatalog {
  packageId: string;
  packageRevision: number;
  pageSize: "LETTER" | "A4";
  textProfile: PrintTextProfile;
  presets: PrintPresetPreview[];
}

export interface PrintPackageManifest {
  packageId: string;
  packageRevision: number;
  lessonSpecId: string;
  lessonSpecRevision: number;
  profileRevision: string;
  schemaVersion: 2;
  printPreset: PrintPreset;
  pageSize: "LETTER" | "A4";
  locale: string;
  sections: PrintPackageManifestSection[];
  excludedEntries: PrintPresetInventoryEntry[];
  materialRevisions: Record<string, number>;
  visualPlanRevisions: Record<string, number>;
  assetVersions: Record<string, number>;
  tableOfContents: boolean;
  pageNumbers: boolean;
  textProfile: PrintTextProfile;
  generatedAt: string;
  rendererVersion: string;
  sourceApprovalReadinessEvidence: {
    evaluatedAt: string;
    ready: boolean;
    packageApprovalStatus: "approved";
    packageRevision: number;
    lessonSpecRevision: number;
    materialReviewedRevisions: Record<string, number>;
    materialApprovedRevisions: Record<string, number>;
    warningBlockerIds: string[];
  };
  pageCount?: number | null;
}

export interface LessonSectionEditPreview {
  packageId: string;
  sectionId: string;
  sectionLabel: string;
  beforeText: string;
  revisedText: string;
  instruction: string;
  providerUsed: string;
  fallbackUsed: boolean;
}

export interface PrintableLessonKitInput {
  materialIds: string[];
  printPreset?: PrintPreset;
  pageSize: "Letter" | "A4";
  locale?: string;
  tableOfContents?: boolean;
  pageNumbers?: boolean;
  textProfile?: PrintTextProfile;
  reviewedConfirmation: true;
}

export type PrintReadinessBlockerCategory =
  | "semantic_validation_failure"
  | "safety_validation_failure"
  | "pending_visual"
  | "failed_optional_visual_with_fallback"
  | "failed_required_visual"
  | "material_revision_not_reviewed"
  | "material_revision_not_approved"
  | "package_not_approved"
  | "stale_lesson_spec_revision"
  | "stale_package_revision"
  | "stale_material_revision"
  | "stale_visual_plan_revision"
  | "generation_job_incomplete"
  | "generation_job_failed"
  | "storage_download_preparation_failure"
  | "renderer_manifest_incompatibility";

export interface PackagePrintReadinessBlocker {
  blockerId: string;
  category: PrintReadinessBlockerCategory;
  severity: "blocking" | "warning";
  materialId?: string | null;
  visualId?: string | null;
  explanation: string;
  expectedRevision?: number | null;
  currentRevision?: number | null;
  expectedLessonSpecRevision?: number | null;
  currentLessonSpecRevision?: number | null;
  recoveryAction: string;
  recoveryRoute: string;
  recoveryTargetId?: string | null;
  retryPossible: boolean;
}

export interface PackagePrintReadiness {
  packageId: string;
  packageRevision: number;
  lessonSpecId: string;
  lessonSpecRevision: number;
  ready: boolean;
  evaluatedAt: string;
  materialRevisions: Record<string, number>;
  visualPlanRevisions: Record<string, number>;
  packageApprovalStatus: string;
  blockers: PackagePrintReadinessBlocker[];
  recommendedNextAction?: PackagePrintReadinessBlocker | null;
  rendererVersion: string;
  manifestCompatible: boolean;
}

export interface PrintableLessonKitArtifact {
  artifactId: string;
  packageId: string;
  packageRevision: number;
  manifestVersion: 2;
  printPreset: PrintPreset;
  pageSize: "LETTER" | "A4";
  textProfile: PrintTextProfile;
  materialRevisions: Record<string, number>;
  status: "ready";
  filename: string;
  contentType: "application/pdf";
  sizeBytes: number;
  pageCount: number;
  sha256: string;
  downloadUrl: string;
  expiresAt: string;
  reused: boolean;
}

export type PdfDownloadPhase =
  | "idle"
  | "preparing"
  | "ready"
  | "download_starting"
  | "downloaded"
  | "failed";

export interface PdfDownloadState {
  phase: PdfDownloadPhase;
  message: string;
  errorCode?: string;
  retryable: boolean;
  artifact?: PrintableLessonKitArtifact;
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
export type MaterialQuickEditAction =
  | "simplify_wording"
  | "regenerate_artwork"
  | "adjust_reward";

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
