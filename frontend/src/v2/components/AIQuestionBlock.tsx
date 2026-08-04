import { useEffect,useState } from "react";
import type { AIQuestion } from "../types";
import { OptionChip } from "./OptionChip";
import { Tag } from "./Tag";
import {nextOptionSelection,shouldShowCustomAnswer} from "../lessonDecisionViewModel";

export function AIQuestionBlock({ question,onAnswer,busy=false }:{ question:AIQuestion;onAnswer:(ids:string[],customAnswer?:string,saveForFuture?:boolean)=>void|Promise<void>;busy?:boolean }) {
  const [showCustom,setShowCustom]=useState(shouldShowCustomAnswer(question));
  const [customDraft,setCustomDraft]=useState(question.customAnswer);
  useEffect(()=>{setCustomDraft(question.customAnswer);},[question.id,question.customAnswer]);
  const toggle=(id:string)=>{
    if(busy)return;
    const onlyOne=question.inputType==="single_select"||question.maxSelections===1;
    const next=nextOptionSelection(question,id);
    void onAnswer(next,onlyOne?"":question.customAnswer);
  };
  const selectableIds=question.options.filter((option)=>option.source!=="teacher_custom").map((option)=>option.id);
  const canSelectAll=question.inputType==="multi_select"&&question.maxSelections==null&&selectableIds.length>1;
  const allSelected=canSelectAll&&selectableIds.every((id)=>question.selectedOptionIds.includes(id));
  return <div className="v2-question"><div className="v2-bot">✦</div><div className="v2-question-body">
    <div className="v2-question-title"><strong>{question.prompt}</strong></div>
    {question.helperText&&<p className="v2-question-helper">{question.helperText}</p>}
    {question.inputType!=="free_text"&&<div className="v2-option-list">{question.options.map((option)=><div key={option.id}><OptionChip option={option} selected={question.selectedOptionIds.includes(option.id)} disabled={busy} onToggle={()=>toggle(option.id)}/>{question.selectedOptionIds.includes(option.id)&&(option.reason||option.affects?.length||option.unsupportedReason)&&<small className={option.supported===false?"v2-option-warning":"v2-option-reason"}>{option.unsupportedReason||option.reason}{option.profileFactorIds?.length?" · Learner-profile informed":""}{option.affects?.length?` · Affects ${option.affects.join(", ")}`:""}{option.supported===false&&!option.savedForFuture&&<button type="button" disabled={busy} onClick={()=>void onAnswer(question.selectedOptionIds,option.value,true)}>Save as future request</button>}{option.savedForFuture&&" · Saved for future use; it will not be generated"}</small>}</div>)}{canSelectAll&&<button type="button" disabled={busy} className={allSelected?"is-custom":""} onClick={()=>void onAnswer(allSelected?[]:selectableIds,"")}>{allSelected?"Clear all":"✓ Select all"}</button>}{question.allowCustomAnswer&&<button type="button" disabled={busy} className={showCustom?"is-custom":""} onClick={()=>setShowCustom(true)}>＋ Write my own</button>}</div>}
    {(showCustom||question.inputType==="free_text")&&<div className="v2-custom-answer"><input value={customDraft} disabled={busy} onChange={(event)=>setCustomDraft(event.target.value)} onKeyDown={(event)=>{if(event.key==="Enter"&&customDraft.trim()){event.preventDefault();void onAnswer(question.maxSelections===1?[]:question.selectedOptionIds,customDraft.trim());}}} placeholder="Write a short answer"/><button type="button" disabled={busy||!customDraft.trim()||customDraft.trim()===question.customAnswer.trim()} onClick={()=>void onAnswer(question.maxSelections===1?[]:question.selectedOptionIds,customDraft.trim())}>{busy?"Saving…":"Use answer"}</button>{question.customAnswer&&<Tag tone="purple">Your answer</Tag>}</div>}
  </div></div>;
}
