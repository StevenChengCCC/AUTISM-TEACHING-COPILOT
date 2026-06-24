import { StatusMessage } from "../components/StatusMessage";
import type { LessonPlanResponse } from "../types";

type Props = {
  lesson: LessonPlanResponse | null;
};

export function LessonPackagePreviewPage({ lesson }: Props) {
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
    </section>
  );
}
