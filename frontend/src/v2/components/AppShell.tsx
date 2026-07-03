import type { ReactNode } from "react";
import type { StudioPage, WorkflowStep } from "../types";
import { TopNav } from "./TopNav";
import { WorkflowStepper } from "./WorkflowStepper";

export function AppShell({ page, step, onNavigate, children }: { page: StudioPage; step?: WorkflowStep; onNavigate: (page: StudioPage) => void; children: ReactNode }) {
  return (
    <div className="lesson-kit-studio">
      <TopNav page={page} onNavigate={onNavigate} />
      {step && <div className="v2-stepper-wrap"><WorkflowStepper current={step} /></div>}
      <main className={`v2-page ${step ? "v2-page--workflow" : ""}`}>{children}</main>
    </div>
  );
}
