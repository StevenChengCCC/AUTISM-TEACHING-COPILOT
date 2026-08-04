from __future__ import annotations

from base64 import b64decode
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html import escape as html_escape
from io import BytesIO
from pathlib import Path
import re
import time
from typing import Any
from uuid import uuid4

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.graphics.shapes import Circle, Drawing, Line, Path as GraphicsPath, Polygon, Rect
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from pypdf import PdfReader, PdfWriter

from app.core.config import Settings, settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ObjectStorageUnavailableError,
    ValidationError,
)
from app.integrations.private_object_storage import (
    PrivateObjectStorage,
    get_private_object_storage,
)
from app.schemas.v2_dto import (
    GeneratedMaterialDto,
    HandoffExportDownloadDto,
    LessonPackageDto,
    LessonPackageExportJobDto,
    PrintPackageManifest,
    PrintPackageManifestExclusion,
    PrintPackageManifestSection,
    PrintSourceApprovalReadinessEvidence,
    PrintableLessonKitArtifactDto,
    PrintableLessonKitRequest,
)
from app.services.v2_package_content_plan_service import V2PackageContentPlanService
from app.services.v2_classroom_run_sheet_service import V2ClassroomRunSheetService
from app.services.v2_print_readiness_service import V2PrintReadinessService
from app.services.v2_print_preset_service import (
    PrintPresetResolution,
    V2PrintPresetService,
)
from app.services.v2_print_layout_policy import (
    normalize_print_text,
    print_layout_policy,
)
from app.services.v2_repositories import V2Repositories, repositories


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def escape(value: object) -> str:
    """Normalize printable glyphs before applying HTML escaping."""

    return html_escape(normalize_print_text(value))


class V2PrintableLessonKitService:
    """Build one classroom-ready PDF instead of a data handoff ZIP."""

    renderer_version = "print-package-reportlab-v4-accessible-text"

    def __init__(
        self,
        repos: V2Repositories = repositories,
        storage: PrivateObjectStorage | None = None,
        config: Settings = settings,
    ) -> None:
        self.repos = repos
        self.storage = storage or get_private_object_storage(config)
        self.config = config

    def create(
        self, package_id: str, request: PrintableLessonKitRequest
    ) -> LessonPackageExportJobDto:
        package = self._package(package_id)
        preset_service = V2PrintPresetService(self.repos)
        resolution = preset_service.resolve(
            package, request.printPreset, request.materialIds
        )
        preset_service.require_available(resolution)
        materials = self._validated_materials(package, resolution.materials)

        manifest = self.build_manifest(
            package,
            materials,
            resolution=resolution,
            print_preset=request.printPreset,
            page_size=request.pageSize,
            locale=request.locale,
            table_of_contents=request.tableOfContents,
            page_numbers=request.pageNumbers,
            text_profile=request.textProfile,
        )

        created = _now()
        job = LessonPackageExportJobDto(
            exportId=f"print-kit-{uuid4()}",
            learnerId=package.learnerId,
            packageId=package.id,
            status="processing",
            format="pdf",
            progressPercent=20,
            requestedAt=_iso(created),
            startedAt=_iso(created),
            expiresAt=_iso(
                created + timedelta(days=self.config.EXPORT_RETENTION_DAYS)
            ),
            fileName=self._artifact_filename(
                package, request.printPreset, request.pageSize, request.textProfile
            ),
            message=f"Building the {resolution.display_name} PDF.",
        )
        self.repos.export_jobs.save(job)
        key: str | None = None
        active_stage = "pdf_composition"
        self._mark_generation_stage(
            package.id, active_stage, "in_progress", f"Composing the approved {resolution.display_name} PDF."
        )
        try:
            body = self._build_pdf(
                package, materials, request.pageSize, manifest=manifest
            )
            page_count = self._validate_pdf_artifact(
                body, package, materials, manifest, job.fileName
            )
            manifest = manifest.model_copy(update={"pageCount": page_count})
            if len(body) > min(self.config.MAX_EXPORT_BYTES, self.config.MAX_PDF_BYTES):
                raise ValidationError("The printable lesson kit is too large.")
            self._mark_generation_stage(
                package.id, active_stage, "completed", "PDF composition passed integrity checks."
            )
            active_stage = "artifact_upload"
            self._mark_generation_stage(
                package.id, active_stage, "in_progress", "Uploading the complete PDF artifact."
            )
            key = self._object_key()
            self._write_with_retry(key, body)
            completed = job.model_copy(
                update={
                    "status": "completed",
                    "progressPercent": 100,
                    "completedAt": _iso(_now()),
                    "fileSizeBytes": len(body),
                    "pageCount": page_count,
                    "artifactSha256": sha256(body).hexdigest(),
                    "storageObjectKey": key,
                    "printPackageManifest": manifest,
                    "manifest": [
                        *[section.title for section in manifest.sections],
                        *[f"material:{item.id}:{item.title}" for item in materials],
                    ],
                    "message": f"{resolution.display_name} PDF is ready.",
                }
            )
            saved = self.repos.export_jobs.save(completed)
            self._mark_generation_stage(
                package.id, active_stage, "completed", "The complete PDF artifact is stored."
            )
            self._mark_generation_stage(
                package.id, "download_readiness", "completed", "The signed PDF download is ready."
            )
            return saved
        except Exception as exc:
            if key:
                try:
                    self.storage.delete(key)
                except Exception:
                    pass
            self.repos.export_jobs.save(
                job.model_copy(
                    update={
                        "status": "failed",
                        "progressPercent": 0,
                        "errorCode": "PRINTABLE_KIT_GENERATION_FAILED",
                        "message": "The printable lesson kit could not be generated.",
                    }
                )
            )
            self._mark_generation_stage(
                package.id,
                active_stage,
                "failed",
                "The PDF stage failed; completed materials were preserved for retry.",
                failure_category=(
                    "storage_unavailable"
                    if active_stage == "artifact_upload"
                    else "pdf_generation_failure"
                ),
                recoverable=not isinstance(exc, ValidationError),
            )
            raise

    def _validated_materials(
        self,
        package: LessonPackageDto,
        materials: list[GeneratedMaterialDto],
    ) -> list[GeneratedMaterialDto]:
        if package.status != "approved":
            raise ConflictError("Approve the lesson package before creating a print kit.")
        if package.validationPolicy == "strict_v1":
            if package.validationStatus != "passed" or package.validatedRevision != package.version:
                raise ConflictError("The current package revision has not passed validation.")
            if package.lessonSpec is None or package.validatedLessonSpecRevision != package.lessonSpec.revision:
                raise ConflictError("The package was not validated against the current LessonSpec revision.")
            if any(item.blocking for item in package.lessonSpec.unresolved_assumptions):
                raise ConflictError("Resolve blocking LessonSpec assumptions before printing.")
        materials = self._ordered_materials(materials)
        unapproved = [item.title for item in materials if item.status != "approved"]
        if unapproved:
            raise ConflictError(
                "Approve all selected materials before printing: "
                + ", ".join(unapproved)
            )
        if package.validationPolicy == "strict_v1":
            invalid_revisions = [
                item.title for item in materials
                if item.materialSchemaVersion != 1
                or item.materialSpec is None
                or item.materialSpec.semantic_validation.status != "passed"
                or item.materialSpec.safety_validation.status != "passed"
                or item.materialSpec.approval.status != "approved"
                or item.materialSpec.approval.reviewed_revision != item.materialSpec.revision
                or item.materialSpec.approval.approved_revision != item.materialSpec.revision
            ]
            if invalid_revisions:
                raise ConflictError(
                    "Every selected current material revision must be validated, reviewed, and approved before printing: "
                    + ", ".join(invalid_revisions)
                )
        incomplete_visuals = [
            item.title
            for item in materials
            if not self._has_complete_visual_set(item)
        ]
        if incomplete_visuals:
            raise ConflictError(
                "Every planned classroom visual must be ready before printing: "
                + ", ".join(incomplete_visuals)
            )
        unresolved_visuals = [
            item.title
            for item in materials
            if not self._has_resolvable_visual_set(item)
        ]
        if unresolved_visuals:
            raise ConflictError(
                "Every required classroom visual must resolve before printing: "
                + ", ".join(unresolved_visuals)
            )
        readiness = V2PrintReadinessService(self.repos).evaluate(package.id)
        blocking = [item for item in readiness.blockers if item.severity == "blocking"]
        if blocking:
            first = blocking[0]
            raise ConflictError(
                f"Printing is blocked ({first.blockerId}): {first.explanation}"
            )
        return materials

    def create_artifact(
        self,
        package_id: str,
        request: PrintableLessonKitRequest,
    ) -> PrintableLessonKitArtifactDto:
        package = self._package(package_id)
        preset_service = V2PrintPresetService(self.repos)
        resolution = preset_service.resolve(
            package, request.printPreset, request.materialIds
        )
        preset_service.require_available(resolution)
        materials = self._validated_materials(package, resolution.materials)
        reusable = self._find_reusable_artifact(package, materials, request)
        job = reusable or self.create(package_id, request)
        if reusable is not None:
            self._mark_generation_stage(
                package.id, "download_readiness", "completed",
                "A revision-matched complete PDF artifact was reused."
            )
        return self._artifact_metadata(job, reused=reusable is not None)

    def _write_with_retry(self, key: str, body: bytes) -> None:
        last: Exception | None = None
        for attempt in range(self.config.GENERATION_STORAGE_MAX_RETRIES + 1):
            try:
                self.storage.write_bytes(key, body, "application/pdf")
                return
            except Exception as exc:
                last = exc
                if attempt >= self.config.GENERATION_STORAGE_MAX_RETRIES:
                    raise ObjectStorageUnavailableError(
                        "The PDF could not be stored after bounded retries."
                    ) from exc
                time.sleep(self.config.GENERATION_RETRY_BASE_SECONDS * (2**attempt))
        raise last or ObjectStorageUnavailableError("The PDF could not be stored.")

    def _mark_generation_stage(
        self,
        package_id: str,
        stage: str,
        status: str,
        message: str,
        *,
        failure_category: str | None = None,
        recoverable: bool = True,
    ) -> None:
        from app.services.v2_generation_job_service import V2GenerationJobService

        V2GenerationJobService(self.repos, config=self.config).mark_pdf_stage(
            package_id,
            stage,
            status,
            message,
            failure_category=failure_category,
            recoverable=recoverable,
        )

    def create_download(self, export_id: str) -> HandoffExportDownloadDto:
        job = self.repos.export_jobs.get(export_id)
        if (
            not isinstance(job, LessonPackageExportJobDto)
            or job.format != "pdf"
            or not job.exportId.startswith("print-kit-")
        ):
            raise NotFoundError("Printable lesson kit not found")
        artifact = self._artifact_metadata(job, reused=True)
        return HandoffExportDownloadDto(
            exportId=artifact.artifactId,
            downloadUrl=artifact.downloadUrl,
            expiresAt=artifact.expiresAt,
        )

    def _artifact_metadata(
        self,
        job: LessonPackageExportJobDto,
        *,
        reused: bool,
    ) -> PrintableLessonKitArtifactDto:
        if job.status != "completed" or not job.storageObjectKey:
            raise ConflictError("The printable lesson-kit artifact is not ready.")
        if not job.packageId:
            raise ConflictError("The printable lesson-kit artifact has no package.")
        package = self._package(job.packageId)
        manifest = job.printPackageManifest
        if manifest is None or manifest.packageRevision != package.version:
            raise ConflictError(
                "The printable lesson-kit artifact is stale. Prepare a new PDF."
            )
        if not job.pageCount or not job.artifactSha256:
            raise ObjectStorageUnavailableError(
                "The printable lesson-kit artifact metadata is incomplete."
            )
        metadata = self.storage.head(job.storageObjectKey)
        if metadata.size_bytes <= 0:
            raise ObjectStorageUnavailableError(
                "The printable lesson-kit artifact is empty."
            )
        if metadata.content_type not in {"application/pdf", ""}:
            raise ObjectStorageUnavailableError(
                "The stored lesson-kit artifact is not a PDF."
            )
        body = self.storage.read_bytes(
            job.storageObjectKey, self.config.MAX_EXPORT_BYTES
        )
        if not body.startswith(b"%PDF-"):
            raise ObjectStorageUnavailableError(
                "The stored lesson-kit artifact is not a valid PDF."
            )
        if len(body) != metadata.size_bytes or (
            job.fileSizeBytes is not None and len(body) != job.fileSizeBytes
        ):
            raise ObjectStorageUnavailableError(
                "The stored lesson-kit artifact size does not match its metadata."
            )
        digest = sha256(body).hexdigest()
        if digest != job.artifactSha256:
            raise ObjectStorageUnavailableError(
                "The stored lesson-kit artifact failed its integrity check."
            )
        try:
            if len(PdfReader(BytesIO(body)).pages) != job.pageCount:
                raise ObjectStorageUnavailableError(
                    "The stored lesson-kit page count does not match its metadata."
                )
        except ObjectStorageUnavailableError:
            raise
        except Exception as exc:
            raise ObjectStorageUnavailableError(
                "The stored lesson-kit artifact could not be reopened."
            ) from exc
        signed = self.storage.create_presigned_get(job.storageObjectKey, job.fileName)
        self.repos.export_jobs.save(
            job.model_copy(
                update={
                    "downloadCount": job.downloadCount + 1,
                    "lastDownloadedAt": _iso(_now()),
                }
            )
        )
        return PrintableLessonKitArtifactDto(
            artifactId=job.exportId,
            packageId=package.id,
            packageRevision=manifest.packageRevision,
            manifestVersion=manifest.schemaVersion,
            printPreset=manifest.printPreset,
            pageSize=manifest.pageSize,
            textProfile=manifest.textProfile,
            materialRevisions=manifest.materialRevisions,
            filename=job.fileName,
            sizeBytes=len(body),
            pageCount=job.pageCount,
            sha256=digest,
            downloadUrl=signed.url,
            expiresAt=_iso(signed.expires_at),
            reused=reused,
        )

    def _find_reusable_artifact(
        self,
        package: LessonPackageDto,
        materials: list[GeneratedMaterialDto],
        request: PrintableLessonKitRequest,
    ) -> LessonPackageExportJobDto | None:
        revisions = {
            item.id: (
                item.materialSpec.revision
                if item.materialSpec is not None
                else item.version
            )
            for item in self._ordered_materials(materials)
        }
        candidates = reversed(self.repos.export_jobs.list())
        for candidate in candidates:
            if not isinstance(candidate, LessonPackageExportJobDto):
                continue
            manifest = candidate.printPackageManifest
            retained_until = _parse_iso(candidate.expiresAt)
            if (
                candidate.status != "completed"
                or candidate.packageId != package.id
                or candidate.format != "pdf"
                or not candidate.exportId.startswith("print-kit-")
                or manifest is None
                or manifest.schemaVersion != 2
                or manifest.rendererVersion != self.renderer_version
                or manifest.packageRevision != package.version
                or manifest.lessonSpecRevision != (
                    package.lessonSpec.revision if package.lessonSpec else 1
                )
                or manifest.printPreset != request.printPreset
                or manifest.materialRevisions != revisions
                or manifest.visualPlanRevisions != {
                    item.id: item.visualAssetPlan.material_revision
                    for item in self._ordered_materials(materials)
                    if item.visualAssetPlan is not None
                }
                or manifest.pageSize != ("A4" if request.pageSize == "A4" else "LETTER")
                or manifest.locale != request.locale
                or manifest.tableOfContents != request.tableOfContents
                or manifest.pageNumbers != request.pageNumbers
                or manifest.textProfile != request.textProfile
                or retained_until is None
                or retained_until <= _now()
            ):
                continue
            try:
                self._verify_reusable_bytes(candidate)
            except ObjectStorageUnavailableError:
                continue
            return candidate
        return None

    def _verify_reusable_bytes(self, job: LessonPackageExportJobDto) -> None:
        if not job.storageObjectKey or not job.artifactSha256:
            raise ObjectStorageUnavailableError(
                "The reusable lesson-kit artifact metadata is incomplete."
            )
        metadata = self.storage.head(job.storageObjectKey)
        if metadata.size_bytes <= 0:
            raise ObjectStorageUnavailableError(
                "The reusable lesson-kit artifact is empty."
            )
        body = self.storage.read_bytes(
            job.storageObjectKey, self.config.MAX_EXPORT_BYTES
        )
        if not body.startswith(b"%PDF-") or sha256(body).hexdigest() != job.artifactSha256:
            raise ObjectStorageUnavailableError(
                "The reusable lesson-kit artifact failed validation."
            )

    def build_manifest(
        self,
        package: LessonPackageDto,
        materials: list[GeneratedMaterialDto],
        *,
        page_size: str,
        print_preset: str = "complete_kit",
        resolution: PrintPresetResolution | None = None,
        locale: str = "en-US",
        table_of_contents: bool = True,
        page_numbers: bool = True,
        text_profile: str = "standard",
    ) -> PrintPackageManifest:
        preset_service = V2PrintPresetService(self.repos)
        resolution = resolution or preset_service.resolve(package, print_preset)
        preset_service.require_available(resolution)
        materials = resolution.materials
        ordered = self._ordered_materials(materials)
        readiness = V2PrintReadinessService(self.repos).evaluate(package.id)
        blocking = [item for item in readiness.blockers if item.severity == "blocking"]
        if blocking:
            raise ConflictError(
                f"Printing is blocked ({blocking[0].blockerId}): {blocking[0].explanation}"
            )
        front_titles = preset_service._front_titles
        sections = [
            PrintPackageManifestSection(
                sectionType=section,
                title=front_titles[section],
                materialIds=[],
                includedReason=preset_service._front_inclusion_reason(
                    resolution.preset, section
                ),
            )
            for section in resolution.front_sections
        ]
        grouped: dict[str, list[GeneratedMaterialDto]] = {}
        group_order: list[str] = []
        for material in ordered:
            group = self._material_section_group(material.type)
            if group not in grouped:
                grouped[group] = []
                group_order.append(group)
            grouped[group].append(material)
        section_details = {
            "instructional": ("instructional_material", "Personalized instructional activities"),
            "functional": ("functional_support", "Functional support cards and boards"),
            "scenario": ("instructional_material", "Scenario and generalization practice"),
            "data": ("data_collection", "Goal-specific data collection"),
            "summary": ("lesson_summary", "Lesson summary"),
            "appendix": ("appendix", "Optional teacher appendix"),
        }
        for group in group_order:
            section_type, title = section_details[group]
            if resolution.preset == "teacher_desk" and group == "functional":
                title = "Teacher cue and prompting guide"
            sections.append(
                PrintPackageManifestSection(
                    sectionType=section_type,
                    title=title,
                    materialIds=[item.id for item in grouped[group]],
                    required=group != "appendix",
                    includedReason=" ".join(dict.fromkeys(
                        resolution.included_reasons[item.id]
                        for item in grouped[group]
                    )),
                )
            )
        lesson_spec_id = package.lessonSpec.id if package.lessonSpec else "legacy"
        lesson_spec_revision = package.lessonSpec.revision if package.lessonSpec else 1
        profile_revision = (
            package.lessonSpec.profile_revision
            if package.lessonSpec
            else package.profileRevision or "legacy"
        )
        return PrintPackageManifest(
            packageId=package.id,
            packageRevision=package.version,
            lessonSpecId=lesson_spec_id,
            lessonSpecRevision=lesson_spec_revision,
            profileRevision=profile_revision,
            printPreset=resolution.preset,
            pageSize="A4" if page_size == "A4" else "LETTER",
            locale=locale,
            sections=sections,
            excludedEntries=[
                PrintPackageManifestExclusion(
                    entryType=item.entryType,
                    entryId=item.entryId,
                    title=item.title,
                    reason=item.reason,
                )
                for item in resolution.excluded_entries
            ],
            materialRevisions={
                item.id: (
                    item.materialSpec.revision
                    if item.materialSpec is not None
                    else item.version
                )
                for item in ordered
            },
            visualPlanRevisions={
                item.id: item.visualAssetPlan.material_revision
                for item in ordered
                if item.visualAssetPlan is not None
            },
            assetVersions=self._asset_versions(ordered),
            tableOfContents=table_of_contents,
            pageNumbers=page_numbers,
            textProfile=text_profile,
            generatedAt=_iso(_now()),
            rendererVersion=self.renderer_version,
            sourceApprovalReadinessEvidence=PrintSourceApprovalReadinessEvidence(
                evaluatedAt=readiness.evaluatedAt,
                ready=True,
                packageApprovalStatus="approved",
                packageRevision=package.version,
                lessonSpecRevision=lesson_spec_revision,
                materialReviewedRevisions={
                    item.id: item.materialSpec.approval.reviewed_revision
                    for item in ordered if item.materialSpec is not None
                },
                materialApprovedRevisions={
                    item.id: item.materialSpec.approval.approved_revision
                    for item in ordered if item.materialSpec is not None
                },
                warningBlockerIds=[
                    item.blockerId for item in readiness.blockers
                    if item.severity == "warning"
                ],
            ),
        )

    def _build_pdf(
        self,
        package: LessonPackageDto,
        materials: list[GeneratedMaterialDto],
        page_size: str,
        *,
        manifest: PrintPackageManifest | None = None,
    ) -> bytes:
        manifest = manifest or self.build_manifest(
            package, materials, page_size=page_size
        )
        styles = self._styles(manifest.textProfile)
        base_size = A4 if page_size == "A4" else LETTER
        learner_code = self._learner_code(package)
        material_by_id = {item.id: item for item in materials}
        # The desk-copy run sheet is a projection of the whole approved package,
        # even though its printable material appendix is intentionally smaller.
        # This keeps preparation and materials-needed guidance complete.
        run_sheet_materials = V2PrintReadinessService(self.repos).current_materials(
            package
        )
        parts: list[tuple[str, bytes]] = []
        for section in manifest.sections:
            if section.sectionType == "cover":
                story = self._cover_story(
                    package, manifest, learner_code, styles
                )
                parts.append(
                    (
                        section.title,
                        self._render_story(
                            story, base_size, section.title, manifest.textProfile
                        ),
                    )
                )
                continue
            if not section.materialIds:
                story = self._front_matter_story(
                    section.title, package, run_sheet_materials, learner_code, styles
                )
                parts.append(
                    (
                        section.title,
                        self._render_story(
                            story, base_size, section.title, manifest.textProfile
                        ),
                    )
                )
                continue
            for material_id in section.materialIds:
                material = material_by_id.get(material_id)
                if material is None:
                    raise ValidationError(
                        f"Print manifest references missing material {material_id}"
                    )
                orientation = self._material_orientation(material)
                dimensions = landscape(base_size) if orientation == "landscape" else base_size
                usable_width = dimensions[0] - 1.1 * inch
                story = self._material_story(
                    material, package, styles, usable_width=usable_width
                )
                parts.append(
                    (
                        material.title,
                        self._render_story(
                            story, dimensions, material.title, manifest.textProfile
                        ),
                    )
                )
        return self._assemble_pdf(
            parts,
            package_title=str((package.documentContent or {}).get("title") or package.goal),
            learner_code=learner_code,
            page_numbers=manifest.pageNumbers,
            text_profile=manifest.textProfile,
        )

    def _resolve_current_package_materials(
        self, package: LessonPackageDto, requested_material_ids: list[str]
    ) -> list[GeneratedMaterialDto]:
        repository_materials = {
            item.id: item
            for item in self.repos.generated_materials.for_package(package.id)
            if isinstance(item, GeneratedMaterialDto)
        }
        snapshots = [
            repository_materials.get(item.id, item)
            for item in package.materials
        ]
        if package.packageContentPlan is not None:
            included_types = V2PackageContentPlanService.included_material_types(
                package.packageContentPlan
            )
            by_type: dict[str, list[GeneratedMaterialDto]] = {}
            for material in snapshots:
                by_type.setdefault(material.type, []).append(material)
            missing_types = [
                material_type
                for material_type in included_types
                if len(by_type.get(material_type, [])) != 1
            ]
            if missing_types:
                raise ValidationError(
                    "The approved package does not contain exactly one current material for every planned type.",
                    payload={"missingOrDuplicateMaterialTypes": missing_types},
                )
            expected = [by_type[material_type][0] for material_type in included_types]
        else:
            # Legacy packages predate PackageContentPlan. Their complete stored
            # package inventory remains the compatibility source of truth.
            expected = snapshots
        if not expected:
            raise ValidationError("The approved package has no printable materials.")
        expected_ids = {item.id for item in expected}
        requested_ids = set(requested_material_ids)
        if requested_ids and requested_ids != expected_ids:
            raise ValidationError(
                "A complete lesson-kit PDF must include every approved package material.",
                payload={
                    "omittedMaterialIds": sorted(expected_ids - requested_ids),
                    "unknownMaterialIds": sorted(requested_ids - expected_ids),
                },
            )
        return self._ordered_materials(expected)

    @classmethod
    def _ordered_materials(
        cls, materials: list[GeneratedMaterialDto]
    ) -> list[GeneratedMaterialDto]:
        order = {
            "blue_line_activity": 10,
            "quantity_cards": 11,
            "number_cards": 12,
            "matching_page": 13,
            "sorting_page": 14,
            "sequence_cards": 15,
            "task_analysis_cards": 16,
            "social_narrative": 17,
            "visual_card": 18,
            "break_card": 30,
            "help_card": 31,
            "first_then_board": 32,
            "token_board": 33,
            "visual_timer": 34,
            "choice_board": 35,
            "core_word_board": 36,
            "emotion_scale": 37,
            "visual_schedule": 38,
            "teacher_cue_card": 39,
            "scenario_cards": 50,
            "data_sheet": 60,
            "summary_template": 70,
            "session_summary": 71,
            "handoff_note": 80,
        }
        return sorted(
            materials,
            key=lambda item: (order.get(item.type, 90), item.type, item.id),
        )

    @staticmethod
    def _material_section_group(material_type: str) -> str:
        if material_type == "scenario_cards":
            return "scenario"
        if material_type == "data_sheet":
            return "data"
        if material_type in {"summary_template", "session_summary"}:
            return "summary"
        if material_type in {
            "break_card", "help_card", "first_then_board", "token_board",
            "visual_timer", "choice_board", "core_word_board", "emotion_scale",
            "visual_schedule", "teacher_cue_card",
        }:
            return "functional"
        if material_type == "handoff_note":
            return "appendix"
        return "instructional"

    def _asset_versions(
        self, materials: list[GeneratedMaterialDto]
    ) -> dict[str, int]:
        versions: dict[str, int] = {}
        for material in materials:
            if material.visualAssetPlan is not None:
                for item in material.visualAssetPlan.visual_items:
                    asset_id = item.asset_id or item.fallback_asset_id
                    if not asset_id:
                        continue
                    stored = self.repos.image_assets.get(asset_id)
                    versions[asset_id] = int(getattr(stored, "version", 1) or 1)
                continue
            for item in self._visual_items(self._material_content(material)):
                asset_id = item.get("imageAssetId") or item.get("assetId")
                if asset_id:
                    stored = self.repos.image_assets.get(str(asset_id))
                    versions[str(asset_id)] = int(getattr(stored, "version", 1) or 1)
        return versions

    def _cover_story(
        self,
        package: LessonPackageDto,
        manifest: PrintPackageManifest,
        learner_code: str,
        styles: dict[str, Any],
    ) -> list[Any]:
        content = package.documentContent or {}
        story: list[Any] = [
            Spacer(1, 0.35 * inch),
            Paragraph(
                escape(str(content.get("title") or package.goal)), styles["Title"]
            ),
            Paragraph("Complete printable lesson kit", styles["Kicker"]),
            Spacer(1, 18),
            self._facts_table(package, learner_code, styles),
            Spacer(1, 18),
            Paragraph("Lesson goal", styles["Heading2"]),
            Paragraph(
                escape(str(content.get("goal") or package.goal)), styles["BodyText"]
            ),
        ]
        if manifest.tableOfContents:
            story.extend(
                [Spacer(1, 18), Paragraph("Package contents", styles["Heading2"])]
            )
            for index, section in enumerate(manifest.sections[1:], start=1):
                suffix = (
                    f" - {len(section.materialIds)} material"
                    f"{'s' if len(section.materialIds) != 1 else ''}"
                    if section.materialIds
                    else ""
                )
                story.append(
                    Paragraph(
                        f"{index}. {escape(section.title)}{escape(suffix)}",
                        styles["BodyText"],
                    )
                )
        return story

    def _front_matter_story(
        self,
        title: str,
        package: LessonPackageDto,
        materials: list[GeneratedMaterialDto],
        learner_code: str,
        styles: dict[str, Any],
    ) -> list[Any]:
        content = package.documentContent or {}
        story: list[Any] = [Paragraph(escape(title), styles["Title"]), Spacer(1, 12)]
        if title == "Learner privacy and synthetic-data notice":
            story.extend(
                [
                    Paragraph(
                        "This demonstration package uses synthetic learner data.",
                        styles["Heading2"],
                    ),
                    Paragraph(
                        "Only the learner code is printed. Direct identifiers, uploaded source-document text, and record excerpts are excluded from this PDF.",
                        styles["BodyText"],
                    ),
                ]
            )
            return story
        if title == "Why this lesson is personalized":
            story.append(
                Paragraph(
                    f"This lesson was prepared for {escape(learner_code)} from the current teacher-approved learner profile and lesson decisions.",
                    styles["BodyText"],
                )
            )
            for value in self._personalization_points(package):
                story.append(Paragraph(f"- {escape(value)}", styles["BodyText"]))
            return story
        if title == "Teacher lesson brief":
            story.extend(
                [
                    Paragraph("Lesson goal", styles["Heading2"]),
                    Paragraph(escape(package.goal), styles["BodyText"]),
                    Paragraph("Lesson brief", styles["Heading2"]),
                    Paragraph(
                        escape(str(content.get("lessonBrief") or package.lessonBrief)),
                        styles["BodyText"],
                    ),
                ]
            )
            for label, key in (
                ("Prompting plan", "promptingPlan"),
                ("Reinforcement plan", "reinforcementPlan"),
                ("Data collection", "dataCollectionPlan"),
            ):
                value = content.get(key)
                if value:
                    story.extend(
                        [
                            Paragraph(label, styles["Heading2"]),
                            Paragraph(escape(str(value)), styles["BodyText"]),
                        ]
                    )
            return story
        if title == "Classroom Run Sheet":
            return self._classroom_run_sheet_story(
                package, materials, learner_code, styles
            )
        story.append(Paragraph("Teaching flow", styles["Heading2"]))
        for index, step in enumerate(package.teachingFlow, start=1):
            story.extend(
                [
                    Paragraph(f"{index}. {escape(step.title)}", styles["Heading3"]),
                    Paragraph(escape(step.description), styles["BodyText"]),
                    Paragraph(
                        f"<b>Teacher:</b> {escape(step.teacherAction)}<br/>"
                        f"<b>Learner:</b> {escape(step.learnerAction)}",
                        styles["Small"],
                    ),
                    Spacer(1, 7),
                ]
            )
        return story

    def _classroom_run_sheet_story(
        self,
        package: LessonPackageDto,
        materials: list[GeneratedMaterialDto],
        learner_code: str,
        styles: dict[str, Any],
    ) -> list[Any]:
        sheet = V2ClassroomRunSheetService().build(
            package, materials, learner_code=learner_code
        )
        compact = styles["RunSheetCompact"]
        label = styles["RunSheetLabel"]
        story: list[Any] = [
            Paragraph("Classroom Run Sheet", styles["Title"]),
            Paragraph(
                "A compact guide for preparation, instruction, data capture, and closeout.",
                styles["Kicker"],
            ),
            Spacer(1, 7),
            Table(
                [
                    [Paragraph("Learner code", label), Paragraph(escape(sheet.learnerCode), compact),
                     Paragraph("Duration", label), Paragraph(escape(sheet.totalDuration), compact)],
                    [Paragraph("Goal", label), Paragraph(escape(sheet.goal), compact),
                     Paragraph("Modes", label), Paragraph(escape(", ".join(sheet.communicationModes) or "Use the current approved communication plan"), compact)],
                    [Paragraph("Success", label), Paragraph(escape(sheet.successCriterion), compact), "", ""],
                ],
                colWidths=[0.78 * inch, 2.45 * inch, 0.9 * inch, 2.45 * inch],
                style=TableStyle(
                    [
                        ("SPAN", (1, 2), (3, 2)),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EFF6FF")),
                        ("BACKGROUND", (2, 0), (2, 1), colors.HexColor("#EFF6FF")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                ),
            ),
            Spacer(1, 7),
        ]
        before = "<br/>".join(
            f"[ ] {escape(value)}" for value in sheet.beforeClassChecklist
        ) or "No additional preparation actions are recorded."
        materials_text = "<br/>".join(
            f"- {escape(value)}" for value in sheet.materialsNeeded
        )
        story.append(
            Table(
                [
                    [Paragraph("Before class", label), Paragraph("Materials needed", label)],
                    [Paragraph(before, compact), Paragraph(materials_text, compact)],
                ],
                colWidths=[3.3 * inch, 3.3 * inch],
                repeatRows=1,
                splitByRow=1,
                splitInRow=1,
                style=TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#93C5FD")),
                        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DBEAFE")),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFF6FF")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                ),
            )
        )
        story.extend([Spacer(1, 7), Paragraph("Timed lesson flow", styles["Heading2"])])
        flow_rows: list[list[Any]] = [
            [Paragraph("Step", label), Paragraph("Run the lesson", label)]
        ]
        for index, step in enumerate(sheet.steps, start=1):
            script = (
                f"<b>Say:</b> {escape(step.teacherScript)}<br/>"
                if step.teacherScript
                else ""
            )
            break_line = (
                f"<br/><b>Break:</b> {escape(step.breakOption)}"
                if step.breakOption
                else ""
            )
            data = ", ".join(step.dataToRecord) or "Record the goal-aligned response."
            details = (
                f"<b>{escape(step.title)}</b><br/>"
                f"{script}<b>Do:</b> {escape(step.teacherAction)}<br/>"
                f"<b>Look for:</b> {escape(step.expectedLearnerResponse)} - "
                f"<b>Wait:</b> {escape(step.waitTime)}<br/>"
                f"<b>Prompt/fade:</b> {escape(step.promptAction)}<br/>"
                f"<b>Reinforce:</b> {escape(step.reinforcementAction)} - "
                f"<b>Neutral correction:</b> {escape(step.errorCorrectionAction)}<br/>"
                f"<b>Record:</b> {escape(data)} - "
                f"<b>Transition:</b> {escape(step.transitionCue)}{break_line}"
            )
            flow_rows.append(
                [
                    Paragraph(f"<b>{index}</b><br/>{escape(step.duration)}", compact),
                    Paragraph(details, compact),
                ]
            )
        story.append(
            Table(
                flow_rows,
                colWidths=[0.72 * inch, 5.88 * inch],
                repeatRows=1,
                # A teaching step may be taller than the remaining printable
                # area. Let ReportLab continue that row beneath a repeated
                # header instead of leaving most of the preceding page blank.
                splitByRow=0,
                splitInRow=1,
                style=TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#CBD5E1")),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DBEAFE")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                ),
            )
        )
        reminder = "<br/>".join(f"- {escape(value)}" for value in sheet.dataReminder)
        closeout = "<br/>".join(f"[ ] {escape(value)}" for value in sheet.closeout)
        story.append(
            KeepTogether(
                [
                    Spacer(1, 7),
                    Table(
                    [
                        [Paragraph("In-the-moment data", label), Paragraph("Two-minute closeout", label)],
                        [Paragraph(reminder, compact), Paragraph(closeout, compact)],
                    ],
                    colWidths=[3.3 * inch, 3.3 * inch],
                    style=TableStyle(
                        [
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#93C5FD")),
                            ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DBEAFE")),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFF6FF")),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]
                    ),
                    ),
                    Spacer(1, 6),
                    Paragraph(
                        f"<b>{escape(sheet.teacherJudgmentNote)}</b>",
                        styles["RunSheetNote"],
                    ),
                ]
            )
        )
        return story

    @staticmethod
    def _personalization_points(package: LessonPackageDto) -> list[str]:
        spec = package.lessonSpec
        if spec is None:
            return [
                "Teacher-approved goal, materials, theme, prompting, and reinforcement are preserved.",
                "No source-document text is reproduced.",
            ]
        points: list[str] = []
        if spec.goal.accepted_response_modes:
            points.append(
                "Accepted responses: " + ", ".join(spec.goal.accepted_response_modes)
            )
        if spec.personalization_themes:
            points.append("Relevant interests: " + ", ".join(spec.personalization_themes))
        if spec.access_plan.layout_requirements:
            points.append("Visual access: " + "; ".join(spec.access_plan.layout_requirements))
        if spec.access_plan.motor_access_alternatives:
            points.append("Motor access: " + "; ".join(spec.access_plan.motor_access_alternatives))
        if spec.access_plan.prohibited_audio_features:
            points.append("Excluded audio: " + "; ".join(spec.access_plan.prohibited_audio_features))
        if spec.reinforcement_plan.earned_reward:
            points.append("Earned reward: " + spec.reinforcement_plan.earned_reward)
        if spec.contexts:
            points.append("Practice contexts: " + "; ".join(item.label for item in spec.contexts))
        return points or ["Current teacher-approved lesson decisions are preserved."]

    @staticmethod
    def _render_story(
        story: list[Any],
        page_dimensions: tuple[float, float],
        title: str,
        text_profile: str = "standard",
    ) -> bytes:
        policy = print_layout_policy(text_profile)
        output = BytesIO()
        document = SimpleDocTemplate(
            output,
            pagesize=page_dimensions,
            rightMargin=policy.safe_margin_inches * inch,
            leftMargin=policy.safe_margin_inches * inch,
            topMargin=policy.safe_margin_inches * inch,
            bottomMargin=policy.safe_margin_inches * inch,
            title=title,
            allowSplitting=1,
        )
        document.build(story)
        return output.getvalue()

    @staticmethod
    def _assemble_pdf(
        parts: list[tuple[str, bytes]],
        *,
        package_title: str,
        learner_code: str,
        page_numbers: bool,
        text_profile: str,
    ) -> bytes:
        policy = print_layout_policy(text_profile)
        writer = PdfWriter()
        page_index = 0
        for title, body in parts:
            reader = PdfReader(BytesIO(body))
            if reader.pages:
                try:
                    writer.add_outline_item(title, page_index)
                except Exception:
                    pass
            for page in reader.pages:
                width = float(page.mediabox.width)
                height = float(page.mediabox.height)
                overlay_bytes = BytesIO()
                overlay = Canvas(overlay_bytes, pagesize=(width, height))
                overlay.setFont(
                    "Helvetica",
                    max(8, policy.teacher_compact_points - 1),
                )
                overlay.setFillColor(colors.HexColor("#64748B"))
                footer_title = package_title.strip()[:72]
                overlay.drawString(
                    0.55 * inch,
                    0.25 * inch,
                    f"{normalize_print_text(footer_title)} - {normalize_print_text(learner_code)}",
                )
                if page_numbers:
                    overlay.drawRightString(
                        width - 0.55 * inch,
                        0.25 * inch,
                        f"Page {page_index + 1}",
                    )
                overlay.save()
                overlay_page = PdfReader(BytesIO(overlay_bytes.getvalue())).pages[0]
                writer.add_page(page)
                writer.pages[-1].merge_page(overlay_page)
                page_index += 1
        writer.add_metadata(
            {
                "/Title": "Complete Lesson Kit",
                "/Producer": V2PrintableLessonKitService.renderer_version,
            }
        )
        output = BytesIO()
        writer.write(output)
        return output.getvalue()

    def _validate_pdf_artifact(
        self,
        body: bytes,
        package: LessonPackageDto,
        materials: list[GeneratedMaterialDto],
        manifest: PrintPackageManifest,
        file_name: str,
    ) -> int:
        if not body or not body.startswith(b"%PDF"):
            raise ValidationError("Generated printable artifact is not a valid PDF.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.pdf", file_name):
            raise ValidationError("Generated printable filename is unsafe.")
        expected_ids = {item.id for item in materials}
        manifest_ids = {
            material_id
            for section in manifest.sections
            for material_id in section.materialIds
        }
        if manifest_ids != expected_ids:
            raise ValidationError(
                "The print manifest omitted or added package materials.",
                payload={
                    "omittedMaterialIds": sorted(expected_ids - manifest_ids),
                    "unexpectedMaterialIds": sorted(manifest_ids - expected_ids),
                },
            )
        try:
            reader = PdfReader(BytesIO(body))
            page_count = len(reader.pages)
            page_text = [page.extract_text() or "" for page in reader.pages]
        except Exception as exc:
            raise ValidationError("Generated PDF could not be reopened.") from exc
        minimum_pages = self._expected_minimum_pages(package, materials, manifest)
        if page_count < minimum_pages:
            raise ValidationError(
                "Generated PDF has fewer pages than the complete package requires.",
                payload={"pageCount": page_count, "expectedMinimum": minimum_pages},
            )
        combined = "\n".join(page_text).casefold()
        cursor = 0
        for material in self._ordered_materials(materials):
            printable_title = normalize_print_text(material.title).casefold()
            position = combined.find(printable_title, cursor)
            if position < 0:
                raise ValidationError(
                    f"Generated PDF omitted required material text: {material.title}"
                )
            cursor = position + len(printable_title)
        return page_count

    @staticmethod
    def _expected_minimum_pages(
        package: LessonPackageDto,
        materials: list[GeneratedMaterialDto],
        manifest: PrintPackageManifest,
    ) -> int:
        front_pages = len([section for section in manifest.sections if not section.materialIds])
        material_pages = len(materials)
        for material in materials:
            if material.type == "blue_line_activity":
                material_pages += 1
            elif material.type == "scenario_cards":
                scenarios = V2PrintableLessonKitService._material_content(material).get("scenarios")
                count = len(scenarios) if isinstance(scenarios, list) else 0
                cards_per_page = V2PrintableLessonKitService._scenario_cards_per_page(scenarios)
                material_pages += max(0, ((count + cards_per_page - 1) // cards_per_page) - 1)
        return front_pages + material_pages

    @staticmethod
    def _scenario_cards_per_page(scenarios: Any) -> int:
        if not isinstance(scenarios, list) or not scenarios:
            return 1
        longest = max(len(str(item)) for item in scenarios)
        return 2 if longest <= 420 else 1

    def _learner_code(self, package: LessonPackageDto) -> str:
        learner = self.repos.learners.get(package.learnerId)
        code = str(getattr(learner, "code", "") or "").strip()
        return code or "Learner"

    @staticmethod
    def _material_orientation(material: GeneratedMaterialDto) -> str:
        requested = str(material.printLayout.get("orientation") or "").casefold()
        if material.materialSpec is not None:
            requested = material.materialSpec.design_constraints.orientation.casefold()
        if material.type == "data_sheet":
            columns = V2PrintableLessonKitService._material_content(material).get("columns")
            if isinstance(columns, list) and len(columns) >= 5:
                return "landscape"
        return "landscape" if requested == "landscape" else "portrait"

    def _material_story(
        self,
        material: GeneratedMaterialDto,
        package: LessonPackageDto,
        styles: dict[str, Any],
        *,
        usable_width: float = 6.8 * inch,
    ) -> list[Any]:
        content = self._material_content(material)
        if (
            material.materialSpec is not None
            and material.visualAssetPlan is not None
            and material.visualAssetPlan.material_revision != material.materialSpec.revision
        ):
            raise ConflictError(
                f"{material.title} has a stale visual plan and cannot be printed."
            )
        palette = self._design_palette(content)
        header = self._material_header(material.title, styles)
        image = self._embedded_image(content)
        visual_items = self._visual_items(content)
        if image is None and visual_items:
            image = self._embedded_image(visual_items[0])
        card_types = {
            "quantity_cards",
            "number_cards",
            "visual_card",
            "scenario_cards",
            "sequence_cards",
            "social_narrative",
            "sorting_page",
            "visual_schedule",
            "task_analysis_cards",
            "emotion_scale",
            "blue_line_activity",
            "visual_timer",
        }
        header_image_excluded_types = {
            *card_types,
            "first_then_board",
            "token_board",
        }
        if image is not None and material.type not in header_image_excluded_types:
            header.extend([image, Spacer(1, 10)])

        if material.type == "blue_line_activity":
            stations = [
                item for item in visual_items
                if str(item.get("semanticKey") or "").startswith("station:")
            ]
            station_cells: list[Any] = []
            for index, station in enumerate(stations, 1):
                station_image = self._embedded_image(
                    station, width=1.25 * inch, height=1.25 * inch
                )
                cell: list[Any] = [Paragraph(f"<b>{index}</b>", styles["Kicker"])]
                if station_image is not None:
                    cell.extend([station_image, Spacer(1, 4)])
                cell.append(Paragraph(escape(str(station.get("label") or "")), styles["Card"]))
                station_cells.append(cell)
            route = self._route_drawing(palette, width=usable_width)
            setup = content.get("teacherSetup") if isinstance(content.get("teacherSetup"), list) else []
            answer = content.get("answerKeyOrExpectedSequence") if isinstance(content.get("answerKeyOrExpectedSequence"), list) else []
            result: list[Any] = [
                *self._material_header(material.title, styles),
                Paragraph(escape(str(content.get("learnerAction") or "")), styles["BigInstruction"]),
                Spacer(1, 10), route,
                Spacer(1, 12),
                Paragraph("<b>Teacher setup</b>", styles["Heading3"]),
                *[Paragraph(f"{index}. {escape(str(step))}", styles["BodyText"]) for index, step in enumerate(setup, 1)],
                Paragraph(f"<b>Complete when:</b> {escape(str(content.get('completionCriterion') or ''))}", styles["BodyText"]),
                PageBreak(),
                *self._material_header(f"{material.title} - Station cards", styles),
            ]
            if station_cells:
                result.append(
                    Table(
                        [station_cells],
                        colWidths=[usable_width / len(station_cells)] * len(station_cells),
                        rowHeights=[2.55 * inch],
                        style=self._visual_sheet_style(),
                    )
                )
            result.extend([
                Spacer(1, 12),
                Paragraph("<b>Station sequence / answer key</b>", styles["Heading3"]),
                Paragraph(" -> ".join(escape(str(item)) for item in answer), styles["BodyText"]),
                Paragraph(f"<b>Generalize:</b> {escape(str(content.get('generalizationExtension') or ''))}", styles["BodyText"]),
            ])
            return result

        if material.type == "visual_timer":
            duration = int(content.get("durationMinutes") or content.get("duration") or 1)
            timer_item = visual_items[0] if visual_items else {"role": "timer_state", "designConstraints": {"fallbackKind": "timer"}}
            timer = self._deterministic_visual(timer_item, width=3.0 * inch, height=3.0 * inch)
            return [
                *self._material_header(material.title, styles), timer, Spacer(1, 12),
                Paragraph(f"<b>{duration}:00 visual-only countdown</b>", styles["MaterialTitle"]),
                Paragraph(f"{escape(str(content.get('startLabel') or 'Start'))} -> {escape(str(content.get('endLabel') or 'Finished'))}", styles["BigInstruction"]),
                Paragraph(f"<b>Return cue:</b> {escape(str(content.get('returnToTaskCue') or ''))}", styles["BodyText"]),
                Paragraph("No alarm or audio cue.", styles["Kicker"]),
            ]

        if material.type == "scenario_cards" and isinstance(content.get("scenarios"), list):
            result: list[Any] = []
            scenarios = [item for item in content["scenarios"] if isinstance(item, dict)]
            cards_per_page = (
                1
                if styles["BodyText"].fontSize >= 12
                else self._scenario_cards_per_page(scenarios)
            )
            for index, scenario in enumerate(scenarios):
                if index and index % cards_per_page == 0:
                    result.append(PageBreak())
                if cards_per_page == 2:
                    result.extend(
                        [
                            Paragraph(
                                escape(f"{material.title} {index + 1}"),
                                styles["Heading2"],
                            ),
                            Spacer(1, 4),
                        ]
                    )
                else:
                    result.extend(self._material_header(f"{material.title} {index + 1}", styles))
                visual = visual_items[index] if index < len(visual_items) else {}
                scenario_image = self._embedded_image(visual, width=2.0 * inch, height=1.5 * inch)
                if scenario_image is not None:
                    result.extend([scenario_image, Spacer(1, 8)])
                scenario_style = styles["ScenarioCompact"] if cards_per_page == 2 else styles["BodyText"]
                context_style = styles["Heading3"] if cards_per_page == 2 else styles["MaterialTitle"]
                result.append(Paragraph(f"<b>{escape(str(scenario.get('context') or ''))}</b>", context_style))
                for label, key in (
                    ("Situation", "triggerOrTransition"), ("Visual cue", "visualCue"),
                    ("Teacher wording", "teacherWording"), ("Independent opportunity", "learnerOpportunity"),
                    ("Prompt sequence", "promptSequence"), ("Accepted response", "acceptedModalities"),
                    ("Outcome", "breakOutcome"), ("Return support", "returnSupport"),
                    ("Generalization", "generalizationLabel"),
                ):
                    value = scenario.get(key)
                    if isinstance(value, list):
                        value = " -> ".join(str(item) for item in value)
                    if key == "learnerOpportunity":
                        value = f"{value}; wait {scenario.get('waitTimeSeconds')} seconds."
                    result.append(Paragraph(f"<b>{label}:</b> {escape(str(value or ''))}", scenario_style))
            return result

        if material.type == "matching_page":
            labels = self._card_labels(material, package)
            rows: list[list[Any]] = []
            for index, label in enumerate(labels):
                visual_item = (
                    visual_items[index]
                    if index < len(visual_items)
                    else (visual_items[0] if visual_items else content)
                )
                quantity = visual_item.get("quantity")
                if not isinstance(quantity, int) and label.strip().isdigit():
                    quantity = int(label.strip())
                quantity_grid = self._quantity_image_grid(visual_item, quantity)
                visual = quantity_grid or self._embedded_image(
                    visual_item, width=0.8 * inch, height=0.8 * inch
                )
                rows.append(
                    [
                        Paragraph(f"<b>{escape(label)}</b>", styles["BigCard"]),
                        Paragraph("↔", styles["Card"]),
                        visual or Paragraph("Custom visual", styles["Kicker"]),
                    ]
                )
            result: list[Any] = []
            row_chunks = [
                rows[index : index + 6] for index in range(0, len(rows), 6)
            ] or [[]]
            for sheet_index, row_chunk in enumerate(row_chunks, start=1):
                if sheet_index > 1:
                    result.append(PageBreak())
                result.extend(
                    self._material_header(
                        material.title,
                        styles,
                        sheet_index=sheet_index,
                        sheet_count=len(row_chunks),
                    )
                )
                table = Table(
                    row_chunk,
                    colWidths=[usable_width * 0.15, usable_width * 0.08, usable_width * 0.77],
                    rowHeights=[0.9 * inch] * len(row_chunk),
                )
                table.setStyle(self._card_table_style(palette))
                result.append(table)
            return result

        if material.type in card_types:
            labels = self._card_labels(material, package)
            cells: list[Any] = []
            for index, label in enumerate(labels):
                # Multiple concept exemplars intentionally share a child-facing
                # label (for example four different banana cards). Preserve the
                # generated order instead of repeatedly selecting the first item
                # with that label.
                visual_item = (
                    visual_items[index]
                    if index < len(visual_items)
                    else (visual_items[0] if visual_items else content)
                )
                card_image = self._embedded_image(
                    visual_item, width=2.15 * inch, height=2.15 * inch
                )
                cell: list[Any] = []
                quantity = visual_item.get("quantity")
                if not isinstance(quantity, int) and label.strip().isdigit():
                    quantity = int(label.strip())
                quantity_grid = self._quantity_image_grid(visual_item, quantity)
                if quantity_grid is not None:
                    cell.extend([quantity_grid, Spacer(1, 4)])
                elif card_image is not None:
                    cell.extend([card_image, Spacer(1, 5)])
                cell.append(Paragraph(f"<b>{escape(label)}</b>", styles["Card"]))
                cells.append(cell)
            sheet_cells = [
                cells[index : index + 4] for index in range(0, len(cells), 4)
            ] or [[]]
            result: list[Any] = []
            for sheet_index, cell_chunk in enumerate(sheet_cells, start=1):
                if sheet_index > 1:
                    result.append(PageBreak())
                result.extend(
                    self._material_header(
                        material.title,
                        styles,
                        sheet_index=sheet_index,
                        sheet_count=len(sheet_cells),
                    )
                )
                if len(cell_chunk) % 2:
                    cell_chunk.append(Paragraph("", styles["Card"]))
                rows = [
                    cell_chunk[index : index + 2]
                    for index in range(0, len(cell_chunk), 2)
                ]
                table = Table(
                    rows,
                    colWidths=[usable_width / 2, usable_width / 2],
                    rowHeights=[2.9 * inch] * len(rows),
                )
                table.setStyle(self._visual_sheet_style())
                result.append(table)
            return result

        if material.type == "teacher_cue_card":
            prompts = content.get("promptsUsed")
            if not isinstance(prompts, list):
                prompts = []
            result = [
                *header,
                Paragraph("Goal", styles["Heading3"]),
                Paragraph(
                    escape(str(content.get("goal") or package.goal)),
                    styles["BodyText"],
                ),
                Spacer(1, 8),
                Paragraph("Prompting and fading", styles["Heading3"]),
            ]
            result.extend(
                Paragraph(escape(str(prompt)), styles["BodyText"])
                for prompt in prompts
            )
            if content.get("nextStep"):
                result.extend(
                    [
                        Spacer(1, 8),
                        Paragraph("Next step", styles["Heading3"]),
                        Paragraph(
                            escape(str(content["nextStep"])), styles["BodyText"]
                        ),
                    ]
                )
            return result

        if material.type in {"help_card", "break_card"}:
            phrase = str(
                content.get("phrase")
                or content.get("requestText")
                or content.get("instruction")
                or package.goal
            )
            result = [
                *header,
                Table(
                    [[Paragraph(escape(phrase), styles["BigCard"])]],
                    colWidths=[usable_width],
                    rowHeights=[4.4 * inch],
                    style=self._card_table_style(palette),
                ),
            ]
            modes = content.get("acceptedCommunicationModes")
            if isinstance(modes, list) and modes:
                result.append(Paragraph(f"Accepted: {escape(' or '.join(str(item) for item in modes))}", styles["BigInstruction"]))
            if content.get("teacherResponseAfterUse"):
                result.append(Paragraph(f"<b>Teacher action:</b> {escape(str(content['teacherResponseAfterUse']))}", styles["BodyText"]))
            return result

        if material.type in {"choice_board", "first_then_board", "core_word_board"}:
            maximum = 2 if material.type == "first_then_board" else 6
            labels = self._card_labels(material, package)[:maximum]
            minimum = (
                2
                if material.type == "first_then_board"
                else 4
                if material.type == "core_word_board"
                else 2
            )
            while len(labels) < minimum:
                labels.append("Teacher-confirmed choice")
            choice_cells: list[Any] = []
            for index, label in enumerate(labels):
                visual_item = (
                    visual_items[index] if index < len(visual_items) else content
                )
                choice_image = self._embedded_image(
                    visual_item, width=2.0 * inch, height=2.0 * inch
                )
                cell: list[Any] = []
                if choice_image is not None:
                    cell.extend([choice_image, Spacer(1, 8)])
                cell.append(Paragraph(escape(label), styles["BigCard"]))
                choice_cells.append(cell)
            if material.type != "first_then_board":
                if len(choice_cells) % 2:
                    choice_cells.append(Paragraph("", styles["Card"]))
                rows = [
                    choice_cells[index : index + 2]
                    for index in range(0, len(choice_cells), 2)
                ]
                table = Table(
                    rows,
                    colWidths=[usable_width / 2, usable_width / 2],
                    rowHeights=[1.75 * inch] * len(rows),
                )
            else:
                table = Table(
                    [choice_cells],
                    colWidths=[usable_width / 2, usable_width / 2],
                    rowHeights=[3.2 * inch],
                )
            table.setStyle(self._card_table_style(palette))
            result = [*header, table]
            if material.type == "first_then_board":
                result.extend([
                    Paragraph(f"<b>Complete when:</b> {escape(str(content.get('completionCriterion') or ''))}", styles["BodyText"]),
                    Paragraph(f"<b>After THEN:</b> {escape(str(content.get('returnOrTransitionInstruction') or ''))}", styles["BodyText"]),
                ])
                return result
            return result

        if material.type == "token_board":
            count = int(content.get("tokens") or content.get("tokenCount") or 5)
            count = min(max(count, 2), 10)
            reward = escape(
                str(
                    content.get("reward")
                    or content.get("rewardLabel")
                    or "Teacher-confirmed reward"
                )
            )
            token_visual = next(
                (item for item in visual_items if item.get("semanticKey") == "token-symbol"),
                visual_items[0] if visual_items else content,
            )
            reward_visual = next(
                (item for item in visual_items if item.get("role") == "reward"),
                None,
            )
            token_row = self._quantity_image_grid(
                token_visual, count, image_size=0.65 * inch
            ) or self._token_row(
                count, palette, width=usable_width
            )
            reward_image = self._embedded_image(
                reward_visual or {}, width=1.0 * inch, height=1.0 * inch
            )
            result = [
                *header,
                Paragraph(
                    escape(str(content.get("instruction") or "Earn tokens, then choose a reward.")),
                    styles["BigInstruction"],
                ),
                Spacer(1, 5),
                token_row,
                Spacer(1, 7),
                Paragraph(f"Reward: <b>{reward}</b>", styles["BigInstruction"]),
            ]
            if reward_image is not None:
                result.extend([Spacer(1, 3), reward_image])
            if content.get("specificPraise"):
                result.append(Paragraph(f"<b>Specific praise:</b> {escape(str(content['specificPraise']))}", styles["BodyText"]))
            return result

        if material.type == "data_sheet":
            columns = content.get("columns")
            if not isinstance(columns, list) or not columns:
                columns = ["Opportunity", "Response", "Prompt level", "Notes"]
            columns = [str(item).replace("_", " ").title() for item in columns]
            requested_rows = content.get("opportunityRows", content.get("rowCount", 10))
            try:
                row_count = min(max(int(requested_rows), 1), 100)
            except (TypeError, ValueError):
                row_count = 10
            header_cells = [
                Paragraph(escape(column), styles["DataHeader"])
                for column in columns
            ]
            rows = [header_cells, *[[""] * len(columns) for _ in range(row_count)]]
            writable_height = (
                0.42 if styles["BodyText"].fontSize >= 12 else 0.36
            )
            table = Table(
                rows,
                repeatRows=1,
                colWidths=[usable_width / len(columns)] * len(columns),
                rowHeights=[None, *([writable_height * inch] * row_count)],
                splitByRow=1,
                splitInRow=1,
            )
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), palette["soft"]),
                        ("TEXTCOLOR", (0, 0), (-1, 0), palette["dark"]),
                        ("GRID", (0, 0), (-1, -1), 0.8, palette["border"]),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        (
                            "FONTSIZE",
                            (0, 0),
                            (-1, -1),
                            styles["DataHeader"].fontSize,
                        ),
                    ]
                )
            )
            result = [*header, table]
            definitions = content.get("promptLevelDefinitions")
            if isinstance(definitions, list):
                result.extend([
                    Spacer(1, 10), Paragraph("Prompt and independence definitions", styles["Heading3"]),
                    *[Paragraph(escape(str(item)), styles["BodyText"]) for item in definitions],
                ])
            independence_rule = str(content.get("independenceRule") or "").strip()
            rule_already_defined = any(
                independence_rule.casefold() in str(item).casefold()
                for item in definitions
            ) if isinstance(definitions, list) and independence_rule else False
            if independence_rule and not rule_already_defined:
                result.append(Paragraph(f"<b>Independent:</b> {escape(str(content['independenceRule']))}", styles["BodyText"]))
            return result

        prompts = content.get("prompts")
        if not isinstance(prompts, list) or not prompts:
            prompts = [
                "What worked well?",
                "What support was needed?",
                "What small win should we build on next?",
            ]
        result = list(header)
        is_summary = material.type in {"summary_template", "session_summary"}
        if is_summary:
            result.extend(
                [
                    Paragraph("Goal", styles["Heading3"]),
                    Paragraph(
                        escape(str(content.get("goal") or package.goal)),
                        styles["BodyText"],
                    ),
                    Spacer(1, 5),
                ]
            )
        for prompt in prompts:
            result.extend(
                [
                    Paragraph(escape(str(prompt)), styles["Heading3"]),
                    Table([[""]], colWidths=[usable_width], rowHeights=[
                              (0.30 if is_summary else 0.65) * inch
                          ],
                          style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.7, palette["border"])])),
                    Spacer(1, 1 if is_summary else 9),
                ]
            )
        return result

    @staticmethod
    def _material_header(
        title: str,
        styles: dict[str, Any],
        *,
        sheet_index: int = 1,
        sheet_count: int = 1,
    ) -> list[Any]:
        subtitle = "Ready to print, cut, laminate, or use as a full-page support."
        if sheet_count > 1:
            subtitle = (
                f"Printable sheet {sheet_index} of {sheet_count}. "
                "Use each card as a separate teaching exemplar."
            )
        return [
            Paragraph(escape(title), styles["MaterialTitle"]),
            Paragraph(subtitle, styles["Kicker"]),
            Spacer(1, 14),
        ]

    @staticmethod
    def _token_row(
        count: int,
        palette: dict[str, colors.Color],
        *,
        width: float = 6.7 * inch,
    ) -> Drawing:
        height = 0.8 * inch
        drawing = Drawing(width, height)
        spacing = width / count
        radius = min(0.3 * inch, spacing * 0.32)
        for index in range(count):
            drawing.add(
                Circle(
                    spacing * (index + 0.5),
                    height / 2,
                    radius,
                    strokeColor=palette["accent"],
                    strokeWidth=2,
                    fillColor=palette["soft"],
                )
            )
        return drawing

    @staticmethod
    def _card_labels(
        material: GeneratedMaterialDto, package: LessonPackageDto
    ) -> list[str]:
        content = V2PrintableLessonKitService._material_content(material)
        visual_items = V2PrintableLessonKitService._visual_items(content)
        if visual_items:
            labels = [
                str(item.get("label") or "").strip()
                for item in visual_items
                if str(item.get("label") or "").strip()
            ]
            if labels:
                return labels[:12]
        if material.type == "first_then_board":
            return [
                str(content.get("firstText") or "First"),
                str(content.get("thenText") or "Then"),
            ]
        for key in (
            "examples",
            "options",
            "items",
            "scenarios",
            "steps",
            "words",
            "responseOptions",
            "categories",
            "cueSteps",
        ):
            value = content.get(key)
            if isinstance(value, list) and value:
                return [str(item) for item in value[:12]]
        text = " ".join(
            str(value)
            for value in (
                content.get("phrase"),
                content.get("instruction"),
                material.title,
                package.goal,
            )
            if value
        )
        match = re.search(r"\b(\d{1,2})\s+(?:to|through|-)\s+(\d{1,2})\b", text, re.I)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            if 0 <= start <= end <= 20 and end - start <= 9:
                return [str(number) for number in range(start, end + 1)]
        label = content.get("label")
        if isinstance(label, str) and label.strip():
            return [label.strip()]
        return [
            str(
                content.get("phrase")
                or content.get("instruction")
                or material.title
                or package.goal
            )
        ]

    def _quantity_image_grid(
        self,
        content: dict[str, Any],
        quantity: Any,
        *,
        image_size: float = 0.34 * inch,
    ) -> Table | None:
        if not isinstance(quantity, int) or quantity < 2 or quantity > 10:
            return None
        cells: list[Any] = []
        for _ in range(quantity):
            image = self._embedded_image(
                content, width=image_size, height=image_size
            )
            if image is None:
                return None
            cells.append(image)
        while len(cells) % 5:
            cells.append("")
        table = Table(
            [cells[index : index + 5] for index in range(0, len(cells), 5)],
            colWidths=[image_size + 0.04 * inch] * 5,
            rowHeights=[image_size + 0.04 * inch] * (len(cells) // 5),
        )
        table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 1),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 1),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]
            )
        )
        return table

    @staticmethod
    def _visual_items(content: dict[str, Any]) -> list[dict[str, Any]]:
        value = content.get("visualItems")
        if not isinstance(value, list):
            return []
        return [dict(item) for item in value if isinstance(item, dict)]

    @classmethod
    def _has_complete_visual_set(cls, material: GeneratedMaterialDto) -> bool:
        content = cls._material_content(material)
        visual_items = cls._visual_items(content)
        if material.materialSchemaVersion == 1 and material.materialSpec is not None:
            requests = material.materialSpec.visual_asset_requests
            if requests and not visual_items:
                return all(item.status == "ready" for item in requests)
        if not visual_items:
            # Older approved packages did not have an asset plan. Keep those
            # printable while enforcing completeness for every newly planned kit.
            return True
        return all(
            bool(item.get("imageUrl") or item.get("imageBase64"))
            and str(item.get("generationStatus") or "")
            not in {"pending", "processing", "failed", "not_started"}
            for item in visual_items
        )

    def _has_resolvable_visual_set(self, material: GeneratedMaterialDto) -> bool:
        visual_items = self._visual_items(self._material_content(material))
        planned_visuals = (
            material.materialSpec.visual_asset_requests
            if material.materialSpec is not None
            else []
        )
        if planned_visuals and not visual_items:
            return False
        return all(
            not bool(item.get("required", True))
            or self._embedded_image(item) is not None
            for item in visual_items
        )

    @staticmethod
    def _material_content(material: GeneratedMaterialDto) -> dict[str, Any]:
        specification = (
            material.specification.model_dump(by_alias=True, exclude_none=True)
            if material.specification is not None
            else {}
        )
        typed = (
            material.materialSpec.content.model_dump(mode="json", by_alias=True)
            if material.materialSpec is not None else {}
        )
        return {**specification, **material.content, **typed}

    @staticmethod
    def _route_drawing(
        palette: dict[str, colors.Color], *, width: float = 6.7 * inch
    ) -> Drawing:
        height = 1.65 * inch
        drawing = Drawing(width, height)
        path = GraphicsPath(
            strokeColor=colors.HexColor("#2563eb"),
            strokeWidth=10,
            fillColor=None,
        )
        path.moveTo(width * .06, height * .30)
        path.curveTo(width * .24, height * .95, width * .42, height * .05, width * .57, height * .62)
        path.curveTo(width * .72, height * 1.0, width * .86, height * .18, width * .94, height * .55)
        drawing.add(path)
        drawing.add(Circle(width * .06, height * .30, 14, fillColor=colors.HexColor("#16a34a"), strokeColor=colors.white, strokeWidth=2))
        drawing.add(Rect(width * .91, height * .40, 28, 28, fillColor=colors.white, strokeColor=colors.HexColor("#111827"), strokeWidth=2))
        return drawing

    def _embedded_image(
        self,
        content: dict[str, Any],
        *,
        width: float = 2.5 * inch,
        height: float = 2.5 * inch,
    ) -> Image | Drawing | None:
        value = content.get("imageBase64")
        try:
            if isinstance(value, str) and value:
                raw = b64decode(value.split(",", 1)[-1])
                return Image(
                    BytesIO(raw), width=width, height=height, kind="proportional"
                )

            image_url = content.get("imageUrl")
            if isinstance(image_url, str) and image_url.startswith("data:image/svg+xml"):
                return self._deterministic_visual(content, width=width, height=height)
            if not isinstance(image_url, str) or not image_url.startswith("/storage/"):
                return None
            storage_root = Path(self.config.STORAGE_DIR).resolve()
            relative_path = image_url.removeprefix("/storage/").lstrip("/")
            source = (storage_root / relative_path).resolve()
            if storage_root not in source.parents or not source.is_file():
                return None
            return Image(
                str(source), width=width, height=height, kind="proportional"
            )
        except Exception:
            return None

    @staticmethod
    def _deterministic_visual(
        content: dict[str, Any], *, width: float, height: float
    ) -> Drawing:
        """Render planned SVG fallbacks as vector PDF shapes without rasterizing."""

        drawing = Drawing(width, height)
        constraints = content.get("designConstraints")
        constraints = constraints if isinstance(constraints, dict) else {}
        kind = str(constraints.get("fallbackKind") or content.get("role") or "symbol")
        accent = colors.HexColor(str(constraints.get("accentColor") or "#2563eb"))
        cx, cy = width / 2, height / 2
        scale = min(width, height)
        if kind == "route":
            path = GraphicsPath(
                strokeColor=accent,
                strokeWidth=max(4, scale * .06),
                fillColor=None,
            )
            path.moveTo(width * .10, height * .25)
            path.curveTo(width * .25, height * .90, width * .55, height * .08, width * .72, height * .70)
            path.curveTo(width * .82, height * .96, width * .92, height * .74, width * .90, height * .38)
            drawing.add(path)
        elif kind == "start":
            drawing.add(Circle(cx, cy, scale * .30, fillColor=colors.HexColor("#16a34a"), strokeColor=None))
            drawing.add(Polygon([cx-scale*.10,cy-scale*.16,cx+scale*.16,cy,cx-scale*.10,cy+scale*.16], fillColor=colors.white, strokeColor=None))
        elif kind == "finish":
            side = scale * .50
            x, y = cx-side/2, cy-side/2
            drawing.add(Rect(x, y, side, side, fillColor=colors.white, strokeColor=colors.HexColor("#1f2937"), strokeWidth=2))
            cell = side / 2
            drawing.add(Rect(x, y+cell, cell, cell, fillColor=colors.HexColor("#1f2937"), strokeColor=None))
            drawing.add(Rect(x+cell, y, cell, cell, fillColor=colors.HexColor("#1f2937"), strokeColor=None))
        elif kind == "timer":
            drawing.add(Circle(cx, cy, scale*.30, fillColor=colors.HexColor("#eef2ff"), strokeColor=accent, strokeWidth=max(4,scale*.06)))
            drawing.add(Line(cx, cy, cx, cy+scale*.20, strokeColor=colors.HexColor("#334155"), strokeWidth=max(3,scale*.03)))
            drawing.add(Line(cx, cy, cx+scale*.16, cy-scale*.08, strokeColor=colors.HexColor("#334155"), strokeWidth=max(3,scale*.03)))
        elif kind == "bus":
            drawing.add(Rect(width*.18, height*.30, width*.64, height*.42, rx=8, ry=8, fillColor=accent, strokeColor=None))
            drawing.add(Rect(width*.28, height*.49, width*.17, height*.13, fillColor=colors.white, strokeColor=None))
            drawing.add(Rect(width*.55, height*.49, width*.17, height*.13, fillColor=colors.white, strokeColor=None))
            drawing.add(Circle(width*.34, height*.28, scale*.07, fillColor=colors.HexColor("#334155"), strokeColor=None))
            drawing.add(Circle(width*.66, height*.28, scale*.07, fillColor=colors.HexColor("#334155"), strokeColor=None))
        else:
            concept = " ".join(
                str(constraints.get("concept") or content.get("label") or "")
                .casefold()
                .replace("-", " ")
                .split()
            )
            semantic_key = str(content.get("semanticKey") or concept)
            palette = (
                colors.HexColor("#0F766E"),
                colors.HexColor("#7C3AED"),
                colors.HexColor("#C2410C"),
                colors.HexColor("#0369A1"),
            )
            secondary = palette[sha256(semantic_key.encode("utf-8")).digest()[0] % len(palette)]
            if "art" in concept or "cleanup" in concept:
                # A brush and a cleanup bin communicate this transition without
                # putting any instructional wording inside the artwork.
                drawing.add(Rect(width*.57, height*.20, width*.25, height*.40, rx=6, ry=6, fillColor=colors.HexColor("#E2E8F0"), strokeColor=colors.HexColor("#475569"), strokeWidth=2))
                drawing.add(Line(width*.18, height*.24, width*.48, height*.76, strokeColor=accent, strokeWidth=max(6, scale*.07)))
                drawing.add(Line(width*.44, height*.70, width*.54, height*.86, strokeColor=secondary, strokeWidth=max(9, scale*.10)))
                drawing.add(Line(width*.61, height*.67, width*.78, height*.67, strokeColor=colors.HexColor("#475569"), strokeWidth=max(3, scale*.03)))
            elif "reading" in concept or "book" in concept:
                # Two open pages make the reading context visibly different
                # from a table task or route-map activity.
                drawing.add(Polygon([
                    width*.12, height*.74, width*.47, height*.64,
                    width*.47, height*.20, width*.12, height*.30,
                ], fillColor=colors.HexColor("#DBEAFE"), strokeColor=accent, strokeWidth=3))
                drawing.add(Polygon([
                    width*.88, height*.74, width*.53, height*.64,
                    width*.53, height*.20, width*.88, height*.30,
                ], fillColor=colors.HexColor("#EDE9FE"), strokeColor=secondary, strokeWidth=3))
                drawing.add(Line(width*.50, height*.20, width*.50, height*.66, strokeColor=colors.HexColor("#475569"), strokeWidth=2))
            elif "table" in concept or "item" in concept or "task" in concept:
                drawing.add(Rect(width*.14, height*.43, width*.72, height*.12, rx=5, ry=5, fillColor=accent, strokeColor=None))
                drawing.add(Line(width*.24, height*.43, width*.24, height*.18, strokeColor=colors.HexColor("#475569"), strokeWidth=max(5, scale*.05)))
                drawing.add(Line(width*.76, height*.43, width*.76, height*.18, strokeColor=colors.HexColor("#475569"), strokeWidth=max(5, scale*.05)))
                for x, fill in ((.27, secondary), (.45, colors.HexColor("#0F766E")), (.63, colors.HexColor("#C2410C"))):
                    drawing.add(Rect(width*x, height*.62, width*.10, height*.12, rx=4, ry=4, fillColor=fill, strokeColor=None))
            elif "transit" in concept or "route" in concept or "map" in concept:
                path = GraphicsPath(strokeColor=accent, strokeWidth=max(5, scale*.06), fillColor=None)
                path.moveTo(width*.12, height*.25)
                path.curveTo(width*.28, height*.82, width*.55, height*.24, width*.70, height*.68)
                path.curveTo(width*.80, height*.88, width*.88, height*.72, width*.90, height*.52)
                drawing.add(path)
                for x, y in ((.12, .25), (.55, .45), (.90, .52)):
                    drawing.add(Circle(width*x, height*y, scale*.055, fillColor=colors.white, strokeColor=secondary, strokeWidth=3))
            elif "break" in concept or "pause" in concept or "communication" in concept:
                drawing.add(Rect(width*.16, height*.34, width*.68, height*.46, rx=10, ry=10, fillColor=colors.HexColor("#EFF6FF"), strokeColor=accent, strokeWidth=3))
                drawing.add(Polygon([
                    width*.30, height*.34, width*.42, height*.34,
                    width*.30, height*.20,
                ], fillColor=colors.HexColor("#EFF6FF"), strokeColor=accent, strokeWidth=3))
                drawing.add(Rect(width*.38, height*.47, width*.07, height*.20, rx=3, ry=3, fillColor=secondary, strokeColor=None))
                drawing.add(Rect(width*.55, height*.47, width*.07, height*.20, rx=3, ry=3, fillColor=secondary, strokeColor=None))
            else:
                drawing.add(Rect(width*.20, height*.20, width*.60, height*.60, rx=12, ry=12, fillColor=colors.HexColor("#eff6ff"), strokeColor=accent, strokeWidth=3))
                drawing.add(Circle(cx, height*.58, scale*.10, fillColor=secondary, strokeColor=None))
                drawing.add(Line(width*.36, height*.34, width*.64, height*.34, strokeColor=accent, strokeWidth=max(4,scale*.06)))
        return drawing

    @staticmethod
    def _facts_table(
        package: LessonPackageDto,
        learner_code: str,
        styles: dict[str, Any],
    ) -> Table:
        label = styles["RunSheetLabel"]
        body = styles["BodyText"]
        table = Table(
            [
                [
                    Paragraph("Learner", label),
                    Paragraph("Duration", label),
                    Paragraph("Theme", label),
                ],
                [
                    Paragraph(escape(learner_code), body),
                    Paragraph(escape(package.duration), body),
                    Paragraph(escape(package.theme), body),
                ],
            ],
            colWidths=[2.2 * inch, 2.2 * inch, 2.4 * inch],
            repeatRows=1,
            splitByRow=1,
            splitInRow=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFF6FF")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1D4ED8")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        return table

    @staticmethod
    def _design_palette(content: dict[str, Any]) -> dict[str, colors.Color]:
        variant = str(content.get("selectedDesignVariant") or "calm-blue")
        palettes = {
            "calm-blue": {
                "accent": colors.HexColor("#2563EB"),
                "dark": colors.HexColor("#1E3A8A"),
                "soft": colors.HexColor("#EFF6FF"),
                "border": colors.HexColor("#93C5FD"),
            },
            "playful-green": {
                "accent": colors.HexColor("#16A34A"),
                "dark": colors.HexColor("#166534"),
                "soft": colors.HexColor("#F0FDF4"),
                "border": colors.HexColor("#86EFAC"),
            },
            "warm-gold": {
                "accent": colors.HexColor("#D97706"),
                "dark": colors.HexColor("#92400E"),
                "soft": colors.HexColor("#FFFBEB"),
                "border": colors.HexColor("#FCD34D"),
            },
        }
        return palettes.get(variant, palettes["calm-blue"])

    @staticmethod
    def _card_table_style(
        palette: dict[str, colors.Color] | None = None,
    ) -> TableStyle:
        palette = palette or V2PrintableLessonKitService._design_palette({})
        return TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 1.4, palette["accent"]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BACKGROUND", (0, 0), (-1, -1), palette["soft"]),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )

    @staticmethod
    def _visual_sheet_style() -> TableStyle:
        """Place completed artwork directly on the printable page.

        The image model is responsible only for the artwork.  The PDF should not
        wrap each image in a heavy template frame that competes with the teaching
        concept.  Whitespace separates cards while preserving a clean printable
        sheet.
        """

        return TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("LEFTPADDING", (0, 0), (-1, -1), 18),
                ("RIGHTPADDING", (0, 0), (-1, -1), 18),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ]
        )

    @staticmethod
    def _styles(text_profile: str = "standard") -> dict[str, Any]:
        policy = print_layout_policy(text_profile)
        body_size = policy.teacher_body_points
        compact_size = policy.teacher_compact_points
        compact_leading = compact_size * 1.24
        body_leading = body_size * 1.35
        styles = getSampleStyleSheet()
        styles["BodyText"].fontSize = body_size
        styles["BodyText"].leading = body_leading
        styles["BodyText"].allowWidows = 0
        styles["BodyText"].allowOrphans = 0
        styles.add(ParagraphStyle(name="Kicker", parent=styles["BodyText"], fontSize=compact_size, textColor=colors.HexColor("#475569"), leading=compact_leading, keepWithNext=1))
        styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=max(compact_size, 9), leading=max(compact_leading, 12), textColor=colors.HexColor("#334155")))
        styles.add(ParagraphStyle(name="ScenarioCompact", parent=styles["BodyText"], fontSize=compact_size, leading=compact_leading, textColor=colors.HexColor("#334155")))
        styles.add(ParagraphStyle(name="DataHeader", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=policy.teacher_data_header_points, leading=policy.teacher_data_header_points * 1.2, alignment=1, textColor=colors.HexColor("#1E3A8A")))
        styles.add(ParagraphStyle(name="RunSheetCompact", parent=styles["BodyText"], fontSize=compact_size, leading=compact_leading, textColor=colors.HexColor("#1E293B"), spaceAfter=0, spaceBefore=0))
        styles.add(ParagraphStyle(name="RunSheetLabel", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=compact_size, leading=compact_leading, textColor=colors.HexColor("#1E3A8A"), spaceAfter=0, spaceBefore=0, keepWithNext=1))
        styles.add(ParagraphStyle(name="RunSheetNote", parent=styles["BodyText"], fontSize=compact_size, leading=compact_leading, borderColor=colors.HexColor("#F59E0B"), borderWidth=0.7, borderPadding=5, backColor=colors.HexColor("#FFFBEB"), textColor=colors.HexColor("#78350F")))
        styles.add(ParagraphStyle(name="Card", parent=styles["BodyText"], fontSize=policy.learner_label_points, leading=policy.learner_label_points * 1.2, alignment=1, textColor=colors.HexColor("#0F172A")))
        styles.add(ParagraphStyle(name="BigCard", parent=styles["BodyText"], fontSize=policy.learner_primary_points, leading=policy.learner_primary_points * 1.2, alignment=1, textColor=colors.HexColor("#0F172A")))
        styles.add(ParagraphStyle(name="Token", parent=styles["BodyText"], fontSize=46 if text_profile == "large" else 42, leading=50 if text_profile == "large" else 46, alignment=1, textColor=colors.HexColor("#1D4ED8")))
        styles.add(ParagraphStyle(name="BigInstruction", parent=styles["BodyText"], fontSize=20 if text_profile == "large" else 18, leading=26 if text_profile == "large" else 24, alignment=1))
        styles.add(ParagraphStyle(name="MaterialTitle", parent=styles["Title"], fontSize=28 if text_profile == "large" else 25, leading=34 if text_profile == "large" else 30, textColor=colors.HexColor("#0F172A"), keepWithNext=1))
        styles["Title"].textColor = colors.HexColor("#0F172A")
        styles["Title"].fontSize = 24 if text_profile == "large" else styles["Title"].fontSize
        styles["Title"].leading = 29 if text_profile == "large" else styles["Title"].leading
        styles["Title"].keepWithNext = 1
        styles["Heading2"].textColor = colors.HexColor("#1D4ED8")
        styles["Heading2"].fontSize = 17 if text_profile == "large" else styles["Heading2"].fontSize
        styles["Heading2"].leading = 21 if text_profile == "large" else styles["Heading2"].leading
        styles["Heading2"].keepWithNext = 1
        styles["Heading3"].fontSize = 14 if text_profile == "large" else styles["Heading3"].fontSize
        styles["Heading3"].leading = 18 if text_profile == "large" else styles["Heading3"].leading
        styles["Heading3"].keepWithNext = 1
        return styles

    @staticmethod
    def _footer(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(
            document.leftMargin,
            0.3 * inch,
            "Autism Teaching Copilot - Teacher-reviewed printable lesson kit",
        )
        canvas.drawRightString(
            document.pagesize[0] - document.rightMargin,
            0.3 * inch,
            f"Page {canvas.getPageNumber()}",
        )
        canvas.restoreState()

    def _package(self, package_id: str) -> LessonPackageDto:
        package = self.repos.lesson_packages.get(package_id)
        if not isinstance(package, LessonPackageDto):
            raise NotFoundError("Lesson package not found")
        return package

    def _artifact_filename(
        self,
        package: LessonPackageDto,
        print_preset: str,
        page_size: str,
        text_profile: str,
    ) -> str:
        learner = re.sub(r"[^A-Za-z0-9]+", "-", self._learner_code(package)).strip("-")
        goal_text = package.goal.casefold()
        if "break" in goal_text and "request" in goal_text:
            goal_slug = "break-request"
        elif "help" in goal_text and ("ask" in goal_text or "request" in goal_text):
            goal_slug = "help-request"
        elif "count" in goal_text:
            goal_slug = "counting"
        else:
            goal = re.sub(r"[^A-Za-z0-9]+", "-", package.goal).strip("-")
            goal_slug = "-".join(
                value for value in goal.split("-") if value
            )[:80] or "lesson"
        learner_slug = learner or "learner"
        preset_suffix = {
            "complete_kit": "kit",
            "teacher_desk": "teacher-desk",
            "classroom_materials": "classroom-materials",
            "data_and_closeout": "data-and-closeout",
        }[print_preset]
        page_suffix = "a4" if page_size == "A4" else "letter"
        stem = (
            f"learner-{learner_slug}-{goal_slug}-{preset_suffix}-"
            f"{page_suffix}-{text_profile}"
        )[:170].rstrip("-")
        return f"{stem}.pdf"

    def _object_key(self) -> str:
        token = uuid4().hex
        prefix = self.config.S3_EXPORT_PREFIX.strip("/")
        return f"{prefix}/printable-kits/{token[:2]}/{token}.pdf"
