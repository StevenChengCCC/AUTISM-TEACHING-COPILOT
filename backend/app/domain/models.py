from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class ChildProfile(Base):
    __tablename__ = "child_profiles"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    age = Column(Integer, nullable=True)
    diagnosis_level = Column(String(100), nullable=True)
    attention_span_minutes = Column(Integer, nullable=True)
    communication_mode = Column(String(255), nullable=True)
    communication_level = Column(String(255), nullable=True)
    current_level = Column(Text, default="")
    interests_json = Column(Text, default="[]")
    reinforcers_json = Column(Text, default="[]")
    preferred_reinforcers_json = Column(Text, default="[]")
    prompting_that_works = Column(Text, default="")
    avoid_notes = Column(Text, default="")
    behavior_notes = Column(Text, default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    goals = relationship("TeachingGoal", back_populates="child")
    lesson_packages = relationship("LessonPackage", back_populates="child")
    records = relationship("SessionRecord", back_populates="child")
    uploaded_materials = relationship("UploadedMaterial", back_populates="child")


class TeachingGoal(Base):
    __tablename__ = "teaching_goals"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("child_profiles.id"), nullable=False)
    target_skill = Column(String(255), nullable=False)
    concept = Column(String(255), nullable=True)
    status = Column(String(50), default="active")
    mastery_level = Column(Integer, default=0)
    notes = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    child = relationship("ChildProfile", back_populates="goals")
    lesson_packages = relationship("LessonPackage", back_populates="goal")
    records = relationship("SessionRecord", back_populates="goal")


class ImageAsset(Base):
    __tablename__ = "image_assets"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    source_type = Column(
        String(50), nullable=False
    )  # reused/searched/generated/uploaded
    source_url = Column(Text, nullable=True)
    thumbnail_url = Column(Text, nullable=True)
    local_path = Column(Text, nullable=True)
    tags_json = Column(Text, default="[]")
    skill_target = Column(String(255), nullable=True)
    concept = Column(String(255), nullable=True)
    variation_type = Column(String(100), nullable=True)
    quality_score = Column(Integer, default=0)
    license_info = Column(Text, nullable=True)
    reason = Column(Text, default="")
    approved = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class LessonPackage(Base):
    __tablename__ = "lesson_packages"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("child_profiles.id"), nullable=False)
    goal_id = Column(Integer, ForeignKey("teaching_goals.id"), nullable=True)
    target_skill = Column(String(255), nullable=False)
    duration_minutes = Column(Integer, default=25)
    selected_image_asset_ids_json = Column(Text, default="[]")
    printable_card_pdf_links_json = Column(Text, default="{}")
    package_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    child = relationship("ChildProfile", back_populates="lesson_packages")
    goal = relationship("TeachingGoal", back_populates="lesson_packages")


class SessionRecord(Base):
    __tablename__ = "session_records"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("child_profiles.id"), nullable=False)
    goal_id = Column(Integer, ForeignKey("teaching_goals.id"), nullable=True)
    target_skill = Column(String(255), nullable=False)
    independent_count = Column(Integer, default=0)
    prompted_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    notes = Column(Text, default="")
    mastery_level = Column(Integer, default=0)
    progress_delta = Column(Integer, default=0)
    confidence_score = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    child = relationship("ChildProfile", back_populates="records")
    goal = relationship("TeachingGoal", back_populates="records")


LessonPlan = LessonPackage


class UploadedMaterial(Base):
    __tablename__ = "uploaded_materials"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("child_profiles.id"), nullable=False)
    title = Column(String(255), nullable=False)
    material_type = Column(String(100), default="document")
    source_path = Column(Text, nullable=True)
    extracted_text = Column(Text, default="")
    status = Column(String(50), default="uploaded")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    child = relationship("ChildProfile", back_populates="uploaded_materials")


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    external_ref = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    display_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    role = Column(String(100), default="teacher")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class TeacherChildAccess(Base):
    __tablename__ = "teacher_child_access"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    child_id = Column(Integer, ForeignKey("child_profiles.id"), nullable=False)
    permission_level = Column(String(100), default="editor")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CurriculumContent(Base):
    __tablename__ = "curriculum_content"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    title = Column(String(255), nullable=False)
    content_type = Column(String(100), default="goal_template")
    content_json = Column(Text, default="{}")
    status = Column(String(50), default="draft")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor_teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(Integer, nullable=True)
    child_id = Column(Integer, ForeignKey("child_profiles.id"), nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    metadata_json = Column(Text, default="{}")
