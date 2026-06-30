from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

from app.core.config import settings
from app.domain.models import ImageAsset, LessonPackage

PAGE_SIZES = {"a4": A4, "letter": letter}


def _wrap_title(
    pdf: canvas.Canvas,
    title: str,
    max_width: float,
    max_lines: int = 2,
    sizes: tuple[int, ...] = (24, 20, 16),
) -> tuple[list[str], int]:
    """Wrap ``title`` to ``max_width``, dropping a font size if it overflows.

    Returns the wrapped lines and the chosen font size. The largest size that
    fits within ``max_lines`` wins; if none fit, the smallest size is used and
    the title is truncated to ``max_lines`` (with an ellipsis) so it never
    clips off the card edge.
    """
    for size in sizes:
        lines = simpleSplit(title, "Helvetica-Bold", size, max_width)
        if len(lines) <= max_lines:
            return lines, size
    smallest = sizes[-1]
    lines = simpleSplit(title, "Helvetica-Bold", smallest, max_width)
    trimmed = lines[:max_lines]
    if len(lines) > max_lines and trimmed:
        trimmed[-1] = trimmed[-1].rstrip() + "…"
    return trimmed, smallest


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
        margin = 14 * mm
        card_x = margin
        card_y = margin
        card_width = width - 2 * margin
        card_height = height - 2 * margin

        # One large, image-dominant card per page so the printout is usable.
        for index, asset in enumerate(assets):
            if index > 0:
                pdf.showPage()
            self._draw_card(
                pdf, card_x, card_y, card_width, card_height, lesson, asset, concept
            )

        if not assets:
            self._draw_empty_card(
                pdf, card_x, card_y, card_width, card_height, lesson, concept
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
        pad = 10 * mm
        pdf.setStrokeColor(colors.black)
        pdf.roundRect(x, y, width, height, 6 * mm, stroke=1, fill=0)

        inner_x = x + pad
        inner_w = width - 2 * pad

        # --- Wrapped, non-clipping title at the top of the card ---
        pdf.setFillColor(colors.black)
        title_lines, title_size = _wrap_title(pdf, asset.title, inner_w)
        line_gap = title_size + 4
        title_top = y + height - pad - title_size
        pdf.setFont("Helvetica-Bold", title_size)
        for line_index, line in enumerate(title_lines):
            pdf.drawString(inner_x, title_top - line_index * line_gap, line)
        title_block_bottom = title_top - (len(title_lines) - 1) * line_gap

        pdf.setFont("Helvetica", 11)
        subtitle_y = title_block_bottom - 8 * mm
        pdf.drawString(inner_x, subtitle_y, f"Concept: {concept}")
        subtitle_y -= 6 * mm
        goal_lines = simpleSplit(
            f"Goal: {lesson.target_skill}", "Helvetica", 11, inner_w
        )
        for goal_line in goal_lines[:2]:
            pdf.drawString(inner_x, subtitle_y, goal_line)
            subtitle_y -= 6 * mm

        # --- Metadata footer reserved at the very bottom ---
        footer_height = 22 * mm

        # --- Dominant centered image between subtitle and footer ---
        img_top = subtitle_y - 4 * mm
        img_bottom = y + footer_height
        img_x = inner_x
        img_w = inner_w
        img_h = img_top - img_bottom
        image_path = _asset_image_path(asset)
        if image_path is not None and img_h > 0:
            try:
                pdf.drawImage(
                    ImageReader(str(image_path)),
                    img_x,
                    img_bottom,
                    width=img_w,
                    height=img_h,
                    preserveAspectRatio=True,
                    anchor="c",
                    mask="auto",
                )
            except Exception:
                # Corrupt/unsupported image: fall back to the placeholder box.
                image_path = None
        if image_path is None or img_h <= 0:
            pdf.setFillColor(colors.whitesmoke)
            pdf.rect(img_x, img_bottom, img_w, max(img_h, 0), stroke=0, fill=1)
            pdf.setFillColor(colors.darkgray)
            pdf.setFont("Helvetica-Bold", 32)
            pdf.drawCentredString(
                x + width / 2, img_bottom + max(img_h, 0) / 2, "IMAGE"
            )

        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica", 8)
        pdf.drawString(
            inner_x,
            y + 16 * mm,
            f"Source: {asset.source_type} | Score: {asset.quality_score}",
        )
        pdf.drawString(
            inner_x,
            y + 11 * mm,
            f"License: {(asset.license_info or 'review required')[:80]}",
        )
        pdf.drawString(
            inner_x, y + 6 * mm, f"Approved: {'yes' if asset.approved else 'no'}"
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
        pad = 10 * mm
        inner_x = x + pad
        inner_w = width - 2 * pad
        pdf.setStrokeColor(colors.black)
        pdf.roundRect(x, y, width, height, 6 * mm, stroke=1, fill=0)
        pdf.setFillColor(colors.black)
        title_lines, title_size = _wrap_title(
            pdf, f"{concept} card placeholder", inner_w
        )
        title_top = y + height - pad - title_size
        pdf.setFont("Helvetica-Bold", title_size)
        for line_index, line in enumerate(title_lines):
            pdf.drawString(inner_x, title_top - line_index * (title_size + 4), line)
        pdf.setFont("Helvetica", 11)
        for offset, line in enumerate(
            simpleSplit(lesson.target_skill, "Helvetica", 11, inner_w)[:2]
        ):
            pdf.drawString(
                inner_x, title_top - (len(title_lines) + offset) * (title_size + 4), line
            )
        pdf.drawString(
            inner_x,
            y + 12 * mm,
            "Confirm image assets before printing final cards.",
        )
