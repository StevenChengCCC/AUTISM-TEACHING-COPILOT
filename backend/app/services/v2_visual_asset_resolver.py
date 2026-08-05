from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64Error
from pathlib import Path
from typing import Any

from app.core.config import Settings, settings
from app.integrations.private_object_storage import (
    PrivateObjectStorage,
    get_private_object_storage,
)
from app.schemas.v2_dto import ImageAssetDto
from app.services.v2_repositories import V2Repositories, repositories


class V2VisualAssetResolver:
    """Resolve visual bytes from durable storage, DB payloads, or local cache."""

    def __init__(
        self,
        repos: V2Repositories = repositories,
        storage: PrivateObjectStorage | None = None,
        config: Settings = settings,
    ) -> None:
        self.repos = repos
        self.storage = storage or get_private_object_storage(config)
        self.config = config

    def is_resolvable(self, item: dict[str, Any]) -> bool:
        image_url = item.get("imageUrl")
        if isinstance(image_url, str) and image_url.startswith(
            "data:image/svg+xml"
        ):
            return True
        if self.read_raster_bytes(item) is not None:
            return True
        return False

    def read_raster_bytes(self, item: dict[str, Any]) -> bytes | None:
        direct = self._decode(item.get("imageBase64"))
        if direct:
            return direct

        asset = self._asset(item)
        if asset is not None:
            stored = self._decode(asset.imageBase64)
            if stored:
                return stored
            if asset.storageObjectKey:
                try:
                    return self.storage.read_bytes(
                        asset.storageObjectKey, self.config.MAX_EXPORT_BYTES
                    )
                except Exception:
                    return None
            cached = self._local_bytes(asset.imageUrl)
            if cached:
                return cached

        return self._local_bytes(item.get("imageUrl"))

    def _asset(self, item: dict[str, Any]) -> ImageAssetDto | None:
        asset_id = item.get("imageAssetId") or item.get("assetId")
        if not asset_id:
            return None
        asset = self.repos.image_assets.get(str(asset_id))
        return asset if isinstance(asset, ImageAssetDto) else None

    def _local_bytes(self, image_url: object) -> bytes | None:
        if not isinstance(image_url, str) or not image_url.startswith("/storage/"):
            return None
        storage_root = Path(self.config.STORAGE_DIR).resolve()
        relative_path = image_url.removeprefix("/storage/").lstrip("/")
        source = (storage_root / relative_path).resolve()
        if storage_root not in source.parents or not source.is_file():
            return None
        try:
            return source.read_bytes()
        except OSError:
            return None

    @staticmethod
    def _decode(value: object) -> bytes | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return b64decode(value.split(",", 1)[-1], validate=True)
        except (Base64Error, ValueError):
            return None
