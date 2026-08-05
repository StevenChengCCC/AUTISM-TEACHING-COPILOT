import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const questionSource=readFileSync(new URL("../src/v2/components/AIQuestionBlock.tsx",import.meta.url),"utf8");
const optionSource=readFileSync(new URL("../src/v2/components/OptionChip.tsx",import.meta.url),"utf8");
const pageSource=readFileSync(new URL("../src/v2/pages/PlanWithAIChatPage.tsx",import.meta.url),"utf8");
const backendClientSource=readFileSync(new URL("../src/v2/api/backendClient.ts",import.meta.url),"utf8");
const profilePageSource=readFileSync(new URL("../src/v2/pages/ReviewLearnerPage.tsx",import.meta.url),"utf8");
const profileStyles=readFileSync(new URL("../src/v2/pages/ReviewLearnerPage.css",import.meta.url),"utf8");
const uploadPageSource=readFileSync(new URL("../src/v2/pages/UploadRecordsPage.tsx",import.meta.url),"utf8");
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
test("package-plan failures show the exact issue and retry package planning",()=>{
  assert.match(backendClientSource,/public issues\?: string\[\]/);
  assert.match(backendClientSource,/payload\.issues/);
  assert.match(pageSource,/setRetryAction\("content_plan"\)/);
  assert.match(pageSource,/retryAction==="content_plan"\?previewContentPlan\(\):sendMessage\(\)/);
});

test("learner profile keeps detailed factors available without showing every card",()=>{
  assert.match(profilePageSource,/<details className="v2-teaching-details">/);
  assert.match(profilePageSource,/Show teaching details/);
  assert.match(profileStyles,/\.v2-teaching-details\s*>\s*summary/);
  assert.doesNotMatch(profilePageSource,/<details className="v2-teaching-details" open/);
});

test("learner profile analysis shows durable progress and a safe retry",()=>{
  assert.match(profilePageSource,/Preparing learner summary/);
  assert.match(profilePageSource,/Your reviewed record is safely saved/);
  assert.match(profilePageSource,/Your uploaded record is safe/);
  assert.match(profilePageSource,/Try profile analysis again/);
  assert.match(profilePageSource,/Record ready for AI analysis/);
  assert.match(profilePageSource,/Prepare learner summary/);
  assert.match(profileStyles,/\.v2-profile-loading__spinner/);
  assert.match(uploadPageSource,/analyzeLearnerProfile\(learnerId\)/);
  assert.match(uploadPageSource,/AI is preparing the summary/);
  assert.match(uploadPageSource,/Your record is safely saved/);
});

test("lesson planning layout wraps long tags and buttons inside their containers",()=>{
  assert.match(styles,/\.v2-learner-context\s*\{[^}]*flex-wrap:wrap/);
  assert.match(styles,/\.v2-button\s*\{[^}]*overflow-wrap:anywhere/);
  assert.match(styles,/\.v2-tag\s*\{[^}]*overflow-wrap:anywhere/);
  assert.match(styles,/grid-template-columns:340px minmax\(0,1fr\)/);
});
