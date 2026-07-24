import type { ProgressDataPoint } from "../types";

const WIDTH = 560;
const HEIGHT = 220;
const PADDING = { top: 20, right: 22, bottom: 42, left: 42 };

function pointsFor(data: ProgressDataPoint[], key: "accuracyPercent" | "independencePercent") {
  const usableWidth = WIDTH - PADDING.left - PADDING.right;
  const usableHeight = HEIGHT - PADDING.top - PADDING.bottom;
  return data.map((point, index) => {
    const x = PADDING.left + (data.length === 1 ? usableWidth / 2 : index * usableWidth / (data.length - 1));
    const value = Math.min(100, Math.max(0, point[key]));
    const y = PADDING.top + usableHeight - value / 100 * usableHeight;
    return { x, y, value, point };
  });
}

export function ProgressTrendChart({ data }: { data: ProgressDataPoint[] }) {
  const ordered = [...data].sort((a, b) => a.sessionDate.localeCompare(b.sessionDate)).slice(-8);
  if (!ordered.length) return <div className="v2-progress-empty">Record a session to begin the progress timeline.</div>;
  const accuracy = pointsFor(ordered, "accuracyPercent");
  const independence = pointsFor(ordered, "independencePercent");
  const line = (items: typeof accuracy) => items.map(({ x, y }) => `${x},${y}`).join(" ");
  return <div className="v2-progress-chart">
    <div className="v2-progress-legend"><span><i className="is-accuracy" />Accuracy</span><span><i className="is-independence" />Independence</span></div>
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-labelledby="progress-chart-title progress-chart-desc">
      <title id="progress-chart-title">Learner progress over recent sessions</title>
      <desc id="progress-chart-desc">Accuracy and independence percentages, with prompt level shown below each session.</desc>
      {[0, 25, 50, 75, 100].map((value) => {
        const y = PADDING.top + (100 - value) / 100 * (HEIGHT - PADDING.top - PADDING.bottom);
        return <g key={value}><line x1={PADDING.left} x2={WIDTH - PADDING.right} y1={y} y2={y} className="v2-chart-grid" /><text x={PADDING.left - 8} y={y + 4} textAnchor="end">{value}%</text></g>;
      })}
      <polyline points={line(accuracy)} className="v2-chart-line is-accuracy" />
      <polyline points={line(independence)} className="v2-chart-line is-independence" />
      {accuracy.map(({ x, y, point }, index) => <g key={point.id}>
        <circle cx={x} cy={y} r="5" className="v2-chart-dot is-accuracy"><title>{point.sessionDate}: {point.accuracyPercent}% accuracy</title></circle>
        <circle cx={independence[index].x} cy={independence[index].y} r="5" className="v2-chart-dot is-independence"><title>{point.sessionDate}: {point.independencePercent}% independence</title></circle>
        <text x={x} y={HEIGHT - 22} textAnchor="middle">{new Date(`${point.sessionDate}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</text>
        <text x={x} y={HEIGHT - 7} textAnchor="middle" className="v2-chart-prompt">{point.promptLevel}</text>
      </g>)}
    </svg>
    <details><summary>View accessible session data</summary><table><thead><tr><th>Date</th><th>Accuracy</th><th>Independence</th><th>Prompt</th><th>Small win / note</th></tr></thead><tbody>{ordered.map((point) => <tr key={point.id}><td>{point.sessionDate}</td><td>{point.accuracyPercent}%</td><td>{point.independencePercent}%</td><td>{point.promptLevel}</td><td>{point.teacherNotes}</td></tr>)}</tbody></table></details>
  </div>;
}
