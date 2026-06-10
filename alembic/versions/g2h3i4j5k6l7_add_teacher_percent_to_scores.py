"""Add teacher_percent to scores

Revision ID: g2h3i4j5k6l7
Revises: f1a2b3c4d5e7
Create Date: 2026-06-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g2h3i4j5k6l7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scores", sa.Column("teacher_percent", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("scores", "teacher_percent")
