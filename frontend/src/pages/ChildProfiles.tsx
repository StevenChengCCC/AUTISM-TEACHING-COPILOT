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
    communication_mode: "short spoken phrases",
    current_level: "Can match identical picture cards with gesture prompts.",
    interests: "cars, dinosaurs",
    preferred_reinforcers: "car toy, sticker",
    prompting_that_works: "gesture prompt, model prompt",
    avoid_notes: "avoid long verbal instructions and noisy materials",
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
        communication_mode: form.communication_mode,
        communication_level: form.communication_mode,
        current_level: form.current_level,
        interests: splitList(form.interests),
        reinforcers: splitList(form.preferred_reinforcers),
        preferred_reinforcers: splitList(form.preferred_reinforcers),
        prompting_that_works: form.prompting_that_works,
        avoid_notes: form.avoid_notes,
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
        <label>Communication Mode</label>
        <input
          value={form.communication_mode}
          onChange={(event) =>
            setForm({ ...form, communication_mode: event.target.value })
          }
        />
        <label>Current Level</label>
        <input
          value={form.current_level}
          onChange={(event) =>
            setForm({ ...form, current_level: event.target.value })
          }
        />
        <label>Interests</label>
        <input
          value={form.interests}
          onChange={(event) =>
            setForm({ ...form, interests: event.target.value })
          }
        />
        <label>Preferred Reinforcers</label>
        <input
          value={form.preferred_reinforcers}
          onChange={(event) =>
            setForm({ ...form, preferred_reinforcers: event.target.value })
          }
        />
        <label>Prompting That Works</label>
        <input
          value={form.prompting_that_works}
          onChange={(event) =>
            setForm({ ...form, prompting_that_works: event.target.value })
          }
        />
        <label>Avoid Notes</label>
        <input
          value={form.avoid_notes}
          onChange={(event) =>
            setForm({ ...form, avoid_notes: event.target.value })
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
