from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from config import get_db
from schemas.models import *
from auth_utils import verify_access_token
from routes.auth import oauth2_scheme
from typing import List, Optional

router = APIRouter()

@router.get("/", response_model=List[TeacherAssignmentResponse])
async def get_teacher_assignments(
    grade_id: Optional[int] = Query(None),
    subject_id: Optional[int] = Query(None),
    teacher_id: Optional[int] = Query(None),
    subgroup_id: Optional[int] = Query(None),
    subject_group_id: Optional[int] = Query(None),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get teacher assignments with optional filters"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    query = db.query(TeacherAssignmentInDB).filter(TeacherAssignmentInDB.is_active == 1)

    if grade_id:
        query = query.filter(TeacherAssignmentInDB.grade_id == grade_id)
    if subject_id:
        query = query.filter(TeacherAssignmentInDB.subject_id == subject_id)
    if teacher_id:
        query = query.filter(TeacherAssignmentInDB.teacher_id == teacher_id)
    if subgroup_id:
        query = query.filter(TeacherAssignmentInDB.subgroup_id == subgroup_id)
    if subject_group_id:
        query = query.filter(TeacherAssignmentInDB.subject_group_id == subject_group_id)

    assignments = query.all()

    result = []
    for assignment in assignments:
        teacher = db.query(UserInDB).filter(UserInDB.id == assignment.teacher_id).first()
        subject = db.query(SubjectInDB).filter(SubjectInDB.id == assignment.subject_id).first()
        grade = db.query(GradeInDB).filter(GradeInDB.id == assignment.grade_id).first() if assignment.grade_id else None
        subgroup = db.query(SubgroupInDB).filter(SubgroupInDB.id == assignment.subgroup_id).first() if assignment.subgroup_id else None
        subject_group = db.query(SubjectGroupInDB).filter(SubjectGroupInDB.id == assignment.subject_group_id).first() if assignment.subject_group_id else None

        assignment_data = {
            "id": assignment.id,
            "teacher_id": assignment.teacher_id,
            "subject_id": assignment.subject_id,
            "grade_id": assignment.grade_id,
            "subgroup_id": assignment.subgroup_id,
            "subject_group_id": assignment.subject_group_id,
            "is_active": assignment.is_active,
            "created_at": assignment.created_at,
            "updated_at": assignment.updated_at,
            "teacher_name": teacher.name if teacher else None,
            "subject_name": subject.name if subject else None,
            "grade_name": f"{grade.grade}{grade.parallel}" if grade else None,
            "subgroup_name": subgroup.name if subgroup else None,
            "subject_group_name": subject_group.name if subject_group else None
        }
        result.append(assignment_data)

    return result

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_teacher_assignment(
    assignment: CreateTeacherAssignment,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Create a new teacher assignment"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create teacher assignments")
    
    # Validate teacher exists and is a teacher
    teacher = db.query(UserInDB).filter(
        UserInDB.id == assignment.teacher_id,
        UserInDB.is_active == 1
    ).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    
    if teacher.type not in ['teacher', 'admin']:
        raise HTTPException(status_code=400, detail="User is not a teacher")
    
    # Validate subject exists
    subject = db.query(SubjectInDB).filter(
        SubjectInDB.id == assignment.subject_id,
        SubjectInDB.is_active == 1
    ).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    # Validate grade if provided
    if assignment.grade_id:
        grade = db.query(GradeInDB).filter(GradeInDB.id == assignment.grade_id).first()
        if not grade:
            raise HTTPException(status_code=404, detail="Grade not found")
    
    # Validate subgroup if provided
    if assignment.subgroup_id:
        subgroup = db.query(SubgroupInDB).filter(
            SubgroupInDB.id == assignment.subgroup_id,
            SubgroupInDB.is_active == 1
        ).first()
        if not subgroup:
            raise HTTPException(status_code=404, detail="Subgroup not found")

        if assignment.grade_id and subgroup.grade_id != assignment.grade_id:
            raise HTTPException(status_code=400, detail="Subgroup does not belong to the specified grade")

        if not assignment.grade_id:
            assignment.grade_id = subgroup.grade_id

    # Validate subject_group if provided (only for grades 11-12)
    if assignment.subject_group_id:
        sg = db.query(SubjectGroupInDB).filter(
            SubjectGroupInDB.id == assignment.subject_group_id,
            SubjectGroupInDB.is_active == 1
        ).first()
        if not sg:
            raise HTTPException(status_code=404, detail="Subject group not found")
        grade = db.query(GradeInDB).filter(GradeInDB.id == sg.grade_id).first()
        if grade:
            try:
                grade_num = int(grade.grade) if (grade.grade and str(grade.grade).isdigit()) else None
                if grade_num not in (11, 12):
                    raise HTTPException(status_code=400, detail="Subject groups are only allowed for grades 11-12")
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail="Subject groups are only allowed for grades 11-12")
        if assignment.grade_id and sg.grade_id != assignment.grade_id:
            raise HTTPException(status_code=400, detail="Subject group does not belong to the specified grade")
        if sg.subject_id != assignment.subject_id:
            raise HTTPException(status_code=400, detail="Subject group does not match the assignment subject")
        if not assignment.grade_id:
            assignment.grade_id = sg.grade_id

    grade_match = TeacherAssignmentInDB.grade_id == assignment.grade_id if assignment.grade_id else TeacherAssignmentInDB.grade_id.is_(None)
    subgroup_match = TeacherAssignmentInDB.subgroup_id == assignment.subgroup_id if assignment.subgroup_id else TeacherAssignmentInDB.subgroup_id.is_(None)
    sg_match = TeacherAssignmentInDB.subject_group_id == assignment.subject_group_id if assignment.subject_group_id else TeacherAssignmentInDB.subject_group_id.is_(None)

    existing_assignment = db.query(TeacherAssignmentInDB).filter(
        and_(
            TeacherAssignmentInDB.teacher_id == assignment.teacher_id,
            TeacherAssignmentInDB.subject_id == assignment.subject_id,
            grade_match,
            subgroup_match,
            sg_match,
            TeacherAssignmentInDB.is_active == 1
        )
    ).first()

    if existing_assignment:
        raise HTTPException(status_code=400, detail="This teacher assignment already exists")

    db_assignment = TeacherAssignmentInDB(
        teacher_id=assignment.teacher_id,
        subject_id=assignment.subject_id,
        grade_id=assignment.grade_id,
        subgroup_id=assignment.subgroup_id,
        subject_group_id=assignment.subject_group_id
    )
    
    db.add(db_assignment)
    db.commit()
    db.refresh(db_assignment)
    
    return {"id": db_assignment.id, "message": "Teacher assignment created successfully"}

@router.put("/{assignment_id}", status_code=status.HTTP_200_OK)
async def update_teacher_assignment(
    assignment_id: int,
    update_data: UpdateTeacherAssignment,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Update a teacher assignment by ID"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can update teacher assignments")
    
    assignment = db.query(TeacherAssignmentInDB).filter(
        TeacherAssignmentInDB.id == assignment_id
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Teacher assignment not found")
    
    # Update only the fields that are provided
    update_dict = update_data.dict(exclude_unset=True)
    
    for key, value in update_dict.items():
        if hasattr(assignment, key):
            setattr(assignment, key, value)
    
    db.commit()
    db.refresh(assignment)
    
    return {"message": "Teacher assignment updated successfully"}

@router.delete("/{assignment_id}", status_code=status.HTTP_200_OK)
async def delete_teacher_assignment(
    assignment_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Delete a teacher assignment by ID (soft delete)"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete teacher assignments")
    
    assignment = db.query(TeacherAssignmentInDB).filter(
        TeacherAssignmentInDB.id == assignment_id
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Teacher assignment not found")
    
    # Soft delete by setting is_active to 0
    assignment.is_active = 0
    db.commit()
    
    return {"message": "Teacher assignment deleted successfully"}

@router.get("/teachers", response_model=List[dict])
async def get_available_teachers(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get list of users who can be assigned as teachers"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    teachers = db.query(UserInDB).filter(
        UserInDB.type.in_(['teacher', 'admin']),
        UserInDB.is_active == 1
    ).all()
    
    result = []
    for teacher in teachers:
        result.append({
            "id": teacher.id,
            "name": teacher.name,
            "email": teacher.email,
            "type": teacher.type
        })
    
    return result

@router.get("/by-grade/{grade_id}", response_model=List[TeacherAssignmentResponse])
async def get_assignments_by_grade(
    grade_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get all teacher assignments for a specific grade"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Verify grade exists
    grade = db.query(GradeInDB).filter(GradeInDB.id == grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    
    assignments = db.query(TeacherAssignmentInDB).filter(
        TeacherAssignmentInDB.grade_id == grade_id,
        TeacherAssignmentInDB.is_active == 1
    ).all()
    
    result = []
    for assignment in assignments:
        teacher = db.query(UserInDB).filter(UserInDB.id == assignment.teacher_id).first()
        subject = db.query(SubjectInDB).filter(SubjectInDB.id == assignment.subject_id).first()
        subgroup = db.query(SubgroupInDB).filter(SubgroupInDB.id == assignment.subgroup_id).first() if assignment.subgroup_id else None
        subject_group = db.query(SubjectGroupInDB).filter(SubjectGroupInDB.id == assignment.subject_group_id).first() if assignment.subject_group_id else None

        assignment_data = {
            "id": assignment.id,
            "teacher_id": assignment.teacher_id,
            "subject_id": assignment.subject_id,
            "grade_id": assignment.grade_id,
            "subgroup_id": assignment.subgroup_id,
            "subject_group_id": assignment.subject_group_id,
            "is_active": assignment.is_active,
            "created_at": assignment.created_at,
            "updated_at": assignment.updated_at,
            "teacher_name": teacher.name if teacher else None,
            "subject_name": subject.name if subject else None,
            "grade_name": f"{grade.grade}{grade.parallel}",
            "subgroup_name": subgroup.name if subgroup else None,
            "subject_group_name": subject_group.name if subject_group else None
        }
        result.append(assignment_data)

    return result



