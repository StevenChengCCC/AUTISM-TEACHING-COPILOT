import type { WorkflowStep } from "../types";

const steps: { key: WorkflowStep; label: string }[] = [
  { key: "learner", label: "Learner" },
  { key: "records", label: "Records" },
  { key: "profile", label: "Profile" },
  { key: "lesson", label: "Lesson" },
  { key: "outputs", label: "Outputs" },
];

export function WorkflowStepper({ current }: { current: WorkflowStep }) {
  const currentIndex = steps.findIndex((step) => step.key === current);
  return (
    <ol className="v2-stepper" aria-label="Lesson creation progress">
      {steps.map((step, index) => {
        const completed = index < currentIndex;
        const active = index === currentIndex;
        return (
          <li key={step.key} className={`${completed ? "is-complete" : ""} ${active ? "is-active" : ""}`} aria-current={active ? "step" : undefined}>
            <span className="v2-step-line" aria-hidden="true" />
            <span className="v2-step-number">{completed ? "✓" : index + 1}</span>
            <span className="v2-step-label">{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}
