export type ChildProfile = {
  id: number;
  code: string;
  age?: number | null;
  diagnosis_level?: string | null;
  attention_span_minutes?: number | null;
  communication_level?: string | null;
  interests: string[];
  reinforcers: string[];
  behavior_notes: string;
  notes: string;
};

export type ImageCandidate = {
  id?: number | null;
  title: string;
  source_type: string;
  source_url?: string | null;
  thumbnail_url?: string | null;
  local_path?: string | null;
  tags: string[];
  variation_type?: string | null;
  quality_score: number;
  license_info?: string | null;
  license_label?: string | null;
  generation_prompt?: string | null;
};

export type ImagePipelineResult = {
  concept: string;
  target_skill: string;
  strategy_used: string;
  next_action: string;
  missing_count: number;
  notes: string[];
  candidates: ImageCandidate[];
};

export type LessonPlanResponse = {
  id?: number | null;
  target_skill: string;
  duration_minutes: number;
  teaching_goal: Record<string, unknown>;
  segments: Record<string, unknown>[];
  generalization_plan: Record<string, unknown>[];
  reinforcement_plan: {
    rotation: string[];
    schedule: string[];
    saturation_warnings: string[];
  };
  candidate_images: ImageCandidate[];
  teacher_script: string[];
  data_recording_sheet: Record<string, unknown>;
  session_notes_template: Record<string, unknown>;
  ai_used: boolean;
  cost_saving_notes: string[];
};

export type SessionRecordRead = {
  id: number;
  child_id: number;
  target_skill: string;
  independent_count: number;
  prompted_count: number;
  error_count: number;
  notes: string;
  progress_level: number;
  mastery_level: number;
  progress_delta: number;
  confidence_score: number;
};
