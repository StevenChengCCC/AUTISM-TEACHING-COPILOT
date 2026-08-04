import type {
  PackagePrintReadiness,
  PackagePrintReadinessBlocker,
} from "./types";

export function blockingReadinessItems(
  readiness: PackagePrintReadiness | null,
): PackagePrintReadinessBlocker[] {
  return readiness?.blockers.filter((item) => item.severity === "blocking") ?? [];
}

export function nextReadinessItem(
  readiness: PackagePrintReadiness | null,
): PackagePrintReadinessBlocker | null {
  return readiness?.recommendedNextAction ?? readiness?.blockers[0] ?? null;
}

export function nextPendingMaterialId(
  readiness: PackagePrintReadiness | null,
  currentMaterialId?: string,
): string | null {
  return (
    readiness?.blockers.find(
      (item) =>
        item.severity === "blocking" &&
        Boolean(item.materialId) &&
        item.materialId !== currentMaterialId,
    )?.materialId ?? null
  );
}

export function readinessActionLabel(
  item: PackagePrintReadinessBlocker,
): string {
  const labels: Record<string, string> = {
    review_material: "Review material",
    approve_material: "Approve material",
    approve_package: "Approve complete package",
    retry_visual: "Open visual recovery",
    wait_for_visual: "Check visual progress",
    retry_generation: "Retry package generation",
    wait_for_generation: "Check generation progress",
    repair_material: "Open material repair",
    repair_package: "Open package repair",
    retry_pdf: "Retry PDF preparation",
    regenerate_pdf: "Build a current PDF",
    review_fallback: "Review fallback",
  };
  return labels[item.recoveryAction] ?? "Fix next issue";
}
