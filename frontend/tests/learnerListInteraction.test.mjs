import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

test("learner list scrolls independently without pagination",()=>{
  const page=fs.readFileSync(new URL("../src/v2/pages/StudentsPage.tsx",import.meta.url),"utf8");
  const css=fs.readFileSync(new URL("../src/v2/styles.css",import.meta.url),"utf8");
  assert.doesNotMatch(page,/learnerPage|Previous|Page \{/);
  assert.match(page,/filtered\.map\(\(learner\)/);
  assert.match(css,/\.v2-student-list \{ max-height:/);
  assert.match(css,/overflow-y:auto/);
  assert.match(css,/overscroll-behavior:contain/);
});

test("single click selects and double click opens the learner",()=>{
  const page=fs.readFileSync(new URL("../src/v2/pages/StudentsPage.tsx",import.meta.url),"utf8");
  assert.match(page,/onClick=\{\(\) => setSelectedId\(learner\.id\)\}/);
  assert.match(page,/onDoubleClick=\{\(\) => onStartLesson\(learner\.id\)\}/);
  assert.match(page,/onClick=\{\(\) => onStartLesson\(selected\.id\)\}/);
});

test("new lesson learner chooser scrolls and supports both open paths",()=>{
  const page=fs.readFileSync(new URL("../src/v2/pages/StartNewLessonPage.tsx",import.meta.url),"utf8");
  const css=fs.readFileSync(new URL("../src/v2/styles.css",import.meta.url),"utf8");
  assert.match(page,/onClick=\{\(\)=>setSelectedId\(learner\.id\)\}/);
  assert.match(page,/onDoubleClick=\{\(\)=>onSelectExisting\(learner\.id\)\}/);
  assert.match(page,/onClick=\{\(\)=>onSelectExisting\(selectedId\)\}/);
  assert.match(css,/\.v2-learner-list \{[^}]*max-height:420px;[^}]*overflow-y:auto;[^}]*overscroll-behavior:contain;/s);
  assert.match(css,/\.v2-start-grid \{[^}]*align-items:start;/s);
});

test("records remain lazy-loaded for only the selected learner",()=>{
  const page=fs.readFileSync(new URL("../src/v2/pages/StudentsPage.tsx",import.meta.url),"utf8");
  assert.match(page,/getRecordsForLearner\(selectedId\)/);
  assert.doesNotMatch(page,/items\.map\(async \(item\).*getRecordsForLearner/s);
});
