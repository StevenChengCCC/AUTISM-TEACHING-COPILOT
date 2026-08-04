"""add goal-specific session outcomes

Revision ID: d73a10f2b9c4
Revises: c42c8f1e8a10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d73a10f2b9c4"
down_revision: Union[str, Sequence[str], None] = "c42c8f1e8a10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v2_session_outcomes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=180), nullable=False),
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("teaching_session_id", sa.Uuid(), nullable=False),
        sa.Column("lesson_package_id", sa.Uuid(), nullable=True),
        sa.Column("lesson_package_revision", sa.Integer(), nullable=False),
        sa.Column("lesson_spec_id", sa.String(length=180), nullable=False),
        sa.Column("goal_id", sa.String(length=180), nullable=False),
        sa.Column("goal_revision", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(["teaching_session_id"], ["v2_teaching_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "external_id", name="uq_v2_session_outcome_org_external"),
        sa.UniqueConstraint("organization_id", "teaching_session_id", name="uq_v2_session_outcome_org_session"),
    )
    op.create_index("ix_v2_session_outcome_org_learner", "v2_session_outcomes", ["organization_id", "learner_id"])
    op.create_index("ix_v2_session_outcome_org_goal", "v2_session_outcomes", ["organization_id", "goal_id", "goal_revision"])
    op.create_index("ix_v2_session_outcomes_learner_id", "v2_session_outcomes", ["learner_id"])
    op.create_index("ix_v2_session_outcomes_teaching_session_id", "v2_session_outcomes", ["teaching_session_id"])
    op.create_index("ix_v2_session_outcomes_lesson_package_id", "v2_session_outcomes", ["lesson_package_id"])
    op.create_index("ix_v2_session_outcomes_deleted_at", "v2_session_outcomes", ["deleted_at"])
    op.create_index("ix_v2_session_outcomes_organization_id", "v2_session_outcomes", ["organization_id"])
    op.create_index("ix_v2_session_outcomes_created_by_user_id", "v2_session_outcomes", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_table("v2_session_outcomes")
