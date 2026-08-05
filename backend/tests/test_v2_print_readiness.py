from fastapi.testclient import TestClient

from app.api.v2_routes import _print_readiness_service
from app.main import app
from app.schemas.v2_dto import (
    GenerationJobDto,
    LessonPackageDecisionRequest,
    LessonPackageExportJobDto,
    MaterialValidationResult,
    PrintPackageManifest,
    PrintPackageManifestSection,
    PrintSourceApprovalReadinessEvidence,
)
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_material_service import V2MaterialService
from app.services.v2_print_readiness_service import V2PrintReadinessService
from app.services.v2_repositories import V2Repositories
from test_v2_lesson_spec import (
    build_instructional_constraint_snapshot,
    n482_draft,
    n482_learner,
)
from test_v2_printable_lesson_kit import _seed_package


def _generated_package(repos: V2Repositories):
    learner = n482_learner()
    repos.learners.save(learner)
    snapshot = build_instructional_constraint_snapshot(learner, [])
    packages = V2LessonPackageService(repos)
    draft = n482_draft(snapshot)
    draft = draft.model_copy(
        update={"packageContentPlan": packages.preview_content_plan(draft)}
    )
    return packages.generate_product(draft)


def _ready_package(repos: V2Repositories):
    package, _materials = _seed_package(repos)
    return package


def test_canonical_readiness_is_ready_and_api_matches_service():
    repos = V2Repositories()
    package = _ready_package(repos)
    service = V2PrintReadinessService(repos)
    direct = service.evaluate(package.id)
    assert direct.ready is True
    assert direct.blockers == []
    assert set(direct.materialRevisions) == {
        item.id for item in package.materials
    }
    assert direct.packageRevision == package.version

    client = TestClient(app)
    app.dependency_overrides[_print_readiness_service] = lambda: service
    try:
        response = client.get(
            f"/api/v2/lesson-packages/{package.id}/print-readiness"
        )
    finally:
        app.dependency_overrides.pop(_print_readiness_service, None)
    assert response.status_code == 200
    payload = response.json()
    expected = direct.model_dump(mode="json", by_alias=True)
    payload.pop("evaluatedAt")
    expected.pop("evaluatedAt")
    assert payload == expected


def test_readiness_reports_ordered_material_visual_and_revision_recovery():
    repos = V2Repositories()
    package = _generated_package(repos)
    material = repos.generated_materials.for_package(package.id)[0]
    spec = material.materialSpec.model_copy(
        update={
            "revision": material.materialSpec.revision + 1,
            "semantic_validation": MaterialValidationResult(status="failed"),
            "safety_validation": MaterialValidationResult(status="failed"),
        }
    )
    visuals = material.visualAssetPlan.visual_items
    required_failed = visuals[0].model_copy(update={"status": "failed"})
    pending_required = visuals[min(1, len(visuals) - 1)].model_copy(
        update={"status": "planned", "fallback_asset_id": None}
    )
    optional_failed = visuals[-1].model_copy(
        update={"required": False, "status": "failed"}
    )
    plan = material.visualAssetPlan.model_copy(
        update={"visual_items": [required_failed, pending_required, optional_failed]}
    )
    repos.generated_materials.save(
        material.model_copy(
            update={
                "materialSpec": spec,
                "visualAssetPlan": plan,
                "status": "validation_failed",
            }
        )
    )

    result = V2PrintReadinessService(repos).evaluate(package.id)
    categories = [item.category for item in result.blockers]
    assert result.ready is False
    assert "stale_material_revision" in categories
    assert "stale_visual_plan_revision" in categories
    assert "semantic_validation_failure" in categories
    assert "safety_validation_failure" in categories
    assert "failed_required_visual" in categories
    assert "pending_visual" in categories
    assert "failed_optional_visual_with_fallback" in categories
    assert "material_revision_not_reviewed" in categories
    assert "material_revision_not_approved" in categories
    assert "package_not_approved" in categories
    priorities = V2PrintReadinessService._priority
    assert [priorities[item] for item in categories] == sorted(
        priorities[item] for item in categories
    )
    required = next(
        item for item in result.blockers
        if item.category == "failed_required_visual"
    )
    assert required.materialId == material.id
    assert required.visualId == required_failed.id
    assert required.recoveryRoute == "reviewPrintableContent"
    assert required.retryPossible is True


def test_readiness_blocks_ready_visual_when_stored_bytes_are_missing(tmp_path):
    repos = V2Repositories()
    package = _generated_package(repos)
    material = next(
        item
        for item in repos.generated_materials.for_package(package.id)
        if item.visualAssetPlan is not None
    )
    target = material.visualAssetPlan.visual_items[0]
    plan = material.visualAssetPlan.model_copy(
        update={
            "visual_items": [
                target.model_copy(update={"status": "ready"}),
                *material.visualAssetPlan.visual_items[1:],
            ]
        }
    )
    content = {
        **material.content,
        "visualItems": [
            {
                "id": target.id,
                "required": True,
                "generationStatus": "ready",
                "imageAssetId": "missing-durable-asset",
                "imageUrl": "/storage/generated-images/missing.png",
            }
        ],
    }
    repos.generated_materials.save(
        material.model_copy(update={"visualAssetPlan": plan, "content": content})
    )

    result = V2PrintReadinessService(repos).evaluate(package.id)
    blocker = next(
        item
        for item in result.blockers
        if item.category == "storage_download_preparation_failure"
        and item.visualId == target.id
    )

    assert result.ready is False
    assert blocker.materialId == material.id
    assert blocker.recoveryAction == "retry_visual"


def test_readiness_reports_jobs_storage_renderer_and_privacy_safe_text():
    repos = V2Repositories()
    package = _ready_package(repos)
    repos.generation_jobs.save(GenerationJobDto(
        jobId="synthetic-failed-job",
        learnerId=package.learnerId,
        draftId=package.draftId,
        lessonSpecId="legacy-lesson-spec",
        lessonSpecRevision=1,
        packageContentPlanRevision=1,
        packageId=package.id,
        status="failed",
        failureCategory="provider_timeout",
        recoverable=True,
        idempotencyKey="synthetic-readiness-key",
    ))
    manifest = PrintPackageManifest(
        packageId=package.id,
        packageRevision=package.version,
        lessonSpecId="legacy-lesson-spec",
        lessonSpecRevision=1,
        profileRevision=package.profileRevision,
        sections=[PrintPackageManifestSection(
            sectionType="cover", title="Cover"
        )],
        materialRevisions={
            item.id: item.materialSpec.revision if item.materialSpec else item.version
            for item in package.materials
        },
        generatedAt="2026-08-04T00:00:00Z",
        rendererVersion="obsolete-renderer",
        sourceApprovalReadinessEvidence=PrintSourceApprovalReadinessEvidence(
            evaluatedAt="2026-08-04T00:00:00Z",
            ready=True,
            packageApprovalStatus="approved",
            packageRevision=package.version,
            lessonSpecRevision=1,
            materialReviewedRevisions={},
            materialApprovedRevisions={},
        ),
    )
    repos.export_jobs.save(LessonPackageExportJobDto(
        exportId="print-kit-synthetic-failure",
        packageId=package.id,
        status="failed",
        format="pdf",
        printPackageManifest=manifest,
        errorCode="STORAGE_UNAVAILABLE",
    ))

    result = V2PrintReadinessService(repos).evaluate(package.id)
    categories = {item.category for item in result.blockers}
    assert "generation_job_failed" in categories
    assert "storage_download_preparation_failure" in categories
    assert "renderer_manifest_incompatibility" in categories
    assert result.manifestCompatible is False
    serialized = result.model_dump_json().casefold()
    assert package.learnerId.casefold() not in serialized
    assert package.goal.casefold() not in serialized


def test_readiness_distinguishes_incomplete_and_stale_package_boundaries():
    repos = V2Repositories()
    package = _generated_package(repos)
    current = repos.lesson_packages.get(package.id)
    repos.lesson_packages.save(current.model_copy(update={
        "validatedRevision": None,
        "validatedLessonSpecRevision": None,
    }))
    repos.generation_jobs.save(GenerationJobDto(
        jobId="synthetic-incomplete-job",
        learnerId=package.learnerId,
        draftId=package.draftId,
        lessonSpecId=package.lessonSpec.id,
        lessonSpecRevision=package.lessonSpec.revision,
        packageContentPlanRevision=package.packageContentPlan.lesson_spec_revision,
        packageId=package.id,
        status="in_progress",
        idempotencyKey="synthetic-incomplete-key",
    ))

    categories = {
        item.category
        for item in V2PrintReadinessService(repos).evaluate(package.id).blockers
    }
    assert "generation_job_incomplete" in categories
    assert "stale_lesson_spec_revision" in categories
    assert "stale_package_revision" in categories


def test_stale_generation_job_offers_retry_instead_of_permanent_wait():
    repos = V2Repositories()
    package = _generated_package(repos)
    repos.generation_jobs.save(GenerationJobDto(
        jobId="synthetic-stale-job",
        learnerId=package.learnerId,
        draftId=package.draftId,
        lessonSpecId=package.lessonSpec.id,
        lessonSpecRevision=package.lessonSpec.revision,
        packageContentPlanRevision=package.packageContentPlan.lesson_spec_revision,
        packageId=package.id,
        status="in_progress",
        lastUpdatedAt="2020-01-01T00:00:00+00:00",
        idempotencyKey="synthetic-stale-key",
    ))

    blocker = next(
        item for item in V2PrintReadinessService(repos).evaluate(package.id).blockers
        if item.category == "generation_job_incomplete"
    )
    assert blocker.recoveryAction == "retry_generation"
    assert blocker.retryPossible is True


def test_revalidation_persists_current_package_and_lesson_spec_revisions():
    repos = V2Repositories()
    package = _generated_package(repos)
    current = repos.lesson_packages.get(package.id)
    stale = repos.lesson_packages.save(current.model_copy(update={
        "status": "teacher_review_needed",
        "validatedRevision": None,
        "validatedLessonSpecRevision": None,
    }))

    updated = V2LessonPackageService(repos).revalidate_product(stale.id)
    persisted = repos.lesson_packages.get(stale.id)

    assert updated.validationStatus == "passed"
    assert updated.validatedRevision == updated.version
    assert updated.validatedLessonSpecRevision == updated.lessonSpec.revision
    assert persisted.validatedRevision == persisted.version
    assert persisted.status == "teacher_review_needed"
    categories = {
        item.category
        for item in V2PrintReadinessService(repos).evaluate(stale.id).blockers
    }
    assert "stale_lesson_spec_revision" not in categories
    assert "stale_package_revision" not in categories
    assert "package_not_approved" in categories


def test_package_semantic_and_safety_failures_are_separate_categories():
    repos = V2Repositories()
    package = _generated_package(repos)
    current = repos.lesson_packages.get(package.id)
    blocked_review = current.safetyReview.model_copy(update={"status": "blocked"})
    repos.lesson_packages.save(current.model_copy(update={
        "validationStatus": "failed",
        "safetyReview": blocked_review,
    }))

    categories = {
        item.category
        for item in V2PrintReadinessService(repos).evaluate(package.id).blockers
    }
    assert "semantic_validation_failure" in categories
    assert "safety_validation_failure" in categories
