from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from auth_utils import hash_password, verify_password, create_access_token, verify_access_token
from config import get_db
from schemas.models import *
from datetime import timedelta
from typing import List, Optional
from routes.auth import oauth2_scheme

router = APIRouter()

@router.get("/", response_model=List[dict])
async def get_all_users(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get all users"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can view all users")
    
    users = db.query(UserInDB).all()
    
    result = []
    for user in users:
        # Не включаем хэш пароля в ответ
        result.append({
            "id": user.id,
            "name": user.name,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "type": user.type,
            "company_name": user.company_name,
            "shanyrak": user.shanyrak,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "updated_at": user.updated_at
        })
    
    return result

@router.get("/by-type/{user_type}", response_model=List[dict])
async def get_users_by_type(
    user_type: str,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get users by type (curator, teacher, admin, etc.)"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Validate user type
    valid_types = ['admin', 'curator', 'teacher', 'user']
    if user_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid user type. Must be one of: {valid_types}")
    
    users = db.query(UserInDB).filter(
        UserInDB.type == user_type,
        UserInDB.is_active == 1
    ).all()
    
    result = []
    for user in users:
        # Get additional info based on user type
        additional_info = {}
        
        if user_type == 'curator':
            # Count assigned grades
            grade_count = db.query(GradeInDB).filter(GradeInDB.curator_id == user.id).count()
            additional_info['assigned_grades_count'] = grade_count
        
        elif user_type == 'teacher':
            # Count teaching assignments
            assignment_count = db.query(TeacherAssignmentInDB).filter(
                TeacherAssignmentInDB.teacher_id == user.id,
                TeacherAssignmentInDB.is_active == 1
            ).count()
            additional_info['assignment_count'] = assignment_count
        
        result.append({
            "id": user.id,
            "name": user.name,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "type": user.type,
            "company_name": user.company_name,
            "shanyrak": user.shanyrak,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            **additional_info
        })
    
    return result

@router.get("/{user_id}", response_model=dict)
async def get_user(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get user by ID"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Admins can view any user, regular users can only view themselves
    if user_data.get("type") != "admin" and user_data.get("id") != user_id:
        raise HTTPException(status_code=403, detail="You can only view your own data")
    
    user = db.query(UserInDB).filter(UserInDB.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "type": user.type
    }

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    type: str

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Create a new user"""
    admin_data = verify_access_token(token)
    if not admin_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Only admins can create users
    if admin_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create users")
    
    # Check if email already exists
    existing_user = db.query(UserInDB).filter(UserInDB.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user
    hashed_password = hash_password(user_data.password)
    
    new_user = UserInDB(
        name=user_data.name,
        email=user_data.email,
        hashed_password=hashed_password,
        type=user_data.type
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {
        "id": new_user.id,
        "message": "User created successfully"
    }

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    type: Optional[str] = None

@router.put("/{user_id}", status_code=status.HTTP_200_OK)
async def update_user(
    user_id: int,
    update_data: UserUpdate,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Update user by ID"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Admins can update any user, regular users can only update themselves and not change their type
    if user_data.get("type") != "admin":
        if user_data.get("id") != user_id:
            raise HTTPException(status_code=403, detail="You can only update your own data")
        if update_data.type is not None:
            raise HTTPException(status_code=403, detail="You cannot change your user type")
    
    user = db.query(UserInDB).filter(UserInDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update email if provided and not already taken
    if update_data.email is not None and update_data.email != user.email:
        existing_user = db.query(UserInDB).filter(UserInDB.email == update_data.email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        user.email = update_data.email
    
    # Update name if provided
    if update_data.name is not None:
        user.name = update_data.name
    
    # Update type if provided (admin only)
    if update_data.type is not None and user_data.get("type") == "admin":
        user.type = update_data.type
    
    # Update password if provided
    if update_data.password is not None:
        user.hashed_password = hash_password(update_data.password)
    
    db.commit()
    db.refresh(user)
    
    return {
        "message": "User updated successfully"
    }

@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Delete user by ID"""
    admin_data = verify_access_token(token)
    if not admin_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Only admins can delete users
    if admin_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete users")
    
    # Prevent admin from deleting themselves
    if admin_data.get("id") == user_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    
    user = db.query(UserInDB).filter(UserInDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(user)
    db.commit()
    
    return {
        "message": "User deleted successfully"
    }


