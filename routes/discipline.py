from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from config import get_db
from schemas.models import *
from auth_utils import verify_access_token
from routes.auth import oauth2_scheme
from typing import List, Optional
from datetime import datetime

router = APIRouter()

@router.get("/", response_model=List[DisciplinaryActionResponse])
async def get_disciplinary_actions(
    student_id: Optional[int] = Query(None),
    severity_level: Optional[int] = Query(None),
    is_resolved: Optional[int] = Query(None),
    limit: Optional[int] = Query(100),
    offset: Optional[int] = Query(0),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get disciplinary actions with optional filters"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    query = db.query(DisciplinaryActionInDB)
    
    # Apply filters
    if student_id:
        query = query.filter(DisciplinaryActionInDB.student_id == student_id)
    if severity_level is not None:
        query = query.filter(DisciplinaryActionInDB.severity_level == severity_level)
    if is_resolved is not None:
        query = query.filter(DisciplinaryActionInDB.is_resolved == is_resolved)
    
    # Order by most recent first
    query = query.order_by(DisciplinaryActionInDB.action_date.desc())
    
    # Apply pagination
    actions = query.offset(offset).limit(limit).all()
    
    # Enrich with related data
    result = []
    for action in actions:
        student = db.query(StudentInDB).filter(StudentInDB.id == action.student_id).first()
        issuer = db.query(UserInDB).filter(UserInDB.id == action.issued_by).first()
        
        action_data = {
            "id": action.id,
            "student_id": action.student_id,
            "action_type": action.action_type,
            "description": action.description,
            "severity_level": action.severity_level,
            "issued_by": action.issued_by,
            "action_date": action.action_date,
            "is_resolved": action.is_resolved,
            "resolution_notes": action.resolution_notes,
            "created_at": action.created_at,
            "updated_at": action.updated_at,
            "student_name": student.name if student else None,
            "issuer_name": issuer.name if issuer else None
        }
        result.append(action_data)
    
    return result

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_disciplinary_action(
    action: CreateDisciplinaryAction,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Create a new disciplinary action"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin or teacher
    if user_data.get("type") not in ["admin", "teacher", "curator"]:
        raise HTTPException(
            status_code=403, 
            detail="Only admins, teachers, and curators can create disciplinary actions"
        )
    
    # Validate student exists
    student = db.query(StudentInDB).filter(
        StudentInDB.id == action.student_id,
        StudentInDB.is_active == 1
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # Validate severity level
    if action.severity_level < 1 or action.severity_level > 5:
        raise HTTPException(
            status_code=400, 
            detail="Severity level must be between 1 and 5"
        )
    
    db_action = DisciplinaryActionInDB(
        student_id=action.student_id,
        action_type=action.action_type,
        description=action.description,
        severity_level=action.severity_level,
        issued_by=user_data.get("id"),
        action_date=action.action_date or datetime.utcnow()
    )
    
    db.add(db_action)
    db.commit()
    db.refresh(db_action)
    
    return {"id": db_action.id, "message": "Disciplinary action created successfully"}

@router.put("/{action_id}", status_code=status.HTTP_200_OK)
async def update_disciplinary_action(
    action_id: int,
    update_data: UpdateDisciplinaryAction,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Update a disciplinary action by ID"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin, teacher, or curator
    if user_data.get("type") not in ["admin", "teacher", "curator"]:
        raise HTTPException(
            status_code=403, 
            detail="Only admins, teachers, and curators can update disciplinary actions"
        )
    
    action = db.query(DisciplinaryActionInDB).filter(
        DisciplinaryActionInDB.id == action_id
    ).first()
    if not action:
        raise HTTPException(status_code=404, detail="Disciplinary action not found")
    
    # Only admin or the original issuer can update
    if user_data.get("type") != "admin" and action.issued_by != user_data.get("id"):
        raise HTTPException(
            status_code=403, 
            detail="You can only update your own disciplinary actions"
        )
    
    # Update only the fields that are provided
    update_dict = update_data.dict(exclude_unset=True)
    
    # Validate severity level if being updated
    if "severity_level" in update_dict:
        if update_dict["severity_level"] < 1 or update_dict["severity_level"] > 5:
            raise HTTPException(
                status_code=400, 
                detail="Severity level must be between 1 and 5"
            )
    
    for key, value in update_dict.items():
        if hasattr(action, key):
            setattr(action, key, value)
    
    db.commit()
    db.refresh(action)
    
    return {"message": "Disciplinary action updated successfully"}

@router.delete("/{action_id}", status_code=status.HTTP_200_OK)
async def delete_disciplinary_action(
    action_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Delete a disciplinary action by ID"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Only admins can delete disciplinary actions
    if user_data.get("type") != "admin":
        raise HTTPException(
            status_code=403, 
            detail="Only admins can delete disciplinary actions"
        )
    
    action = db.query(DisciplinaryActionInDB).filter(
        DisciplinaryActionInDB.id == action_id
    ).first()
    if not action:
        raise HTTPException(status_code=404, detail="Disciplinary action not found")
    
    # Hard delete disciplinary action
    db.delete(action)
    db.commit()
    
    return {"message": "Disciplinary action deleted successfully"}

@router.get("/student/{student_id}", response_model=List[DisciplinaryActionResponse])
async def get_student_disciplinary_actions(
    student_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get all disciplinary actions for a specific student"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Verify student exists
    student = db.query(StudentInDB).filter(StudentInDB.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    actions = db.query(DisciplinaryActionInDB).filter(
        DisciplinaryActionInDB.student_id == student_id
    ).order_by(DisciplinaryActionInDB.action_date.desc()).all()
    
    # Enrich with related data
    result = []
    for action in actions:
        issuer = db.query(UserInDB).filter(UserInDB.id == action.issued_by).first()
        
        action_data = {
            "id": action.id,
            "student_id": action.student_id,
            "action_type": action.action_type,
            "description": action.description,
            "severity_level": action.severity_level,
            "issued_by": action.issued_by,
            "action_date": action.action_date,
            "is_resolved": action.is_resolved,
            "resolution_notes": action.resolution_notes,
            "created_at": action.created_at,
            "updated_at": action.updated_at,
            "student_name": student.name,
            "issuer_name": issuer.name if issuer else None
        }
        result.append(action_data)
    
    return result

@router.get("/statistics", response_model=dict)
async def get_discipline_statistics(
    grade_id: Optional[int] = Query(None),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get disciplinary action statistics"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    query = db.query(DisciplinaryActionInDB)
    
    # Filter by grade if specified
    if grade_id:
        query = query.join(StudentInDB).filter(StudentInDB.grade_id == grade_id)
    
    actions = query.all()
    
    # Calculate statistics
    total_actions = len(actions)
    resolved_actions = len([a for a in actions if a.is_resolved == 1])
    unresolved_actions = total_actions - resolved_actions
    
    # Group by severity level
    severity_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for action in actions:
        severity_distribution[action.severity_level] += 1
    
    # Group by action type
    action_type_distribution = {}
    for action in actions:
        action_type = action.action_type
        if action_type in action_type_distribution:
            action_type_distribution[action_type] += 1
        else:
            action_type_distribution[action_type] = 1
    
    return {
        "total_actions": total_actions,
        "resolved_actions": resolved_actions,
        "unresolved_actions": unresolved_actions,
        "resolution_rate": round((resolved_actions / total_actions * 100), 2) if total_actions > 0 else 0,
        "severity_distribution": severity_distribution,
        "action_type_distribution": action_type_distribution
    }



