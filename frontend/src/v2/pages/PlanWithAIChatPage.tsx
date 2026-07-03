import { useEffect,useState } from "react";
import { AIQuestionBlock } from "../components/AIQuestionBlock";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { LearnerContextBar } from "../components/LearnerContextBar";
import { Tag } from "../components/Tag";
import { lessonKitMockApi } from "../mockApi";
import type { AIChatState,LearnerProfile,LessonPackage } from "../types";

export function PlanWithAIChatPage({ learnerId,onGenerate,onViewProfile,onChangeLearner,onFeedback }:{ learnerId:string;onGenerate:(value:LessonPackage)=>void;onViewProfile:()=>void;onChangeLearner:()=>void;onFeedback:(message:string)=>void }) {
  const [learner,setLearner]=useState<LearnerProfile|null>(null);
  const [chat,setChat]=useState<AIChatState|null>(null);
  const [generating,setGenerating]=useState(false);
  const [composer,setComposer]=useState("");
  useEffect(()=>{ void Promise.all([lessonKitMockApi.getLearnerById(learnerId),lessonKitMockApi.getInitialLessonChat(learnerId)]).then(([profile,state])=>{setLearner(profile);setChat(state);}); },[learnerId]);
  async function answer(questionId:string,ids:string[],customAnswer="") { if(!chat)return; setChat(await lessonKitMockApi.updateAIQuestionAnswer(chat.conversationId,questionId,ids,customAnswer)); }
  async function generate(){if(!chat?.canGenerate)return;setGenerating(true);const value=await lessonKitMockApi.generateLessonPackageFromDraft(chat.draft);onGenerate(value);}
  async function sendMessage(){const content=composer.trim();if(!chat||!content)return;setChat(await lessonKitMockApi.sendChatMessage(chat.conversationId,content));setComposer("");onFeedback("Message added to the mock lesson conversation.");}
  async function clearChat(){if(!chat)return;setChat(await lessonKitMockApi.clearLessonChat(chat.conversationId));onFeedback("Conversation messages cleared; lesson answers were kept.");}
  if(!learner||!chat)return <div className="v2-loading">Preparing lesson conversation…</div>;
  return <><div className="v2-page-heading"><h1>Plan with AI Chat</h1><p>Describe the lesson you want to teach and confirm each detail before generating materials.</p></div><LearnerContextBar learner={learner} onViewProfile={onViewProfile} onChangeLearner={onChangeLearner}/>
    <div className="v2-chat-layout"><aside><Card><h3>▤ &nbsp; Lesson context</h3><small>Learner</small><p>{learner.code} · Age {learner.age}</p><small>Goal (draft)</small><p>{chat.draft.goalText}</p><div className="v2-ai-note">✦ AI will ask a few questions and gather the remaining details.</div></Card><Card><h3>▧ &nbsp; What will be generated</h3>{["Lesson Brief","Teaching Flow","Visual Cards","Help Card","Token Board","Data Sheet","Summary Template"].map((item)=><p key={item}>▧ &nbsp; {item}</p>)}</Card></aside>
      <Card className="v2-chat-panel"><div className="v2-chat-header"><h3>✦ &nbsp; Lesson Copilot</h3><button onClick={()=>void clearChat()} disabled={chat.messages.length===0}>Clear chat</button></div><div className="v2-message-list">{chat.messages.map((message)=><div key={message.id} className={`v2-message v2-message--${message.role}`}><span>{message.role==="assistant"?"✦":"👩🏻"}</span><div><p>{message.content}</p><small>{message.createdAt}</small></div></div>)}</div>
        <div className="v2-question-list">{chat.questions.map((question)=><AIQuestionBlock key={question.id} question={question} onAnswer={(ids,custom)=>void answer(question.id,ids,custom)}/>)}</div>
        <div className="v2-draft"><strong>✦ Current lesson plan <em>(AI draft)</em></strong><div><span><small>Goal</small>{chat.draft.goalText}</span><span><small>Theme</small>{chat.draft.theme}</span><span><small>Materials</small><span className="v2-draft-tags">{chat.draft.selectedMaterials.map((item)=><Tag key={item}>{item}</Tag>)}</span></span><span><small>Duration</small>{chat.draft.duration}</span></div></div>
        <div className="v2-chat-actions"><div className="v2-composer"><input value={composer} onChange={(event)=>setComposer(event.target.value)} onKeyDown={(event)=>{if(event.key==="Enter")void sendMessage();}} placeholder="Add a note for the lesson copilot…"/><Button variant="secondary" disabled={!composer.trim()} onClick={()=>void sendMessage()}>Send</Button></div><Button disabled={!chat.canGenerate||generating} onClick={()=>void generate()}>{generating?"Generating…":"Generate Lesson Package"}</Button></div>
      </Card></div></>;
}
