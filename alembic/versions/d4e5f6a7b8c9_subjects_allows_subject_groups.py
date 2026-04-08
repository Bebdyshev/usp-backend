"""subjects allows_subject_groups

Revision ID: d4e5f6a7b8c9
Revises: c8d9e0f1a2b3
Create Date: 2026-04-08

"""
from typing import Sequence, Union

import unicodedata

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _legacy_name_eligible_for_backfill(subject_name: str) -> bool:
    """Совпадает с прежней эвристикой по названию — только для разового backfill."""
    n = unicodedata.normalize("NFKC", (subject_name or "").strip()).lower()
    if not n:
        return False
    if "физическая культура" in n or "физкультур" in n or "физкультура" in n:
        return False
    if "биофиз" in n:
        return False
    if "физик" in n:
        return True
    if "биолог" in n:
        return True
    if n == "химия" or n.startswith("химия"):
        return True
    if "информатик" in n:
        return True
    return False


def upgrade() -> None:
    op.add_column(
        "subjects",
        sa.Column(
            "allows_subject_groups",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, name FROM subjects")).fetchall()
    for row in rows:
        sid, name = row[0], row[1]
        if _legacy_name_eligible_for_backfill(name or ""):
            conn.execute(
                sa.text("UPDATE subjects SET allows_subject_groups = true WHERE id = :id"),
                {"id": sid},
            )


def downgrade() -> None:
    op.drop_column("subjects", "allows_subject_groups")
