"""
Role-based access control utilities.
Helper functions to determine which grades/subjects a user can access based on their role.
"""

from sqlalchemy.orm import Session
from schemas.models import UserInDB, GradeInDB, CuratorGradeInDB, TeacherAssignmentInDB
from typing import List, Optional, Set


def get_user_from_token(user_data: dict, db: Session) -> Optional[UserInDB]:
    """Get the user object from token data."""
    user_email = user_data.get("sub")
    if not user_email:
        return None
    return db.query(UserInDB).filter(UserInDB.email == user_email).first()


def get_user_allowed_grade_ids(user_data: dict, db: Session) -> Optional[Set[int]]:
    """
    Get the set of grade IDs that a user is allowed to access.
    
    Returns:
        - None if user is admin (meaning access to ALL grades)
        - Set of grade IDs for curator/teacher
        - Empty set if no assignments found
    """
    user_type = user_data.get("type")
    
    # Admins can access everything
    if user_type == "admin":
        return None
    
    user = get_user_from_token(user_data, db)
    if not user:
        return set()
    
    allowed_grades: Set[int] = set()
    
    if user_type == "curator":
        # Get grades assigned to this curator via CuratorGradeInDB
        curator_assignments = db.query(CuratorGradeInDB).filter(
            CuratorGradeInDB.curator_id == user.id
        ).all()
        for assignment in curator_assignments:
            allowed_grades.add(assignment.grade_id)
        
        # Also check GradeInDB.curator_id (legacy assignment)
        legacy_grades = db.query(GradeInDB).filter(
            GradeInDB.curator_id == user.id
        ).all()
        for grade in legacy_grades:
            allowed_grades.add(grade.id)
    
    elif user_type == "teacher":
        # Get grades assigned to this teacher via TeacherAssignmentInDB
        teacher_assignments = db.query(TeacherAssignmentInDB).filter(
            TeacherAssignmentInDB.teacher_id == user.id,
            TeacherAssignmentInDB.is_active == 1
        ).all()
        for assignment in teacher_assignments:
            if assignment.grade_id:
                allowed_grades.add(assignment.grade_id)
    
    return allowed_grades


def get_user_allowed_subject_ids(user_data: dict, db: Session) -> Optional[Set[int]]:
    """
    Get the set of subject IDs that a user is allowed to access.
    
    Returns:
        - None if user is admin or curator (they see all subjects in their grades)
        - Set of subject IDs for teacher
        - Empty set if no assignments found
    """
    user_type = user_data.get("type")
    
    # Admins and curators can see all subjects within their allowed grades
    if user_type in ("admin", "curator"):
        return None
    
    user = get_user_from_token(user_data, db)
    if not user:
        return set()
    
    allowed_subjects: Set[int] = set()
    
    if user_type == "teacher":
        teacher_assignments = db.query(TeacherAssignmentInDB).filter(
            TeacherAssignmentInDB.teacher_id == user.id,
            TeacherAssignmentInDB.is_active == 1
        ).all()
        for assignment in teacher_assignments:
            if assignment.subject_id:
                allowed_subjects.add(assignment.subject_id)
    
    return allowed_subjects


def check_grade_access(user_data: dict, grade_id: int, db: Session) -> bool:
    """
    Check if a user has access to a specific grade.
    
    Returns True if access is allowed, False otherwise.
    """
    allowed_grades = get_user_allowed_grade_ids(user_data, db)
    
    # None means admin - full access
    if allowed_grades is None:
        return True
    
    return grade_id in allowed_grades


def filter_grades_by_access(user_data: dict, grades: List[GradeInDB], db: Session) -> List[GradeInDB]:
    """
    Filter a list of grades to only include those the user can access.
    """
    allowed_grades = get_user_allowed_grade_ids(user_data, db)
    
    # None means admin - return all
    if allowed_grades is None:
        return grades
    
    return [g for g in grades if g.id in allowed_grades]
