import type {AIQuestion,LessonDesignDraft} from "./types";

export function nextOptionSelection(question:AIQuestion,id:string):string[]{
  const selected=question.selectedOptionIds.includes(id);
  const withoutCustom=question.selectedOptionIds.filter((item)=>!item.startsWith("custom-"));
  const onlyOne=question.inputType==="single_select"||question.maxSelections===1;
  if(onlyOne)return selected?[]:[id];
  return selected?withoutCustom.filter((item)=>item!==id):[...withoutCustom,id];
}

export function shouldShowCustomAnswer(question:AIQuestion):boolean{
  return Boolean(question.customAnswer)||question.inputType==="free_text";
}

export function isDecisionAnswered(question:AIQuestion):boolean{
  return Boolean(question.selectedOptionIds.length||question.customAnswer.trim()||!question.required);
}

export function staleProfileAction(draft:LessonDesignDraft):"refresh"|"none"{
  return draft.profileStale?"refresh":"none";
}
