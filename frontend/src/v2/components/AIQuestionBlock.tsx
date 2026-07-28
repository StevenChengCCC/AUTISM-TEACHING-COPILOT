import { useEffect,useState } from "react";
import type { AIQuestion } from "../types";
import { OptionChip } from "./OptionChip";
import { Tag } from "./Tag";

export function AIQuestionBlock({ question,onAnswer,busy=false }:{ question:AIQuestion;onAnswer:(ids:string[],customAnswer?:string)=>void|Promise<void>;busy?:boolean }) {
  const [showCustom,setShowCustom]=useState(Boolean(question.customAnswer)||question.inputType==="free_text");
  const [customDraft,setCustomDraft]=useState(question.customAnswer);
  useEffect(()=>{setCustomDraft(question.customAnswer);},[question.id,question.customAnswer]);
  const toggle=(id:string)=>{
    if(busy)return;
    const selected=question.selectedOptionIds.includes(id);
    const withoutCustom=question.selectedOptionIds.filter((item)=>!item.startsWith("custom-"));
    const onlyOne=question.inputType==="single_select"||question.maxSelections===1;
    const next=onlyOne?(selected?[]:[id]):selected?withoutCustom.filter((item)=>item!==id):[...withoutCustom,id];
    void onAnswer(next,onlyOne?"":question.customAnswer);
  };
  return <div className="v2-question"><div className="v2-bot">✦</div><div className="v2-question-body">
    <div className="v2-question-title"><strong>{question.prompt}</strong></div>
    {question.helperText&&<p className="v2-question-helper">{question.helperText}</p>}
    {question.inputType!=="free_text"&&<div className="v2-option-list">{question.options.map((option)=><OptionChip key={option.id} option={option} selected={question.selectedOptionIds.includes(option.id)} disabled={busy} onToggle={()=>toggle(option.id)}/>)}{question.allowCustomAnswer&&<button type="button" disabled={busy} className={showCustom?"is-custom":""} onClick={()=>setShowCustom(true)}>＋ Write my own</button>}</div>}
    {(showCustom||question.inputType==="free_text")&&<div className="v2-custom-answer"><input value={customDraft} disabled={busy} onChange={(event)=>setCustomDraft(event.target.value)} onKeyDown={(event)=>{if(event.key==="Enter"&&customDraft.trim()){event.preventDefault();void onAnswer(question.maxSelections===1?[]:question.selectedOptionIds.filter((id)=>!id.startsWith("custom-")),customDraft.trim());}}} placeholder="Write a short answer"/><button type="button" disabled={busy||!customDraft.trim()||customDraft.trim()===question.customAnswer.trim()} onClick={()=>void onAnswer(question.maxSelections===1?[]:question.selectedOptionIds.filter((id)=>!id.startsWith("custom-")),customDraft.trim())}>{busy?"Saving…":"Use answer"}</button>{question.customAnswer&&<Tag tone="purple">Your answer</Tag>}</div>}
  </div></div>;
}
