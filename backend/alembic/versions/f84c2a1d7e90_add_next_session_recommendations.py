"""add durable next-session recommendations

Revision ID: f84c2a1d7e90
Revises: d73a10f2b9c4
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f84c2a1d7e90"
down_revision: Union[str, Sequence[str], None] = "d73a10f2b9c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v2_next_session_recommendations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=180), nullable=False),
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("goal_id", sa.String(length=180), nullable=False),
        sa.Column("goal_revision", sa.Integer(), nullable=False),
        sa.Column("recommendation_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["v2_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["learner_id"], ["v2_learners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["v2_organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "external_id", name="uq_v2_next_recommendation_org_external"),
    )
    op.create_index(
        "ix_v2_next_recommendation_org_goal",
        "v2_next_session_recommendations",
        ["organization_id", "learner_id", "goal_id", "goal_revision"],
    )
    op.create_index(
        "ix_v2_next_recommendation_org_status",
        "v2_next_session_recommendations",
        ["organization_id", "status"],
    )
    for column in (
        "learner_id", "deleted_at", "organization_id", "created_by_user_id"
    ):
        op.create_index(
            f"ix_v2_next_session_recommendations_{column}",
            "v2_next_session_recommendations",
            [column],
        )


def downgrade() -> None:
    op.drop_table("v2_next_session_recommendations")
