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
    return <div className="v2-print-readiness" role="status"><strong>Checking print readiness…</strong></div>;
  }
  const next = readiness.recommendedNextAction ?? readiness.blockers[0] ?? null;
  const actionLabel = next?.materialId
    ? "Review next page"
    : next?.recoveryAction.includes("generation")
      ? "Check progress"
      : "Refresh download";
  return <section className={`v2-print-readiness ${readiness.ready ? "is-ready" : "is-blocked"}`} aria-label="Complete package print readiness">
    <div className="v2-print-readiness__heading">
      <div><strong>{readiness.ready ? "Ready to download" : "Finish teacher review"}</strong><small>{readiness.ready ? "The approved PDF is ready." : "Download opens automatically after the last required page is approved."}</small></div>
      <span aria-label={readiness.ready ? "Ready" : "Blocked"}>{readiness.ready ? "✓" : "!"}</span>
    </div>
    {next && <Button fullWidth disabled={busy} onClick={()=>onFix(next)}>{busy ? "Checking…" : actionLabel}</Button>}
  </section>;
}
