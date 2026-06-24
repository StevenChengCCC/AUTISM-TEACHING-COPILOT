export type ChildProfile = {
  id: number;
  code: string;
  age?: number | null;
  diagnosis_level?: string | null;
  attention_span_minutes?: number | null;
  communication_mode?: string | null;
  communication_level?: string | null;
  current_level: string;
  interests: string[];
  reinforcers: string[];
  preferred_reinforcers: string[];
  prompting_that_works: string;
  avoid_notes: string;
  behavior_notes: string;
  notes: string;
};

export type TeachingGoal = {
  id: number;
  child_id: number;
  target_skill: string;
  concept?: string | null;
  status: string;
  mastery_level: number;
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
  reason?: string | null;
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
  child_id?: number | null;
  goal_id?: number | null;
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
  downloadable_card_pdf_links: Record<string, string>;
  teacher_script: string[];
  data_recording_sheet: Record<string, unknown>;
  session_notes_template: Record<string, unknown>;
  ai_used: boolean;
  cost_saving_notes: string[];
};

export type SessionRecordRead = {
  id: number;
  child_id: number;
  goal_id?: number | null;
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

export type UploadedMaterial = {
  id: number;
  child_id: number;
  title: string;
  material_type: string;
  source_path?: string | null;
  extracted_text: string;
  status: string;
};

export type Organization = {
  id: number;
  name: string;
  external_ref?: string | null;
};

export type Teacher = {
  id: number;
  organization_id?: number | null;
  display_name: string;
  email?: string | null;
  role: string;
};

export type TeacherChildAccess = {
  id: number;
  teacher_id: number;
  child_id: number;
  permission_level: string;
};

export type CurriculumContent = {
  id: number;
  organization_id?: number | null;
  title: string;
  content_type: string;
  content_json: Record<string, unknown>;
  status: string;
};
