import json

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.domain.models import ImageAsset
from app.schemas.dto import ImageCandidate


def asset_to_candidate(asset: ImageAsset, source_type: str | None = None) -> ImageCandidate:
    return ImageCandidate(
        id=asset.id,
        title=asset.title,
        source_type=source_type or asset.source_type,
        source_url=asset.source_url,
        thumbnail_url=asset.thumbnail_url,
        local_path=asset.local_path,
        tags=json.loads(asset.tags_json or "[]"),
        variation_type=asset.variation_type,
        quality_score=asset.quality_score,
        license_info=asset.license_info,
    )


class ImageAssetRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_recent(self, limit: int = 100) -> list[ImageAsset]:
        return self.db.query(ImageAsset).order_by(ImageAsset.id.desc()).limit(limit).all()

    def find_reusable(self, concept: str, target_skill: str, limit: int) -> list[ImageAsset]:
        terms = [concept, target_skill]
        return (
            self.db.query(ImageAsset)
            .filter(ImageAsset.approved.is_(True))
            .filter(
                or_(
                    ImageAsset.concept.in_(terms),
                    ImageAsset.skill_target == target_skill,
                    ImageAsset.tags_json.contains(concept),
                )
            )
            .order_by(ImageAsset.quality_score.desc(), ImageAsset.id.desc())
            .limit(limit)
            .all()
        )

    def save_candidate(self, candidate: ImageCandidate, skill_target: str, concept: str) -> ImageAsset:
        asset = ImageAsset(
            title=candidate.title,
            source_type=candidate.source_type,
            source_url=candidate.source_url,
            thumbnail_url=candidate.thumbnail_url,
            local_path=candidate.local_path,
            tags_json=json.dumps(candidate.tags, ensure_ascii=False),
            skill_target=skill_target,
            concept=concept,
            variation_type=candidate.variation_type,
            quality_score=candidate.quality_score,
            license_info=candidate.license_info,
            approved=True,
        )
        self.db.add(asset)
        self.db.flush()
        return asset

    def commit(self) -> None:
        self.db.commit()
