from sqlalchemy.orm import Session

from app.repositories.images import ImageAssetRepository
from app.schemas.dto import ConfirmImageRequest, ImageCandidate


class ImageAssetService:
    def __init__(self, db: Session):
        self.db = db
        self.assets = ImageAssetRepository(db)

    def confirm_assets(self, payload: ConfirmImageRequest) -> list[ImageCandidate]:
        saved: list[ImageCandidate] = []
        for index in payload.approved_indexes:
            if index < 0 or index >= len(payload.candidates):
                continue
            c = payload.candidates[index]
            if not c.license_info and c.license_label:
                c.license_info = c.license_label
            asset = self.assets.save_candidate(c, payload.skill_target, payload.concept)
            c.id = asset.id
            c.teacher_approved = True
            saved.append(c)
        self.assets.commit()
        return saved
