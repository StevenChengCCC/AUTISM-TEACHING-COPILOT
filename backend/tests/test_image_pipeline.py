from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.domain import models
from app.domain.models import ChildProfile
from app.pipelines.image_pipeline import ImagePipeline
from app.schemas.dto import ImageNeedRequest


def test_image_pipeline_search_fallback_before_generation():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add(ChildProfile(code="C-1", attention_span_minutes=5))
    session.commit()

    result = ImagePipeline(session).run(
        ImageNeedRequest(
            child_id=1,
            target_skill="recognize apple",
            concept="apple",
            needed_count=3,
            variation_requirements=["visual_variation"],
        )
    )

    assert result.strategy_used == "reuse_then_search_external_assets"
    assert all(candidate.source_type == "searched" for candidate in result.candidates)
    assert len(result.candidates) == 3
