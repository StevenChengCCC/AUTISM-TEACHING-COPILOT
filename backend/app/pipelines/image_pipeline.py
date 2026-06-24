from typing import Iterable

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.images import ImageAssetRepository, asset_to_candidate
from app.schemas.dto import ImageNeedRequest, ImageCandidate, ImagePipelineResult
from app.integrations.ai import get_ai_provider
from app.domain.engines import build_image_search_queries


class ImagePipeline:
    """Cost-controlled image pipeline: Reuse → Search → Generate.

    Design rules:
    1. Code first: query DB and build search queries deterministically.
    2. API only when needed: external search provider keys are optional.
    3. Image generation last: return generation prompts by default; real generation can be wired later.
    """

    def __init__(self, db: Session):
        self.db = db
        self.assets = ImageAssetRepository(db)
        self.ai = get_ai_provider()

    def run(self, req: ImageNeedRequest) -> ImagePipelineResult:
        notes: list[str] = []
        reused = self._reuse(req)
        if len(reused) >= req.needed_count:
            return ImagePipelineResult(
                concept=req.concept,
                target_skill=req.target_skill,
                strategy_used="reuse_existing_assets",
                candidates=reused[: req.needed_count],
                next_action="teacher_review",
                notes=[
                    "All candidate images came from the approved asset library; no search or generation cost."
                ],
            )

        notes.append(
            f"Asset library matched {len(reused)} image(s); remaining need moves to external search."
        )
        searched = self._search(req, req.needed_count - len(reused))
        combined = reused + searched
        if len(combined) >= req.needed_count:
            return ImagePipelineResult(
                concept=req.concept,
                target_skill=req.target_skill,
                strategy_used="reuse_then_search_external_assets",
                candidates=combined[: req.needed_count],
                next_action="teacher_review",
                notes=notes
                + [
                    "External search supplied enough candidates; image generation was not used."
                ],
            )

        notes.append(
            f"Still missing {req.needed_count - len(combined)} image(s) after search; creating generation candidates."
        )
        generated = self._generate(req, req.needed_count - len(combined))
        candidates = (combined + generated)[: req.needed_count]
        return ImagePipelineResult(
            concept=req.concept,
            target_skill=req.target_skill,
            strategy_used="reuse_then_search_then_generate",
            candidates=candidates,
            next_action="teacher_review",
            missing_count=max(0, req.needed_count - len(candidates)),
            notes=notes
            + [
                "Mock mode returns generation prompts; configured image generation can create actual assets later."
            ],
        )

    def _reuse(self, req: ImageNeedRequest) -> list[ImageCandidate]:
        assets = self.assets.find_reusable(
            req.concept, req.target_skill, req.needed_count
        )
        return [asset_to_candidate(asset, "reused") for asset in assets]

    def _search(self, req: ImageNeedRequest, count: int) -> list[ImageCandidate]:
        if count <= 0:
            return []
        queries = build_image_search_queries(
            req.concept, req.variation_requirements, req.prefer_real_photos
        )
        candidates: list[ImageCandidate] = []

        # Providers are optional; if keys are absent, deterministic placeholders keep MVP runnable.
        for q in queries:
            if len(candidates) >= count:
                break
            candidates.extend(self._search_pexels(q, req, count - len(candidates)))
            if len(candidates) >= count:
                break
            candidates.extend(self._search_pixabay(q, req, count - len(candidates)))

        if not candidates:
            candidates = self._mock_search(req, count)
        return self._dedupe(candidates)[:count]

    def _generate(self, req: ImageNeedRequest, count: int) -> list[ImageCandidate]:
        candidates: list[ImageCandidate] = []
        variations = req.variation_requirements or ["general"]
        for i in range(count):
            variation = variations[i % len(variations)]
            prompt = self.ai.generate_image_prompt(req.concept, variation)
            candidates.append(
                ImageCandidate(
                    title=f"{req.concept} 生成候选 {i + 1}",
                    source_type="generated",
                    tags=[req.concept, req.target_skill, "generated_prompt"],
                    variation_type=variation,
                    quality_score=65,
                    license_info="generated-by-configured-model",
                    license_label="generated-by-configured-model",
                    reason="Generated candidate because reuse and external search did not fully satisfy the requested count.",
                    generation_prompt=prompt,
                )
            )
        return candidates

    def _search_pexels(
        self, query: str, req: ImageNeedRequest, count: int
    ) -> list[ImageCandidate]:
        if not settings.PEXELS_API_KEY or count <= 0:
            return []
        try:
            res = requests.get(
                "https://api.pexels.com/v1/search",
                params={
                    "query": query,
                    "per_page": min(count, 10),
                    "orientation": "landscape",
                },
                headers={"Authorization": settings.PEXELS_API_KEY},
                timeout=8,
            )
            res.raise_for_status()
            data = res.json()
            return [
                ImageCandidate(
                    title=photo.get("alt") or f"{req.concept} Pexels photo",
                    source_type="searched",
                    source_url=photo.get("url"),
                    thumbnail_url=(photo.get("src") or {}).get("medium"),
                    tags=[req.concept, req.target_skill, "pexels"],
                    variation_type="search_result",
                    quality_score=80,
                    license_info="Pexels license - verify before commercial use",
                    license_label="Pexels license - verify before commercial use",
                    reason="External search candidate returned after approved library reuse was insufficient.",
                )
                for photo in data.get("photos", [])
            ]
        except Exception:
            return []

    def _search_pixabay(
        self, query: str, req: ImageNeedRequest, count: int
    ) -> list[ImageCandidate]:
        if not settings.PIXABAY_API_KEY or count <= 0:
            return []
        try:
            res = requests.get(
                "https://pixabay.com/api/",
                params={
                    "key": settings.PIXABAY_API_KEY,
                    "q": query,
                    "per_page": min(count, 10),
                    "image_type": "photo",
                    "safesearch": "true",
                },
                timeout=8,
            )
            res.raise_for_status()
            data = res.json()
            return [
                ImageCandidate(
                    title=f"{req.concept} Pixabay photo",
                    source_type="searched",
                    source_url=hit.get("pageURL"),
                    thumbnail_url=hit.get("webformatURL"),
                    tags=[req.concept, req.target_skill, "pixabay"],
                    variation_type="search_result",
                    quality_score=78,
                    license_info="Pixabay content license - verify before commercial use",
                    license_label="Pixabay content license - verify before commercial use",
                    reason="External search candidate returned after approved library reuse was insufficient.",
                )
                for hit in data.get("hits", [])
            ]
        except Exception:
            return []

    def _mock_search(self, req: ImageNeedRequest, count: int) -> list[ImageCandidate]:
        variations = req.variation_requirements or ["general"]
        return [
            ImageCandidate(
                title=f"{req.concept} 找图占位 {i + 1}",
                source_type="searched",
                source_url=f"https://example.com/search?q={req.concept}-{i+1}",
                tags=[req.concept, req.target_skill, "placeholder"],
                variation_type=variations[i % len(variations)],
                quality_score=55,
                license_info="placeholder - configure PEXELS_API_KEY or PIXABAY_API_KEY",
                license_label="placeholder - configure PEXELS_API_KEY or PIXABAY_API_KEY",
                reason="Mock searched asset keeps the review workflow runnable without external API keys.",
            )
            for i in range(count)
        ]

    def _dedupe(self, candidates: Iterable[ImageCandidate]) -> list[ImageCandidate]:
        seen = set()
        result = []
        for c in candidates:
            key = c.source_url or c.thumbnail_url or c.generation_prompt or c.title
            if key in seen:
                continue
            seen.add(key)
            result.append(c)
        return result
