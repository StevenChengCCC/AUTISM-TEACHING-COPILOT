from pathlib import Path

from reportlab.pdfgen import canvas

from app.domain.models import ImageAsset, LessonPackage
from app.services.printable_card_service import (
    PrintableCardService,
    _asset_image_path,
    _wrap_title,
)

FIXTURE_PNG = Path(__file__).parent / "fixtures" / "sample_card.png"


def _lesson() -> LessonPackage:
    return LessonPackage(
        id=42,
        child_id=1,
        target_skill="recognize apple",
        duration_minutes=10,
        package_json="{}",
    )


def _asset(**kwargs) -> ImageAsset:
    base = dict(
        id=1,
        title="Apple photo",
        source_type="searched",
        concept="apple",
        quality_score=80,
        approved=True,
    )
    base.update(kwargs)
    return ImageAsset(**base)


def test_resolve_local_path_on_disk():
    assert _asset_image_path(_asset(local_path=str(FIXTURE_PNG))) == FIXTURE_PNG


def test_resolve_returns_none_for_remote_url():
    asset = _asset(source_url="https://example.com/apple.png")
    assert _asset_image_path(asset) is None


def test_pdf_embeds_real_image_when_local_path_present(tmp_path):
    service = PrintableCardService()
    page_size = (595.27, 841.89)  # A4 in points

    with_image = tmp_path / "with_image.pdf"
    service._write_pdf(
        with_image,
        page_size,
        _lesson(),
        [_asset(local_path=str(FIXTURE_PNG))],
        "apple",
    )

    placeholder_only = tmp_path / "placeholder.pdf"
    service._write_pdf(
        placeholder_only,
        page_size,
        _lesson(),
        [_asset(local_path=None)],
        "apple",
    )

    assert with_image.exists() and placeholder_only.exists()
    # An embedded raster image makes the PDF materially larger than the
    # placeholder-only version, which contains no image stream.
    assert with_image.stat().st_size > placeholder_only.stat().st_size


def test_pdf_falls_back_to_placeholder_without_crash(tmp_path):
    service = PrintableCardService()
    out = tmp_path / "fallback.pdf"
    service._write_pdf(
        out,
        (595.27, 841.89),
        _lesson(),
        [_asset(local_path="/does/not/exist.png")],
        "apple",
    )
    assert out.exists() and out.stat().st_size > 0


def test_generate_pdfs_both_formats_with_real_image(tmp_path, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "STORAGE_DIR", str(tmp_path))
    service = PrintableCardService()

    links = service.generate_pdfs(
        lesson=_lesson(),
        assets=[
            _asset(
                title="Apple (real photo-style card) for receptive identification",
                local_path=str(FIXTURE_PNG),
            )
        ],
        concept="apple",
        formats=["a4", "letter"],
    )

    assert set(links) == {"a4", "letter"}
    for fmt in ("a4", "letter"):
        pdf_path = tmp_path / "cards" / f"lesson_42_cards_{fmt}.pdf"
        assert pdf_path.exists() and pdf_path.stat().st_size > 0


def _page_count(pdf_bytes: bytes) -> int:
    # reportlab writes uncompressed page dictionaries; count the page objects.
    return pdf_bytes.count(b"/Type /Page\n") + pdf_bytes.count(b"/Type /Page ")


def test_one_large_card_per_page(tmp_path):
    service = PrintableCardService()
    out = tmp_path / "multi.pdf"
    service._write_pdf(
        out,
        (595.27, 841.89),
        _lesson(),
        [
            _asset(id=1, title="Apple", local_path=str(FIXTURE_PNG)),
            _asset(id=2, title="Dog", local_path=str(FIXTURE_PNG)),
            _asset(id=3, title="Cup", local_path=str(FIXTURE_PNG)),
        ],
        "apple",
    )
    assert _page_count(out.read_bytes()) == 3


def test_long_title_wraps_without_clipping(tmp_path):
    pdf = canvas.Canvas(str(tmp_path / "measure.pdf"))
    long_title = "Apple (real photo-style card) for receptive identification practice"
    max_width = 400
    lines, size = _wrap_title(pdf, long_title, max_width)

    assert 1 <= len(lines) <= 2
    # Every wrapped line fits within the available width at the chosen size.
    for line in lines:
        assert pdf.stringWidth(line, "Helvetica-Bold", size) <= max_width
    # The closing paren is preserved, not clipped off mid-word.
    assert "card)" in " ".join(lines)
