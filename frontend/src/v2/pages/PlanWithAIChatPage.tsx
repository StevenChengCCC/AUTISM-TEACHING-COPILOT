import { useEffect,useRef,useState } from "react";
import { AIQuestionBlock } from "../components/AIQuestionBlock";
import { TeacherAvatar } from "../components/Avatar";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { LearnerContextBar } from "../components/LearnerContextBar";
import { Tag } from "../components/Tag";
import { lessonKitApi } from "../api/lessonKitApi";
import { LessonKitApiError } from "../api/backendClient";
import type { AIChatState,LearnerProfile,LessonPackage } from "../types";

export function PlanWithAIChatPage({ learnerId,resumeExisting=false,onGenerate,onViewProfile,onChangeLearner,onFeedback }:{ learnerId:string;resumeExisting?:boolean;onGenerate:(value:LessonPackage)=>void;onViewProfile:()=>void;onChangeLearner:()=>void;onFeedback:(message:string)=>void }) {
  const [learner,setLearner]=useState<LearnerProfile|null>(null);
  const [chat,setChat]=useState<AIChatState|null>(null);
  const [generating,setGenerating]=useState(false);
  const [sending,setSending]=useState(false);
  const [loadError,setLoadError]=useState<string|null>(null);
  const [chatError,setChatError]=useState<string|null>(null);
  const [composer,setComposer]=useState("");
  const [savingQuestionId,setSavingQuestionId]=useState<string|null>(null);
  const requestController=useRef<AbortController|null>(null);
  const packageController=useRef<AbortController|null>(null);
  useEffect(()=>{
    let active=true;
    setLoadError(null);
    void Promise.all([lessonKitApi.getLearnerById(learnerId),lessonKitApi.getInitialLessonChat(learnerId,resumeExisting)])
      .then(([profile,state])=>{if(active){setLearner(profile);setChat(state);}})
      .catch((error)=>{if(active)setLoadError(error instanceof Error?error.message:"The lesson conversation could not be loaded.");});
    return()=>{active=false;requestController.current?.abort();packageController.current?.abort();};
  },[learnerId,resumeExisting]);
  async function answer(questionId:string,ids:string[],customAnswer="") {
    if(!chat||savingQuestionId)return;
    setChatError(null);
    setSavingQuestionId(questionId);
    try{setChat(await lessonKitApi.updateAIQuestionAnswer(chat.conversationId,questionId,ids,customAnswer));}
    catch(error){
      if(error instanceof LessonKitApiError&&error.status===409){
        try{
          const latest=await lessonKitApi.getLessonChat(chat.conversationId);
          const questionStillExists=latest.questions.some((question)=>question.id===questionId);
          if(!questionStillExists){setChat(latest);setChatError("The lesson suggestions changed. Review the refreshed choices.");return;}
          setChat(await lessonKitApi.updateAIQuestionAnswer(latest.conversationId,questionId,ids,customAnswer));
          setChatError("Your latest choice was saved after refreshing the lesson draft.");
          return;
        }catch(retryError){setChatError(retryError instanceof Error?retryError.message:"The refreshed choice could not be saved.");return;}
      }
      setChatError(error instanceof Error?error.message:"This answer could not be saved.");
    }
    finally{setSavingQuestionId(null);}
  }
  async function generate(){
    if(!chat?.canGenerate||generating)return;
    const controller=new AbortController();packageController.current=controller;setGenerating(true);
    try{const value=await lessonKitApi.generateLessonPackageFromDraft(chat.draft,controller.signal);try{await lessonKitApi.createSession({learnerId,status:"planned",goal:value.goal});}catch{onFeedback("The lesson kit was saved, but its session shortcut could not be created.");}onGenerate(value);}
    catch(error){if(!controller.signal.aborted)onFeedback(error instanceof Error?error.message:"Lesson package generation is temporarily unavailable.");}
    finally{if(packageController.current===controller){packageController.current=null;setGenerating(false);}}
  }
  function cancelPackageGeneration(){packageController.current?.abort();packageController.current=null;setGenerating(false);onFeedback("Lesson kit generation canceled. Your confirmed choices are still here.");}
  async function sendMessage(){
    const content=composer.trim();if(!chat||!content||sending)return;
    const firstRequest=chat.questions.length===0;
    const controller=new AbortController();requestController.current=controller;
    setSending(true);setChatError(null);setComposer("");
    try{
      const next=await lessonKitApi.submitLessonRequest(chat.conversationId,learnerId,content,chat.draft,controller.signal);
      setChat(next);
      onFeedback(firstRequest?"Lesson suggestions generated from your request.":"Follow-up note added to the lesson draft.");
    }catch(error){
      if(controller.signal.aborted)return;
      setComposer(content);
      setChatError(error instanceof Error?error.message:"Lesson planning AI is temporarily unavailable.");
    }finally{if(requestController.current===controller){requestController.current=null;setSending(false);}}
  }
  async function cancelSuggestionGeneration(){
    const controller=requestController.current;
    controller?.abort();requestController.current=null;setChatError(null);
    if(!chat)return;
    try{setChat(await lessonKitApi.cancelLessonRequest(chat.conversationId));setComposer("");onFeedback("That request was canceled. Enter the corrected teaching skill.");}
    catch(error){setChatError(error instanceof Error?error.message:"The request could not be canceled.");}
    finally{setSending(false);}
  }
  async function restartPlanning(){
    if(sending||savingQuestionId)return;
    setSending(true);setChatError(null);setComposer("");
    try{setChat(await lessonKitApi.getInitialLessonChat(learnerId,false));onFeedback("Ready for a new teaching request.");}
    catch(error){setChatError(error instanceof Error?error.message:"The lesson planner could not restart.");}
    finally{setSending(false);}
  }
  if(loadError)return <div className="v2-load-error" role="alert"><Card><span className="v2-load-error__icon" aria-hidden="true">!</span><h2>We couldn’t open this lesson plan</h2><p>{loadError}</p><Button onClick={onChangeLearner}>Choose another learner</Button></Card></div>;
  if(!learner||!chat)return <div className="v2-loading">Preparing lesson conversation…</div>;
  const hasQuestions=chat.questions.length>0;
  const answered=(question:AIChatState["questions"][number])=>Boolean(question.selectedOptionIds.length||question.customAnswer.trim()||!question.required);
  const confirmedCount=chat.questions.filter(answered).length;
  const localMock=chat.generationStatus==="local_mock"||chat.generationMetadata?.outputSource==="local_mock";
  return <><div className="v2-page-heading"><h1>Build a lesson kit</h1><p>Tell AI the teaching goal, then confirm three useful suggestions.</p></div>{localMock&&<div className="v2-generation-state v2-generation-state--mock" role="status"><strong>Local demo suggestions</strong><span>These options came from the deterministic local provider, not OpenAI. Teacher confirmation is still required.</span></div>}<LearnerContextBar learner={learner} onViewProfile={onViewProfile} onChangeLearner={onChangeLearner}/>
    <div className="v2-chat-layout"><aside><Card><h3>▤ &nbsp; Lesson context</h3><small>Learner</small><p>{learner.code} · {learner.age>0?`Age ${learner.age}`:"Age to confirm"}</p><small>Goal (draft)</small><p>{chat.draft.goalText||"Not set yet"}</p><div className="v2-ai-note">✦ {hasQuestions?"Choose what fits. You can edit any suggestion.":"Start with one short teaching request."}</div></Card><LessonKitVisualPreview/></aside>
      <Card className="v2-chat-panel"><div className="v2-chat-header"><h3>✦ &nbsp; Lesson Copilot</h3>{hasQuestions&&<button onClick={()=>void restartPlanning()} disabled={sending||Boolean(savingQuestionId)}>Change request</button>}</div>
        {!hasQuestions?<div className="v2-message-list">{chat.messages.slice(-2).map((message)=><div key={message.id} className={`v2-message v2-message--${message.role}`}><span>{message.role==="assistant"?"✦":<TeacherAvatar size={34} alt="Teacher"/>}</span><div><p>{message.content}</p></div></div>)}</div>:<div className="v2-ai-understood"><span aria-hidden="true">✓</span><div><strong>AI understood your teaching request</strong><p>Review these three suggestions. Change only what does not fit.</p></div></div>}
        {sending&&<div className="v2-chat-pending" role="status" aria-live="polite"><span className="v2-spinner"/><div><strong>Building suggestions for this lesson…</strong><small>This can take up to about 45 seconds.</small></div><button type="button" onClick={()=>void cancelSuggestionGeneration()}>Cancel</button></div>}
        {chatError&&<div className="v2-inline-error" role="alert">{chatError} <button onClick={()=>void sendMessage()}>Try again</button></div>}
        {hasQuestions&&<div className="v2-question-guide" role="note"><strong>{confirmedCount}/{chat.questions.length} confirmed</strong><span>Goal · practice setting · printable pages</span></div>}
        {hasQuestions&&<div className="v2-suggestion-board">{chat.questions.map((question,index)=><div className={`v2-suggestion-card ${answered(question)?"is-confirmed":""}`} key={question.id}><span className="v2-suggestion-number">{index+1}</span><AIQuestionBlock question={question} busy={Boolean(savingQuestionId)} onAnswer={(ids,custom)=>answer(question.id,ids,custom)}/>{savingQuestionId===question.id&&<small className="v2-saving-answer">Saving…</small>}</div>)}</div>}
        <div className={`v2-draft ${hasQuestions?"":"v2-draft--waiting"}`}><strong>✦ Current lesson plan <em>{hasQuestions?"(AI draft)":"Waiting for lesson request"}</em></strong><div><span><small>Goal</small>{chat.draft.goalText||"Not set yet"}</span><span><small>Theme</small>{chat.draft.theme||"—"}</span><span><small>Materials</small>{chat.draft.selectedMaterials.length?<span className="v2-draft-tags">{chat.draft.selectedMaterials.map((item)=><Tag key={item}>{item}</Tag>)}</span>:"—"}</span><span><small>Duration</small>{chat.draft.duration||"—"}</span></div></div>
        <div className={`v2-chat-actions ${hasQuestions?"v2-chat-actions--confirm":""}`}>{!hasQuestions&&<div className="v2-composer"><input value={composer} disabled={sending} onChange={(event)=>setComposer(event.target.value)} onKeyDown={(event)=>{if(event.key==="Enter"){event.preventDefault();void sendMessage();}}} placeholder="Example: Teach asking for help during table work"/><Button variant="secondary" disabled={!composer.trim()||sending} onClick={()=>void sendMessage()}>{sending?"Planning…":"Show suggestions"}</Button></div>}{generating&&<Button variant="secondary" onClick={cancelPackageGeneration}>Cancel generation</Button>}<Button disabled={!chat.canGenerate||generating||sending||Boolean(savingQuestionId)} title={!chat.canGenerate?"Confirm the three suggestions first.":undefined} onClick={()=>void generate()}>{generating?"Generating…":"Generate Lesson Kit"}</Button></div>
      </Card></div></>;
}

function LessonKitVisualPreview(){
  return <Card className="v2-kit-visual-preview"><div><small>YOUR PRINTABLE KIT</small><h3>Ready-to-use pages</h3></div><div className="v2-kit-thumbnail-grid">
    <figure><div className="v2-mini-visual-card"><i/><i/><i/></div><figcaption>Visual cards</figcaption></figure>
    <figure><div className="v2-mini-first-then"><i/><b>→</b><i/></div><figcaption>First–Then</figcaption></figure>
    <figure><div className="v2-mini-token-board"><i/><i/><i/><i/><i/><b>★</b></div><figcaption>Token board</figcaption></figure>
    <figure><div className="v2-mini-data-sheet"><i/><i/><i/><i/><i/><i/></div><figcaption>Data sheet</figcaption></figure>
  </div></Card>;
}
