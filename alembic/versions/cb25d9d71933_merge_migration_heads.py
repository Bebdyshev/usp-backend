"""merge_migration_heads

Revision ID: cb25d9d71933
Revises: 93262454752a, add_company_name_to_users
Create Date: 2025-09-23 21:20:48.896565

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cb25d9d71933'
down_revision: Union[str, Sequence[str], None] = ('93262454752a', 'add_company_name_to_users')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
