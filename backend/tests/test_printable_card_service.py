from pathlib import Path

from app.domain.models import ImageAsset, LessonPackage
from app.services.printable_card_service import (
    PrintableCardService,
    _asset_image_path,
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
