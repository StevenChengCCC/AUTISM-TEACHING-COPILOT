from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.pipelines.image_pipeline import ImagePipeline
from app.repositories.children import ChildProfileRepository
from app.repositories.images import ImageAssetRepository, asset_to_candidate
from app.schemas.dto import ImageCandidate, ImageNeedRequest, ImagePipelineResult


class ImagePipelineService:
    def __init__(self, db: Session):
        self.children = ChildProfileRepository(db)
        self.assets = ImageAssetRepository(db)
        self.pipeline = ImagePipeline(db)

    def run(self, payload: ImageNeedRequest) -> ImagePipelineResult:
        if not self.children.get(payload.child_id):
            raise NotFoundError("Child profile not found")
        return self.pipeline.run(payload)

    def list_assets(self) -> list[ImageCandidate]:
        return [asset_to_candidate(asset) for asset in self.assets.list_recent()]
