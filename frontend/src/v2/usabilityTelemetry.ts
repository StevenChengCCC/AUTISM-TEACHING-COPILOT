export type StudyTask = "prepare_package"|"locate_and_print_subset"|"start_session"|"record_valid_trial"|"recover_after_reload_or_conflict"|"complete_closeout"|"understand_progress_and_recommendation"|"inspect_print_output"|"compare_current_workflow";
export type StudyEvent = {schemaVersion:"usability-event-v1";eventId:string;participantId:string;syntheticCaseId:string;eventName:"task_started"|"task_completed"|"task_abandoned"|"workflow_error"|"retry"|"assistance_requested"|"task_rating";taskName:StudyTask;occurredAt:string;durationMs?:number;interactionCount?:number;rating?:number;outcome?:"success"|"failure"|"abandoned";errorCategory?:string};

const STORAGE_KEY="autism-teaching-copilot.usability-events.v1",CONSENT_KEY="autism-teaching-copilot.usability-opt-in.v1";
const participantPattern=/^P-[A-Z0-9]{3,12}$/,syntheticCasePattern=/^SYN-[A-Z0-9-]{2,24}$/,errorPattern=/^[a-z][a-z0-9_]{1,48}$/;
const allowedKeys=new Set(["schemaVersion","eventId","participantId","syntheticCaseId","eventName","taskName","occurredAt","durationMs","interactionCount","rating","outcome","errorCategory"]);

export function validateStudyEvent(event:StudyEvent):void {
  if(Object.keys(event).some((key)=>!allowedKeys.has(key)))throw new Error("Unsupported telemetry field.");
  if(!participantPattern.test(event.participantId))throw new Error("Use a pseudonymous participant ID such as P-001.");
  if(!syntheticCasePattern.test(event.syntheticCaseId))throw new Error("Only a synthetic case ID may be recorded.");
  if(event.durationMs!==undefined&&(event.durationMs<0||event.durationMs>7_200_000))throw new Error("Duration is outside the study range.");
  if(event.interactionCount!==undefined&&(event.interactionCount<0||event.interactionCount>1000))throw new Error("Interaction count is outside the study range.");
  if(event.rating!==undefined&&(event.rating<1||event.rating>5))throw new Error("Rating must be 1–5.");
  if(event.errorCategory!==undefined&&!errorPattern.test(event.errorCategory))throw new Error("Use a predefined error category.");
}
export function telemetryOptedIn(storage:Storage=window.localStorage):boolean{return storage.getItem(CONSENT_KEY)==="true";}
export function setTelemetryOptIn(enabled:boolean,storage:Storage=window.localStorage):void{storage.setItem(CONSENT_KEY,String(enabled));}
export function readLocalStudyEvents(storage:Storage=window.localStorage):StudyEvent[]{try{return (JSON.parse(storage.getItem(STORAGE_KEY)??"[]") as StudyEvent[]).filter((event)=>{try{validateStudyEvent(event);return true;}catch{return false;}});}catch{return [];}}
export function recordLocalStudyEvent(event:StudyEvent,storage:Storage=window.localStorage):StudyEvent[]{if(!telemetryOptedIn(storage))throw new Error("Study measurement is disabled until the participant opts in.");validateStudyEvent(event);const current=readLocalStudyEvents(storage);current.push(event);storage.setItem(STORAGE_KEY,JSON.stringify(current));return current;}
export function deleteLocalStudyEvents(storage:Storage=window.localStorage):void{storage.removeItem(STORAGE_KEY);}
export const studyTaskLabels:Record<StudyTask,string>={prepare_package:"Prepare a lesson package",locate_and_print_subset:"Locate and print the right subset",start_session:"Start a session",record_valid_trial:"Record one valid trial",recover_after_reload_or_conflict:"Recover after reload or conflict",complete_closeout:"Complete closeout",understand_progress_and_recommendation:"Understand progress and next-session guidance",inspect_print_output:"Inspect print readability and usefulness",compare_current_workflow:"Compare with the current workflow"};
