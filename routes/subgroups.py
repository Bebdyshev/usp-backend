from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from config import get_db
from schemas.models import *
from auth_utils import verify_access_token
from routes.auth import oauth2_scheme
from typing import List

router = APIRouter()

@router.get("/{grade_id}", response_model=List[SubgroupResponse])
async def get_subgroups_by_grade(
    grade_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get all subgroups for a specific grade"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Verify grade exists
    grade = db.query(GradeInDB).filter(GradeInDB.id == grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    
    subgroups = db.query(SubgroupInDB).filter(
        SubgroupInDB.grade_id == grade_id,
        SubgroupInDB.is_active == 1
    ).all()
    
    return subgroups

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_subgroup(
    subgroup: CreateSubgroup,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Create a new subgroup"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create subgroups")
    
    # Verify grade exists
    grade = db.query(GradeInDB).filter(GradeInDB.id == subgroup.grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    
    # Check if subgroup with this name already exists in this grade
    existing_subgroup = db.query(SubgroupInDB).filter(
        SubgroupInDB.name == subgroup.name,
        SubgroupInDB.grade_id == subgroup.grade_id,
        SubgroupInDB.is_active == 1
    ).first()
    
    if existing_subgroup:
        raise HTTPException(
            status_code=400, 
            detail="Subgroup with this name already exists in this grade"
        )
    
    db_subgroup = SubgroupInDB(
        name=subgroup.name,
        grade_id=subgroup.grade_id
    )
    
    db.add(db_subgroup)
    db.commit()
    db.refresh(db_subgroup)
    
    return {"id": db_subgroup.id, "message": "Subgroup created successfully"}

@router.put("/{subgroup_id}", status_code=status.HTTP_200_OK)
async def update_subgroup(
    subgroup_id: int,
    update_data: UpdateSubgroup,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Update a subgroup by ID"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can update subgroups")
    
    subgroup = db.query(SubgroupInDB).filter(SubgroupInDB.id == subgroup_id).first()
    if not subgroup:
        raise HTTPException(status_code=404, detail="Subgroup not found")
    
    # Update only the fields that are provided
    update_dict = update_data.dict(exclude_unset=True)
    
    # Check if name is being updated and if it already exists
    if "name" in update_dict:
        existing_subgroup = db.query(SubgroupInDB).filter(
            SubgroupInDB.name == update_dict["name"],
            SubgroupInDB.grade_id == subgroup.grade_id,
            SubgroupInDB.id != subgroup_id,
            SubgroupInDB.is_active == 1
        ).first()
        if existing_subgroup:
            raise HTTPException(
                status_code=400, 
                detail="Subgroup with this name already exists in this grade"
            )
    
    for key, value in update_dict.items():
        if hasattr(subgroup, key):
            setattr(subgroup, key, value)
    
    db.commit()
    db.refresh(subgroup)
    
    return {"message": "Subgroup updated successfully"}

@router.delete("/{subgroup_id}", status_code=status.HTTP_200_OK)
async def delete_subgroup(
    subgroup_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Delete a subgroup by ID (soft delete)"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete subgroups")
    
    subgroup = db.query(SubgroupInDB).filter(SubgroupInDB.id == subgroup_id).first()
    if not subgroup:
        raise HTTPException(status_code=404, detail="Subgroup not found")
    
    # Check if subgroup has students assigned
    students_count = db.query(StudentInDB).filter(
        StudentInDB.subgroup_id == subgroup_id,
        StudentInDB.is_active == 1
    ).count()
    
    if students_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete subgroup with {students_count} assigned students. "
                   "Please reassign students first."
        )
    
    # Soft delete by setting is_active to 0
    subgroup.is_active = 0
    db.commit()
    
    return {"message": "Subgroup deleted successfully"}

@router.get("/{subgroup_id}/students", response_model=List[dict])
async def get_subgroup_students(
    subgroup_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get all students in a specific subgroup"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    subgroup = db.query(SubgroupInDB).filter(SubgroupInDB.id == subgroup_id).first()
    if not subgroup:
        raise HTTPException(status_code=404, detail="Subgroup not found")
    
    students = db.query(StudentInDB).filter(
        StudentInDB.subgroup_id == subgroup_id,
        StudentInDB.is_active == 1
    ).all()
    
    result = []
    for student in students:
        result.append({
            "id": student.id,
            "name": student.name,
            "email": student.email,
            "grade_id": student.grade_id,
            "subgroup_id": student.subgroup_id
        })
    
    return result



