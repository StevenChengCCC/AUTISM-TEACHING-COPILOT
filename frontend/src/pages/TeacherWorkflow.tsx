import { useState } from "react";
import { ApiError, api } from "../api/client";
import { StatusMessage } from "../components/StatusMessage";
import type {
  ChildProfile,
  ImageCandidate,
  LessonPlanResponse,
  TeachingGoal,
} from "../types";

type Props = {
  children: ChildProfile[];
  goals: TeachingGoal[];
  selectedChildId: number | null;
  selectedGoalId: number | null;
  confirmedImages: ImageCandidate[];
  onSelectChild: (childId: number | null) => void;
  onGoalsChange: (goals: TeachingGoal[]) => void;
  onSelectGoal: (goalId: number | null) => void;
  onLessonChange: (lesson: LessonPlanResponse) => void;
  onNavigateImages: () => void;
  onNavigatePreview: () => void;
};

type GuidedQuestion = {
  field: string;
  question: string;
  reason: string;
};

export function TeacherWorkflowPage({
  children,
  goals,
  selectedChildId,
  selectedGoalId,
  confirmedImages,
  onSelectChild,
  onGoalsChange,
  onSelectGoal,
  onLessonChange,
  onNavigateImages,
  onNavigatePreview,
}: Props) {
  const [goalForm, setGoalForm] = useState({
    target_skill: "recognize apple",
    concept: "apple",
    notes: "Use confirmed image cards and real-object generalization.",
  });
  const [durationMinutes, setDurationMinutes] = useState(25);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [guidedQuestions, setGuidedQuestions] = useState<GuidedQuestion[]>([]);

  const selectedChild = children.find((child) => child.id === selectedChildId);
  const selectedGoal = goals.find((goal) => goal.id === selectedGoalId);

  async function selectChild(value: string) {
    const childId = value ? Number(value) : null;
    onSelectChild(childId);
    onSelectGoal(null);
    if (!childId) return;
    setLoading(true);
    setError("");
    try {
      onGoalsChange(await api.listGoals(childId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load goals");
    } finally {
      setLoading(false);
    }
  }

  async function createGoal() {
    if (!selectedChild) {
      setError("Select a child code first.");
      return;
    }
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      const goal = await api.createGoal({
        child_id: selectedChild.id,
        target_skill: goalForm.target_skill,
        concept: goalForm.concept,
        status: "active",
        notes: goalForm.notes,
      });
      onGoalsChange([goal, ...goals]);
      onSelectGoal(goal.id);
      setSuccess("Teaching goal created.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create goal");
    } finally {
      setLoading(false);
    }
  }

  async function generatePackage() {
    if (!selectedChild || !selectedGoal) {
      setError("Select a child code and teaching goal first.");
      return;
    }
    if (confirmedImages.length === 0) {
      setError("Confirm images before saving a lesson package.");
      onNavigateImages();
      return;
    }
    setLoading(true);
    setError("");
    setSuccess("");
    setGuidedQuestions([]);
    try {
      const lesson = await api.createLesson({
        child_id: selectedChild.id,
        goal_id: selectedGoal.id,
        target_skill: selectedGoal.target_skill,
        duration_minutes: durationMinutes,
        print_formats: ["a4", "letter"],
        selected_image_asset_ids: confirmedImages.flatMap((image) =>
          image.id ? [image.id] : [],
        ),
      });
      onLessonChange(lesson);
      setSuccess("Teaching package and printable card PDFs are ready.");
      onNavigatePreview();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        const data = err.data as {
          profile_completeness?: { guided_questions?: GuidedQuestion[] };
        };
        setGuidedQuestions(data.profile_completeness?.guided_questions ?? []);
      } else {
        setError(
          err instanceof Error ? err.message : "Failed to generate package",
        );
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="grid two">
      <div className="card">
        <h2>Main Teacher Workflow</h2>
        {loading && <StatusMessage tone="hint">Loading...</StatusMessage>}
        {error && <StatusMessage tone="error">{error}</StatusMessage>}
        {success && <StatusMessage tone="success">{success}</StatusMessage>}
        <label>Select child code</label>
        <select
          value={selectedChildId ?? ""}
          onChange={(event) => void selectChild(event.target.value)}
        >
          <option value="">Select child</option>
          {children.map((child) => (
            <option key={child.id} value={child.id}>
              {child.code}
            </option>
          ))}
        </select>

        <label>Select teaching goal</label>
        <select
          value={selectedGoalId ?? ""}
          onChange={(event) =>
            onSelectGoal(event.target.value ? Number(event.target.value) : null)
          }
          disabled={!selectedChild}
        >
          <option value="">Select goal</option>
          {goals.map((goal) => (
            <option key={goal.id} value={goal.id}>
              {goal.target_skill} · {goal.concept ?? "concept?"}
            </option>
          ))}
        </select>

        <label>Duration minutes</label>
        <input
          type="number"
          min={5}
          max={90}
          value={durationMinutes}
          onChange={(event) => setDurationMinutes(Number(event.target.value))}
        />

        <div className="heroActions left">
          <button disabled={!selectedGoal} onClick={onNavigateImages}>
            Review Images
          </button>
          <button
            className="primary"
            disabled={loading || !selectedChild || !selectedGoal}
            onClick={generatePackage}
          >
            Generate Teaching Package
          </button>
        </div>

        {guidedQuestions.length > 0 && (
          <div className="questionList">
            <h3>Complete Intake First</h3>
            {guidedQuestions.map((item) => (
              <div className="row" key={item.field}>
                <strong>{item.field}</strong>
                <br />
                {item.question}
                <small>{item.reason}</small>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <h2>Create Goal</h2>
        <label>Target skill</label>
        <input
          value={goalForm.target_skill}
          onChange={(event) =>
            setGoalForm({ ...goalForm, target_skill: event.target.value })
          }
        />
        <label>Concept</label>
        <input
          value={goalForm.concept}
          onChange={(event) =>
            setGoalForm({ ...goalForm, concept: event.target.value })
          }
        />
        <label>Notes</label>
        <input
          value={goalForm.notes}
          onChange={(event) =>
            setGoalForm({ ...goalForm, notes: event.target.value })
          }
        />
        <button
          className="primary"
          disabled={loading || !selectedChild}
          onClick={createGoal}
        >
          Create Teaching Goal
        </button>
      </div>
    </section>
  );
}
