from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class ChildProfile(Base):
    __tablename__ = "child_profiles"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    age = Column(Integer, nullable=True)
    diagnosis_level = Column(String(100), nullable=True)
    attention_span_minutes = Column(Integer, nullable=True)
    communication_level = Column(String(255), nullable=True)
    interests_json = Column(Text, default="[]")
    reinforcers_json = Column(Text, default="[]")
    behavior_notes = Column(Text, default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    goals = relationship("TeachingGoal", back_populates="child")
    lesson_packages = relationship("LessonPackage", back_populates="child")
    records = relationship("SessionRecord", back_populates="child")


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
