from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from schemas.models import ScoresInDB, StudentInDB, GradeInDB
from auth_utils import verify_access_token
from routes.auth import oauth2_scheme
from config import get_db 

router = APIRouter()

@router.get("/danger-levels")
def get_danger_level_stats(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
    ):
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Define possible danger levels
    danger_levels = [1, 2, 3]

    # Query to count students per danger level and calculate the average delta percentage
    stats = db.query(
                ScoresInDB.danger_level,
                func.count(ScoresInDB.student_id).label("student_count"),
                func.avg(ScoresInDB.delta_percentage).label("avg_delta_percentage")
            ).filter(ScoresInDB.danger_level.in_(danger_levels))\
             .group_by(ScoresInDB.danger_level)\
             .all()

    # Query to get the total number of students
    total_students = db.query(func.count(ScoresInDB.student_id)).scalar()

    # Query to get the average danger level across all students
    avg_danger_level = db.query(func.avg(ScoresInDB.danger_level)).scalar()

    # Initialize the result with zeros and None for missing values
    danger_level_stats = {level: {
                            "student_count": 0,
                            "avg_delta_percentage": None
                         } for level in danger_levels}

    # Update the result with the actual data from the database
    for level, student_count, avg_delta_percentage in stats:
        danger_level_stats[level]["student_count"] = student_count
        danger_level_stats[level]["avg_delta_percentage"] = avg_delta_percentage
    
    # Add total number of students and average danger level to the result
    danger_level_stats["total_students"] = total_students
    danger_level_stats["avg_danger_level"] = avg_danger_level

    # Query to get all dangerous classes ordered by average danger level
    dangerous_classes = db.query(
        GradeInDB.grade,
        func.avg(ScoresInDB.danger_level).label("avg_danger_level")
    ).join(StudentInDB, StudentInDB.grade_id == GradeInDB.id) \
     .join(ScoresInDB, ScoresInDB.student_id == StudentInDB.id) \
     .group_by(GradeInDB.grade) \
     .order_by(func.avg(ScoresInDB.danger_level).desc()).all()

    all_dangerous_classes = [
        {"grade": grade, "avg_danger_level": avg_danger_level}
        for grade, avg_danger_level in dangerous_classes
    ]

    return {
        "danger_level_stats": danger_level_stats,
        "all_dangerous_classes": all_dangerous_classes
    }
