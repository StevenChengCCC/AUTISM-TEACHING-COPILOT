from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Base
from app.core.exceptions import VersionConflictError
from app.domain import models as domain_models
from app.models import v2_entities as entities
from app.schemas.v2_dto import (
    GeneratedMaterialDto,
    LearnerProfile,
    LessonPackageDto,
    LessonSession,
    ProgressDataPointDto,
    ProgressObservation,
)
from app.services.v2_sqlalchemy_repositories import SQLAlchemyV2Repositories


def _repository(database_url: str, *, organization: str = "org-one"):
    engine = create_engine(database_url)
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    config = Settings(
        _env_file=None,
        APP_ENV="test",
        V2_REPOSITORY_MODE="sqlalchemy",
        V2_SEED_SYNTHETIC_DATA=False,
    )
    return (
        engine,
        factory,
        SQLAlchemyV2Repositories(
            factory,
            config,
            organization_external_id=organization,
            user_external_id="teacher-one",
            seed_synthetic=False,
        ),
    )


def test_crud_restart_soft_delete_scope_and_optimistic_concurrency(tmp_path):
    url = f"sqlite:///{tmp_path / 'durable.db'}"
    engine, factory, repository = _repository(url)
    learner = repository.learners.save(
        LearnerProfile(id="synthetic-learner", code="S-001", age=7)
    )

    first_copy = repository.learners.get(learner.id)
    stale_copy = repository.learners.get(learner.id)
    assert first_copy and stale_copy
    saved = repository.learners.save(first_copy.model_copy(update={"notes": "saved"}))
    assert saved.version == 2
    with pytest.raises(VersionConflictError):
        repository.learners.save(stale_copy.model_copy(update={"notes": "stale"}))

    restarted = SQLAlchemyV2Repositories(
        factory,
        Settings(_env_file=None, APP_ENV="test"),
        organization_external_id="org-one",
        user_external_id="teacher-one",
        seed_synthetic=False,
    )
    assert restarted.learners.get(learner.id).notes == "saved"
    other_organization = restarted.for_scope("org-two", "teacher-two")
    assert other_organization.learners.get(learner.id) is None
    other_owner = restarted.for_scope("org-one", "teacher-two")
    assert other_owner.learners.get(learner.id) is None
    assert restarted.learners.delete(learner.id, expected_version=2)
    assert restarted.learners.get(learner.id) is None
    with factory() as session:
        row = session.scalar(
            text(
                "SELECT deleted_at FROM v2_learners WHERE external_id='synthetic-learner'"
            )
        )
        assert row is not None
    engine.dispose()


def test_transaction_rollback_and_foreign_keys(tmp_path):
    engine, factory, repository = _repository(
        f"sqlite:///{tmp_path / 'transaction.db'}"
    )
    with pytest.raises(RuntimeError):
        with repository.transaction():
            repository.learners.save(
                LearnerProfile(id="rolled-back", code="S-ROLLBACK", age=8)
            )
            raise RuntimeError("force rollback")
    assert repository.learners.get("rolled-back") is None

    with factory() as session, pytest.raises(Exception):
        session.add(
            entities.Learner(
                external_id="invalid-owner",
                code="INVALID",
                age=7,
                organization_id="00000000-0000-0000-0000-000000000001",
                created_by_user_id="00000000-0000-0000-0000-000000000002",
            )
        )
        session.commit()
    engine.dispose()


def test_round_two_acceptance_data_survives_repository_recreation(tmp_path):
    url = f"sqlite:///{tmp_path / 'restart.db'}"
    engine, factory, repository = _repository(url)
    repository.learners.save(
        LearnerProfile(id="acceptance-learner", code="S-ACCEPT", age=7)
    )
    package = repository.lesson_packages.save(
        LessonPackageDto(
            id="acceptance-package",
            learnerId="acceptance-learner",
            draftId="acceptance-draft",
            goal="Ask for help",
            duration="10 min",
            theme="Vehicles",
            lessonBrief="Synthetic persistence check.",
            teachingFlow=[],
            materials=[],
            summaryTemplate="Record small wins.",
        )
    )
    package = repository.lesson_packages.save(
        package.model_copy(update={"lessonBrief": "Version two persistence check."})
    )
    material = repository.generated_materials.save(
        GeneratedMaterialDto(
            id="acceptance-material",
            packageId=package.id,
            type="help_card",
            title="Help Card",
            status="ready",
            content={"instruction": "Help, please."},
            printLayout={"pageSize": "Letter"},
        )
    )
    repository.generated_materials.save(
        material.model_copy(update={"title": "Updated Help Card"})
    )
    repository.sessions.save(
        LessonSession(
            id="acceptance-session",
            learner_id="acceptance-learner",
            goal=package.goal,
            status="completed",
        )
    )
    repository.progress.add(
        ProgressObservation(
            session_id="acceptance-session",
            learner_id="acceptance-learner",
            independence_level=2,
            prompt_level=2,
            engagement_level=3,
            regulation_level=3,
            notes="A small independent attempt.",
        )
    )
    repository.progress_data.save(
        ProgressDataPointDto(
            id="acceptance-data-point",
            learnerId="acceptance-learner",
            sessionDate="2026-07-15",
            goal=package.goal,
            opportunities=4,
            accuracyPercent=50,
            independencePercent=25,
            promptLevel="Level 2",
            signalsHighlighted=["participation"],
            teacherNotes="Participation continued even when accuracy was uneven.",
        )
    )

    restarted = SQLAlchemyV2Repositories(
        factory,
        Settings(_env_file=None, APP_ENV="test"),
        organization_external_id="org-one",
        user_external_id="teacher-one",
        seed_synthetic=False,
    )
    assert restarted.learners.get("acceptance-learner") is not None
    assert restarted.lesson_packages.get("acceptance-package") is not None
    assert restarted.generated_materials.get("acceptance-material").version == 2
    assert restarted.sessions.get("acceptance-session") is not None
    assert len(restarted.progress.for_learner("acceptance-learner")) == 1
    assert restarted.progress_data.get("acceptance-data-point") is not None
    with factory() as session:
        assert (
            session.scalar(
                text(
                    "SELECT COUNT(*) FROM v2_lesson_package_versions "
                    "WHERE package_id=(SELECT id FROM v2_lesson_packages "
                    "WHERE external_id='acceptance-package')"
                )
            )
            == 2
        )
        assert (
            session.scalar(
                text(
                    "SELECT COUNT(*) FROM v2_generated_material_versions "
                    "WHERE material_id=(SELECT id FROM v2_generated_materials "
                    "WHERE external_id='acceptance-material')"
                )
            )
            == 2
        )
    engine.dispose()


def test_initial_migration_upgrade_downgrade_upgrade(tmp_path):
    root = Path(__file__).resolve().parents[2]
    database = tmp_path / "migration.db"
    environment = os.environ.copy()
    environment["ALEMBIC_DATABASE_URL"] = f"sqlite:///{database}"
    command = ["alembic", "-c", str(root / "backend" / "alembic.ini")]
    subprocess.run(command + ["upgrade", "head"], cwd=root, env=environment, check=True)
    subprocess.run(
        command + ["downgrade", "base"], cwd=root, env=environment, check=True
    )
    subprocess.run(command + ["upgrade", "head"], cwd=root, env=environment, check=True)


@pytest.mark.skipif(
    not (os.getenv("TEST_DATABASE_URL") or "").startswith("postgresql"),
    reason="Set TEST_DATABASE_URL to run PostgreSQL integration coverage.",
)
def test_postgresql_repository_round_trip():
    url = os.environ["TEST_DATABASE_URL"]
    engine, _, repository = _repository(url, organization="postgres-test-org")
    item_id = f"postgres-{datetime.now(timezone.utc).timestamp()}"
    repository.learners.save(LearnerProfile(id=item_id, code=item_id, age=7))
    assert repository.learners.get(item_id) is not None
    repository.learners.delete(item_id)
    engine.dispose()
