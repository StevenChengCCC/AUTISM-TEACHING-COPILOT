import { useState } from "react";
import type { AIQuestion } from "../types";
import { OptionChip } from "./OptionChip";
import { Tag } from "./Tag";

export function AIQuestionBlock({ question,onAnswer }:{ question:AIQuestion;onAnswer:(ids:string[],customAnswer?:string)=>void }) {
  const [showCustom,setShowCustom]=useState(Boolean(question.customAnswer)||question.inputType==="free_text");
  const toggle=(id:string)=>{
    const selected=question.selectedOptionIds.includes(id);
    const withoutCustom=question.selectedOptionIds.filter((item)=>!item.startsWith("custom-"));
    const next=question.inputType==="single_select"?(selected?[]:[id]):selected?withoutCustom.filter((item)=>item!==id):[...withoutCustom,id];
    onAnswer(next,id.startsWith("custom-")||question.inputType==="single_select"?"":question.customAnswer);
  };
  return <div className="v2-question"><div className="v2-bot">✦</div><div className="v2-question-body">
    <div className="v2-question-title"><strong>{question.prompt}</strong></div>
    {question.inputType!=="free_text"&&<div className="v2-option-list">{question.options.map((option)=><OptionChip key={option.id} option={option} selected={question.selectedOptionIds.includes(option.id)} onToggle={()=>toggle(option.id)}/>)}{question.allowCustomAnswer&&<button className={showCustom?"is-custom":""} onClick={()=>setShowCustom(true)}>＋ Add custom answer</button>}</div>}
    {(showCustom||question.inputType==="free_text")&&<div className="v2-custom-answer"><input value={question.customAnswer} onChange={(event)=>onAnswer(question.selectedOptionIds.filter((id)=>!id.startsWith("custom-")),event.target.value)} placeholder="Type a custom answer"/>{question.customAnswer&&<Tag tone="purple">Teacher custom</Tag>}</div>}
  </div></div>;
}
