import type { ChildProfile, ImageCandidate, ImagePipelineResult, LessonPlanResponse, SessionRecordRead } from '../types';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const api = {
  listChildren: () => request<ChildProfile[]>('/children'),
  createChild: (payload: Omit<ChildProfile, 'id'>) =>
    request<ChildProfile>('/children', { method: 'POST', body: JSON.stringify(payload) }),
  runImagePipeline: (payload: {
    child_id: number;
    target_skill: string;
    concept: string;
    needed_count: number;
    prefer_real_photos: boolean;
    variation_requirements: string[];
  }) => request<ImagePipelineResult>('/images/pipeline', { method: 'POST', body: JSON.stringify(payload) }),
  confirmImages: (payload: { candidates: ImageCandidate[]; approved_indexes: number[]; skill_target: string; concept: string }) =>
    request<ImageCandidate[]>('/images/confirm', { method: 'POST', body: JSON.stringify(payload) }),
  createLesson: (payload: { child_id: number; target_skill: string; duration_minutes: number; selected_image_asset_ids: number[] }) =>
    request<LessonPlanResponse>('/lessons', { method: 'POST', body: JSON.stringify(payload) }),
  createRecord: (payload: { child_id: number; target_skill: string; independent_count: number; prompted_count: number; error_count: number; notes: string }) =>
    request<SessionRecordRead>('/records', { method: 'POST', body: JSON.stringify(payload) }),
};
