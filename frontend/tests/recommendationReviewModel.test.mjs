import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  recommendationDisplayText,
  recommendationReviewInput,
  recommendationStatusLabel,
} from "../src/v2/recommendationReviewModel.ts";

function recommendation(overrides = {}) {
  return {
    id: "recommendation-1",
    learnerId: "n482",
    goalId: "goal-break",
    goalRevision: 1,
    type: "collect_more_data",
    title: "Collect more observations",
    recommendation: "More observations may be useful before changing the plan.",
    evidence: [
      {
        sessionId: "session-1",
        description: "1 of 5 opportunities was independent.",
        metricPath: "responses.independentSuccessful/opportunities.valid",
        observedValue: 20,
        contextId: null,
        contextLabel: null,
      },
    ],
    confidence: "high",
    confidenceReason: "One completed session is available.",
    teacherReviewRequired: true,
    affectedLessonSpecPaths: [],
    affectedMaterialIds: [],
    affectedMaterialTypes: [],
    status: "pending",
    teacherEditedText: null,
    ruleId: "collect-v1",
    evidenceFingerprint: "fingerprint",
    createdAt: "2026-08-04T09:00:00Z",
    reviewedAt: null,
    reviewHistory: [],
    version: 3,
    ...overrides,
  };
}

test("accept and reject payloads review only the selected recommendation version", () => {
  const current = recommendation();
  assert.deepEqual(recommendationReviewInput(current, "accepted"), {
    action: "accepted",
    expectedVersion: 3,
  });
  assert.deepEqual(recommendationReviewInput(current, "rejected"), {
    action: "rejected",
    expectedVersion: 3,
  });
});

test("teacher-edited text is preserved verbatim", () => {
  const current = recommendation();
  const exact = "  Keep this exact wording.\nSecond line.  ";
  assert.deepEqual(recommendationReviewInput(current, "edited", exact), {
    action: "edited",
    expectedVersion: 3,
    teacherEditedText: exact,
  });
  assert.throws(
    () => recommendationReviewInput(current, "edited", "   "),
    /Enter the teacher-edited recommendation/,
  );
  assert.equal(
    recommendationDisplayText(
      recommendation({ status: "edited", teacherEditedText: exact }),
    ),
    exact,
  );
});

test("rejected status states that it is excluded from future planning", () => {
  assert.match(
    recommendationStatusLabel(recommendation({ status: "rejected" })),
    /excluded from future planning inputs/,
  );
});

test("review UI exposes evidence and one-at-a-time accept edit reject controls", () => {
  const source = readFileSync(
    new URL(
      "../src/v2/components/NextSessionRecommendationsPanel.tsx",
      import.meta.url,
    ),
    "utf8",
  );
  assert.match(source, /Recommendation \{index \+ 1\} of \{items.length\}/);
  assert.match(source, /Accept this recommendation/);
  assert.match(source, /Edit wording/);
  assert.match(source, /Reject/);
  assert.match(source, /View cited evidence/);
  assert.doesNotMatch(
    source,
    /regenerateLessonPackage|generateLessonPackageFromDraft/,
  );
});
