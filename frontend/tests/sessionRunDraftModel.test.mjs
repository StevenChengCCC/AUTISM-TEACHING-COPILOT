import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { applyDraftOutcome,applyRecorderResult,autosaveLabel,codingDefinitions,draftPatch,incompleteTrialDetails,materialCooccurrenceNotice,rawTrialCounts,resultPathForOutcome,trialRequirementReasons } from "../src/v2/sessionRunDraftModel.ts";
import { formatLocalDateTime } from "../src/v2/dateTime.ts";

const trial={trialId:"trial-1",opportunityNumber:1,contextId:"context-1",contextLabel:"Transit to table",valid:null,outcome:null,responseMode:null,promptLevel:null,latencySeconds:null,breakRequested:null,breakDelivered:null,returnedAfterBreak:null,materialIdsUsed:[],note:""};
const draft={id:"draft-1",sessionId:"session-1",snapshotId:"use-1",status:"in_progress",trials:[trial],generalization:{status:null,people:[],settings:[],materials:[]},helpfulMaterialIds:[],unhelpfulMaterialIds:[],observations:{engagementLevel:null,regulationLevel:null,teacherNotes:"",rawCountsConfirmed:false},activeTrialNumber:1,lastSavedAt:"2026-08-04T09:00:00Z",version:3};

test("autosave patch preserves partial values and expected version",()=>{
  const payload=draftPatch(draft,"retry-key");
  assert.equal(payload.expectedVersion,3);
  assert.equal(payload.idempotencyKey,"retry-key");
  assert.equal(payload.activeTrialNumber,1);
  assert.equal(payload.trials[0].outcome,null);
});

test("draft outcome selection never invents speech AAC or prompt data",()=>{
  const changed=applyDraftOutcome(draft.trials[0],"prompted_success");
  assert.equal(changed.responseMode,null);
  assert.equal(changed.promptLevel,null);
  assert.deepEqual(incompleteTrialDetails({...draft,trials:[changed]},["speech","AAC"]),[{opportunityNumber:1,reasons:["choose the observed response mode","choose the prompt used"]}]);
});

test("five result paths reveal only their progressive required evidence",()=>{
  const independent=applyRecorderResult(trial,"independent",["speech","AAC"]);
  assert.equal(independent.promptLevel,null);
  assert.equal(independent.responseMode,null);
  assert.deepEqual(trialRequirementReasons(independent,["speech","AAC"]),["choose the observed response mode"]);

  const prompted=applyRecorderResult(trial,"prompted",["speech","AAC"]);
  assert.deepEqual(trialRequirementReasons(prompted,["speech","AAC"]),["choose the observed response mode","choose the prompt used"]);

  const notObserved=applyRecorderResult(trial,"not_observed",["speech","AAC"]);
  assert.equal(notObserved.outcome,"not_observed_unsuccessful");
  assert.deepEqual(trialRequirementReasons(notObserved,["speech","AAC"]),[]);

  const breakHonored=applyRecorderResult(trial,"break_honored",["speech","AAC"]);
  assert.equal(breakHonored.breakDelivered,true);
  assert.deepEqual(trialRequirementReasons(breakHonored,["speech","AAC"]),["confirm whether a break or stop was requested","record return status"]);

  const invalid=applyRecorderResult(trial,"invalid",["speech","AAC"]);
  assert.equal(invalid.valid,false);
  assert.deepEqual(trialRequirementReasons(invalid,["speech","AAC"]),["add a concise validity reason"]);
  assert.equal(resultPathForOutcome(invalid.outcome),"invalid");
});

test("raw counts keep invalid trials separate and material language is non-causal",()=>{
  const valid=applyRecorderResult(trial,"independent",["speech"]);
  const invalid={...applyRecorderResult({...trial,trialId:"trial-2",opportunityNumber:2},"invalid"),note:"Interrupted transition"};
  assert.deepEqual(rawTrialCounts({...draft,trials:[valid,invalid]}),{valid:1,invalid:1,recorded:2,remaining:0});
  assert.match(materialCooccurrenceNotice,/do not show that a material caused/);
});

test("digital coding key projects frozen printable definitions",()=>{
  const values=codingDefinitions({independenceDefinition:"No prompt after the cue",promptLevelDefinitions:["Visual: point once"]});
  assert.deepEqual(values,["Independent: No prompt after the cue","Prompt: Visual: point once"]);
});

test("autosave status communicates saving failure and conflict",()=>{
  assert.equal(autosaveLabel("saving"),"Saving…");
  assert.match(autosaveLabel("failed"),/local input is preserved/);
  assert.match(autosaveLabel("conflict"),/Conflict/);
});

test("session UI uses start continue reload and debounced durable draft APIs",()=>{
  const sessions=fs.readFileSync(new URL("../src/v2/pages/SessionsPage.tsx",import.meta.url),"utf8");
  const form=fs.readFileSync(new URL("../src/v2/components/SessionCompletionForm.tsx",import.meta.url),"utf8");
  assert.match(sessions,/Start Session/);
  assert.match(sessions,/Continue Recording/);
  assert.match(form,/getSessionRun/);
  assert.match(form,/patchSessionRunDraft/);
  assert.match(form,/setTimeout\(\(\)=>\{void save\(\);\},450\)/);
  assert.match(form,/saveInFlightRef/);
  assert.match(form,/const rebased=\{\.\.\.latest,version:value\.draft\.version/);
  assert.match(form,/Retry local changes/);
  assert.doesNotMatch(form,/Frozen revisions/);
  assert.doesNotMatch(form,/manifest v/);
  assert.match(form,/formatLocalDateTime\(run\.snapshot\.startedAt\)/);
  assert.match(form,/advanceLockRef/);
  assert.match(form,/Context remembered/);
  assert.match(form,/Generalization status/);
  assert.match(form,/rawCountsConfirmed/);
  assert.match(form,/Needs change before reuse/);
  assert.match(form,/Next Trial/);
  assert.match(form,/Undo last change/);
  assert.match(form,/Coding definitions used in print and digital recording/);
  assert.match(sessions,/atc-active-session-run/);
  const mock=fs.readFileSync(new URL("../src/v2/mockApi.ts",import.meta.url),"utf8");
  assert.match(mock,/generalization: \{ status: null/);
});

test("teacher-facing timestamps use a concise local timezone format",()=>{
  const formatted=formatLocalDateTime("2026-07-27T05:09:54.826582+00:00");
  assert.doesNotMatch(formatted,/T05:09:54/);
  assert.doesNotMatch(formatted,/826582/);
  assert.match(formatted,/2026/);
  assert.equal(formatLocalDateTime("Just now"),"Just now");
});

test("recorder CSS provides visible focus, touch targets, and single-column phone flow",()=>{
  const css=fs.readFileSync(new URL("../src/v2/styles.css",import.meta.url),"utf8");
  assert.match(css,/min-height:48px/);
  assert.match(css,/:focus-visible/);
  assert.match(css,/\.v2-classroom-recorder\{max-height:none;overflow:visible/);
  assert.match(css,/@media\(max-width:620px\)/);
});

test("recorder actions stay native keyboard controls and closeout has no inferred status",()=>{
  const form=fs.readFileSync(new URL("../src/v2/components/SessionCompletionForm.tsx",import.meta.url),"utf8");
  assert.match(form,/<button type="button" key=\{path\}/);
  assert.match(form,/aria-pressed=\{currentPath===path\}/);
  assert.doesNotMatch(form,/onMouseDown=/);
  assert.match(form,/draft\.generalization\.status===value/);
  assert.doesNotMatch(form,/generalization:\{status:"not_attempted"/);
});
