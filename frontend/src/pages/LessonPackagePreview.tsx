import { useState } from "react";
import { api } from "../api/client";
import { StatusMessage } from "../components/StatusMessage";
import { useAsyncAction } from "../hooks/useAsyncAction";
import type {
  ArtifactType,
  Disposition,
  DirectUseMetrics,
  LessonPlanResponse,
} from "../types";

type Props = {
  lesson: LessonPlanResponse | null;
};

const DISPOSITIONS: { value: Disposition; label: string }[] = [
  { value: "used_as_is", label: "Used as-is" },
  { value: "edited", label: "Edited" },
  { value: "not_used", label: "Didn't use" },
];

const ARTIFACTS: { key: ArtifactType; label: string }[] = [
  { key: "teacher_script", label: "Teacher Script" },
  { key: "generalization_plan", label: "Generalization Plan" },
  { key: "reinforcement_plan", label: "Reinforcement Plan" },
  { key: "data_recording_sheet", label: "Data Recording Sheet" },
  { key: "session_notes_template", label: "Session Notes Template" },
  { key: "image_cards", label: "Printable Image Cards" },
];

type ArtifactState = { disposition?: Disposition; edit_note: string };

function ArtifactRater({
  label,
  state,
  onChange,
}: {
  label: string;
  state: ArtifactState;
  onChange: (next: ArtifactState) => void;
}) {
  return (
    <div className="row">
      <strong>{label}</strong>
      <div className="heroActions left">
        {DISPOSITIONS.map((d) => (
          <label key={d.value} style={{ marginRight: "0.75rem" }}>
            <input
              type="radio"
              name={`disp-${label}`}
              checked={state.disposition === d.value}
              onChange={() => onChange({ ...state, disposition: d.value })}
            />{" "}
            {d.label}
          </label>
        ))}
      </div>
      <input
        type="text"
        placeholder="Optional: what did you change?"
        value={state.edit_note}
        onChange={(e) => onChange({ ...state, edit_note: e.target.value })}
      />
    </div>
  );
}

export function LessonPackagePreviewPage({ lesson }: Props) {
  const { loading, error, run } = useAsyncAction();
  const [ratings, setRatings] = useState<Record<string, ArtifactState>>({});
  const [metrics, setMetrics] = useState<DirectUseMetrics | null>(null);
  const [submitted, setSubmitted] = useState(false);

  if (!lesson) {
    return (
      <section className="card">
        <h2>Lesson Package Preview</h2>
        <StatusMessage tone="hint">
          Create a teaching package first.
        </StatusMessage>
      </section>
    );
  }

  const lessonId = lesson.id;
  const childId = lesson.child_id;

  function setArtifact(key: string, next: ArtifactState) {
    setRatings((prev) => ({ ...prev, [key]: next }));
  }

  async function handleSubmit() {
    if (lessonId == null) return;
    const items = ARTIFACTS.filter((a) => ratings[a.key]?.disposition).map(
      (a) => ({
        artifact_type: a.key,
        disposition: ratings[a.key].disposition as Disposition,
        edit_note: ratings[a.key].edit_note?.trim() || null,
      }),
    );
    if (items.length === 0) return;
    const result = await run(async () => {
      await api.submitLessonFeedback(lessonId, items);
      return api.getDirectUseMetrics(
        childId != null ? { child_id: childId } : undefined,
      );
    });
    if (result) {
      setMetrics(result);
      setSubmitted(true);
    }
  }

  return (
    <section className="grid two">
      <div className="card">
        <h2>Attention-Aware Flow</h2>
        {lesson.cost_saving_notes.map((note) => (
          <StatusMessage tone="success" key={note}>
            {note}
          </StatusMessage>
        ))}
        {lesson.segments.map((segment, index) => (
          <div className="row" key={index}>
            {String(segment.order)}. {String(segment.title)} ·{" "}
            {String(segment.duration_minutes)} min
            <br />
            {String(segment.activity)}
          </div>
        ))}
      </div>
      <div className="card">
        <h2>Teacher Script</h2>
        <div className="heroActions left">
          {Object.entries(lesson.downloadable_card_pdf_links).map(
            ([format, href]) => (
              <a className="buttonLink" href={href} key={format}>
                Download {format.toUpperCase()} Cards
              </a>
            ),
          )}
        </div>
        <ol>
          {lesson.teacher_script.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ol>
      </div>
      <div className="card">
        <h2>Generalization Plan</h2>
        {lesson.generalization_plan.map((item, index) => (
          <div className="row" key={index}>
            <strong>{String(item.dimension ?? item.type)}</strong>
            <br />
            {Array.isArray(item.examples) ? item.examples.join(" / ") : ""}
          </div>
        ))}
      </div>
      <div className="card">
        <h2>Reinforcement Plan</h2>
        <p className="hint">
          Rotation: {lesson.reinforcement_plan.rotation.join(", ")}
        </p>
        <ul>
          {lesson.reinforcement_plan.schedule.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h2>Did you use it? (direct-use feedback)</h2>
        <StatusMessage tone="hint">
          Mark how you used each artifact so we can measure the direct-use rate.
        </StatusMessage>
        {ARTIFACTS.map((a) => (
          <ArtifactRater
            key={a.key}
            label={a.label}
            state={ratings[a.key] ?? { edit_note: "" }}
            onChange={(next) => setArtifact(a.key, next)}
          />
        ))}
        {error && <StatusMessage tone="error">{error}</StatusMessage>}
        <div className="heroActions left">
          <button type="button" onClick={handleSubmit} disabled={loading}>
            {loading ? "Submitting…" : "Submit feedback"}
          </button>
        </div>
        {submitted && metrics && (
          <StatusMessage tone="success">
            Direct-use rate: {(metrics.direct_use_rate * 100).toFixed(0)}% (
            {metrics.by_disposition.used_as_is}/{metrics.total_rated} used as-is)
          </StatusMessage>
        )}
      </div>
    </section>
  );
}
