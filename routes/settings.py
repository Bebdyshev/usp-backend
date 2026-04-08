from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from config import get_db
from schemas.models import *
from auth_utils import verify_access_token
from routes.auth import oauth2_scheme
from typing import List

from services.school_year import (
    get_current_academic_year,
    next_academic_year_label,
    promote_all_students_to_next_grade,
)

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


@router.post("/advance-academic-year", response_model=AdvanceAcademicYearResponse)
async def advance_academic_year(
    dry_run: bool = Query(False, description="Только проверка, без изменений в БД"),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """
    Новый учебный год: перевести всех учеников на следующий параллельный класс (та же литера),
    затем увеличить учебный год в настройках (2024-2025 → 2025-2026).
    Оценки прошлых лет в таблице scores не удаляются — привязаны к полю academic_year.
    """
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can advance the academic year")

    settings = db.query(SystemSettingsInDB).filter(SystemSettingsInDB.is_active == 1).first()
    if not settings:
        raise HTTPException(status_code=400, detail="Сначала создайте системные настройки")

    current = get_current_academic_year(db)
    try:
        next_label = next_academic_year_label(current)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    preview = promote_all_students_to_next_grade(db, dry_run=True)
    if dry_run:
        return AdvanceAcademicYearResponse(
            dry_run=True,
            previous_academic_year=current,
            new_academic_year=next_label,
            promoted=preview["promoted"],
            graduated_unchanged=preview["graduated_unchanged"],
            issues=preview["issues"],
        )

    if preview["issues"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Устраните проблемы со справочником классов или учениками, затем повторите",
                "issues": preview["issues"],
            },
        )

    promote_all_students_to_next_grade(db, dry_run=False)
    settings.academic_year = next_label
    db.commit()
    db.refresh(settings)

    return AdvanceAcademicYearResponse(
        dry_run=False,
        previous_academic_year=current,
        new_academic_year=next_label,
        promoted=preview["promoted"],
        graduated_unchanged=preview["graduated_unchanged"],
        issues=[],
    )


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

@router.get("/prediction-weights", response_model=PredictionWeightsResponse)
async def get_prediction_weights(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get current prediction weights (admin only)"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can view prediction weights")
    
    # Get active prediction settings
    settings = db.query(PredictionSettings).filter(PredictionSettings.is_active == 1).first()
    
    if not settings:
        # Create default settings if none exist
        default_weights = {
            'previous_class': 0.3,
            'teacher': 0.2,
            'quarters': 0.5
        }
        default_settings = PredictionSettings(
            name="default_weights",
            weights=default_weights
        )
        db.add(default_settings)
        db.commit()
        db.refresh(default_settings)
        settings = default_settings
    
    return settings

@router.put("/prediction-weights", response_model=PredictionWeightsResponse)
async def update_prediction_weights(
    update_data: UpdatePredictionWeights,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Update prediction weights (admin only)"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can update prediction weights")
    
    # Validate weights sum to approximately 1.0
    weights = update_data.weights
    total = sum(weights.values())
    if abs(total - 1.0) > 0.01:  # Allow small floating point errors
        raise HTTPException(
            status_code=400, 
            detail=f"Weights must sum to 1.0, but they sum to {total}"
        )
    
    # Validate required weight keys
    required_keys = {'previous_class', 'teacher', 'quarters'}
    if not required_keys.issubset(weights.keys()):
        raise HTTPException(
            status_code=400,
            detail=f"Missing required weight keys. Required: {required_keys}, provided: {set(weights.keys())}"
        )
    
    # Get or create prediction settings
    settings = db.query(PredictionSettings).filter(PredictionSettings.is_active == 1).first()
    
    if not settings:
        settings = PredictionSettings(
            name=update_data.name or "default_weights",
            weights=weights
        )
        db.add(settings)
    else:
        settings.weights = weights
        if update_data.name:
            settings.name = update_data.name
    
    db.commit()
    db.refresh(settings)
    
    return settings

@router.get("/excel-mapping", response_model=List[ExcelColumnMappingResponse])
async def get_excel_column_mappings(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get all Excel column mappings (admin only)"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can view Excel column mappings")
    
    mappings = db.query(ExcelColumnMapping).filter(ExcelColumnMapping.is_active == 1).all()
    
    return mappings

@router.put("/excel-mapping/{field_name}", response_model=ExcelColumnMappingResponse)
async def update_excel_column_mapping(
    field_name: str,
    update_data: UpdateExcelColumnMapping,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Update Excel column mapping for a specific field (admin only)"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can update Excel column mappings")
    
    # Find existing mapping
    mapping = db.query(ExcelColumnMapping).filter(
        ExcelColumnMapping.field_name == field_name
    ).first()
    
    if not mapping:
        raise HTTPException(status_code=404, detail=f"Column mapping for field '{field_name}' not found")
    
    # Update fields
    if update_data.column_aliases is not None:
        if len(update_data.column_aliases) == 0:
            raise HTTPException(status_code=400, detail="At least one column alias is required")
        mapping.column_aliases = update_data.column_aliases
    
    if update_data.is_active is not None:
        mapping.is_active = update_data.is_active
    
    db.commit()
    db.refresh(mapping)
    
    return mapping

@router.post("/excel-mapping", status_code=status.HTTP_201_CREATED, response_model=ExcelColumnMappingResponse)
async def create_excel_column_mapping(
    mapping_data: CreateExcelColumnMapping,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Create a new Excel column mapping (admin only)"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create Excel column mappings")
    
    # Check if mapping already exists
    existing = db.query(ExcelColumnMapping).filter(
        ExcelColumnMapping.field_name == mapping_data.field_name
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Column mapping for field '{mapping_data.field_name}' already exists. Use PUT to update."
        )
    
    # Validate aliases
    if len(mapping_data.column_aliases) == 0:
        raise HTTPException(status_code=400, detail="At least one column alias is required")
    
    # Create new mapping
    new_mapping = ExcelColumnMapping(
        field_name=mapping_data.field_name,
        column_aliases=mapping_data.column_aliases
    )
    
    db.add(new_mapping)
    db.commit()
    db.refresh(new_mapping)
    
    return new_mapping
