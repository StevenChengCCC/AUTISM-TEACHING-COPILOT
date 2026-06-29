import type {
  ArtifactFeedbackItem,
  ArtifactFeedbackRead,
  ChildProfile,
  DirectUseMetrics,
  ImageCandidate,
  ImagePipelineResult,
  LessonPlanResponse,
  CurriculumContent,
  Organization,
  SessionRecordRead,
  TeachingGoal,
  Teacher,
  TeacherChildAccess,
  UploadedMaterial,
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api";

export class ApiError extends Error {
  data: unknown;

  constructor(message: string, data: unknown) {
    super(message);
    this.name = "ApiError";
    this.data = data;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {}),
    },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    try {
      const data = JSON.parse(text);
      throw new ApiError(data.detail || `Request failed: ${res.status}`, data);
    } catch (err) {
      if (err instanceof ApiError) throw err;
      throw new Error(text || `Request failed: ${res.status}`);
    }
  }
  return res.json();
}

export const api = {
  listChildren: () => request<ChildProfile[]>("/children"),
  createChild: (payload: Omit<ChildProfile, "id">) =>
    request<ChildProfile>("/children", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  checkChildCompleteness: (childId: number) =>
    request<{
      child_id: number;
      is_complete: boolean;
      missing_fields: string[];
      guided_questions: { field: string; question: string; reason: string }[];
    }>(`/children/${childId}/completeness`),
  updateChild: (childId: number, payload: Partial<Omit<ChildProfile, "id">>) =>
    request<ChildProfile>(`/children/${childId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  listGoals: (childId?: number) =>
    request<TeachingGoal[]>(childId ? `/goals?child_id=${childId}` : "/goals"),
  createGoal: (payload: Omit<TeachingGoal, "id" | "mastery_level">) =>
    request<TeachingGoal>("/goals", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateGoal: (
    goalId: number,
    payload: Partial<Omit<TeachingGoal, "id" | "child_id">>,
  ) =>
    request<TeachingGoal>(`/goals/${goalId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  runImagePipeline: (payload: {
    child_id: number;
    target_skill: string;
    concept: string;
    needed_count: number;
    prefer_real_photos: boolean;
    variation_requirements: string[];
  }) =>
    request<ImagePipelineResult>("/images/pipeline", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  confirmImages: (payload: {
    candidates: ImageCandidate[];
    approved_indexes: number[];
    skill_target: string;
    concept: string;
  }) =>
    request<ImageCandidate[]>("/images/confirm", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listAssets: () => request<ImageCandidate[]>("/images/assets"),
  createLesson: (payload: {
    child_id: number;
    goal_id?: number | null;
    target_skill: string;
    duration_minutes: number;
    print_formats?: string[];
    selected_image_asset_ids: number[];
  }) =>
    request<LessonPlanResponse>("/lessons", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  createRecord: (payload: {
    child_id: number;
    goal_id?: number | null;
    target_skill: string;
    independent_count: number;
    prompted_count: number;
    error_count: number;
    notes: string;
  }) =>
    request<SessionRecordRead>("/records", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  submitLessonFeedback: (lessonId: number, items: ArtifactFeedbackItem[]) =>
    request<ArtifactFeedbackRead[]>(`/lessons/${lessonId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ items }),
    }),
  getLessonFeedback: (lessonId: number) =>
    request<ArtifactFeedbackRead[]>(`/lessons/${lessonId}/feedback`),
  getDirectUseMetrics: (params?: {
    child_id?: number;
    goal_id?: number;
    since?: string;
  }) => {
    const query = new URLSearchParams();
    if (params?.child_id != null) query.set("child_id", String(params.child_id));
    if (params?.goal_id != null) query.set("goal_id", String(params.goal_id));
    if (params?.since) query.set("since", params.since);
    const qs = query.toString();
    return request<DirectUseMetrics>(`/metrics/direct-use${qs ? `?${qs}` : ""}`);
  },
  listMaterials: (childId?: number) =>
    request<UploadedMaterial[]>(
      childId ? `/materials?child_id=${childId}` : "/materials",
    ),
  createMaterial: (payload: Omit<UploadedMaterial, "id">) =>
    request<UploadedMaterial>("/materials", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateMaterial: (materialId: number, payload: Partial<UploadedMaterial>) =>
    request<UploadedMaterial>(`/materials/${materialId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteMaterial: (materialId: number) =>
    request<{ deleted: boolean; id: number }>(`/materials/${materialId}`, {
      method: "DELETE",
    }),
  listOrganizations: () => request<Organization[]>("/organizations"),
  createOrganization: (payload: Omit<Organization, "id">) =>
    request<Organization>("/organizations", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listTeachers: () => request<Teacher[]>("/teachers"),
  createTeacher: (payload: Omit<Teacher, "id">) =>
    request<Teacher>("/teachers", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listAccess: () => request<TeacherChildAccess[]>("/access"),
  createAccess: (payload: Omit<TeacherChildAccess, "id">) =>
    request<TeacherChildAccess>("/access", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteAccess: (accessId: number) =>
    request<{ deleted: boolean; id: number }>(`/access/${accessId}`, {
      method: "DELETE",
    }),
  listCurriculum: () => request<CurriculumContent[]>("/curriculum"),
  createCurriculum: (payload: Omit<CurriculumContent, "id">) =>
    request<CurriculumContent>("/curriculum", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateCurriculum: (
    contentId: number,
    payload: Partial<Omit<CurriculumContent, "id">>,
  ) =>
    request<CurriculumContent>(`/curriculum/${contentId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteCurriculum: (contentId: number) =>
    request<{ deleted: boolean; id: number }>(`/curriculum/${contentId}`, {
      method: "DELETE",
    }),
};
