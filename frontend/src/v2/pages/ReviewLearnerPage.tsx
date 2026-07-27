import { useCallback,useEffect,useState } from "react";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Tag } from "../components/Tag";
import { lessonKitApi } from "../api/lessonKitApi";
import type { LearnerProfile,LearnerProfileExtraction,LearnerRecord } from "../types";

type EditableProfile={ code:string;age:string;communication:string;supportNeeds:string;interests:string;reinforcement:string;activityFormats:string;notes:string };
const emptyProfile:EditableProfile={code:"",age:"",communication:"",supportNeeds:"",interests:"",reinforcement:"",activityFormats:"",notes:""};
const profileFromLearner=(learner:LearnerProfile):EditableProfile=>({code:learner.code,age:learner.age>0?String(learner.age):"",communication:learner.communicationMode,supportNeeds:learner.supportNeeds.join(", "),interests:learner.interests.join(", "),reinforcement:learner.reinforcementPreferences.join(", "),activityFormats:learner.attentionProfile,notes:learner.notes});
const shortList=(value:string,limit=2)=>value.split(",").map((item)=>item.trim()).filter(Boolean).slice(0,limit).join(", ")||"Confirm with teacher";
const conciseInsight=(value:string)=>{
  const cleaned=value
    .replace(/\s*Teacher confirmation is required\.?/gi,"")
    .replace(/\s+/g," ")
    .trim();
  const firstSentence=cleaned.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim()??cleaned;
  return firstSentence.length>132?`${firstSentence.slice(0,129).trimEnd()}…`:firstSentence;
};
const formatRecordDate=(value:string)=>{
  const parsed=new Date(value);
  if(Number.isNaN(parsed.getTime()))return value;
  return new Intl.DateTimeFormat(undefined,{month:"short",day:"numeric",year:"numeric"}).format(parsed);
};

function RecordCard({ record,onFeedback }:{ record:LearnerRecord;onFeedback:(message:string)=>void }) {
  const icon=record.fileType.toLowerCase().includes("pdf")||record.fileName.endsWith(".pdf")?"PDF":record.fileName.endsWith(".docx")?"W":"TXT";
  const status=record.status==="processing"?"Processing":record.status==="reviewed"?"Reviewed":"Ready";
  return <div className="v2-review-record"><span>{icon}</span><div><strong title={record.fileName}>{record.fileName.replace(/\.[^.]+$/,"")}</strong><small>{formatRecordDate(record.uploadedAt)}</small></div><Tag tone={record.status==="processing"?"amber":"green"}>{status}</Tag><button aria-label={`Open ${record.fileName} details`} onClick={()=>onFeedback(`${record.fileName} source details opened.`)}>⋮</button></div>;
}

export function ReviewLearnerPage({ learnerId,isNew,onContinue,onBack,onFeedback }:{ learnerId:string;isNew:boolean;onContinue:()=>void;onBack?:()=>void;onFeedback:(message:string)=>void }) {
  const [extraction,setExtraction]=useState<LearnerProfileExtraction|null>(null);const [form,setForm]=useState<EditableProfile>(emptyProfile);const [isLoading,setIsLoading]=useState(true);const [isSavingProfile,setIsSavingProfile]=useState(false);const [loadError,setLoadError]=useState<string|null>(null);const [formError,setFormError]=useState<string|null>(null);
  const loadExtraction=useCallback(async()=>{setIsLoading(true);setLoadError(null);try{const value=await lessonKitApi.getExtractedLearnerProfile(learnerId);setExtraction(value);setForm(profileFromLearner(value.learner));}catch(error){setExtraction(null);setLoadError(error instanceof Error?error.message:"Learner information is temporarily unavailable.");}finally{setIsLoading(false);}},[learnerId]);
  useEffect(()=>{void loadExtraction();},[loadExtraction]);
  if(isLoading)return <div className="v2-loading" role="status" aria-live="polite">Preparing learner information…</div>;
  if(loadError||!extraction)return <div className="v2-load-error" role="alert"><Card><span className="v2-load-error__icon" aria-hidden="true">!</span><h2>We couldn’t prepare this learner profile</h2><p>{loadError??"Learner information is temporarily unavailable."}</p><Button onClick={()=>void loadExtraction()}>Try again</Button></Card></div>;
  const learner=extraction.learner;const update=(field:keyof EditableProfile,value:string)=>setForm((current)=>({...current,[field]:value}));
  const addRecord=async(fileName:string)=>{const record=await lessonKitApi.addRecordForLearner(learnerId,{fileName,fileType:"TXT",text:"Supplemental information for teacher review."});setExtraction((current)=>current?{...current,records:[...current.records,record],analyzedRecordCount:current.analyzedRecordCount+1}:current);onFeedback(`${fileName} added for review.`);};
  const saveAndContinue=async()=>{
    const age=Number(form.age);
    if(!form.code.trim()){setFormError("Enter a learner code before continuing.");return;}
    if(!Number.isInteger(age)||age<1||age>30){setFormError("Enter the learner’s confirmed age between 1 and 30.");return;}
    setFormError(null);setIsSavingProfile(true);
    try{
      const updated=await lessonKitApi.updateLearner(learnerId,{code:form.code.trim(),age,communicationMode:form.communication.trim(),supportNeeds:form.supportNeeds.split(",").map((item)=>item.trim()).filter(Boolean),interests:form.interests.split(",").map((item)=>item.trim()).filter(Boolean),reinforcementPreferences:form.reinforcement.split(",").map((item)=>item.trim()).filter(Boolean),attentionProfile:form.activityFormats.trim(),notes:form.notes.trim(),expectedVersion:learner.version});
      const confirmed=await lessonKitApi.confirmLearnerProfile(learnerId,updated.version??1);
      setExtraction((current)=>current?{...current,learner:confirmed}:current);
      onFeedback(`${confirmed.code} profile confirmed and saved.`);
      onContinue();
    }catch(error){setFormError(error instanceof Error?error.message:"The learner profile could not be confirmed.");}
    finally{setIsSavingProfile(false);}
  };
  const replaceFirstRecord=()=>{setExtraction((current)=>current?{...current,records:current.records.map((record,index)=>index===0?{...record,fileName:"Replacement learner summary.pdf",uploadedAt:"Just now",status:"ready"}:record)}:current);onFeedback("The first source record was replaced.");};
  return <section><div className="v2-page-heading"><h1>{isNew?"Review Uploaded Learner Information":"Review & Update Learner Information"}</h1><p>{isNew?`AI extracted key details from the uploaded records for ${learner.code}. Edit anything before planning the lesson.`:`Check current records, upload supplemental files, and update the profile for ${learner.code}.`}</p></div><div className="v2-review-layout">
    <Card className="v2-review-sources">{isNew?<><h2>Uploaded records</h2>{extraction.records.map((record)=><RecordCard record={record} onFeedback={onFeedback} key={record.id}/>) }<button className="v2-source-action" onClick={replaceFirstRecord}>↻ &nbsp; Replace file</button><button className="v2-source-action" onClick={()=>void addRecord("Additional family notes.txt")}>＋ &nbsp; Add another file</button></>:<><div className="v2-review-learner"><span>{learner.avatar}</span><div><h2>{learner.code} <small>· {learner.age>0?`Age ${learner.age}`:"Age to confirm"}</small></h2><p>{learner.interests.length?`Likes ${learner.interests[0].toLowerCase()}`:"Interests to confirm"}{learner.supportNeeds.length?` · ${learner.supportNeeds.join(" · ")}`:""}</p></div></div><hr/><h3>Current records</h3>{extraction.records.map((record)=><RecordCard record={record} onFeedback={onFeedback} key={record.id}/>)}<button className="v2-supplemental" onClick={()=>void addRecord("Supplemental classroom record.txt")}>⇧<strong>Upload supplemental record</strong><small>PDF, DOCX, or image (Max 20MB)</small></button></>}</Card>
    <Card className="v2-profile-editor"><h2>{isNew?"Extracted Learner Profile":"Editable Learner Profile"}</h2><div className="v2-form-row v2-form-row--split"><label>Learner code<input value={form.code} onChange={(event)=>update("code",event.target.value)}/></label><label>Age<input type="number" min="1" max="30" inputMode="numeric" value={form.age} placeholder="Confirm" onChange={(event)=>update("age",event.target.value)}/></label></div><ProfileField label="Primary communication" value={form.communication} onChange={(value)=>update("communication",value)}/><ProfileField label="Support needs" value={form.supportNeeds} onChange={(value)=>update("supportNeeds",value)} pills/><ProfileField label="Interests" value={form.interests} onChange={(value)=>update("interests",value)} pills/><ProfileField label={isNew?"Best activity formats":"Reinforcement preferences"} value={isNew?form.activityFormats:form.reinforcement} onChange={(value)=>update(isNew?"activityFormats":"reinforcement",value)}/><div className="v2-form-row"><label>Notes<textarea value={form.notes} onChange={(event)=>update("notes",event.target.value)}/></label></div>{formError&&<p className="v2-inline-error" role="alert">{formError}</p>}<div className="v2-editor-actions">{isNew?<Button variant="secondary" onClick={onBack}>Back</Button>:<Button variant="secondary" onClick={()=>{setForm(profileFromLearner(learner));setFormError(null);}}>Reset changes</Button>}<Button disabled={isSavingProfile} onClick={()=>void saveAndContinue()}>{isSavingProfile?"Saving…":isNew?"Confirm & Continue":"Save & Continue"}</Button></div></Card>
    <Card className="v2-review-insights">{isNew?<><div className="v2-snapshot-heading"><div><small>AI draft from {extraction.analyzedRecordCount} {extraction.analyzedRecordCount===1?"record":"records"}</small><h2>Teaching snapshot</h2></div><Tag tone="green">Teacher review</Tag></div><p className="v2-insight-disclaimer">Use these as planning cues. Confirm the editable profile before continuing.</p><div className="v2-teaching-snapshot">{extraction.insights.slice(0,3).map((insight,index)=><div className="v2-insight" key={insight}><span>{["◉","◷","▱"][index]}</span><strong>{conciseInsight(insight)}</strong></div>)}</div>{extraction.insights.length>3&&<details className="v2-evidence-details"><summary>View {extraction.insights.length-3} more record notes</summary><ul>{extraction.insights.slice(3).map((insight)=><li key={insight}>{insight}</li>)}</ul></details>}<div className="v2-extraction-complete">✓ &nbsp; Ready for teacher confirmation</div></>:<><h2>Profile Summary</h2><div className="v2-profile-summary"><h3>{form.code} · {form.age?`Age ${form.age}`:"Age to confirm"}</h3><dl><div><dt>Communication</dt><dd>{conciseInsight(form.communication)||"Confirm with teacher"}</dd></div><div><dt>Supports</dt><dd>{shortList(form.supportNeeds)}</dd></div><div><dt>Interests</dt><dd>{shortList(form.interests)}</dd></div><div><dt>Motivators</dt><dd>{shortList(form.reinforcement)}</dd></div></dl></div><h3>Planning cues</h3>{[["◯","One step at a time","Keep directions brief."],["▧","Show, then tell","Pair words with a visual."],["⌁","Offer choices","Use 2–3 clear options."]].map(([icon,title,copy])=><div className="v2-suggestion" key={title}><span>{icon}</span><div><strong>{title}</strong><small>{copy}</small></div></div>)}<Button variant="secondary" fullWidth onClick={()=>onFeedback("Profile values are ready to compare with source records.")}>Compare source records</Button></>}</Card>
  </div></section>;
}

function ProfileField({ label,value,onChange,pills=false }:{ label:string;value:string;onChange:(value:string)=>void;pills?:boolean }) {
  return <div className="v2-form-row"><label>{label}<div className={pills?"v2-pill-input":""}><textarea className="v2-profile-field-control" aria-label={label} rows={pills?2:3} value={value} onChange={(event)=>onChange(event.target.value)} placeholder={pills?"Separate items with commas":""}/></div></label></div>;
}
