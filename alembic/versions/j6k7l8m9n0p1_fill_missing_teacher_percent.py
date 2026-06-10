"""Fill missing teacher_percent values

Revision ID: j6k7l8m9n0p1
Revises: i5j6k7l8m9n0
Create Date: 2026-06-10 13:40:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'j6k7l8m9n0p1'
down_revision = 'i5j6k7l8m9n0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Fill missing teacher_percent values:
    - If teacher_percent is NULL but previous_class_score exists, 
      use previous_class_score as teacher_percent (assumption: teacher predicted similar to previous year)
    - Recalculate predicted_scores and danger_level based on the new values
    """
    
    # Step 1: Fill teacher_percent from previous_class_score where it's NULL
    op.execute("""
        UPDATE scores
        SET teacher_percent = previous_class_score
        WHERE teacher_percent IS NULL 
          AND previous_class_score IS NOT NULL
          AND previous_class_score > 0
    """)
    
    # Step 2: For records still without teacher_percent, infer from actual_scores JSON/JSONB array
    op.execute("""
        UPDATE scores
        SET teacher_percent = (
            SELECT AVG(val::float)
            FROM jsonb_array_elements_text(scores.actual_scores::jsonb) AS val
            WHERE val ~ '^-?[0-9]+(\\.[0-9]+)?$'
              AND (val::float) > 0
        )
        WHERE teacher_percent IS NULL
          AND actual_scores IS NOT NULL
          AND jsonb_typeof(actual_scores::jsonb) = 'array'
          AND EXISTS (
              SELECT 1
              FROM jsonb_array_elements_text(scores.actual_scores::jsonb) AS val
              WHERE val ~ '^-?[0-9]+(\\.[0-9]+)?$'
                AND (val::float) > 0
          )
    """)
    
    print("✅ Filled missing teacher_percent values")
    print("⚠️ Note: Predicted scores should be recalculated by re-syncing or re-uploading data")


def downgrade() -> None:
    """
    No downgrade - we don't want to remove inferred data
    """
    pass
