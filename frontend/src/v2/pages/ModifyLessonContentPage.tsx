import { useEffect,useState } from "react";
import { lessonKitApi } from "../api/lessonKitApi";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { EditableDocumentBlock } from "../components/EditableDocumentBlock";
import type { LessonPackage,LessonSectionEditPreview,TeachingStep } from "../types";

type DocumentFields = {
  title: string;
  learnerContext: string;
  goal: string;
  lessonBrief: string;
  materialsNeeded: string;
  promptingPlan: string;
  reinforcementPlan: string;
  dataCollectionPlan: string;
  postLessonSummary: string;
};

function savedText(value: unknown, fallback: string): string {
  return typeof value === "string" ? value : fallback;
}

function learnerLabel(learnerId: string): string {
  const match = learnerId.match(/^([a-z])(\d+)$/i);
  return match ? `Learner ${match[1].toUpperCase()}-${match[2]}` : "The learner";
}

export function ModifyLessonContentPage({ lessonPackage,onBack,onContinue,onSave,onFeedback }:{ lessonPackage:LessonPackage|null;onBack:()=>void;onContinue:()=>void;onSave:(updated:LessonPackage)=>void;onFeedback:(message:string)=>void }) {
  const stored=lessonPackage?.documentContent??{};
  const [fields,setFields]=useState<DocumentFields>(()=>({
    title:savedText(stored.title,`${lessonPackage?.goal??"Lesson"} Lesson Kit`),
    learnerContext:savedText(stored.learnerContext,lessonPackage?`${learnerLabel(lessonPackage.learnerId)} benefits from short activities, visual supports, wait time, and motivating reinforcement.`:""),
    goal:savedText(stored.goal,lessonPackage?.goal??""),
    lessonBrief:savedText(stored.lessonBrief,lessonPackage?.lessonBrief??""),
    materialsNeeded:savedText(stored.materialsNeeded,lessonPackage?.materials.map((item)=>item.title).join(", ")??""),
    promptingPlan:savedText(stored.promptingPlan,"Use visual prompt first, wait 5 seconds, then move to a partial verbal prompt if needed. Fade prompts when the learner initiates or approximates the request."),
    reinforcementPlan:savedText(stored.reinforcementPlan,"Provide praise and a token after each appropriate request. After 5 tokens, offer the selected reward."),
    dataCollectionPlan:savedText(stored.dataCollectionPlan,"Record scenario, independence, prompt level, participation, regulation, and notes for each opportunity."),
    postLessonSummary:savedText(stored.postLessonSummary,lessonPackage?.summaryTemplate??""),
  }));
  const [flow,setFlow]=useState<TeachingStep[]>(()=>lessonPackage?.teachingFlow.map((step)=>({...step}))??[]);
  const [active,setActive]=useState("");
  const [saving,setSaving]=useState(false);
  const [savedAt,setSavedAt]=useState("Not saved yet");
  const [dirty,setDirty]=useState(false);
  const [editInstruction,setEditInstruction]=useState("");
  const [editPreview,setEditPreview]=useState<LessonSectionEditPreview|null>(null);
  const [aiBusy,setAiBusy]=useState(false);

  useEffect(()=>{const warn=(event:BeforeUnloadEvent)=>{if(!dirty)return;event.preventDefault();event.returnValue="";};window.addEventListener("beforeunload",warn);return()=>window.removeEventListener("beforeunload",warn);},[dirty]);

  if(!lessonPackage)return <section className="v2-empty"><h2>No lesson content to modify</h2><Button onClick={onBack}>Back to Package</Button></section>;
  const packageId=lessonPackage.id;

  const updateField=(key:keyof DocumentFields,value:string)=>{setFields((current)=>({...current,[key]:value}));setDirty(true);};
  const updateFlow=(index:number,key:keyof TeachingStep,value:string)=>{setFlow((current)=>current.map((step,stepIndex)=>stepIndex===index?{...step,[key]:value}:step));setDirty(true);};
  const selectActive=(id:string)=>{setActive(id);setEditPreview(null);};

  function activeValue():{label:string;value:string}|null {
    if(!active)return null;
    if(active.startsWith("flow-")){
      const match=active.match(/^flow-(\d+)-(title|description|teacherAction|learnerAction)$/);
      if(!match)return null;
      const index=Number(match[1]);const key=match[2] as keyof TeachingStep;
      const label=`Teaching flow step ${index+1} ${key.replace(/([A-Z])/g," $1").toLowerCase()}`;
      return {label,value:String(flow[index]?.[key]??"")};
    }
    const key=active as keyof DocumentFields;
    const labels:Record<keyof DocumentFields,string>={title:"Lesson title",learnerContext:"Learner context",goal:"Lesson goal",lessonBrief:"Lesson brief",materialsNeeded:"Materials needed",promptingPlan:"Prompting plan",reinforcementPlan:"Reinforcement plan",dataCollectionPlan:"Data collection plan",postLessonSummary:"Post-lesson summary template"};
    return {label:labels[key],value:fields[key]};
  }

  function changeActive(transform:(value:string)=>string) {
    if(!active){onFeedback("Select a section to edit first.");return;}
    if(active.startsWith("flow-")){
      const match=active.match(/^flow-(\d+)-(title|description|teacherAction|learnerAction)$/);
      if(!match)return;
      const index=Number(match[1]);const key=match[2] as keyof TeachingStep;
      updateFlow(index,key,transform(String(flow[index]?.[key]??"")));return;
    }
    const key=active as keyof DocumentFields;
    updateField(key,transform(fields[key]));
  }

  const assist=async(instruction:string)=>{
    const selected=activeValue();if(!selected){onFeedback("Select a section to edit first.");return;}
    setAiBusy(true);setEditPreview(null);
    try{const preview=await lessonKitApi.previewLessonSectionEdit(packageId,{sectionId:active,sectionLabel:selected.label,currentText:selected.value,instruction,expectedVersion:lessonPackage.version??1});setEditPreview(preview);setEditInstruction(instruction);}
    catch(reason){onFeedback(reason instanceof Error?reason.message:"AI could not revise this section.");}
    finally{setAiBusy(false);}
  };
  const applyPreview=()=>{if(!editPreview||editPreview.sectionId!==active)return;changeActive(()=>editPreview.revisedText);setEditPreview(null);onFeedback("AI revision applied locally. Save Changes when ready.");};

  async function save(continueAfter=false) {
    setSaving(true);
    try{
      const updated=await lessonKitApi.updateLessonPackage(packageId,{
        lessonBrief:fields.lessonBrief,
        summaryTemplate:fields.postLessonSummary,
        teachingFlow:flow,
        documentContent:{...fields,teachingFlow:flow},
      });
      onSave(updated);setDirty(false);setSavedAt("Saved just now");onFeedback("Lesson content saved.");
      if(continueAfter)onContinue();
    }catch(error){onFeedback(error instanceof Error?error.message:"Lesson content could not be saved.");}
    finally{setSaving(false);}
  }

  const block=(key:keyof DocumentFields,label:string,multiline=true)=><EditableDocumentBlock id={key} label={label} value={fields[key]} multiline={multiline} onChange={(value)=>updateField(key,value)} active={active===key} onFocus={selectActive}/>;
  return <section>
    <div className="v2-page-heading"><h1>Modify Lesson Content</h1><p>Edit the AI-generated lesson directly before reviewing printable materials.</p></div>
    <div className="v2-editor-breadcrumb"><span>Plan with AI Chat</span><b>→</b><span>Lesson Package Ready</span><b>→</b><strong>Modify Lesson Content</strong><b>→</b><span>Review Printable Content</span></div>
    <div className="v2-document-layout">
      <article className="v2-document-paper">
        {block("title","Lesson title",false)}
        {block("learnerContext","Learner context")}
        {block("goal","Lesson goal")}
        {block("lessonBrief","Lesson brief")}
        {block("materialsNeeded","Materials needed")}
        <section className="v2-document-flow"><h2>Teaching flow</h2>{flow.map((step,index)=><div className="v2-document-step" key={step.id}><span>{index+1}</span><div>
          <EditableDocumentBlock id={`flow-${index}-title`} label="Step title" value={step.title} multiline={false} onChange={(value)=>updateFlow(index,"title",value)} active={active===`flow-${index}-title`} onFocus={selectActive}/>
          <EditableDocumentBlock id={`flow-${index}-description`} label="Description" value={step.description} onChange={(value)=>updateFlow(index,"description",value)} active={active===`flow-${index}-description`} onFocus={selectActive}/>
          <EditableDocumentBlock id={`flow-${index}-teacherAction`} label="Teacher action" value={step.teacherAction} onChange={(value)=>updateFlow(index,"teacherAction",value)} active={active===`flow-${index}-teacherAction`} onFocus={selectActive}/>
          <EditableDocumentBlock id={`flow-${index}-learnerAction`} label="Learner action" value={step.learnerAction} onChange={(value)=>updateFlow(index,"learnerAction",value)} active={active===`flow-${index}-learnerAction`} onFocus={selectActive}/>
        </div></div>)}</section>
        {block("promptingPlan","Prompting plan")}
        {block("reinforcementPlan","Reinforcement plan")}
        {block("dataCollectionPlan","Data collection plan")}
        {block("postLessonSummary","Post-lesson summary template")}
      </article>
      <aside className="v2-document-sidebar">
        <Card><h2>AI Assist</h2><p>{active?`Only “${activeValue()?.label??"selected section"}” will change.`:"Select a document section first."}</p><div className="v2-ai-assist-actions"><button disabled={aiBusy} onClick={()=>void assist("Simplify the wording while preserving the teaching meaning.")}>Simplify selected section</button><button disabled={aiBusy} onClick={()=>void assist("Make this section more concrete and teacher-actionable.")}>Make more concrete</button><button disabled={aiBusy} onClick={()=>void assist("Shorten this section for a clean printable page.")}>Shorten for printing</button><button disabled={aiBusy} onClick={()=>void assist("Add clear wait time, prompting, and prompt-fading detail.")}>Add prompting detail</button></div><label className="v2-ai-custom-edit">Custom instruction<textarea value={editInstruction} onChange={(event)=>setEditInstruction(event.target.value)} placeholder="Example: Use simpler language and add one counting example."/></label><Button variant="secondary" fullWidth disabled={!active||!editInstruction.trim()||aiBusy} onClick={()=>void assist(editInstruction)}>{aiBusy?"Creating preview…":"Preview AI revision"}</Button>{editPreview&&<div className="v2-ai-edit-preview"><strong>Review before applying</strong><small>Current</small><p>{editPreview.beforeText}</p><small>AI suggestion</small><p>{editPreview.revisedText}</p>{editPreview.fallbackUsed&&<em>Local fallback preview</em>}<div><Button variant="secondary" onClick={()=>setEditPreview(null)}>Dismiss</Button><Button onClick={applyPreview}>Apply to this section</Button></div></div>}</Card>
        <Card><h2>Safety &amp; Quality</h2>{lessonPackage.safetyReview?<><p><strong>{lessonPackage.safetyReview.status}</strong> · {lessonPackage.safetyReview.riskLevel} risk</p>{lessonPackage.safetyReview.appliedEdits.map((item)=><small key={item}>✓ {item}</small>)}</>:<p>No safety review attached.</p>}<h3>Standards checks</h3>{lessonPackage.standardsChecks?.map((check)=><small key={check.id}>{check.status==="pass"?"✓":"○"} {check.label}</small>)}<footer>Instructional guidance only. Teacher review is still required.</footer></Card>
        <Card><h2>Document Info</h2><dl><div><dt>Learner</dt><dd>{lessonPackage.learnerId}</dd></div><div><dt>Goal</dt><dd>{lessonPackage.goal}</dd></div><div><dt>Duration</dt><dd>{lessonPackage.duration}</dd></div><div><dt>Theme</dt><dd>{lessonPackage.theme}</dd></div><div><dt>Materials</dt><dd>{lessonPackage.materials.length}</dd></div><div><dt>Status</dt><dd>{dirty?"Unsaved changes":savedAt}</dd></div></dl></Card>
      </aside>
    </div>
    <div className="v2-document-actions"><Button variant="secondary" onClick={onBack}>Back to Package</Button><span>{dirty?"You have unsaved changes.":savedAt}</span><Button variant="secondary" disabled={saving} onClick={()=>void save()}>{saving?"Saving…":"Save Changes"}</Button><Button disabled={saving} onClick={()=>void save(true)}>Continue to Printable Review</Button></div>
  </section>;
}
