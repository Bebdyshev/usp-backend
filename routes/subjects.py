from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from config import get_db
from schemas.models import *
from auth_utils import verify_access_token
from routes.auth import oauth2_scheme
from typing import List

router = APIRouter()

@router.get("/", response_model=List[SubjectResponse])
async def get_all_subjects(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get all subjects"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    subjects = db.query(SubjectInDB).filter(SubjectInDB.is_active == 1).all()
    return subjects

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_subject(
    subject: CreateSubject,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Create a new subject"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create subjects")
    
    # Check if subject with this name already exists
    existing_subject = db.query(SubjectInDB).filter(SubjectInDB.name == subject.name).first()
    if existing_subject:
        raise HTTPException(status_code=400, detail="Subject with this name already exists")
    
    # Validate applicable_parallels (1..12, no duplicates)
    parallels = subject.applicable_parallels or []
    if any(p < 1 or p > 12 for p in parallels):
        raise HTTPException(status_code=400, detail="applicable_parallels must contain integers from 1 to 12")
    parallels = sorted(list(set(parallels)))

    db_subject = SubjectInDB(
        name=subject.name,
        description=subject.description,
        applicable_parallels=parallels,
        is_active=1
    )
    
    db.add(db_subject)
    db.commit()
    db.refresh(db_subject)
    
    return {"id": db_subject.id, "message": "Subject created successfully"}

@router.get("/{subject_id}", response_model=SubjectResponse)
async def get_subject(
    subject_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get a subject by ID"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    subject = db.query(SubjectInDB).filter(SubjectInDB.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    return subject

@router.put("/{subject_id}", status_code=status.HTTP_200_OK)
async def update_subject(
    subject_id: int,
    update_data: UpdateSubject,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Update a subject by ID"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can update subjects")
    
    subject = db.query(SubjectInDB).filter(SubjectInDB.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    # Update only the fields that are provided
    update_dict = update_data.dict(exclude_unset=True)
    
    # Check if name is being updated and if it already exists
    if "name" in update_dict:
        existing_subject = db.query(SubjectInDB).filter(
            SubjectInDB.name == update_dict["name"],
            SubjectInDB.id != subject_id
        ).first()
        if existing_subject:
            raise HTTPException(status_code=400, detail="Subject with this name already exists")
    
    # Validate parallels
    if "applicable_parallels" in update_dict and update_dict["applicable_parallels"] is not None:
        parallels = update_dict["applicable_parallels"]
        if any(p < 1 or p > 12 for p in parallels):
            raise HTTPException(status_code=400, detail="applicable_parallels must contain integers from 1 to 12")
        update_dict["applicable_parallels"] = sorted(list(set(parallels)))

    for key, value in update_dict.items():
        if hasattr(subject, key):
            setattr(subject, key, value)
    
    db.commit()
    db.refresh(subject)
    
    return {"message": "Subject updated successfully"}

@router.delete("/{subject_id}", status_code=status.HTTP_200_OK)
async def delete_subject(
    subject_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Delete a subject by ID (hard delete)"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete subjects")
    
    subject = db.query(SubjectInDB).filter(SubjectInDB.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    # Hard delete - physically remove from database
    db.delete(subject)
    db.commit()
    
    return {"message": "Subject deleted successfully"}