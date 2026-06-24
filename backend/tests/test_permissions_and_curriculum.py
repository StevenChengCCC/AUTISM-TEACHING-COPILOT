from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth import CurrentTeacher, require_child_access
from app.core.database import Base
from app.core.exceptions import ForbiddenError
from app.domain.models import AuditLog, ChildProfile, Teacher, TeacherChildAccess
from app.schemas.dto import CurriculumContentCreate
from app.services.management_service import ManagementService


def make_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_teacher_child_access_permission_checks():
    session = make_session()
    session.add(ChildProfile(code="C-ACCESS"))
    session.add(Teacher(display_name="Viewer", role="teacher"))
    session.flush()
    session.add(TeacherChildAccess(teacher_id=1, child_id=1, permission_level="viewer"))
    session.commit()

    teacher = CurrentTeacher(id=1, role="teacher")
    assert require_child_access(session, 1, teacher, "viewer").code == "C-ACCESS"
    try:
        require_child_access(session, 1, teacher, "editor")
    except ForbiddenError:
        pass
    else:
        raise AssertionError("Expected editor permission to be rejected")


def test_curriculum_crud_and_audit_log_creation():
    session = make_session()
    service = ManagementService(session)

    created = service.create_curriculum(
        CurriculumContentCreate(
            title="Template",
            content_type="goal_template",
            content_json={"goal": "match"},
        ),
        actor_teacher_id=1,
    )
    assert created.id == 1
    assert service.list_curriculum()[0].title == "Template"
    assert service.delete_curriculum(1, actor_teacher_id=1)["deleted"] is True
    assert (
        session.query(AuditLog)
        .filter(AuditLog.entity_type == "CurriculumContent")
        .count()
        == 2
    )
