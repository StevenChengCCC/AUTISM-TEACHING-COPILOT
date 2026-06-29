from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.core.config import settings
from app.domain.models import ImageAsset, LessonPackage

PAGE_SIZES = {"a4": A4, "letter": letter}


def _resolve_local_image_path(value: str | None) -> Path | None:
    """Resolve an asset path/URL to an on-disk file if one exists.

    Handles direct filesystem paths and local-storage web paths such as
    ``/storage/...`` that map under ``settings.STORAGE_DIR``. Returns None for
    remote URLs or paths that do not resolve on disk.
    """
    if not value:
        return None
    candidate = Path(value)
    if candidate.is_file():
        return candidate
    storage_root = Path(settings.STORAGE_DIR)
    normalized = value.replace("\\", "/")
    if normalized.startswith("/storage/"):
        mapped = storage_root / normalized[len("/storage/") :]
        if mapped.is_file():
            return mapped
    if normalized.startswith("storage/"):
        mapped = storage_root / normalized[len("storage/") :]
        if mapped.is_file():
            return mapped
    return None


def _asset_image_path(asset: ImageAsset) -> Path | None:
    for value in (asset.local_path, asset.thumbnail_url, asset.source_url):
        resolved = _resolve_local_image_path(value)
        if resolved is not None:
            return resolved
    return None


class PrintableCardService:
    def __init__(self):
        self.cards_dir = Path(settings.STORAGE_DIR) / "cards"
        self.cards_dir.mkdir(parents=True, exist_ok=True)

    def generate_pdfs(
        self,
        lesson: LessonPackage,
        assets: list[ImageAsset],
        concept: str,
        formats: list[str],
    ) -> dict[str, str]:
        links: dict[str, str] = {}
        for fmt in formats or ["a4"]:
            normalized = fmt.lower()
            if normalized not in PAGE_SIZES:
                continue
            filename = f"lesson_{lesson.id}_cards_{normalized}.pdf"
            path = self.cards_dir / filename
            self._write_pdf(path, PAGE_SIZES[normalized], lesson, assets, concept)
            links[normalized] = f"/storage/cards/{filename}"
        return links

    def _write_pdf(
        self,
        path: Path,
        page_size: tuple[float, float],
        lesson: LessonPackage,
        assets: list[ImageAsset],
        concept: str,
    ) -> None:
        pdf = canvas.Canvas(str(path), pagesize=page_size)
        width, height = page_size
        margin = 12 * mm
        gutter = 6 * mm
        card_width = (width - 2 * margin - gutter) / 2
        card_height = (height - 2 * margin - 2 * gutter) / 3

        for index, asset in enumerate(assets):
            position = index % 6
            if index > 0 and position == 0:
                pdf.showPage()
            col = position % 2
            row = position // 2
            x = margin + col * (card_width + gutter)
            y = height - margin - (row + 1) * card_height - row * gutter
            self._draw_card(pdf, x, y, card_width, card_height, lesson, asset, concept)

        if not assets:
            self._draw_empty_card(
                pdf,
                margin,
                height - margin - card_height,
                card_width,
                card_height,
                lesson,
                concept,
            )
        pdf.save()

    def _draw_card(
        self,
        pdf: canvas.Canvas,
        x: float,
        y: float,
        width: float,
        height: float,
        lesson: LessonPackage,
        asset: ImageAsset,
        concept: str,
    ) -> None:
        pdf.setStrokeColor(colors.black)
        pdf.roundRect(x, y, width, height, 5 * mm, stroke=1, fill=0)
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(x + 8 * mm, y + height - 14 * mm, asset.title[:28])
        pdf.setFont("Helvetica", 10)
        pdf.drawString(x + 8 * mm, y + height - 22 * mm, f"Concept: {concept}")
        pdf.drawString(
            x + 8 * mm, y + height - 29 * mm, f"Goal: {lesson.target_skill[:34]}"
        )
        img_x = x + 8 * mm
        img_y = y + 28 * mm
        img_w = width - 16 * mm
        img_h = height - 68 * mm
        image_path = _asset_image_path(asset)
        if image_path is not None:
            try:
                pdf.drawImage(
                    ImageReader(str(image_path)),
                    img_x,
                    img_y,
                    width=img_w,
                    height=img_h,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception:
                # Corrupt/unsupported image: fall back to the placeholder box.
                image_path = None
        if image_path is None:
            pdf.setFillColor(colors.whitesmoke)
            pdf.rect(img_x, img_y, img_w, img_h, stroke=0, fill=1)
            pdf.setFillColor(colors.darkgray)
            pdf.setFont("Helvetica-Bold", 28)
            pdf.drawCentredString(x + width / 2, y + height / 2, "IMAGE")
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica", 8)
        pdf.drawString(
            x + 8 * mm,
            y + 18 * mm,
            f"Source: {asset.source_type} | Score: {asset.quality_score}",
        )
        pdf.drawString(
            x + 8 * mm,
            y + 12 * mm,
            f"License: {(asset.license_info or 'review required')[:48]}",
        )
        pdf.drawString(
            x + 8 * mm, y + 6 * mm, f"Approved: {'yes' if asset.approved else 'no'}"
        )

    def _draw_empty_card(
        self,
        pdf: canvas.Canvas,
        x: float,
        y: float,
        width: float,
        height: float,
        lesson: LessonPackage,
        concept: str,
    ) -> None:
        pdf.roundRect(x, y, width, height, 5 * mm, stroke=1, fill=0)
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(x + 8 * mm, y + height - 14 * mm, f"{concept} card placeholder")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(x + 8 * mm, y + height - 24 * mm, lesson.target_skill[:42])
        pdf.drawString(
            x + 8 * mm,
            y + height - 34 * mm,
            "Confirm image assets before printing final cards.",
        )
