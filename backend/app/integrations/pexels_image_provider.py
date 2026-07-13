from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from app.core.config import Settings, settings
from app.integrations.image_search_provider import ImageSearchProvider
from app.schemas.v2_dto import ImageAssetDto

logger = logging.getLogger(__name__)


class PexelsImageProvider(ImageSearchProvider):
    provider_name = "pexels"
    search_url = "https://api.pexels.com/v1/search"

    def __init__(
        self, config: Settings = settings, session: requests.Session | None = None
    ) -> None:
        self._config = config
        self._session = session or requests.Session()

    def search(
        self, concept: str, material_type: str, max_results: int
    ) -> list[ImageAssetDto]:
        api_key = self._config.reveal(self._config.PEXELS_API_KEY)
        if not api_key or not concept.strip() or max_results <= 0:
            return []
        # Only the generic concept is sent externally. Learner context and records
        # are intentionally unavailable at this provider boundary.
        try:
            response = self._session.get(
                self.search_url,
                headers={"Authorization": api_key},
                params={"query": concept.strip(), "per_page": min(max_results, 80)},
                timeout=self._config.IMAGE_SEARCH_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError, TypeError):
            logger.warning("Pexels image search failed; continuing without external results")
            return []
        photos = payload.get("photos", []) if isinstance(payload, dict) else []
        if not isinstance(photos, list):
            return []
        return [
            asset
            for photo in photos[:max_results]
            if (asset := self._to_asset(photo, concept, material_type)) is not None
        ]

    @staticmethod
    def _to_asset(
        photo: Any, concept: str, material_type: str
    ) -> ImageAssetDto | None:
        if not isinstance(photo, dict) or photo.get("id") is None:
            return None
        sources = photo.get("src") if isinstance(photo.get("src"), dict) else {}
        image_url = sources.get("large2x") or sources.get("large") or sources.get("original")
        thumbnail_url = sources.get("medium") or sources.get("small")
        if not image_url:
            return None
        photographer = str(photo.get("photographer") or "Pexels contributor")
        alt_text = str(photo.get("alt") or f"Pexels photo related to {concept}")
        return ImageAssetDto(
            id=f"pexels-{photo['id']}",
            sourceType="pexels",
            title=alt_text,
            concept=concept,
            imageUrl=str(image_url),
            thumbnailUrl=str(thumbnail_url) if thumbnail_url else None,
            altText=alt_text,
            tags=[concept, material_type, "external candidate"],
            licenseInfo="Pexels License",
            attribution=f"Photo by {photographer} on Pexels",
            providerAssetId=str(photo["id"]),
            approved=False,
            safetyStatus="needs_review",
            createdAt=datetime.now(timezone.utc).isoformat(),
        )
