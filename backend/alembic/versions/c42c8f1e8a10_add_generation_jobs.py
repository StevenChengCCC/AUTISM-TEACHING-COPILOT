"""add durable generation jobs

Revision ID: c42c8f1e8a10
Revises: a61f7e9c2d44
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c42c8f1e8a10"
down_revision: Union[str, Sequence[str], None] = "a61f7e9c2d44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v2_generation_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=180), nullable=False),
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("lesson_package_id", sa.Uuid(), nullable=True),
        sa.Column("draft_external_id", sa.String(length=180), nullable=False),
        sa.Column("lesson_spec_id", sa.String(length=180), nullable=False),
        sa.Column("lesson_spec_revision", sa.Integer(), nullable=False),
        sa.Column("package_plan_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["v2_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["learner_id"], ["v2_learners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lesson_package_id"], ["v2_lesson_packages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["v2_organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "external_id", name="uq_v2_generation_job_org_external"),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_v2_generation_job_org_key"),
    )
    op.create_index("ix_v2_generation_job_org_status", "v2_generation_jobs", ["organization_id", "status"])
    op.create_index("ix_v2_generation_job_org_learner", "v2_generation_jobs", ["organization_id", "learner_id"])
    op.create_index("ix_v2_generation_jobs_learner_id", "v2_generation_jobs", ["learner_id"])
    op.create_index("ix_v2_generation_jobs_lesson_package_id", "v2_generation_jobs", ["lesson_package_id"])
    op.create_index("ix_v2_generation_jobs_draft_external_id", "v2_generation_jobs", ["draft_external_id"])
    op.create_index("ix_v2_generation_jobs_deleted_at", "v2_generation_jobs", ["deleted_at"])
    op.create_index("ix_v2_generation_jobs_organization_id", "v2_generation_jobs", ["organization_id"])
    op.create_index("ix_v2_generation_jobs_created_by_user_id", "v2_generation_jobs", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_table("v2_generation_jobs")
