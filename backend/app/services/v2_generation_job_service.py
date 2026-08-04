from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
import logging
from threading import RLock
import time
from typing import Callable, TypeVar

from sqlalchemy.exc import IntegrityError

from app.core.config import Settings, settings
from app.core.exceptions import (
    AIProviderUnavailableError,
    AuthenticationError,
    ConflictError,
    ForbiddenError,
    ObjectStorageUnavailableError,
    SafetyDeferralError,
    ValidationError,
)
from app.schemas.v2_dto import (
    GenerationArtifactState,
    GenerationCostMetadata,
    GenerationJobDto,
    GenerationStageState,
    GenerationVisualState,
    LessonDesignDraftDto,
    LessonPackageDto,
    utc_now,
)
from app.services.v2_generation_observability import emit_generation_metric
from app.services.v2_lesson_package_service import V2LessonPackageService
from app.services.v2_repositories import V2Repositories, repositories


logger = logging.getLogger(__name__)
T = TypeVar("T")
_CREATE_LOCK = RLock()

STAGES = (
    "planning",
    "material_specification",
    "semantic_validation",
    "repair",
    "visual_planning",
    "image_generation",
    "rendering",
    "safety_validation",
    "pdf_composition",
    "artifact_upload",
    "download_readiness",
)


def _iso() -> str:
    return utc_now().isoformat()


class V2GenerationJobService:
    """Durable, revision-aware orchestration around the existing package pipeline.

    The package and every completed visual remain canonical repository records.
    Retrying a job only executes unfinished work and never discards those records.
    """

    def __init__(
        self,
        repos: V2Repositories = repositories,
        package_service: V2LessonPackageService | None = None,
        config: Settings = settings,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.repos = repos
        self.config = config
        self.packages = package_service or V2LessonPackageService(repos, config=config)
        self._sleep = sleeper

    def create_or_resume(
        self, draft: LessonDesignDraftDto
    ) -> tuple[GenerationJobDto, LessonPackageDto]:
        lesson_spec = self.packages._lesson_spec_for_content_plan(draft)
        plan = draft.packageContentPlan or self.packages.content_plans.build(lesson_spec)
        plan = self.packages.content_plans.validate(plan, lesson_spec)
        key = self._idempotency_key(draft, lesson_spec.revision, plan)
        existing = self._by_key(key)
        if existing and existing.packageId:
            package = self.repos.lesson_packages.get(existing.packageId)
            if isinstance(package, LessonPackageDto):
                if existing.status == "failed" and not existing.recoverable:
                    raise ConflictError(
                        "This generation revision failed with a non-recoverable error; revise the lesson before retrying."
                    )
                return existing, package
        if existing and not existing.packageId and existing.status == "in_progress":
            age_seconds = (
                datetime.fromisoformat(_iso())
                - datetime.fromisoformat(existing.lastUpdatedAt)
            ).total_seconds()
            if age_seconds < self.config.GENERATION_STALE_JOB_SECONDS:
                raise ConflictError(
                    f"Generation job {existing.jobId} is already running; follow its progress instead of starting a duplicate."
                )

        if existing is None:
            with _CREATE_LOCK:
                # A second check closes the duplicate-click race in local mode.
                # The database uniqueness constraint closes the cross-process race.
                existing = self._by_key(key)
                if existing is None:
                    self._enforce_preflight_limits(draft, plan.estimated_artifact_count)
                    provider = getattr(self.packages.ai, "provider_name", "unknown")
                    estimated_tokens = self._estimated_tokens(draft, plan.estimated_artifact_count)
                    job = GenerationJobDto(
                        jobId=self.repos.next_id("generation-job"),
                        learnerId=draft.learnerId,
                        draftId=draft.id,
                        lessonSpecId=lesson_spec.id,
                        lessonSpecRevision=lesson_spec.revision,
                        packageContentPlanRevision=plan.lesson_spec_revision,
                        provider=provider,
                        model=self._configured_model(provider),
                        idempotencyKey=key,
                        stages=[GenerationStageState(stage=stage) for stage in STAGES],
                        cost=GenerationCostMetadata(
                            estimatedTokens=estimated_tokens,
                            estimatedCost=(
                                estimated_tokens / 1000
                                * self.config.GENERATION_ESTIMATED_TEXT_COST_PER_1K_TOKENS
                            ),
                        ),
                    )
                    try:
                        job = self.repos.generation_jobs.save(job)
                    except IntegrityError:
                        existing = self._by_key(key)
                        if existing is None:
                            raise
                if existing is not None:
                    job = existing
        else:
            job = existing

        job = self._stage(job, "planning", "in_progress", "Building the revision-locked lesson plan.")
        try:
            package = self._retry(
                lambda: self.packages.generate_product(
                    draft.model_copy(update={"packageContentPlan": plan})
                ),
                attempts=self.config.GENERATION_PROVIDER_MAX_RETRIES,
                retry_categories={"provider_timeout", "rate_limit", "temporary_network"},
                on_attempt=lambda attempt: self._increment_attempt(job.jobId, attempt),
            )
        except Exception as exc:
            category, recoverable = self._classify_failure(exc)
            self._fail_job(job.jobId, "planning", category, recoverable)
            raise

        job = self.get(job.jobId)
        job = job.model_copy(
            update={
                "packageId": package.id,
                "requestedArtifactIds": [item.id for item in package.materials],
                "artifacts": self._artifact_states(package),
                "status": "in_progress",
                "startedAt": job.startedAt or _iso(),
                "lastUpdatedAt": _iso(),
            }
        )
        job = self.repos.generation_jobs.save(job)
        visual_count = sum(len(item.visuals) for item in job.artifacts)
        if len(job.artifacts) > self.config.MAX_MATERIALS_PER_PACKAGE:
            self._fail_job(job.jobId, "material_specification", "material_limit", False)
            raise ValidationError("The package exceeds the configured material limit.")
        if visual_count > self.config.MAX_AI_VISUALS_PER_PACKAGE:
            self._fail_job(job.jobId, "visual_planning", "visual_cost_limit", False)
            raise ValidationError("The package exceeds the configured AI visual limit.")
        job = self.get(job.jobId)
        job = job.model_copy(
            update={
                "cost": job.cost.model_copy(update={"estimatedVisualCount": visual_count}),
            }
        )
        job = self.repos.generation_jobs.save(job)
        for stage, message in (
            ("planning", "Lesson planning is complete."),
            ("material_specification", "Typed material specifications are complete."),
            ("semantic_validation", "Semantic validation passed."),
            ("repair", "No unfinished repair work remains."),
            ("visual_planning", "Visual plans are ready."),
            ("rendering", "Deterministic material previews are ready."),
            ("safety_validation", "Safety validation passed."),
        ):
            job = self._stage(job, stage, "completed", message)
        if visual_count == 0:
            job = self._stage(job, "image_generation", "skipped", "No AI visuals are required.")
            job = self._finish_generation(job)
        return job, package

    def resume(self, job_id: str, *, only_visual_id: str | None = None) -> GenerationJobDto:
        job = self.get(job_id)
        if not job.packageId:
            raise ConflictError("The generation job has not produced a package yet.")
        package = self.packages.get_product(job.packageId)
        if (
            package.lessonSpec is None
            or package.lessonSpec.id != job.lessonSpecId
            or package.lessonSpec.revision != job.lessonSpecRevision
        ):
            self._fail_job(job.jobId, "image_generation", "stale_job", False)
            raise ConflictError("The generation job is stale for the current LessonSpec revision.")
        image_stage = next(item for item in job.stages if item.stage == "image_generation")
        if image_stage.status != "in_progress":
            job = self._stage(job, "image_generation", "in_progress", "Creating remaining instructional visuals.")
        actual_visuals = job.cost.actualVisualCount
        required_failure = False
        optional_failure = False
        for artifact in job.artifacts:
            if not artifact.visuals:
                continue
            current_artifact = artifact
            for visual in artifact.visuals:
                if only_visual_id and visual.visualId != only_visual_id:
                    continue
                if not only_visual_id and visual.status in {"completed", "fallback"}:
                    continue
                try:
                    updated = self.packages.prepare_material_visual(
                        artifact.artifactId, visual.visualId, force_generation=visual.attempts > 0
                    )
                    updated_item = next(
                        item for item in updated.visualAssetPlan.visual_items
                        if item.id == visual.visualId
                    )
                    used_fallback = updated_item.status == "failed" and bool(updated_item.fallback_asset_id)
                    next_visual = visual.model_copy(update={
                        "status": "fallback" if used_fallback else "completed",
                        "attempts": visual.attempts + (
                            self.config.VISUAL_IMAGE_MAX_RETRIES + 1
                            if used_fallback else 1
                        ),
                        "fallbackAssetId": updated_item.fallback_asset_id,
                        "failureCategory": (
                            str(updated_item.design_constraints.get("failureReason") or "provider_failure")
                            if used_fallback else None
                        ),
                        "recoverable": True,
                    })
                    actual_visuals += 1
                except Exception as exc:
                    category, recoverable = self._classify_failure(exc)
                    next_visual = visual.model_copy(update={
                        "status": "failed",
                        "attempts": visual.attempts + 1,
                        "failureCategory": category,
                        "recoverable": recoverable,
                    })
                    if visual.required:
                        required_failure = True
                    else:
                        optional_failure = True
                current_artifact = current_artifact.model_copy(update={
                    "visuals": [next_visual if item.visualId == visual.visualId else item for item in current_artifact.visuals]
                })
                job = self.get(job.jobId).model_copy(update={
                    "artifacts": [current_artifact if item.artifactId == artifact.artifactId else item for item in self.get(job.jobId).artifacts],
                    "lastUpdatedAt": _iso(),
                    "cost": self.get(job.jobId).cost.model_copy(update={"actualVisualCount": actual_visuals}),
                })
                job = self.repos.generation_jobs.save(job)
            statuses = {item.status for item in current_artifact.visuals}
            artifact_status = "failed" if "failed" in statuses else "fallback" if "fallback" in statuses else "completed"
            job = self.get(job.jobId)
            job = self.repos.generation_jobs.save(job.model_copy(update={
                "artifacts": [
                    current_artifact.model_copy(update={"status": artifact_status})
                    if item.artifactId == artifact.artifactId else item
                    for item in job.artifacts
                ]
            }))
        job = self.get(job.jobId)
        if required_failure:
            return self._fail_job(job.jobId, "image_generation", "required_visual_failure", True)
        if optional_failure:
            job = self._stage(job, "image_generation", "fallback", "Optional visuals failed; completed work and approved fallbacks were preserved.")
            return self._finish_generation(job, partial=True)
        job = self._stage(job, "image_generation", "completed", "All required visuals are ready or have approved fallbacks.")
        return self._finish_generation(job)

    def retry_visual(self, job_id: str, visual_id: str) -> GenerationJobDto:
        job = self.get(job_id)
        found = False
        artifacts = []
        for artifact in job.artifacts:
            visuals = []
            for visual in artifact.visuals:
                if visual.visualId == visual_id:
                    found = True
                    if not visual.recoverable:
                        raise ConflictError("This visual failure is not retryable.")
                    visual = visual.model_copy(update={"status": "pending", "failureCategory": None})
                visuals.append(visual)
            artifacts.append(artifact.model_copy(update={"visuals": visuals}))
        if not found:
            raise ValidationError("The visual is not part of this generation job.")
        self.repos.generation_jobs.save(job.model_copy(update={
            "artifacts": artifacts, "status": "in_progress", "lastUpdatedAt": _iso()
        }))
        return self.resume(job_id, only_visual_id=visual_id)

    def claim_visual_work(self, job_id: str) -> bool:
        """Claim pending visual work before it is handed to a background worker.

        Repository version checks make this a single-winner claim across API
        processes; duplicate requests observe in-progress work and do not queue it.
        """

        job = self.get(job_id)
        stage = next(item for item in job.stages if item.stage == "image_generation")
        if stage.status != "pending":
            return False
        self._stage(
            job, "image_generation", "in_progress",
            "Instructional visual generation is queued.",
        )
        return True

    def get(self, job_id: str) -> GenerationJobDto:
        job = self.repos.generation_jobs.get(job_id)
        if not isinstance(job, GenerationJobDto):
            raise ValidationError("Generation job not found.")
        return job

    def for_package(self, package_id: str) -> GenerationJobDto:
        jobs = [item for item in self.repos.generation_jobs.list() if item.packageId == package_id]
        if not jobs:
            raise ValidationError("Generation job not found for this package.")
        return jobs[-1]

    def mark_pdf_stage(
        self, package_id: str, stage: str, status: str, message: str,
        *, failure_category: str | None = None, recoverable: bool = True,
    ) -> GenerationJobDto | None:
        jobs = [item for item in self.repos.generation_jobs.list() if item.packageId == package_id]
        if not jobs:
            return None
        job = jobs[-1]
        if status == "failed":
            return self._fail_job(
                job.jobId,
                stage,
                failure_category or "stage_failure",
                recoverable,
            )
        saved = self._stage(
            job, stage, status, message,
            failure_category=failure_category, recoverable=recoverable,
        )
        if stage == "download_readiness" and status == "completed":
            saved = self.repos.generation_jobs.save(saved.model_copy(update={
                "status": "completed",
                "completedAt": _iso(),
                "failureCategory": None,
                "recoverable": False,
                "lastUpdatedAt": _iso(),
            }))
        return saved

    def _finish_generation(self, job: GenerationJobDto, partial: bool = False) -> GenerationJobDto:
        saved = self.repos.generation_jobs.save(job.model_copy(update={
            "status": "partially_complete" if partial else "completed",
            "completedAt": _iso(),
            "lastUpdatedAt": _iso(),
            "failureCategory": "optional_visual_failure" if partial else None,
            "recoverable": partial,
        }))
        emit_generation_metric(
            "PackageCount", 1, provider=saved.provider,
            status=saved.status, environment=self.config.APP_ENV,
            artifact_count=len(saved.artifacts),
            visual_count=saved.cost.actualVisualCount,
            estimated_cost=saved.cost.estimatedCost,
        )
        emit_generation_metric(
            "ArtifactsPerPackage", len(saved.artifacts), provider=saved.provider,
            status=saved.status, environment=self.config.APP_ENV,
        )
        emit_generation_metric(
            "VisualsPerPackage", saved.cost.actualVisualCount, provider=saved.provider,
            status=saved.status, environment=self.config.APP_ENV,
        )
        emit_generation_metric(
            "EstimatedCostPerPackage", saved.cost.estimatedCost, unit="None",
            provider=saved.provider, status=saved.status, environment=self.config.APP_ENV,
        )
        fallback_count = sum(
            1 for artifact in saved.artifacts for visual in artifact.visuals
            if visual.status == "fallback"
        )
        if fallback_count:
            emit_generation_metric(
                "FallbackUseCount", fallback_count, stage="image_generation",
                provider=saved.provider, status=saved.status,
                environment=self.config.APP_ENV,
            )
        if saved.packageId:
            package = self.repos.lesson_packages.get(saved.packageId)
            material_specs = [
                item.materialSpec for item in getattr(package, "materials", [])
                if item.materialSpec is not None
            ]
            repaired = sum(1 for spec in material_specs if spec.repair_attempts > 0)
            attempts = sum(spec.repair_attempts for spec in material_specs)
            emit_generation_metric(
                "RepairAttemptCount", attempts, stage="repair",
                provider=saved.provider, status=saved.status,
                environment=self.config.APP_ENV,
            )
            emit_generation_metric(
                "RepairRate", (repaired / len(material_specs) * 100) if material_specs else 0,
                unit="Percent", stage="repair", provider=saved.provider,
                status=saved.status, environment=self.config.APP_ENV,
            )
        return saved

    def _stage(
        self, job: GenerationJobDto, stage: str, status: str, message: str,
        *, failure_category: str | None = None, recoverable: bool = True,
    ) -> GenerationJobDto:
        now = _iso()
        stages = []
        for current in job.stages:
            if current.stage != stage:
                stages.append(current)
                continue
            started = current.startedAt or (now if status == "in_progress" else None)
            duration_ms = current.durationMs
            if started and status in {"completed", "failed", "fallback", "skipped"}:
                duration_ms = max(
                    0,
                    int((datetime.fromisoformat(now) - datetime.fromisoformat(started)).total_seconds() * 1000),
                )
            stages.append(current.model_copy(update={
                "status": status,
                "attempts": current.attempts + (1 if status == "in_progress" else 0),
                "startedAt": started,
                "updatedAt": now,
                "completedAt": now if status in {"completed", "failed", "fallback", "skipped"} else None,
                "durationMs": duration_ms,
                "failureCategory": failure_category,
                "recoverable": recoverable,
                "message": message,
            }))
        saved = self.repos.generation_jobs.save(job.model_copy(update={
            "stages": stages,
            "status": "in_progress" if status == "in_progress" else job.status,
            "startedAt": job.startedAt or (now if status == "in_progress" else None),
            "lastUpdatedAt": now,
        }))
        emit_generation_metric(
            "StageEventCount", 1, stage=stage, provider=saved.provider,
            status=status, environment=self.config.APP_ENV,
        )
        completed_stage = next(item for item in saved.stages if item.stage == stage)
        if completed_stage.durationMs is not None and status in {"completed", "failed", "fallback", "skipped"}:
            emit_generation_metric(
                "StageDuration", completed_stage.durationMs, unit="Milliseconds",
                stage=stage, provider=saved.provider, status=status,
                environment=self.config.APP_ENV,
            )
        failure_metrics = {
            "semantic_validation": "SemanticValidationFailureCount",
            "image_generation": "ImageGenerationFailureCount",
            "pdf_composition": "PDFGenerationFailureCount",
            "artifact_upload": "StorageUploadFailureCount",
            "download_readiness": "PDFDownloadFailureCount",
        }
        if status == "failed":
            emit_generation_metric(
                failure_metrics.get(stage, "ProviderFailureCount"), 1,
                stage=stage, provider=saved.provider, status=status,
                environment=self.config.APP_ENV,
                failure_category=failure_category,
            )
        return saved

    def _fail_job(self, job_id: str, stage: str, category: str, recoverable: bool) -> GenerationJobDto:
        job = self.get(job_id)
        job = self._stage(
            job, stage, "failed", "This stage needs attention before generation can continue.",
            failure_category=category, recoverable=recoverable,
        )
        return self.repos.generation_jobs.save(job.model_copy(update={
            "status": "failed", "failureCategory": category,
            "recoverable": recoverable, "lastUpdatedAt": _iso(),
        }))

    def _increment_attempt(self, job_id: str, attempt: int) -> None:
        job = self.get(job_id)
        self.repos.generation_jobs.save(job.model_copy(update={
            "attempts": max(job.attempts, attempt), "lastUpdatedAt": _iso()
        }))

    def _retry(
        self, operation: Callable[[], T], *, attempts: int,
        retry_categories: set[str], on_attempt: Callable[[int], None],
    ) -> T:
        last: Exception | None = None
        for attempt in range(attempts + 1):
            on_attempt(attempt + 1)
            try:
                return operation()
            except Exception as exc:
                last = exc
                category, recoverable = self._classify_failure(exc)
                if not recoverable or category not in retry_categories or attempt >= attempts:
                    raise
                self._sleep(self.config.GENERATION_RETRY_BASE_SECONDS * (2**attempt))
        raise last or RuntimeError("Generation retry failed")

    def _by_key(self, key: str) -> GenerationJobDto | None:
        return next(
            (item for item in self.repos.generation_jobs.list() if item.idempotencyKey == key),
            None,
        )

    @staticmethod
    def _idempotency_key(draft, lesson_spec_revision: int, plan) -> str:
        payload = {
            "learner": draft.learnerId,
            "draft": draft.id,
            "draftVersion": draft.version,
            "profileRevision": draft.profileRevision,
            "lessonSpecRevision": lesson_spec_revision,
            "planRevision": plan.lesson_spec_revision,
            "core": [item.material_type for item in plan.teacher_selected_core],
            "companions": [item.material_type for item in plan.required_companions if item.included],
            "optionals": [item.material_type for item in plan.optional_enrichments if item.default_included],
            "decisionRevisions": sorted((item.id, item.revision) for item in draft.decisions),
        }
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _enforce_preflight_limits(self, draft: LessonDesignDraftDto, planned_count: int) -> None:
        if planned_count > self.config.MAX_MATERIALS_PER_PACKAGE:
            raise ValidationError("The package exceeds the configured material limit.")
        estimate = self._estimated_tokens(draft, planned_count)
        if estimate > self.config.MAX_PACKAGE_TOKEN_BUDGET:
            raise ValidationError("The package exceeds the configured token budget.")

    @staticmethod
    def _estimated_tokens(draft: LessonDesignDraftDto, planned_count: int) -> int:
        text_size = len(draft.teacherRequest or "") + len(draft.goalText or "") + len(draft.customNotes or "")
        return max(1000, text_size // 4 + planned_count * 1200)

    def _configured_model(self, provider: str) -> str:
        if provider == "openai":
            return self.config.OPENAI_PACKAGE_MODEL
        if provider == "azure_openai":
            return self.config.AZURE_OPENAI_TEXT_DEPLOYMENT or self.config.AZURE_OPENAI_DEPLOYMENT or ""
        return "deterministic-local-mock"

    @staticmethod
    def _artifact_states(package: LessonPackageDto) -> list[GenerationArtifactState]:
        states = []
        for material in package.materials:
            visuals = []
            if material.visualAssetPlan is not None:
                visuals = [GenerationVisualState(
                    visualId=item.id,
                    semanticKey=item.semantic_key,
                    required=item.required,
                    provider=(material.generationMetadata.provider if material.generationMetadata else ""),
                    model=(material.generationMetadata.model if material.generationMetadata else ""),
                    fallbackAssetId=item.fallback_asset_id,
                ) for item in material.visualAssetPlan.visual_items if item.generation_method == "ai_generated"]
            states.append(GenerationArtifactState(
                artifactId=material.id,
                materialType=material.type,
                status="pending" if visuals else "completed",
                visuals=visuals,
            ))
        return states

    @staticmethod
    def _classify_failure(exc: Exception) -> tuple[str, bool]:
        if isinstance(exc, (AuthenticationError, ForbiddenError)):
            return "authorization", False
        if isinstance(exc, SafetyDeferralError):
            return "prohibited_content", False
        if isinstance(exc, ValidationError):
            text = str(exc).casefold()
            if "repair exhausted" in text:
                return "repair_exhausted", False
            if "unsupported" in text:
                return "unsupported_material", False
            if "limit" in text or "budget" in text:
                return "cost_limit", False
            return "semantic_validation", False
        if isinstance(exc, ObjectStorageUnavailableError):
            return "storage_unavailable", True
        if isinstance(exc, AIProviderUnavailableError):
            text = str(exc).casefold()
            if "rate" in text:
                return "rate_limit", True
            if "timeout" in text or "timed out" in text:
                return "provider_timeout", True
            return "temporary_network", True
        if isinstance(exc, (TimeoutError, ConnectionError)):
            return "provider_timeout" if isinstance(exc, TimeoutError) else "temporary_network", True
        return type(exc).__name__, False
