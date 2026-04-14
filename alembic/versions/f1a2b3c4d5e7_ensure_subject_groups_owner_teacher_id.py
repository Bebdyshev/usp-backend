"""Ensure subject_groups.owner_teacher_id exists (repair drifted DBs)

Revision ID: f1a2b3c4d5e7
Revises: e7f8a9b0c1d2
Create Date: 2026-04-14

Some deployments reached alembic head without applying c8d9e0f1a2b3 DDL
(e.g. stamp, restore). This revision idempotently adds the column if missing.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e7"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'subject_groups'
              AND column_name = 'owner_teacher_id'
            """
        )
    ).first()
    if row is not None:
        return

    op.add_column(
        "subject_groups",
        sa.Column("owner_teacher_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_subject_groups_owner_teacher_id"),
        "subject_groups",
        ["owner_teacher_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_subject_groups_owner_teacher",
        "subject_groups",
        "users",
        ["owner_teacher_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # No-op: same column may come from c8d9e0f1a2b3; dropping here would risk data loss.
    pass
