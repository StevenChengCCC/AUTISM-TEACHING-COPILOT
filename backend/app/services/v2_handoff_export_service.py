from __future__ import annotations

from base64 import b64decode
from csv import DictWriter
from datetime import date, datetime, timedelta, timezone
from html import escape
from io import BytesIO, StringIO
import json
import logging
from pathlib import PurePosixPath
from typing import Any, Protocol
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
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

from app.core.config import Settings, settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.integrations.private_object_storage import (
    PrivateObjectStorage,
    get_private_object_storage,
)
from app.schemas.v2_dto import (
    GeneratedMaterialDto,
    HandoffExportDataDto,
    HandoffExportDownloadDto,
    LessonPackageDto,
    LessonPackageExportJobDto,
    LessonPackageExportRequest,
    TeacherHandoffExportRequest,
)
from app.services.v2_repositories import V2Repositories, repositories


EXPORT_SCHEMA_VERSION = "teacher-handoff-v1"
CONFIDENTIAL_NOTICE = (
    "CONFIDENTIAL EDUCATIONAL INFORMATION — Share only with authorized educational staff."
)
DEFAULT_EXCLUSIONS = [
    "Original uploaded documents and raw extracted text",
    "Unapproved AI drafts and internal AI conversations",
    "System prompts, provider responses, and audit logs",
    "Deleted content, credentials, and unnecessary contact details",
]
CSV_COLUMNS = [
    "sessionDate",
    "goal",
    "opportunities",
    "accuracyPercent",
    "independencePercent",
    "promptLevel",
    "signalsHighlighted",
    "teacherNotes",
]
logger = logging.getLogger(__name__)


class HandoffExportExecutor(Protocol):
    """Submission boundary that can be replaced by an SQS producer."""

    def submit(
        self, service: "V2HandoffExportService", export_id: str
    ) -> LessonPackageExportJobDto: ...


class InlineHandoffExportExecutor:
    """Reliable demo executor; persisted job state brackets synchronous work."""

    def submit(
        self, service: "V2HandoffExportService", export_id: str
    ) -> LessonPackageExportJobDto:
        return service._execute(export_id)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValidationError("Export dates must use YYYY-MM-DD format.") from exc


def _value(item: Any, camel: str, snake: str | None = None, default: Any = None) -> Any:
    return getattr(item, camel, getattr(item, snake or camel, default))


def _safe_csv(value: Any) -> str:
    text = "" if value is None else str(value)
    # Preserve the teacher-authored value while preventing spreadsheet execution.
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _safe_member_name(value: str) -> str:
    name = PurePosixPath(value).name
    if not name or name in {".", ".."} or name != value or "\\" in value:
        raise ValidationError("An export file name was unsafe.")
    return name


class V2HandoffExportService:
    """Synchronous, queue-ready teacher handoff export coordinator.

    Job state is persisted before and after work. The execution method can be
    moved behind SQS later without changing the DTO or route contract.
    """

    def __init__(
        self,
        repos: V2Repositories = repositories,
        storage: PrivateObjectStorage | None = None,
        config: Settings = settings,
        executor: HandoffExportExecutor | None = None,
    ) -> None:
        self.repos = repos
        self.config = config
        self.storage = storage or get_private_object_storage(config)
        self.executor = executor or InlineHandoffExportExecutor()

    def create(
        self, learner_id: str, request: TeacherHandoffExportRequest
    ) -> LessonPackageExportJobDto:
        learner = self.repos.learners.get(learner_id)
        if learner is None:
            raise NotFoundError("Learner not found")
        now = _utc_now()
        job = LessonPackageExportJobDto(
            exportId=f"handoff-{uuid4()}",
            learnerId=learner_id,
            packageId=request.packageIds[0] if request.packageIds else None,
            status="pending",
            format="zip",
            progressPercent=0,
            requestedAt=_iso(now),
            expiresAt=_iso(now + timedelta(days=self.config.EXPORT_RETENTION_DAYS)),
            fileName="teacher-handoff.zip",
            message="Export queued.",
            request=request,
        )
        job = self.repos.export_jobs.save(job)
        return self.executor.submit(self, job.exportId)

    def create_for_package(
        self, package_id: str, request: LessonPackageExportRequest
    ) -> LessonPackageExportJobDto:
        package = self._product_package(package_id)
        if not request.reviewedConfirmation:
            raise ValidationError("Teacher review confirmation is required before export.")
        payload = TeacherHandoffExportRequest(
            packageIds=[package_id],
            materialIds=request.materialIds,
            includePrintableMaterials=True,
            reviewedConfirmation=True,
        )
        return self.create(package.learnerId, payload)

    def list(self, learner_id: str | None = None) -> list[LessonPackageExportJobDto]:
        jobs = [
            self._expire_if_needed(job)
            for job in self.repos.export_jobs.list()
            if not learner_id or job.learnerId == learner_id
        ]
        return sorted(jobs, key=lambda item: item.requestedAt, reverse=True)

    def get(self, export_id: str) -> LessonPackageExportJobDto:
        job = self.repos.export_jobs.get(export_id)
        if job is None:
            raise NotFoundError("Export job not found")
        return self._expire_if_needed(job)

    def retry(self, export_id: str) -> LessonPackageExportJobDto:
        job = self.get(export_id)
        if job.status not in {"failed", "expired"}:
            raise ConflictError("Only failed or expired exports can be retried.")
        if job.request is None:
            raise ConflictError("The export request is no longer available for retry.")
        return self.create(job.learnerId, job.request)

    def create_download(self, export_id: str) -> HandoffExportDownloadDto:
        job = self.get(export_id)
        if job.status != "completed" or not job.storageObjectKey:
            raise ConflictError("The export is not ready for download.")
        signed = self.storage.create_presigned_get(job.storageObjectKey, job.fileName)
        updated = job.model_copy(
            update={
                "downloadCount": job.downloadCount + 1,
                "lastDownloadedAt": _iso(_utc_now()),
            }
        )
        self.repos.export_jobs.save(updated)
        self._audit("download", export_id, {"format": "zip"})
        return HandoffExportDownloadDto(
            exportId=export_id,
            downloadUrl=signed.url,
            expiresAt=_iso(signed.expires_at),
        )

    def delete(self, export_id: str) -> LessonPackageExportJobDto:
        job = self.get(export_id)
        if job.storageObjectKey:
            self.storage.delete(job.storageObjectKey)
        updated = job.model_copy(
            update={
                "status": "deleted",
                "storageObjectKey": None,
                "downloadUrl": None,
                "message": "Export deleted.",
            }
        )
        saved = self.repos.export_jobs.save(updated)
        self._audit("delete", export_id)
        return saved

    def _execute(self, export_id: str) -> LessonPackageExportJobDto:
        job = self.get(export_id)
        started = job.model_copy(
            update={
                "status": "processing",
                "progressPercent": 15,
                "startedAt": _iso(_utc_now()),
                "message": "Collecting approved handoff content.",
            }
        )
        started = self.repos.export_jobs.save(started)
        written_key: str | None = None
        try:
            data, materials = self._collect(started)
            bundle, manifest = self._build_zip(data, materials, started.request)
            if len(bundle) > self.config.MAX_EXPORT_BYTES:
                raise ValidationError("The selected export exceeds the configured size limit.")
            key = self._object_key()
            self.storage.write_bytes(key, bundle, "application/zip")
            written_key = key
            completed_at = _utc_now()
            completed = started.model_copy(
                update={
                    "status": "completed",
                    "progressPercent": 100,
                    "completedAt": _iso(completed_at),
                    "expiresAt": _iso(
                        completed_at + timedelta(days=self.config.EXPORT_RETENTION_DAYS)
                    ),
                    "fileSizeBytes": len(bundle),
                    "storageObjectKey": key,
                    "manifest": manifest,
                    "message": "Teacher handoff export is ready.",
                    "errorCode": None,
                }
            )
            saved = self.repos.export_jobs.save(completed)
            self._audit("complete", export_id, {"fileCount": len(manifest)})
            return saved
        except Exception as exc:
            logger.error(
                "export_failure",
                extra={
                    "event": "export_failure",
                    "error_code": "EXPORT_GENERATION_FAILED",
                    "error_category": type(exc).__name__,
                },
            )
            if written_key:
                try:
                    self.storage.delete(written_key)
                except Exception:
                    pass
            failed = started.model_copy(
                update={
                    "status": "failed",
                    "progressPercent": 0,
                    "errorCode": "EXPORT_GENERATION_FAILED",
                    "message": "The export could not be generated. It can be retried.",
                }
            )
            saved = self.repos.export_jobs.save(failed)
            self._audit("failed", export_id, {"errorType": type(exc).__name__})
            return saved

    def _collect(
        self, job: LessonPackageExportJobDto
    ) -> tuple[HandoffExportDataDto, list[GeneratedMaterialDto]]:
        request = job.request
        if request is None:
            raise ValidationError("Export request is missing.")
        learner = self.repos.learners.get(job.learnerId)
        if learner is None:
            raise NotFoundError("Learner not found")
        if _value(learner, "profileReviewStatus", "profile_review_status", "draft") != "confirmed":
            raise ConflictError("The learner profile must be approved before export.")

        start = _parse_date(request.dateRange.startDate)
        end = _parse_date(request.dateRange.endDate)
        if start and end and start > end:
            raise ValidationError("Export start date must be on or before end date.")

        packages = [
            item
            for item in self.repos.packages.list()
            if isinstance(item, LessonPackageDto)
            and item.learnerId == job.learnerId
            and item.status == "approved"
            and (not request.packageIds or item.id in request.packageIds)
        ]
        package_ids = {item.id for item in packages}
        materials = [
            item
            for item in self.repos.generated_materials.list()
            if isinstance(item, GeneratedMaterialDto)
            and item.packageId in package_ids
            and item.status == "approved"
            and (not request.materialIds or item.id in request.materialIds)
        ]
        progress = [
            item
            for item in self.repos.progress_data.list()
            if item.learnerId == job.learnerId and self._within(item.sessionDate, start, end)
        ]
        sessions = [
            item
            for item in self.repos.sessions.list()
            if _value(item, "learnerId", "learner_id") == job.learnerId
            and (not request.sessionIds or item.id in request.sessionIds)
            and self._within(str(_value(item, "updatedAt", "updated_at", "")), start, end)
        ]
        sections = request.sections
        selected_sections = [
            name
            for name, enabled in sections.model_dump(mode="json").items()
            if enabled
        ]
        overview = {
            "code": learner.code,
            "age": learner.age,
            "communicationMode": _value(learner, "communicationMode", "communication_mode", ""),
            "supportNeeds": _value(learner, "supportNeeds", "support_needs", []),
            "interests": learner.interests,
            "reinforcementPreferences": _value(
                learner, "reinforcementPreferences", "reinforcement_preferences", []
            ),
            "attentionProfile": _value(learner, "attentionProfile", "attention_profile", ""),
        }
        strategies = list(dict.fromkeys(
            _value(learner, "promptingPreferences", "prompting_preferences", [])
            + _value(learner, "effectiveSupports", "effective_supports", [])
            + _value(learner, "supportNeeds", "support_needs", [])
        ))
        goals = list(dict.fromkeys(
            _value(learner, "currentGoals", "current_goals", [])
            + [item.goal for item in packages]
        ))
        data = HandoffExportDataDto(
            learnerReference={"id": learner.id, "displayName": learner.code},
            selectedSections=selected_sections,
            dateRange=request.dateRange,
            learnerOverview=overview if sections.learnerOverview else None,
            teachingStrategies=strategies if sections.teachingStrategies else [],
            activeGoals=goals if sections.activeGoals else [],
            progressData=[self._progress_dict(item) for item in progress] if sections.progress else [],
            recentSessions=[self._session_dict(item) for item in sessions] if sections.recentSessions else [],
            lessonPackages=[self._package_dict(item) for item in packages] if sections.lessonPackages else [],
            approvedMaterials=[self._material_dict(item) for item in materials] if sections.approvedMaterials else [],
            transitionNotes=request.transitionNotes if sections.transitionNotes else "",
            generatedAt=_iso(_utc_now()),
            provenance={
                "exportVersion": "1.0",
                "contentPolicy": "approved-content-only",
                "aiAssistedContentLabel": True,
                "defaultExclusions": DEFAULT_EXCLUSIONS,
            },
        )
        return data, materials

    @staticmethod
    def _within(value: str, start: date | None, end: date | None) -> bool:
        if not value:
            return start is None and end is None
        try:
            current = date.fromisoformat(value[:10])
        except ValueError:
            return start is None and end is None
        return (start is None or current >= start) and (end is None or current <= end)

    @staticmethod
    def _progress_dict(item: Any) -> dict[str, Any]:
        return {column: getattr(item, column) for column in CSV_COLUMNS}

    @staticmethod
    def _session_dict(item: Any) -> dict[str, Any]:
        return {
            "id": item.id,
            "goal": item.goal,
            "status": item.status,
            "updatedAt": str(_value(item, "updatedAt", "updated_at", "")),
        }

    @staticmethod
    def _package_dict(item: LessonPackageDto) -> dict[str, Any]:
        return {
            "id": item.id,
            "goal": item.goal,
            "duration": item.duration,
            "theme": item.theme,
            "lessonBrief": item.lessonBrief,
            "summaryTemplate": item.summaryTemplate,
            "teachingFlow": [
                {
                    "title": step.title,
                    "description": step.description,
                    "duration": step.duration,
                    "teacherAction": step.teacherAction,
                    "learnerAction": step.learnerAction,
                }
                for step in item.teachingFlow
            ],
            "status": item.status,
            "aiAssisted": bool(item.aiProvider),
            "version": item.version,
        }

    @staticmethod
    def _material_dict(item: GeneratedMaterialDto) -> dict[str, Any]:
        safe_content = {
            key: value
            for key, value in item.content.items()
            if key not in {"imageBase64", "providerResponse", "imagePrompt", "rawText"}
        }
        return {
            "id": item.id,
            "packageId": item.packageId,
            "type": item.type,
            "title": item.title,
            "status": item.status,
            "content": safe_content,
            "printLayout": item.printLayout,
            "version": item.version,
            "aiAssisted": item.generationMetadata is not None,
        }

    def _build_zip(
        self,
        data: HandoffExportDataDto,
        materials: list[GeneratedMaterialDto],
        request: TeacherHandoffExportRequest | None,
    ) -> tuple[bytes, list[str]]:
        if request is None:
            raise ValidationError("Export request is missing.")
        files: dict[str, bytes] = {
            "handoff-summary.pdf": self._summary_pdf(data, request.pageSize),
            "progress-data.csv": self._progress_csv(data.progressData),
            "handoff-data.json": json.dumps(
                data.model_dump(mode="json", by_alias=True),
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
        }
        if request.includePrintableMaterials:
            for index, material in enumerate(materials, start=1):
                name = _safe_member_name(f"material-{index:02d}-{material.type}.pdf")
                files[name] = self._material_pdf(material, request.pageSize)
        file_names = list(files)
        files["README.txt"] = self._readme(data, [*file_names, "README.txt"]).encode("utf-8")
        names = [_safe_member_name(name) for name in files]
        if len(names) != len(set(name.casefold() for name in names)):
            raise ValidationError("The export contained duplicate file names.")
        output = BytesIO()
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            for name, body in files.items():
                archive.writestr(name, body)
        return output.getvalue(), names

    def _summary_pdf(self, data: HandoffExportDataDto, page_size: str) -> bytes:
        output = BytesIO()
        styles = self._styles()
        document = SimpleDocTemplate(
            output,
            pagesize=A4 if page_size == "A4" else LETTER,
            rightMargin=0.65 * inch,
            leftMargin=0.65 * inch,
            topMargin=0.7 * inch,
            bottomMargin=0.65 * inch,
            title="Teacher Handoff Summary",
        )
        story: list[Any] = [
            Paragraph("Teacher Handoff Summary", styles["Title"]),
            Paragraph(CONFIDENTIAL_NOTICE, styles["Notice"]),
            Paragraph(
                f"Learner: {escape(str(data.learnerReference.get('displayName', 'Learner')))}<br/>"
                f"Generated: {escape(data.generatedAt)}<br/>Export version: 1.0",
                styles["BodyText"],
            ),
            Spacer(1, 12),
        ]
        if data.learnerOverview:
            story += self._pdf_section("Learner Overview", [
                f"Communication: {data.learnerOverview.get('communicationMode', '')}",
                f"Support needs: {', '.join(data.learnerOverview.get('supportNeeds', []))}",
                f"Interests: {', '.join(data.learnerOverview.get('interests', []))}",
                f"Reinforcement preferences: {', '.join(data.learnerOverview.get('reinforcementPreferences', []))}",
            ], styles)
        story += self._pdf_section("Approved Teaching Strategies", data.teachingStrategies, styles)
        story += self._pdf_section("Active Goals", data.activeGoals, styles)
        if data.progressData:
            story.append(Paragraph("Progress", styles["Heading2"]))
            rows = [["Date", "Goal", "Accuracy", "Independence", "Prompt"]]
            rows += [[
                item["sessionDate"], item["goal"], f"{item['accuracyPercent']}%",
                f"{item['independencePercent']}%", item["promptLevel"],
            ] for item in data.progressData]
            table = Table(rows, repeatRows=1, colWidths=[0.85*inch, 2.3*inch, 0.8*inch, 0.9*inch, 0.8*inch])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF2FF")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ]))
            story += [table, Spacer(1, 12)]
        for package in data.lessonPackages:
            story += self._pdf_section(
                f"Approved Lesson Package: {package['goal']}",
                [package["lessonBrief"], f"Duration: {package['duration']} · Theme: {package['theme']}"],
                styles,
            )
        if data.approvedMaterials:
            story += self._pdf_section(
                "Approved Materials",
                [f"{item['title']} ({item['type']})" for item in data.approvedMaterials],
                styles,
            )
        if data.transitionNotes:
            story += self._pdf_section("Teacher Transition Notes", [data.transitionNotes], styles)
        story += [PageBreak(), Paragraph("Export Notes", styles["Heading2"])]
        story += [Paragraph(f"• {item}", styles["BodyText"]) for item in DEFAULT_EXCLUSIONS]
        story.append(Paragraph("AI-assisted content is labeled in the structured data and remains subject to teacher review.", styles["Notice"]))
        document.build(story, onFirstPage=self._page_footer, onLaterPages=self._page_footer)
        return output.getvalue()

    def _material_pdf(self, material: GeneratedMaterialDto, page_size: str) -> bytes:
        output = BytesIO()
        styles = self._styles()
        document = SimpleDocTemplate(
            output,
            pagesize=A4 if page_size == "A4" else LETTER,
            rightMargin=0.65 * inch,
            leftMargin=0.65 * inch,
            topMargin=0.7 * inch,
            bottomMargin=0.65 * inch,
            title=material.title,
        )
        story: list[Any] = [Paragraph(escape(material.title), styles["Title"])]
        image_data = material.content.get("imageBase64")
        if image_data:
            try:
                raw = image_data.split(",", 1)[-1]
                story += [Image(BytesIO(b64decode(raw)), width=3.5*inch, height=3.5*inch), Spacer(1, 12)]
            except Exception:
                pass
        for key, value in material.content.items():
            if key in {"imageBase64", "providerResponse", "imagePrompt", "rawText"}:
                continue
            label = key.replace("_", " ").replace("Text", " text").title()
            rendered = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
            story.append(KeepTogether([Paragraph(escape(label), styles["Heading2"]), Paragraph(escape(rendered), styles["BodyText"])]))
            story.append(Spacer(1, 8))
        story.append(Paragraph("AI-assisted educational material — teacher reviewed and approved.", styles["Notice"]))
        document.build(story, onFirstPage=self._page_footer, onLaterPages=self._page_footer)
        return output.getvalue()

    @staticmethod
    def _pdf_section(title: str, values: list[str], styles: dict[str, Any]) -> list[Any]:
        if not values:
            return []
        result: list[Any] = [Paragraph(escape(title), styles["Heading2"])]
        result.extend(Paragraph(f"• {escape(str(value))}", styles["BodyText"]) for value in values if value)
        result.append(Spacer(1, 10))
        return result

    @staticmethod
    def _styles() -> dict[str, Any]:
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name="Notice", parent=styles["BodyText"], textColor=colors.HexColor("#475569"), fontSize=8.5, leading=11, spaceBefore=5, spaceAfter=8))
        styles["Title"].textColor = colors.HexColor("#0F172A")
        styles["Heading2"].textColor = colors.HexColor("#1D4ED8")
        styles["BodyText"].leading = 15
        return styles

    @staticmethod
    def _page_footer(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(document.leftMargin, 0.35 * inch, "Lesson Kit Studio · Authorized educational handoff")
        canvas.drawRightString(document.pagesize[0] - document.rightMargin, 0.35 * inch, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    @staticmethod
    def _progress_csv(rows: list[dict[str, Any]]) -> bytes:
        output = StringIO(newline="")
        writer = DictWriter(output, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _safe_csv(row.get(key)) for key in CSV_COLUMNS})
        return ("\ufeff" + output.getvalue()).encode("utf-8")

    @staticmethod
    def _readme(data: HandoffExportDataDto, files: list[str]) -> str:
        return "\n".join([
            "LESSON KIT STUDIO — TEACHER HANDOFF EXPORT",
            "",
            CONFIDENTIAL_NOTICE,
            f"Export schema: {EXPORT_SCHEMA_VERSION}",
            f"Generated: {data.generatedAt}",
            "",
            "Included files:",
            *[f"- {name}" for name in files],
            "",
            "Default exclusions:",
            *[f"- {item}" for item in DEFAULT_EXCLUSIONS],
            "",
            "This export supports an authorized educational handoff. Teacher confirmation is not a claim of legal compliance.",
        ])

    def _object_key(self) -> str:
        token = uuid4().hex
        prefix = self.config.S3_EXPORT_PREFIX.strip("/")
        return f"{prefix}/{token[:2]}/{token}.zip"

    def _expire_if_needed(self, job: LessonPackageExportJobDto) -> LessonPackageExportJobDto:
        if job.status != "completed" or not job.expiresAt:
            return job
        expires = datetime.fromisoformat(job.expiresAt.replace("Z", "+00:00"))
        if expires > _utc_now():
            return job
        deletion_failed = False
        if job.storageObjectKey:
            try:
                self.storage.delete(job.storageObjectKey)
            except Exception:
                deletion_failed = True
        expired = job.model_copy(update={
            "status": "expired",
            "storageObjectKey": job.storageObjectKey if deletion_failed else None,
            "message": "Export expired; private object cleanup is pending." if deletion_failed else "Export expired.",
        })
        return self.repos.export_jobs.save(expired)

    def _product_package(self, package_id: str) -> LessonPackageDto:
        package = self.repos.packages.get(package_id)
        if package is None or not isinstance(package, LessonPackageDto):
            raise NotFoundError("Lesson package not found")
        return package

    def _audit(self, action: str, export_id: str, metadata: dict | None = None) -> None:
        recorder = getattr(self.repos, "record_audit", None)
        if callable(recorder):
            try:
                recorder(action, "teacher_handoff_export", export_id, metadata or {})
            except Exception:
                # Artifact/job correctness must not be rolled back by telemetry.
                pass
