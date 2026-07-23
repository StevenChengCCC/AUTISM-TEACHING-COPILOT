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
  "home", "uploadRecords", "reviewLearnerExisting", "reviewLearnerNew",
  "planWithAIChat", "students", "sessions", "materials",
  "lessonPackageReady", "modifyLessonContent", "reviewPrintableContent",
];

const packagePages: StudioPage[] = [
  "lessonPackageReady", "modifyLessonContent", "reviewPrintableContent",
];

const learnerPages: StudioPage[] = [
  "uploadRecords", "reviewLearnerExisting", "reviewLearnerNew", "planWithAIChat",
];

export function AutismTeachingCopilotApp() {
  const storedPage = sessionStorage.getItem("autism-teaching-copilot.page") as StudioPage | null;
  const [page, setPage] = useState<StudioPage>(storedPage && resumablePages.includes(storedPage) ? storedPage : "home");
  const [learnerId, setLearnerId] = useState(sessionStorage.getItem("autism-teaching-copilot.learner-id") ?? "");
  const [lessonPackage, setLessonPackage] = useState<LessonPackage | null>(null);
  const [resumeLessonChat, setResumeLessonChat] = useState(storedPage === "planWithAIChat");
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const [restoring, setRestoring] = useState(true);

  useEffect(() => {
    sessionStorage.setItem("autism-teaching-copilot.page", page);
    sessionStorage.setItem("autism-teaching-copilot.learner-id", learnerId);
  }, [page, learnerId]);

  useEffect(() => {
    async function restoreWorkspace() {
      try {
        if (learnerPages.includes(page)) {
          if (!learnerId) {
            setPage("home");
            return;
          }
          await lessonKitApi.getLearnerById(learnerId);
        }
        const packageId = sessionStorage.getItem("autism-teaching-copilot.package-id");
        if (packagePages.includes(page) && !packageId) {
          setPage("home");
          return;
        }
        if (packageId) setLessonPackage(await lessonKitApi.getLessonPackage(packageId));
      } catch {
        sessionStorage.removeItem("autism-teaching-copilot.package-id");
        if (packagePages.includes(page) || learnerPages.includes(page)) setPage("home");
      } finally {
        setRestoring(false);
      }
    }
    void restoreWorkspace();
  }, []);

  const savePackage = (value: LessonPackage | null) => {
    setLessonPackage(value);
    if (value) sessionStorage.setItem("autism-teaching-copilot.package-id", value.id);
    else sessionStorage.removeItem("autism-teaching-copilot.package-id");
  };
  const navigateTo = (next: StudioPage) => { setFeedbackMessage(""); setPage(next); };
  const openLessonChat = (resumeExisting: boolean) => {
    setResumeLessonChat(resumeExisting);
    navigateTo("planWithAIChat");
  };
  const startExistingLearnerFlow = (id: string) => { setLearnerId(id); navigateTo("reviewLearnerExisting"); };
  const startNewLearnerFlow = () => {
    void lessonKitApi.createLearner({
      code:`Learner N-${String(Date.now()).slice(-6)}`,
      age:0,
      avatar:"🧒🏻",
      tags:[],
      interests:[],
      supportNeeds:[],
      reinforcementPreferences:[],
      communicationMode:"",
      attentionProfile:"",
      notes:"",
    }).then((learner)=>{setLearnerId(learner.id);navigateTo("uploadRecords");}).catch((error)=>setFeedbackMessage(error instanceof Error?error.message:"A learner draft could not be created."));
  };

  async function resumeSession(session: LessonSession) {
    setLearnerId(session.learnerId);
    if (session.status === "draft") { openLessonChat(true); return; }
    try {
      const existing = await lessonKitApi.getLessonPackages(session.learnerId);
      const saved = existing.find((item) => item.goal === session.goal) ?? existing[0];
      if (saved) {
        savePackage(saved);
        navigateTo(session.status === "in_progress" ? "reviewPrintableContent" : "lessonPackageReady");
        return;
      }
      openLessonChat(true);
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
      {page === "reviewLearnerExisting" && <ReviewLearnerPage learnerId={learnerId} isNew={false} onContinue={() => openLessonChat(false)} onFeedback={setFeedbackMessage} />}
      {page === "reviewLearnerNew" && <ReviewLearnerPage learnerId={learnerId} isNew onBack={() => navigateTo("uploadRecords")} onContinue={() => openLessonChat(false)} onFeedback={setFeedbackMessage} />}
      {page === "planWithAIChat" && <PlanWithAIChatPage learnerId={learnerId} resumeExisting={resumeLessonChat} onGenerate={(value) => { savePackage(value); navigateTo("lessonPackageReady"); }} onViewProfile={() => navigateTo("reviewLearnerExisting")} onChangeLearner={() => navigateTo("home")} onFeedback={setFeedbackMessage} />}
      {page === "lessonPackageReady" && <LessonPackageReadyPage lessonPackage={lessonPackage} onModify={() => navigateTo("modifyLessonContent")} onReview={() => navigateTo("reviewPrintableContent")} onEdit={() => openLessonChat(true)} onStartOver={() => { savePackage(null); navigateTo("home"); }} onSave={savePackage} onFeedback={setFeedbackMessage} />}
      {page === "modifyLessonContent" && <ModifyLessonContentPage lessonPackage={lessonPackage} onBack={() => navigateTo("lessonPackageReady")} onContinue={() => navigateTo("reviewPrintableContent")} onSave={savePackage} onFeedback={setFeedbackMessage} />}
      {page === "reviewPrintableContent" && <ReviewPrintableContentPage lessonPackage={lessonPackage} onBack={() => { if (!lessonPackage) { navigateTo("lessonPackageReady"); return; } void lessonKitApi.getLessonPackage(lessonPackage.id).then((value) => { savePackage(value); navigateTo("lessonPackageReady"); }); }} onFeedback={setFeedbackMessage} />}
      {page === "students" && <StudentsPage onStartLesson={startExistingLearnerFlow} onCreateLearner={startNewLearnerFlow} onFeedback={setFeedbackMessage} />}
      {page === "sessions" && <SessionsPage onNewSession={() => navigateTo("home")} onResume={(session) => void resumeSession(session)} onFeedback={setFeedbackMessage} />}
      {page === "materials" && <MaterialsPage onUseInLesson={() => learnerId ? openLessonChat(false) : navigateTo("home")} onCreateMaterial={() => setFeedbackMessage("Custom material template created.")} onFeedback={setFeedbackMessage} />}
      {page === "developerAI" && import.meta.env.DEV && <DeveloperAISettingsPage />}
    </AppShell>
  );
}
