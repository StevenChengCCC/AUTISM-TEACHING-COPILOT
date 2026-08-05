import { useCallback,useEffect,useState } from "react";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Tag } from "../components/Tag";
import { lessonKitApi } from "../api/lessonKitApi";
import { LearnerAvatar } from "../components/Avatar";
import type { LearnerProfile,LearnerProfileExtraction,LearnerRecord,ProfileFactor } from "../types";
import { factorStatusLabel,profileFactorSections,profileSummaryView,visibleFactorsForSection } from "../profileViewModel";
import "./ReviewLearnerPage.css";

type EditableProfile={ code:string;age:string;communication:string;supportNeeds:string;interests:string;reinforcement:string;activityFormats:string;notes:string };
const emptyProfile:EditableProfile={code:"",age:"",communication:"",supportNeeds:"",interests:"",reinforcement:"",activityFormats:"",notes:""};
const profileFromLearner=(learner:LearnerProfile):EditableProfile=>{const summary=profileSummaryView(learner);return {code:learner.code,age:learner.age>0?String(learner.age):"",communication:summary.communication,supportNeeds:summary.supports.join(", "),interests:summary.currentInterests.join(", "),reinforcement:learner.reinforcementPreferences.join(", "),activityFormats:summary.learningFormat,notes:summary.keyTeachingNotes.join("; ")};};
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
  const [extraction,setExtraction]=useState<LearnerProfileExtraction|null>(null);const [form,setForm]=useState<EditableProfile>(emptyProfile);const [isLoading,setIsLoading]=useState(true);const [loadingSeconds,setLoadingSeconds]=useState(0);const [isSavingProfile,setIsSavingProfile]=useState(false);const [isEditing,setIsEditing]=useState(false);const [loadError,setLoadError]=useState<string|null>(null);const [formError,setFormError]=useState<string|null>(null);
  const loadExtraction=useCallback(async()=>{setIsLoading(true);setLoadError(null);try{const value=await lessonKitApi.getExtractedLearnerProfile(learnerId);setExtraction(value);setForm(profileFromLearner(value.learner));}catch(error){setExtraction(null);setLoadError(error instanceof Error?error.message:"Learner information is temporarily unavailable.");}finally{setIsLoading(false);}},[learnerId]);
  useEffect(()=>{void loadExtraction();},[loadExtraction]);
  useEffect(()=>{if(!isLoading){setLoadingSeconds(0);return;}const startedAt=Date.now();const timer=window.setInterval(()=>setLoadingSeconds(Math.floor((Date.now()-startedAt)/1000)),1000);return()=>window.clearInterval(timer);},[isLoading,learnerId]);
  if(isLoading){const message=loadingSeconds<8?"Reading the reviewed record…":loadingSeconds<35?"AI is organizing communication, support, and learning details…":"AI is still working. Your reviewed record is safely saved.";return <div className="v2-profile-loading" role="status" aria-live="polite"><Card><span className="v2-profile-loading__spinner" aria-hidden="true"/><h2>Preparing learner summary</h2><p>{message}</p><small>This usually takes under a minute. Please keep this page open.</small></Card></div>;}
  if(loadError||!extraction)return <div className="v2-load-error" role="alert"><Card><span className="v2-load-error__icon" aria-hidden="true">!</span><h2>AI needs another try</h2><p>Your uploaded record is safe. The AI service did not finish the learner summary this time.</p><Button onClick={()=>void loadExtraction()}>Try profile analysis again</Button></Card></div>;
  const learner=extraction.learner;const update=(field:keyof EditableProfile,value:string)=>setForm((current)=>({...current,[field]:value}));
  const factors=learner.normalizedProfile?.factors??[];
  const reviewFactor=async(factor:ProfileFactor,value?:string)=>{try{const updated=await lessonKitApi.reviewProfileFactor(learnerId,factor.id,{decision:value===undefined?"confirm":"edit",editedValue:value,expectedVersion:learner.version??1});setExtraction((current)=>current?{...current,learner:updated}:current);setForm(profileFromLearner(updated));onFeedback(`${factor.label} updated without changing other profile factors.`);}catch(error){setFormError(error instanceof Error?error.message:"The profile factor could not be updated.");}};
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
  const summaryItems=[
    {label:"Communication",icon:"💬",value:conciseInsight(form.communication)||"Needs confirmation",tone:"blue"},
    {label:"Supports",icon:"✦",value:shortList(form.supportNeeds,3),tone:"violet"},
    {label:"Interests",icon:"★",value:shortList(form.interests,3),tone:"gold"},
    {label:isNew?"Learning format":"Motivators",icon:"✓",value:conciseInsight(isNew?form.activityFormats:form.reinforcement)||"Needs confirmation",tone:"green"},
  ];
  return <section className="v2-review-page">
    <div className="v2-page-heading"><h1>Review learner summary</h1><p>Confirm the essentials before planning the lesson.</p></div>
    <Card className="v2-learner-summary-card">
      <header className="v2-learner-summary-header">
        <div className="v2-learner-identity"><LearnerAvatar learnerId={learner.id} avatar={learner.avatar} alt="" size={64}/><div><h2>{form.code||learner.code}</h2><p>{form.age?`Age ${form.age}`:"Age needs confirmation"} · {extraction.records.length} {extraction.records.length===1?"record":"records"}</p></div></div>
        <Button variant="secondary" onClick={()=>setIsEditing((value)=>!value)}>{isEditing?"Close editing":"Edit details"}</Button>
      </header>

      {!isEditing&&<>
        <div className="v2-summary-grid">{summaryItems.map((item)=><article className={`v2-summary-tile v2-summary-tile--${item.tone}`} key={item.label}><span aria-hidden>{item.icon}</span><div><small>{item.label}</small><strong title={item.value}>{item.value}</strong></div></article>)}</div>
        {form.notes&&<details className="v2-summary-details"><summary>View learner notes</summary><p>{conciseInsight(form.notes)}</p></details>}
        {isNew&&extraction.insights.length>0&&<div className="v2-summary-cues"><small>Key teaching notes</small><ul>{extraction.insights.slice(0,3).map((insight)=><li key={insight}>{conciseInsight(insight)}</li>)}</ul></div>}
        {factors.length>0&&<details className="v2-teaching-details"><summary><span>Show teaching details</span><small>{factors.length} profile constraints available when needed</small></summary><div className="v2-factor-sections">{profileFactorSections.map((section)=>{const visible=visibleFactorsForSection(factors,section.title,section.categories);if(!visible.length)return null;return <section key={section.title}><h3>{section.title}</h3><div>{visible.map((factor)=><FactorCard factor={factor} onReview={reviewFactor} key={factor.id}/>)}</div></section>;})}</div></details>}
      </>}

      {isEditing&&<div className="v2-compact-profile-editor">
        <div className="v2-form-row v2-form-row--split"><label>Learner code<input value={form.code} onChange={(event)=>update("code",event.target.value)}/></label><label>Age<input type="number" min="1" max="30" inputMode="numeric" value={form.age} placeholder="Confirm" onChange={(event)=>update("age",event.target.value)}/></label></div>
        {factors.length>0?<p className="v2-structured-edit-note">Edit individual profile factors in the structured sections. This keeps unrelated evidence and constraints intact.</p>:<>
        <ProfileField label="Primary communication" value={form.communication} onChange={(value)=>update("communication",value)}/>
        <ProfileField label="Support needs" value={form.supportNeeds} onChange={(value)=>update("supportNeeds",value)} pills/>
        <ProfileField label="Interests" value={form.interests} onChange={(value)=>update("interests",value)} pills/>
        <ProfileField label={isNew?"Best activity formats":"Reinforcement preferences"} value={isNew?form.activityFormats:form.reinforcement} onChange={(value)=>update(isNew?"activityFormats":"reinforcement",value)}/>
        <div className="v2-form-row"><label>Notes<textarea value={form.notes} onChange={(event)=>update("notes",event.target.value)}/></label></div>
        </>}
        <button className="v2-reset-link" onClick={()=>{setForm(profileFromLearner(learner));setFormError(null);}}>Reset changes</button>
      </div>}

      <div className="v2-summary-records">
        <div><div><h3>Source records</h3><p>{isNew?"Uploaded for this profile":"Records currently on file"}</p></div><button onClick={()=>void addRecord(isNew?"Additional family notes.txt":"Supplemental classroom record.txt")}>＋ Add record</button></div>
        <div className="v2-summary-record-list">{extraction.records.map((record)=><RecordCard record={record} onFeedback={onFeedback} key={record.id}/>)}</div>
        {isNew&&extraction.records.length>0&&<button className="v2-replace-link" onClick={replaceFirstRecord}>Replace first file</button>}
      </div>

      {formError&&<p className="v2-inline-error" role="alert">{formError}</p>}
      <footer className="v2-summary-actions">{onBack&&<Button variant="secondary" onClick={onBack}>Back</Button>}<Button disabled={isSavingProfile} onClick={()=>void saveAndContinue()}>{isSavingProfile?"Saving…":"Confirm & Continue"}</Button></footer>
    </Card>
  </section>;
}

function ProfileField({ label,value,onChange,pills=false }:{ label:string;value:string;onChange:(value:string)=>void;pills?:boolean }) {
  return <div className="v2-form-row"><label>{label}<div className={pills?"v2-pill-input":""}><textarea className="v2-profile-field-control" aria-label={label} rows={pills?2:3} value={value} onChange={(event)=>onChange(event.target.value)} placeholder={pills?"Separate items with commas":""}/></div></label></div>;
}

function FactorCard({factor,onReview}:{factor:ProfileFactor;onReview:(factor:ProfileFactor,value?:string)=>Promise<void>}){
  const [editing,setEditing]=useState(false);const [value,setValue]=useState(factor.value);
  const access=["sensory","visual_access","motor_access","safety","prohibited_item"].includes(factor.category)&&factor.status==="confirmed_current";
  return <article className="v2-factor-card"><div><strong>{factor.label}</strong><span className={`v2-factor-status v2-factor-status--${access?"access":factor.status}`}>{factorStatusLabel(factor)}</span></div>{editing?<><textarea aria-label={`Edit ${factor.label}`} value={value} onChange={(event)=>setValue(event.target.value)}/><div className="v2-factor-actions"><button onClick={()=>setEditing(false)}>Cancel</button><button onClick={()=>{void onReview(factor,value).then(()=>setEditing(false));}}>Save</button></div></>:<><p>{factor.value}</p>{factor.instructionalImplication&&<small><b>Teaching implication:</b> {factor.instructionalImplication}</small>}<details><summary>Source evidence</summary><small>{factor.sourceEvidence}</small></details><div className="v2-factor-actions"><button onClick={()=>setEditing(true)}>Edit</button>{factor.status==="unconfirmed"&&<button onClick={()=>void onReview(factor)}>Confirm</button>}</div></>}</article>;
}
