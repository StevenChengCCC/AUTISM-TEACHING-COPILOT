from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64Error
import logging
from pathlib import Path
import re
from uuid import uuid4

from app.core.config import Settings, settings
from app.core.exceptions import NotFoundError, ValidationError
from app.integrations.ai_provider import V2AIProvider, get_v2_ai_provider
from app.integrations.image_search_provider import (
    ImageSearchProvider,
    get_image_search_providers,
)
from app.schemas.v2_dto import (
    ApproveImageAssetRequest,
    ImageAssetDto,
    ImageCandidateResponse,
    ImageSearchRequest,
    GenerateImageCandidateRequest,
    LearnerProfile,
    utc_now,
)
from app.services.v2_material_service import V2MaterialService
from app.services.v2_repositories import V2Repositories, repositories


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


logger = logging.getLogger(__name__)


class V2ImageAssetService:
    """Deterministic internal-first image asset lookup boundary.

    External providers receive generic concept text only. Image generation remains
    outside this service and is never called by candidate lookup.
    """

    def __init__(
        self,
        repos: V2Repositories = repositories,
        external_providers: list[ImageSearchProvider] | None = None,
        ai: V2AIProvider | None = None,
        config: Settings = settings,
    ):
        self.repos = repos
        self.config = config
        self.ai = ai or get_v2_ai_provider(config)
        self.external_providers = (
            get_image_search_providers(config)
            if external_providers is None
            else external_providers
        )

    def list_assets(
        self, concept: str | None = None, approved: bool | None = None
    ) -> list[ImageAssetDto]:
        assets = self.repos.image_assets.list()
        if approved is not None:
            assets = [asset for asset in assets if asset.approved is approved]
        if concept and concept.strip():
            query = _normalize(concept)
            assets = [asset for asset in assets if self._match_score(query, asset) > 0]
        return sorted(assets, key=self._base_sort_key)

    def find_internal_candidates(
        self, concept: str, material_type: str, max_results: int
    ) -> list[ImageAssetDto]:
        query = _normalize(concept)
        if not query or max_results <= 0:
            return []
        material_query = _normalize(material_type)
        scored: list[tuple[int, ImageAssetDto]] = []
        for asset in self.repos.image_assets.list():
            if asset.sourceType not in {"internal", "mock"}:
                continue
            if not asset.approved or asset.safetyStatus != "ready":
                continue
            score = self._match_score(query, asset)
            if score <= 0:
                continue
            searchable = self._searchable_text(asset)
            if material_query and material_query in searchable:
                score += 2
            if asset.approved:
                score += 20
            if asset.safetyStatus == "ready":
                score += 10
            if asset.sourceType == "internal":
                score += 5
            scored.append((score, asset))
        scored.sort(
            key=lambda item: (
                0
                if item[1].approved and item[1].sourceType == "internal"
                else 1,
                -item[0],
                0 if item[1].approved else 1,
                item[1].title.lower(),
            )
        )
        return [asset for _, asset in scored[:max_results]]

    def get_image_candidates(
        self, request: ImageSearchRequest
    ) -> ImageCandidateResponse:
        concept = _normalize(request.concept)
        candidates = self.find_internal_candidates(
            concept, request.materialType, request.maxResults
        )
        source_order = ["internal"]
        external_candidates: list[ImageAssetDto] = []
        if request.allowExternalSearch and len(candidates) < request.maxResults:
            remaining = request.maxResults - len(candidates)
            for provider in self.external_providers:
                if remaining <= 0:
                    break
                source_order.append(provider.provider_name)
                try:
                    results = provider.search(
                        concept, request.materialType, remaining
                    )
                except Exception:
                    logger.warning(
                        "External image provider failed; continuing with remaining sources"
                    )
                    results = []
                external_candidates.extend(results)
                remaining = request.maxResults - len(candidates) - len(
                    external_candidates
                )
        merged = self._deduplicate([*candidates, *external_candidates])[
            : request.maxResults
        ]
        for asset in merged:
            if asset.sourceType not in {"internal", "mock"}:
                self.repos.image_assets.save(asset)
        external_in_merged = any(
            asset.sourceType not in {"internal", "mock"} for asset in merged
        )
        if external_in_merged:
            message = "Found internal and external image candidates for teacher review."
        elif merged:
            message = "Found approved internal assets."
        else:
            message = "No image candidates found. Teacher may try a different concept or explicitly generate an image."
        return ImageCandidateResponse(
            concept=concept,
            materialType=request.materialType,
            sourceOrder=source_order,
            candidates=merged,
            generationAvailable=False,
            fallbackUsed=False,
            message=message,
        )

    @staticmethod
    def _deduplicate(assets: list[ImageAssetDto]) -> list[ImageAssetDto]:
        seen: set[str] = set()
        result: list[ImageAssetDto] = []
        for asset in assets:
            if asset.providerAssetId:
                key = f"provider:{asset.sourceType}:{asset.providerAssetId}"
            elif asset.imageUrl:
                key = f"url:{asset.imageUrl}"
            else:
                key = f"id:{asset.id}"
            if key in seen:
                continue
            seen.add(key)
            result.append(asset)
        return result

    def approve_asset(
        self, asset_id: str, request: ApproveImageAssetRequest
    ) -> ImageAssetDto:
        if request.assetId != asset_id:
            raise ValidationError("Image asset ID does not match the request path")
        asset = self.repos.image_assets.get(asset_id)
        if not asset:
            raise NotFoundError("Image asset not found")
        updates: dict[str, object] = {
            "approved": True,
            "safetyStatus": "ready",
        }
        if request.concept and request.concept.strip():
            updates["concept"] = _normalize(request.concept)
        approved_asset = self.repos.image_assets.save(
            asset.model_copy(update=updates)
        )
        if request.materialId:
            V2MaterialService(self.repos).attach_image_asset_if_exists(
                request.materialId, approved_asset
            )
        return approved_asset

    def prepare_generated_image_for_material(
        self,
        learner_id: str,
        material_id: str,
        material_type: str,
        concept: str,
        prompt: str,
        style: str | None = None,
        size: str | None = "1024x1024",
        *,
        allow_generation: bool = True,
        allow_external_search: bool = True,
        force_generation: bool = False,
    ) -> ImageAssetDto:
        normalized_concept = _normalize(concept)
        normalized_material_type = _normalize(material_type)
        if not force_generation:
            cached = self._find_cached_asset(
                normalized_concept, normalized_material_type
            )
            if cached:
                self._attach_if_present(material_id, cached)
                return cached

        if (
            allow_external_search
            and not force_generation
            and self.config.IMAGE_ASSET_STRATEGY == "reuse_search_generate"
        ):
            external = self._first_external_candidate(
                normalized_concept, normalized_material_type
            )
            if external:
                self._attach_if_present(material_id, external)
                return external

        if allow_generation:
            generated = self._generate_asset(
                learner_id,
                normalized_concept,
                normalized_material_type,
                prompt,
                style,
                size,
            )
            if generated:
                self._attach_if_present(material_id, generated)
                return generated

        if allow_external_search:
            external = self._first_external_candidate(
                normalized_concept, normalized_material_type
            )
            if external:
                self._attach_if_present(material_id, external)
                return external

        internal = self.find_internal_candidates(
            normalized_concept, normalized_material_type, 1
        )
        if internal:
            reusable = self._cache_fallback_for_material(
                internal[0], normalized_concept, normalized_material_type
            )
            self._attach_if_present(material_id, reusable)
            return reusable

        fallback = self._create_mock_fallback(
            normalized_concept, normalized_material_type
        )
        self._attach_if_present(material_id, fallback)
        return fallback

    def generate_candidate(
        self, request: GenerateImageCandidateRequest
    ) -> ImageAssetDto:
        return self.prepare_generated_image_for_material(
            learner_id=request.learnerId,
            material_id=f"candidate-{request.materialType}-{_normalize(request.concept)}",
            material_type=request.materialType,
            concept=request.concept,
            prompt=request.prompt,
            style=request.style,
            size=request.size,
        )

    def _find_cached_asset(
        self, concept: str, material_type: str
    ) -> ImageAssetDto | None:
        type_tag = self._material_type_tag(material_type)
        matches = [
            asset
            for asset in self.repos.image_assets.list()
            if _normalize(asset.concept) == concept
            and type_tag in {_normalize(tag) for tag in asset.tags}
            and (asset.sourceType in {"generated", "mock"} or asset.approved)
            and asset.safetyStatus != "blocked"
        ]
        matches.sort(
            key=lambda asset: (
                0 if asset.sourceType == "generated" else 1,
                0 if asset.approved else 1,
                asset.createdAt,
                asset.id,
            )
        )
        return matches[0] if matches else None

    def _generate_asset(
        self,
        learner_id: str,
        concept: str,
        material_type: str,
        prompt: str,
        style: str | None,
        size: str | None,
    ) -> ImageAssetDto | None:
        learner = self.repos.learners.get(learner_id) or LearnerProfile(
            id=learner_id, code="Learner", age=0
        )
        try:
            result = self.ai.generate_material_image(
                learner, material_type, prompt, style, size
            )
        except Exception:
            logger.warning(
                "Configured image generation was unavailable; continuing with safe fallbacks"
            )
            return None
        image_url = result.get("imageUrl")
        image_base64 = result.get("imageBase64")
        if image_base64:
            saved_url = self._save_generated_image(image_base64)
            if saved_url:
                image_url = saved_url
                image_base64 = None
        status = result.get("status")
        if not image_url and not image_base64:
            return None
        source_type = "generated" if status == "ready" else "mock"
        asset = ImageAssetDto(
            id=f"generated-asset-{uuid4().hex}",
            sourceType=source_type,
            title=f"{material_type.replace('_', ' ').title()} – {concept.title()}",
            concept=concept,
            imageUrl=image_url,
            imageBase64=image_base64,
            thumbnailUrl=image_url,
            altText=f"Teacher-reviewable {material_type.replace('_', ' ')} illustration for {concept}.",
            tags=[concept, self._material_type_tag(material_type), "teacher review"],
            licenseInfo="Generated by configured AI provider; teacher review required",
            attribution=None,
            providerAssetId=str(result.get("imageId") or "") or None,
            approved=False,
            safetyStatus="needs_review",
            createdAt=utc_now().isoformat(),
        )
        return self.repos.image_assets.save(asset)

    def _first_external_candidate(
        self, concept: str, material_type: str
    ) -> ImageAssetDto | None:
        for provider in self.external_providers:
            try:
                results = provider.search(concept, material_type, 1)
            except Exception:
                logger.warning(
                    "External image provider failed; continuing with safe fallbacks"
                )
                continue
            if not results:
                continue
            asset = results[0]
            if self._material_type_tag(material_type) not in {
                _normalize(tag) for tag in asset.tags
            }:
                asset = asset.model_copy(
                    update={
                        "tags": [
                            *asset.tags,
                            self._material_type_tag(material_type),
                        ]
                    }
                )
            return self.repos.image_assets.save(asset)
        return None

    def _create_mock_fallback(
        self, concept: str, material_type: str
    ) -> ImageAssetDto:
        asset = ImageAssetDto(
            id=f"mock-generated-{uuid4().hex}",
            sourceType="mock",
            title=f"{material_type.replace('_', ' ').title()} Placeholder",
            concept=concept,
            imageUrl="/storage/demo-assets/visual-prompt-card.svg",
            thumbnailUrl="/storage/demo-assets/visual-prompt-card-thumb.svg",
            altText=f"Placeholder educational visual for {concept}.",
            tags=[concept, self._material_type_tag(material_type), "mock fallback"],
            licenseInfo="Internal demo asset",
            attribution=None,
            providerAssetId=None,
            approved=False,
            safetyStatus="needs_review",
            createdAt=utc_now().isoformat(),
        )
        return self.repos.image_assets.save(asset)

    def _cache_fallback_for_material(
        self, asset: ImageAssetDto, concept: str, material_type: str
    ) -> ImageAssetDto:
        type_tag = self._material_type_tag(material_type)
        tags = list(dict.fromkeys([*asset.tags, type_tag, "reusable fallback"]))
        if _normalize(asset.concept) == concept:
            return self.repos.image_assets.save(
                asset.model_copy(update={"tags": tags})
            )
        contextual = asset.model_copy(
            update={
                "id": f"cached-fallback-{uuid4().hex}",
                "concept": concept,
                "tags": tags,
                "providerAssetId": None,
                "createdAt": utc_now().isoformat(),
            }
        )
        return self.repos.image_assets.save(contextual)

    def _save_generated_image(self, image_base64: str) -> str | None:
        try:
            image_bytes = b64decode(image_base64, validate=True)
        except (Base64Error, ValueError):
            logger.warning("Generated image data was invalid; using fallback asset")
            return None
        if not image_bytes or len(image_bytes) > 25 * 1024 * 1024:
            logger.warning("Generated image exceeded the local storage safety limit")
            return None
        try:
            output_dir = Path(self.config.STORAGE_DIR) / "generated-images"
            output_dir.mkdir(parents=True, exist_ok=True)
            file_name = f"{uuid4().hex}.png"
            (output_dir / file_name).write_bytes(image_bytes)
        except OSError:
            logger.warning("Generated image could not be saved to local storage")
            return None
        return f"/storage/generated-images/{file_name}"

    def _attach_if_present(
        self, material_id: str, asset: ImageAssetDto
    ) -> None:
        if material_id:
            V2MaterialService(self.repos).attach_image_asset_if_exists(
                material_id, asset
            )

    @staticmethod
    def _material_type_tag(material_type: str) -> str:
        return f"material type {material_type}"

    def get_seed_assets(self) -> list[ImageAssetDto]:
        return self.repos.image_assets.list()

    @staticmethod
    def _searchable_text(asset: ImageAssetDto) -> str:
        return _normalize(" ".join([asset.concept, asset.title, *asset.tags]))

    @classmethod
    def _match_score(cls, query: str, asset: ImageAssetDto) -> int:
        if not query:
            return 0
        concept = _normalize(asset.concept)
        searchable = cls._searchable_text(asset)
        if query == concept:
            return 100
        if query in concept or concept in query:
            return 70
        query_tokens = set(query.split())
        searchable_tokens = set(searchable.split())
        overlap = len(query_tokens & searchable_tokens)
        return overlap * 10

    @staticmethod
    def _base_sort_key(asset: ImageAssetDto) -> tuple[int, int, str]:
        return (
            0 if asset.approved and asset.sourceType == "internal" else 1,
            0 if asset.safetyStatus == "ready" else 1,
            asset.title.lower(),
        )
