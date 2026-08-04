import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const questionSource=readFileSync(new URL("../src/v2/components/AIQuestionBlock.tsx",import.meta.url),"utf8");
const optionSource=readFileSync(new URL("../src/v2/components/OptionChip.tsx",import.meta.url),"utf8");
const pageSource=readFileSync(new URL("../src/v2/pages/PlanWithAIChatPage.tsx",import.meta.url),"utf8");
const styles=readFileSync(new URL("../src/v2/styles.css",import.meta.url),"utf8");

test("lesson suggestions use classroom-situation language and styled selection cards",()=>{
  assert.match(questionSource,/Which classroom situations should this lesson cover\?/);
  assert.doesNotMatch(questionSource,/Where will the learner practice\?/);
  assert.match(optionSource,/v2-option-chip__indicator/);
  assert.match(styles,/\.v2-option-chip\s*\{/);
  assert.doesNotMatch(styles,/\.v2-option-list>button\s*\{/);
});

test("package review replaces the selection board and keeps optional content compact",()=>{
  assert.match(pageSource,/hasQuestions&&!showPlan&&<div className="v2-suggestion-board"/);
  assert.match(pageSource,/!showPlan&&<div className=\{`v2-draft/);
  assert.match(pageSource,/plan\.requiredCompanions\.length>0&&<section/);
  assert.match(pageSource,/<details className="v2-content-plan__disclosure">/);
  assert.match(pageSource,/Edit lesson choices/);
});
