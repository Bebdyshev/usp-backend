from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body, Query
from sqlalchemy.orm import Session
from config import get_db
from schemas.models import *
from auth_utils import verify_access_token
from routes.auth import oauth2_scheme
from role_utils import check_grade_access, get_user_allowed_subject_ids
import pandas as pd
from io import BytesIO, StringIO
from services.analyze import analyze_excel
from typing import Optional

router = APIRouter()

@router.get("/class/{classParam}")
def get_class_info(
    classParam: str,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Query to get the class information
    class_info = db.query(GradeInDB).filter(GradeInDB.grade == classParam).first()

    if not class_info:
        raise HTTPException(status_code=404, detail="Class not found")

    if not check_grade_access(user_data, class_info.id, db):
        raise HTTPException(status_code=403, detail="You don't have access to this class")

    allowed_subject_ids = get_user_allowed_subject_ids(user_data, db)
    if allowed_subject_ids is not None and not allowed_subject_ids:
        return {
            "class_name": class_info.grade,
            "avg_danger_level": 0,
            "students": []
        }

    # Query to get all students in the specified class
    students_in_class = db.query(StudentInDB).filter(StudentInDB.grade_id == class_info.id).all()

    # Prepare student details with their scores and attendance
    students_details = []
    total_danger_level = 0
    for student in students_in_class:
        scores_q = db.query(ScoresInDB).filter(ScoresInDB.student_id == student.id)
        if allowed_subject_ids is not None:
            scores_q = scores_q.filter(ScoresInDB.subject_id.in_(allowed_subject_ids))
        scores = scores_q.all()
        student_scores = {score.subject_name: score.actual_scores for score in scores}
        danger_level = sum(score.danger_level for score in scores) / len(scores) if scores else 0
        total_danger_level += danger_level

        # Assuming attendance is calculated or stored somewhere
        attendance = 95  # Placeholder for actual attendance calculation

        students_details.append({
            "id": student.id,
            "name": student.name,
            "danger_level": danger_level,
            "attendance": attendance,
            "grades": student_scores
        })

    avg_danger_level = total_danger_level / len(students_in_class) if students_in_class else 0

    # Construct the response
    response = {
        "class_name": class_info.grade,
        "avg_danger_level": avg_danger_level,
        "students": students_details
    }

    return response