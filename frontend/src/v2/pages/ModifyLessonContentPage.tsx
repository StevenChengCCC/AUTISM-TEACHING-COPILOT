import { useEffect,useState } from "react";
import { lessonKitApi } from "../api/lessonKitApi";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { EditableDocumentBlock } from "../components/EditableDocumentBlock";
import type { LessonPackage,TeachingStep } from "../types";

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

  useEffect(()=>{const warn=(event:BeforeUnloadEvent)=>{if(!dirty)return;event.preventDefault();event.returnValue="";};window.addEventListener("beforeunload",warn);return()=>window.removeEventListener("beforeunload",warn);},[dirty]);

  if(!lessonPackage)return <section className="v2-empty"><h2>No lesson content to modify</h2><Button onClick={onBack}>Back to Package</Button></section>;
  const packageId=lessonPackage.id;

  const updateField=(key:keyof DocumentFields,value:string)=>{setFields((current)=>({...current,[key]:value}));setDirty(true);};
  const updateFlow=(index:number,key:keyof TeachingStep,value:string)=>{setFlow((current)=>current.map((step,stepIndex)=>stepIndex===index?{...step,[key]:value}:step));setDirty(true);};

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

  const assist=(action:"simplify"|"concrete"|"shorten"|"prompting"|"parent")=>{
    const transforms={
      simplify:(value:string)=>value.replace(/\butilize\b/gi,"use").replace(/\bin order to\b/gi,"to").split(/(?<=[.!?])\s+/).slice(0,2).join(" "),
      concrete:(value:string)=>`${value.trim()} Use one familiar example, model the expected response, and note the learner’s level of support.`,
      shorten:(value:string)=>{const sentence=value.trim().split(/(?<=[.!?])\s+/)[0]??value;return sentence.length>180?`${sentence.slice(0,177).trim()}…`:sentence;},
      prompting:(value:string)=>`${value.trim()} Wait 5 seconds, begin with a visual prompt, and fade toward a lighter prompt after successful attempts.`,
      parent:(value:string)=>`${value.trim()} Parent-friendly note: We are practicing this skill in small steps and noticing participation, communication, and growing independence.`,
    };
    changeActive(transforms[action]);
  };

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

  const block=(key:keyof DocumentFields,label:string,multiline=true)=><EditableDocumentBlock id={key} label={label} value={fields[key]} multiline={multiline} onChange={(value)=>updateField(key,value)} active={active===key} onFocus={setActive}/>;
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
          <EditableDocumentBlock id={`flow-${index}-title`} label="Step title" value={step.title} multiline={false} onChange={(value)=>updateFlow(index,"title",value)} active={active===`flow-${index}-title`} onFocus={setActive}/>
          <EditableDocumentBlock id={`flow-${index}-description`} label="Description" value={step.description} onChange={(value)=>updateFlow(index,"description",value)} active={active===`flow-${index}-description`} onFocus={setActive}/>
          <EditableDocumentBlock id={`flow-${index}-teacherAction`} label="Teacher action" value={step.teacherAction} onChange={(value)=>updateFlow(index,"teacherAction",value)} active={active===`flow-${index}-teacherAction`} onFocus={setActive}/>
          <EditableDocumentBlock id={`flow-${index}-learnerAction`} label="Learner action" value={step.learnerAction} onChange={(value)=>updateFlow(index,"learnerAction",value)} active={active===`flow-${index}-learnerAction`} onFocus={setActive}/>
        </div></div>)}</section>
        {block("promptingPlan","Prompting plan")}
        {block("reinforcementPlan","Reinforcement plan")}
        {block("dataCollectionPlan","Data collection plan")}
        {block("postLessonSummary","Post-lesson summary template")}
      </article>
      <aside className="v2-document-sidebar">
        <Card><h2>AI Assist</h2><p>{active?"Applying changes to the selected section.":"Select a document section first."}</p><div className="v2-ai-assist-actions"><button onClick={()=>assist("simplify")}>Simplify selected section</button><button onClick={()=>assist("concrete")}>Make more concrete</button><button onClick={()=>assist("shorten")}>Shorten for printing</button><button onClick={()=>assist("prompting")}>Add prompting detail</button><button onClick={()=>assist("parent")}>Make parent-friendly</button></div></Card>
        <Card><h2>Safety &amp; Quality</h2>{lessonPackage.safetyReview?<><p><strong>{lessonPackage.safetyReview.status}</strong> · {lessonPackage.safetyReview.riskLevel} risk</p>{lessonPackage.safetyReview.appliedEdits.map((item)=><small key={item}>✓ {item}</small>)}</>:<p>No safety review attached.</p>}<h3>Standards checks</h3>{lessonPackage.standardsChecks?.map((check)=><small key={check.id}>{check.status==="pass"?"✓":"○"} {check.label}</small>)}<footer>Instructional guidance only. Teacher review is still required.</footer></Card>
        <Card><h2>Document Info</h2><dl><div><dt>Learner</dt><dd>{lessonPackage.learnerId}</dd></div><div><dt>Goal</dt><dd>{lessonPackage.goal}</dd></div><div><dt>Duration</dt><dd>{lessonPackage.duration}</dd></div><div><dt>Theme</dt><dd>{lessonPackage.theme}</dd></div><div><dt>Materials</dt><dd>{lessonPackage.materials.length}</dd></div><div><dt>Status</dt><dd>{dirty?"Unsaved changes":savedAt}</dd></div></dl></Card>
      </aside>
    </div>
    <div className="v2-document-actions"><Button variant="secondary" onClick={onBack}>Back to Package</Button><span>{dirty?"You have unsaved changes.":savedAt}</span><Button variant="secondary" disabled={saving} onClick={()=>void save()}>{saving?"Saving…":"Save Changes"}</Button><Button disabled={saving} onClick={()=>void save(true)}>Continue to Printable Review</Button></div>
  </section>;
}
