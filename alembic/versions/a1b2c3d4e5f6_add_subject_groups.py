"""add_subject_groups

Revision ID: a1b2c3d4e5f6
Revises: 812064162958
Create Date: 2025-03-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '812064162958'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'subject_groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('grade_id', sa.Integer(), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['grade_id'], ['grades.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_subject_groups_grade_id'), 'subject_groups', ['grade_id'], unique=False)
    op.create_index(op.f('ix_subject_groups_subject_id'), 'subject_groups', ['subject_id'], unique=False)
    op.create_index(op.f('ix_subject_groups_is_active'), 'subject_groups', ['is_active'], unique=False)
    op.create_index(
        'ix_subject_groups_grade_subject_name',
        'subject_groups',
        ['grade_id', 'subject_id', 'name'],
        unique=True
    )

    op.add_column('teacher_assignments', sa.Column('subject_group_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_teacher_assignments_subject_group',
        'teacher_assignments',
        'subject_groups',
        ['subject_group_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index(
        op.f('ix_teacher_assignments_subject_group_id'),
        'teacher_assignments',
        ['subject_group_id'],
        unique=False
    )

    op.drop_index('ix_teacher_assignment_unique', table_name='teacher_assignments')
    op.execute("""
        CREATE UNIQUE INDEX ix_teacher_assignment_unique ON teacher_assignments
        (teacher_id, subject_id, COALESCE(grade_id, -1), COALESCE(subgroup_id, -1), COALESCE(subject_group_id, -1))
    """)

    op.add_column('scores', sa.Column('subject_group_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_scores_subject_group',
        'scores',
        'subject_groups',
        ['subject_group_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index(op.f('ix_scores_subject_group_id'), 'scores', ['subject_group_id'], unique=False)

    op.create_table(
        'student_subject_group_memberships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('subject_group_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subject_group_id'], ['subject_groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        'ix_student_subject_group_memberships_unique',
        'student_subject_group_memberships',
        ['student_id', 'subject_group_id'],
        unique=True
    )
    op.create_index(op.f('ix_student_subject_group_memberships_student_id'), 'student_subject_group_memberships', ['student_id'], unique=False)
    op.create_index(op.f('ix_student_subject_group_memberships_subject_group_id'), 'student_subject_group_memberships', ['subject_group_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_student_subject_group_memberships_subject_group_id'), table_name='student_subject_group_memberships')
    op.drop_index(op.f('ix_student_subject_group_memberships_student_id'), table_name='student_subject_group_memberships')
    op.drop_index('ix_student_subject_group_memberships_unique', table_name='student_subject_group_memberships')
    op.drop_table('student_subject_group_memberships')

    op.drop_index(op.f('ix_scores_subject_group_id'), table_name='scores')
    op.drop_constraint('fk_scores_subject_group', 'scores', type_='foreignkey')
    op.drop_column('scores', 'subject_group_id')

    op.drop_index('ix_teacher_assignment_unique', table_name='teacher_assignments')
    op.create_index(
        'ix_teacher_assignment_unique',
        'teacher_assignments',
        ['teacher_id', 'subject_id', 'grade_id', 'subgroup_id'],
        unique=True
    )
    op.drop_index(op.f('ix_teacher_assignments_subject_group_id'), table_name='teacher_assignments')
    op.drop_constraint('fk_teacher_assignments_subject_group', 'teacher_assignments', type_='foreignkey')
    op.drop_column('teacher_assignments', 'subject_group_id')

    op.drop_index('ix_subject_groups_grade_subject_name', table_name='subject_groups')
    op.drop_index(op.f('ix_subject_groups_is_active'), table_name='subject_groups')
    op.drop_index(op.f('ix_subject_groups_subject_id'), table_name='subject_groups')
    op.drop_index(op.f('ix_subject_groups_grade_id'), table_name='subject_groups')
    op.drop_table('subject_groups')
