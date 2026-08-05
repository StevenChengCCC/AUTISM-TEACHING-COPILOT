from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import Settings, settings
from app.core.exceptions import NotFoundError
from app.integrations.private_object_storage import PrivateObjectStorage
from app.schemas.v2_dto import (
    GeneratedMaterialDto,
    GenerationJobDto,
    LessonPackageDto,
    LessonPackageExportJobDto,
    PackagePrintReadiness,
    PackagePrintReadinessBlocker,
)
from app.services.v2_package_content_plan_service import V2PackageContentPlanService
from app.services.v2_repositories import V2Repositories, repositories
from app.services.v2_visual_asset_resolver import V2VisualAssetResolver


class V2PrintReadinessService:
    """Canonical, privacy-safe decision boundary for complete-kit printing."""

    renderer_version = "print-package-reportlab-v5-teacher-efficient"
    _priority = {
        "generation_job_failed": 10,
        "generation_job_incomplete": 20,
        "stale_lesson_spec_revision": 30,
        "stale_package_revision": 40,
        "stale_material_revision": 50,
        "stale_visual_plan_revision": 60,
        "semantic_validation_failure": 70,
        "safety_validation_failure": 80,
        "failed_required_visual": 90,
        "pending_visual": 100,
        "material_revision_not_reviewed": 110,
        "material_revision_not_approved": 120,
        "package_not_approved": 130,
        "failed_optional_visual_with_fallback": 140,
        "storage_download_preparation_failure": 150,
        "renderer_manifest_incompatibility": 160,
    }

    def __init__(
        self,
        repos: V2Repositories = repositories,
        storage: PrivateObjectStorage | None = None,
        config: Settings = settings,
    ) -> None:
        self.repos = repos
        self.visual_assets = V2VisualAssetResolver(
            repos, storage=storage, config=config
        )

    @staticmethod
    def _revision(material: GeneratedMaterialDto) -> int:
        return material.materialSpec.revision if material.materialSpec else material.version

    @staticmethod
    def _label(material: GeneratedMaterialDto) -> str:
        return material.type.replace("_", " ").title()

    def current_materials(self, package: LessonPackageDto) -> list[GeneratedMaterialDto]:
        stored = {
            item.id: item
            for item in self.repos.generated_materials.for_package(package.id)
            if isinstance(item, GeneratedMaterialDto)
        }
        snapshots = [stored.get(item.id, item) for item in package.materials]
        if package.packageContentPlan is None:
            return snapshots
        included = V2PackageContentPlanService.included_material_types(
            package.packageContentPlan
        )
        by_type: dict[str, list[GeneratedMaterialDto]] = {}
        for material in snapshots:
            by_type.setdefault(material.type, []).append(material)
        return [by_type[kind][0] for kind in included if len(by_type.get(kind, [])) == 1]

    def evaluate(self, package_id: str) -> PackagePrintReadiness:
        package = self.repos.lesson_packages.get(package_id)
        if not isinstance(package, LessonPackageDto):
            raise NotFoundError("Lesson package not found")
        materials = self.current_materials(package)
        blockers: list[PackagePrintReadinessBlocker] = []

        def add(
            category: str,
            explanation: str,
            recovery_action: str,
            recovery_route: str,
            *,
            material: GeneratedMaterialDto | None = None,
            visual_id: str | None = None,
            severity: str = "blocking",
            expected_revision: int | None = None,
            current_revision: int | None = None,
            expected_spec_revision: int | None = None,
            current_spec_revision: int | None = None,
            retry: bool = False,
        ) -> None:
            target = visual_id or (material.id if material else package.id)
            blockers.append(PackagePrintReadinessBlocker(
                blockerId=f"print-readiness:{category}:{target}",
                category=category,
                severity=severity,
                materialId=material.id if material else None,
                visualId=visual_id,
                explanation=explanation,
                expectedRevision=expected_revision,
                currentRevision=current_revision,
                expectedLessonSpecRevision=expected_spec_revision,
                currentLessonSpecRevision=current_spec_revision,
                recoveryAction=recovery_action,
                recoveryRoute=recovery_route,
                recoveryTargetId=target,
                retryPossible=retry,
            ))

        jobs = [
            item for item in self.repos.generation_jobs.list()
            if isinstance(item, GenerationJobDto) and item.packageId == package.id
        ]
        if jobs:
            job = jobs[-1]
            if job.status == "failed":
                add("generation_job_failed", "Package generation stopped before every required stage completed.", "retry_generation", "lessonPackageReady", retry=job.recoverable)
            elif job.status in {"pending", "in_progress"}:
                add("generation_job_incomplete", "Package generation is still completing required stages.", "wait_for_generation", "lessonPackageReady", retry=False)

        lesson_spec = package.lessonSpec
        spec_id = lesson_spec.id if lesson_spec else "legacy-lesson-spec"
        spec_revision = lesson_spec.revision if lesson_spec else 1
        if package.validationPolicy == "strict_v1":
            if lesson_spec is None or package.validatedLessonSpecRevision != spec_revision:
                add(
                    "stale_lesson_spec_revision",
                    "The package was not validated against the current lesson specification.",
                    "revalidate_package", "lessonPackageReady",
                    expected_spec_revision=spec_revision,
                    current_spec_revision=package.validatedLessonSpecRevision,
                )
            if package.validationStatus != "passed" or package.validatedRevision != package.version:
                category = "semantic_validation_failure" if package.validationStatus == "failed" else "stale_package_revision"
                add(
                    category,
                    "The current package revision has not passed semantic validation." if category == "semantic_validation_failure" else "The current package revision has not been revalidated.",
                    "repair_package" if category == "semantic_validation_failure" else "revalidate_package",
                    "lessonPackageReady",
                    expected_revision=package.version,
                    current_revision=package.validatedRevision,
                )
            if package.safetyReview and package.safetyReview.status == "blocked":
                add("safety_validation_failure", "The package has a blocking instructional safety finding.", "repair_package", "lessonPackageReady")

        expected_types = (
            V2PackageContentPlanService.included_material_types(package.packageContentPlan)
            if package.packageContentPlan is not None else []
        )
        if expected_types and len(materials) != len(expected_types):
            add("stale_package_revision", "The current package inventory does not match its approved content plan.", "regenerate_package", "lessonPackageReady", expected_revision=package.version, current_revision=package.version, retry=True)

        snapshots = {item.id: item for item in package.materials}
        for material in materials:
            label = self._label(material)
            revision = self._revision(material)
            snapshot = snapshots.get(material.id)
            if (
                package.validationPolicy == "strict_v1"
                and snapshot is not None
                and snapshot.materialSpec is not None
                and material.materialSpec is not None
                and snapshot.materialSpec.revision != material.materialSpec.revision
            ):
                add("stale_material_revision", f"{label} changed after the package snapshot was created.", "refresh_package", "reviewPrintableContent", material=material, expected_revision=revision, current_revision=self._revision(snapshot))
            spec = material.materialSpec
            if package.validationPolicy == "strict_v1":
                if material.materialSchemaVersion != 1 or spec is None or spec.semantic_validation.status != "passed":
                    add("semantic_validation_failure", f"{label} has not passed semantic validation.", "repair_material", "reviewPrintableContent", material=material, expected_revision=revision, current_revision=revision)
                if spec is None or spec.safety_validation.status != "passed":
                    add("safety_validation_failure", f"{label} has not passed safety validation.", "repair_material", "reviewPrintableContent", material=material, expected_revision=revision, current_revision=revision)
            plan = material.visualAssetPlan
            rendered_items = [
                item
                for item in material.content.get("visualItems", [])
                if isinstance(item, dict)
            ]
            if plan is not None:
                rendered_visuals = {
                    str(item.get("id")): item
                    for item in rendered_items
                    if item.get("id")
                }
                if plan.material_revision != revision:
                    add("stale_visual_plan_revision", f"{label}'s visual plan belongs to an older material revision.", "regenerate_visual_plan", "reviewPrintableContent", material=material, expected_revision=revision, current_revision=plan.material_revision, retry=True)
                for visual in plan.visual_items:
                    fallback = bool(visual.fallback_asset_id)
                    if visual.required and visual.status == "failed":
                        add("failed_required_visual", f"A required visual for {label} failed and must be replaced or regenerated.", "retry_visual", "reviewPrintableContent", material=material, visual_id=visual.id, expected_revision=revision, current_revision=plan.material_revision, retry=True)
                    elif visual.required and visual.status in {"planned", "generating"} and not fallback:
                        add("pending_visual", f"A required visual for {label} is not ready.", "retry_visual" if visual.status == "planned" else "wait_for_visual", "reviewPrintableContent", material=material, visual_id=visual.id, retry=visual.status == "planned")
                    elif not visual.required and visual.status == "failed" and fallback:
                        add("failed_optional_visual_with_fallback", f"An optional visual for {label} failed; its approved deterministic fallback will be printed.", "review_fallback", "reviewPrintableContent", material=material, visual_id=visual.id, severity="warning", retry=True)
                    elif not visual.required and visual.status == "failed":
                        add("pending_visual", f"An optional visual for {label} failed without a fallback and will be omitted unless retried.", "retry_visual", "reviewPrintableContent", material=material, visual_id=visual.id, severity="warning", retry=True)
                    elif (
                        visual.required
                        and visual.status in {"ready", "needs_review"}
                        and not self.visual_assets.is_resolvable(
                            rendered_visuals.get(visual.id, {})
                        )
                    ):
                        add(
                            "storage_download_preparation_failure",
                            f"A required visual for {label} is marked ready but its stored image cannot be reopened.",
                            "retry_visual",
                            "reviewPrintableContent",
                            material=material,
                            visual_id=visual.id,
                            retry=True,
                        )
            planned_ids = {
                item.id for item in plan.visual_items
            } if plan is not None else set()
            for rendered in rendered_items:
                visual_id = str(rendered.get("id") or "rendered-visual")
                if visual_id in planned_ids:
                    continue
                required = bool(rendered.get("required", True))
                status = str(rendered.get("generationStatus") or "").casefold()
                if required and status == "failed":
                    add(
                        "failed_required_visual",
                        f"A required visual for {label} failed and must be replaced or regenerated.",
                        "retry_visual",
                        "reviewPrintableContent",
                        material=material,
                        visual_id=visual_id,
                        retry=True,
                    )
                elif required and status in {"pending", "processing", "not_started"}:
                    add(
                        "pending_visual",
                        f"A required visual for {label} is not ready.",
                        "retry_visual",
                        "reviewPrintableContent",
                        material=material,
                        visual_id=visual_id,
                        retry=True,
                    )
                elif required and not self.visual_assets.is_resolvable(rendered):
                    add(
                        "storage_download_preparation_failure",
                        f"A required visual for {label} is marked ready but its stored image cannot be reopened.",
                        "retry_visual",
                        "reviewPrintableContent",
                        material=material,
                        visual_id=visual_id,
                        retry=True,
                    )
            approval = spec.approval if spec else None
            if spec is not None and (approval.reviewed_revision != revision or approval.status == "not_reviewed"):
                add("material_revision_not_reviewed", f"The current {label} revision has not been individually reviewed.", "review_material", "reviewPrintableContent", material=material, expected_revision=revision, current_revision=approval.reviewed_revision)
            if material.status != "approved" or (approval is not None and (approval.status != "approved" or approval.approved_revision != revision)):
                add("material_revision_not_approved", f"The current {label} revision has not been explicitly approved for print.", "approve_material", "reviewPrintableContent", material=material, expected_revision=revision, current_revision=approval.approved_revision if approval else None)

        if package.status != "approved":
            add("package_not_approved", "The complete package has not been explicitly approved.", "approve_package", "lessonPackageReady", expected_revision=package.version, current_revision=package.version)

        manifests_compatible = True
        export_jobs = [
            item for item in self.repos.export_jobs.list()
            if isinstance(item, LessonPackageExportJobDto)
            and item.packageId == package.id
            and item.format == "pdf"
            and item.exportId.startswith("print-kit-")
        ]
        if export_jobs:
            latest = export_jobs[-1]
            if latest.status == "failed":
                add("storage_download_preparation_failure", "The last PDF preparation or storage attempt failed; approved source materials were preserved.", "retry_pdf", "lessonPackageReady", severity="warning", retry=True)
            manifest = latest.printPackageManifest
            if manifest is not None and manifest.rendererVersion != self.renderer_version:
                manifests_compatible = False
                add("renderer_manifest_incompatibility", "The existing PDF uses an older renderer manifest and must be rebuilt.", "regenerate_pdf", "lessonPackageReady", severity="warning", retry=True)

        blockers.sort(key=lambda item: (self._priority[item.category], item.materialId or "", item.visualId or ""))
        blocking = [item for item in blockers if item.severity == "blocking"]
        return PackagePrintReadiness(
            packageId=package.id,
            packageRevision=package.version,
            lessonSpecId=spec_id,
            lessonSpecRevision=spec_revision,
            ready=not blocking,
            evaluatedAt=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            materialRevisions={item.id: self._revision(item) for item in materials},
            visualPlanRevisions={item.id: item.visualAssetPlan.material_revision for item in materials if item.visualAssetPlan is not None},
            packageApprovalStatus=package.status,
            blockers=blockers,
            recommendedNextAction=(blocking or blockers or [None])[0],
            rendererVersion=self.renderer_version,
            manifestCompatible=manifests_compatible,
        )
