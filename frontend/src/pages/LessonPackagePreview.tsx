import type { CSSProperties } from "react";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { StatusMessage } from "../components/StatusMessage";
import { useAsyncAction } from "../hooks/useAsyncAction";
import type {
  ArtifactType,
  Disposition,
  DirectUseMetrics,
  ImageCandidate,
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
  { key: "teacher_script", label: "Teacher script" },
  { key: "generalization_plan", label: "Generalization plan" },
  { key: "reinforcement_plan", label: "Reinforcement plan" },
  { key: "data_recording_sheet", label: "Data recording sheet" },
  { key: "session_notes_template", label: "Session notes template" },
  { key: "image_cards", label: "Printable image cards" },
];

type ArtifactState = { disposition?: Disposition; edit_note: string };

/** Resolve a (possibly relative) storage path to an absolute URL. */
function resolveImageUrl(image: ImageCandidate): string | null {
  const raw = image.thumbnail_url || image.local_path || image.source_url;
  if (!raw) return null;
  if (/^https?:\/\//.test(raw)) return raw;
  const base = (
    import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api"
  ).replace(/\/api\/?$/, "");
  return `${base}${raw.startsWith("/") ? "" : "/"}${raw}`;
}

function CheckBadge() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path className="check" d="M5 13l4 4L19 7" />
    </svg>
  );
}

/** Calm segmented control for a single artifact's disposition. */
function DispositionControl({
  artifactKey,
  state,
  onChange,
}: {
  artifactKey: string;
  state: ArtifactState;
  onChange: (next: ArtifactState) => void;
}) {
  return (
    <div className="disposition">
      <span className="displabel">Did you use this?</span>
      <div
        className="segmented"
        role="radiogroup"
        aria-label={`How you used ${artifactKey}`}
      >
        {DISPOSITIONS.map((d) => {
          const selected = state.disposition === d.value;
          return (
            <button
              key={d.value}
              type="button"
              role="radio"
              aria-checked={selected}
              data-disp={d.value}
              className={selected ? "sel" : ""}
              onClick={() => onChange({ ...state, disposition: d.value })}
            >
              {d.label}
            </button>
          );
        })}
      </div>
      {state.disposition === "edited" && (
        <input
          className="editnote"
          type="text"
          placeholder="Optional: what did you change?"
          value={state.edit_note}
          onChange={(e) => onChange({ ...state, edit_note: e.target.value })}
        />
      )}
    </div>
  );
}

export function LessonPackagePreviewPage({ lesson }: Props) {
  const { loading, error, run } = useAsyncAction();
  const [ratings, setRatings] = useState<Record<string, ArtifactState>>({});
  const [metrics, setMetrics] = useState<DirectUseMetrics | null>(null);
  const [approved, setApproved] = useState(false);

  // Live, optimistic direct-use rate as the teacher rates — recomputed
  // locally; the server value replaces it on approve.
  const live = useMemo(() => {
    const rated = Object.values(ratings).filter((r) => r.disposition);
    const used = rated.filter((r) => r.disposition === "used_as_is").length;
    const rate = rated.length ? used / rated.length : 0;
    return { total: rated.length, used, rate };
  }, [ratings]);

  if (!lesson) {
    return (
      <section className="card rise rise-1">
        <h2>Lesson package preview</h2>
        <StatusMessage tone="hint">
          No package yet — generate one from your session to review it here.
        </StatusMessage>
      </section>
    );
  }

  const lessonId = lesson.id;
  const childId = lesson.child_id;
  const images = lesson.candidate_images ?? [];

  function setArtifact(key: string, next: ArtifactState) {
    setRatings((prev) => ({ ...prev, [key]: next }));
    setApproved(false);
  }

  async function handleApprove() {
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
      setApproved(true);
    }
  }

  const shownRate = metrics ? metrics.direct_use_rate : live.rate;
  const shownTotal = metrics ? metrics.total_rated : live.total;
  const shownUsed = metrics ? metrics.by_disposition.used_as_is : live.used;

  return (
    <section className="grid">
      <div className="orient">
        <span className="stepcount">Step 5 of 6</span>
        <span className="stepwhat">Review each piece, rate it, then approve.</span>
      </div>

      {/* Printable image cards — large, dominant */}
      <div className="card artifact panel lift rise rise-1">
        <div className="arthead">
          <h2>Printable image cards</h2>
          <span className="tag">Teacher-confirmed</span>
        </div>
        <div className="cardpreview">
          {images.length > 0 && resolveImageUrl(images[0]) ? (
            <img src={resolveImageUrl(images[0])!} alt={images[0].title} />
          ) : (
            <div className="placeholder">Image card</div>
          )}
        </div>
        <div className="heroActions left">
          {Object.entries(lesson.downloadable_card_pdf_links).map(
            ([format, href]) => (
              <a className="buttonLink" href={href} key={format}>
                Download {format.toUpperCase()} cards
              </a>
            ),
          )}
        </div>
        <DispositionControl
          artifactKey="image_cards"
          state={ratings.image_cards ?? { edit_note: "" }}
          onChange={(next) => setArtifact("image_cards", next)}
        />
      </div>

      {/* Session flow */}
      <div className="card artifact lift rise rise-2">
        <div className="arthead">
          <h2>Session flow</h2>
          <span className="tag rule">Attention-paced</span>
        </div>
        {lesson.segments.map((segment, index) => (
          <div className="row" key={index}>
            <strong>
              {String(segment.order)}. {String(segment.title)}
            </strong>{" "}
            · <span className="mono">{String(segment.duration_minutes)}</span> min
            <br />
            {String(segment.activity)}
          </div>
        ))}
      </div>

      {/* Teacher script */}
      <div className="card artifact lift rise rise-3">
        <div className="arthead">
          <h2>Teacher script</h2>
          <span className="tag rule">Rule-based draft</span>
        </div>
        <ol>
          {lesson.teacher_script.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ol>
        <DispositionControl
          artifactKey="teacher_script"
          state={ratings.teacher_script ?? { edit_note: "" }}
          onChange={(next) => setArtifact("teacher_script", next)}
        />
      </div>

      {/* Generalization plan */}
      <div className="card artifact lift rise rise-4">
        <div className="arthead">
          <h2>Generalization plan</h2>
          <span className="tag rule">Across people & settings</span>
        </div>
        {lesson.generalization_plan.map((item, index) => (
          <div className="row" key={index}>
            <strong>{String(item.dimension ?? item.type)}</strong>
            <br />
            {Array.isArray(item.examples) ? item.examples.join(" / ") : ""}
          </div>
        ))}
        <DispositionControl
          artifactKey="generalization_plan"
          state={ratings.generalization_plan ?? { edit_note: "" }}
          onChange={(next) => setArtifact("generalization_plan", next)}
        />
      </div>

      {/* Reinforcement plan */}
      <div className="card artifact lift rise rise-5">
        <div className="arthead">
          <h2>Reinforcement plan</h2>
          <span className="tag rule">From this learner's profile</span>
        </div>
        <p className="hint">
          Rotation: {lesson.reinforcement_plan.rotation.join(", ")}
        </p>
        <ul>
          {lesson.reinforcement_plan.schedule.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <DispositionControl
          artifactKey="reinforcement_plan"
          state={ratings.reinforcement_plan ?? { edit_note: "" }}
          onChange={(next) => setArtifact("reinforcement_plan", next)}
        />
      </div>

      {/* Data recording sheet */}
      <div className="card artifact lift rise rise-6">
        <div className="arthead">
          <h2>Data recording sheet</h2>
          <span className="tag rule">For session data</span>
        </div>
        <ul>
          {dataSheetFields(lesson).map((field) => (
            <li key={field}>{field}</li>
          ))}
        </ul>
        <DispositionControl
          artifactKey="data_recording_sheet"
          state={ratings.data_recording_sheet ?? { edit_note: "" }}
          onChange={(next) => setArtifact("data_recording_sheet", next)}
        />
      </div>

      {/* Session notes template */}
      <div className="card artifact lift rise rise-6">
        <div className="arthead">
          <h2>Session notes template</h2>
          <span className="tag rule">Write-up scaffold</span>
        </div>
        <ul>
          {notesSections(lesson).map((section) => (
            <li key={section}>{section}</li>
          ))}
        </ul>
        <DispositionControl
          artifactKey="session_notes_template"
          state={ratings.session_notes_template ?? { edit_note: "" }}
          onChange={(next) => setArtifact("session_notes_template", next)}
        />
      </div>

      {/* Approve + live direct-use rate */}
      <div className="card panel rise rise-6">
        <div className="arthead">
          <h2>Approve &amp; export</h2>
          <span className="tag">Direct-use feedback</span>
        </div>
        <p className="hint">
          Rate each piece above, then approve. Your ratings tell us how much of
          the package you can use as-is.
        </p>

        <div className="durate" aria-live="polite">
          <span className="pct mono">{Math.round(shownRate * 100)}%</span>
          <div className="dubar">
            <span style={{ width: `${Math.round(shownRate * 100)}%` }} />
          </div>
          <span className="pctmeta">
            <span className="mono">{shownUsed}</span> of{" "}
            <span className="mono">{shownTotal}</span> rated pieces used as-is
          </span>
        </div>

        {error && <StatusMessage tone="error">{error}</StatusMessage>}

        <div className="approvebar" style={{ marginTop: 16 }}>
          <button
            type="button"
            className="spark celebrate"
            onClick={handleApprove}
            disabled={loading || live.total === 0}
          >
            {loading ? "Approving…" : "Approve & export"}
          </button>
          {approved && (
            <span className="approved-pill" role="status">
              <span className="celebrate">
                <CheckBadge />
                <span className="confetti" aria-hidden="true">
                  <i style={{ background: "var(--spark)", "--cx": "46px", "--cy": "-34px" } as CSSProperties} />
                  <i style={{ background: "var(--grow)", "--cx": "-30px", "--cy": "-40px" } as CSSProperties} />
                  <i style={{ background: "var(--sky)", "--cx": "52px", "--cy": "20px" } as CSSProperties} />
                  <i style={{ background: "var(--spark)", "--cx": "-44px", "--cy": "12px" } as CSSProperties} />
                </span>
              </span>
              Approved
            </span>
          )}
          {live.total === 0 && !approved && (
            <span className="hint">Rate at least one piece to approve.</span>
          )}
        </div>
      </div>
    </section>
  );
}

function dataSheetFields(lesson: LessonPlanResponse): string[] {
  const sheet = lesson.data_recording_sheet as {
    fields?: { label?: string }[];
  };
  const fields = (sheet.fields ?? [])
    .map((f) => f.label)
    .filter((l): l is string => !!l);
  return fields.length ? fields : ["Independent", "Prompted", "Error", "Notes"];
}

function notesSections(lesson: LessonPlanResponse): string[] {
  const tmpl = lesson.session_notes_template as {
    sections?: { label?: string }[];
  };
  const sections = (tmpl.sections ?? [])
    .map((s) => s.label)
    .filter((l): l is string => !!l);
  return sections.length ? sections : ["What worked", "What to adjust"];
}
