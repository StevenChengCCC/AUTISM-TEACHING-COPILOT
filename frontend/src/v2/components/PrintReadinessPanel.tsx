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
  const blockingCount = readiness.blockers.filter((item)=>item.severity==="blocking").length;
  const remaining = readiness.blockers.slice(1);
  return <section className={`v2-print-readiness ${readiness.ready ? "is-ready" : "is-blocked"}`} aria-label="Complete package print readiness">
    <div className="v2-print-readiness__heading">
      <div><strong>{readiness.ready ? "Ready to print" : "Printing needs attention"}</strong><small>{readiness.ready ? "All required reviews are complete." : `${blockingCount} check${blockingCount===1?"":"s"} remaining`}</small></div>
      <span aria-label={readiness.ready ? "Ready" : "Blocked"}>{readiness.ready ? "✓" : "!"}</span>
    </div>
    {next && !readiness.ready && <div className="v2-print-readiness__next"><b>{next.category.replace(/_/g," ")}</b><p>{next.explanation}</p></div>}
    {remaining.length > 0 && <details><summary>View {remaining.length} more check{remaining.length===1?"":"s"}</summary><ol>{remaining.map((item)=><li key={item.blockerId} className={item.severity === "warning" ? "is-warning" : ""}><div><b>{item.category.replace(/_/g," ")}</b><p>{item.explanation}</p></div></li>)}</ol></details>}
    {next && <Button fullWidth disabled={busy} onClick={()=>onFix(next)}>{busy ? "Checking…" : readinessActionLabel(next)}</Button>}
  </section>;
}
