import type {
  GoalContextSummary,
  GoalMaterialUsageSummary,
  GoalProgressMetric,
  GoalProgressPoint,
  GoalProgressSeries,
} from "./types";

export const metricLabels: Record<GoalProgressMetric, string> = {
  independent_success_rate: "Independent target response rate",
  prompt_independence_display_score: "Prompt independence display score",
  average_response_latency: "Average response latency",
  generalization_context_count: "Generalization context count",
  return_after_break_rate: "Return-after-break rate",
};

export function metricUnit(metric: GoalProgressMetric): string {
  if (metric === "average_response_latency") return "seconds";
  if (metric === "generalization_context_count") return "contexts";
  return "percent";
}

export function limitedStateText(count: number): string | null {
  if (count === 0) return "No completed sessions are available for this goal.";
  if (count === 1)
    return "One observation is available. More sessions are needed to show a trend.";
  if (count === 2)
    return "Two observations are available. This shows a comparison but not a stable trend.";
  return null;
}

export function accessibleSeriesSummary(series: GoalProgressSeries): string {
  const limited = limitedStateText(series.sessionCount);
  if (limited) return limited;
  if (series.metric === "independent_success_rate") {
    const observations = series.points.map(
      (point) =>
        `${point.details.independentSuccessfulCount ?? point.numeratorCount} of ${point.validOpportunityCount}`,
    );
    return `Across ${series.sessionCount} recorded sessions, independent responses were ${joinList(observations)}.`;
  }
  const values = series.points.map((point) =>
    formatMetricValue(series.metric, point.value),
  );
  return `Across ${series.sessionCount} recorded sessions, ${metricLabels[series.metric].toLowerCase()} values were ${joinList(values)}.`;
}

export function formatMetricValue(
  metric: GoalProgressMetric,
  value: number,
): string {
  if (metricUnit(metric) === "percent") return `${value}%`;
  if (metric === "average_response_latency") return `${value} seconds`;
  return `${value} context${value === 1 ? "" : "s"}`;
}

export function pointAriaLabel(
  point: GoalProgressPoint,
  index: number,
): string {
  return `Session ${index + 1}, ${new Date(point.completedAt).toLocaleDateString()}, ${formatMetricValue(point.metric, point.value)}, ${point.details.independentSuccessfulCount ?? point.numeratorCount} independent responses of ${point.validOpportunityCount} valid opportunities${point.confidence === "low" ? ", low confidence" : ""}.`;
}

export function isPointActivationKey(key: string): boolean {
  return key === "Enter" || key === " ";
}

export function contextSummaryText(context: GoalContextSummary): string {
  return `${context.independentSuccessfulCount} of ${context.validOpportunityCount} independent · ${context.independentSuccessRate}%`;
}

export function contextComparisonText(
  contexts: GoalContextSummary[],
): string | null {
  if (contexts.length < 2) return null;
  const ordered = [...contexts].sort(
    (a, b) => b.independentSuccessRate - a.independentSuccessRate,
  );
  if (
    ordered[0].independentSuccessRate ===
    ordered[ordered.length - 1].independentSuccessRate
  )
    return "Independent response rates were the same across the recorded contexts.";
  return `Performance was higher in ${ordered[0].contextLabel} than in ${ordered[ordered.length - 1].contextLabel} during the recorded opportunities.`;
}

export function materialUsageText(material: GoalMaterialUsageSummary): string {
  return `Used in ${material.sessionCount} session${material.sessionCount === 1 ? "" : "s"} with ${material.independentSuccessfulCount} independent response${material.independentSuccessfulCount === 1 ? "" : "s"}.`;
}

export interface ProgressEvidenceReport {
  observationWindow: string;
  scopeStatement: string;
  totalValidOpportunities: number;
  totalIndependentResponses: number;
  totalPromptedResponses: number;
  responseModeCounts: Record<string, number>;
  breakRequestCount: number;
  breaksDeliveredCount: number;
  returnedAfterBreakCount: number;
  teacherObservationCount: number;
  changeStatement: string | null;
}

export function buildProgressEvidenceReport(
  series: GoalProgressSeries,
): ProgressEvidenceReport {
  const points = series.points;
  const first = points[0];
  const latest = points[points.length - 1];
  const responseModeCounts: Record<string, number> = {};
  let totalValidOpportunities = 0;
  let totalIndependentResponses = 0;
  let totalPromptedResponses = 0;
  let breakRequestCount = 0;
  let breaksDeliveredCount = 0;
  let returnedAfterBreakCount = 0;
  let teacherObservationCount = 0;
  for (const point of points) {
    totalValidOpportunities += point.validOpportunityCount;
    totalIndependentResponses +=
      point.details.independentSuccessfulCount ?? point.numeratorCount;
    totalPromptedResponses += point.details.promptedSuccessfulCount;
    breakRequestCount += point.details.breakRequestCount;
    breaksDeliveredCount += point.details.breaksDeliveredCount;
    returnedAfterBreakCount += point.details.returnedAfterBreakCount;
    if (point.details.teacherNotes.trim()) teacherObservationCount += 1;
    for (const [mode, count] of Object.entries(
      point.details.responseModeCounts,
    )) {
      responseModeCounts[mode] = (responseModeCounts[mode] ?? 0) + count;
    }
  }
  const observationWindow =
    first && latest
      ? `${new Date(first.completedAt).toLocaleDateString()} to ${new Date(latest.completedAt).toLocaleDateString()}`
      : "No completed observation window";
  const activeContext = series.activeContextKey
    ? series.contextSummaries?.find(
        (context) => context.contextKey === series.activeContextKey,
      )
    : undefined;
  const scopeStatement = series.activeContextKey
    ? activeContext
      ? `Counts and metric values are filtered to ${activeContext.contextLabel}; teacher observations remain whole-session notes.`
      : "Counts and metric values are filtered to the selected structured context; its saved label is unavailable. Teacher observations remain whole-session notes."
    : "Totals and session details include all recorded contexts in this goal series.";
  let changeStatement: string | null = null;
  if (first && latest && points.length >= 2) {
    const firstValue = formatMetricValue(series.metric, first.value);
    const latestValue = formatMetricValue(series.metric, latest.value);
    changeStatement =
      first.value === latest.value
        ? `The first and most recent recorded values were both ${latestValue}.`
        : `The most recent recorded value was ${latestValue}, compared with ${firstValue} in the first recorded session.`;
  }
  return {
    observationWindow,
    scopeStatement,
    totalValidOpportunities,
    totalIndependentResponses,
    totalPromptedResponses,
    responseModeCounts,
    breakRequestCount,
    breaksDeliveredCount,
    returnedAfterBreakCount,
    teacherObservationCount,
    changeStatement,
  };
}

export function chartCoordinates(
  series: GoalProgressSeries,
  width = 640,
  height = 280,
) {
  const padding = { top: 24, right: 28, bottom: 48, left: 54 };
  const usableWidth = width - padding.left - padding.right;
  const usableHeight = height - padding.top - padding.bottom;
  const isPercent = metricUnit(series.metric) === "percent";
  const maximum = isPercent
    ? 100
    : Math.max(1, ...series.points.map((point) => point.value));
  return series.points.map((point, index) => ({
    point,
    x:
      padding.left +
      (series.points.length === 1
        ? usableWidth / 2
        : (index * usableWidth) / (series.points.length - 1)),
    y:
      padding.top +
      usableHeight -
      (Math.min(maximum, Math.max(0, point.value)) / maximum) * usableHeight,
  }));
}

function joinList(values: string[]): string {
  if (values.length <= 1) return values[0] ?? "";
  if (values.length === 2) return `${values[0]} and ${values[1]}`;
  return `${values.slice(0, -1).join(", ")}, and ${values[values.length - 1]}`;
}
