"""Add missing columns to existing tables

Revision ID: a055c33aee96
Revises: 4edab55ad5f6
Create Date: 2025-09-16 10:49:56.846098

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a055c33aee96'
down_revision: Union[str, Sequence[str], None] = '4edab55ad5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add missing columns to users table
    op.add_column('users', sa.Column('company_name', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('is_active', sa.Integer(), nullable=True, server_default='1'))
    op.add_column('users', sa.Column('created_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('updated_at', sa.DateTime(), nullable=True))
    
    # Add missing columns to grades table
    op.add_column('grades', sa.Column('created_at', sa.DateTime(), nullable=True))
    op.add_column('grades', sa.Column('updated_at', sa.DateTime(), nullable=True))
    
    # Add missing columns to students table
    op.add_column('students', sa.Column('student_id_number', sa.String(50), nullable=True))
    op.add_column('students', sa.Column('phone', sa.String(20), nullable=True))
    op.add_column('students', sa.Column('parent_contact', sa.String(255), nullable=True))
    op.add_column('students', sa.Column('is_active', sa.Integer(), nullable=True, server_default='1'))
    op.add_column('students', sa.Column('created_at', sa.DateTime(), nullable=True))
    op.add_column('students', sa.Column('updated_at', sa.DateTime(), nullable=True))
    
    # Add missing columns to scores table
    op.add_column('scores', sa.Column('semester', sa.Integer(), nullable=True, server_default='1'))
    op.add_column('scores', sa.Column('academic_year', sa.String(10), nullable=True, server_default="'2024-2025'"))
    op.add_column('scores', sa.Column('created_at', sa.DateTime(), nullable=True))
    op.add_column('scores', sa.Column('updated_at', sa.DateTime(), nullable=True))
    op.add_column('scores', sa.Column('grade_id', sa.Integer(), nullable=True))
    
    # Add foreign key constraint for grade_id in scores
    op.create_foreign_key('fk_scores_grade_id', 'scores', 'grades', ['grade_id'], ['id'], ondelete='CASCADE')
    
    # Create indexes
    op.create_index('ix_users_company_name', 'users', ['company_name'])
    op.create_index('ix_users_is_active', 'users', ['is_active'])
    op.create_index('ix_users_created_at', 'users', ['created_at'])
    op.create_index('ix_users_updated_at', 'users', ['updated_at'])
    
    op.create_index('ix_grades_created_at', 'grades', ['created_at'])
    op.create_index('ix_grades_updated_at', 'grades', ['updated_at'])
    
    op.create_index('ix_students_student_id_number', 'students', ['student_id_number'])
    op.create_index('ix_students_phone', 'students', ['phone'])
    op.create_index('ix_students_is_active', 'students', ['is_active'])
    op.create_index('ix_students_created_at', 'students', ['created_at'])
    op.create_index('ix_students_updated_at', 'students', ['updated_at'])
    
    op.create_index('ix_scores_semester', 'scores', ['semester'])
    op.create_index('ix_scores_academic_year', 'scores', ['academic_year'])
    op.create_index('ix_scores_created_at', 'scores', ['created_at'])
    op.create_index('ix_scores_updated_at', 'scores', ['updated_at'])
    op.create_index('ix_scores_grade_id', 'scores', ['grade_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('ix_scores_grade_id', table_name='scores')
    op.drop_index('ix_scores_updated_at', table_name='scores')
    op.drop_index('ix_scores_created_at', table_name='scores')
    op.drop_index('ix_scores_academic_year', table_name='scores')
    op.drop_index('ix_scores_semester', table_name='scores')
    
    op.drop_index('ix_students_updated_at', table_name='students')
    op.drop_index('ix_students_created_at', table_name='students')
    op.drop_index('ix_students_is_active', table_name='students')
    op.drop_index('ix_students_phone', table_name='students')
    op.drop_index('ix_students_student_id_number', table_name='students')
    
    op.drop_index('ix_grades_updated_at', table_name='grades')
    op.drop_index('ix_grades_created_at', table_name='grades')
    
    op.drop_index('ix_users_updated_at', table_name='users')
    op.drop_index('ix_users_created_at', table_name='users')
    op.drop_index('ix_users_is_active', table_name='users')
    op.drop_index('ix_users_company_name', table_name='users')
    
    # Drop foreign key
    op.drop_constraint('fk_scores_grade_id', 'scores', type_='foreignkey')
    
    # Drop columns
    op.drop_column('scores', 'grade_id')
    op.drop_column('scores', 'updated_at')
    op.drop_column('scores', 'created_at')
    op.drop_column('scores', 'academic_year')
    op.drop_column('scores', 'semester')
    
    op.drop_column('students', 'updated_at')
    op.drop_column('students', 'created_at')
    op.drop_column('students', 'is_active')
    op.drop_column('students', 'parent_contact')
    op.drop_column('students', 'phone')
    op.drop_column('students', 'student_id_number')
    
    op.drop_column('grades', 'updated_at')
    op.drop_column('grades', 'created_at')
    
    op.drop_column('users', 'updated_at')
    op.drop_column('users', 'created_at')
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'company_name')
