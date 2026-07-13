import { useState } from "react";
import { AppShell } from "./components/AppShell";
import { LessonPackageReadyPage } from "./pages/LessonPackageReadyPage";
import { MaterialsPage } from "./pages/MaterialsPage";
import { ModifyLessonContentPage } from "./pages/ModifyLessonContentPage";
import { DeveloperAISettingsPage } from "./pages/DeveloperAISettingsPage";
import { PlanWithAIChatPage } from "./pages/PlanWithAIChatPage";
import { ReviewLearnerPage } from "./pages/ReviewLearnerPage";
import { ReviewPrintableContentPage } from "./pages/ReviewPrintableContentPage";
import { SessionsPage } from "./pages/SessionsPage";
import { StartNewLessonPage } from "./pages/StartNewLessonPage";
import { StudentsPage } from "./pages/StudentsPage";
import { UploadRecordsPage } from "./pages/UploadRecordsPage";
import { lessonKitApi } from "./api/lessonKitApi";
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

export function LessonKitStudioApp() {
  const [page, setPage] = useState<StudioPage>("home");
  const [learnerId, setLearnerId] = useState("a102");
  const [lessonPackage, setLessonPackage] = useState<LessonPackage | null>(null);
  const [feedbackMessage, setFeedbackMessage] = useState("");

  const navigateTo=(next:StudioPage)=>{setFeedbackMessage("");setPage(next);};
  const startExistingLearnerFlow=(id:string)=>{setLearnerId(id);navigateTo("reviewLearnerExisting");};
  const startNewLearnerFlow=()=>{setLearnerId("n501");navigateTo("uploadRecords");};
  async function resumeSession(session:LessonSession) {
    setLearnerId(session.learnerId);
    if(session.status==="draft") { navigateTo("planWithAIChat"); return; }
    const emptyChat=await lessonKitApi.getInitialLessonChat(session.learnerId);
    const chat=await lessonKitApi.submitLessonRequest(emptyChat.conversationId,session.learnerId,`I want to teach ${session.goal.toLowerCase()}.`,emptyChat.draft);
    const generated=await lessonKitApi.generateLessonPackageFromDraft(chat.draft);
    setLessonPackage(generated);
    navigateTo(session.status==="in_progress"?"reviewPrintableContent":"lessonPackageReady");
  }

  return (
    <AppShell page={page} step={workflowSteps[page]} onNavigate={navigateTo}>
      {feedbackMessage&&<div className="v2-global-feedback" role="status">✓ {feedbackMessage}<button onClick={()=>setFeedbackMessage("")} aria-label="Dismiss message">×</button></div>}
      {page === "home" && <StartNewLessonPage onSelectExisting={startExistingLearnerFlow} onCreateNew={startNewLearnerFlow} onFeedback={setFeedbackMessage} />}
      {page === "uploadRecords" && <UploadRecordsPage learnerId={learnerId} onContinue={() => navigateTo("reviewLearnerNew")} onFeedback={setFeedbackMessage} />}
      {page === "reviewLearnerExisting" && <ReviewLearnerPage learnerId={learnerId} isNew={false} onContinue={() => navigateTo("planWithAIChat")} onFeedback={setFeedbackMessage} />}
      {page === "reviewLearnerNew" && <ReviewLearnerPage learnerId={learnerId} isNew onBack={() => navigateTo("uploadRecords")} onContinue={() => navigateTo("planWithAIChat")} onFeedback={setFeedbackMessage} />}
      {page === "planWithAIChat" && <PlanWithAIChatPage learnerId={learnerId} onGenerate={(value) => { setLessonPackage(value); navigateTo("lessonPackageReady"); }} onViewProfile={() => navigateTo("reviewLearnerExisting")} onChangeLearner={() => navigateTo("home")} onFeedback={setFeedbackMessage} />}
      {page === "lessonPackageReady" && <LessonPackageReadyPage lessonPackage={lessonPackage} onModify={() => navigateTo("modifyLessonContent")} onReview={() => navigateTo("reviewPrintableContent")} onEdit={() => navigateTo("planWithAIChat")} onStartOver={() => navigateTo("home")} onFeedback={setFeedbackMessage} />}
      {page === "modifyLessonContent" && <ModifyLessonContentPage lessonPackage={lessonPackage} onBack={() => navigateTo("lessonPackageReady")} onContinue={() => navigateTo("reviewPrintableContent")} onSave={setLessonPackage} onFeedback={setFeedbackMessage} />}
      {page === "reviewPrintableContent" && <ReviewPrintableContentPage lessonPackage={lessonPackage} onBack={() => {if(!lessonPackage){navigateTo("lessonPackageReady");return;}void lessonKitApi.getLessonPackage(lessonPackage.id).then((value)=>{setLessonPackage(value);navigateTo("lessonPackageReady");});}} onFeedback={setFeedbackMessage} />}
      {page === "students" && <StudentsPage onStartLesson={startExistingLearnerFlow} onCreateLearner={startNewLearnerFlow} onFeedback={setFeedbackMessage} />}
      {page === "sessions" && <SessionsPage onNewSession={() => navigateTo("home")} onResume={(session)=>void resumeSession(session)} onFeedback={setFeedbackMessage} />}
      {page === "materials" && <MaterialsPage onUseInLesson={() => {setLearnerId("a102");navigateTo("planWithAIChat");}} onCreateMaterial={()=>setFeedbackMessage("Custom material template created.")} onFeedback={setFeedbackMessage} />}
      {page === "developerAI" && import.meta.env.DEV && <DeveloperAISettingsPage />}
    </AppShell>
  );
}
