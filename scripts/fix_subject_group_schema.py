import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


def _get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if database_url:
        return database_url

    raise RuntimeError("DATABASE_URL or POSTGRES_URL is not set")


def _apply_patch() -> None:
    database_url = _get_database_url()
    engine = create_engine(database_url)

    statements = [
        """
        ALTER TABLE teacher_assignments
        ADD COLUMN IF NOT EXISTS subject_group_id INTEGER
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_teacher_assignments_subject_group_id
        ON teacher_assignments (subject_group_id)
        """,
        """
        ALTER TABLE scores
        ADD COLUMN IF NOT EXISTS subject_group_id INTEGER
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_scores_subject_group_id
        ON scores (subject_group_id)
        """,
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'subject_groups'
            ) THEN
                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.table_constraints
                    WHERE table_schema = 'public'
                      AND table_name = 'teacher_assignments'
                      AND constraint_name = 'fk_teacher_assignments_subject_group'
                ) THEN
                    ALTER TABLE teacher_assignments
                    ADD CONSTRAINT fk_teacher_assignments_subject_group
                    FOREIGN KEY (subject_group_id)
                    REFERENCES subject_groups(id)
                    ON DELETE SET NULL;
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.table_constraints
                    WHERE table_schema = 'public'
                      AND table_name = 'scores'
                      AND constraint_name = 'fk_scores_subject_group'
                ) THEN
                    ALTER TABLE scores
                    ADD CONSTRAINT fk_scores_subject_group
                    FOREIGN KEY (subject_group_id)
                    REFERENCES subject_groups(id)
                    ON DELETE SET NULL;
                END IF;
            END IF;
        END
        $$;
        """,
    ]

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def main() -> int:
    try:
        _apply_patch()
    except (RuntimeError, SQLAlchemyError) as error:
        print(f"Schema patch failed: {error}")
        return 1

    print("Schema patch completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
