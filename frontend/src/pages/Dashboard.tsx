import { useEffect, useMemo, useState } from "react";
import { ChildProfilesPage } from "./ChildProfiles";
import { CreateLessonPackagePage } from "./CreateLessonPackage";
import { ImagePipelineReviewPage } from "./ImagePipelineReview";
import { LessonPackagePreviewPage } from "./LessonPackagePreview";
import { MaterialsPage } from "./Materials";
import { OrganizationManagementPage } from "./OrganizationManagement";
import { SessionRecordsPage } from "./SessionRecords";
import { TeachingGoalsPage } from "./TeachingGoals";
import { TeacherAccessManagementPage } from "./TeacherAccessManagement";
import { TeacherWorkflowPage } from "./TeacherWorkflow";
import { CurriculumContentPage } from "./CurriculumContent";
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
type ManagementPageKey =
  | "materials"
  | "organizations"
  | "access"
  | "curriculum";
type AnyPageKey = PageKey | ManagementPageKey;

export function Dashboard() {
  const [page, setPage] = useState<AnyPageKey>("workflow");
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

  const steps: SessionStep[] = [
    {
      page: "children",
      title: "Add a child",
      done: !!selectedChild,
      meta: selectedChild ? selectedChild.code : "Pick or create a learner",
    },
    {
      page: "goals",
      title: "Set the goal",
      enabled: !!selectedChild,
      done: !!selectedGoal,
      meta: selectedGoal ? selectedGoal.target_skill : "Choose a teaching goal",
    },
    {
      page: "images",
      title: "Review images",
      enabled: !!selectedGoal,
      done: confirmedImages.length > 0,
      meta:
        confirmedImages.length > 0
          ? `${confirmedImages.length} confirmed`
          : "Confirm picture cards",
    },
    {
      page: "workflow",
      title: "Generate package",
      enabled: !!selectedGoal && confirmedImages.length > 0,
      done: !!lesson,
      meta: lesson ? "Ready to review" : "Build the lesson",
    },
    {
      page: "preview",
      title: "Review & approve",
      enabled: !!lesson,
      done: false,
      meta: lesson ? "Read, rate, export" : "Waiting on a package",
    },
    {
      page: "records",
      title: "Record the session",
      enabled: !!selectedGoal,
      done: false,
      meta: "After you teach it",
    },
  ];

  const currentStep =
    steps.find((s) => s.page === page) ?? steps.find((s) => !s.done);

  return (
    <main className="app">
      <aside className="sidebar">
        <div className="brand">
          <p className="eyebrow">Teaching copilot</p>
          <h1>Plan a session</h1>
          <p>A ready-to-print lesson, fast.</p>
        </div>

        <nav className="steppath" aria-label="Session steps">
          <p className="pathlabel">Your session</p>
          {steps.map((step) => {
            const isCurrent = currentStep?.page === step.page;
            const cls = [
              "step",
              step.done ? "done" : "",
              isCurrent ? "current" : "",
            ]
              .filter(Boolean)
              .join(" ");
            return (
              <button
                key={step.page}
                className={cls}
                disabled={step.enabled === false}
                aria-current={isCurrent ? "step" : undefined}
                onClick={() => setPage(step.page)}
              >
                <span className="dot">
                  {step.done ? <CheckIcon /> : steps.indexOf(step) + 1}
                </span>
                <span className="steptext">
                  <span className="steptitle">{step.title}</span>
                  <span className="stepmeta">{step.meta}</span>
                </span>
              </button>
            );
          })}
        </nav>

        <hr className="sidebar-divider" />
        <div className="manage-nav" aria-label="Manage">
          <p className="pathlabel">Manage</p>
          {(
            [
              "materials",
              "lesson",
              "organizations",
              "access",
              "curriculum",
            ] as AnyPageKey[]
          ).map((key) => (
            <button
              key={key}
              className={page === key ? "active" : ""}
              onClick={() => setPage(key)}
            >
              {pageLabel(key)}
            </button>
          ))}
        </div>
      </aside>

      <div className="work">
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
          onContinue={() => setPage("goals")}
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
      {page === "materials" && <MaterialsPage child={selectedChild} />}
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
        {page === "organizations" && <OrganizationManagementPage />}
        {page === "access" && (
          <TeacherAccessManagementPage children={children} />
        )}
        {page === "curriculum" && <CurriculumContentPage />}
      </div>
    </main>
  );
}

type SessionStep = {
  page: AnyPageKey;
  title: string;
  meta: string;
  done: boolean;
  enabled?: boolean;
};

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M5 13l4 4L19 7"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function pageLabel(page: AnyPageKey): string {
  return {
    children: "Child profiles",
    workflow: "Workflow",
    goals: "Teaching goals",
    materials: "Materials",
    images: "Image review",
    lesson: "Create package",
    preview: "Preview",
    records: "Session records",
    organizations: "Organizations",
    access: "Teacher access",
    curriculum: "Curriculum",
  }[page];
}
