"""add learner profile version history

Revision ID: 9f2a6d4b1c30
Revises: 875cbc95a52b
Create Date: 2026-07-16 02:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f2a6d4b1c30"
down_revision: Union[str, Sequence[str], None] = "875cbc95a52b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "v2_learner_profile_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["organization_id"], ["v2_organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["v2_learner_profiles.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_id", "snapshot_version", name="uq_v2_profile_version"
        ),
    )
    op.create_index(
        "ix_v2_learner_profile_versions_profile_id",
        "v2_learner_profile_versions",
        ["profile_id"],
    )
    op.create_index(
        "ix_v2_learner_profile_versions_organization_id",
        "v2_learner_profile_versions",
        ["organization_id"],
    )
    op.create_index(
        "ix_v2_learner_profile_versions_created_by_user_id",
        "v2_learner_profile_versions",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_v2_learner_profile_versions_deleted_at",
        "v2_learner_profile_versions",
        ["deleted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_v2_learner_profile_versions_deleted_at",
        table_name="v2_learner_profile_versions",
    )
    op.drop_index(
        "ix_v2_learner_profile_versions_created_by_user_id",
        table_name="v2_learner_profile_versions",
    )
    op.drop_index(
        "ix_v2_learner_profile_versions_organization_id",
        table_name="v2_learner_profile_versions",
    )
    op.drop_index(
        "ix_v2_learner_profile_versions_profile_id",
        table_name="v2_learner_profile_versions",
    )
    op.drop_table("v2_learner_profile_versions")
