from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from config import get_db
from schemas.models import *
from auth_utils import verify_access_token
from routes.auth import oauth2_scheme
from typing import List, Optional

router = APIRouter()


def _grade_allows_subject_groups(grade: GradeInDB) -> bool:
    try:
        num = int(grade.grade) if (grade.grade and str(grade.grade).isdigit()) else None
        return num in (11, 12)
    except (ValueError, TypeError):
        return False


@router.get("/", response_model=List[SubjectGroupResponse])
async def get_subject_groups(
    grade_id: Optional[int] = Query(None),
    subject_id: Optional[int] = Query(None),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get subject groups (for grades 11-12 only). Filter by grade_id and/or subject_id."""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    query = db.query(SubjectGroupInDB).filter(SubjectGroupInDB.is_active == 1)

    if grade_id:
        query = query.filter(SubjectGroupInDB.grade_id == grade_id)
    if subject_id:
        query = query.filter(SubjectGroupInDB.subject_id == subject_id)

    groups = query.all()
    result = []
    for g in groups:
        grade = db.query(GradeInDB).filter(GradeInDB.id == g.grade_id).first()
        subject = db.query(SubjectInDB).filter(SubjectInDB.id == g.subject_id).first()
        result.append({
            "id": g.id,
            "grade_id": g.grade_id,
            "subject_id": g.subject_id,
            "name": g.name,
            "is_active": g.is_active,
            "created_at": g.created_at,
            "updated_at": g.updated_at,
            "grade_name": f"{grade.grade}{grade.parallel}" if grade else None,
            "subject_name": subject.name if subject else None
        })
    return result


@router.get("/by-grade/{grade_id}", response_model=List[SubjectGroupResponse])
async def get_subject_groups_by_grade(
    grade_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get subject groups for a specific grade (11-12 only)."""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    grade = db.query(GradeInDB).filter(GradeInDB.id == grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")

    if not _grade_allows_subject_groups(grade):
        return []

    groups = db.query(SubjectGroupInDB).filter(
        SubjectGroupInDB.grade_id == grade_id,
        SubjectGroupInDB.is_active == 1
    ).all()

    result = []
    for g in groups:
        subject = db.query(SubjectInDB).filter(SubjectInDB.id == g.subject_id).first()
        result.append({
            "id": g.id,
            "grade_id": g.grade_id,
            "subject_id": g.subject_id,
            "name": g.name,
            "is_active": g.is_active,
            "created_at": g.created_at,
            "updated_at": g.updated_at,
            "grade_name": f"{grade.grade}{grade.parallel}",
            "subject_name": subject.name if subject else None
        })
    return result


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_subject_group(
    data: CreateSubjectGroup,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Create a subject group (grades 11-12 only)."""
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

    existing = db.query(SubjectGroupInDB).filter(
        SubjectGroupInDB.grade_id == data.grade_id,
        SubjectGroupInDB.subject_id == data.subject_id,
        SubjectGroupInDB.name == data.name.strip(),
        SubjectGroupInDB.is_active == 1
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Subject group with this name already exists")

    db_group = SubjectGroupInDB(
        grade_id=data.grade_id,
        subject_id=data.subject_id,
        name=data.name.strip(),
        is_active=1
    )
    db.add(db_group)
    db.commit()
    db.refresh(db_group)
    return {"id": db_group.id, "message": "Subject group created successfully"}


@router.put("/{group_id}", status_code=status.HTTP_200_OK)
async def update_subject_group(
    group_id: int,
    update_data: UpdateSubjectGroup,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Update a subject group."""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can update subject groups")

    group = db.query(SubjectGroupInDB).filter(SubjectGroupInDB.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Subject group not found")

    update_dict = update_data.dict(exclude_unset=True)
    if "name" in update_dict:
        existing = db.query(SubjectGroupInDB).filter(
            SubjectGroupInDB.grade_id == group.grade_id,
            SubjectGroupInDB.subject_id == group.subject_id,
            SubjectGroupInDB.name == update_dict["name"],
            SubjectGroupInDB.id != group_id,
            SubjectGroupInDB.is_active == 1
        ).first()
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
    db: Session = Depends(get_db)
):
    """Soft-delete a subject group."""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete subject groups")

    group = db.query(SubjectGroupInDB).filter(SubjectGroupInDB.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Subject group not found")

    group.is_active = 0
    db.commit()
    return {"message": "Subject group deleted successfully"}
