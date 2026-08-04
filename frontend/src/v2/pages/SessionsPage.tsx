import { useEffect,useState } from "react";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { LearnerAvatar } from "../components/Avatar";
import { SessionCompletionForm } from "../components/SessionCompletionForm";
import { Tag } from "../components/Tag";
import { lessonKitApi } from "../api/lessonKitApi";
import type { LearnerProfile,LessonSession,LessonSessionStat,SessionOutcome } from "../types";
import { readPrintableArtifact } from "../printPresetModel";

const tone={planned:"blue",in_progress:"amber",completed:"green",draft:"purple"} as const;
const activeRunStorageKey="atc-active-session-run";

export function SessionsPage({onNewSession,onResume,onFeedback}:{onNewSession:()=>void;onResume:(session:LessonSession)=>void;onFeedback:(message:string)=>void}) {
  const [sessions,setSessions]=useState<LessonSession[]>([]);
  const [stats,setStats]=useState<LessonSessionStat[]>([]);
  const [learners,setLearners]=useState<LearnerProfile[]>([]);
  const [selectedId,setSelectedId]=useState(()=>sessionStorage.getItem(activeRunStorageKey)??"s1");
  const [query,setQuery]=useState("");
  const [completing,setCompleting]=useState(false);
  const [starting,setStarting]=useState(false);
  const [error,setError]=useState("");

  const refresh=async()=>{
    const [sessionItems,summary,learnerItems]=await Promise.all([lessonKitApi.getSessions(),lessonKitApi.getSessionStats(),lessonKitApi.getLearners()]);
    setSessions(sessionItems);setStats(summary);setLearners(learnerItems);
    const active=sessionStorage.getItem(activeRunStorageKey);
    if(active&&sessionItems.some((item)=>item.id===active&&item.status==="in_progress")){setSelectedId(active);setCompleting(true);}
    else setSelectedId((current)=>sessionItems.some((item)=>item.id===current)?current:(sessionItems[0]?.id??""));
  };
  useEffect(()=>{void refresh();},[]);
  const selected=sessions.find((item)=>item.id===selectedId)??sessions[0];
  const learner=(id:string)=>learners.find((item)=>item.id===id);
  const shown=sessions.filter((session)=>`${learner(session.learnerId)?.code} ${session.goal}`.toLowerCase().includes(query.toLowerCase()));
  const duplicate=async()=>{if(!selected)return;const copy=await lessonKitApi.duplicateSession(selected.id);setSessions((current)=>[...current,copy]);setSelectedId(copy.id);setStats(await lessonKitApi.getSessionStats());onFeedback(`${selected.goal} duplicated as a draft.`);};
  const openRecorder=(id:string)=>{sessionStorage.setItem(activeRunStorageKey,id);setCompleting(true);};
  const completed=async(outcome:SessionOutcome)=>{sessionStorage.removeItem(activeRunStorageKey);setCompleting(false);await refresh();onFeedback(`Session saved: ${outcome.opportunities.valid} valid opportunities, ${outcome.responses.independentSuccessful} independent and ${outcome.responses.promptedSuccessful} prompted successes.`);};
  const start=async()=>{if(!selected?.lessonPackageId||!selected.lessonPackageRevision)return;setStarting(true);setError("");try{const packageValue=await lessonKitApi.getLessonPackage(selected.lessonPackageId);if(!packageValue.lessonSpec)throw new Error("The linked package does not contain a current LessonSpec.");const artifact=readPrintableArtifact(packageValue.id);const currentArtifact=artifact?.packageRevision===selected.lessonPackageRevision?artifact:null;await lessonKitApi.startSession(selected.id,{idempotencyKey:`start:${selected.id}:package:${selected.lessonPackageRevision}`,startedByTeacher:"current-teacher",expectedPackageRevision:selected.lessonPackageRevision,contextIds:packageValue.lessonSpec.contexts.map((item)=>item.id),pdfExportId:currentArtifact?.artifactId,printPreset:currentArtifact?.printPreset});await refresh();openRecorder(selected.id);}catch(reason){setError(reason instanceof Error?reason.message:"The session could not be started.");}finally{setStarting(false);}};

  return <section>
    <div className="v2-title-action"><div className="v2-page-heading"><h1>Sessions</h1><p>Track lesson sessions and record observable, goal-specific outcomes.</p></div><Button onClick={onNewSession}>＋ New Session</Button></div>
    <div className="v2-session-stats">{stats.map((stat)=><Card key={stat.status}><span>{stat.status==="completed"?"✓":stat.status==="planned"?"▣":stat.status==="draft"?"▤":"▷"}</span><div><b>{stat.count}</b><strong>{stat.label}</strong><small>{stat.helperText}</small></div></Card>)}</div>
    <div className={`v2-sessions-layout${completing?" is-recording":""}`}>{!completing&&<Card><h2>Recent Sessions</h2><label className="v2-search"><span>⌕</span><input value={query} onChange={(event)=>setQuery(event.target.value)} placeholder="Search sessions by learner or goal"/></label><div className="v2-session-table"><div className="v2-table-head"><span>LEARNER</span><span>GOAL</span><span>STATUS</span><span>SCHEDULED / UPDATED</span></div>{shown.map((session)=><button key={session.id} onClick={()=>{setSelectedId(session.id);setCompleting(false);}} className={selected?.id===session.id?"is-selected":""}><strong>{learner(session.learnerId)?.code}</strong><span>{session.goal}</span><Tag tone={tone[session.status]}>{session.status.replace("_"," ")}</Tag><span>{session.updatedAt} &nbsp;›</span></button>)}</div></Card>}
      {selected&&<Card className="v2-session-preview">{completing?<SessionCompletionForm sessionId={selected.id} onCancel={()=>setCompleting(false)} onCompleted={(outcome)=>void completed(outcome)}/>:<>
        <h2>Session Preview</h2><div className="v2-profile-title"><LearnerAvatar learnerId={selected.learnerId} avatar={learner(selected.learnerId)?.avatar} alt={`${learner(selected.learnerId)?.code??"Learner"} avatar`} size={64}/><div><h2>{learner(selected.learnerId)?.code}</h2><p>{selected.goal}</p></div><Tag tone={tone[selected.status]}>{selected.status}</Tag></div>
        <dl className="v2-session-details"><div><dt>◎ Goal</dt><dd>{selected.operationalizedGoal||selected.goal}</dd></div><div><dt>▤ Package revision</dt><dd>{selected.lessonPackageRevision??"Not linked"}</dd></div><div><dt>◇ Goal revision</dt><dd>{selected.goalRevision??"Not linked"}</dd></div><div><dt>◷ Last updated</dt><dd>{selected.updatedAt}</dd></div></dl>
        {error&&<p role="alert">{error}</p>}<div className="v2-session-actions"><Button onClick={()=>onResume(selected)}>▷ Resume lesson plan</Button>{selected.status==="planned"&&selected.lessonPackageId&&<Button onClick={()=>void start()} disabled={starting}>{starting?"Checking package…":"▷ Start Session"}</Button>}{selected.status==="in_progress"&&selected.lessonPackageId&&<Button onClick={()=>openRecorder(selected.id)}>Continue Recording</Button>}<Button variant="secondary" onClick={()=>void duplicate()}>Duplicate</Button>{selected.status==="completed"&&<Button variant="secondary" onClick={()=>void lessonKitApi.getSessionOutcome(selected.id).then((value)=>onFeedback(`${value.opportunities.valid} valid opportunities; ${value.responses.independentSuccessful} independent successes.`)).catch(()=>lessonKitApi.getSessionSummary(selected.id).then((value)=>onFeedback(value.overview)))}>View outcome</Button>}</div>
      </>}</Card>}
    </div>
  </section>;
}
