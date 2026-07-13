from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.config import Settings, settings
from app.schemas.v2_dto import ImageAssetDto


class ImageSearchProvider(ABC):
    """Backend-only boundary for optional public image catalog searches."""

    provider_name: str

    @abstractmethod
    def search(
        self, concept: str, material_type: str, max_results: int
    ) -> list[ImageAssetDto]:
        raise NotImplementedError


def get_image_search_providers(
    config: Settings = settings,
) -> list[ImageSearchProvider]:
    from app.integrations.pexels_image_provider import PexelsImageProvider
    from app.integrations.pixabay_image_provider import PixabayImageProvider
    from app.integrations.unsplash_image_provider import UnsplashImageProvider

    return [
        PexelsImageProvider(config),
        PixabayImageProvider(config),
        UnsplashImageProvider(config),
    ]
