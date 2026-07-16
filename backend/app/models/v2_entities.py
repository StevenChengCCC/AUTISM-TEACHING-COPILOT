from __future__ import annotations

from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.sql import func

from app.core.database import Base


class TimestampVersionMixin:
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")


class OwnedEntityMixin(TimestampVersionMixin):
    organization_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )


class Organization(Base, TimestampVersionMixin):
    __tablename__ = "v2_organizations"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_id = Column(String(100), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)


class User(Base, TimestampVersionMixin):
    __tablename__ = "v2_users"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_id = Column(String(255), nullable=False, unique=True, index=True)
    email = Column(String(320), nullable=True, index=True)
    display_name = Column(String(255), nullable=False)


class OrganizationMembership(Base, TimestampVersionMixin):
    __tablename__ = "v2_organization_memberships"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "user_id", name="uq_v2_membership_organization_user"
        ),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(50), nullable=False, default="teacher")


class Learner(Base, OwnedEntityMixin):
    __tablename__ = "v2_learners"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "external_id", name="uq_v2_learner_org_external"
        ),
        UniqueConstraint("organization_id", "code", name="uq_v2_learner_org_code"),
        Index("ix_v2_learner_org_owner", "organization_id", "created_by_user_id"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_id = Column(String(100), nullable=False)
    code = Column(String(100), nullable=False)
    age = Column(Integer, nullable=False)
    avatar = Column(String(64), nullable=False, default="")


class LearnerProfile(Base, OwnedEntityMixin):
    __tablename__ = "v2_learner_profiles"
    __table_args__ = (
        UniqueConstraint("learner_id", name="uq_v2_profile_learner"),
        Index("ix_v2_profile_org_learner", "organization_id", "learner_id"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    learner_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_learners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    review_status = Column(String(30), nullable=False, default="draft")
    payload = Column(JSON, nullable=False, default=dict)


class LearnerProfileVersion(Base, OwnedEntityMixin):
    __tablename__ = "v2_learner_profile_versions"
    __table_args__ = (
        UniqueConstraint(
            "profile_id", "snapshot_version", name="uq_v2_profile_version"
        ),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_learner_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_version = Column(Integer, nullable=False)
    payload = Column(JSON, nullable=False)


class ProfileSignal(Base, OwnedEntityMixin):
    __tablename__ = "v2_profile_signals"
    __table_args__ = (
        UniqueConstraint(
            "profile_id", "external_id", name="uq_v2_profile_signal_external"
        ),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_id = Column(String(150), nullable=False)
    profile_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_learner_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False, default="suggested")
    payload = Column(JSON, nullable=False, default=dict)


class LearnerRecord(Base, OwnedEntityMixin):
    __tablename__ = "v2_learner_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "external_id", name="uq_v2_record_org_external"
        ),
        Index("ix_v2_record_org_learner", "organization_id", "learner_id"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_id = Column(String(150), nullable=False)
    learner_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_learners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_name = Column(String(512), nullable=False)
    file_type = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False)
    storage_key = Column(Text, nullable=True)
    declared_content_type = Column(
        String(255), nullable=False, default="application/octet-stream"
    )
    expected_size_bytes = Column(Integer, nullable=False, default=0)
    object_size_bytes = Column(Integer, nullable=True)
    malware_scan_status = Column(String(30), nullable=False, default="not_configured")
    parsing_message = Column(Text, nullable=False, default="")
    deletion_status = Column(String(30), nullable=False, default="active")
    upload_completed_at = Column(DateTime(timezone=True), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), nullable=False)


class ExtractedRecordText(Base, OwnedEntityMixin):
    __tablename__ = "v2_extracted_record_texts"
    __table_args__ = (
        UniqueConstraint("record_id", name="uq_v2_extracted_text_record"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    record_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_learner_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text = Column(Text, nullable=False, default="")
    teacher_corrected_text = Column(Text, nullable=True)
    extraction_method = Column(String(30), nullable=False, default="parser")
    corrected_at = Column(DateTime(timezone=True), nullable=True)
    extraction_status = Column(String(30), nullable=False, default="complete")


class LessonConversation(Base, OwnedEntityMixin):
    __tablename__ = "v2_lesson_conversations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "external_id", name="uq_v2_conversation_org_external"
        ),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_id = Column(String(150), nullable=False)
    learner_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_learners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    state_payload = Column(JSON, nullable=False, default=dict)

    @property
    def payload(self):
        return self.state_payload

    @payload.setter
    def payload(self, value):
        self.state_payload = value


class LessonMessage(Base, OwnedEntityMixin):
    __tablename__ = "v2_lesson_messages"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "external_id", name="uq_v2_message_conversation_external"
        ),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_id = Column(String(150), nullable=False)
    conversation_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_lesson_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(30), nullable=False)
    content = Column(Text, nullable=False)
    message_created_at = Column(DateTime(timezone=True), nullable=False)


class LessonDesignDraft(Base, OwnedEntityMixin):
    __tablename__ = "v2_lesson_design_drafts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "external_id", name="uq_v2_draft_org_external"
        ),
        UniqueConstraint("conversation_id", name="uq_v2_draft_conversation"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_id = Column(String(150), nullable=False)
    learner_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_learners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_lesson_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payload = Column(JSON, nullable=False, default=dict)


class LessonPackage(Base, OwnedEntityMixin):
    __tablename__ = "v2_lesson_packages"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "external_id", name="uq_v2_package_org_external"
        ),
        Index("ix_v2_package_org_learner", "organization_id", "learner_id"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_id = Column(String(150), nullable=False)
    learner_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_learners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    draft_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_lesson_design_drafts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = Column(String(30), nullable=False, default="draft")
    payload = Column(JSON, nullable=False, default=dict)


class LessonPackageVersion(Base, OwnedEntityMixin):
    __tablename__ = "v2_lesson_package_versions"
    __table_args__ = (
        UniqueConstraint(
            "package_id", "snapshot_version", name="uq_v2_package_version"
        ),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    package_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_lesson_packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_version = Column(Integer, nullable=False)
    payload = Column(JSON, nullable=False)


class GeneratedMaterial(Base, OwnedEntityMixin):
    __tablename__ = "v2_generated_materials"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "external_id", name="uq_v2_material_org_external"
        ),
        Index("ix_v2_material_org_package", "organization_id", "package_id"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_id = Column(String(150), nullable=False)
    package_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_lesson_packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    material_type = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)


class GeneratedMaterialVersion(Base, OwnedEntityMixin):
    __tablename__ = "v2_generated_material_versions"
    __table_args__ = (
        UniqueConstraint(
            "material_id", "snapshot_version", name="uq_v2_material_version"
        ),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    material_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_generated_materials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_version = Column(Integer, nullable=False)
    payload = Column(JSON, nullable=False)


class TeachingSession(Base, OwnedEntityMixin):
    __tablename__ = "v2_teaching_sessions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "external_id", name="uq_v2_session_org_external"
        ),
        Index("ix_v2_session_org_learner", "organization_id", "learner_id"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_id = Column(String(150), nullable=False)
    learner_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_learners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lesson_package_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_lesson_packages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = Column(String(30), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)


class ProgressObservation(Base, OwnedEntityMixin):
    __tablename__ = "v2_progress_observations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "external_id", name="uq_v2_progress_org_external"
        ),
        Index("ix_v2_progress_org_learner", "organization_id", "learner_id"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_id = Column(String(180), nullable=False)
    learner_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_learners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    teaching_session_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_teaching_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    observation_type = Column(String(40), nullable=False, default="observation")
    observed_at = Column(DateTime(timezone=True), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)


class MaterialLibraryItem(Base, OwnedEntityMixin):
    __tablename__ = "v2_material_library_items"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "external_id", name="uq_v2_library_org_external"
        ),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_id = Column(String(150), nullable=False)
    title = Column(String(255), nullable=False)
    material_type = Column(String(100), nullable=False)
    reusable = Column(Boolean, nullable=False, default=True)
    payload = Column(JSON, nullable=False, default=dict)


class ImageAsset(Base, OwnedEntityMixin):
    __tablename__ = "v2_image_assets"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "external_id", name="uq_v2_image_org_external"
        ),
        Index("ix_v2_image_org_concept", "organization_id", "concept"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_id = Column(String(180), nullable=False)
    concept = Column(String(255), nullable=False)
    source_type = Column(String(30), nullable=False)
    approved = Column(Boolean, nullable=False, default=False)
    payload = Column(JSON, nullable=False, default=dict)


class ExportJob(Base, OwnedEntityMixin):
    __tablename__ = "v2_export_jobs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "external_id", name="uq_v2_export_org_external"
        ),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_id = Column(String(180), nullable=False)
    learner_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_learners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lesson_package_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_lesson_packages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = Column(String(30), nullable=False)
    export_format = Column(String(20), nullable=False)
    storage_key = Column(Text, nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    payload = Column(JSON, nullable=False, default=dict)


class AuditEvent(Base):
    __tablename__ = "v2_audit_events"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("v2_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action = Column(String(100), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_external_id = Column(String(180), nullable=True, index=True)
    metadata_payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PersistenceProjection(Base, OwnedEntityMixin):
    """Durable read projection for existing DTOs without a dedicated aggregate."""

    __tablename__ = "v2_persistence_projections"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "projection_type",
            "external_id",
            name="uq_v2_projection_org_type_external",
        ),
        Index("ix_v2_projection_org_type", "organization_id", "projection_type"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    projection_type = Column(String(60), nullable=False)
    external_id = Column(String(180), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
