import { Tag } from "./Tag";
import type { AIQuestionOption } from "../types";

export function OptionChip({ option,selected,onToggle,disabled=false }:{ option:AIQuestionOption;selected:boolean;onToggle:()=>void;disabled?:boolean }) {
  return <button type="button" disabled={disabled} className={`v2-option-chip ${selected?"is-selected":""}`} aria-pressed={selected} onClick={onToggle}>
    <span className="v2-option-chip__indicator" aria-hidden="true">{selected?"✓":""}</span>
    <span className="v2-option-chip__label">{option.label}</span>
    <span className="v2-option-chip__tags">{option.recommended&&<Tag tone="green">Recommended</Tag>}{option.source==="teacher_custom"&&<Tag tone="purple">Your option</Tag>}</span>
  </button>;
}
