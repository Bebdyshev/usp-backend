"""Rename subject groups from 'Group #N' to 'Группа N'

Revision ID: h3i4j5k6l7m8
Revises: g2h3i4j5k6l7
Create Date: 2026-06-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h3i4j5k6l7m8"
down_revision: Union[str, Sequence[str], None] = "g2h3i4j5k6l7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update existing subject group names from 'Group #N' to 'Группа N'
    op.execute("""
        UPDATE subject_groups
        SET name = REPLACE(name, 'Group #', 'Группа ')
        WHERE name ~ '^Group #[0-9]+$'
    """)


def downgrade() -> None:
    # Revert 'Группа N' back to 'Group #N'
    op.execute("""
        UPDATE subject_groups
        SET name = REPLACE(name, 'Группа ', 'Group #')
        WHERE name ~ '^Группа [0-9]+$'
    """)
