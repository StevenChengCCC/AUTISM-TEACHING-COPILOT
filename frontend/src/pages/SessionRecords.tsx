import { useState } from "react";
import { StatusMessage } from "../components/StatusMessage";
import { api } from "../api/client";
import type { ChildProfile, SessionRecordRead, TeachingGoal } from "../types";

type Props = {
  child: ChildProfile | null;
  goal: TeachingGoal | null;
  onGoalsRefresh: (goals: TeachingGoal[]) => void;
};

export function SessionRecordsPage({ child, goal, onGoalsRefresh }: Props) {
  const [record, setRecord] = useState({
    independent_count: 0,
    prompted_count: 0,
    error_count: 0,
    notes: "",
  });
  const [savedRecord, setSavedRecord] = useState<SessionRecordRead | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function saveRecord() {
    if (!child || !goal) {
      setError("Select a child and teaching goal first.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const result = await api.createRecord({
        child_id: child.id,
        goal_id: goal.id,
        target_skill: goal.target_skill,
        ...record,
      });
      setSavedRecord(result);
      onGoalsRefresh(await api.listGoals(child.id));
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to save session record",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card">
      <h2>Session Records</h2>
      {loading && <StatusMessage tone="hint">Loading...</StatusMessage>}
      {error && <StatusMessage tone="error">{error}</StatusMessage>}
      <div className="formGrid">
        <input
          type="number"
          value={record.independent_count}
          onChange={(event) =>
            setRecord({
              ...record,
              independent_count: Number(event.target.value),
            })
          }
          placeholder="Independent"
        />
        <input
          type="number"
          value={record.prompted_count}
          onChange={(event) =>
            setRecord({ ...record, prompted_count: Number(event.target.value) })
          }
          placeholder="Prompted"
        />
        <input
          type="number"
          value={record.error_count}
          onChange={(event) =>
            setRecord({ ...record, error_count: Number(event.target.value) })
          }
          placeholder="Errors"
        />
      </div>
      <label>Notes</label>
      <input
        value={record.notes}
        onChange={(event) =>
          setRecord({ ...record, notes: event.target.value })
        }
      />
      <button
        className="primary"
        disabled={loading || !child || !goal}
        onClick={saveRecord}
      >
        Save Session Record
      </button>
      {savedRecord && (
        <StatusMessage tone="success">
          Mastery L{savedRecord.mastery_level}, delta{" "}
          {savedRecord.progress_delta}, confidence{" "}
          {savedRecord.confidence_score}
        </StatusMessage>
      )}
    </section>
  );
}
