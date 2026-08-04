from __future__ import annotations

import json

import pytest

from app.core.config import Settings
from app.core.exceptions import AIProviderUnavailableError, ConflictError, ValidationError
from app.schemas.v2_dto import LessonDesignDraftDto
from app.services.v2_generation_job_service import V2GenerationJobService
from app.services.v2_generation_observability import emit_generation_metric
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_printable_lesson_kit_service import V2PrintableLessonKitService
from app.services.v2_repositories import V2Repositories
from app.services.v2_session_service import V2SessionService
from app.schemas.v2_dto import SessionCreate


def _config(**updates) -> Settings:
    return Settings(
        _env_file=None,
        APP_ENV="test",
        AI_PROVIDER="mock",
        GENERATION_RETRY_BASE_SECONDS=0,
        **updates,
    )


def _draft(*, version: int = 1) -> LessonDesignDraftDto:
    return LessonDesignDraftDto(
        id="generation-reliability-draft",
        learnerId="a102",
        goalText="Learner will ask for help using a short phrase.",
        observableResponse="Asks for help using a short phrase.",
        responseLevel="Short phrase",
        scenarios=["Toy car stuck", "Closed box", "Missing puzzle piece"],
        selectedMaterials=["Visual Cards", "Data Sheet"],
        theme="Vehicles",
        duration="10 minutes",
        customNotes="",
        version=version,
    )


def test_duplicate_generation_click_reuses_job_package_and_materials():
    repos = V2Repositories()
    service = V2GenerationJobService(repos, config=_config())

    first_job, first_package = service.create_or_resume(_draft())
    second_job, second_package = service.create_or_resume(_draft())

    assert second_job.jobId == first_job.jobId
    assert second_package.id == first_package.id
    assert len(repos.generation_jobs.list()) == 1
    assert len(repos.lesson_packages.list()) == 1
    assert len(repos.generated_materials.list()) == len(first_package.materials)


def test_visual_background_work_has_a_single_winner_claim():
    repos = V2Repositories()
    service = V2GenerationJobService(repos, config=_config())
    job, _ = service.create_or_resume(_draft())

    assert service.claim_visual_work(job.jobId) is True
    assert service.claim_visual_work(job.jobId) is False


class _TimeoutOncePackageService(V2LessonPackageService):
    def __init__(self, repos, config):
        super().__init__(repos, config=config)
        self.calls = 0

    def generate_product(self, draft):
        self.calls += 1
        if self.calls == 1:
            raise AIProviderUnavailableError("Provider timeout")
        return super().generate_product(draft)


def test_provider_timeout_is_retried_with_bounded_backoff():
    repos = V2Repositories()
    config = _config(GENERATION_PROVIDER_MAX_RETRIES=2)
    packages = _TimeoutOncePackageService(repos, config)
    sleeps: list[float] = []
    service = V2GenerationJobService(
        repos, package_service=packages, config=config, sleeper=sleeps.append
    )

    job, package = service.create_or_resume(_draft())

    assert package.id == job.packageId
    assert packages.calls == 2
    assert len(sleeps) == 1
    assert service.get(job.jobId).attempts == 2


class _OneVisualFailurePackageService(V2LessonPackageService):
    fail_visual_id = ""

    def prepare_material_visual(self, material_id, visual_item_id, **kwargs):
        if visual_item_id == self.fail_visual_id:
            raise ConnectionError("temporary image network failure")
        return super().prepare_material_visual(material_id, visual_item_id, **kwargs)


def test_optional_visual_failure_preserves_package_and_only_failed_visual_retries():
    repos = V2Repositories()
    config = _config()
    packages = _OneVisualFailurePackageService(repos, config=config)
    service = V2GenerationJobService(repos, package_service=packages, config=config)
    job, package = service.create_or_resume(_draft())
    target_artifact = next(item for item in job.artifacts if item.visuals)
    target_visual = target_artifact.visuals[0]
    packages.fail_visual_id = target_visual.visualId
    revised_artifacts = [
        item.model_copy(update={
            "visuals": [
                visual.model_copy(update={"required": False})
                if visual.visualId == target_visual.visualId else visual
                for visual in item.visuals
            ]
        })
        for item in job.artifacts
    ]
    repos.generation_jobs.save(job.model_copy(update={"artifacts": revised_artifacts}))

    partial = service.resume(job.jobId)

    assert partial.status == "partially_complete"
    assert repos.lesson_packages.get(package.id) is not None
    failed = next(
        visual
        for artifact in partial.artifacts
        for visual in artifact.visuals
        if visual.visualId == target_visual.visualId
    )
    assert failed.status == "failed" and failed.recoverable is True
    untouched_attempts = [
        visual.attempts
        for artifact in partial.artifacts
        for visual in artifact.visuals
        if visual.visualId != target_visual.visualId
    ]
    packages.fail_visual_id = ""
    recovered = service.retry_visual(job.jobId, target_visual.visualId)
    assert recovered.status == "completed"
    assert [
        visual.attempts
        for artifact in recovered.artifacts
        for visual in artifact.visuals
        if visual.visualId != target_visual.visualId
    ] == untouched_attempts


class _RepairExhaustedPackageService(V2LessonPackageService):
    def generate_product(self, draft):
        raise ValidationError("MaterialSpec repair exhausted; teacher action is required")


def test_repair_exhaustion_is_not_retried_and_fails_closed():
    repos = V2Repositories()
    config = _config(GENERATION_PROVIDER_MAX_RETRIES=3)
    service = V2GenerationJobService(
        repos,
        package_service=_RepairExhaustedPackageService(repos, config=config),
        config=config,
    )

    with pytest.raises(ValidationError, match="repair exhausted"):
        service.create_or_resume(_draft())

    job = repos.generation_jobs.list()[0]
    assert job.status == "failed"
    assert job.failureCategory == "repair_exhausted"
    assert job.recoverable is False
    assert job.attempts == 1


def test_revision_change_creates_new_job_and_stale_job_is_rejected():
    repos = V2Repositories()
    service = V2GenerationJobService(repos, config=_config())
    first, _ = service.create_or_resume(_draft(version=1))
    second, _ = service.create_or_resume(_draft(version=2))
    assert first.jobId != second.jobId

    stale = service.get(first.jobId)
    repos.generation_jobs.save(
        stale.model_copy(update={"lessonSpecRevision": stale.lessonSpecRevision + 1})
    )
    with pytest.raises(ConflictError, match="stale"):
        service.resume(first.jobId)
    assert service.get(first.jobId).failureCategory == "stale_job"
    assert service.get(first.jobId).recoverable is False


def test_cost_limits_fail_before_provider_or_package_creation():
    repos = V2Repositories()
    service = V2GenerationJobService(
        repos, config=_config(MAX_MATERIALS_PER_PACKAGE=1)
    )
    with pytest.raises(ValidationError, match="material limit"):
        service.create_or_resume(_draft())
    assert repos.lesson_packages.list() == []
    assert repos.generation_jobs.list() == []


class _FlakyStorage:
    def __init__(self):
        self.calls = 0

    def write_bytes(self, key, body, content_type):
        self.calls += 1
        if self.calls < 3:
            raise OSError("temporary storage outage")


def test_storage_upload_has_bounded_retry_without_regenerating_materials():
    storage = _FlakyStorage()
    service = V2PrintableLessonKitService(
        V2Repositories(), storage=storage, config=_config(GENERATION_STORAGE_MAX_RETRIES=2)
    )
    service._write_with_retry("safe/test.pdf", b"%PDF-test")
    assert storage.calls == 3


def test_generation_metrics_redact_sensitive_content(caplog):
    caplog.set_level("INFO", logger="app.generation")
    emit_generation_metric(
        "ProviderFailureCount",
        1,
        stage="planning",
        provider="openai",
        status="failed",
        prompt="secret learner prompt",
        record_text="private record",
        learner_code="N-999",
        failure_category="provider_timeout",
    )
    payload = json.loads(caplog.records[-1].message)
    assert payload["prompt"] == payload["record_text"] == payload["learner_code"] == "[REDACTED]"
    assert "secret learner prompt" not in caplog.text
    assert "private record" not in caplog.text


def test_duplicate_session_click_reuses_explicit_idempotency_key():
    repos = V2Repositories()
    service = V2SessionService(repos)
    request = SessionCreate(
        learnerId="a102",
        goal="Ask for help",
        status="planned",
        idempotencyKey="package-1:revision-3:planned-session",
    )
    first = service.create(request)
    second = service.create(request)
    assert second.id == first.id
    assert len([
        item for item in repos.sessions.list()
        if item.idempotency_key == request.idempotency_key
    ]) == 1
