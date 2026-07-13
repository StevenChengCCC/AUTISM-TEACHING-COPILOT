from __future__ import annotations

from app.core.config import Settings, settings
from app.integrations.image_search_provider import ImageSearchProvider
from app.schemas.v2_dto import ImageAssetDto


class PixabayImageProvider(ImageSearchProvider):
    """Placeholder adapter; a later round will implement the vendor contract."""

    provider_name = "pixabay"

    def __init__(self, config: Settings = settings) -> None:
        self._configured = bool(config.reveal(config.PIXABAY_API_KEY))

    def search(
        self, concept: str, material_type: str, max_results: int
    ) -> list[ImageAssetDto]:
        return []
