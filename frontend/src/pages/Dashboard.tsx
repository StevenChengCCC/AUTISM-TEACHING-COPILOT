import { useEffect, useMemo, useState } from "react";
import { ChildProfilesPage } from "./ChildProfiles";
import { CreateLessonPackagePage } from "./CreateLessonPackage";
import { ImagePipelineReviewPage } from "./ImagePipelineReview";
import { LessonPackagePreviewPage } from "./LessonPackagePreview";
import { SessionRecordsPage } from "./SessionRecords";
import { TeachingGoalsPage } from "./TeachingGoals";
import { TeacherWorkflowPage } from "./TeacherWorkflow";
import { api } from "../api/client";
import type {
  ChildProfile,
  ImageCandidate,
  ImagePipelineResult,
  LessonPlanResponse,
  TeachingGoal,
} from "../types";
import "../styles.css";

type PageKey =
  | "workflow"
  | "children"
  | "goals"
  | "images"
  | "lesson"
  | "preview"
  | "records";

export function Dashboard() {
  const [page, setPage] = useState<PageKey>("workflow");
  const [children, setChildren] = useState<ChildProfile[]>([]);
  const [goals, setGoals] = useState<TeachingGoal[]>([]);
  const [selectedChildId, setSelectedChildId] = useState<number | null>(null);
  const [selectedGoalId, setSelectedGoalId] = useState<number | null>(null);
  const [imageResult, setImageResult] = useState<ImagePipelineResult | null>(
    null,
  );
  const [confirmedImages, setConfirmedImages] = useState<ImageCandidate[]>([]);
  const [lesson, setLesson] = useState<LessonPlanResponse | null>(null);

  const selectedChild = useMemo(
    () => children.find((child) => child.id === selectedChildId) ?? null,
    [children, selectedChildId],
  );
  const selectedGoal = useMemo(
    () => goals.find((goal) => goal.id === selectedGoalId) ?? null,
    [goals, selectedGoalId],
  );

  useEffect(() => {
    api
      .listChildren()
      .then(setChildren)
      .catch(() => setChildren([]));
  }, []);

  useEffect(() => {
    if (!selectedChildId && children.length > 0) {
      setSelectedChildId(children[0].id);
    }
  }, [children, selectedChildId]);

  useEffect(() => {
    if (!selectedChildId) {
      setGoals([]);
      return;
    }
    api
      .listGoals(selectedChildId)
      .then(setGoals)
      .catch(() => setGoals([]));
  }, [selectedChildId]);

  useEffect(() => {
    if (selectedGoalId && goals.some((goal) => goal.id === selectedGoalId))
      return;
    setSelectedGoalId(goals[0]?.id ?? null);
  }, [goals, selectedGoalId]);

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Autism Teaching Operating System</p>
          <h1>Teaching Copilot</h1>
          <p>
            Student profile, teaching goal, generalization planning,
            attention-aware flow, reinforcement, image review, and progress
            tracking.
          </p>
        </div>
        <div className="heroActions">
          {(
            [
              "workflow",
              "children",
              "goals",
              "images",
              "lesson",
              "preview",
              "records",
            ] as PageKey[]
          ).map((key) => (
            <button
              className={page === key ? "primary" : ""}
              key={key}
              onClick={() => setPage(key)}
            >
              {pageLabel(key)}
            </button>
          ))}
        </div>
      </header>

      <section className="contextBar">
        <span>
          Child: {selectedChild ? selectedChild.code : "not selected"}
        </span>
        <span>
          Goal: {selectedGoal ? selectedGoal.target_skill : "not selected"}
        </span>
        <span>Confirmed images: {confirmedImages.length}</span>
      </section>

      {page === "workflow" && (
        <TeacherWorkflowPage
          children={children}
          goals={goals}
          selectedChildId={selectedChildId}
          selectedGoalId={selectedGoalId}
          confirmedImages={confirmedImages}
          onSelectChild={setSelectedChildId}
          onGoalsChange={setGoals}
          onSelectGoal={setSelectedGoalId}
          onLessonChange={setLesson}
          onNavigateImages={() => setPage("images")}
          onNavigatePreview={() => setPage("preview")}
        />
      )}
      {page === "children" && (
        <ChildProfilesPage
          children={children}
          selectedChildId={selectedChildId}
          onChildrenChange={setChildren}
          onSelectChild={setSelectedChildId}
        />
      )}
      {page === "goals" && (
        <TeachingGoalsPage
          child={selectedChild}
          goals={goals}
          selectedGoalId={selectedGoalId}
          onGoalsChange={setGoals}
          onSelectGoal={setSelectedGoalId}
        />
      )}
      {page === "images" && (
        <ImagePipelineReviewPage
          child={selectedChild}
          goal={selectedGoal}
          imageResult={imageResult}
          onImageResultChange={setImageResult}
          onConfirmedImagesChange={setConfirmedImages}
        />
      )}
      {page === "lesson" && (
        <CreateLessonPackagePage
          child={selectedChild}
          goal={selectedGoal}
          confirmedImages={confirmedImages}
          onLessonChange={setLesson}
          onNavigatePreview={() => setPage("preview")}
        />
      )}
      {page === "preview" && <LessonPackagePreviewPage lesson={lesson} />}
      {page === "records" && (
        <SessionRecordsPage
          child={selectedChild}
          goal={selectedGoal}
          onGoalsRefresh={setGoals}
        />
      )}
    </main>
  );
}

function pageLabel(page: PageKey): string {
  return {
    children: "Child Profiles",
    workflow: "Workflow",
    goals: "Teaching Goals",
    images: "Image Review",
    lesson: "Create Package",
    preview: "Preview",
    records: "Session Records",
  }[page];
}
