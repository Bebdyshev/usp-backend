from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from config import get_db
from schemas.models import *
from auth_utils import verify_access_token
from routes.auth import oauth2_scheme
from typing import List

router = APIRouter()

@router.get("/", response_model=SystemSettingsResponse)
async def get_system_settings(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get current system settings"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Get the first (and should be only) settings record
    settings = db.query(SystemSettingsInDB).filter(SystemSettingsInDB.is_active == 1).first()
    
    if not settings:
        # Create default settings if none exist
        default_settings = SystemSettingsInDB(
            min_grade=7,
            max_grade=12,
            class_letters=['A', 'B', 'C', 'D', 'E', 'F'],
            school_name="Школа",
            academic_year="2024-2025"
        )
        db.add(default_settings)
        db.commit()
        db.refresh(default_settings)
        settings = default_settings
    
    return settings

@router.put("/", response_model=SystemSettingsResponse)
async def update_system_settings(
    update_data: UpdateSystemSettings,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Update system settings (admin only)"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can update system settings")
    
    # Get current settings
    settings = db.query(SystemSettingsInDB).filter(SystemSettingsInDB.is_active == 1).first()
    
    if not settings:
        # Create new settings if none exist
        settings = SystemSettingsInDB()
        db.add(settings)
    
    # Update only the fields that are provided
    update_dict = update_data.dict(exclude_unset=True)
    
    # Validate grade range
    if "min_grade" in update_dict and "max_grade" in update_dict:
        if update_dict["min_grade"] >= update_dict["max_grade"]:
            raise HTTPException(status_code=400, detail="min_grade must be less than max_grade")
    elif "min_grade" in update_dict:
        if update_dict["min_grade"] >= settings.max_grade:
            raise HTTPException(status_code=400, detail="min_grade must be less than max_grade")
    elif "max_grade" in update_dict:
        if settings.min_grade >= update_dict["max_grade"]:
            raise HTTPException(status_code=400, detail="min_grade must be less than max_grade")
    
    # Validate class letters
    if "class_letters" in update_dict:
        class_letters = update_dict["class_letters"]
        if not class_letters or len(class_letters) == 0:
            raise HTTPException(status_code=400, detail="At least one class letter is required")
        if len(set(class_letters)) != len(class_letters):
            raise HTTPException(status_code=400, detail="Class letters must be unique")
    
    for key, value in update_dict.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
    
    db.commit()
    db.refresh(settings)
    
    return settings

@router.get("/available-classes", response_model=AvailableClassesResponse)
async def get_available_classes(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get all available classes based on current settings"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Get current settings
    settings = db.query(SystemSettingsInDB).filter(SystemSettingsInDB.is_active == 1).first()
    
    if not settings:
        # Return default if no settings
        settings = SystemSettingsInDB(
            min_grade=7,
            max_grade=12,
            class_letters=['A', 'B', 'C', 'D', 'E', 'F']
        )
    
    # Generate all possible classes
    classes = []
    grades = list(range(settings.min_grade, settings.max_grade + 1))
    
    for grade in grades:
        for letter in settings.class_letters:
            classes.append(f"{grade}{letter}")
    
    return AvailableClassesResponse(
        classes=classes,
        grades=grades
    )

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_system_settings(
    settings_data: CreateSystemSettings,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Create system settings (admin only, for initial setup)"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create system settings")
    
    # Check if settings already exist
    existing_settings = db.query(SystemSettingsInDB).filter(SystemSettingsInDB.is_active == 1).first()
    if existing_settings:
        raise HTTPException(status_code=400, detail="System settings already exist. Use PUT to update.")
    
    # Validate grade range
    if settings_data.min_grade >= settings_data.max_grade:
        raise HTTPException(status_code=400, detail="min_grade must be less than max_grade")
    
    # Validate class letters
    if not settings_data.class_letters or len(settings_data.class_letters) == 0:
        raise HTTPException(status_code=400, detail="At least one class letter is required")
    if len(set(settings_data.class_letters)) != len(settings_data.class_letters):
        raise HTTPException(status_code=400, detail="Class letters must be unique")
    
    # Create new settings
    db_settings = SystemSettingsInDB(
        min_grade=settings_data.min_grade,
        max_grade=settings_data.max_grade,
        class_letters=settings_data.class_letters,
        school_name=settings_data.school_name,
        academic_year=settings_data.academic_year
    )
    
    db.add(db_settings)
    db.commit()
    db.refresh(db_settings)
    
    return {"id": db_settings.id, "message": "System settings created successfully"}



