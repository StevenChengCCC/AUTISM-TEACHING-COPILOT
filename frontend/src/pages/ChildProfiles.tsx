import { useEffect, useState } from "react";
import { StatusMessage } from "../components/StatusMessage";
import { api } from "../api/client";
import type { ChildProfile } from "../types";

type Props = {
  children: ChildProfile[];
  selectedChildId: number | null;
  onChildrenChange: (children: ChildProfile[]) => void;
  onSelectChild: (childId: number) => void;
  onContinue?: () => void;
};

type Mode = "pick" | "new";

export function ChildProfilesPage({
  children,
  selectedChildId,
  onChildrenChange,
  onSelectChild,
  onContinue,
}: Props) {
  const [mode, setMode] = useState<Mode>(children.length > 0 ? "pick" : "new");
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
      .then((list) => {
        onChildrenChange(list);
        if (list.length > 0) setMode("pick");
      })
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
      onContinue?.();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to save child profile",
      );
    } finally {
      setLoading(false);
    }
  }

  function continueWithSelected() {
    if (selectedChildId == null) {
      setError("Pick a learner first, or add a new one.");
      return;
    }
    onContinue?.();
  }

  return (
    <section className="grid">
      <div className="card panel rise rise-1">
        <div className="orient">
          <span className="stepcount">Step 1 of 6</span>
          <span className="stepwhat">Add the child you're planning for.</span>
        </div>
        <h2>Who is this session for?</h2>

        <div className="toggle" role="tablist" aria-label="Pick or add a child">
          <button
            role="tab"
            aria-selected={mode === "pick"}
            className={mode === "pick" ? "sel" : ""}
            disabled={children.length === 0}
            onClick={() => setMode("pick")}
          >
            Pick existing
          </button>
          <button
            role="tab"
            aria-selected={mode === "new"}
            className={mode === "new" ? "sel" : ""}
            onClick={() => setMode("new")}
          >
            Add new
          </button>
        </div>

        {loading && <StatusMessage tone="hint">Loading…</StatusMessage>}
        {error && <StatusMessage tone="error">{error}</StatusMessage>}
        {success && <StatusMessage tone="success">{success}</StatusMessage>}

        {mode === "pick" ? (
          <>
            <div className="pick-list">
              {children.map((child) => (
                <button
                  key={child.id}
                  className={
                    selectedChildId === child.id
                      ? "pick-item sel"
                      : "pick-item"
                  }
                  onClick={() => onSelectChild(child.id)}
                >
                  <span className="pick-code">{child.code}</span>
                  <span className="pick-meta">
                    {child.diagnosis_level ?? "—"} · attention{" "}
                    <span className="mono">
                      {child.attention_span_minutes ?? "?"}
                    </span>{" "}
                    min
                  </span>
                </button>
              ))}
            </div>
            <button
              className="primary"
              disabled={selectedChildId == null}
              onClick={continueWithSelected}
            >
              Save &amp; continue
            </button>
          </>
        ) : (
          <>
            <label htmlFor="cp-code">Child code</label>
            <input
              id="cp-code"
              className="mono"
              value={form.code}
              onChange={(event) => setForm({ ...form, code: event.target.value })}
            />
            <div className="formGrid">
              <div>
                <label htmlFor="cp-age">Age</label>
                <input
                  id="cp-age"
                  className="mono"
                  value={form.age}
                  onChange={(event) =>
                    setForm({ ...form, age: event.target.value })
                  }
                />
              </div>
              <div>
                <label htmlFor="cp-attn">Attention span (min)</label>
                <input
                  id="cp-attn"
                  className="mono"
                  value={form.attention_span_minutes}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      attention_span_minutes: event.target.value,
                    })
                  }
                />
              </div>
            </div>
            <label htmlFor="cp-dx">Diagnosis level</label>
            <input
              id="cp-dx"
              value={form.diagnosis_level}
              onChange={(event) =>
                setForm({ ...form, diagnosis_level: event.target.value })
              }
            />
            <label htmlFor="cp-comm">Communication mode</label>
            <input
              id="cp-comm"
              value={form.communication_mode}
              onChange={(event) =>
                setForm({ ...form, communication_mode: event.target.value })
              }
            />

            <details className="disclosure">
              <summary>Add more detail (optional)</summary>
              <label htmlFor="cp-level">Current level</label>
              <input
                id="cp-level"
                value={form.current_level}
                onChange={(event) =>
                  setForm({ ...form, current_level: event.target.value })
                }
              />
              <label htmlFor="cp-interests">Interests</label>
              <input
                id="cp-interests"
                value={form.interests}
                onChange={(event) =>
                  setForm({ ...form, interests: event.target.value })
                }
              />
              <label htmlFor="cp-reinforcers">Preferred reinforcers</label>
              <input
                id="cp-reinforcers"
                value={form.preferred_reinforcers}
                onChange={(event) =>
                  setForm({ ...form, preferred_reinforcers: event.target.value })
                }
              />
              <label htmlFor="cp-prompt">Prompting that works</label>
              <input
                id="cp-prompt"
                value={form.prompting_that_works}
                onChange={(event) =>
                  setForm({ ...form, prompting_that_works: event.target.value })
                }
              />
              <label htmlFor="cp-avoid">Avoid notes</label>
              <input
                id="cp-avoid"
                value={form.avoid_notes}
                onChange={(event) =>
                  setForm({ ...form, avoid_notes: event.target.value })
                }
              />
            </details>

            <button className="primary" disabled={loading} onClick={createChild}>
              Save &amp; continue
            </button>
          </>
        )}
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
