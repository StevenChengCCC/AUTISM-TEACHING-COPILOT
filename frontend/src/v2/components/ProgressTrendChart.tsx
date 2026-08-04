import { useId,useMemo,useState } from "react";
import { accessibleSeriesSummary,chartCoordinates,formatMetricValue,isPointActivationKey,metricLabels,metricUnit,pointAriaLabel } from "../goalProgressChartModel";
import type { GoalProgressMetric,GoalProgressPoint,GoalProgressSeries } from "../types";

const WIDTH=640;const HEIGHT=280;const PADDING={top:24,right:28,bottom:48,left:54};

export function GoalProgressChart({series,metric,onMetricChange}:{series:GoalProgressSeries;metric:GoalProgressMetric;onMetricChange:(metric:GoalProgressMetric)=>void}) {
  const titleId=useId();const descriptionId=useId();
  const [selectedSession,setSelectedSession]=useState(series.points[series.points.length-1]?.sessionId??"");
  const coordinates=useMemo(()=>chartCoordinates(series,WIDTH,HEIGHT),[series]);
  const selected=series.points.find((point)=>point.sessionId===selectedSession)??series.points[series.points.length-1];
  const percent=metricUnit(metric)==="percent";
  const maximum=percent?100:Math.max(1,...series.points.map((point)=>point.value));
  const ticks=percent?[0,25,50,75,100]:[0,maximum/2,maximum];
  const polyline=coordinates.map(({x,y})=>`${x},${y}`).join(" ");
  const summary=accessibleSeriesSummary(series);
  return <div className="v2-progress-chart v2-goal-progress-chart">
    <div className="v2-progress-chart-controls"><label>Metric<select value={metric} onChange={(event)=>onMetricChange(event.target.value as GoalProgressMetric)}><option value="independent_success_rate">Independent success rate</option><option value="prompt_independence_display_score">Prompt independence display score</option><option value="average_response_latency">Average response latency</option><option value="generalization_context_count">Generalization context count</option><option value="return_after_break_rate">Return-after-break rate</option></select></label></div>
    {series.points.length===0?<p className="v2-progress-empty">{summary}</p>:<>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-labelledby={`${titleId} ${descriptionId}`}>
        <title id={titleId}>{metricLabels[metric]} for {series.operationalizedGoal}</title><desc id={descriptionId}>{summary} Use Tab to focus each session point and Enter or Space to select its details.</desc>
        {ticks.map((value)=>{const y=PADDING.top+(maximum-value)/maximum*(HEIGHT-PADDING.top-PADDING.bottom);return <g key={value}><line x1={PADDING.left} x2={WIDTH-PADDING.right} y1={y} y2={y} className="v2-chart-grid"/><text x={PADDING.left-8} y={y+4} textAnchor="end">{percent?`${Math.round(value)}%`:Math.round(value*10)/10}</text></g>;})}
        <text className="v2-chart-axis-label" transform={`translate(14 ${HEIGHT/2}) rotate(-90)`}>{metricLabels[metric]}</text>
        {coordinates.length>1&&<polyline points={polyline} className="v2-chart-line is-primary"/>}
        {coordinates.map(({point,x,y},index)=><g key={point.sessionId}><circle cx={x} cy={y} r={selected?.sessionId===point.sessionId?8:6} className={`v2-chart-dot is-primary ${point.confidence==="low"?"is-low-confidence":""}`} role="button" tabIndex={0} aria-label={pointAriaLabel(point,index)} aria-pressed={selected?.sessionId===point.sessionId} onClick={()=>setSelectedSession(point.sessionId)} onFocus={()=>setSelectedSession(point.sessionId)} onKeyDown={(event)=>{if(isPointActivationKey(event.key)){event.preventDefault();setSelectedSession(point.sessionId);}}}><title>{pointAriaLabel(point,index)}</title></circle><text x={x} y={HEIGHT-23} textAnchor="middle">{new Date(point.completedAt).toLocaleDateString(undefined,{month:"short",day:"numeric"})}</text>{point.annotation&&<text x={x} y={y-13} textAnchor="middle" className="v2-revision-marker">revision</text>}</g>)}
      </svg>
      <p className="v2-progress-accessible-summary" aria-live="polite">{summary}</p>
      {selected&&<PointDetails point={selected}/>}<details><summary>View all session values as a table</summary><table><thead><tr><th>Session date</th><th>{metricLabels[metric]}</th><th>Independent</th><th>Valid opportunities</th><th>Confidence</th></tr></thead><tbody>{series.points.map((point)=><tr key={point.sessionId}><td>{new Date(point.completedAt).toLocaleDateString()}</td><td>{formatMetricValue(metric,point.value)}</td><td>{point.details.independentSuccessfulCount??point.numeratorCount}</td><td>{point.validOpportunityCount}</td><td>{point.confidence}{point.confidenceReason?`: ${point.confidenceReason}`:""}</td></tr>)}</tbody></table></details>
    </>}
  </div>;
}

function PointDetails({point}:{point:GoalProgressPoint}) {
  return <section className="v2-progress-point-details" aria-live="polite" aria-label="Selected session details"><h4>{new Date(point.completedAt).toLocaleString()}</h4><p>{point.details.operationalizedGoal}</p><dl><div><dt>Independent responses</dt><dd>{point.details.independentSuccessfulCount??point.numeratorCount} of {point.validOpportunityCount}</dd></div><div><dt>Prompted successful</dt><dd>{point.details.promptedSuccessfulCount}</dd></div><div><dt>Response modes</dt><dd>{entries(point.details.responseModeCounts)}</dd></div><div><dt>Average prompt level</dt><dd>{point.details.averagePromptLevel??"Not recorded"}</dd></div><div><dt>Original prompt labels</dt><dd>{entries(point.details.promptLevelCounts)}</dd></div><div><dt>Average latency</dt><dd>{point.details.averageLatencySeconds===null?"Not recorded":`${point.details.averageLatencySeconds} seconds`}</dd></div><div><dt>Contexts attempted</dt><dd>{point.contextsAttempted.join(", ")||"None"}</dd></div><div><dt>Break and return</dt><dd>{point.details.returnedAfterBreakCount} returned after {point.details.breaksDeliveredCount} delivered breaks ({point.details.breakRequestCount} requests)</dd></div><div><dt>Materials used</dt><dd>{point.details.materialIdsUsed.join(", ")||"None recorded"}</dd></div><div><dt>Teacher notes</dt><dd>{point.details.teacherNotes||"No notes"}</dd></div></dl>{point.confidence==="low"&&<p className="v2-low-confidence-note">Low confidence: {point.confidenceReason}</p>}{point.annotation&&<p className="v2-revision-note">{point.annotation}</p>}</section>;
}

function entries(values:Record<string,number>):string{return Object.entries(values).filter(([,count])=>count>0).map(([label,count])=>`${label}: ${count}`).join(", ")||"None recorded";}
