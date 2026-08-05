import { Button } from "./Button";
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
    return <div className="v2-print-readiness is-checking" role="status"><strong>Preparing download…</strong></div>;
  }
  const next = readiness.recommendedNextAction ?? readiness.blockers[0] ?? null;
  const needsDirectAction = Boolean(next?.materialId || next?.recoveryAction.includes("generation"));
  const actionLabel = next?.materialId ? "Review next page" : "Check progress";
  return <section className={`v2-print-readiness ${readiness.ready ? "is-ready" : "is-blocked"}`} aria-label="Complete package print readiness">
    <div className="v2-print-readiness__heading">
      <div><strong>{readiness.ready ? "Ready to download" : "Preparing download"}</strong><small>{readiness.ready ? "The approved PDF is ready." : "Your approvals are saved. This updates automatically."}</small></div>
      <span aria-label={readiness.ready ? "Ready" : "Preparing"}>{readiness.ready ? "✓" : "…"}</span>
    </div>
    {next && needsDirectAction && <Button fullWidth disabled={busy} onClick={()=>onFix(next)}>{busy ? "Checking…" : actionLabel}</Button>}
  </section>;
}
