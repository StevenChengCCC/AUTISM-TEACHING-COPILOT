from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable, Generic, Iterator, TypeVar
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, settings
from app.core.auth_context import get_authenticated_scope
from app.core.database import SessionLocal
from app.core.exceptions import VersionConflictError
from app.models import v2_entities as entities
from app.schemas.v2_dto import (
    AIChatState,
    GeneratedMaterial,
    GeneratedMaterialDto,
    ImageAssetDto,
    LearnerProfile,
    LearnerProgressSummaryDto,
    LearnerRecord,
    LessonPackage,
    LessonPackageDto,
    LessonPackageExportJobDto,
    LessonSession,
    MaterialLibraryItem,
    ProgressDataPointDto,
    ProgressObservation,
    ProgressSignalDto,
    RecentLessonDto,
)


T = TypeVar("T", bound=BaseModel)
ModelFactory = Callable[[Session, T, dict[str, Any]], Any]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class SQLAlchemyDtoRepository(Generic[T]):
    def __init__(
        self,
        registry: "SQLAlchemyV2Repositories",
        model: type,
        dto_types: dict[str, type[T]],
        *,
        key_field: str = "id",
        projection_type: str | None = None,
        model_factory: ModelFactory[T] | None = None,
        version_model: type | None = None,
        parent_field: str | None = None,
    ) -> None:
        self.registry = registry
        self.model = model
        self.dto_types = dto_types
        self.key_field = key_field
        self.projection_type = projection_type
        self.model_factory = model_factory
        self.version_model = version_model
        self.parent_field = parent_field

    def _query(self, session: Session):
        scope = self.registry._resolve_scope(session)
        query = select(self.model).where(
            self.model.organization_id == scope.organization_id,
            self.model.created_by_user_id == scope.user_id,
            self.model.deleted_at.is_(None),
        )
        if self.projection_type is not None:
            query = query.where(self.model.projection_type == self.projection_type)
        return query

    def list(self) -> list[T]:
        with self.registry.session_scope() as session:
            rows = session.scalars(
                self._query(session).order_by(self.model.created_at)
            ).all()
            return [self._to_dto(row) for row in rows]

    def get(self, item_id: str) -> T | None:
        with self.registry.session_scope() as session:
            row = session.scalar(
                self._query(session).where(self.model.external_id == item_id)
            )
            return self._to_dto(row) if row is not None else None

    def list_versions(self, item_id: str) -> list[T]:
        if self.version_model is None or self.parent_field is None:
            current = self.get(item_id)
            return [current] if current is not None else []
        with self.registry.session_scope() as session:
            row = session.scalar(
                self._query(session).where(self.model.external_id == item_id)
            )
            if row is None:
                return []
            scope = self.registry._resolve_scope(session)
            version_rows = session.scalars(
                select(self.version_model)
                .where(
                    getattr(self.version_model, self.parent_field) == row.id,
                    self.version_model.organization_id == scope.organization_id,
                    self.version_model.created_by_user_id == scope.user_id,
                    self.version_model.deleted_at.is_(None),
                )
                .order_by(self.version_model.snapshot_version)
            ).all()
            return [self._snapshot_to_dto(version_row) for version_row in version_rows]

    def get_version(self, item_id: str, version: int) -> T | None:
        return next(
            (
                item
                for item in self.list_versions(item_id)
                if getattr(item, "version", None) == version
            ),
            None,
        )

    def save(self, item: T) -> T:
        external_id = str(getattr(item, self.key_field))
        payload = item.model_dump(mode="json", by_alias=True)
        dto_type = type(item).__name__
        payload["_dtoType"] = dto_type
        with self.registry.session_scope(write=True) as session:
            scope = self.registry._resolve_scope(session)
            row = session.scalar(
                self._query(session).where(self.model.external_id == external_id)
            )
            if row is None:
                if self.model_factory is not None:
                    row = self.model_factory(session, item, payload)
                else:
                    row = self.model(
                        external_id=external_id,
                        organization_id=scope.organization_id,
                        created_by_user_id=scope.user_id,
                        payload=payload,
                    )
                if self.projection_type is not None:
                    row.projection_type = self.projection_type
                session.add(row)
                session.flush()
                action = "create"
            else:
                expected_version = getattr(item, "version", row.version)
                if expected_version != row.version:
                    raise VersionConflictError(
                        "The resource changed after it was loaded. Refresh and try again."
                    )
                row.version += 1
                row.payload = payload
                row.updated_at = _utc_now()
                self._sync_indexed_columns(row, item)
                action = "update"
            payload["version"] = row.version
            row.payload = payload
            self._save_version(session, row, payload)
            self.registry._audit(session, action, self.model.__tablename__, external_id)
            session.flush()
            return self._to_dto(row)

    @staticmethod
    def _sync_indexed_columns(row: Any, item: T) -> None:
        """Keep queryable columns aligned with the canonical DTO payload."""

        if isinstance(row, entities.GeneratedMaterial):
            row.material_type = item.type
            row.status = item.status
        elif isinstance(row, entities.MaterialLibraryItem):
            row.title = item.title
            row.material_type = item.type
            row.reusable = item.reusable
        elif isinstance(row, entities.ImageAsset):
            row.concept = item.concept
            row.source_type = item.sourceType
            row.approved = item.approved
        elif isinstance(row, entities.TeachingSession):
            row.status = item.status
        elif isinstance(row, entities.ExportJob):
            row.status = item.status
            row.export_format = item.format
            row.storage_key = item.storageObjectKey
            row.file_size_bytes = item.fileSizeBytes
            row.completed_at = _parse_datetime(item.completedAt)
            row.expires_at = _parse_datetime(item.expiresAt)

    create = save
    update = save

    def delete(self, item_id: str, expected_version: int | None = None) -> bool:
        with self.registry.session_scope(write=True) as session:
            row = session.scalar(
                self._query(session).where(self.model.external_id == item_id)
            )
            if row is None:
                return False
            if expected_version is not None and row.version != expected_version:
                raise VersionConflictError(
                    "The resource changed after it was loaded. Refresh and try again."
                )
            row.deleted_at = _utc_now()
            row.version += 1
            self.registry._audit(
                session, "soft_delete", self.model.__tablename__, item_id
            )
            return True

    def _save_version(
        self, session: Session, row: Any, payload: dict[str, Any]
    ) -> None:
        if self.version_model is None or self.parent_field is None:
            return
        scope = self.registry._resolve_scope(session)
        session.add(
            self.version_model(
                **{
                    self.parent_field: row.id,
                    "snapshot_version": row.version,
                    "payload": deepcopy(payload),
                    "organization_id": scope.organization_id,
                    "created_by_user_id": scope.user_id,
                }
            )
        )

    def _to_dto(self, row: Any) -> T:
        payload = dict(row.payload or {})
        dto_name = payload.pop("_dtoType", next(iter(self.dto_types)))
        dto_type = self.dto_types.get(dto_name, next(iter(self.dto_types.values())))
        if "version" in dto_type.model_fields:
            payload["version"] = row.version
        return dto_type.model_validate(payload)

    def _snapshot_to_dto(self, row: Any) -> T:
        payload = dict(row.payload or {})
        dto_name = payload.pop("_dtoType", next(iter(self.dto_types)))
        dto_type = self.dto_types.get(dto_name, next(iter(self.dto_types.values())))
        if "version" in dto_type.model_fields:
            payload["version"] = row.snapshot_version
        return dto_type.model_validate(payload)


class SQLAlchemyLearnerRepository(SQLAlchemyDtoRepository[LearnerProfile]):
    def __init__(self, registry: "SQLAlchemyV2Repositories") -> None:
        super().__init__(registry, entities.Learner, {"LearnerProfile": LearnerProfile})

    def _query(self, session: Session):
        scope = self.registry._resolve_scope(session)
        return select(entities.Learner).where(
            entities.Learner.organization_id == scope.organization_id,
            entities.Learner.created_by_user_id == scope.user_id,
            entities.Learner.deleted_at.is_(None),
        )

    def save(self, item: LearnerProfile) -> LearnerProfile:
        payload = item.model_dump(mode="json", by_alias=True)
        payload["_dtoType"] = "LearnerProfile"
        with self.registry.session_scope(write=True) as session:
            scope = self.registry._resolve_scope(session)
            learner = session.scalar(
                self._query(session).where(entities.Learner.external_id == item.id)
            )
            if learner is None:
                learner = entities.Learner(
                    external_id=item.id,
                    code=item.code,
                    age=item.age,
                    avatar=item.avatar,
                    organization_id=scope.organization_id,
                    created_by_user_id=scope.user_id,
                )
                session.add(learner)
                session.flush()
                profile = entities.LearnerProfile(
                    learner_id=learner.id,
                    review_status=item.profile_review_status,
                    payload=payload,
                    organization_id=scope.organization_id,
                    created_by_user_id=scope.user_id,
                )
                session.add(profile)
                session.flush()
                action = "create"
            else:
                profile = session.scalar(
                    select(entities.LearnerProfile).where(
                        entities.LearnerProfile.learner_id == learner.id,
                        entities.LearnerProfile.organization_id
                        == scope.organization_id,
                        entities.LearnerProfile.deleted_at.is_(None),
                    )
                )
                if profile is None:
                    raise RuntimeError("Learner profile row is missing")
                if item.version != profile.version:
                    raise VersionConflictError(
                        "The learner profile changed after it was loaded. Refresh and try again."
                    )
                learner.version += 1
                profile.version += 1
                learner.code = item.code
                learner.age = item.age
                learner.avatar = item.avatar
                profile.review_status = item.profile_review_status
                profile.updated_at = _utc_now()
                action = "update"
            payload["version"] = profile.version
            profile.payload = payload
            session.add(
                entities.LearnerProfileVersion(
                    profile_id=profile.id,
                    snapshot_version=profile.version,
                    payload=deepcopy(payload),
                    organization_id=scope.organization_id,
                    created_by_user_id=scope.user_id,
                )
            )
            self._sync_signals(session, profile, item)
            self.registry._audit(session, action, "v2_learner_profiles", item.id)
            session.flush()
            return self._profile_to_dto(profile)

    create = save
    update = save

    def list(self) -> list[LearnerProfile]:
        with self.registry.session_scope() as session:
            scope = self.registry._resolve_scope(session)
            profiles = session.scalars(
                select(entities.LearnerProfile)
                .where(
                    entities.LearnerProfile.organization_id == scope.organization_id,
                    entities.LearnerProfile.created_by_user_id == scope.user_id,
                    entities.LearnerProfile.deleted_at.is_(None),
                )
                .order_by(entities.LearnerProfile.created_at)
            ).all()
            return [self._profile_to_dto(profile) for profile in profiles]

    def get(self, item_id: str) -> LearnerProfile | None:
        with self.registry.session_scope() as session:
            scope = self.registry._resolve_scope(session)
            profile = session.scalar(
                select(entities.LearnerProfile)
                .join(
                    entities.Learner,
                    entities.Learner.id == entities.LearnerProfile.learner_id,
                )
                .where(
                    entities.Learner.external_id == item_id,
                    entities.Learner.organization_id == scope.organization_id,
                    entities.Learner.created_by_user_id == scope.user_id,
                    entities.Learner.deleted_at.is_(None),
                    entities.LearnerProfile.deleted_at.is_(None),
                )
            )
            return self._profile_to_dto(profile) if profile else None

    def list_versions(self, item_id: str) -> list[LearnerProfile]:
        with self.registry.session_scope() as session:
            scope = self.registry._resolve_scope(session)
            profile = session.scalar(
                select(entities.LearnerProfile)
                .join(entities.Learner, entities.Learner.id == entities.LearnerProfile.learner_id)
                .where(
                    entities.Learner.external_id == item_id,
                    entities.Learner.organization_id == scope.organization_id,
                    entities.Learner.created_by_user_id == scope.user_id,
                    entities.Learner.deleted_at.is_(None),
                    entities.LearnerProfile.deleted_at.is_(None),
                )
            )
            if profile is None:
                return []
            rows = session.scalars(
                select(entities.LearnerProfileVersion)
                .where(
                    entities.LearnerProfileVersion.profile_id == profile.id,
                    entities.LearnerProfileVersion.organization_id == scope.organization_id,
                    entities.LearnerProfileVersion.created_by_user_id == scope.user_id,
                    entities.LearnerProfileVersion.deleted_at.is_(None),
                )
                .order_by(entities.LearnerProfileVersion.snapshot_version)
            ).all()
            return [
                LearnerProfile.model_validate(
                    {**dict(row.payload or {}), "version": row.snapshot_version}
                )
                for row in rows
            ]

    def get_version(self, item_id: str, version: int) -> LearnerProfile | None:
        return next(
            (
                item
                for item in self.list_versions(item_id)
                if item.version == version
            ),
            None,
        )

    def delete(self, item_id: str, expected_version: int | None = None) -> bool:
        with self.registry.session_scope(write=True) as session:
            scope = self.registry._resolve_scope(session)
            learner = session.scalar(
                select(entities.Learner).where(
                    entities.Learner.external_id == item_id,
                    entities.Learner.organization_id == scope.organization_id,
                    entities.Learner.created_by_user_id == scope.user_id,
                    entities.Learner.deleted_at.is_(None),
                )
            )
            if not learner:
                return False
            profile = session.scalar(
                select(entities.LearnerProfile).where(
                    entities.LearnerProfile.learner_id == learner.id,
                    entities.LearnerProfile.deleted_at.is_(None),
                )
            )
            if (
                profile
                and expected_version is not None
                and profile.version != expected_version
            ):
                raise VersionConflictError(
                    "The learner profile changed after it was loaded. Refresh and try again."
                )
            learner.deleted_at = _utc_now()
            learner.version += 1
            if profile:
                profile.deleted_at = learner.deleted_at
                profile.version += 1
            self.registry._audit(session, "soft_delete", "v2_learners", item_id)
            return True

    def _sync_signals(
        self, session: Session, profile: entities.LearnerProfile, item: LearnerProfile
    ) -> None:
        scope = self.registry._resolve_scope(session)
        existing = {
            signal.external_id: signal
            for signal in session.scalars(
                select(entities.ProfileSignal).where(
                    entities.ProfileSignal.profile_id == profile.id,
                    entities.ProfileSignal.deleted_at.is_(None),
                )
            ).all()
        }
        retained: set[str] = set()
        for signal in item.profile_signals:
            retained.add(signal.id)
            payload = signal.model_dump(mode="json", by_alias=True)
            row = existing.get(signal.id)
            if row is None:
                session.add(
                    entities.ProfileSignal(
                        external_id=signal.id,
                        profile_id=profile.id,
                        category=signal.category,
                        status=signal.status,
                        payload=payload,
                        organization_id=scope.organization_id,
                        created_by_user_id=scope.user_id,
                    )
                )
            else:
                row.category = signal.category
                row.status = signal.status
                row.payload = payload
                row.version += 1
        for external_id, row in existing.items():
            if external_id not in retained:
                row.deleted_at = _utc_now()

    @staticmethod
    def _profile_to_dto(profile: entities.LearnerProfile) -> LearnerProfile:
        payload = dict(profile.payload or {})
        payload.pop("_dtoType", None)
        payload["version"] = profile.version
        return LearnerProfile.model_validate(payload)


class SQLAlchemyRecordRepository(SQLAlchemyDtoRepository[LearnerRecord]):
    def __init__(self, registry: "SQLAlchemyV2Repositories") -> None:
        super().__init__(
            registry, entities.LearnerRecord, {"LearnerRecord": LearnerRecord}
        )

    def save(self, item: LearnerRecord) -> LearnerRecord:
        with self.registry.session_scope(write=True) as session:
            scope = self.registry._resolve_scope(session)
            learner = self.registry._learner_row(session, item.learner_id)
            row = session.scalar(
                self._query(session).where(
                    entities.LearnerRecord.external_id == item.id
                )
            )
            if row is None:
                row = entities.LearnerRecord(
                    external_id=item.id,
                    learner_id=learner.id,
                    file_name=item.file_name,
                    file_type=item.file_type,
                    status=item.status,
                    storage_key=item.storage_key,
                    declared_content_type=item.declared_content_type,
                    expected_size_bytes=item.expected_size_bytes,
                    object_size_bytes=item.object_size_bytes,
                    malware_scan_status=item.malware_scan_status,
                    parsing_message=item.parsing_message,
                    deletion_status=item.deletion_status,
                    upload_completed_at=item.upload_completed_at,
                    uploaded_at=item.uploaded_at,
                    organization_id=scope.organization_id,
                    created_by_user_id=scope.user_id,
                )
                session.add(row)
                session.flush()
                text = entities.ExtractedRecordText(
                    record_id=row.id,
                    text=item.extracted_text,
                    teacher_corrected_text=item.teacher_corrected_text,
                    extraction_method=item.extraction_method,
                    corrected_at=(
                        _utc_now() if item.teacher_corrected_text is not None else None
                    ),
                    organization_id=scope.organization_id,
                    created_by_user_id=scope.user_id,
                )
                session.add(text)
                action = "create"
            else:
                if item.version != row.version:
                    raise VersionConflictError(
                        "The learner record changed after it was loaded. Refresh and try again."
                    )
                row.version += 1
                row.file_name = item.file_name
                row.file_type = item.file_type
                row.status = item.status
                row.storage_key = item.storage_key
                row.declared_content_type = item.declared_content_type
                row.expected_size_bytes = item.expected_size_bytes
                row.object_size_bytes = item.object_size_bytes
                row.malware_scan_status = item.malware_scan_status
                row.parsing_message = item.parsing_message
                row.deletion_status = item.deletion_status
                row.upload_completed_at = item.upload_completed_at
                text = session.scalar(
                    select(entities.ExtractedRecordText).where(
                        entities.ExtractedRecordText.record_id == row.id,
                        entities.ExtractedRecordText.deleted_at.is_(None),
                    )
                )
                if text is None:
                    text = entities.ExtractedRecordText(
                        record_id=row.id,
                        organization_id=scope.organization_id,
                        created_by_user_id=scope.user_id,
                    )
                    session.add(text)
                text.text = item.extracted_text
                text.teacher_corrected_text = item.teacher_corrected_text
                text.extraction_method = item.extraction_method
                text.corrected_at = (
                    _utc_now() if item.teacher_corrected_text is not None else None
                )
                text.version += 1
                action = "update"
            self.registry._audit(session, action, "v2_learner_records", item.id)
            session.flush()
            return self._row_to_dto(session, row)

    create = save
    update = save

    def list(self) -> list[LearnerRecord]:
        with self.registry.session_scope() as session:
            rows = session.scalars(
                self._query(session).order_by(entities.LearnerRecord.created_at)
            ).all()
            return [self._row_to_dto(session, row) for row in rows]

    def get(self, item_id: str) -> LearnerRecord | None:
        with self.registry.session_scope() as session:
            row = session.scalar(
                self._query(session).where(
                    entities.LearnerRecord.external_id == item_id
                )
            )
            return self._row_to_dto(session, row) if row else None

    def for_learner(self, learner_id: str) -> list[LearnerRecord]:
        return [record for record in self.list() if record.learner_id == learner_id]

    def delete(self, item_id: str, expected_version: int | None = None) -> bool:
        with self.registry.session_scope(write=True) as session:
            row = session.scalar(
                self._query(session).where(
                    entities.LearnerRecord.external_id == item_id
                )
            )
            if row is None:
                return False
            if expected_version is not None and row.version != expected_version:
                raise VersionConflictError(
                    "The learner record changed after it was loaded. Refresh and try again."
                )
            deleted_at = _utc_now()
            row.status = "deleted"
            row.deletion_status = "deleted"
            row.deleted_at = deleted_at
            row.version += 1
            text = session.scalar(
                select(entities.ExtractedRecordText).where(
                    entities.ExtractedRecordText.record_id == row.id,
                    entities.ExtractedRecordText.deleted_at.is_(None),
                )
            )
            if text:
                text.text = ""
                text.teacher_corrected_text = None
                text.deleted_at = deleted_at
                text.version += 1
            self.registry._audit(
                session, "soft_delete", "v2_learner_records", item_id
            )
            return True

    @staticmethod
    def _row_to_dto(session: Session, row: entities.LearnerRecord) -> LearnerRecord:
        learner_external_id = session.scalar(
            select(entities.Learner.external_id).where(
                entities.Learner.id == row.learner_id
            )
        )
        text = session.scalar(
            select(entities.ExtractedRecordText).where(
                entities.ExtractedRecordText.record_id == row.id,
                entities.ExtractedRecordText.deleted_at.is_(None),
            )
        )
        return LearnerRecord(
            id=row.external_id,
            learner_id=learner_external_id,
            file_name=row.file_name,
            file_type=row.file_type,
            status=row.status,
            uploaded_at=row.uploaded_at,
            extracted_text=text.text if text else "",
            teacher_corrected_text=(text.teacher_corrected_text if text else None),
            storage_key=row.storage_key,
            declared_content_type=row.declared_content_type,
            expected_size_bytes=row.expected_size_bytes,
            object_size_bytes=row.object_size_bytes,
            malware_scan_status=row.malware_scan_status,
            parsing_message=row.parsing_message,
            deletion_status=row.deletion_status,
            upload_completed_at=row.upload_completed_at,
            extraction_method=text.extraction_method if text else "parser",
            version=row.version,
        )


class SQLAlchemyConversationRepository(SQLAlchemyDtoRepository[AIChatState]):
    """Persists the conversation aggregate and its editable draft atomically."""

    def save(self, item: AIChatState) -> AIChatState:
        with self.registry.transaction():
            with self.registry.session_scope(write=True) as session:
                scope = self.registry._resolve_scope(session)
                learner = self.registry._learner_row(session, item.learner_id)
                row = session.scalar(
                    self._query(session).where(
                        entities.LessonConversation.external_id == item.conversation_id
                    )
                )
                action = "update" if row is not None else "create"
                if row is None:
                    row = entities.LessonConversation(
                        external_id=item.conversation_id,
                        learner_id=learner.id,
                        state_payload={},
                        organization_id=scope.organization_id,
                        created_by_user_id=scope.user_id,
                    )
                    session.add(row)
                    session.flush()
                else:
                    row.version += 1

                draft = session.scalar(
                    select(entities.LessonDesignDraft).where(
                        entities.LessonDesignDraft.conversation_id == row.id,
                        entities.LessonDesignDraft.deleted_at.is_(None),
                    )
                )
                draft_payload = item.draft.model_dump(mode="json", by_alias=True)
                if draft is None:
                    draft = entities.LessonDesignDraft(
                        external_id=item.draft.id,
                        learner_id=learner.id,
                        conversation_id=row.id,
                        payload=draft_payload,
                        organization_id=scope.organization_id,
                        created_by_user_id=scope.user_id,
                    )
                    session.add(draft)
                    session.flush()
                else:
                    if item.draft.version != draft.version:
                        raise VersionConflictError(
                            "The lesson draft changed after it was loaded. Refresh and try again."
                        )
                    draft.version += 1
                    draft.payload = draft_payload
                    draft.updated_at = _utc_now()
                draft_payload["version"] = draft.version
                draft.payload = draft_payload

                existing_messages = {
                    message.external_id: message
                    for message in session.scalars(
                        select(entities.LessonMessage).where(
                            entities.LessonMessage.conversation_id == row.id,
                            entities.LessonMessage.deleted_at.is_(None),
                        )
                    ).all()
                }
                retained: set[str] = set()
                for message in item.messages:
                    retained.add(message.id)
                    message_row = existing_messages.get(message.id)
                    if message_row is None:
                        session.add(
                            entities.LessonMessage(
                                external_id=message.id,
                                conversation_id=row.id,
                                role=message.role,
                                content=message.content,
                                message_created_at=message.created_at,
                                organization_id=scope.organization_id,
                                created_by_user_id=scope.user_id,
                            )
                        )
                    else:
                        message_row.role = message.role
                        message_row.content = message.content
                        message_row.version += 1
                for message_id, message_row in existing_messages.items():
                    if message_id not in retained:
                        message_row.deleted_at = _utc_now()

                state = item.model_copy(
                    update={
                        "draft": item.draft.model_copy(
                            update={"version": draft.version}
                        )
                    }
                )
                payload = state.model_dump(mode="json", by_alias=True)
                payload["_dtoType"] = "AIChatState"
                row.state_payload = payload
                self.registry._audit(
                    session, action, "v2_lesson_conversations", item.conversation_id
                )
                session.flush()
                return state

    create = save
    update = save


class SQLAlchemyMaterialRepository(SQLAlchemyDtoRepository):
    def for_package(self, package_id: str) -> list:
        return [
            item
            for item in self.list()
            if getattr(item, "package_id", getattr(item, "packageId", None))
            == package_id
        ]


class SQLAlchemyExportRepository(SQLAlchemyDtoRepository[LessonPackageExportJobDto]):
    def _to_dto(self, row):
        dto = super()._to_dto(row)
        return dto.model_copy(update={"storageObjectKey": row.storage_key})


class SQLAlchemyProgressRepository:
    def __init__(self, registry: "SQLAlchemyV2Repositories") -> None:
        self.registry = registry

    def add(self, item: ProgressObservation) -> ProgressObservation:
        with self.registry.session_scope(write=True) as session:
            scope = self.registry._resolve_scope(session)
            learner = self.registry._learner_row(session, item.learner_id)
            teaching_session = self.registry._session_row(session, item.session_id)
            session.add(
                entities.ProgressObservation(
                    external_id=f"observation-{uuid4()}",
                    learner_id=learner.id,
                    teaching_session_id=(
                        teaching_session.id if teaching_session else None
                    ),
                    observation_type="observation",
                    observed_at=item.observed_at,
                    payload=item.model_dump(mode="json", by_alias=True),
                    organization_id=scope.organization_id,
                    created_by_user_id=scope.user_id,
                )
            )
            self.registry._audit(
                session, "create", "v2_progress_observations", item.session_id
            )
            return item.model_copy(deep=True)

    def for_learner(self, learner_id: str) -> list[ProgressObservation]:
        with self.registry.session_scope() as session:
            scope = self.registry._resolve_scope(session)
            learner = self.registry._learner_row(session, learner_id, required=False)
            if learner is None:
                return []
            rows = session.scalars(
                select(entities.ProgressObservation)
                .where(
                    entities.ProgressObservation.organization_id
                    == scope.organization_id,
                    entities.ProgressObservation.created_by_user_id == scope.user_id,
                    entities.ProgressObservation.learner_id == learner.id,
                    entities.ProgressObservation.observation_type == "observation",
                    entities.ProgressObservation.deleted_at.is_(None),
                )
                .order_by(entities.ProgressObservation.observed_at)
            ).all()
            return [ProgressObservation.model_validate(row.payload) for row in rows]


class SQLAlchemyProgressDataRepository:
    """Stores product progress data points in the progress observation table."""

    def __init__(self, registry: "SQLAlchemyV2Repositories") -> None:
        self.registry = registry

    def _query(self, session: Session):
        scope = self.registry._resolve_scope(session)
        return select(entities.ProgressObservation).where(
            entities.ProgressObservation.organization_id == scope.organization_id,
            entities.ProgressObservation.created_by_user_id == scope.user_id,
            entities.ProgressObservation.observation_type == "data_point",
            entities.ProgressObservation.deleted_at.is_(None),
        )

    def list(self) -> list[ProgressDataPointDto]:
        with self.registry.session_scope() as session:
            rows = session.scalars(
                self._query(session).order_by(entities.ProgressObservation.observed_at)
            ).all()
            return [ProgressDataPointDto.model_validate(row.payload) for row in rows]

    def get(self, item_id: str) -> ProgressDataPointDto | None:
        with self.registry.session_scope() as session:
            row = session.scalar(
                self._query(session).where(
                    entities.ProgressObservation.external_id == item_id
                )
            )
            return ProgressDataPointDto.model_validate(row.payload) if row else None

    def save(self, item: ProgressDataPointDto) -> ProgressDataPointDto:
        with self.registry.session_scope(write=True) as session:
            scope = self.registry._resolve_scope(session)
            learner = self.registry._learner_row(session, item.learnerId)
            row = session.scalar(
                self._query(session).where(
                    entities.ProgressObservation.external_id == item.id
                )
            )
            payload = item.model_dump(mode="json", by_alias=True)
            observed_at = datetime.fromisoformat(item.sessionDate).replace(
                tzinfo=timezone.utc
            )
            if row is None:
                row = entities.ProgressObservation(
                    external_id=item.id,
                    learner_id=learner.id,
                    teaching_session_id=None,
                    observation_type="data_point",
                    observed_at=observed_at,
                    payload=payload,
                    organization_id=scope.organization_id,
                    created_by_user_id=scope.user_id,
                )
                session.add(row)
                action = "create"
            else:
                row.observed_at = observed_at
                row.payload = payload
                row.version += 1
                action = "update"
            self.registry._audit(session, action, "v2_progress_observations", item.id)
            return item.model_copy(deep=True)

    create = save
    update = save


class RepositoryScope:
    def __init__(self, organization_id, user_id) -> None:
        self.organization_id = organization_id
        self.user_id = user_id


class SQLAlchemyV2Repositories:
    """Organization-scoped durable adapter preserving the existing service API."""

    def __init__(
        self,
        session_factory: sessionmaker = SessionLocal,
        config: Settings = settings,
        *,
        organization_external_id: str | None = None,
        user_external_id: str | None = None,
        seed_synthetic: bool | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.config = config
        self.organization_external_id = (
            organization_external_id or config.V2_DEFAULT_ORGANIZATION_ID
        )
        self.user_external_id = user_external_id or config.V2_DEFAULT_USER_ID
        self._current_session: ContextVar[Session | None] = ContextVar(
            f"v2_session_{id(self)}", default=None
        )
        self._id_lock = RLock()
        self._seed_synthetic = (
            seed_synthetic
            if seed_synthetic is not None
            else config.V2_SEED_SYNTHETIC_DATA
            and config.APP_ENV in {"development", "test"}
        )
        self.learners = SQLAlchemyLearnerRepository(self)
        self.records = SQLAlchemyRecordRepository(self)
        self.conversations = SQLAlchemyConversationRepository(
            self,
            entities.LessonConversation,
            {"AIChatState": AIChatState},
            key_field="conversation_id",
            model_factory=self._conversation_factory,
        )
        self.chats = self.conversations
        self.lesson_packages = SQLAlchemyDtoRepository(
            self,
            entities.LessonPackage,
            {"LessonPackage": LessonPackage, "LessonPackageDto": LessonPackageDto},
            model_factory=self._package_factory,
            version_model=entities.LessonPackageVersion,
            parent_field="package_id",
        )
        self.packages = self.lesson_packages
        self.materials = SQLAlchemyMaterialRepository(
            self,
            entities.GeneratedMaterial,
            {
                "GeneratedMaterial": GeneratedMaterial,
                "GeneratedMaterialDto": GeneratedMaterialDto,
            },
            model_factory=self._material_factory,
            version_model=entities.GeneratedMaterialVersion,
            parent_field="material_id",
        )
        self.generated_materials = self.materials
        self.materials_library = SQLAlchemyDtoRepository(
            self,
            entities.MaterialLibraryItem,
            {"MaterialLibraryItem": MaterialLibraryItem},
            model_factory=self._library_factory,
        )
        self.library = self.materials_library
        self.image_assets = SQLAlchemyDtoRepository(
            self,
            entities.ImageAsset,
            {"ImageAssetDto": ImageAssetDto},
            model_factory=self._image_factory,
        )
        self.sessions = SQLAlchemyDtoRepository(
            self,
            entities.TeachingSession,
            {"LessonSession": LessonSession},
            model_factory=self._teaching_session_factory,
        )
        self.export_jobs = SQLAlchemyExportRepository(
            self,
            entities.ExportJob,
            {"LessonPackageExportJobDto": LessonPackageExportJobDto},
            key_field="exportId",
            model_factory=self._export_job_factory,
        )
        self.recent_lessons = self._projection(
            "recent_lesson", RecentLessonDto, key_field="id"
        )
        self.progress_summaries = self._projection(
            "progress_summary", LearnerProgressSummaryDto, key_field="learnerId"
        )
        self.progress_signals = self._projection(
            "progress_signal", ProgressSignalDto, key_field="id"
        )
        self.progress_data = SQLAlchemyProgressDataRepository(self)
        self.progress = SQLAlchemyProgressRepository(self)

    def _projection(self, projection_type: str, dto_type: type[T], key_field: str):
        return SQLAlchemyDtoRepository(
            self,
            entities.PersistenceProjection,
            {dto_type.__name__: dto_type},
            key_field=key_field,
            projection_type=projection_type,
        )

    @contextmanager
    def session_scope(self, write: bool = False) -> Iterator[Session]:
        existing = self._current_session.get()
        if existing is not None:
            yield existing
            return
        session = self.session_factory()
        token: Token[Session | None] = self._current_session.set(session)
        try:
            yield session
            if write:
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            self._current_session.reset(token)
            session.close()

    @contextmanager
    def transaction(self) -> Iterator["SQLAlchemyV2Repositories"]:
        existing = self._current_session.get()
        if existing is not None:
            yield self
            return
        session = self.session_factory()
        token: Token[Session | None] = self._current_session.set(session)
        try:
            yield self
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            self._current_session.reset(token)
            session.close()

    def for_scope(
        self, organization_external_id: str, user_external_id: str
    ) -> "SQLAlchemyV2Repositories":
        return SQLAlchemyV2Repositories(
            self.session_factory,
            self.config,
            organization_external_id=organization_external_id,
            user_external_id=user_external_id,
            seed_synthetic=False,
        )

    def next_id(self, prefix: str) -> str:
        with self._id_lock:
            return f"{prefix}-{uuid4().hex}"

    def seed_if_empty(self) -> None:
        if not self._seed_synthetic or self.learners.list():
            return
        from app.services.v2_repositories import V2Repositories

        source = V2Repositories()
        with self.transaction():
            for learner in source.learners.list():
                self.learners.save(learner)
            for record in source.records.list():
                self.records.save(record)
            for item in source.materials_library.list():
                self.materials_library.save(item)
            for item in source.image_assets.list():
                self.image_assets.save(item)
            for item in source.sessions.list():
                self.sessions.save(item)
            for item in source.recent_lessons.list():
                self.recent_lessons.save(item)
            for item in source.progress_summaries.list():
                self.progress_summaries.save(item)
            for item in source.progress_signals.list():
                self.progress_signals.save(item)
            for item in source.progress_data.list():
                self.progress_data.save(item)
            for learner in source.learners.list():
                for observation in source.progress.for_learner(learner.id):
                    self.progress.add(observation)

    def _resolve_scope(self, session: Session) -> RepositoryScope:
        authenticated_scope = get_authenticated_scope()
        organization_external_id = (
            authenticated_scope.organization_external_id
            if authenticated_scope is not None
            else self.organization_external_id
        )
        user_external_id = (
            authenticated_scope.user_external_id
            if authenticated_scope is not None
            else self.user_external_id
        )
        organization = session.scalar(
            select(entities.Organization).where(
                entities.Organization.external_id == organization_external_id,
                entities.Organization.deleted_at.is_(None),
            )
        )
        if organization is None:
            organization = entities.Organization(
                external_id=organization_external_id,
                name="Lesson Kit Studio Organization",
            )
            session.add(organization)
            session.flush()
        user = session.scalar(
            select(entities.User).where(
                entities.User.external_id == user_external_id,
                entities.User.deleted_at.is_(None),
            )
        )
        if user is None:
            user = entities.User(
                external_id=user_external_id,
                display_name="Lesson Kit Studio Teacher",
            )
            session.add(user)
            session.flush()
        membership = session.scalar(
            select(entities.OrganizationMembership).where(
                entities.OrganizationMembership.organization_id == organization.id,
                entities.OrganizationMembership.user_id == user.id,
                entities.OrganizationMembership.deleted_at.is_(None),
            )
        )
        if membership is None:
            session.add(
                entities.OrganizationMembership(
                    organization_id=organization.id,
                    user_id=user.id,
                    role="teacher",
                )
            )
            session.flush()
        return RepositoryScope(organization.id, user.id)

    def _learner_row(
        self, session: Session, external_id: str, required: bool = True
    ) -> entities.Learner | None:
        scope = self._resolve_scope(session)
        row = session.scalar(
            select(entities.Learner).where(
                entities.Learner.organization_id == scope.organization_id,
                entities.Learner.created_by_user_id == scope.user_id,
                entities.Learner.external_id == external_id,
                entities.Learner.deleted_at.is_(None),
            )
        )
        if row is None and required:
            raise RuntimeError("Learner persistence reference is missing")
        return row

    def _session_row(self, session: Session, external_id: str):
        scope = self._resolve_scope(session)
        return session.scalar(
            select(entities.TeachingSession).where(
                entities.TeachingSession.organization_id == scope.organization_id,
                entities.TeachingSession.created_by_user_id == scope.user_id,
                entities.TeachingSession.external_id == external_id,
                entities.TeachingSession.deleted_at.is_(None),
            )
        )

    def _conversation_factory(
        self, session: Session, item: AIChatState, payload: dict[str, Any]
    ) -> entities.LessonConversation:
        scope = self._resolve_scope(session)
        learner = self._learner_row(session, item.learner_id)
        row = entities.LessonConversation(
            external_id=item.conversation_id,
            learner_id=learner.id,
            state_payload=payload,
            organization_id=scope.organization_id,
            created_by_user_id=scope.user_id,
        )
        # Generic repositories expect a payload attribute.
        row.payload = payload  # type: ignore[attr-defined]
        return row

    def _package_factory(self, session: Session, item, payload):
        scope = self._resolve_scope(session)
        learner_external_id = getattr(
            item, "learner_id", getattr(item, "learnerId", "")
        )
        learner = self._learner_row(session, learner_external_id)
        draft_external_id = getattr(item, "draft_id", getattr(item, "draftId", ""))
        draft = session.scalar(
            select(entities.LessonDesignDraft).where(
                entities.LessonDesignDraft.organization_id == scope.organization_id,
                entities.LessonDesignDraft.created_by_user_id == scope.user_id,
                entities.LessonDesignDraft.external_id == draft_external_id,
                entities.LessonDesignDraft.deleted_at.is_(None),
            )
        )
        return entities.LessonPackage(
            external_id=item.id,
            learner_id=learner.id,
            draft_id=draft.id if draft else None,
            status="draft",
            payload=payload,
            organization_id=scope.organization_id,
            created_by_user_id=scope.user_id,
        )

    def _material_factory(self, session: Session, item, payload):
        scope = self._resolve_scope(session)
        package_external_id = getattr(
            item, "package_id", getattr(item, "packageId", "")
        )
        package = session.scalar(
            select(entities.LessonPackage).where(
                entities.LessonPackage.organization_id == scope.organization_id,
                entities.LessonPackage.created_by_user_id == scope.user_id,
                entities.LessonPackage.external_id == package_external_id,
                entities.LessonPackage.deleted_at.is_(None),
            )
        )
        if package is None:
            raise RuntimeError("Lesson package persistence reference is missing")
        return entities.GeneratedMaterial(
            external_id=item.id,
            package_id=package.id,
            material_type=item.type,
            status=item.status,
            payload=payload,
            organization_id=scope.organization_id,
            created_by_user_id=scope.user_id,
        )

    def _library_factory(self, session: Session, item, payload):
        scope = self._resolve_scope(session)
        return entities.MaterialLibraryItem(
            external_id=item.id,
            title=item.title,
            material_type=item.type,
            reusable=item.reusable,
            payload=payload,
            organization_id=scope.organization_id,
            created_by_user_id=scope.user_id,
        )

    def _image_factory(self, session: Session, item, payload):
        scope = self._resolve_scope(session)
        return entities.ImageAsset(
            external_id=item.id,
            concept=item.concept,
            source_type=item.sourceType,
            approved=item.approved,
            payload=payload,
            organization_id=scope.organization_id,
            created_by_user_id=scope.user_id,
        )

    def _teaching_session_factory(self, session: Session, item, payload):
        scope = self._resolve_scope(session)
        learner = self._learner_row(session, item.learner_id)
        return entities.TeachingSession(
            external_id=item.id,
            learner_id=learner.id,
            status=item.status,
            payload=payload,
            organization_id=scope.organization_id,
            created_by_user_id=scope.user_id,
        )

    def _export_job_factory(self, session: Session, item, payload):
        scope = self._resolve_scope(session)
        learner = self._learner_row(session, item.learnerId)
        package = session.scalar(
            select(entities.LessonPackage).where(
                entities.LessonPackage.organization_id == scope.organization_id,
                entities.LessonPackage.created_by_user_id == scope.user_id,
                entities.LessonPackage.external_id == item.packageId,
                entities.LessonPackage.deleted_at.is_(None),
            )
        )
        if item.packageId and package is None:
            raise RuntimeError("Lesson package persistence reference is missing")
        return entities.ExportJob(
            external_id=item.exportId,
            learner_id=learner.id,
            lesson_package_id=package.id if package is not None else None,
            status=item.status,
            export_format=item.format,
            storage_key=item.storageObjectKey,
            file_size_bytes=item.fileSizeBytes,
            completed_at=_parse_datetime(item.completedAt),
            expires_at=_parse_datetime(item.expiresAt),
            payload=payload,
            organization_id=scope.organization_id,
            created_by_user_id=scope.user_id,
        )

    def record_audit(
        self,
        action: str,
        entity_type: str,
        entity_external_id: str,
        metadata: dict | None = None,
    ) -> None:
        with self.session_scope(write=True) as session:
            scope = self._resolve_scope(session)
            session.add(
                entities.AuditEvent(
                    organization_id=scope.organization_id,
                    actor_user_id=scope.user_id,
                    action=action,
                    entity_type=entity_type,
                    entity_external_id=entity_external_id,
                    metadata_payload=metadata or {},
                )
            )

    def _audit(
        self,
        session: Session,
        action: str,
        entity_type: str,
        entity_external_id: str,
    ) -> None:
        scope = self._resolve_scope(session)
        session.add(
            entities.AuditEvent(
                organization_id=scope.organization_id,
                actor_user_id=scope.user_id,
                action=action,
                entity_type=entity_type,
                entity_external_id=entity_external_id,
                metadata_payload={},
            )
        )
