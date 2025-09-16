"""Fix JSON columns and add GIN indexes

Revision ID: 93262454752a
Revises: a055c33aee96
Create Date: 2025-09-16 10:50:21.947058

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '93262454752a'
down_revision: Union[str, Sequence[str], None] = 'a055c33aee96'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Convert JSON columns to JSONB
    op.execute("ALTER TABLE scores ALTER COLUMN actual_scores TYPE JSONB USING actual_scores::JSONB")
    op.execute("ALTER TABLE scores ALTER COLUMN predicted_scores TYPE JSONB USING predicted_scores::JSONB")
    
    # Drop old B-tree indexes if they exist
    op.execute("DROP INDEX IF EXISTS ix_scores_actual_scores")
    op.execute("DROP INDEX IF EXISTS ix_scores_predicted_scores")
    
    # Create GIN indexes for JSONB columns
    op.execute("CREATE INDEX IF NOT EXISTS ix_scores_actual_scores_gin ON scores USING GIN (actual_scores)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_scores_predicted_scores_gin ON scores USING GIN (predicted_scores)")
    
    # Create composite indexes for better performance
    op.execute("CREATE INDEX IF NOT EXISTS ix_scores_student_subject ON scores (student_id, subject_name)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_scores_grade_semester ON scores (grade_id, semester)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_grades_grade_parallel ON grades (grade, parallel)")


def downgrade() -> None:
    """Downgrade schema."""
    # Drop GIN indexes
    op.execute("DROP INDEX IF EXISTS ix_grades_grade_parallel")
    op.execute("DROP INDEX IF EXISTS ix_scores_grade_semester")
    op.execute("DROP INDEX IF EXISTS ix_scores_student_subject")
    op.execute("DROP INDEX IF EXISTS ix_scores_predicted_scores_gin")
    op.execute("DROP INDEX IF EXISTS ix_scores_actual_scores_gin")
    
    # Convert JSONB back to JSON
    op.execute("ALTER TABLE scores ALTER COLUMN actual_scores TYPE JSON USING actual_scores::JSON")
    op.execute("ALTER TABLE scores ALTER COLUMN predicted_scores TYPE JSON USING predicted_scores::JSON")
    
    # Recreate B-tree indexes
    op.create_index('ix_scores_actual_scores', 'scores', ['actual_scores'])
    op.create_index('ix_scores_predicted_scores', 'scores', ['predicted_scores'])
