from __future__ import annotations

from base64 import b64decode
from datetime import datetime, timedelta, timezone
from html import escape
from io import BytesIO
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.graphics.shapes import Circle, Drawing
from reportlab.platypus import (
    Image,
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
    HandoffExportDownloadDto,
    LessonPackageDto,
    LessonPackageExportJobDto,
    PrintableLessonKitRequest,
)
from app.services.v2_repositories import V2Repositories, repositories


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


class V2PrintableLessonKitService:
    """Build one classroom-ready PDF instead of a data handoff ZIP."""

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
        if package.status != "approved":
            raise ConflictError("Approve the lesson package before creating a print kit.")
        requested_ids = set(request.materialIds)
        materials = [
            item
            for item in self.repos.generated_materials.for_package(package_id)
            if isinstance(item, GeneratedMaterialDto)
            and (not requested_ids or item.id in requested_ids)
        ]
        if requested_ids - {item.id for item in materials}:
            raise ValidationError("One or more selected materials were not found.")
        if not materials:
            materials = list(package.materials)
        unapproved = [item.title for item in materials if item.status != "approved"]
        if unapproved:
            raise ConflictError(
                "Approve all selected materials before printing: "
                + ", ".join(unapproved)
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
            fileName="complete-lesson-kit.pdf",
            message="Building the complete printable lesson kit.",
        )
        self.repos.export_jobs.save(job)
        key: str | None = None
        try:
            body = self._build_pdf(package, materials, request.pageSize)
            if len(body) > self.config.MAX_EXPORT_BYTES:
                raise ValidationError("The printable lesson kit is too large.")
            key = self._object_key()
            self.storage.write_bytes(key, body, "application/pdf")
            completed = job.model_copy(
                update={
                    "status": "completed",
                    "progressPercent": 100,
                    "completedAt": _iso(_now()),
                    "fileSizeBytes": len(body),
                    "storageObjectKey": key,
                    "manifest": [
                        "lesson plan",
                        *[f"printable: {item.title}" for item in materials],
                    ],
                    "message": "Complete printable lesson kit is ready.",
                }
            )
            return self.repos.export_jobs.save(completed)
        except Exception:
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
            raise

    def create_download(self, export_id: str) -> HandoffExportDownloadDto:
        job = self.repos.export_jobs.get(export_id)
        if (
            not isinstance(job, LessonPackageExportJobDto)
            or job.format != "pdf"
            or not job.exportId.startswith("print-kit-")
        ):
            raise NotFoundError("Printable lesson kit not found")
        if job.status != "completed" or not job.storageObjectKey:
            raise ConflictError("The printable lesson kit is not ready.")
        signed = self.storage.create_presigned_get(
            job.storageObjectKey, job.fileName
        )
        self.repos.export_jobs.save(
            job.model_copy(
                update={
                    "downloadCount": job.downloadCount + 1,
                    "lastDownloadedAt": _iso(_now()),
                }
            )
        )
        return HandoffExportDownloadDto(
            exportId=job.exportId,
            downloadUrl=signed.url,
            expiresAt=_iso(signed.expires_at),
        )

    def _build_pdf(
        self,
        package: LessonPackageDto,
        materials: list[GeneratedMaterialDto],
        page_size: str,
    ) -> bytes:
        output = BytesIO()
        styles = self._styles()
        document = SimpleDocTemplate(
            output,
            pagesize=A4 if page_size == "A4" else LETTER,
            rightMargin=0.55 * inch,
            leftMargin=0.55 * inch,
            topMargin=0.55 * inch,
            bottomMargin=0.55 * inch,
            title="Complete Lesson Kit",
        )
        content = package.documentContent or {}
        story: list[Any] = [
            Paragraph(escape(str(content.get("title") or package.goal)), styles["Title"]),
            Paragraph("Complete printable lesson kit", styles["Kicker"]),
            Spacer(1, 8),
            self._facts_table(package),
            Spacer(1, 14),
            Paragraph("Lesson goal", styles["Heading2"]),
            Paragraph(escape(str(content.get("goal") or package.goal)), styles["BodyText"]),
            Paragraph("Lesson brief", styles["Heading2"]),
            Paragraph(
                escape(str(content.get("lessonBrief") or package.lessonBrief)),
                styles["BodyText"],
            ),
            Paragraph("Teaching flow", styles["Heading2"]),
        ]
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
        for material in materials:
            story.extend([PageBreak(), *self._material_story(material, package, styles)])
        document.build(story, onFirstPage=self._footer, onLaterPages=self._footer)
        return output.getvalue()

    def _material_story(
        self,
        material: GeneratedMaterialDto,
        package: LessonPackageDto,
        styles: dict[str, Any],
    ) -> list[Any]:
        content = self._material_content(material)
        title = escape(material.title)
        header: list[Any] = [
            Paragraph(title, styles["MaterialTitle"]),
            Paragraph("Cut, laminate, or use as a full-page support.", styles["Kicker"]),
            Spacer(1, 10),
        ]
        image = self._embedded_image(content)
        card_types = {
            "quantity_cards",
            "visual_card",
            "scenario_cards",
            "sequence_cards",
            "social_narrative",
            "sorting_page",
            "visual_schedule",
            "task_analysis_cards",
            "emotion_scale",
        }
        if image is not None and material.type not in card_types:
            header.extend([image, Spacer(1, 10)])

        if material.type == "matching_page":
            labels = self._card_labels(material, package)
            visual_items = self._visual_items(content)
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
            table = Table(
                rows,
                colWidths=[1.0 * inch, 0.5 * inch, 5.2 * inch],
                rowHeights=[0.9 * inch] * len(rows),
            )
            table.setStyle(self._card_table_style())
            return [*header, table]

        if material.type in card_types:
            labels = self._card_labels(material, package)
            visual_items = self._visual_items(content)
            cells: list[Any] = []
            for index, label in enumerate(labels):
                visual_item = next(
                    (
                        item
                        for item in visual_items
                        if str(item.get("label") or "") == label
                    ),
                    visual_items[index] if index < len(visual_items) else (
                        visual_items[0] if visual_items else content
                    ),
                )
                card_image = self._embedded_image(
                    visual_item, width=1.05 * inch, height=1.05 * inch
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
            if len(cells) % 2:
                cells.append(Paragraph("", styles["Card"]))
            table = Table(
                [cells[index : index + 2] for index in range(0, len(cells), 2)],
                colWidths=[3.45 * inch, 3.45 * inch],
                rowHeights=[2.0 * inch] * ((len(cells) + 1) // 2),
            )
            table.setStyle(self._card_table_style())
            return [*header, table]

        if material.type in {"help_card", "break_card", "teacher_cue_card"}:
            phrase = str(
                content.get("phrase")
                or content.get("requestText")
                or content.get("instruction")
                or package.goal
            )
            return [
                *header,
                Table(
                    [[Paragraph(escape(phrase), styles["BigCard"])]],
                    colWidths=[6.8 * inch],
                    rowHeights=[4.4 * inch],
                    style=self._card_table_style(),
                ),
            ]

        if material.type in {"choice_board", "first_then_board", "core_word_board"}:
            labels = self._card_labels(material, package)[
                : (6 if material.type == "core_word_board" else 2)
            ]
            visual_items = self._visual_items(content)
            minimum = 4 if material.type == "core_word_board" else 2
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
            if material.type == "core_word_board":
                if len(choice_cells) % 2:
                    choice_cells.append(Paragraph("", styles["Card"]))
                rows = [
                    choice_cells[index : index + 2]
                    for index in range(0, len(choice_cells), 2)
                ]
                table = Table(
                    rows,
                    colWidths=[3.35 * inch, 3.35 * inch],
                    rowHeights=[1.75 * inch] * len(rows),
                )
            else:
                table = Table(
                    [choice_cells],
                    colWidths=[3.35 * inch, 3.35 * inch],
                    rowHeights=[4.0 * inch],
                )
            table.setStyle(self._card_table_style())
            return [*header, table]

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
            return [
                *header,
                Paragraph(
                    escape(str(content.get("instruction") or "Earn tokens, then choose a reward.")),
                    styles["BigInstruction"],
                ),
                Spacer(1, 22),
                self._token_row(count),
                Spacer(1, 28),
                Paragraph(f"Reward: <b>{reward}</b>", styles["BigInstruction"]),
            ]

        if material.type == "data_sheet":
            columns = content.get("columns")
            if not isinstance(columns, list) or not columns:
                columns = ["Opportunity", "Response", "Prompt level", "Notes"]
            columns = [str(item) for item in columns[:6]]
            rows = [columns, *[[""] * len(columns) for _ in range(10)]]
            table = Table(
                rows,
                repeatRows=1,
                colWidths=[6.8 * inch / len(columns)] * len(columns),
                rowHeights=[0.35 * inch] * len(rows),
            )
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DBEAFE")),
                        ("GRID", (0, 0), (-1, -1), 0.8, colors.HexColor("#64748B")),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ]
                )
            )
            return [*header, table]

        prompts = content.get("prompts")
        if not isinstance(prompts, list) or not prompts:
            prompts = [
                "What worked well?",
                "What support was needed?",
                "What small win should we build on next?",
            ]
        result = list(header)
        for prompt in prompts:
            result.extend(
                [
                    Paragraph(escape(str(prompt)), styles["Heading3"]),
                    Table([[""]], colWidths=[6.8 * inch], rowHeights=[0.65 * inch],
                          style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.7, colors.HexColor("#94A3B8"))])),
                    Spacer(1, 9),
                ]
            )
        return result

    @staticmethod
    def _token_row(count: int) -> Drawing:
        width = 6.7 * inch
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
                    strokeColor=colors.HexColor("#2563EB"),
                    strokeWidth=2,
                    fillColor=colors.white,
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
                return labels[:8]
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
                return [str(item) for item in value[:8]]
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
        self, content: dict[str, Any], quantity: Any
    ) -> Table | None:
        if not isinstance(quantity, int) or quantity < 2 or quantity > 10:
            return None
        cells: list[Any] = []
        for _ in range(quantity):
            image = self._embedded_image(
                content, width=0.34 * inch, height=0.34 * inch
            )
            if image is None:
                return None
            cells.append(image)
        while len(cells) % 5:
            cells.append("")
        table = Table(
            [cells[index : index + 5] for index in range(0, len(cells), 5)],
            colWidths=[0.38 * inch] * 5,
            rowHeights=[0.38 * inch] * (len(cells) // 5),
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

    @staticmethod
    def _material_content(material: GeneratedMaterialDto) -> dict[str, Any]:
        specification = (
            material.specification.model_dump(by_alias=True, exclude_none=True)
            if material.specification is not None
            else {}
        )
        return {**specification, **material.content}

    def _embedded_image(
        self,
        content: dict[str, Any],
        *,
        width: float = 2.5 * inch,
        height: float = 2.5 * inch,
    ) -> Image | None:
        value = content.get("imageBase64")
        try:
            if isinstance(value, str) and value:
                raw = b64decode(value.split(",", 1)[-1])
                return Image(BytesIO(raw), width=width, height=height)

            image_url = content.get("imageUrl")
            if not isinstance(image_url, str) or not image_url.startswith("/storage/"):
                return None
            storage_root = Path(self.config.STORAGE_DIR).resolve()
            relative_path = image_url.removeprefix("/storage/").lstrip("/")
            source = (storage_root / relative_path).resolve()
            if storage_root not in source.parents or not source.is_file():
                return None
            return Image(str(source), width=width, height=height)
        except Exception:
            return None

    @staticmethod
    def _facts_table(package: LessonPackageDto) -> Table:
        table = Table(
            [
                ["Learner", "Duration", "Theme"],
                [package.learnerId, package.duration, package.theme],
            ],
            colWidths=[2.2 * inch, 2.2 * inch, 2.4 * inch],
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
    def _card_table_style() -> TableStyle:
        return TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 1.4, colors.HexColor("#2563EB")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )

    @staticmethod
    def _styles() -> dict[str, Any]:
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name="Kicker", parent=styles["BodyText"], fontSize=9, textColor=colors.HexColor("#64748B"), leading=12))
        styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=9, leading=12, textColor=colors.HexColor("#334155")))
        styles.add(ParagraphStyle(name="Card", parent=styles["BodyText"], fontSize=22, leading=26, alignment=1, textColor=colors.HexColor("#0F172A")))
        styles.add(ParagraphStyle(name="BigCard", parent=styles["BodyText"], fontSize=30, leading=36, alignment=1, textColor=colors.HexColor("#0F172A")))
        styles.add(ParagraphStyle(name="Token", parent=styles["BodyText"], fontSize=42, leading=46, alignment=1, textColor=colors.HexColor("#1D4ED8")))
        styles.add(ParagraphStyle(name="BigInstruction", parent=styles["BodyText"], fontSize=18, leading=24, alignment=1))
        styles.add(ParagraphStyle(name="MaterialTitle", parent=styles["Title"], fontSize=25, textColor=colors.HexColor("#0F172A")))
        styles["Title"].textColor = colors.HexColor("#0F172A")
        styles["Heading2"].textColor = colors.HexColor("#1D4ED8")
        styles["BodyText"].leading = 15
        return styles

    @staticmethod
    def _footer(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(
            document.leftMargin,
            0.3 * inch,
            "Autism Teaching Copilot · Teacher-reviewed printable lesson kit",
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

    def _object_key(self) -> str:
        token = uuid4().hex
        prefix = self.config.S3_EXPORT_PREFIX.strip("/")
        return f"{prefix}/printable-kits/{token[:2]}/{token}.pdf"
