import { Button } from "./Button";
import { readinessActionLabel } from "../printReadinessModel";
import type { PackagePrintReadiness } from "../types";

export function PrintReadinessPanel({
  readiness,
  busy = false,
  onFix,
}: {
  readiness: PackagePrintReadiness | null;
  busy?: boolean;
  onFix: (blocker: NonNullable<PackagePrintReadiness["recommendedNextAction"]>) => void;
}) {
  if (!readiness) {
    return <div className="v2-print-readiness" role="status"><strong>Checking print readiness…</strong></div>;
  }
  const next = readiness.recommendedNextAction ?? readiness.blockers[0] ?? null;
  const visible = readiness.blockers.slice(0, 3);
  const remaining = readiness.blockers.slice(3);
  const blockerItem = (item: (typeof readiness.blockers)[number]) => <li key={item.blockerId} className={item.severity === "warning" ? "is-warning" : ""}>
    <div><b>{item.category.replace(/_/g," ")}</b><p>{item.explanation}</p>{item.materialId&&<small>Material {item.materialId}{item.visualId?` · visual ${item.visualId}`:""}</small>}</div>
    <em>{item.retryPossible ? "Recovery available" : item.severity === "warning" ? "Approved fallback" : "Teacher action required"}</em>
  </li>;
  return <section className={`v2-print-readiness ${readiness.ready ? "is-ready" : "is-blocked"}`} aria-label="Complete package print readiness">
    <div className="v2-print-readiness__heading">
      <div><strong>{readiness.ready ? "Complete package ready" : `${readiness.blockers.filter((item)=>item.severity==="blocking").length} issue${readiness.blockers.filter((item)=>item.severity==="blocking").length===1?"":"s"} block printing`}</strong><small>Package revision {readiness.packageRevision} · Lesson specification revision {readiness.lessonSpecRevision}</small></div>
      <span aria-label={readiness.ready ? "Ready" : "Blocked"}>{readiness.ready ? "✓" : "!"}</span>
    </div>
    {visible.length > 0 && <ol>{visible.map(blockerItem)}</ol>}
    {remaining.length > 0 && <details><summary>Show {remaining.length} more readiness checks</summary><ol start={4}>{remaining.map(blockerItem)}</ol></details>}
    {next && <Button fullWidth disabled={busy} onClick={()=>onFix(next)}>{busy ? "Updating readiness…" : `Fix next issue · ${readinessActionLabel(next)}`}</Button>}
  </section>;
}
