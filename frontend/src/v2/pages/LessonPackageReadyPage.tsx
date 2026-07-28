import { useEffect,useState } from "react";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { LearnerAvatar } from "../components/Avatar";
import { lessonKitApi } from "../api/lessonKitApi";
import { resolveBackendAssetUrl } from "../api/backendClient";
import type { LearnerProfile,LessonPackage } from "../types";
import { TeacherHandoffExportPanel } from "../components/TeacherHandoffExportPanel";
import { PrintableMaterialCanvas } from "../components/PrintableMaterialCanvas";

const visualTypes=new Set(["quantity_cards","visual_card","scenario_cards","sequence_cards","social_narrative","core_word_board","visual_schedule","task_analysis_cards","emotion_scale","sorting_page","matching_page","choice_board","first_then_board","help_card","break_card","teacher_cue_card","token_board"]);
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

export function LessonPackageReadyPage({ lessonPackage,onModify,onReview,onEdit,onStartOver,onSave,onFeedback }:{ lessonPackage:LessonPackage|null;onModify:()=>void;onReview:()=>void;onEdit:()=>void;onStartOver:()=>void;onSave:(value:LessonPackage)=>void;onFeedback:(message:string)=>void }) {
  const [learner,setLearner]=useState<LearnerProfile|null>(null);const [exports,setExports]=useState<Record<string,boolean>>({pdf:true});
  const [printBusy,setPrintBusy]=useState(false);const [pageSize,setPageSize]=useState<"Letter"|"A4">("Letter");
  useEffect(()=>{if(lessonPackage)void lessonKitApi.getLearnerById(lessonPackage.learnerId).then(setLearner);},[lessonPackage]);
  const imageStateKey=lessonPackage?.materials.map((item)=>String(item.content.imageGenerationStatus??"")).join("|")??"";
  useEffect(()=>{
    if(!lessonPackage||!lessonPackage.materials.some((item)=>["pending","processing"].includes(String(item.content.imageGenerationStatus??""))))return;
    let cancelled=false;
    const refresh=async()=>{try{const updated=await lessonKitApi.getLessonPackage(lessonPackage.id);if(!cancelled)onSave(updated);}catch{/* Keep the package usable while artwork continues in the background. */}};
    const timer=window.setInterval(()=>void refresh(),3000);
    void refresh();
    return()=>{cancelled=true;window.clearInterval(timer);};
  },[lessonPackage?.id,imageStateKey]);
  if(!lessonPackage)return <section className="v2-empty"><h2>No lesson package yet</h2><Button onClick={onStartOver}>Start a New Lesson</Button></section>;
  const goalTitle=lessonPackage.goal.toLowerCase().includes("ask for help")?"Asking for Help":lessonPackage.goal;
  const summaryMaterial=lessonPackage.materials.find((item)=>item.type==="summary_template");
  const summaryPrompts=Array.isArray(summaryMaterial?.content.prompts)?summaryMaterial.content.prompts:[];
  const appliedEdits=lessonPackage.safetyReview?.appliedEdits??[];
  const standardsChecks=lessonPackage.standardsChecks??[];
  const qualityScore=lessonPackage.qualityScore;
  const localMock=lessonPackage.generationStatus==="local_mock"||lessonPackage.generationMetadata?.outputSource==="local_mock";
  const blocked=lessonPackage.safetyReview?.status==="blocked"||qualityScore?.overallStatus==="blocked"||lessonPackage.status==="validation_failed";
  const incompleteVisuals=lessonPackage.materials.filter((item)=>!materialVisualsReady(item));
  const toggle=(id:string)=>{setExports((current)=>({...current,[id]:current[id]===false}));onFeedback("Export selection updated.");};
  const printCompleteKit=async()=>{setPrintBusy(true);try{
    const approvedMaterials=[];
    for(const material of lessonPackage.materials)approvedMaterials.push(material.status==="approved"?material:await lessonKitApi.approveGeneratedMaterial(material.id));
    const latest=await lessonKitApi.getLessonPackage(lessonPackage.id);
    const approved=latest.status==="approved"?latest:await lessonKitApi.approveLessonPackage(latest.id,latest.version??1,"Teacher approved complete printable lesson kit");
    const next={...approved,materials:approvedMaterials};onSave(next);
    const selectedIds=approvedMaterials.filter((item)=>exports[item.id]!==false).map((item)=>item.id);
    const job=await lessonKitApi.createPrintableLessonKit(next.id,{materialIds:selectedIds,pageSize,reviewedConfirmation:true});
    if(job.status!=="completed")throw new Error(job.message);
    const download=await lessonKitApi.getPrintableLessonKitDownload(job.exportId);
    window.location.assign(download.downloadUrl);onFeedback("Complete lesson kit PDF is ready to print.");
  }catch(reason){onFeedback(reason instanceof Error?reason.message:"Printable lesson kit could not be prepared.");}finally{setPrintBusy(false);}};
  return <section><div className="v2-page-heading"><h1>Lesson Package Ready</h1><p>Review the generated teaching package before exporting or printing.</p></div>{localMock&&<div className="v2-generation-state v2-generation-state--mock" role="status"><strong>Local demo output</strong><span>This package was created by the deterministic local provider. It is not a successful external AI result and still requires teacher review.</span></div>}{blocked&&<div className="v2-generation-state v2-generation-state--blocked" role="alert"><strong>Review required</strong><span>This package did not pass the instructional safety gate. Modify the flagged content before printable approval.</span></div>}
    <div className="v2-package-layout"><div><Card className="v2-summary-strip"><div className="v2-summary-strip-learner"><LearnerAvatar learnerId={learner?.id ?? lessonPackage.learnerId} avatar={learner?.avatar} alt={`${learner?.code ?? "Learner"} avatar`} size={58}/><small>Learner</small><strong>{learner?.code??"Learner"}</strong></div><div><span>◎</span><small>Goal</small><strong>{goalTitle}</strong></div><div><span>◷</span><small>Duration</small><strong>{lessonPackage.duration}</strong></div><div><span>✦</span><small>Theme</small><strong>{lessonPackage.theme}</strong></div></Card>
      <Card className="v2-kit-preview-gallery"><div className="v2-kit-preview-heading"><div><small>YOUR COMPLETE PRINTABLE KIT</small><h2>{lessonPackage.materials.length} ready-to-use classroom pages</h2><p>Open any page to review the finished design. One PDF prints the complete set.</p></div><Button variant="secondary" onClick={onReview}>Review all designs</Button></div><div className="v2-kit-preview-grid">{lessonPackage.materials.map((material)=><button type="button" onClick={onReview} key={material.id}><div className={`v2-kit-mini-paper v2-paper--${material.printLayout.color||"blue"}`}><div><PrintableMaterialCanvas material={material}/></div></div><span><b>{material.title}</b><small>{materialVisualsReady(material)?"Ready to review":"Creating custom visuals…"}</small></span></button>)}</div></Card>
      <div className="v2-package-modules"><Card><h2><span>▤</span> 1. Lesson Brief</h2><strong>{lessonPackage.lessonBrief}</strong>{appliedEdits.length>0&&<><hr/><h3>Teacher-ready adjustments</h3>{appliedEdits.slice(0,3).map((item)=><p key={item}>✓ &nbsp; {item}</p>)}</>}</Card><Card><h2><span>⌘</span> 2. Teaching Flow</h2>{lessonPackage.teachingFlow.map((step,index)=><div className="v2-flow-step" key={step.id}><b>{index+1}</b><div><strong>{step.title}</strong><span>{step.description}</span><small><b>Teacher:</b> {step.teacherAction}</small><small><b>Learner:</b> {step.learnerAction}</small></div></div>)}</Card>
        <Card><h2><span>▰</span> 3. Materials Included</h2><div className="v2-included-materials">{lessonPackage.materials.filter((item)=>item.type!=="summary_template").map((material)=>{const imageUrl=resolveBackendAssetUrl(material.content.imageUrl)??(typeof material.content.imageBase64==="string"?`data:image/png;base64,${material.content.imageBase64}`:null);const imageStatus=String(material.content.imageGenerationStatus??"");return <div key={material.id}>{imageUrl?<img src={imageUrl} alt={String(material.content.imageAltText??material.title)}/>:<span>{imageStatus==="pending"||imageStatus==="processing"?"◌":material.type==="visual_card"?"🚙":material.type==="help_card"?"💬":material.type==="token_board"?"○○○⭐":"▦"}</span>}<small>{material.title}</small>{(imageStatus==="pending"||imageStatus==="processing")&&<em>Artwork generating…</em>}{imageStatus==="failed"&&<em>Artwork unavailable</em>}</div>;})}</div></Card><Card><h2><span>▧</span> 4. Post-Lesson Summary Template</h2>{summaryPrompts.map((item)=><div className="v2-summary-line" key={item}><span>{item}</span><i/></div>)}</Card></div>
      {lessonPackage.safetyReview&&<Card className="v2-quality-card"><div className="v2-quality-heading"><div><span>{qualityScore?.overallStatus==="blocked"?"!":qualityScore?.overallStatus==="pass"?"✓":"○"}</span><div><h2>Lesson Kit Quality</h2><p>Eight classroom-readiness checks · 0–2 points each</p></div></div>{qualityScore?<strong className={`v2-quality-total v2-quality-total--${qualityScore.overallStatus}`}>{qualityScore.totalScore}/{qualityScore.maxScore}</strong>:<strong>{lessonPackage.safetyReview.status}</strong>}</div>
        {qualityScore&&<div className="v2-score-grid">{qualityScore.items.map((item)=><div className={`v2-score-item v2-score-item--${item.status}`} key={item.id}><span aria-hidden="true">{item.score===2?"✓":item.score===1?"○":"!"}</span><div><strong>{item.label}</strong><small>{item.explanation}</small>{item.recommendedEdits[0]&&<em>{item.recommendedEdits[0]}</em>}</div><b>{item.score}/2</b></div>)}</div>}
        <details className="v2-quality-details"><summary>View safety and instructional checks</summary><div className="v2-quality-grid"><div><h3>Applied safety edits</h3>{appliedEdits.map((item)=><p key={item}>✓ {item}</p>)}</div><div><h3>Detailed instructional checks</h3>{standardsChecks.map((check)=><p key={check.id}><span>{check.status==="pass"?"✓":"○"}</span><b>{check.label}</b><small>{check.recommendation}</small></p>)}</div></div></details><footer>Automatic scoring supports review; it does not replace teacher judgment.</footer></Card>}
      <details className="v2-handoff-disclosure"><summary>Need to share records with another teacher? Create a private handoff ZIP</summary><TeacherHandoffExportPanel lessonPackage={lessonPackage} onPackageChange={onSave} onFeedback={onFeedback}/></details>
    </div><Card className="v2-export-panel"><h2>Print lesson kit</h2><p>One PDF includes the lesson plan and every selected classroom card or worksheet.</p>{incompleteVisuals.length>0&&<p className="v2-kit-generation-status" role="status"><strong>Creating {incompleteVisuals.length} customized material{incompleteVisuals.length===1?"":"s"}…</strong><small>Printing unlocks automatically when every classroom visual is ready.</small></p>}{lessonPackage.materials.map((item)=><label key={item.id}><input type="checkbox" checked={exports[item.id]!==false} onChange={()=>toggle(item.id)}/><span>▧</span>{item.title}</label>)}<label className="v2-page-size-field">Page size<select value={pageSize} onChange={(event)=>setPageSize(event.target.value as "Letter"|"A4")}><option>Letter</option><option>A4</option></select></label><Button fullWidth disabled={blocked||printBusy||incompleteVisuals.length>0} onClick={()=>void printCompleteKit()}>{printBusy?"Preparing complete PDF…":incompleteVisuals.length>0?"Building customized materials…":"Approve & Print Complete PDF"}</Button><Button variant="secondary" fullWidth onClick={onModify}>Modify Lesson Content</Button><Button variant="secondary" fullWidth disabled={blocked} onClick={onReview}>Review Individual Materials</Button><Button variant="secondary" fullWidth onClick={onEdit}>Back to Edit Lesson</Button></Card></div>
    <div className="v2-how-it-works"><strong>How this works &nbsp; ⓘ</strong><span>⇩ <b>Review outputs</b><small>Preview the teaching materials</small></span><i>→</i><span>✓ <b>Export or print</b><small>Choose items and export</small></span><i>→</i><span>▣ <b>Use in session</b><small>Bring materials to your session</small></span></div>
  </section>;
}
