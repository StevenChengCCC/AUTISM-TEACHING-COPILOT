import { useState } from "react";
import { StatusMessage } from "../components/StatusMessage";
import { api } from "../api/client";
import type {
  ChildProfile,
  ImageCandidate,
  LessonPlanResponse,
  TeachingGoal,
} from "../types";

type Props = {
  child: ChildProfile | null;
  goal: TeachingGoal | null;
  confirmedImages: ImageCandidate[];
  onLessonChange: (lesson: LessonPlanResponse) => void;
  onNavigatePreview: () => void;
};

export function CreateLessonPackagePage({
  child,
  goal,
  confirmedImages,
  onLessonChange,
  onNavigatePreview,
}: Props) {
  const [durationMinutes, setDurationMinutes] = useState(25);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function createLesson() {
    if (!child || !goal) {
      setError("Select a child and teaching goal first.");
      return;
    }
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      const lesson = await api.createLesson({
        child_id: child.id,
        goal_id: goal.id,
        target_skill: goal.target_skill,
        duration_minutes: durationMinutes,
        selected_image_asset_ids: confirmedImages.flatMap((image) =>
          image.id ? [image.id] : [],
        ),
      });
      onLessonChange(lesson);
      setSuccess("Teaching package generated and saved.");
      onNavigatePreview();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to create lesson package",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card">
      <h2>Create Lesson Package</h2>
      {loading && <StatusMessage tone="hint">Loading...</StatusMessage>}
      {error && <StatusMessage tone="error">{error}</StatusMessage>}
      {success && <StatusMessage tone="success">{success}</StatusMessage>}
      <p className="hint">
        Confirmed images available: {confirmedImages.length}
      </p>
      <label>Duration minutes</label>
      <input
        min={5}
        max={90}
        type="number"
        value={durationMinutes}
        onChange={(event) => setDurationMinutes(Number(event.target.value))}
      />
      <button
        className="primary"
        disabled={loading || !child || !goal}
        onClick={createLesson}
      >
        Generate Teaching Package
      </button>
    </section>
  );
}
