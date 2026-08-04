import assert from "node:assert/strict";
import test from "node:test";
import {factorStatusLabel,profileSummaryView,visibleFactorsForSection} from "../src/v2/profileViewModel.ts";

const factor=(id,category,value,status="confirmed_current")=>({id,category,label:id,value,status,confidence:.9,sourceEvidence:"synthetic",instructionalImplication:value,generationConstraints:[],teacherReviewed:false});
const factors=[
  factor("communication","communication","Uses speech and AAC"),
  factor("current-transit","current_interest","Subway maps"),
  factor("historical-dinosaurs","historical_interest","Dinosaurs","historical"),
  factor("food","reinforcement","Food rewards","not_approved"),
  factor("hand-over-hand","prohibited_item","Hand-over-hand prompting is prohibited"),
  factor("spanish","unresolved_assumption","Paired Spanish labels","unconfirmed"),
];
const learner={communicationMode:"",supportNeeds:[],interests:[],attentionProfile:"",notes:"",normalizedProfile:{summary:{communication:"Uses speech and AAC",supports:["First–Then"],currentInterests:["Subway maps"],learningFormat:"Brief visual blocks",keyTeachingNotes:[]},factors}};

test("confirmed structured summaries do not render confirmation fallbacks",()=>{
  const view=profileSummaryView(learner);
  assert.equal(view.communication,"Uses speech and AAC");
  assert.deepEqual(view.supports,["First–Then"]);
  assert.deepEqual(view.currentInterests,["Subway maps"]);
  assert.equal(factorStatusLabel(factors[0]),"Confirmed");
});

test("frontend grouping separates current, historical, excluded, and unresolved factors",()=>{
  assert.deepEqual(visibleFactorsForSection(factors,"Current interests",["current_interest"]).map(({id})=>id),["current-transit"]);
  assert.deepEqual(visibleFactorsForSection(factors,"Historical information",[]).map(({id})=>id),["historical-dinosaurs"]);
  assert.deepEqual(visibleFactorsForSection(factors,"Not approved or prohibited",[]).map(({id})=>id),["food","hand-over-hand"]);
  assert.deepEqual(visibleFactorsForSection(factors,"Needs teacher confirmation",[]).map(({id})=>id),["spanish"]);
});
