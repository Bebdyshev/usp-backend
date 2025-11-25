from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from schemas.models import ScoresInDB, StudentInDB, GradeInDB
from auth_utils import verify_access_token
from routes.auth import oauth2_scheme
from config import get_db 
import re

router = APIRouter()

@router.get("/danger-levels")
def get_danger_level_stats(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
    ):
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Fetch all scores with student_id and danger_level
    scores_data = db.query(ScoresInDB.student_id, ScoresInDB.danger_level).all()

    # Group by student
    student_danger_sums = {}
    student_danger_counts = {}

    for student_id, danger_level in scores_data:
        if danger_level is not None:
            student_danger_sums[student_id] = student_danger_sums.get(student_id, 0) + danger_level
            student_danger_counts[student_id] = student_danger_counts.get(student_id, 0) + 1
    
    # Get all student IDs to handle those with no scores
    all_student_ids = db.query(StudentInDB.id).all()
    all_student_ids = set(s[0] for s in all_student_ids)
    
    danger_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    total_danger_sum = 0
    students_with_danger = 0

    for student_id in all_student_ids:
        if student_id in student_danger_counts and student_danger_counts[student_id] > 0:
            avg_danger = round(student_danger_sums[student_id] / student_danger_counts[student_id])
            # Clamp to valid range 0-3 just in case
            avg_danger = max(0, min(3, int(avg_danger)))
            danger_counts[avg_danger] += 1
            
            total_danger_sum += avg_danger
            students_with_danger += 1
        else:
            # No scores -> Low risk (0)
            danger_counts[0] += 1

    # Initialize the result
    danger_level_stats = {level: {
                            "student_count": count,
                            "avg_delta_percentage": 0 # Placeholder as we focus on counts
                         } for level, count in danger_counts.items()}
    
    # Add total number of students and average danger level to the result
    danger_level_stats["total_students"] = len(all_student_ids)
    danger_level_stats["avg_danger_level"] = round(total_danger_sum / students_with_danger, 2) if students_with_danger > 0 else 0

    # Query to get all dangerous classes ordered by average danger level
    # We need to recalculate this too to be consistent, but for now let's keep the query 
    # or update it to use the same logic if possible. 
    # The original query was:
    # dangerous_classes = db.query(GradeInDB.grade, func.avg(ScoresInDB.danger_level)...)
    # This is also averaging per score, which might be slightly off but acceptable for "average danger of class".
    # However, "average danger of class" usually means "average of (average danger of student)".
    # Let's leave the dangerous_classes query as is for now to minimize changes, 
    # as the user specifically complained about the counts.
    
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

@router.get("/danger-levels-piechart")
def get_class_danger_percentages(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    total_students_by_class = db.query(
        GradeInDB.grade,
        func.count(StudentInDB.id)
    ).join(StudentInDB, StudentInDB.grade_id == GradeInDB.id) \
     .group_by(GradeInDB.grade).all()

    total_students_dict = {grade: count for grade, count in total_students_by_class}
    total_students = sum(total_students_dict.values())

    if not total_students:
        return {
            "class_danger_percentages": [],
            "overall_danger_summary": {
                "total_danger_students": 0,
                "percentage_of_all_students": 0.00
            }
        }

    class_danger_stats = db.query(
        GradeInDB.grade,
        ScoresInDB.danger_level,
        func.count(ScoresInDB.student_id).label("student_count")
    ).join(StudentInDB, StudentInDB.grade_id == GradeInDB.id) \
     .join(ScoresInDB, ScoresInDB.student_id == StudentInDB.id) \
     .group_by(GradeInDB.grade, ScoresInDB.danger_level) \
     .order_by(GradeInDB.grade, ScoresInDB.danger_level).all()

    class_percentages = {}
    danger_students_by_class = {}

    total_students_by_danger = {1: 0, 2: 0, 3: 0}  

    for grade, danger_level, student_count in class_danger_stats:
        if danger_level > 0:  
            total_students_by_danger[danger_level] += student_count  

        if grade not in class_percentages:
            class_percentages[grade] = {1: 0, 2: 0, 3: 0}
            danger_students_by_class[grade] = 0

        if danger_level > 0:  
            class_percentages[grade][danger_level] += student_count
            danger_students_by_class[grade] += student_count  

    total_danger_students = sum(danger_students_by_class.values())

    class_danger_result = []
    for grade, levels in class_percentages.items():
        total_danger = danger_students_by_class.get(grade, 0)

        class_danger_result.append({
            "grade": grade,
            "1": round((levels[1] / total_students_by_danger[1]) * 100, 2) if total_students_by_danger[1] > 0 else 0.00,
            "2": round((levels[2] / total_students_by_danger[2]) * 100, 2) if total_students_by_danger[2] > 0 else 0.00,
            "3": round((levels[3] / total_students_by_danger[3]) * 100, 2) if total_students_by_danger[3] > 0 else 0.00,
            "total": round((total_danger / total_danger_students) * 100, 2) if total_danger_students > 0 else 0.00
        })

    return {
        "class_danger_percentages": class_danger_result
    }
