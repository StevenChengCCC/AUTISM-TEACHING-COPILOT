"""add durable teacher handoff export state

Revision ID: a61f7e9c2d44
Revises: 9f2a6d4b1c30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a61f7e9c2d44"
down_revision: Union[str, Sequence[str], None] = "9f2a6d4b1c30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("v2_export_jobs") as batch:
        batch.add_column(sa.Column("learner_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("file_size_bytes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.alter_column("lesson_package_id", existing_type=sa.Uuid(), nullable=True)
        batch.create_foreign_key(
            "fk_v2_export_jobs_learner_id", "v2_learners", ["learner_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_index("ix_v2_export_jobs_learner_id", ["learner_id"])
        batch.create_index("ix_v2_export_jobs_expires_at", ["expires_at"])

    # Existing rows are legacy mock export metadata. Link them through their package.
    op.execute(
        "UPDATE v2_export_jobs SET learner_id = "
        "(SELECT learner_id FROM v2_lesson_packages WHERE v2_lesson_packages.id = v2_export_jobs.lesson_package_id) "
        "WHERE learner_id IS NULL"
    )
    with op.batch_alter_table("v2_export_jobs") as batch:
        batch.alter_column("learner_id", existing_type=sa.Uuid(), nullable=False)


def downgrade() -> None:
    # Standalone handoff exports cannot be represented by the old schema.
    op.execute("DELETE FROM v2_export_jobs WHERE lesson_package_id IS NULL")
    with op.batch_alter_table("v2_export_jobs") as batch:
        batch.alter_column("lesson_package_id", existing_type=sa.Uuid(), nullable=False)
        batch.drop_index("ix_v2_export_jobs_expires_at")
        batch.drop_index("ix_v2_export_jobs_learner_id")
        batch.drop_constraint("fk_v2_export_jobs_learner_id", type_="foreignkey")
        batch.drop_column("expires_at")
        batch.drop_column("completed_at")
        batch.drop_column("file_size_bytes")
        batch.drop_column("learner_id")
