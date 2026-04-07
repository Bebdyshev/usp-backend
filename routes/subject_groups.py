import re
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.orm import Session
from config import get_db
from schemas.models import *
from auth_utils import verify_access_token
from routes.auth import oauth2_scheme
from typing import List, Optional

router = APIRouter()


def parallel_int_from_grade_row(grade: Optional[GradeInDB]) -> Optional[int]:
    if not grade or grade.grade is None:
        return None
    m = re.match(r"^(\d+)", str(grade.grade).strip())
    return int(m.group(1)) if m else None


def _grade_allows_subject_groups(grade: GradeInDB) -> bool:
    p = parallel_int_from_grade_row(grade)
    return p in (11, 12)


def _canonical_grade_name(grade: GradeInDB) -> str:
    from routes.grades import _normalize_grade_key
    canonical, _, _ = _normalize_grade_key(grade.grade, grade.parallel)
    return canonical


def _serialize_subject_group(db: Session, g: SubjectGroupInDB) -> dict:
    grade = db.query(GradeInDB).filter(GradeInDB.id == g.grade_id).first()
    subject = db.query(SubjectInDB).filter(SubjectInDB.id == g.subject_id).first()
    grade_name = _canonical_grade_name(grade) if grade else None
    return {
        "id": g.id,
        "grade_id": g.grade_id,
        "subject_id": g.subject_id,
        "name": g.name,
        "is_active": g.is_active,
        "created_at": g.created_at,
        "updated_at": g.updated_at,
        "grade_name": grade_name,
        "subject_name": subject.name if subject else None,
        "owner_teacher_id": g.owner_teacher_id,
    }


def _get_user_from_token(db: Session, user_data: dict) -> Optional[UserInDB]:
    user = db.query(UserInDB).filter(UserInDB.email == user_data.get("sub")).first()
    if user:
        return user
    uid = user_data.get("id")
    if uid:
        return db.query(UserInDB).filter(UserInDB.id == uid).first()
    return None


def _teacher_may_manage_subject_parallel(
    db: Session, teacher_id: int, subject_id: int, anchor: GradeInDB
) -> bool:
    anchor_p = parallel_int_from_grade_row(anchor)
    if anchor_p not in (11, 12):
        return False
    assignments = (
        db.query(TeacherAssignmentInDB)
        .filter(
            TeacherAssignmentInDB.teacher_id == teacher_id,
            TeacherAssignmentInDB.subject_id == subject_id,
            TeacherAssignmentInDB.is_active == 1,
        )
        .all()
    )
    if not assignments:
        return False
    for a in assignments:
        if a.grade_id is None:
            return True
        g = db.query(GradeInDB).filter(GradeInDB.id == a.grade_id).first()
        if g and parallel_int_from_grade_row(g) == anchor_p:
            return True
    return False


def _ensure_teacher_assignment_for_subject_group(
    db: Session, teacher_id: int, subject_id: int, anchor_grade_id: int, subject_group_id: int
) -> None:
    existing = (
        db.query(TeacherAssignmentInDB)
        .filter(
            TeacherAssignmentInDB.teacher_id == teacher_id,
            TeacherAssignmentInDB.subject_id == subject_id,
            TeacherAssignmentInDB.subject_group_id == subject_group_id,
            TeacherAssignmentInDB.is_active == 1,
        )
        .first()
    )
    if existing:
        return
    row = TeacherAssignmentInDB(
        teacher_id=teacher_id,
        subject_id=subject_id,
        grade_id=anchor_grade_id,
        subgroup_id=None,
        subject_group_id=subject_group_id,
        is_active=1,
    )
    db.add(row)
    db.commit()


def _group_anchor_parallel(db: Session, group: SubjectGroupInDB) -> Optional[int]:
    g = db.query(GradeInDB).filter(GradeInDB.id == group.grade_id).first()
    return parallel_int_from_grade_row(g)


def _student_parallel(db: Session, student_id: int) -> Optional[int]:
    st = db.query(StudentInDB).filter(StudentInDB.id == student_id).first()
    if not st:
        return None
    g = db.query(GradeInDB).filter(GradeInDB.id == st.grade_id).first()
    return parallel_int_from_grade_row(g)


def _can_teacher_manage_group(db: Session, user: UserInDB, group: SubjectGroupInDB) -> bool:
    if group.owner_teacher_id is None:
        return False
    return group.owner_teacher_id == user.id


@router.get("/", response_model=List[SubjectGroupResponse])
async def get_subject_groups(
    grade_id: Optional[int] = Query(None),
    subject_id: Optional[int] = Query(None),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    query = db.query(SubjectGroupInDB).filter(SubjectGroupInDB.is_active == 1)

    if grade_id:
        query = query.filter(SubjectGroupInDB.grade_id == grade_id)
    if subject_id:
        query = query.filter(SubjectGroupInDB.subject_id == subject_id)

    groups = query.all()
    return [_serialize_subject_group(db, g) for g in groups]


@router.get("/my", response_model=List[SubjectGroupResponse])
async def get_my_subject_groups(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if user_data.get("type") == "admin":
        groups = (
            db.query(SubjectGroupInDB)
            .filter(SubjectGroupInDB.is_active == 1)
            .order_by(SubjectGroupInDB.updated_at.desc())
            .all()
        )
        return [_serialize_subject_group(db, g) for g in groups]

    if user_data.get("type") != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can list their subject groups")

    user = _get_user_from_token(db, user_data)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    groups = (
        db.query(SubjectGroupInDB)
        .filter(
            SubjectGroupInDB.owner_teacher_id == user.id,
            SubjectGroupInDB.is_active == 1,
        )
        .order_by(SubjectGroupInDB.updated_at.desc())
        .all()
    )
    return [_serialize_subject_group(db, g) for g in groups]


@router.get("/by-grade/{grade_id}", response_model=List[SubjectGroupResponse])
async def get_subject_groups_by_grade(
    grade_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    grade = db.query(GradeInDB).filter(GradeInDB.id == grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")

    if not _grade_allows_subject_groups(grade):
        return []

    groups = (
        db.query(SubjectGroupInDB)
        .filter(
            SubjectGroupInDB.grade_id == grade_id,
            SubjectGroupInDB.is_active == 1,
        )
        .all()
    )
    return [_serialize_subject_group(db, g) for g in groups]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_subject_group(
    data: CreateSubjectGroup,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create subject groups")

    grade = db.query(GradeInDB).filter(GradeInDB.id == data.grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    if not _grade_allows_subject_groups(grade):
        raise HTTPException(status_code=400, detail="Subject groups are only allowed for grades 11-12")

    subject = db.query(SubjectInDB).filter(SubjectInDB.id == data.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    existing = (
        db.query(SubjectGroupInDB)
        .filter(
            SubjectGroupInDB.grade_id == data.grade_id,
            SubjectGroupInDB.subject_id == data.subject_id,
            SubjectGroupInDB.name == data.name.strip(),
            SubjectGroupInDB.is_active == 1,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Subject group with this name already exists")

    db_group = SubjectGroupInDB(
        grade_id=data.grade_id,
        subject_id=data.subject_id,
        name=data.name.strip(),
        is_active=1,
        owner_teacher_id=None,
    )
    db.add(db_group)
    db.commit()
    db.refresh(db_group)
    return {"id": db_group.id, "message": "Subject group created successfully"}


@router.post("/teacher", status_code=status.HTTP_201_CREATED)
async def create_subject_group_teacher(
    data: CreateTeacherSubjectGroup,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if user_data.get("type") not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Only teachers and admins can create groups here")

    user = _get_user_from_token(db, user_data)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    anchor = db.query(GradeInDB).filter(GradeInDB.id == data.anchor_grade_id).first()
    if not anchor:
        raise HTTPException(status_code=404, detail="Anchor grade not found")
    if not _grade_allows_subject_groups(anchor):
        raise HTTPException(status_code=400, detail="Subject groups are only allowed for grades 11-12")

    # Admins skip the assignment check
    if user_data.get("type") != "admin":
        if not _teacher_may_manage_subject_parallel(db, user.id, data.subject_id, anchor):
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to teach this subject for this parallel",
            )

    subject = db.query(SubjectInDB).filter(SubjectInDB.id == data.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    name_clean = data.name.strip()
    existing = (
        db.query(SubjectGroupInDB)
        .filter(
            SubjectGroupInDB.grade_id == data.anchor_grade_id,
            SubjectGroupInDB.subject_id == data.subject_id,
            SubjectGroupInDB.name == name_clean,
            SubjectGroupInDB.is_active == 1,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Subject group with this name already exists for this class")

    db_group = SubjectGroupInDB(
        grade_id=data.anchor_grade_id,
        subject_id=data.subject_id,
        name=name_clean,
        is_active=1,
        owner_teacher_id=user.id,
    )
    db.add(db_group)
    db.commit()
    db.refresh(db_group)

    _ensure_teacher_assignment_for_subject_group(
        db, user.id, data.subject_id, data.anchor_grade_id, db_group.id
    )

    return {"id": db_group.id, "message": "Subject group created successfully"}


@router.put("/{group_id}", status_code=status.HTTP_200_OK)
async def update_subject_group(
    group_id: int,
    update_data: UpdateSubjectGroup,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    group = db.query(SubjectGroupInDB).filter(SubjectGroupInDB.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Subject group not found")

    user = _get_user_from_token(db, user_data)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user_data.get("type") == "teacher":
        if not _can_teacher_manage_group(db, user, group):
            raise HTTPException(status_code=403, detail="You can only update your own subject groups")
    elif user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")

    update_dict = update_data.dict(exclude_unset=True)
    if "name" in update_dict:
        existing = (
            db.query(SubjectGroupInDB)
            .filter(
                SubjectGroupInDB.grade_id == group.grade_id,
                SubjectGroupInDB.subject_id == group.subject_id,
                SubjectGroupInDB.name == update_dict["name"],
                SubjectGroupInDB.id != group_id,
                SubjectGroupInDB.is_active == 1,
            )
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail="Subject group with this name already exists")

    for key, value in update_dict.items():
        if hasattr(group, key):
            setattr(group, key, value)
    db.commit()
    db.refresh(group)
    return {"message": "Subject group updated successfully"}


@router.delete("/{group_id}", status_code=status.HTTP_200_OK)
async def delete_subject_group(
    group_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    group = db.query(SubjectGroupInDB).filter(SubjectGroupInDB.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Subject group not found")

    user = _get_user_from_token(db, user_data)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user_data.get("type") == "teacher":
        if not _can_teacher_manage_group(db, user, group):
            raise HTTPException(status_code=403, detail="You can only delete your own subject groups")
    elif user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")

    group.is_active = 0
    db.commit()
    return {"message": "Subject group deleted successfully"}


def _require_group_manage_members(db: Session, user_data: dict, user: UserInDB, group: SubjectGroupInDB) -> None:
    if user_data.get("type") == "admin":
        return
    if user_data.get("type") == "teacher" and _can_teacher_manage_group(db, user, group):
        return
    raise HTTPException(status_code=403, detail="Not allowed to manage members of this group")


@router.get("/{group_id}/members", response_model=List[SubjectGroupMemberResponse])
async def get_subject_group_members(
    group_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    group = db.query(SubjectGroupInDB).filter(SubjectGroupInDB.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Subject group not found")

    user = _get_user_from_token(db, user_data)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    _require_group_manage_members(db, user_data, user, group)

    rows = (
        db.query(StudentSubjectGroupMembershipInDB)
        .filter(
            StudentSubjectGroupMembershipInDB.subject_group_id == group_id,
            StudentSubjectGroupMembershipInDB.is_active == 1,
        )
        .all()
    )
    out: List[dict] = []
    for m in rows:
        st = db.query(StudentInDB).filter(StudentInDB.id == m.student_id).first()
        g = db.query(GradeInDB).filter(GradeInDB.id == st.grade_id).first() if st else None
        out.append(
            {
                "id": m.id,
                "student_id": m.student_id,
                "name": st.name if st else None,
                "grade_id": st.grade_id if st else None,
                "grade_name": _canonical_grade_name(g) if g else None,
                "is_active": m.is_active,
            }
        )
    return out


@router.post("/{group_id}/members", status_code=status.HTTP_200_OK)
async def add_subject_group_members(
    group_id: int,
    body: SubjectGroupMembersBulk,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    group = db.query(SubjectGroupInDB).filter(SubjectGroupInDB.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Subject group not found")
    if group.is_active != 1:
        raise HTTPException(status_code=400, detail="Subject group is inactive")

    user = _get_user_from_token(db, user_data)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    _require_group_manage_members(db, user_data, user, group)

    anchor_p = _group_anchor_parallel(db, group)
    if anchor_p is None:
        raise HTTPException(status_code=400, detail="Cannot determine group parallel")

    added = 0
    errors: List[str] = []
    for sid in body.student_ids:
        st = db.query(StudentInDB).filter(StudentInDB.id == sid).first()
        if not st:
            errors.append(f"Student {sid} not found")
            continue
        sp = _student_parallel(db, sid)
        if sp != anchor_p:
            errors.append(f"Student {sid} is not in parallel {anchor_p}")
            continue
        existing = (
            db.query(StudentSubjectGroupMembershipInDB)
            .filter(
                StudentSubjectGroupMembershipInDB.student_id == sid,
                StudentSubjectGroupMembershipInDB.subject_group_id == group_id,
            )
            .first()
        )
        if existing:
            if existing.is_active != 1:
                existing.is_active = 1
                added += 1
            continue
        db.add(
            StudentSubjectGroupMembershipInDB(
                student_id=sid,
                subject_group_id=group_id,
                is_active=1,
            )
        )
        added += 1

    db.commit()
    return {"message": "Members updated", "added_or_reactivated": added, "errors": errors}


@router.delete("/{group_id}/members/{student_id}", status_code=status.HTTP_200_OK)
async def remove_subject_group_member(
    group_id: int,
    student_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    group = db.query(SubjectGroupInDB).filter(SubjectGroupInDB.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Subject group not found")

    user = _get_user_from_token(db, user_data)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    _require_group_manage_members(db, user_data, user, group)

    row = (
        db.query(StudentSubjectGroupMembershipInDB)
        .filter(
            StudentSubjectGroupMembershipInDB.subject_group_id == group_id,
            StudentSubjectGroupMembershipInDB.student_id == student_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Membership not found")

    row.is_active = 0
    db.commit()
    return {"message": "Member removed from group"}


def _grade_display_name(g: GradeInDB) -> str:
    return _canonical_grade_name(g)


@router.get("/{group_id}/parallel-students", response_model=List[SubjectGroupParallelStudentItem])
async def get_subject_group_parallel_students(
    group_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """All active students in the same numeric parallel (11 or 12) as the group anchor — for picking members across letters."""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    group = db.query(SubjectGroupInDB).filter(SubjectGroupInDB.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Subject group not found")

    user = _get_user_from_token(db, user_data)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    _require_group_manage_members(db, user_data, user, group)

    anchor_p = _group_anchor_parallel(db, group)
    if anchor_p is None:
        raise HTTPException(status_code=400, detail="Cannot determine group parallel")

    all_grades = db.query(GradeInDB).all()
    grade_ids = [g.id for g in all_grades if parallel_int_from_grade_row(g) == anchor_p]
    if not grade_ids:
        return []

    students = (
        db.query(StudentInDB)
        .filter(StudentInDB.is_active == 1, StudentInDB.grade_id.in_(grade_ids))
        .order_by(StudentInDB.name)
        .all()
    )
    out: List[dict] = []
    for st in students:
        g = db.query(GradeInDB).filter(GradeInDB.id == st.grade_id).first()
        out.append(
            {
                "id": st.id,
                "name": st.name,
                "grade_id": st.grade_id,
                "grade_name": _grade_display_name(g) if g else None,
            }
        )
    return out
