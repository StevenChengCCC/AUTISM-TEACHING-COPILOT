import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const panel = readFileSync(
  new URL(
    "../src/v2/components/NextSessionImpactPlanPanel.tsx",
    import.meta.url,
  ),
  "utf8",
);
const reviewPage = readFileSync(
  new URL("../src/v2/pages/ReviewPrintableContentPage.tsx", import.meta.url),
  "utf8",
);
const api = readFileSync(
  new URL("../src/v2/api/lessonKitApi.ts", import.meta.url),
  "utf8",
);

test("impact preview exposes every required category and preserves recommendation review", () => {
  for (const label of [
    "Reuse unchanged",
    "Revise",
    "New",
    "Remove",
    "Blocking",
  ]) {
    assert.match(panel, new RegExp(`title=\\"${label}\\"`));
  }
  assert.match(panel, /Return to recommendation review/);
  assert.match(panel, /accepted or teacher-edited recommendations/);
  assert.match(panel, /goalSeriesBoundary/);
});

test("teacher overrides are explicit and unsafe keep-existing decisions stay server-gated", () => {
  assert.match(panel, /force_regenerate/);
  assert.match(panel, /keep_existing/);
  assert.match(panel, /reject_new/);
  assert.match(panel, /item\.safeToKeepExisting/);
  assert.match(panel, /blockingIssues\.length > 0/);
});

test("review UI offers material, scenario, image, and semantic-field scope", () => {
  assert.match(reviewPage, /Regenerate this material only/);
  assert.match(reviewPage, /Regenerate one scenario only/);
  assert.match(reviewPage, /Regenerate this image/);
  assert.match(reviewPage, /Edit semantic material fields/);
  assert.match(api, /regenerateNextSessionMaterial/);
  assert.match(api, /regenerateNextSessionScenario/);
});

test("impact flow has no whole-package regeneration shortcut", () => {
  assert.doesNotMatch(
    panel,
    /regenerateLessonPackage|regeneratePackage|generateLessonPackageFromDraft/,
  );
  assert.match(panel, /createNextSessionPackage/);
});
