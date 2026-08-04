import test from "node:test";
import assert from "node:assert/strict";
import { applyTrialOutcome,buildSessionCompletionInput,createSessionTrials } from "../src/v2/sessionOutcomeModel.ts";

const template={sessionId:"session-n482",learnerId:"n482",lessonPackageId:"package-n482",lessonPackageRevision:2,lessonSpecId:"spec-n482",goalId:"spec-n482:goal",goalRevision:2,operationalizedGoal:'Requests "Break, please" using speech or AAC',plannedOpportunities:5,contexts:[{id:"c1",label:"Map to table",setting:"classroom"},{id:"c2",label:"Art to cleanup",setting:"classroom"},{id:"c3",label:"Choice to reading",setting:"classroom"}],materialIds:["break-card","data-sheet"],materialLabels:{"break-card":"Break Card","data-sheet":"Data Sheet"},dataSheetColumns:["Opportunity","Context","Outcome"]};

test("session draft initializes planned opportunity slots without invented observations",()=>{
  const trials=createSessionTrials(template);
  assert.equal(trials.length,5);
  assert.ok(trials.every((trial)=>trial.contextId===null));
  assert.ok(trials.every((trial)=>trial.outcome===null&&trial.responseMode===null&&trial.promptLevel===null));
});

test("outcome selection does not invent response mode or prompt level",()=>{
  const trial=createSessionTrials(template)[0];
  const prompted=applyTrialOutcome(trial,"prompted_success");
  assert.equal(prompted.valid,true);
  assert.equal(prompted.responseMode,null);
  assert.equal(prompted.promptLevel,null);
  const cancelled=applyTrialOutcome(prompted,"cancelled");
  assert.equal(cancelled.valid,false);
  assert.equal(cancelled.responseMode,null);
  assert.equal(cancelled.breakDelivered,null);
});

test("completion payload sends raw trials and revision locks without client totals",()=>{
  const trials=createSessionTrials(template).map((trial,index)=>({...trial,contextId:"c1",contextLabel:"Map to table",valid:true,outcome:"independent_success",responseMode:"speech",promptLevel:"independent",breakRequested:false,breakDelivered:false}));
  const payload=buildSessionCompletionInput(template,"2026-08-03T09:00:00Z",trials,"Observed session",3,2);
  assert.equal(payload.expectedGoalId,"spec-n482:goal");
  assert.equal(payload.trials.length,5);
  assert.equal(payload.observations.engagementLevel,3);
  assert.equal("responses" in payload,false);
  assert.equal("opportunities" in payload,false);
});
