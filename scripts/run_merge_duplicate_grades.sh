#!/usr/bin/env sh
set -eu

# Merge duplicate grades + normalize labels in DB.
# Usage: ./scripts/run_merge_duplicate_grades.sh

python - <<'PY'
from sqlalchemy import text
from config import engine

SQL = """
WITH normalized AS (
  SELECT
    id,
    grade,
    parallel,
    regexp_replace(trim(grade), '\\s+', '', 'g') AS compact_grade,
    COALESCE(NULLIF(upper(trim(parallel)), ''), '') AS parallel_up
  FROM grades
),
parsed AS (
  SELECT
    id,
    grade,
    parallel,
    CASE
      WHEN compact_grade ~ '^\\d{1,2}[A-Za-zА-Яа-яЁёІіҢңҒғҚқӨөҰұҮүҺһ]$'
        THEN regexp_replace(compact_grade, '^([0-9]{1,2}).*$', '\\1')
      WHEN compact_grade ~ '^\\d{1,2}$'
        THEN compact_grade
      ELSE regexp_replace(compact_grade, '^([0-9]{1,2}).*$', '\\1')
    END AS grade_num,
    CASE
      WHEN compact_grade ~ '^\\d{1,2}[A-Za-zА-Яа-яЁёІіҢңҒғҚқӨөҰұҮүҺһ]$'
        THEN upper(regexp_replace(compact_grade, '^[0-9]{1,2}', ''))
      WHEN parallel_up <> '' THEN parallel_up
      ELSE ''
    END AS letter
  FROM normalized
),
keys AS (
  SELECT
    id,
    grade,
    parallel,
    grade_num,
    letter,
    (grade_num || letter) AS key_label
  FROM parsed
),
canonical AS (
  SELECT
    key_label,
    MIN(id) AS keep_id
  FROM keys
  GROUP BY key_label
),
dups AS (
  SELECT
    k.id AS dup_id,
    c.keep_id,
    k.key_label
  FROM keys k
  JOIN canonical c ON c.key_label = k.key_label
  WHERE k.id <> c.keep_id
)
UPDATE students s
SET grade_id = d.keep_id
FROM dups d
WHERE s.grade_id = d.dup_id;

WITH normalized AS (
  SELECT
    id,
    regexp_replace(trim(grade), '\\s+', '', 'g') AS compact_grade,
    COALESCE(NULLIF(upper(trim(parallel)), ''), '') AS parallel_up
  FROM grades
),
parsed AS (
  SELECT
    id,
    CASE
      WHEN compact_grade ~ '^\\d{1,2}[A-Za-zА-Яа-яЁёІіҢңҒғҚқӨөҰұҮүҺһ]$'
        THEN regexp_replace(compact_grade, '^([0-9]{1,2}).*$', '\\1')
      WHEN compact_grade ~ '^\\d{1,2}$'
        THEN compact_grade
      ELSE regexp_replace(compact_grade, '^([0-9]{1,2}).*$', '\\1')
    END AS grade_num,
    CASE
      WHEN compact_grade ~ '^\\d{1,2}[A-Za-zА-Яа-яЁёІіҢңҒғҚқӨөҰұҮүҺһ]$'
        THEN upper(regexp_replace(compact_grade, '^[0-9]{1,2}', ''))
      WHEN parallel_up <> '' THEN parallel_up
      ELSE ''
    END AS letter
  FROM normalized
)
UPDATE grades g
SET
  grade = (p.grade_num || p.letter),
  parallel = CASE WHEN p.letter = '' THEN g.parallel ELSE p.letter END
FROM parsed p
WHERE g.id = p.id;

WITH normalized AS (
  SELECT
    id,
    regexp_replace(trim(grade), '\\s+', '', 'g') AS compact_grade,
    COALESCE(NULLIF(upper(trim(parallel)), ''), '') AS parallel_up
  FROM grades
),
parsed AS (
  SELECT
    id,
    CASE
      WHEN compact_grade ~ '^\\d{1,2}[A-Za-zА-Яа-яЁёІіҢңҒғҚқӨөҰұҮүҺһ]$'
        THEN regexp_replace(compact_grade, '^([0-9]{1,2}).*$', '\\1')
      WHEN compact_grade ~ '^\\d{1,2}$'
        THEN compact_grade
      ELSE regexp_replace(compact_grade, '^([0-9]{1,2}).*$', '\\1')
    END AS grade_num,
    CASE
      WHEN compact_grade ~ '^\\d{1,2}[A-Za-zА-Яа-яЁёІіҢңҒғҚқӨөҰұҮүҺһ]$'
        THEN upper(regexp_replace(compact_grade, '^[0-9]{1,2}', ''))
      WHEN parallel_up <> '' THEN parallel_up
      ELSE ''
    END AS letter
  FROM normalized
),
keys AS (
  SELECT id, (grade_num || letter) AS key_label
  FROM parsed
),
canonical AS (
  SELECT key_label, MIN(id) AS keep_id
  FROM keys
  GROUP BY key_label
),
to_delete AS (
  SELECT k.id
  FROM keys k
  JOIN canonical c ON c.key_label = k.key_label
  WHERE k.id <> c.keep_id
)
DELETE FROM grades
WHERE id IN (SELECT id FROM to_delete);
"""

with engine.begin() as conn:
  conn.execute(text(SQL))

print("Done: duplicate grades merged and normalized")
PY
