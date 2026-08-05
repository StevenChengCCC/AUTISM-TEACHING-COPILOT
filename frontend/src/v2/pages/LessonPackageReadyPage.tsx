import { useCallback,useEffect,useRef,useState } from "react";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { LearnerAvatar } from "../components/Avatar";
import { lessonKitApi } from "../api/lessonKitApi";
import { resolveBackendAssetUrl } from "../api/backendClient";
import type { GenerationJob,LearnerProfile,LessonPackage,PackagePrintReadiness,PackagePrintReadinessBlocker,PrintPreset,PrintPresetCatalog,PrintTextProfile } from "../types";
import { TeacherHandoffExportPanel } from "../components/TeacherHandoffExportPanel";
import { PrintableMaterialCanvas } from "../components/PrintableMaterialCanvas";
import { executePdfArtifactDownload,initialPdfDownloadState } from "../pdfDownload";
import type { PdfDownloadState } from "../types";
import { buildClassroomRunSheet } from "../classroomRunSheetModel";
import { ClassroomRunSheetPreview } from "../components/ClassroomRunSheetPreview";
import { PrintReadinessPanel } from "../components/PrintReadinessPanel";
import { PrintPresetPicker } from "../components/PrintPresetPicker";
import { printPresetLabels,readSelectedPageSize,readSelectedPrintPreset,readSelectedTextProfile,rememberPrintableArtifact,rememberSelectedPageSize,rememberSelectedPrintPreset,rememberSelectedTextProfile } from "../printPresetModel";

const visualTypes=new Set(["quantity_cards","number_cards","visual_card","scenario_cards","sequence_cards","social_narrative","core_word_board","visual_schedule","task_analysis_cards","emotion_scale","sorting_page","matching_page","choice_board","first_then_board","help_card","break_card","teacher_cue_card","token_board"]);
function materialVisualsReady(material:LessonPackage["materials"][number]):boolean {
  if(!visualTypes.has(material.type))return true;
  const items=material.content.visualItems;
  if(Array.isArray(items)&&items.length>0)return items.every((item)=>{
    if(!item||typeof item!=="object")return false;
    const value=item as Record<string,unknown>;
    return Boolean(value.imageUrl||value.imageBase64)&&!["pending","processing","failed","not_started"].includes(String(value.generationStatus??""));
  });
  return Boolean(material.content.imageUrl||material.content.imageBase64);
}
function materialRevisionApproved(material:LessonPackage["materials"][number]):boolean {
  if(material.status!=="approved")return false;
  if(!material.materialSpec)return true;
  return material.materialSpec.approval.status==="approved"&&material.materialSpec.approval.approvedRevision===material.materialSpec.revision;
}

export function LessonPackageReadyPage({ lessonPackage,onModify,onReview,onEdit,onStartOver,onSave,onFeedback }:{ lessonPackage:LessonPackage|null;onModify:()=>void;onReview:(materialId?:string)=>void;onEdit:()=>void;onStartOver:()=>void;onSave:(value:LessonPackage)=>void;onFeedback:(message:string)=>void }) {
  const [learner,setLearner]=useState<LearnerProfile|null>(null);
  const [generationJob,setGenerationJob]=useState<GenerationJob|null>(null);
  const [printReadiness,setPrintReadiness]=useState<PackagePrintReadiness|null>(null);
  const [printPresetCatalog,setPrintPresetCatalog]=useState<PrintPresetCatalog|null>(null);
  const [printPreset,setPrintPreset]=useState<PrintPreset>(()=>lessonPackage?readSelectedPrintPreset(lessonPackage.id):"complete_kit");
  const [printBusy,setPrintBusy]=useState(false);const [retryingId,setRetryingId]=useState("");const [pageSize,setPageSize]=useState<"Letter"|"A4">(()=>lessonPackage?readSelectedPageSize(lessonPackage.id):"Letter");
  const [textProfile,setTextProfile]=useState<PrintTextProfile>(()=>lessonPackage?readSelectedTextProfile(lessonPackage.id):"standard");
  const [pdfDownload,setPdfDownload]=useState<PdfDownloadState>(initialPdfDownloadState);
  const automaticApprovalAttempts=useRef(new Set<string>());
  useEffect(()=>{if(lessonPackage)void lessonKitApi.getLearnerById(lessonPackage.learnerId).then(setLearner);},[lessonPackage]);
  const refreshPrintReadiness=useCallback(async()=>{if(!lessonPackage)return null;const value=await lessonKitApi.getPackagePrintReadiness(lessonPackage.id);setPrintReadiness(value);return value;},[lessonPackage?.id]);
  useEffect(()=>{setPrintReadiness(null);void refreshPrintReadiness();},[refreshPrintReadiness,lessonPackage?.version]);
  useEffect(()=>{if(!lessonPackage)return;setPrintPreset(readSelectedPrintPreset(lessonPackage.id));setPageSize(readSelectedPageSize(lessonPackage.id));setTextProfile(readSelectedTextProfile(lessonPackage.id));},[lessonPackage?.id]);
  useEffect(()=>{if(!lessonPackage)return;let active=true;setPrintPresetCatalog(null);void lessonKitApi.getPrintPresetCatalog(lessonPackage.id,pageSize,textProfile).then((value)=>{if(active)setPrintPresetCatalog(value);}).catch((reason)=>{if(active)onFeedback(reason instanceof Error?reason.message:"Print choices could not be loaded.");});return()=>{active=false;};},[lessonPackage?.id,lessonPackage?.version,pageSize,textProfile]);
  useEffect(()=>{
    if(!lessonPackage)return;
    let cancelled=false;let timer:number|undefined;
    const schedule=()=>{if(!cancelled)timer=window.setTimeout(()=>void refresh(),2500);};
    const refresh=async()=>{try{
      const job=await lessonKitApi.getPackageGenerationJob(lessonPackage.id);
      if(cancelled)return;
      setGenerationJob(job);
      if(["pending","in_progress"].includes(job.status)){schedule();return;}
      const updated=await lessonKitApi.getLessonPackage(lessonPackage.id);
      if(cancelled)return;
      onSave(updated);
      await refreshPrintReadiness();
    }catch{
      // A transient generation-job lookup must not freeze the package on an old
      // revision. Historical packages are harmlessly retried in the background.
      schedule();
    }};
    void refresh();return()=>{cancelled=true;if(timer)window.clearTimeout(timer);};
  },[lessonPackage?.id]);
  const imageStateKey=lessonPackage?.materials.map((item)=>String(item.content.imageGenerationStatus??"")).join("|")??"";
  useEffect(()=>{
    if(!lessonPackage||!lessonPackage.materials.some((item)=>["pending","processing"].includes(String(item.content.imageGenerationStatus??""))))return;
    let cancelled=false;
    const refresh=async()=>{try{const updated=await lessonKitApi.getLessonPackage(lessonPackage.id);if(!cancelled){onSave(updated);void refreshPrintReadiness();}}catch{/* Keep the package usable while artwork continues in the background. */}};
    const timer=window.setInterval(()=>void refresh(),3000);
    void refresh();
    return()=>{cancelled=true;window.clearInterval(timer);};
  },[lessonPackage?.id,imageStateKey,refreshPrintReadiness]);
  const materialApprovalKey=lessonPackage?.materials.map((item)=>`${item.id}:${item.status}:${item.materialSpec?.revision??item.version}:${item.materialSpec?.approval.approvedRevision??0}`).join("|")??"";
  useEffect(()=>{
    if(!lessonPackage||!printReadiness||printReadiness.ready||!lessonPackage.materials.length||!lessonPackage.materials.every(materialRevisionApproved))return;
    const needsTeacherContent=printReadiness.blockers.some((item)=>item.materialId||["generation_job_incomplete","generation_job_failed","pending_visual","failed_required_visual","safety_validation_failure"].includes(item.category));
    if(needsTeacherContent)return;
    const attemptKey=`${lessonPackage.id}:${printReadiness.packageRevision}:${materialApprovalKey}`;
    if(automaticApprovalAttempts.current.has(attemptKey))return;
    automaticApprovalAttempts.current.add(attemptKey);
    let cancelled=false;
    void (async()=>{try{
      const latest=await lessonKitApi.getLessonPackage(lessonPackage.id);
      const approved=latest.status==="approved"?latest:await lessonKitApi.approveLessonPackage(latest.id,latest.version??1,"Teacher approved every current printable material revision");
      if(cancelled)return;
      onSave(approved);
      const readiness=await refreshPrintReadiness();
      if(!cancelled&&readiness?.ready)onFeedback("All teacher-approved pages are ready to download.");
    }catch(reason){if(!cancelled)onFeedback(reason instanceof Error?reason.message:"The approved package could not be finalized.");}})();
    return()=>{cancelled=true;};
  },[lessonPackage?.id,materialApprovalKey,printReadiness?.packageRevision,printReadiness?.ready,refreshPrintReadiness,onSave,onFeedback]);
  if(!lessonPackage)return <section className="v2-empty"><h2>No lesson package yet</h2><Button onClick={onStartOver}>Start a New Lesson</Button></section>;
  const goalTitle=lessonPackage.goal.toLowerCase().includes("ask for help")?"Asking for Help":lessonPackage.goal;
  const summaryMaterial=lessonPackage.materials.find((item)=>item.type==="summary_template");
  const summaryPrompts=Array.isArray(summaryMaterial?.content.prompts)?summaryMaterial.content.prompts:[];
  const appliedEdits=lessonPackage.safetyReview?.appliedEdits??[];
  const standardsChecks=lessonPackage.standardsChecks??[];
  const qualityScore=lessonPackage.qualityScore;
  const localMock=lessonPackage.generationStatus==="local_mock"||lessonPackage.generationMetadata?.outputSource==="local_mock";
  const blocked=printReadiness ? !printReadiness.ready : true;
  const classroomRunSheet=buildClassroomRunSheet(lessonPackage,learner?.code??"Learner");
  const refreshPackageState=async()=>{const updated=await lessonKitApi.getLessonPackage(lessonPackage.id);onSave(updated);return refreshPrintReadiness();};
  const retryVisual=async(materialId:string)=>{setRetryingId(materialId);try{await lessonKitApi.generateGeneratedMaterialImage(materialId);onFeedback("New custom visuals are being created for this material.");const updated=await lessonKitApi.getLessonPackage(lessonPackage.id);onSave(updated);await refreshPrintReadiness();}catch(reason){onFeedback(reason instanceof Error?reason.message:"Custom visuals could not be restarted.");}finally{setRetryingId("");}};
  const fixReadiness=async(item:PackagePrintReadinessBlocker)=>{if(item.materialId){onReview(item.materialId);return;}setPrintBusy(true);try{if(item.recoveryAction==="approve_package"){const latest=await lessonKitApi.getLessonPackage(lessonPackage.id);const approved=await lessonKitApi.approveLessonPackage(latest.id,latest.version??1,"Teacher explicitly approved the complete printable lesson kit");onSave(approved);await refreshPrintReadiness();onFeedback("Complete package approved. PDF download is now available.");return;}if(["revalidate_package","repair_package"].includes(item.recoveryAction)){onSave(await lessonKitApi.revalidateLessonPackage(lessonPackage.id));}if(item.recoveryAction==="retry_generation"&&generationJob){setGenerationJob(await lessonKitApi.retryGenerationJob(generationJob.jobId));}const readiness=await refreshPackageState();onFeedback(readiness?.ready?"The current approved package is ready to download.":readiness?.recommendedNextAction?.explanation??"Package status refreshed.");}catch(reason){onFeedback(reason instanceof Error?reason.message:"Package status could not be refreshed.");}finally{setPrintBusy(false);}};
  const selectPrintPreset=(value:PrintPreset)=>{setPrintPreset(value);rememberSelectedPrintPreset(lessonPackage.id,value);setPdfDownload(initialPdfDownloadState);};
  const printSelectedPreset=async()=>{setPrintBusy(true);try{
    const readiness=await refreshPrintReadiness();if(!readiness?.ready){onFeedback(readiness?.recommendedNextAction?.explanation??"Printing is blocked until readiness checks finish.");return;}
    const latest=await lessonKitApi.getLessonPackage(lessonPackage.id);
    onSave(latest);
    const artifact=await executePdfArtifactDownload({prepareArtifact:()=>lessonKitApi.createPrintableLessonKitArtifact(latest.id,{materialIds:[],printPreset,pageSize,textProfile,reviewedConfirmation:true}),onState:(state)=>{setPdfDownload(state);onFeedback(state.message);}});
    rememberPrintableArtifact(artifact);
  }catch(reason){onFeedback(reason instanceof Error?reason.message:"Printable lesson kit could not be prepared.");}finally{setPrintBusy(false);}};
  const currentStage=generationJob?.stages.find((item)=>item.status==="in_progress")??generationJob?.stages.find((item)=>item.status==="failed");
  const completedStages=generationJob?.stages.filter((item)=>["completed","fallback","skipped"].includes(item.status)).length??0;
  return <section><div className="v2-page-heading"><h1>Lesson Package Ready</h1><p>Review the generated teaching package before exporting or printing.</p></div>{generationJob&&<div className={`v2-generation-state ${generationJob.status==="failed"?"v2-generation-state--blocked":""}`} role={generationJob.status==="failed"?"alert":"status"}><strong>{generationJob.status==="completed"?"Package generation complete":generationJob.status==="partially_complete"?"Package ready with fallbacks":currentStage?.message??"Package work is queued"}</strong><span>{completedStages} of {generationJob.stages.length} stages complete · {generationJob.artifacts.length} materials · {generationJob.cost.actualVisualCount}/{generationJob.cost.estimatedVisualCount} visuals</span>{generationJob.status==="failed"&&generationJob.recoverable&&<button type="button" onClick={()=>void lessonKitApi.retryGenerationJob(generationJob.jobId).then(setGenerationJob)}>Retry failed stage</button>}</div>}{localMock&&<div className="v2-generation-state v2-generation-state--mock" role="status"><strong>Local demo output</strong><span>This package was created by the deterministic local provider. It is not a successful external AI result and still requires teacher review.</span></div>}{blocked&&<div className="v2-generation-state v2-generation-state--blocked" role="alert"><strong>Printing is paused</strong><span>{printReadiness?.recommendedNextAction?.explanation??"Checking the latest generation and approval status…"}</span></div>}
    <div className="v2-package-layout"><div><Card className="v2-summary-strip"><div className="v2-summary-strip-learner"><LearnerAvatar learnerId={learner?.id ?? lessonPackage.learnerId} avatar={learner?.avatar} alt={`${learner?.code ?? "Learner"} avatar`} size={58}/><small>Learner</small><strong>{learner?.code??"Learner"}</strong></div><div><span>◎</span><small>Goal</small><strong>{goalTitle}</strong></div><div><span>◷</span><small>Duration</small><strong>{lessonPackage.duration}</strong></div><div><span>✦</span><small>Theme</small><strong>{lessonPackage.theme}</strong></div></Card>
      <Card className="v2-kit-preview-gallery"><div className="v2-kit-preview-heading"><div><small>YOUR COMPLETE PRINTABLE KIT</small><h2>{lessonPackage.materials.length} classroom pages</h2><p>Open any page to review the finished design. One PDF prints the complete set.</p></div><Button variant="secondary" onClick={()=>onReview()}>Review all designs</Button></div><div className="v2-kit-preview-grid">{lessonPackage.materials.map((material)=>{const imageStatus=String(material.content.imageGenerationStatus??"");const failed=visualTypes.has(material.type)&&imageStatus==="failed";const semanticPassed=material.materialSchemaVersion!==1||material.materialSpec?.semanticValidation.status==="passed";return <article key={material.id}><button type="button" onClick={()=>onReview(material.id)}><div className={`v2-kit-mini-paper v2-paper--${material.printLayout.color||"blue"}`}><div><PrintableMaterialCanvas material={material}/></div></div><span><b>{material.title}</b><small>{!semanticPassed?"Semantic validation failed":materialVisualsReady(material)?(material.status==="approved"?`Approved revision ${material.materialSpec?.revision??material.version??1}`:"Ready to review"):failed?"Visuals need attention":"Creating custom visuals…"}</small></span></button>{failed&&<button type="button" className="v2-kit-retry" disabled={retryingId===material.id} onClick={()=>void retryVisual(material.id)}>{retryingId===material.id?"Restarting…":"Retry visuals"}</button>}</article>;})}</div></Card>
      <details className="v2-lesson-details"><summary><span><b>Teacher plan</b><small>Classroom run sheet, lesson brief, and session notes</small></span><em>View details</em></summary><div className="v2-package-modules"><ClassroomRunSheetPreview sheet={classroomRunSheet}/><Card><h2><span>▤</span> 1. Lesson Brief</h2><strong>{lessonPackage.lessonBrief}</strong>{appliedEdits.length>0&&<><hr/><h3>Teacher-ready adjustments</h3>{appliedEdits.slice(0,3).map((item)=><p key={item}>✓ &nbsp; {item}</p>)}</>}</Card><Card><h2><span>⌘</span> 2. Teaching Flow</h2>{lessonPackage.teachingFlow.map((step,index)=><div className="v2-flow-step" key={step.id}><b>{index+1}</b><div><strong>{step.title}</strong><span>{step.description}</span><small><b>Teacher:</b> {step.teacherAction}</small><small><b>Learner:</b> {step.learnerAction}</small></div></div>)}</Card>
        <Card><h2><span>▰</span> 3. Materials Included</h2><div className="v2-included-materials">{lessonPackage.materials.filter((item)=>item.type!=="summary_template").map((material)=>{const imageUrl=resolveBackendAssetUrl(material.content.imageUrl)??(typeof material.content.imageBase64==="string"?`data:image/png;base64,${material.content.imageBase64}`:null);const imageStatus=String(material.content.imageGenerationStatus??"");return <div key={material.id}>{imageUrl?<img src={imageUrl} alt={String(material.content.imageAltText??material.title)}/>:<span>{imageStatus==="pending"||imageStatus==="processing"?"◌":material.type==="visual_card"?"🚙":material.type==="help_card"?"💬":material.type==="token_board"?"○○○⭐":"▦"}</span>}<small>{material.title}</small>{(imageStatus==="pending"||imageStatus==="processing")&&<em>Artwork generating…</em>}{imageStatus==="failed"&&<em>Artwork unavailable</em>}</div>;})}</div></Card><Card><h2><span>▧</span> 4. Post-Lesson Summary Template</h2>{summaryPrompts.map((item)=><div className="v2-summary-line" key={item}><span>{item}</span><i/></div>)}</Card></div>
      </details>
      {lessonPackage.safetyReview&&<Card className="v2-quality-card"><div className="v2-quality-heading"><div><span>{qualityScore?.overallStatus==="blocked"?"!":qualityScore?.overallStatus==="pass"?"✓":"○"}</span><div><h2>Lesson Kit Quality</h2><p>Eight classroom-readiness checks · 0–2 points each</p></div></div>{qualityScore?<strong className={`v2-quality-total v2-quality-total--${qualityScore.overallStatus}`}>{qualityScore.totalScore}/{qualityScore.maxScore}</strong>:<strong>{lessonPackage.safetyReview.status}</strong>}</div>
        {qualityScore&&<details className="v2-quality-score-details"><summary>View all eight quality checks</summary><div className="v2-score-grid">{qualityScore.items.map((item)=><div className={`v2-score-item v2-score-item--${item.status}`} key={item.id}><span aria-hidden="true">{item.score===2?"✓":item.score===1?"○":"!"}</span><div><strong>{item.label}</strong><small>{item.explanation}</small>{item.recommendedEdits[0]&&<em>{item.recommendedEdits[0]}</em>}</div><b>{item.score}/2</b></div>)}</div></details>}
        <details className="v2-quality-details"><summary>View safety and instructional checks</summary><div className="v2-quality-grid"><div><h3>Safety findings</h3>{(lessonPackage.safetyReview.structuredIssues??[]).map((issue)=><p key={issue.id}><span>{issue.severity==="blocking"?"!":"○"}</span><b>{issue.category.replace(/_/g," ")} · {issue.materialId?lessonPackage.materials.find((item)=>item.id===issue.materialId)?.title??issue.materialId:"Package"}</b><small>{issue.message}</small><em>{issue.suggestedCorrection}</em><small>Related learner constraints: {issue.profileFactorIds.join(", ")||"none recorded"} · revalidation: {lessonPackage.validationStatus??"legacy"}</small></p>)}{appliedEdits.map((item)=><p key={item}>✓ {item}</p>)}</div><div><h3>Detailed instructional checks</h3>{standardsChecks.map((check)=><p key={check.id}><span>{check.status==="pass"?"✓":"○"}</span><b>{check.label}</b><small>{check.recommendation}</small></p>)}</div></div></details><footer>Automatic scoring supports review; it does not replace teacher judgment.</footer></Card>}
      <details className="v2-handoff-disclosure"><summary>Need to share records with another teacher? Create a private handoff ZIP</summary><TeacherHandoffExportPanel lessonPackage={lessonPackage} onPackageChange={onSave} onFeedback={onFeedback}/></details>
    </div><Card className="v2-export-panel"><h2>Download lesson kit</h2><p>Choose a named page set. Complete Kit remains the full approved package.</p><PrintReadinessPanel readiness={printReadiness} busy={printBusy} onFix={(item)=>void fixReadiness(item)}/><PrintPresetPicker catalog={printPresetCatalog} selected={printPreset} onSelect={selectPrintPreset}/>{pdfDownload.message&&<p role={pdfDownload.phase==="failed"?"alert":"status"}>{pdfDownload.message}</p>}<label className="v2-page-size-field">Page size<select value={pageSize} onChange={(event)=>{const value=event.target.value as "Letter"|"A4";setPageSize(value);rememberSelectedPageSize(lessonPackage.id,value);}}><option>Letter</option><option>A4</option></select></label><label className="v2-page-size-field">Text size<select value={textProfile} onChange={(event)=>{const value=event.target.value as PrintTextProfile;setTextProfile(value);rememberSelectedTextProfile(lessonPackage.id,value);}}><option value="standard">Standard</option><option value="large">Large Print</option></select></label><p className="v2-print-profile-note">Large Print uses larger teacher text and learner labels. Extra pages are expected when needed; text is never reduced to preserve pagination.</p><Button fullWidth disabled={blocked||printBusy||!printPresetCatalog?.presets.find((item)=>item.printPreset===printPreset)?.available} onClick={()=>void printSelectedPreset()}>{printBusy?(pdfDownload.phase==="download_starting"?"Download starting…":"Preparing PDF…"):pdfDownload.phase==="failed"?`Retry ${printPresetLabels[printPreset]} PDF`:`Download ${printPresetLabels[printPreset]} PDF`}</Button><Button variant="secondary" fullWidth onClick={onModify}>Modify Lesson Content</Button><Button variant="secondary" fullWidth onClick={()=>onReview()}>Review Individual Materials</Button><Button variant="secondary" fullWidth onClick={onEdit}>Back to Edit Lesson</Button></Card></div>
    <div className="v2-how-it-works"><strong>How this works &nbsp; ⓘ</strong><span>⇩ <b>Review outputs</b><small>Preview the teaching materials</small></span><i>→</i><span>✓ <b>Export or print</b><small>Choose items and export</small></span><i>→</i><span>▣ <b>Use in session</b><small>Bring materials to your session</small></span></div>
  </section>;
}
