import { useEffect, useState } from "react";
import { StatusMessage } from "../components/StatusMessage";
import { api } from "../api/client";
import type { ChildProfile } from "../types";

type Props = {
  children: ChildProfile[];
  selectedChildId: number | null;
  onChildrenChange: (children: ChildProfile[]) => void;
  onSelectChild: (childId: number) => void;
};

export function ChildProfilesPage({
  children,
  selectedChildId,
  onChildrenChange,
  onSelectChild,
}: Props) {
  const [form, setForm] = useState({
    code: `C-${Date.now().toString().slice(-4)}`,
    age: "8",
    diagnosis_level: "ASD Level 2",
    attention_span_minutes: "5",
    communication_level: "short phrases",
    interests: "cars, dinosaurs",
    reinforcers: "car toy, sticker",
    behavior_notes: "Attention drops when tasks are too long.",
    notes: "Use anonymous learner codes only.",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    setLoading(true);
    api
      .listChildren()
      .then(onChildrenChange)
      .catch((err) =>
        setError(
          err instanceof Error ? err.message : "Failed to load child profiles",
        ),
      )
      .finally(() => setLoading(false));
  }, [onChildrenChange]);

  async function createChild() {
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      const child = await api.createChild({
        code: form.code,
        age: Number(form.age) || null,
        diagnosis_level: form.diagnosis_level,
        attention_span_minutes: Number(form.attention_span_minutes) || null,
        communication_level: form.communication_level,
        interests: splitList(form.interests),
        reinforcers: splitList(form.reinforcers),
        behavior_notes: form.behavior_notes,
        notes: form.notes,
      });
      onChildrenChange([child, ...children]);
      onSelectChild(child.id);
      setSuccess("Child profile saved.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to save child profile",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="grid two">
      <div className="card">
        <h2>Child Profiles</h2>
        {loading && <StatusMessage tone="hint">Loading...</StatusMessage>}
        {error && <StatusMessage tone="error">{error}</StatusMessage>}
        {success && <StatusMessage tone="success">{success}</StatusMessage>}
        <div className="formGrid">
          <input
            value={form.code}
            onChange={(event) => setForm({ ...form, code: event.target.value })}
          />
          <input
            value={form.age}
            onChange={(event) => setForm({ ...form, age: event.target.value })}
          />
          <input
            value={form.diagnosis_level}
            onChange={(event) =>
              setForm({ ...form, diagnosis_level: event.target.value })
            }
          />
          <input
            value={form.attention_span_minutes}
            onChange={(event) =>
              setForm({ ...form, attention_span_minutes: event.target.value })
            }
          />
        </div>
        <label>Communication</label>
        <input
          value={form.communication_level}
          onChange={(event) =>
            setForm({ ...form, communication_level: event.target.value })
          }
        />
        <label>Interests</label>
        <input
          value={form.interests}
          onChange={(event) =>
            setForm({ ...form, interests: event.target.value })
          }
        />
        <label>Reinforcers</label>
        <input
          value={form.reinforcers}
          onChange={(event) =>
            setForm({ ...form, reinforcers: event.target.value })
          }
        />
        <button className="primary" disabled={loading} onClick={createChild}>
          Save Child Profile
        </button>
      </div>
      <div className="card">
        <h2>Select Learner</h2>
        {children.map((child) => (
          <button
            className={
              selectedChildId === child.id ? "primary rowButton" : "rowButton"
            }
            key={child.id}
            onClick={() => onSelectChild(child.id)}
          >
            {child.code} · attention {child.attention_span_minutes ?? "?"} min
          </button>
        ))}
      </div>
    </section>
  );
}

function splitList(value: string): string[] {
  return value
    .split(/[，,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}
