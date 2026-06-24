import { useEffect, useState } from "react";
import { StatusMessage } from "../components/StatusMessage";
import { api } from "../api/client";
import type { ChildProfile, TeachingGoal } from "../types";

type Props = {
  child: ChildProfile | null;
  goals: TeachingGoal[];
  selectedGoalId: number | null;
  onGoalsChange: (goals: TeachingGoal[]) => void;
  onSelectGoal: (goalId: number) => void;
};

export function TeachingGoalsPage({
  child,
  goals,
  selectedGoalId,
  onGoalsChange,
  onSelectGoal,
}: Props) {
  const [targetSkill, setTargetSkill] = useState("recognize apple");
  const [concept, setConcept] = useState("apple");
  const [notes, setNotes] = useState("Use real objects and photo cards.");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (!child) return;
    setLoading(true);
    api
      .listGoals(child.id)
      .then(onGoalsChange)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load goals"),
      )
      .finally(() => setLoading(false));
  }, [child, onGoalsChange]);

  async function createGoal() {
    if (!child) {
      setError("Select a child profile first.");
      return;
    }
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      const goal = await api.createGoal({
        child_id: child.id,
        target_skill: targetSkill,
        concept,
        status: "active",
        notes,
      });
      onGoalsChange([goal, ...goals]);
      onSelectGoal(goal.id);
      setSuccess("Teaching goal saved.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to save teaching goal",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="grid two">
      <div className="card">
        <h2>Teaching Goals</h2>
        {!child && (
          <StatusMessage tone="hint">
            Select a child profile first.
          </StatusMessage>
        )}
        {loading && <StatusMessage tone="hint">Loading...</StatusMessage>}
        {error && <StatusMessage tone="error">{error}</StatusMessage>}
        {success && <StatusMessage tone="success">{success}</StatusMessage>}
        <label>Target Skill</label>
        <input
          value={targetSkill}
          onChange={(event) => setTargetSkill(event.target.value)}
        />
        <label>Concept</label>
        <input
          value={concept}
          onChange={(event) => setConcept(event.target.value)}
        />
        <label>Notes</label>
        <input
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
        />
        <button
          className="primary"
          disabled={loading || !child}
          onClick={createGoal}
        >
          Save Teaching Goal
        </button>
      </div>
      <div className="card">
        <h2>Goal List</h2>
        {goals.map((goal) => (
          <button
            className={
              selectedGoalId === goal.id ? "primary rowButton" : "rowButton"
            }
            key={goal.id}
            onClick={() => onSelectGoal(goal.id)}
          >
            {goal.target_skill} · {goal.concept ?? "concept?"} · L
            {goal.mastery_level}
          </button>
        ))}
      </div>
    </section>
  );
}
