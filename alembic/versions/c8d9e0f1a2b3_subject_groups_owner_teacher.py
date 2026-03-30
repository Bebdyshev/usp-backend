"""subject_groups owner_teacher_id

Revision ID: c8d9e0f1a2b3
Revises: a1b2c3d4e5f6
Create Date: 2026-03-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
    op.drop_constraint("fk_subject_groups_owner_teacher", "subject_groups", type_="foreignkey")
    op.drop_index(op.f("ix_subject_groups_owner_teacher_id"), table_name="subject_groups")
    op.drop_column("subject_groups", "owner_teacher_id")
