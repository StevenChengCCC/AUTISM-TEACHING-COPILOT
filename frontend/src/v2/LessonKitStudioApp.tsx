import { useEffect, useState } from "react";
import { lessonKitApi } from "./api/lessonKitApi";
import { BRAND } from "./brand";
import { AppShell } from "./components/AppShell";
import { BrandMark } from "./components/BrandMark";
import { DeveloperAISettingsPage } from "./pages/DeveloperAISettingsPage";
import { LessonPackageReadyPage } from "./pages/LessonPackageReadyPage";
import { MaterialsPage } from "./pages/MaterialsPage";
import { ModifyLessonContentPage } from "./pages/ModifyLessonContentPage";
import { PlanWithAIChatPage } from "./pages/PlanWithAIChatPage";
import { ReviewLearnerPage } from "./pages/ReviewLearnerPage";
import { ReviewPrintableContentPage } from "./pages/ReviewPrintableContentPage";
import { SessionsPage } from "./pages/SessionsPage";
import { StartNewLessonPage } from "./pages/StartNewLessonPage";
import { StudentsPage } from "./pages/StudentsPage";
import { UploadRecordsPage } from "./pages/UploadRecordsPage";
import type { LessonPackage, LessonSession, StudioPage, WorkflowStep } from "./types";
import "./styles.css";

const workflowSteps: Partial<Record<StudioPage, WorkflowStep>> = {
  home: "learner",
  uploadRecords: "records",
  reviewLearnerExisting: "profile",
  reviewLearnerNew: "profile",
  planWithAIChat: "lesson",
  lessonPackageReady: "outputs",
  modifyLessonContent: "outputs",
  reviewPrintableContent: "outputs",
};

const resumablePages: StudioPage[] = [
  "students", "sessions", "materials", "lessonPackageReady",
  "modifyLessonContent", "reviewPrintableContent",
];

export function AutismTeachingCopilotApp() {
  const storedPage = sessionStorage.getItem("autism-teaching-copilot.page") as StudioPage | null;
  const [page, setPage] = useState<StudioPage>(storedPage && resumablePages.includes(storedPage) ? storedPage : "home");
  const [learnerId, setLearnerId] = useState(sessionStorage.getItem("autism-teaching-copilot.learner-id") ?? "a102");
  const [lessonPackage, setLessonPackage] = useState<LessonPackage | null>(null);
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const [restoring, setRestoring] = useState(true);

  useEffect(() => {
    sessionStorage.setItem("autism-teaching-copilot.page", page);
    sessionStorage.setItem("autism-teaching-copilot.learner-id", learnerId);
  }, [page, learnerId]);

  useEffect(() => {
    const packageId = sessionStorage.getItem("autism-teaching-copilot.package-id");
    if (!packageId) { setRestoring(false); return; }
    void lessonKitApi.getLessonPackage(packageId)
      .then(setLessonPackage)
      .catch(() => {
        sessionStorage.removeItem("autism-teaching-copilot.package-id");
        if (["lessonPackageReady", "modifyLessonContent", "reviewPrintableContent"].includes(page)) setPage("home");
      })
      .finally(() => setRestoring(false));
  }, []);

  const savePackage = (value: LessonPackage | null) => {
    setLessonPackage(value);
    if (value) sessionStorage.setItem("autism-teaching-copilot.package-id", value.id);
    else sessionStorage.removeItem("autism-teaching-copilot.package-id");
  };
  const navigateTo = (next: StudioPage) => { setFeedbackMessage(""); setPage(next); };
  const startExistingLearnerFlow = (id: string) => { setLearnerId(id); navigateTo("reviewLearnerExisting"); };
  const startNewLearnerFlow = () => {
    void lessonKitApi.createLearner({
      code:`Learner N-${String(Date.now()).slice(-3)}`,
      age:7,
      avatar:"🧒🏻",
      tags:["Visual prompts","Short phrases"],
      interests:[],
      supportNeeds:["Visual prompts"],
      reinforcementPreferences:[],
      communicationMode:"Short phrases",
      attentionProfile:"Short, structured activities",
      notes:"Teacher review pending.",
    }).then((learner)=>{setLearnerId(learner.id);navigateTo("uploadRecords");}).catch((error)=>setFeedbackMessage(error instanceof Error?error.message:"A learner draft could not be created."));
  };

  async function resumeSession(session: LessonSession) {
    setLearnerId(session.learnerId);
    if (session.status === "draft") { navigateTo("planWithAIChat"); return; }
    try {
      const existing = await lessonKitApi.getLessonPackages(session.learnerId);
      const saved = existing.find((item) => item.goal === session.goal) ?? existing[0];
      if (saved) {
        savePackage(saved);
        navigateTo(session.status === "in_progress" ? "reviewPrintableContent" : "lessonPackageReady");
        return;
      }
      navigateTo("planWithAIChat");
    } catch (error) {
      setFeedbackMessage(error instanceof Error ? error.message : "The session could not be resumed.");
    }
  }

  if (restoring) return <main className="v2-auth-loading" aria-live="polite"><BrandMark decorative={false} /><span className="v2-spinner" /><span>Restoring your {BRAND.shortName} workspace…</span></main>;

  return (
    <AppShell page={page} step={workflowSteps[page]} onNavigate={navigateTo}>
      {feedbackMessage && <div className="v2-global-feedback" role="status" aria-live="polite">{feedbackMessage}<button onClick={() => setFeedbackMessage("")} aria-label="Dismiss message">×</button></div>}
      {page === "home" && <StartNewLessonPage onSelectExisting={startExistingLearnerFlow} onCreateNew={startNewLearnerFlow} onFeedback={setFeedbackMessage} />}
      {page === "uploadRecords" && <UploadRecordsPage learnerId={learnerId} onContinue={() => navigateTo("reviewLearnerNew")} onFeedback={setFeedbackMessage} />}
      {page === "reviewLearnerExisting" && <ReviewLearnerPage learnerId={learnerId} isNew={false} onContinue={() => navigateTo("planWithAIChat")} onFeedback={setFeedbackMessage} />}
      {page === "reviewLearnerNew" && <ReviewLearnerPage learnerId={learnerId} isNew onBack={() => navigateTo("uploadRecords")} onContinue={() => navigateTo("planWithAIChat")} onFeedback={setFeedbackMessage} />}
      {page === "planWithAIChat" && <PlanWithAIChatPage learnerId={learnerId} onGenerate={(value) => { savePackage(value); navigateTo("lessonPackageReady"); }} onViewProfile={() => navigateTo("reviewLearnerExisting")} onChangeLearner={() => navigateTo("home")} onFeedback={setFeedbackMessage} />}
      {page === "lessonPackageReady" && <LessonPackageReadyPage lessonPackage={lessonPackage} onModify={() => navigateTo("modifyLessonContent")} onReview={() => navigateTo("reviewPrintableContent")} onEdit={() => navigateTo("planWithAIChat")} onStartOver={() => { savePackage(null); navigateTo("home"); }} onSave={savePackage} onFeedback={setFeedbackMessage} />}
      {page === "modifyLessonContent" && <ModifyLessonContentPage lessonPackage={lessonPackage} onBack={() => navigateTo("lessonPackageReady")} onContinue={() => navigateTo("reviewPrintableContent")} onSave={savePackage} onFeedback={setFeedbackMessage} />}
      {page === "reviewPrintableContent" && <ReviewPrintableContentPage lessonPackage={lessonPackage} onBack={() => { if (!lessonPackage) { navigateTo("lessonPackageReady"); return; } void lessonKitApi.getLessonPackage(lessonPackage.id).then((value) => { savePackage(value); navigateTo("lessonPackageReady"); }); }} onFeedback={setFeedbackMessage} />}
      {page === "students" && <StudentsPage onStartLesson={startExistingLearnerFlow} onCreateLearner={startNewLearnerFlow} onFeedback={setFeedbackMessage} />}
      {page === "sessions" && <SessionsPage onNewSession={() => navigateTo("home")} onResume={(session) => void resumeSession(session)} onFeedback={setFeedbackMessage} />}
      {page === "materials" && <MaterialsPage onUseInLesson={() => { setLearnerId("a102"); navigateTo("planWithAIChat"); }} onCreateMaterial={() => setFeedbackMessage("Custom material template created.")} onFeedback={setFeedbackMessage} />}
      {page === "developerAI" && import.meta.env.DEV && <DeveloperAISettingsPage />}
    </AppShell>
  );
}
