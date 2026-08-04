import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { LEARNER_PAGE_SIZE, paginateLearners } from "../src/v2/learnerListModel.ts";

test("large learner collections remain bounded to a short page",()=>{
  const learners=Array.from({length:23},(_,index)=>({id:`learner-${index+1}`}));
  const first=paginateLearners(learners,1);
  const last=paginateLearners(learners,99);
  assert.equal(LEARNER_PAGE_SIZE,6);
  assert.equal(first.items.length,6);
  assert.equal(first.pageCount,4);
  assert.equal(last.page,4);
  assert.equal(last.items.length,5);
});

test("learner page loads records only for the selected profile",()=>{
  const page=fs.readFileSync(new URL("../src/v2/pages/StudentsPage.tsx",import.meta.url),"utf8");
  assert.doesNotMatch(page,/items\.map\(async \(item\).*getRecordsForLearner/s);
  assert.match(page,/getRecordsForLearner\(selectedId\)/);
  assert.match(page,/learnerPage\.items\.map/);
  assert.match(page,/Page \{learnerPage\.page\} of \{learnerPage\.pageCount\}/);
});
