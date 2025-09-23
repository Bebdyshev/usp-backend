from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from config import get_db
from schemas.models import *
from auth_utils import verify_access_token
from routes.auth import oauth2_scheme
from typing import List, Optional
from datetime import datetime

router = APIRouter()

@router.get("/", response_model=List[AchievementResponse])
async def get_achievements(
    student_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    limit: Optional[int] = Query(100),
    offset: Optional[int] = Query(0),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get achievements with optional filters"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    query = db.query(AchievementInDB)
    
    # Apply filters
    if student_id:
        query = query.filter(AchievementInDB.student_id == student_id)
    if category:
        query = query.filter(AchievementInDB.category == category)
    
    # Order by most recent first
    query = query.order_by(AchievementInDB.achievement_date.desc())
    
    # Apply pagination
    achievements = query.offset(offset).limit(limit).all()
    
    # Enrich with related data
    result = []
    for achievement in achievements:
        student = db.query(StudentInDB).filter(StudentInDB.id == achievement.student_id).first()
        awarder = db.query(UserInDB).filter(UserInDB.id == achievement.awarded_by).first()
        
        achievement_data = {
            "id": achievement.id,
            "student_id": achievement.student_id,
            "title": achievement.title,
            "description": achievement.description,
            "category": achievement.category,
            "achievement_date": achievement.achievement_date,
            "awarded_by": achievement.awarded_by,
            "points": achievement.points,
            "certificate_url": achievement.certificate_url,
            "created_at": achievement.created_at,
            "updated_at": achievement.updated_at,
            "student_name": student.name if student else None,
            "awarder_name": awarder.name if awarder else None
        }
        result.append(achievement_data)
    
    return result

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_achievement(
    achievement: CreateAchievement,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Create a new achievement"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin, teacher, or curator
    if user_data.get("type") not in ["admin", "teacher", "curator"]:
        raise HTTPException(
            status_code=403, 
            detail="Only admins, teachers, and curators can create achievements"
        )
    
    # Validate student exists
    student = db.query(StudentInDB).filter(
        StudentInDB.id == achievement.student_id,
        StudentInDB.is_active == 1
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # Validate points (non-negative)
    if achievement.points < 0:
        raise HTTPException(
            status_code=400, 
            detail="Achievement points cannot be negative"
        )
    
    db_achievement = AchievementInDB(
        student_id=achievement.student_id,
        title=achievement.title,
        description=achievement.description,
        category=achievement.category,
        achievement_date=achievement.achievement_date or datetime.utcnow(),
        awarded_by=user_data.get("id"),
        points=achievement.points,
        certificate_url=achievement.certificate_url
    )
    
    db.add(db_achievement)
    db.commit()
    db.refresh(db_achievement)
    
    return {"id": db_achievement.id, "message": "Achievement created successfully"}

@router.put("/{achievement_id}", status_code=status.HTTP_200_OK)
async def update_achievement(
    achievement_id: int,
    update_data: UpdateAchievement,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Update an achievement by ID"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin, teacher, or curator
    if user_data.get("type") not in ["admin", "teacher", "curator"]:
        raise HTTPException(
            status_code=403, 
            detail="Only admins, teachers, and curators can update achievements"
        )
    
    achievement = db.query(AchievementInDB).filter(
        AchievementInDB.id == achievement_id
    ).first()
    if not achievement:
        raise HTTPException(status_code=404, detail="Achievement not found")
    
    # Only admin or the original awarder can update
    if user_data.get("type") != "admin" and achievement.awarded_by != user_data.get("id"):
        raise HTTPException(
            status_code=403, 
            detail="You can only update your own achievements"
        )
    
    # Update only the fields that are provided
    update_dict = update_data.dict(exclude_unset=True)
    
    # Validate points if being updated
    if "points" in update_dict and update_dict["points"] < 0:
        raise HTTPException(
            status_code=400, 
            detail="Achievement points cannot be negative"
        )
    
    for key, value in update_dict.items():
        if hasattr(achievement, key):
            setattr(achievement, key, value)
    
    db.commit()
    db.refresh(achievement)
    
    return {"message": "Achievement updated successfully"}

@router.delete("/{achievement_id}", status_code=status.HTTP_200_OK)
async def delete_achievement(
    achievement_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Delete an achievement by ID"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Only admins can delete achievements
    if user_data.get("type") != "admin":
        raise HTTPException(
            status_code=403, 
            detail="Only admins can delete achievements"
        )
    
    achievement = db.query(AchievementInDB).filter(
        AchievementInDB.id == achievement_id
    ).first()
    if not achievement:
        raise HTTPException(status_code=404, detail="Achievement not found")
    
    # Hard delete achievement
    db.delete(achievement)
    db.commit()
    
    return {"message": "Achievement deleted successfully"}

@router.get("/student/{student_id}", response_model=List[AchievementResponse])
async def get_student_achievements(
    student_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get all achievements for a specific student"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Verify student exists
    student = db.query(StudentInDB).filter(StudentInDB.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    achievements = db.query(AchievementInDB).filter(
        AchievementInDB.student_id == student_id
    ).order_by(AchievementInDB.achievement_date.desc()).all()
    
    # Enrich with related data
    result = []
    for achievement in achievements:
        awarder = db.query(UserInDB).filter(UserInDB.id == achievement.awarded_by).first()
        
        achievement_data = {
            "id": achievement.id,
            "student_id": achievement.student_id,
            "title": achievement.title,
            "description": achievement.description,
            "category": achievement.category,
            "achievement_date": achievement.achievement_date,
            "awarded_by": achievement.awarded_by,
            "points": achievement.points,
            "certificate_url": achievement.certificate_url,
            "created_at": achievement.created_at,
            "updated_at": achievement.updated_at,
            "student_name": student.name,
            "awarder_name": awarder.name if awarder else None
        }
        result.append(achievement_data)
    
    return result

@router.get("/categories", response_model=List[str])
async def get_achievement_categories(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get list of all achievement categories"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Get unique categories from achievements table
    categories = db.query(AchievementInDB.category).distinct().all()
    category_list = [category[0] for category in categories if category[0] is not None]
    
    return category_list

@router.get("/statistics", response_model=dict)
async def get_achievement_statistics(
    grade_id: Optional[int] = Query(None),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get achievement statistics"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    query = db.query(AchievementInDB)
    
    # Filter by grade if specified
    if grade_id:
        query = query.join(StudentInDB).filter(StudentInDB.grade_id == grade_id)
    
    achievements = query.all()
    
    # Calculate statistics
    total_achievements = len(achievements)
    total_points = sum(achievement.points for achievement in achievements)
    
    # Group by category
    category_distribution = {}
    category_points = {}
    for achievement in achievements:
        category = achievement.category
        if category in category_distribution:
            category_distribution[category] += 1
            category_points[category] += achievement.points
        else:
            category_distribution[category] = 1
            category_points[category] = achievement.points
    
    # Get top achievers if filtering by grade
    top_achievers = []
    if grade_id:
        student_points = {}
        for achievement in achievements:
            student_id = achievement.student_id
            if student_id in student_points:
                student_points[student_id] += achievement.points
            else:
                student_points[student_id] = achievement.points
        
        # Sort by points and get top 5
        sorted_students = sorted(student_points.items(), key=lambda x: x[1], reverse=True)[:5]
        
        for student_id, points in sorted_students:
            student = db.query(StudentInDB).filter(StudentInDB.id == student_id).first()
            if student:
                top_achievers.append({
                    "student_id": student_id,
                    "student_name": student.name,
                    "total_points": points
                })
    
    return {
        "total_achievements": total_achievements,
        "total_points": total_points,
        "average_points_per_achievement": round(total_points / total_achievements, 2) if total_achievements > 0 else 0,
        "category_distribution": category_distribution,
        "category_points": category_points,
        "top_achievers": top_achievers
    }



