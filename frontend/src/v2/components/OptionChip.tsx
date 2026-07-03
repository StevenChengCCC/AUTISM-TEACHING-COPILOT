import { Tag } from "./Tag";
import type { AIQuestionOption } from "../types";

export function OptionChip({ option,selected,onToggle }:{ option:AIQuestionOption;selected:boolean;onToggle:()=>void }) {
  return <button className={selected?"is-selected":""} aria-pressed={selected} onClick={onToggle}>
    <span>{option.icon}</span><span>{option.label}</span>
    {option.recommended&&<Tag tone="green">Recommended</Tag>}
    {option.source==="teacher_custom"&&<Tag tone="purple">Your option</Tag>}
    {selected&&<b>✓</b>}
  </button>;
}
