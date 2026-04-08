"""
Текущий учебный год из system_settings и перевод класса (7А → 8А).
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from schemas.models import GradeInDB, StudentInDB, SystemSettingsInDB


def get_current_academic_year(db: Session) -> str:
    settings = db.query(SystemSettingsInDB).filter(SystemSettingsInDB.is_active == 1).first()
    if settings and settings.academic_year:
        return str(settings.academic_year).strip()
    return "2024-2025"


def next_academic_year_label(current: str) -> str:
    """«2024-2025» → «2025-2026»"""
    s = (current or "").strip()
    m = re.match(r"^(\d{4})-(\d{4})$", s)
    if not m:
        raise ValueError(f"Неверный формат учебного года: {current!r}, ожидается «YYYY-YYYY»")
    y1, y2 = int(m.group(1)), int(m.group(2))
    return f"{y1 + 1}-{y2 + 1}"


def _normalize_grade_key(grade_text: str, parallel_text: Optional[str]) -> Tuple[str, str, str]:
    """Согласовано с routes.grades._normalize_grade_key"""
    grade_raw = str(grade_text or "").strip()
    parallel_raw = str(parallel_text or "").strip().upper()

    compact_grade = re.sub(r"\s+", "", grade_raw)
    match = re.match(
        r"^(\d{1,2})([A-Za-zА-Яа-яЁёІіҢңҒғҚқӨөҰұҮүҺһ]?)$",
        compact_grade,
    )
    if match:
        num = match.group(1)
        letter = (match.group(2) or parallel_raw).upper()
        canonical = f"{num}{letter}" if letter else num
        return canonical, num, letter

    num_match = re.match(r"^(\d{1,2})", grade_raw)
    if num_match:
        num = num_match.group(1)
        letter = parallel_raw
        canonical = f"{num}{letter}" if letter else num
        return canonical, num, letter

    fallback = f"{grade_raw} {parallel_raw}".strip()
    return fallback, grade_raw, parallel_raw


def find_next_parallel_grade(db: Session, grade: GradeInDB) -> Optional[GradeInDB]:
    """
    Следующий параллельный класс с той же литерой (9А → 10А).
    Для 12 класса возвращает None (выпуск).
    """
    _, num_str, letter = _normalize_grade_key(grade.grade, grade.parallel)
    try:
        n = int(num_str)
    except (TypeError, ValueError):
        return None
    if n >= 12:
        return None
    next_n = n + 1
    letter_u = (letter or "").upper()
    for cg in db.query(GradeInDB).all():
        _, ns, le = _normalize_grade_key(cg.grade, cg.parallel)
        if ns == str(next_n) and (le or "").upper() == letter_u:
            return cg
    return None


def promote_all_students_to_next_grade(
    db: Session,
    *,
    dry_run: bool
) -> dict:
    """
    Для каждого активного ученика: grade_id → следующий класс (та же литера).
    Выпускники (12 класс) не меняют класс (остаются на записи; при необходимости отключите вручную).
    """
    promoted = 0
    graduated = 0
    missing_target: list[dict] = []

    students = db.query(StudentInDB).filter(StudentInDB.is_active == 1).all()
    for st in students:
        grade = db.query(GradeInDB).filter(GradeInDB.id == st.grade_id).first()
        if not grade:
            missing_target.append({"student_id": st.id, "reason": "grade_not_found"})
            continue
        _, num_str, _ = _normalize_grade_key(grade.grade, grade.parallel)
        try:
            n = int(num_str)
        except (TypeError, ValueError):
            missing_target.append({"student_id": st.id, "reason": "bad_grade_format"})
            continue
        if n >= 12:
            graduated += 1
            continue
        nxt = find_next_parallel_grade(db, grade)
        if not nxt:
            missing_target.append(
                {
                    "student_id": st.id,
                    "reason": "no_next_class_row",
                    "from_grade_id": grade.id,
                    "hint": f"Создайте класс {n + 1} с той же литерой или проверьте названия классов",
                }
            )
            continue
        if not dry_run:
            st.grade_id = nxt.id
        promoted += 1

    return {
        "promoted": promoted,
        "graduated_unchanged": graduated,
        "issues": missing_target,
    }
