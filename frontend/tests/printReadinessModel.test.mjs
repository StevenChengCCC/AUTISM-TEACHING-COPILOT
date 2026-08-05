import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  blockingReadinessItems,
  nextPendingMaterialId,
  nextReadinessItem,
  readinessActionLabel,
} from "../src/v2/printReadinessModel.ts";

const blockers = [
  {
    blockerId: "semantic:m-1",
    category: "semantic_validation_failure",
    severity: "blocking",
    materialId: "m-1",
    explanation: "Semantic validation failed.",
    recoveryAction: "repair_material",
    recoveryRoute: "reviewPrintableContent",
    retryPossible: false,
  },
  {
    blockerId: "approval:m-2",
    category: "material_revision_not_approved",
    severity: "blocking",
    materialId: "m-2",
    explanation: "Approval required.",
    recoveryAction: "approve_material",
    recoveryRoute: "reviewPrintableContent",
    retryPossible: false,
  },
  {
    blockerId: "fallback:v-3",
    category: "failed_optional_visual_with_fallback",
    severity: "warning",
    materialId: "m-3",
    visualId: "v-3",
    explanation: "Fallback is visible.",
    recoveryAction: "review_fallback",
    recoveryRoute: "reviewPrintableContent",
    retryPossible: true,
  },
];

const readiness = {
  ready: false,
  blockers,
  recommendedNextAction: blockers[0],
};

test("canonical readiness drives next recovery without approving another item", () => {
  assert.deepEqual(blockingReadinessItems(readiness).map((item) => item.blockerId), [
    "semantic:m-1",
    "approval:m-2",
  ]);
  assert.equal(nextReadinessItem(readiness).materialId, "m-1");
  assert.equal(nextPendingMaterialId(readiness, "m-1"), "m-2");
  assert.equal(readinessActionLabel(blockers[1]), "Approve material");
});

test("both print screens consume the backend contract and disable silent download", () => {
  const readyPage = readFileSync(
    new URL("../src/v2/pages/LessonPackageReadyPage.tsx", import.meta.url),
    "utf8",
  );
  const reviewPage = readFileSync(
    new URL("../src/v2/pages/ReviewPrintableContentPage.tsx", import.meta.url),
    "utf8",
  );
  assert.match(readyPage, /getPackagePrintReadiness/);
  assert.match(readyPage, /const schedule=.*setTimeout/);
  assert.match(readyPage, /const updated=await lessonKitApi\.getLessonPackage\(lessonPackage\.id\)/);
  assert.match(readyPage, /Printing is paused/);
  assert.doesNotMatch(readyPage, /did not pass the instructional safety gate/);
  assert.match(reviewPage, /getPackagePrintReadiness/);
  assert.match(reviewPage, /disabled=\{actionBusy \|\| !printReadiness\?\.ready/);
  assert.match(reviewPage, /Approve and open next pending item/);
  assert.doesNotMatch(reviewPage, /const generating = visualMaterials\.find/);
  assert.match(readyPage, /revalidateLessonPackage/);
  assert.match(reviewPage, /revalidateLessonPackage/);
  assert.doesNotMatch(reviewPage, /decisionIds\.map/);
  assert.doesNotMatch(reviewPage, /Profile revision/);

  const panel = readFileSync(
    new URL("../src/v2/components/PrintReadinessPanel.tsx", import.meta.url),
    "utf8",
  );
  assert.doesNotMatch(panel, /Fix next issue ·/);
  assert.doesNotMatch(panel, /Package revision/);
});
