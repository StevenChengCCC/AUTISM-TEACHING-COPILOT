import { useEffect, useState } from "react";
import { lessonKitApi } from "../api/lessonKitApi";
import {
  accessibleSeriesSummary,
  buildProgressEvidenceReport,
  contextComparisonText,
  contextSummaryText,
  formatMetricValue,
  materialUsageText,
  metricLabels,
} from "../goalProgressChartModel";
import type {
  GoalProgressMetric,
  GoalProgressSeries,
  GoalProgressSeriesOption,
} from "../types";
import { GoalProgressChart } from "./ProgressTrendChart";
import { NextSessionRecommendationsPanel } from "./NextSessionRecommendationsPanel";
import { NextSessionImpactPlanPanel } from "./NextSessionImpactPlanPanel";
import "./progressEvidenceReport.css";

export function GoalProgressPanel({ learnerId }: { learnerId: string }) {
  const [options, setOptions] = useState<GoalProgressSeriesOption[]>([]);
  const [selected, setSelected] = useState("");
  const [metric, setMetric] = useState<GoalProgressMetric>(
    "independent_success_rate",
  );
  const [contextKey, setContextKey] = useState("");
  const [series, setSeries] = useState<GoalProgressSeries | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setOptions([]);
    setSelected("");
    setMetric("independent_success_rate");
    setContextKey("");
    setSeries(null);
    void lessonKitApi
      .getGoalProgressSeriesOptions(learnerId)
      .then((items) => {
        setOptions(items);
        if (items[0])
          setSelected(`${items[0].goalId}|${items[0].goalRevision}`);
        else
          return lessonKitApi
            .getGoalProgressSeries(learnerId, "independent_success_rate")
            .then(setSeries);
      })
      .catch((reason) =>
        setError(
          reason instanceof Error
            ? reason.message
            : "Progress could not be loaded.",
        ),
      );
  }, [learnerId]);
  useEffect(() => {
    if (!selected) return;
    const separator = selected.lastIndexOf("|");
    const goalId = selected.slice(0, separator);
    const revision = Number(selected.slice(separator + 1));
    setError("");
    void lessonKitApi
      .getGoalProgressSeries(
        learnerId,
        metric,
        goalId,
        revision,
        contextKey || undefined,
      )
      .then(setSeries)
      .catch((reason) =>
        setError(
          reason instanceof Error
            ? reason.message
            : "Progress could not be loaded.",
        ),
      );
  }, [learnerId, selected, metric, contextKey]);
  const changeGoal = (value: string) => {
    setSelected(value);
    setContextKey("");
  };
  return (
    <section
      className="v2-progress-panel"
      aria-labelledby="goal-progress-heading"
    >
      <header>
        <div>
          <small>Goal-specific observable progress</small>
          <h3 id="goal-progress-heading">{metricLabels[metric]}</h3>
        </div>
        {options.length > 0 && (
          <label>
            Goal series
            <select
              value={selected}
              onChange={(event) => changeGoal(event.target.value)}
            >
              {options.map((option) => (
                <option
                  key={`${option.goalId}|${option.goalRevision}`}
                  value={`${option.goalId}|${option.goalRevision}`}
                >
                  {option.operationalizedGoal} · revision {option.goalRevision}{" "}
                  · {option.sessionCount} session
                  {option.sessionCount === 1 ? "" : "s"}
                </option>
              ))}
            </select>
          </label>
        )}
      </header>
      {error ? (
        <p role="alert">{error}</p>
      ) : series ? (
        <>
          <GoalProgressChart
            series={series}
            metric={metric}
            onMetricChange={setMetric}
          />
          <TrendSummary series={series} />
          <ContextBreakdown
            series={series}
            contextKey={contextKey}
            onContextChange={setContextKey}
          />
          <MaterialUsage series={series} />
          <ProgressEvidenceReport series={series} />
          {series.sessionCount > 0 && (
            <>
              <NextSessionRecommendationsPanel
                learnerId={learnerId}
                goalId={series.goalId}
                goalRevision={series.goalRevision}
              />
              {series.points.length > 0 && (
                <NextSessionImpactPlanPanel
                  previousPackageId={
                    series.points[series.points.length - 1].lessonPackageId
                  }
                />
              )}
            </>
          )}
        </>
      ) : (
        <p>Loading goal progress…</p>
      )}
    </section>
  );
}

function ProgressEvidenceReport({ series }: { series: GoalProgressSeries }) {
  const report = buildProgressEvidenceReport(series);
  const comparison = series.activeContextKey
    ? null
    : contextComparisonText(series.contextSummaries);
  const responseModes = Object.entries(report.responseModeCounts)
    .filter(([, count]) => count > 0)
    .map(([mode, count]) => `${responseModeLabel(mode)}: ${count}`)
    .join(" · ");
  return (
    <section
      className="v2-progress-evidence-report"
      aria-labelledby="progress-evidence-report-heading"
    >
      <header>
        <div>
          <small>Teacher-facing evidence from completed sessions</small>
          <h4 id="progress-evidence-report-heading">
            Progress evidence report
          </h4>
        </div>
        <span>{report.observationWindow}</span>
      </header>
      <div className="v2-progress-report-goal">
        <strong>Observed goal</strong>
        <p>{series.operationalizedGoal}</p>
      </div>
      <p className="v2-progress-report-scope">{report.scopeStatement}</p>
      <div className="v2-progress-report-totals" aria-label="Recorded totals">
        <article>
          <b>{series.sessionCount}</b>
          <span>completed sessions</span>
        </article>
        <article>
          <b>{report.totalValidOpportunities}</b>
          <span>valid opportunities</span>
        </article>
        <article>
          <b>{report.totalIndependentResponses}</b>
          <span>independent responses</span>
        </article>
        <article>
          <b>{report.totalPromptedResponses}</b>
          <span>prompted successes</span>
        </article>
      </div>
      <section className="v2-progress-report-narrative">
        <h5>What the recorded observations show</h5>
        <p>{accessibleSeriesSummary(series)}</p>
        {report.changeStatement && (
          <p>
            {report.changeStatement} This is a descriptive comparison, not a
            mastery decision.
          </p>
        )}
        {comparison && <p>{comparison}</p>}
        {series.trendEvidence.map((item) => (
          <p key={item}>{item}</p>
        ))}
        <p
          className={
            series.confidence === "low" ? "v2-low-confidence-note" : ""
          }
        >
          <b>Confidence: {series.confidence}.</b>{" "}
          {series.confidenceReasons.length
            ? series.confidenceReasons.join(" ")
            : "The recorded sessions meet the configured completeness checks, while teacher judgment remains necessary."}
        </p>
      </section>
      <div className="v2-progress-report-supports">
        <section>
          <h5>Communication and support record</h5>
          <p>
            <b>Successful response modes:</b> {responseModes || "Not recorded"}
          </p>
          <p>
            <b>Teacher observations:</b> notes were recorded in{" "}
            {report.teacherObservationCount} of {series.sessionCount} completed
            sessions.
          </p>
        </section>
        <section>
          <h5>Break and return record</h5>
          <p>
            {report.breakRequestCount} break requests,{" "}
            {report.breaksDeliveredCount} delivered breaks, and{" "}
            {report.returnedAfterBreakCount} recorded returns after a break.
          </p>
          <p>
            These counts describe recorded events and do not evaluate whether a
            break should have been requested or delivered.
          </p>
        </section>
      </div>
      <div className="v2-progress-report-sessions">
        <h5>Session-by-session evidence</h5>
        <div
          className="v2-progress-report-table-wrap"
          role="region"
          aria-label="Scrollable session-by-session evidence table"
          tabIndex={0}
        >
          <table>
            <thead>
              <tr>
                <th>Session</th>
                <th>{metricLabels[series.metric]}</th>
                <th>Independent</th>
                <th>Prompted</th>
                <th>Valid opportunities</th>
                <th>Response modes</th>
                <th>Contexts</th>
                <th>Teacher observation</th>
              </tr>
            </thead>
            <tbody>
              {series.points.length === 0 ? (
                <tr>
                  <td colSpan={8}>
                    No completed session evidence is available.
                  </td>
                </tr>
              ) : (
                series.points.map((point, index) => {
                  const modes = Object.entries(point.details.responseModeCounts)
                    .filter(([, count]) => count > 0)
                    .map(
                      ([mode, count]) => `${responseModeLabel(mode)}: ${count}`,
                    )
                    .join(", ");
                  const teacherObservation = point.details.teacherNotes.trim();
                  return (
                    <tr key={point.sessionId}>
                      <td>
                        Session {index + 1}
                        <small>
                          {new Date(point.completedAt).toLocaleDateString()}
                        </small>
                      </td>
                      <td>{formatMetricValue(series.metric, point.value)}</td>
                      <td>
                        {point.details.independentSuccessfulCount ??
                          point.numeratorCount}
                      </td>
                      <td>{point.details.promptedSuccessfulCount}</td>
                      <td>{point.validOpportunityCount}</td>
                      <td>{modes || "Not recorded"}</td>
                      <td>
                        {point.contextsAttempted.join(", ") || "Not recorded"}
                      </td>
                      <td>
                        {teacherObservation ||
                          "No teacher observation recorded"}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
      <aside>
        <strong>Interpretation boundary</strong>
        <p>
          This report summarizes teacher-recorded observations. It does not
          diagnose, claim causality, or determine mastery. The teacher decides
          how these observations should inform instruction.
        </p>
      </aside>
    </section>
  );
}

function responseModeLabel(mode: string): string {
  if (mode.toLowerCase() === "aac") return "AAC";
  return mode.charAt(0).toUpperCase() + mode.slice(1).replace(/_/g, " ");
}

function TrendSummary({ series }: { series: GoalProgressSeries }) {
  return (
    <div className="v2-progress-trend">
      <strong>Pattern classification: {series.trend.replace(/_/g, " ")}</strong>
      {series.trendEvidence.map((item) => (
        <p key={item}>{item}</p>
      ))}
      <p
        className={series.confidence === "low" ? "v2-low-confidence-note" : ""}
      >
        <b>Interpretation confidence: {series.confidence}.</b>
        {series.confidenceReasons.length
          ? ` ${series.confidenceReasons.join(" ")}`
          : " The recent observations meet the configured completeness checks."}
      </p>
    </div>
  );
}

function ContextBreakdown({
  series,
  contextKey,
  onContextChange,
}: {
  series: GoalProgressSeries;
  contextKey: string;
  onContextChange: (value: string) => void;
}) {
  const eligible = series.contextSummaries.filter(
    (item) => item.filterEligible,
  );
  const comparison = contextComparisonText(series.contextSummaries);
  return (
    <section
      className="v2-context-breakdown"
      aria-labelledby="context-breakdown-heading"
    >
      <div className="v2-context-breakdown-heading">
        <div>
          <small>Structured trial contexts</small>
          <h4 id="context-breakdown-heading">Context breakdown</h4>
        </div>
        {eligible.length > 0 && (
          <label>
            Filter the main curve
            <select
              value={contextKey}
              onChange={(event) => onContextChange(event.target.value)}
            >
              <option value="">All recorded contexts</option>
              {eligible.map((context) => (
                <option key={context.contextKey} value={context.contextKey}>
                  {context.contextLabel}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {contextKey && (
        <p className="v2-context-filter-note">
          The single main curve is filtered to the selected context. Clear the
          filter to return to overall performance.
        </p>
      )}
      {comparison && <p>{comparison}</p>}
      <ul>
        {series.contextSummaries.map((context) => (
          <li key={context.contextKey}>
            <div>
              <strong>{context.contextLabel}</strong>
              <span>{contextSummaryText(context)}</span>
            </div>
            <small>
              {context.sessionCount} session
              {context.sessionCount === 1 ? "" : "s"}
              {context.contextDimension ? ` · ${context.contextDimension}` : ""}
              {context.averageLatencySeconds === null
                ? " · latency not recorded"
                : ` · ${context.averageLatencySeconds}s average latency`}
            </small>
            {context.confidence === "low" && (
              <p className="v2-low-confidence-note">
                Low confidence: {context.confidenceReasons.join(" ")}
              </p>
            )}
          </li>
        ))}
      </ul>
      {series.contextSummaries.length === 0 && (
        <p>No structured context observations are available for this goal.</p>
      )}
    </section>
  );
}

function MaterialUsage({ series }: { series: GoalProgressSeries }) {
  return (
    <section
      className="v2-material-usage"
      aria-labelledby="material-usage-heading"
    >
      <small>Descriptive association only</small>
      <h4 id="material-usage-heading">
        Materials recorded during opportunities
      </h4>
      <p>
        These counts describe co-occurrence. They do not show that a material
        caused a response.
      </p>
      <ul>
        {series.materialUsageSummaries.map((material) => (
          <li key={material.materialId}>
            <strong>{material.materialLabel}</strong>
            <span>{materialUsageText(material)}</span>
            {material.contextsWithIndependentResponses.length > 0 && (
              <small>
                Independent responses recorded in:{" "}
                {material.contextsWithIndependentResponses.join(", ")}.
              </small>
            )}
            {material.contextsWithoutIndependentResponses.length > 0 && (
              <small>
                No independent responses recorded in:{" "}
                {material.contextsWithoutIndependentResponses.join(", ")}.
              </small>
            )}
          </li>
        ))}
      </ul>
      {series.materialUsageSummaries.length === 0 && (
        <p>No material use was recorded in valid opportunities.</p>
      )}
    </section>
  );
}
