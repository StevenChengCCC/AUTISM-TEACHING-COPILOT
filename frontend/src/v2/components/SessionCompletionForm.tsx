import { useEffect,useRef,useState } from "react";
import { Button } from "../components/Button";
import { lessonKitApi } from "../api/lessonKitApi";
import { LessonKitApiError } from "../api/backendClient";
import {
  applyRecorderResult,autosaveLabel,codingDefinitions,draftPatch,incompleteTrialDetails,
  materialCooccurrenceNotice,rawTrialCounts,resultPathForOutcome,resultPathLabels,
  trialRequirementReasons,type AutosavePhase,type RecorderResultPath,
} from "../sessionRunDraftModel";
import type { SessionOutcome,SessionPromptLevel,SessionResponseMode,SessionRunDraft,SessionRunDraftTrial,SessionRunState } from "../types";

const promptLabels:Record<SessionPromptLevel,string>={independent:"Independent",gesture:"Gesture",visual:"Visual",model:"Model",brief_verbal:"Brief verbal",other:"Other"};
const promptChoices=(Object.entries(promptLabels) as Array<[SessionPromptLevel,string]>).filter(([value])=>value!=="independent");

function resultSummary(trial:SessionRunDraftTrial):string {
  const path=resultPathForOutcome(trial.outcome);
  return path?resultPathLabels[path]:"Not recorded";
}

export function SessionCompletionForm({sessionId,onCancel,onCompleted}:{sessionId:string;onCancel:()=>void;onCompleted:(outcome:SessionOutcome)=>void}) {
  const [run,setRun]=useState<SessionRunState|null>(null);
  const [draft,setDraft]=useState<SessionRunDraft|null>(null);
  const draftRef=useRef<SessionRunDraft|null>(null);
  const timerRef=useRef<ReturnType<typeof setTimeout>|null>(null);
  const pendingKeyRef=useRef<string|null>(null);
  const editSerialRef=useRef(0);
  const saveInFlightRef=useRef<Promise<SessionRunState|null>|null>(null);
  const historyRef=useRef<SessionRunDraft[]>([]);
  const advanceLockRef=useRef(false);
  const [changeSerial,setChangeSerial]=useState(0);
  const [phase,setPhase]=useState<AutosavePhase>("loading");
  const [error,setError]=useState("");
  const [closing,setClosing]=useState(false);

  const install=(value:SessionRunState)=>{setRun(value);setDraft(value.draft);draftRef.current=value.draft;setPhase("saved");};
  useEffect(()=>{void lessonKitApi.getSessionRun(sessionId).then(install).catch((reason)=>{setPhase("failed");setError(reason instanceof Error?reason.message:"Could not resume saved observations.");});return()=>{if(timerRef.current)clearTimeout(timerRef.current);};},[sessionId]);

  const queueAutosave=(updated:SessionRunDraft)=>{draftRef.current=updated;setDraft(updated);editSerialRef.current+=1;pendingKeyRef.current=crypto.randomUUID();setChangeSerial((value)=>value+1);setPhase("idle");setError("");};
  const edit=(change:(value:SessionRunDraft)=>SessionRunDraft)=>{const current=draftRef.current;if(!current)return;historyRef.current.push(current);queueAutosave(change(current));};
  const save=async(status:"in_progress"|"ready_for_closeout"|undefined=undefined):Promise<SessionRunState|null>=>{if(saveInFlightRef.current){await saveInFlightRef.current;return save(status);}const local=draftRef.current;if(!local)return null;const key=pendingKeyRef.current??crypto.randomUUID();const serial=editSerialRef.current;pendingKeyRef.current=key;setPhase("saving");setError("");const operation=(async()=>{try{const value=await lessonKitApi.patchSessionRunDraft(sessionId,draftPatch(local,key,status));if(editSerialRef.current===serial){pendingKeyRef.current=null;install(value);return value;}const latest=draftRef.current;if(!latest)return value;const rebased={...latest,version:value.draft.version,lastSavedAt:value.draft.lastSavedAt};draftRef.current=rebased;setDraft(rebased);setRun({...value,draft:rebased});setPhase("idle");return {...value,draft:rebased};}catch(reason){setPhase(reason instanceof LessonKitApiError&&reason.code==="version_conflict"?"conflict":"failed");setError(reason instanceof Error?reason.message:"Observations could not be saved. Local input is preserved.");return null;}})();saveInFlightRef.current=operation;try{return await operation;}finally{if(saveInFlightRef.current===operation)saveInFlightRef.current=null;}};
  useEffect(()=>{if(changeSerial===0)return;if(timerRef.current)clearTimeout(timerRef.current);timerRef.current=setTimeout(()=>{void save();},450);return()=>{if(timerRef.current)clearTimeout(timerRef.current);};},[changeSerial]);

  const updateTrial=(index:number,change:(trial:SessionRunDraftTrial)=>SessionRunDraftTrial)=>edit((current)=>({...current,trials:current.trials.map((trial,trialIndex)=>trialIndex===index?change(trial):trial),observations:{...current.observations,rawCountsConfirmed:false}}));
  const undo=()=>{const current=draftRef.current;const previous=historyRef.current.pop();if(!current||!previous)return;queueAutosave({...previous,version:current.version,lastSavedAt:current.lastSavedAt});};
  const reloadServer=async()=>{setPhase("loading");setError("");try{install(await lessonKitApi.getSessionRun(sessionId));pendingKeyRef.current=null;historyRef.current=[];}catch(reason){setPhase("failed");setError(reason instanceof Error?reason.message:"Could not reload the saved draft.");}};
  const retryLocal=async()=>{const local=draftRef.current;if(!local)return;setPhase("saving");try{const server=await lessonKitApi.getSessionRun(sessionId);const retry={...local,version:server.draft.version};draftRef.current=retry;setDraft(retry);pendingKeyRef.current=crypto.randomUUID();await save();}catch(reason){setPhase("failed");setError(reason instanceof Error?reason.message:"Could not retry the local draft.");}};
  const submit=async()=>{if(!run||!draftRef.current)return;if(timerRef.current)clearTimeout(timerRef.current);const incomplete=incompleteTrialDetails(draftRef.current,run.snapshot.acceptedResponseModes);if(incomplete.length){setError(incomplete.map((item)=>`Trial ${item.opportunityNumber}: ${item.reasons.join(", ")}`).join(" · "));return;}if(!draftRef.current.observations.rawCountsConfirmed){setError("Confirm the displayed valid and invalid trial counts before completion.");return;}setClosing(true);const saved=await save("ready_for_closeout");if(!saved){setClosing(false);return;}try{const outcome=await lessonKitApi.completeSessionRunDraft(sessionId,{expectedVersion:saved.draft.version,idempotencyKey:`complete-${saved.snapshot.id}`});onCompleted(outcome);}catch(reason){setError(reason instanceof Error?reason.message:"Session outcome could not be saved.");setClosing(false);}};

  if(!run||!draft)return <div className="v2-session-completion"><p role={error?"alert":"status"}>{error||autosaveLabel(phase)}</p><Button variant="secondary" onClick={onCancel}>Cancel</Button></div>;
  const locked=draft.status==="completed"||draft.status==="discarded";
  const activeIndex=Math.min(draft.trials.length-1,Math.max(0,draft.activeTrialNumber-1));
  const active=draft.trials[activeIndex];
  const counts=rawTrialCounts(draft);
  const closeout=draft.status==="ready_for_closeout";
  const lastContext=draft.trials.slice(0,activeIndex).reverse().find((item)=>item.contextId)?.contextId??null;
  const remembered=Boolean(active.contextId&&active.contextId===lastContext);
  const currentPath=resultPathForOutcome(active.outcome);
  const currentReasons=trialRequirementReasons(active,run.snapshot.acceptedResponseModes);
  const contextsPracticed=[...new Set(draft.trials.filter((item)=>item.outcome&&item.contextLabel).map((item)=>item.contextLabel as string))];
  const breakSummary={requested:draft.trials.filter((item)=>item.breakRequested===true).length,delivered:draft.trials.filter((item)=>item.breakDelivered===true).length,returned:draft.trials.filter((item)=>item.returnedAfterBreak===true).length};
  const editWhole=(change:(value:SessionRunDraft)=>SessionRunDraft)=>edit(change);
  const toggleMaterial=(kind:"helpfulMaterialIds"|"unhelpfulMaterialIds",materialId:string)=>editWhole((current)=>{const other=kind==="helpfulMaterialIds"?"unhelpfulMaterialIds":"helpfulMaterialIds";const selected=current[kind].includes(materialId);return {...current,[kind]:selected?current[kind].filter((id)=>id!==materialId):[...current[kind],materialId],[other]:current[other].filter((id)=>id!==materialId)};});
  const openTrial=(number:number)=>editWhole((current)=>({...current,status:"in_progress",activeTrialNumber:number}));
  const advance=()=>{if(advanceLockRef.current)return;advanceLockRef.current=true;setTimeout(()=>{advanceLockRef.current=false;},250);if(currentReasons.length){setError(`Trial ${active.opportunityNumber}: ${currentReasons.join(", ")}.`);return;}if(activeIndex===draft.trials.length-1){editWhole((current)=>({...current,status:"ready_for_closeout"}));return;}editWhole((current)=>{const next=current.trials[activeIndex+1];const rememberedContext=next.contextId?next:{...next,contextId:active.contextId,contextLabel:active.contextLabel};return {...current,activeTrialNumber:active.opportunityNumber+1,trials:current.trials.map((trial,index)=>index===activeIndex+1?rememberedContext:trial)};});};

  return <div className="v2-session-completion v2-classroom-recorder">
    <header className="v2-recorder-sticky"><div><h3>{closeout?"Review and close out":"Record session"}</h3><p><strong>{counts.recorded} completed</strong> · {counts.remaining} remaining</p></div><p className={`v2-autosave-state is-${phase}`} role="status">{autosaveLabel(phase,draft.lastSavedAt)}</p></header>
    <div className="v2-recorder-lineage"><p><strong>Goal:</strong> {run.snapshot.operationalizedGoal}</p><p><strong>Frozen revisions:</strong> package {run.snapshot.packageRevision} · LessonSpec {run.snapshot.lessonSpecRevision} · {Object.keys(run.snapshot.materialRevisions).length} materials</p>{run.snapshot.pdfArtifact&&<p><strong>Printed copy:</strong> {run.snapshot.pdfArtifact.printPreset.split("_").join(" ")} · manifest v{run.snapshot.pdfArtifact.manifestVersion} · {run.snapshot.pdfArtifact.pageSize} · {run.snapshot.pdfArtifact.textProfile === "large" ? "Large Print" : "Standard text"}</p>}</div>
    {run.packageChanged&&<p className="v2-session-revision-warning" role="status">{run.packageChangeWarning}</p>}
    {closeout?<section className="v2-closeout" aria-label="Session closeout review">
      <section className="v2-closeout-summary"><h4>Raw trial count</h4><div className="v2-count-grid"><strong>{counts.valid}<span>Valid</span></strong><strong>{counts.invalid}<span>Invalid</span></strong><strong>{counts.recorded}<span>Recorded</span></strong></div><label className="v2-confirm-row"><input type="checkbox" checked={draft.observations.rawCountsConfirmed} onChange={(event)=>editWhole((current)=>({...current,observations:{...current.observations,rawCountsConfirmed:event.target.checked}}))}/> I confirm these raw valid and invalid counts match my observations.</label></section>
      <section><h4>Observed trials</h4><div className="v2-trial-review-list">{draft.trials.map((trial)=><article key={trial.trialId}><div><strong>Trial {trial.opportunityNumber}: {resultSummary(trial)}</strong><span>{trial.contextLabel||"Context missing"}{trial.responseMode&&trial.responseMode!=="none"?` · ${trial.responseMode}`:""}{trial.promptLevel?` · ${promptLabels[trial.promptLevel]}`:""}</span></div><button type="button" onClick={()=>openTrial(trial.opportunityNumber)}>Edit trial {trial.opportunityNumber}</button></article>)}</div></section>
      <section><h4>Derived review</h4><p>Contexts practiced: {contextsPracticed.join("; ")||"None recorded"}</p><p>Break/return: {breakSummary.requested} requested · {breakSummary.delivered} honored · {breakSummary.returned} returned</p><p>{draft.trials.filter((item)=>item.outcome==="independent_success").length} independent · {draft.trials.filter((item)=>item.outcome==="prompted_success").length} prompted · {draft.trials.filter((item)=>item.outcome==="not_observed_unsuccessful").length} not observed/unsuccessful</p></section>
      <section><h4>Engagement</h4><div className="v2-rating-row" role="group" aria-label="Engagement rating">{[0,1,2,3,4].map((value)=><button type="button" aria-pressed={draft.observations.engagementLevel===value} key={value} onClick={()=>editWhole((current)=>({...current,observations:{...current.observations,engagementLevel:value}}))}>{value}</button>)}</div><h4>Regulation</h4><div className="v2-rating-row" role="group" aria-label="Regulation rating">{[0,1,2,3,4].map((value)=><button type="button" aria-pressed={draft.observations.regulationLevel===value} key={value} onClick={()=>editWhole((current)=>({...current,observations:{...current.observations,regulationLevel:value}}))}>{value}</button>)}</div></section>
      <section><h4>Generalization</h4><div className="v2-choice-grid three" role="group" aria-label="Generalization status">{([['observed','Observed'],['not_observed','Not observed'],['not_attempted','Not attempted']] as const).map(([value,label])=><button type="button" aria-pressed={draft.generalization.status===value} key={value} onClick={()=>editWhole((current)=>({...current,generalization:{...current.generalization,status:value}}))}>{label}</button>)}</div></section>
      <section><h4>Material notes</h4><p>{materialCooccurrenceNotice}</p><div className="v2-material-closeout"><fieldset><legend>Helpful during this session</legend>{Object.entries(run.snapshot.materialLabels).map(([id,label])=><label key={id}><input type="checkbox" checked={draft.helpfulMaterialIds.includes(id)} onChange={()=>toggleMaterial("helpfulMaterialIds",id)}/>{label}</label>)}</fieldset><fieldset><legend>Needs change before reuse</legend>{Object.entries(run.snapshot.materialLabels).map(([id,label])=><label key={id}><input type="checkbox" checked={draft.unhelpfulMaterialIds.includes(id)} onChange={()=>toggleMaterial("unhelpfulMaterialIds",id)}/>{label}</label>)}</fieldset></div></section>
      <label className="v2-full-field">Teacher note<textarea value={draft.observations.teacherNotes} maxLength={2000} onChange={(event)=>editWhole((current)=>({...current,observations:{...current.observations,teacherNotes:event.target.value}}))}/></label>
      <details><summary>Coding definitions used in print and digital recording</summary><ul>{codingDefinitions(run.snapshot).map((value)=><li key={value}>{value}</li>)}</ul><p>The goal-specific printable data sheet remains available in the approved package; device use is optional.</p></details>
      {error&&<p role="alert">{error}</p>}
      <div className="v2-session-actions"><Button variant="secondary" onClick={()=>openTrial(draft.activeTrialNumber)}>Back to trial {draft.activeTrialNumber}</Button><Button onClick={()=>void submit()} disabled={closing||phase==="saving"}>{closing?"Completing…":"Confirm and complete session"}</Button></div>
    </section>:<section className="v2-active-trial" aria-label={`Active trial ${active.opportunityNumber}`}>
      <div className="v2-active-trial-heading"><div><span>Current trial</span><h4>Trial {active.opportunityNumber} of {draft.trials.length}</h4></div>{remembered&&<span className="v2-remembered-context">Context remembered — tap another to change</span>}</div>
      <fieldset className="v2-result-picker"><legend>What did you observe?</legend><div className="v2-result-grid">{(Object.keys(resultPathLabels) as RecorderResultPath[]).map((path)=><button type="button" key={path} aria-pressed={currentPath===path} onClick={()=>updateTrial(activeIndex,(trial)=>applyRecorderResult(trial,path,run.snapshot.acceptedResponseModes))}>{resultPathLabels[path]}</button>)}</div></fieldset>
      {currentPath&&<>
        <fieldset><legend>Context practiced</legend><div className="v2-choice-grid">{run.snapshot.teacherConfirmedContexts.map((context)=><button type="button" key={context.id} aria-pressed={active.contextId===context.id} onClick={()=>updateTrial(activeIndex,(trial)=>({...trial,contextId:context.id,contextLabel:context.label}))}>{context.label}</button>)}</div></fieldset>
        {(currentPath==="independent"||currentPath==="prompted")&&<fieldset><legend>Response mode</legend>{run.snapshot.acceptedResponseModes.length===1?<p>Only approved mode: <strong>{run.snapshot.acceptedResponseModes[0]}</strong></p>:<div className="v2-choice-grid compact">{run.snapshot.acceptedResponseModes.map((mode)=><button type="button" key={mode} aria-pressed={active.responseMode===mode} onClick={()=>updateTrial(activeIndex,(trial)=>({...trial,responseMode:mode as SessionResponseMode}))}>{mode}</button>)}</div>}</fieldset>}
        {currentPath==="independent"&&<p className="v2-neutral-note">Prompt: none used. No prompt value is inferred or stored.</p>}
        {currentPath==="prompted"&&<fieldset><legend>Prompt used</legend><div className="v2-choice-grid compact">{promptChoices.map(([value,label])=><button type="button" key={value} aria-pressed={active.promptLevel===value} onClick={()=>updateTrial(activeIndex,(trial)=>({...trial,promptLevel:value}))}>{label}</button>)}</div></fieldset>}
        {currentPath==="break_honored"&&<fieldset><legend>Break or stop details</legend><div className="v2-binary-row"><span>Requested?</span><button type="button" aria-pressed={active.breakRequested===true} onClick={()=>updateTrial(activeIndex,(trial)=>({...trial,breakRequested:true}))}>Yes</button><button type="button" aria-pressed={active.breakRequested===false} onClick={()=>updateTrial(activeIndex,(trial)=>({...trial,breakRequested:false}))}>No</button></div><p>Honored: <strong>Yes</strong> — recorded from your selected result.</p><div className="v2-binary-row"><span>Returned?</span><button type="button" aria-pressed={active.returnedAfterBreak===true} onClick={()=>updateTrial(activeIndex,(trial)=>({...trial,returnedAfterBreak:true}))}>Yes</button><button type="button" aria-pressed={active.returnedAfterBreak===false} onClick={()=>updateTrial(activeIndex,(trial)=>({...trial,returnedAfterBreak:false}))}>No / not yet</button></div></fieldset>}
        <fieldset><legend>Materials present (optional)</legend><p>{materialCooccurrenceNotice}</p><div className="v2-material-chips">{Object.entries(run.snapshot.materialLabels).map(([materialId,label])=><label key={materialId}><input type="checkbox" checked={active.materialIdsUsed.includes(materialId)} onChange={(event)=>updateTrial(activeIndex,(trial)=>({...trial,materialIdsUsed:event.target.checked?[...trial.materialIdsUsed,materialId]:trial.materialIdsUsed.filter((id)=>id!==materialId)}))}/>{label}</label>)}</div></fieldset>
        <label className="v2-full-field">{currentPath==="invalid"?"Why was this opportunity invalid?":currentPath==="break_honored"&&active.breakRequested===false?"Briefly describe the honored stop":"Short note (optional)"}<textarea maxLength={500} value={active.note} onChange={(event)=>updateTrial(activeIndex,(trial)=>({...trial,note:event.target.value}))}/></label>
        {(currentPath==="independent"||currentPath==="prompted")&&<details><summary>Optional timing detail</summary><label className="v2-full-field">Latency seconds<input type="number" min="0" step="0.1" value={active.latencySeconds??""} onChange={(event)=>updateTrial(activeIndex,(trial)=>({...trial,latencySeconds:event.target.value===""?null:Number(event.target.value)}))}/></label></details>}
      </>}
      {error&&<p role="alert">{error}</p>}
      <div className="v2-recorder-actions"><Button variant="secondary" onClick={undo} disabled={historyRef.current.length===0}>Undo last change</Button><Button onClick={advance} disabled={!currentPath}>{activeIndex===draft.trials.length-1?"Review & close out":"Next Trial"}</Button></div>
    </section>}
    {phase==="conflict"&&<div className="v2-session-actions"><Button variant="secondary" onClick={()=>void retryLocal()}>Retry local changes</Button><Button variant="secondary" onClick={()=>void reloadServer()}>Reload saved draft</Button></div>}
    {!closeout&&<div className="v2-session-actions"><Button variant="secondary" onClick={onCancel} disabled={closing}>Back to sessions</Button></div>}
  </div>;
}
