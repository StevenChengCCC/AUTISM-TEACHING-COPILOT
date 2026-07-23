import { useEffect,useState } from "react";
import { AIQuestionBlock } from "../components/AIQuestionBlock";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { LearnerContextBar } from "../components/LearnerContextBar";
import { Tag } from "../components/Tag";
import { lessonKitApi } from "../api/lessonKitApi";
import type { AIChatState,LearnerProfile,LessonPackage } from "../types";

export function PlanWithAIChatPage({ learnerId,resumeExisting=false,onGenerate,onViewProfile,onChangeLearner,onFeedback }:{ learnerId:string;resumeExisting?:boolean;onGenerate:(value:LessonPackage)=>void;onViewProfile:()=>void;onChangeLearner:()=>void;onFeedback:(message:string)=>void }) {
  const [learner,setLearner]=useState<LearnerProfile|null>(null);
  const [chat,setChat]=useState<AIChatState|null>(null);
  const [generating,setGenerating]=useState(false);
  const [sending,setSending]=useState(false);
  const [loadError,setLoadError]=useState<string|null>(null);
  const [chatError,setChatError]=useState<string|null>(null);
  const [composer,setComposer]=useState("");
  useEffect(()=>{
    setLoadError(null);
    void Promise.all([lessonKitApi.getLearnerById(learnerId),lessonKitApi.getInitialLessonChat(learnerId,resumeExisting)])
      .then(([profile,state])=>{setLearner(profile);setChat(state);})
      .catch((error)=>setLoadError(error instanceof Error?error.message:"The lesson conversation could not be loaded."));
  },[learnerId,resumeExisting]);
  async function answer(questionId:string,ids:string[],customAnswer="") { if(!chat)return; setChat(await lessonKitApi.updateAIQuestionAnswer(chat.conversationId,questionId,ids,customAnswer)); }
  async function generate(){if(!chat?.canGenerate)return;setGenerating(true);try{const value=await lessonKitApi.generateLessonPackageFromDraft(chat.draft);try{await lessonKitApi.createSession({learnerId,status:"draft",goal:value.goal});}catch{onFeedback("The lesson kit was saved, but its session shortcut could not be created.");}onGenerate(value);}catch(error){onFeedback(error instanceof Error?error.message:"Lesson package generation is temporarily unavailable.");}finally{setGenerating(false);}}
  async function sendMessage(){
    const content=composer.trim();if(!chat||!content||sending)return;
    const firstRequest=chat.questions.length===0;
    setSending(true);setChatError(null);setComposer("");
    try{
      setChat(await lessonKitApi.submitLessonRequest(chat.conversationId,learnerId,content,chat.draft));
      onFeedback(firstRequest?"Lesson questions generated from your request.":"Follow-up note added to the lesson draft.");
    }catch(error){
      setComposer(content);
      setChatError(error instanceof Error?error.message:"Lesson planning AI is temporarily unavailable.");
    }finally{setSending(false);}
  }
  async function clearChat(){if(!chat)return;setChat(await lessonKitApi.clearLessonChat(chat.conversationId));onFeedback("Conversation messages cleared; lesson answers were kept.");}
  if(loadError)return <div className="v2-load-error" role="alert"><Card><span className="v2-load-error__icon" aria-hidden="true">!</span><h2>We couldn’t open this lesson plan</h2><p>{loadError}</p><Button onClick={onChangeLearner}>Choose another learner</Button></Card></div>;
  if(!learner||!chat)return <div className="v2-loading">Preparing lesson conversation…</div>;
  const hasQuestions=chat.questions.length>0;
  const localMock=chat.generationStatus==="local_mock"||chat.generationMetadata?.outputSource==="local_mock";
  return <><div className="v2-page-heading"><h1>Plan with AI Chat</h1><p>Describe the lesson you want to teach and confirm each detail before generating materials.</p></div>{localMock&&<div className="v2-generation-state v2-generation-state--mock" role="status"><strong>Local demo suggestions</strong><span>These options came from the deterministic local provider, not OpenAI. Teacher confirmation is still required.</span></div>}<LearnerContextBar learner={learner} onViewProfile={onViewProfile} onChangeLearner={onChangeLearner}/>
    <div className="v2-chat-layout"><aside><Card><h3>▤ &nbsp; Lesson context</h3><small>Learner</small><p>{learner.code} · {learner.age>0?`Age ${learner.age}`:"Age to confirm"}</p><small>Goal (draft)</small><p>{chat.draft.goalText||"Not set yet"}</p><div className="v2-ai-note">✦ {hasQuestions?"Review the suggested details before generating.":"Start with a teaching request. AI will then ask a few focused questions."}</div></Card><Card><h3>▧ &nbsp; What will be generated</h3>{["Lesson Brief","Teaching Flow","Visual Cards","Help Card","Token Board","Data Sheet","Summary Template"].map((item)=><p key={item}>▧ &nbsp; {item}</p>)}</Card></aside>
      <Card className="v2-chat-panel"><div className="v2-chat-header"><h3>✦ &nbsp; Lesson Copilot</h3><button onClick={()=>void clearChat()} disabled={chat.messages.length===0}>Clear chat</button></div><div className="v2-message-list">{chat.messages.map((message)=><div key={message.id} className={`v2-message v2-message--${message.role}`}><span>{message.role==="assistant"?"✦":"👩🏻"}</span><div><p>{message.content}</p><small>{message.createdAt}</small></div></div>)}</div>
        {sending&&<div className="v2-chat-pending" role="status" aria-live="polite"><span className="v2-spinner"/><div><strong>Building questions for this lesson…</strong><small>This can take up to about 45 seconds.</small></div></div>}
        {chatError&&<div className="v2-inline-error" role="alert">{chatError} <button onClick={()=>void sendMessage()}>Try again</button></div>}
        {hasQuestions&&<div className="v2-question-list">{chat.questions.map((question)=><AIQuestionBlock key={question.id} question={question} onAnswer={(ids,custom)=>void answer(question.id,ids,custom)}/>)}</div>}
        <div className={`v2-draft ${hasQuestions?"":"v2-draft--waiting"}`}><strong>✦ Current lesson plan <em>{hasQuestions?"(AI draft)":"Waiting for lesson request"}</em></strong><div><span><small>Goal</small>{chat.draft.goalText||"Not set yet"}</span><span><small>Theme</small>{chat.draft.theme||"—"}</span><span><small>Materials</small>{chat.draft.selectedMaterials.length?<span className="v2-draft-tags">{chat.draft.selectedMaterials.map((item)=><Tag key={item}>{item}</Tag>)}</span>:"—"}</span><span><small>Duration</small>{chat.draft.duration||"—"}</span></div></div>
        <div className="v2-chat-actions"><div className="v2-composer"><input value={composer} disabled={sending} onChange={(event)=>setComposer(event.target.value)} onKeyDown={(event)=>{if(event.key==="Enter"){event.preventDefault();void sendMessage();}}} placeholder="Tell AI what you want to teach, e.g. ‘I want to teach counting.’"/><Button variant="secondary" disabled={!composer.trim()||sending} onClick={()=>void sendMessage()}>{sending?"Sending…":"Send"}</Button></div><Button disabled={!chat.canGenerate||generating||sending} title={!chat.canGenerate?"Send a lesson request and answer required questions first.":undefined} onClick={()=>void generate()}>{generating?"Generating…":"Generate Lesson Package"}</Button></div>
      </Card></div></>;
}
