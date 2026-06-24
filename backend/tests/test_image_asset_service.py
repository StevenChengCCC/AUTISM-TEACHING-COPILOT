from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.schemas.dto import ConfirmImageRequest, ImageCandidate
from app.services.image_asset_service import ImageAssetService


def test_image_confirmation_persists_approved_assets():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    saved = ImageAssetService(session).confirm_assets(
        ConfirmImageRequest(
            skill_target="recognize apple",
            concept="apple",
            approved_indexes=[0],
            candidates=[
                ImageCandidate(
                    title="Apple photo",
                    source_type="searched",
                    tags=["apple"],
                    quality_score=80,
                    license_info="test license",
                    reason="test reason",
                ),
                ImageCandidate(title="Unused", source_type="generated", tags=["apple"]),
            ],
        )
    )

    assert len(saved) == 1
    assert saved[0].id == 1
    assert saved[0].source_type == "searched"
