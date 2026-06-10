"""Cleanup invalid student names

Revision ID: i5j6k7l8m9n0
Revises: h3i4j5k6l7m8
Create Date: 2026-06-10 13:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'i5j6k7l8m9n0'
down_revision = 'h3i4j5k6l7m8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Remove students with invalid names:
    - Only digits
    - "No", "N/A", etc.
    - Less than 2 characters
    - No letters (Cyrillic or Latin)
    """
    # Delete students with invalid names
    op.execute("""
        DELETE FROM students
        WHERE 
            -- Only digits
            name ~ '^[0-9]+$'
            -- "No" or variations
            OR LOWER(name) ~ '^no\.?$'
            -- "N/A" or variations  
            OR LOWER(name) ~ '^n/a$'
            -- Only special characters
            OR name ~ '^[-_]+$'
            -- Unnamed patterns
            OR LOWER(name) LIKE 'unnamed%'
            -- Names starting with #
            OR name ~ '^#[0-9]+'
            -- Too short (less than 2 characters)
            OR LENGTH(TRIM(name)) < 2
            -- No letters (must contain at least one Cyrillic or Latin letter)
            OR NOT (name ~ '[а-яА-ЯёЁa-zA-Z]')
            -- Empty or whitespace only
            OR TRIM(name) = ''
    """)
    
    print("✅ Cleaned up invalid student records")


def downgrade() -> None:
    """
    No downgrade - we don't want to restore invalid data
    """
    pass
