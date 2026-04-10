"""subject_groups grade_id nullable

Revision ID: e7f8a9b0c1d2
Revises: d4e5f6a7b8c9
Create Date: 2026-04-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("subject_groups", "grade_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column("subject_groups", "grade_id", existing_type=sa.Integer(), nullable=False)
