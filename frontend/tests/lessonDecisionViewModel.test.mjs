import assert from "node:assert/strict";
import test from "node:test";
import {isDecisionAnswered,nextOptionSelection,shouldShowCustomAnswer,staleProfileAction} from "../src/v2/lessonDecisionViewModel.ts";

const question=(updates={})=>({id:"goal",prompt:"Goal",helperText:"",field:"goalText",inputType:"hybrid",options:[],selectedOptionIds:[],allowCustomAnswer:true,customAnswer:"",required:true,...updates});

test("selection preserves multi-select choices and single-select edits override prior wording",()=>{
  assert.deepEqual(nextOptionSelection(question({selectedOptionIds:["a"],inputType:"multi_select"}),"b"),["a","b"]);
  assert.deepEqual(nextOptionSelection(question({selectedOptionIds:["ai-goal"],maxSelections:1}),"teacher-goal"),["teacher-goal"]);
});

test("resumed custom answers remain visible and count as answered",()=>{
  const resumed=question({customAnswer:"Teacher-authored transition",selectedOptionIds:["custom-goal"]});
  assert.equal(shouldShowCustomAnswer(resumed),true);
  assert.equal(isDecisionAnswered(resumed),true);
});

test("stale profile state directs the existing page to refresh without discarding decisions",()=>{
  assert.equal(staleProfileAction({profileStale:true}),"refresh");
  assert.equal(staleProfileAction({profileStale:false}),"none");
});
