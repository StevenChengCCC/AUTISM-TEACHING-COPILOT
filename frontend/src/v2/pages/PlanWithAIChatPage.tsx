import { useEffect,useState } from "react";
import { AIQuestionBlock } from "../components/AIQuestionBlock";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { LearnerContextBar } from "../components/LearnerContextBar";
import { Tag } from "../components/Tag";
import { lessonKitApi } from "../api/lessonKitApi";
import type { AIChatState,LearnerProfile,LessonPackage } from "../types";

export function PlanWithAIChatPage({ learnerId,onGenerate,onViewProfile,onChangeLearner,onFeedback }:{ learnerId:string;onGenerate:(value:LessonPackage)=>void;onViewProfile:()=>void;onChangeLearner:()=>void;onFeedback:(message:string)=>void }) {
  const [learner,setLearner]=useState<LearnerProfile|null>(null);
  const [chat,setChat]=useState<AIChatState|null>(null);
  const [generating,setGenerating]=useState(false);
  const [composer,setComposer]=useState("");
  useEffect(()=>{ void Promise.all([lessonKitApi.getLearnerById(learnerId),lessonKitApi.getInitialLessonChat(learnerId)]).then(([profile,state])=>{setLearner(profile);setChat(state);}); },[learnerId]);
  async function answer(questionId:string,ids:string[],customAnswer="") { if(!chat)return; setChat(await lessonKitApi.updateAIQuestionAnswer(chat.conversationId,questionId,ids,customAnswer)); }
  async function generate(){if(!chat?.canGenerate)return;setGenerating(true);try{const value=await lessonKitApi.generateLessonPackageFromDraft(chat.draft);onGenerate(value);}catch(error){onFeedback(error instanceof Error?error.message:"Lesson package generation is temporarily unavailable.");}finally{setGenerating(false);}}
  async function sendMessage(){const content=composer.trim();if(!chat||!content)return;const firstRequest=chat.questions.length===0;try{setChat(await lessonKitApi.submitLessonRequest(chat.conversationId,learnerId,content,chat.draft));setComposer("");onFeedback(firstRequest?"Lesson questions generated from your request.":"Follow-up note added to the lesson draft.");}catch(error){onFeedback(error instanceof Error?error.message:"Lesson planning AI is temporarily unavailable.");}}
  async function clearChat(){if(!chat)return;setChat(await lessonKitApi.clearLessonChat(chat.conversationId));onFeedback("Conversation messages cleared; lesson answers were kept.");}
  if(!learner||!chat)return <div className="v2-loading">Preparing lesson conversation…</div>;
  const hasQuestions=chat.questions.length>0;
  return <><div className="v2-page-heading"><h1>Plan with AI Chat</h1><p>Describe the lesson you want to teach and confirm each detail before generating materials.</p></div><LearnerContextBar learner={learner} onViewProfile={onViewProfile} onChangeLearner={onChangeLearner}/>
    <div className="v2-chat-layout"><aside><Card><h3>▤ &nbsp; Lesson context</h3><small>Learner</small><p>{learner.code} · Age {learner.age}</p><small>Goal (draft)</small><p>{chat.draft.goalText||"Not set yet"}</p><div className="v2-ai-note">✦ {hasQuestions?"Review the suggested details before generating.":"Start with a teaching request. AI will then ask a few focused questions."}</div></Card><Card><h3>▧ &nbsp; What will be generated</h3>{["Lesson Brief","Teaching Flow","Visual Cards","Help Card","Token Board","Data Sheet","Summary Template"].map((item)=><p key={item}>▧ &nbsp; {item}</p>)}</Card></aside>
      <Card className="v2-chat-panel"><div className="v2-chat-header"><h3>✦ &nbsp; Lesson Copilot</h3><button onClick={()=>void clearChat()} disabled={chat.messages.length===0}>Clear chat</button></div><div className="v2-message-list">{chat.messages.map((message)=><div key={message.id} className={`v2-message v2-message--${message.role}`}><span>{message.role==="assistant"?"✦":"👩🏻"}</span><div><p>{message.content}</p><small>{message.createdAt}</small></div></div>)}</div>
        {hasQuestions&&<div className="v2-question-list">{chat.questions.map((question)=><AIQuestionBlock key={question.id} question={question} onAnswer={(ids,custom)=>void answer(question.id,ids,custom)}/>)}</div>}
        <div className={`v2-draft ${hasQuestions?"":"v2-draft--waiting"}`}><strong>✦ Current lesson plan <em>{hasQuestions?"(AI draft)":"Waiting for lesson request"}</em></strong><div><span><small>Goal</small>{chat.draft.goalText||"Not set yet"}</span><span><small>Theme</small>{chat.draft.theme||"—"}</span><span><small>Materials</small>{chat.draft.selectedMaterials.length?<span className="v2-draft-tags">{chat.draft.selectedMaterials.map((item)=><Tag key={item}>{item}</Tag>)}</span>:"—"}</span><span><small>Duration</small>{chat.draft.duration||"—"}</span></div></div>
        <div className="v2-chat-actions"><div className="v2-composer"><input value={composer} onChange={(event)=>setComposer(event.target.value)} onKeyDown={(event)=>{if(event.key==="Enter")void sendMessage();}} placeholder="Tell AI what you want to teach, e.g. ‘I want to teach asking for help.’"/><Button variant="secondary" disabled={!composer.trim()} onClick={()=>void sendMessage()}>Send</Button></div><Button disabled={!chat.canGenerate||generating} title={!chat.canGenerate?"Send a lesson request and answer required questions first.":undefined} onClick={()=>void generate()}>{generating?"Generating…":"Generate Lesson Package"}</Button></div>
      </Card></div></>;
}
