"""add durable next-session material impact plans

Revision ID: b95e4c2d1a70
Revises: f84c2a1d7e90
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b95e4c2d1a70"
down_revision: Union[str, Sequence[str], None] = "f84c2a1d7e90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v2_next_session_impact_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=180), nullable=False),
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("previous_package_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_package_id", sa.Uuid(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["v2_users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["learner_id"], ["v2_learners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["previous_package_id"], ["v2_lesson_packages.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_package_id"], ["v2_lesson_packages.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["v2_organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "external_id", name="uq_v2_next_impact_plan_org_external"
        ),
    )
    op.create_index(
        "ix_v2_next_impact_plan_org_package",
        "v2_next_session_impact_plans",
        ["organization_id", "previous_package_id"],
    )
    for column in (
        "learner_id",
        "previous_package_id",
        "created_package_id",
        "deleted_at",
        "organization_id",
        "created_by_user_id",
    ):
        op.create_index(
            f"ix_v2_next_session_impact_plans_{column}",
            "v2_next_session_impact_plans",
            [column],
        )


def downgrade() -> None:
    op.drop_table("v2_next_session_impact_plans")
