from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.exceptions import ValidationError
from app.domain.models import AuditLog, ChildProfile
from app.schemas.dto import UploadedMaterialCreate, UploadedMaterialUpdate
from app.services.material_service import UploadedMaterialService


def make_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_materials_crud_and_audit():
    session = make_session()
    session.add(ChildProfile(code="C-MAT"))
    session.commit()

    service = UploadedMaterialService(session)
    created = service.create(
        UploadedMaterialCreate(
            child_id=1, title="Notes", material_type="txt", extracted_text="baseline"
        ),
        actor_teacher_id=1,
    )
    assert created.id == 1
    assert service.list_all(child_id=1)[0].title == "Notes"

    updated = service.update(
        1, UploadedMaterialUpdate(status="reviewed"), actor_teacher_id=1
    )
    assert updated.status == "reviewed"

    deleted = service.delete(1, actor_teacher_id=1)
    assert deleted["deleted"] is True
    assert (
        session.query(AuditLog)
        .filter(AuditLog.entity_type == "UploadedMaterial")
        .count()
        == 3
    )


def test_material_rejects_direct_identifiers():
    session = make_session()
    session.add(ChildProfile(code="C-PII"))
    session.commit()

    try:
        UploadedMaterialService(session).create(
            UploadedMaterialCreate(
                child_id=1, title="Unsafe", extracted_text="email test@example.com"
            ),
            actor_teacher_id=1,
        )
    except ValidationError as exc:
        assert "email" in exc.payload["pii_findings"]
    else:
        raise AssertionError("Expected PII material text to be rejected")
