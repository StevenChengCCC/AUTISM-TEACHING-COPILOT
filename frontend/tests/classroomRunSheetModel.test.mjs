import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildClassroomRunSheet } from "../src/v2/classroomRunSheetModel.ts";

const packageFixture = {
  id: "package-1",
  learnerId: "private-learner-id",
  draftId: "draft-1",
  goal: "Request a break during transitions",
  duration: "25 minutes",
  theme: "Transit",
  lessonBrief: "Practice the current goal.",
  summaryTemplate: "Record outcomes.",
  successCriterion: "4 successful opportunities out of 5",
  responseModality: "speech, AAC",
  preparationChecklist: ["Place the Break Card within reach", "Check margins"],
  documentContent: {
    materialsNeeded: "Teacher-edited route board, Break Card, timer, and pencil",
    dataCollectionPlan: "Record response mode, prompt level, and latency.",
    learnerName: "Identifiable Name",
    rawRecordText: "PRIVATE RECORD TEXT",
  },
  materials: [
    {
      id: "material-1",
      packageId: "package-1",
      type: "break_card",
      title: "Break Card",
      status: "approved",
      content: {},
      printLayout: {},
      specification: {
        printPreparation: ["Check margins", "Print at actual size", "Print at actual size"],
      },
    },
    {
      id: "material-2",
      packageId: "package-1",
      type: "data_sheet",
      title: "Goal Data Sheet",
      status: "approved",
      content: {},
      printLayout: {},
      specification: { printPreparation: ["Prepare a pencil"] },
    },
  ],
  teachingFlow: [
    {
      id: "step-1",
      title: "Transition practice",
      description: "Practice the transition.",
      duration: "4 minutes",
      teacherAction: "Show the transition card.",
      learnerAction: "Transitions or requests a break.",
      teacherScript: "The next activity is ready.",
      expectedLearnerResponse: "Requests by speech or AAC.",
      waitTime: "5 seconds",
      promptAction: "Wait, point, then fade.",
      reinforcementAction: "Honor the request.",
      errorCorrectionAction: "Respond neutrally and offer another opportunity.",
      dataToRecord: ["response mode", "prompt level"],
      transitionCue: "Show the next card.",
      breakOption: "Provide the planned break.",
    },
  ],
};

test("run-sheet model preserves edits and rich teaching-step fields", () => {
  const sheet = buildClassroomRunSheet(packageFixture, "N-482");
  assert.equal(sheet.learnerCode, "N-482");
  assert.deepEqual(sheet.communicationModes, ["speech", "AAC"]);
  assert.equal(sheet.materialsSource, "teacher_edit");
  assert.deepEqual(sheet.materialsNeeded, [
    "Teacher-edited route board, Break Card, timer, and pencil",
  ]);
  assert.deepEqual(sheet.beforeClassChecklist, [
    "Place the Break Card within reach",
    "Print at actual size",
    "Prepare a pencil",
  ]);
  assert.equal(sheet.steps[0].teacherScript, "The next activity is ready.");
  assert.equal(sheet.steps[0].waitTime, "5 seconds");
  assert.deepEqual(sheet.steps[0].dataToRecord, ["response mode", "prompt level"]);
  assert.match(sheet.dataReminder[0], /response mode/);
  assert.match(sheet.closeout.join(" "), /invalid opportunities/);
  assert.match(sheet.teacherJudgmentNote, /Teacher judgment overrides this guide/);
  assert.doesNotMatch(JSON.stringify(sheet), /Identifiable Name|PRIVATE RECORD TEXT|private-learner-id/);
});

test("materials fallback uses only included current package titles", () => {
  const withoutOverride = {
    ...packageFixture,
    documentContent: {},
  };
  const sheet = buildClassroomRunSheet(withoutOverride, "N-482");
  assert.equal(sheet.materialsSource, "included_materials");
  assert.deepEqual(sheet.materialsNeeded, ["Break Card", "Goal Data Sheet"]);
});

test("teacher plan contains the compact run-sheet preview without a new route", () => {
  const page = readFileSync(
    new URL("../src/v2/pages/LessonPackageReadyPage.tsx", import.meta.url),
    "utf8",
  );
  const preview = readFileSync(
    new URL("../src/v2/components/ClassroomRunSheetPreview.tsx", import.meta.url),
    "utf8",
  );
  assert.match(page, /buildClassroomRunSheet/);
  assert.match(page, /ClassroomRunSheetPreview/);
  assert.match(page, /Classroom run sheet, lesson brief, and session notes/);
  assert.match(preview, /INCLUDED IN THE COMPLETE PDF/);
  assert.match(preview, /Two-minute closeout/);
  assert.match(preview, /sheet\.teacherJudgmentNote/);
});
