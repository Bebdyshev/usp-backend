from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from config import get_db
from schemas.models import *
from auth_utils import verify_access_token
from routes.auth import oauth2_scheme
from typing import List

router = APIRouter()

@router.get("/", response_model=List[CuratorAssignmentResponse])
async def get_curator_assignments(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get all curator assignments"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    assignments = db.query(CuratorGradeInDB).all()
    
    # Enrich with related data
    result = []
    for assignment in assignments:
        curator = db.query(UserInDB).filter(UserInDB.id == assignment.curator_id).first()
        grade = db.query(GradeInDB).filter(GradeInDB.id == assignment.grade_id).first()
        
        assignment_data = {
            "id": assignment.id,
            "curator_id": assignment.curator_id,
            "grade_id": assignment.grade_id,
            "created_at": assignment.created_at,
            "curator_name": curator.name if curator else None,
            "grade_name": f"{grade.grade} {grade.parallel}" if grade else None
        }
        result.append(assignment_data)
    
    return result

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_curator_assignment(
    assignment: CreateCuratorAssignment,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Assign a curator to a grade"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can assign curators")
    
    # Validate curator exists and is a curator or admin
    curator = db.query(UserInDB).filter(
        UserInDB.id == assignment.curator_id,
        UserInDB.is_active == 1
    ).first()
    if not curator:
        raise HTTPException(status_code=404, detail="Curator not found")
    
    if curator.type not in ['curator', 'admin']:
        raise HTTPException(status_code=400, detail="User is not a curator")
    
    # Validate grade exists
    grade = db.query(GradeInDB).filter(GradeInDB.id == assignment.grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    
    # Check if grade already has a curator
    existing_assignment = db.query(CuratorGradeInDB).filter(
        CuratorGradeInDB.grade_id == assignment.grade_id
    ).first()
    
    if existing_assignment:
        # Update existing assignment
        existing_assignment.curator_id = assignment.curator_id
        db.commit()
        db.refresh(existing_assignment)
        return {"id": existing_assignment.id, "message": "Curator assignment updated successfully"}
    else:
        # Create new assignment
        db_assignment = CuratorGradeInDB(
            curator_id=assignment.curator_id,
            grade_id=assignment.grade_id
        )
        
        db.add(db_assignment)
        db.commit()
        db.refresh(db_assignment)
        
        return {"id": db_assignment.id, "message": "Curator assignment created successfully"}

@router.delete("/{assignment_id}", status_code=status.HTTP_200_OK)
async def delete_curator_assignment(
    assignment_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Remove a curator assignment"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can remove curator assignments")
    
    assignment = db.query(CuratorGradeInDB).filter(
        CuratorGradeInDB.id == assignment_id
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Curator assignment not found")
    
    # Hard delete curator assignment
    db.delete(assignment)
    db.commit()
    
    return {"message": "Curator assignment removed successfully"}

@router.get("/available", response_model=List[dict])
async def get_available_curators(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get list of users who can be assigned as curators"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    curators = db.query(UserInDB).filter(
        UserInDB.type.in_(['curator', 'admin']),
        UserInDB.is_active == 1
    ).all()
    
    result = []
    for curator in curators:
        # Count how many grades this curator is assigned to
        assignment_count = db.query(CuratorGradeInDB).filter(
            CuratorGradeInDB.curator_id == curator.id
        ).count()
        
        result.append({
            "id": curator.id,
            "name": curator.name,
            "email": curator.email,
            "type": curator.type,
            "assigned_grades_count": assignment_count
        })
    
    return result

@router.get("/by-curator/{curator_id}", response_model=List[dict])
async def get_grades_by_curator(
    curator_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get all grades assigned to a specific curator"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Verify curator exists
    curator = db.query(UserInDB).filter(UserInDB.id == curator_id).first()
    if not curator:
        raise HTTPException(status_code=404, detail="Curator not found")
    
    assignments = db.query(CuratorGradeInDB).filter(
        CuratorGradeInDB.curator_id == curator_id
    ).all()
    
    result = []
    for assignment in assignments:
        grade = db.query(GradeInDB).filter(GradeInDB.id == assignment.grade_id).first()
        if grade:
            # Count students in this grade
            student_count = db.query(StudentInDB).filter(
                StudentInDB.grade_id == grade.id,
                StudentInDB.is_active == 1
            ).count()
            
            result.append({
                "assignment_id": assignment.id,
                "grade_id": grade.id,
                "grade_name": f"{grade.grade} {grade.parallel}",
                "curator_name": grade.curator_name,  # Legacy field
                "shanyrak": grade.shanyrak,
                "student_count": student_count,
                "assigned_date": assignment.created_at
            })
    
    return result

@router.get("/by-grade/{grade_id}", response_model=dict)
async def get_curator_by_grade(
    grade_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get curator assigned to a specific grade"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Verify grade exists
    grade = db.query(GradeInDB).filter(GradeInDB.id == grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    
    assignment = db.query(CuratorGradeInDB).filter(
        CuratorGradeInDB.grade_id == grade_id
    ).first()
    
    if not assignment:
        return {"curator": None, "grade_name": f"{grade.grade} {grade.parallel}"}
    
    curator = db.query(UserInDB).filter(UserInDB.id == assignment.curator_id).first()
    
    return {
        "assignment_id": assignment.id,
        "curator": {
            "id": curator.id,
            "name": curator.name,
            "email": curator.email,
            "type": curator.type
        } if curator else None,
        "grade_name": f"{grade.grade} {grade.parallel}",
        "assigned_date": assignment.created_at
    }



