import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  accessibleSeriesSummary,
  chartCoordinates,
  contextComparisonText,
  contextSummaryText,
  formatMetricValue,
  isPointActivationKey,
  limitedStateText,
  materialUsageText,
  metricLabels,
  pointAriaLabel,
} from "../src/v2/goalProgressChartModel.ts";

function point(index, independent) {
  return {
    sessionId: `session-${index}`,
    completedAt: `2026-08-${String(index).padStart(2, "0")}T09:25:00Z`,
    goalId: "break-goal",
    goalRevision: 1,
    metric: "independent_success_rate",
    value: (independent / 5) * 100,
    validOpportunityCount: 5,
    numeratorCount: independent,
    confidence: "normal",
    confidenceReason: null,
    lessonPackageId: "package-1",
    lessonPackageRevision: 1,
    contextsAttempted: ["Map to table", "Art to cleanup", "Choice to reading"],
    annotation: null,
    details: {
      operationalizedGoal: 'Requests "Break, please" using speech or AAC',
      independentSuccessfulCount: independent,
      promptedSuccessfulCount: 5 - independent,
      responseModeCounts: { speech: independent, AAC: 5 - independent },
      promptLevelCounts: { independent, visual: 5 - independent },
      averagePromptLevel: 1.2,
      averageLatencySeconds: 5,
      breakRequestCount: 1,
      breaksDeliveredCount: 1,
      returnedAfterBreakCount: 1,
      materialIdsUsed: ["break-card", "data-sheet"],
      teacherNotes: `Session ${index}`,
    },
  };
}
const series = {
  learnerId: "n482",
  goalId: "break-goal",
  goalRevision: 1,
  operationalizedGoal: 'Requests "Break, please" using speech or AAC',
  metric: "independent_success_rate",
  points: [point(1, 1), point(2, 2), point(3, 3), point(4, 4)],
  trend: "improving",
  trendEvidence: ["Repeated normal-confidence observations."],
  latestValue: 80,
  sessionCount: 4,
};

test("accessible text summary reports raw independent counts", () => {
  assert.equal(
    accessibleSeriesSummary(series),
    "Across 4 recorded sessions, independent responses were 1 of 5, 2 of 5, 3 of 5, and 4 of 5.",
  );
});

test("zero, one, and two observation language is explicit", () => {
  assert.equal(
    limitedStateText(0),
    "No completed sessions are available for this goal.",
  );
  assert.equal(
    limitedStateText(1),
    "One observation is available. More sessions are needed to show a trend.",
  );
  assert.equal(
    limitedStateText(2),
    "Two observations are available. This shows a comparison but not a stable trend.",
  );
});

test("N-482 points map to distinct 20, 40, 60, and 80 percent coordinates", () => {
  const coordinates = chartCoordinates(series);
  assert.deepEqual(
    coordinates.map((item) => item.point.value),
    [20, 40, 60, 80],
  );
  assert.ok(
    coordinates.every(
      (item, index) => index === 0 || item.y < coordinates[index - 1].y,
    ),
  );
});

test("metric selector labels one visualization transformation clearly", () => {
  assert.equal(
    metricLabels.prompt_independence_display_score,
    "Prompt independence display score",
  );
  assert.equal(formatMetricValue("average_response_latency", 5), "5 seconds");
  assert.equal(
    formatMetricValue("generalization_context_count", 3),
    "3 contexts",
  );
});

test("point accessibility includes detail accuracy and keyboard activation", () => {
  const label = pointAriaLabel(series.points[2], 2);
  assert.match(label, /Session 3/);
  assert.match(label, /60%/);
  assert.match(label, /3 independent responses of 5 valid opportunities/);
  assert.equal(isPointActivationKey("Enter"), true);
  assert.equal(isPointActivationKey(" "), true);
  assert.equal(isPointActivationKey("ArrowRight"), false);
});

test("context summaries and comparisons use cautious descriptive language", () => {
  const contexts = [
    {
      contextLabel: "Transit map to table work",
      independentSuccessfulCount: 6,
      validOpportunityCount: 8,
      independentSuccessRate: 75,
    },
    {
      contextLabel: "Free choice to shared reading",
      independentSuccessfulCount: 1,
      validOpportunityCount: 4,
      independentSuccessRate: 25,
    },
  ];
  assert.equal(contextSummaryText(contexts[0]), "6 of 8 independent · 75%");
  const comparison = contextComparisonText(contexts);
  assert.match(comparison, /Performance was higher/);
  assert.doesNotMatch(comparison, /master|effective|caused|regress/i);
});

test("material usage wording does not claim causality", () => {
  const text = materialUsageText({
    sessionCount: 4,
    independentSuccessfulCount: 7,
  });
  assert.equal(text, "Used in 4 sessions with 7 independent responses.");
  assert.doesNotMatch(text, /improved|effective|caused|because/i);
});

test("the default progress chart renders one line rather than context overlays", () => {
  const source = readFileSync(
    new URL("../src/v2/components/ProgressTrendChart.tsx", import.meta.url),
    "utf8",
  );
  assert.equal(source.match(/<polyline/g)?.length, 1);
  assert.doesNotMatch(source, /contextSummaries\.map\([^)]*polyline/);
});
