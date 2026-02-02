from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from schemas.models import ScoresInDB, StudentInDB, GradeInDB
from auth_utils import verify_access_token
from routes.auth import oauth2_scheme
from config import get_db 
from role_utils import get_user_allowed_grade_ids
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

    # Get allowed grade IDs for the current user
    allowed_grade_ids = get_user_allowed_grade_ids(user_data, db)
    
    # Build query for scores - filter by allowed grades if not admin
    scores_query = db.query(ScoresInDB.student_id, ScoresInDB.danger_level, ScoresInDB.grade_id)
    if allowed_grade_ids is not None:  # Not admin
        if not allowed_grade_ids:  # Empty set - no access
            return {
                "danger_level_stats": {
                    0: {"student_count": 0, "avg_delta_percentage": 0},
                    1: {"student_count": 0, "avg_delta_percentage": 0},
                    2: {"student_count": 0, "avg_delta_percentage": 0},
                    3: {"student_count": 0, "avg_delta_percentage": 0},
                    "total_students": 0,
                    "avg_danger_level": 0
                },
                "all_dangerous_classes": []
            }
        scores_query = scores_query.filter(ScoresInDB.grade_id.in_(allowed_grade_ids))
    
    scores_data = scores_query.all()

    # Group by student
    student_danger_sums = {}
    student_danger_counts = {}

    for student_id, danger_level, grade_id in scores_data:
        if danger_level is not None:
            student_danger_sums[student_id] = student_danger_sums.get(student_id, 0) + danger_level
            student_danger_counts[student_id] = student_danger_counts.get(student_id, 0) + 1
    
    # Get student IDs filtered by allowed grades
    students_query = db.query(StudentInDB.id)
    if allowed_grade_ids is not None:
        students_query = students_query.filter(StudentInDB.grade_id.in_(allowed_grade_ids))
    all_student_ids = set(s[0] for s in students_query.all())
    
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
    dangerous_classes_query = db.query(
        GradeInDB.grade,
        func.avg(ScoresInDB.danger_level).label("avg_danger_level")
    ).join(StudentInDB, StudentInDB.grade_id == GradeInDB.id) \
     .join(ScoresInDB, ScoresInDB.student_id == StudentInDB.id)
    
    if allowed_grade_ids is not None:
        dangerous_classes_query = dangerous_classes_query.filter(GradeInDB.id.in_(allowed_grade_ids))
    
    dangerous_classes = dangerous_classes_query.group_by(GradeInDB.grade) \
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

    # Get allowed grade IDs for the current user
    allowed_grade_ids = get_user_allowed_grade_ids(user_data, db)

    # Build base query with optional filtering
    total_students_query = db.query(
        GradeInDB.grade,
        func.count(StudentInDB.id)
    ).join(StudentInDB, StudentInDB.grade_id == GradeInDB.id)
    
    if allowed_grade_ids is not None:
        if not allowed_grade_ids:  # Empty set - no access
            return {
                "class_danger_percentages": [],
                "overall_danger_summary": {
                    "total_danger_students": 0,
                    "percentage_of_all_students": 0.00
                }
            }
        total_students_query = total_students_query.filter(GradeInDB.id.in_(allowed_grade_ids))
    
    total_students_by_class = total_students_query.group_by(GradeInDB.grade).all()

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

    class_danger_query = db.query(
        GradeInDB.grade,
        ScoresInDB.danger_level,
        func.count(ScoresInDB.student_id).label("student_count")
    ).join(StudentInDB, StudentInDB.grade_id == GradeInDB.id) \
     .join(ScoresInDB, ScoresInDB.student_id == StudentInDB.id)
    
    if allowed_grade_ids is not None:
        class_danger_query = class_danger_query.filter(GradeInDB.id.in_(allowed_grade_ids))
    
    class_danger_stats = class_danger_query.group_by(GradeInDB.grade, ScoresInDB.danger_level) \
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

@router.get("/insights")
def get_actionable_insights(
    class_level: Optional[str] = Query(None, description="Class level e.g. '8', '10'"),
    grade_id: Optional[int] = Query(None, description="Specific grade ID"),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Get actionable insights for curators and admins:
    - Top at-risk students requiring immediate attention
    - Classes with declining performance
    - Subject-level analysis
    - Recommendations
    """
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    allowed_grade_ids = get_user_allowed_grade_ids(user_data, db)

    # --- FILTERING ---
    # Apply Filters to allowed_grade_ids
    current_grades_query = db.query(GradeInDB)
    
    if allowed_grade_ids is not None:
        current_grades_query = current_grades_query.filter(GradeInDB.id.in_(allowed_grade_ids))
    
    if grade_id:
        current_grades_query = current_grades_query.filter(GradeInDB.id == grade_id)
        
    if class_level:
        current_grades_query = current_grades_query.filter(
             (GradeInDB.grade == class_level) | 
             (GradeInDB.grade.like(f"{class_level} %")) | 
             (GradeInDB.grade.like(f"{class_level}_%"))
        )
    
    filtered_grades_objs = current_grades_query.all()
    # IMPORTANT: Overwrite allowed_grade_ids with the filtered list
    allowed_grade_ids = [g.id for g in filtered_grades_objs]
    
    # 1. Get top at-risk students (danger_level >= 2)
    at_risk_query = db.query(
        StudentInDB.id,
        StudentInDB.name,
        GradeInDB.grade,
        GradeInDB.parallel,
        func.avg(ScoresInDB.danger_level).label("avg_danger"),
        func.avg(ScoresInDB.delta_percentage).label("avg_delta"),
        func.count(ScoresInDB.id).label("subjects_count")
    ).join(GradeInDB, StudentInDB.grade_id == GradeInDB.id) \
     .join(ScoresInDB, ScoresInDB.student_id == StudentInDB.id)
    
    if allowed_grade_ids is not None:
        if not allowed_grade_ids:
            return {
                "at_risk_students": [],
                "problem_classes": [],
                "subject_analysis": [],
                "recommendations": [],
                "summary": {"total_students": 0, "at_risk_count": 0, "critical_count": 0}
            }
        at_risk_query = at_risk_query.filter(GradeInDB.id.in_(allowed_grade_ids))
    
    at_risk_students = at_risk_query.group_by(
        StudentInDB.id, StudentInDB.name, GradeInDB.grade, GradeInDB.parallel
    ).having(func.avg(ScoresInDB.danger_level) >= 2) \
     .order_by(func.avg(ScoresInDB.danger_level).desc()) \
     .limit(10).all()
    
    at_risk_list = [{
        "id": s.id,
        "name": s.name,
        "class": f"{s.grade} {s.parallel}" if s.parallel else s.grade,
        "avg_danger_level": round(float(s.avg_danger), 1),
        "avg_delta_percentage": round(float(s.avg_delta), 1) if s.avg_delta else 0,
        "subjects_affected": s.subjects_count,
        "priority": "critical" if s.avg_danger >= 2.5 else "high"
    } for s in at_risk_students]
    
    # 2. Problem classes (classes with highest average danger)
    problem_classes_query = db.query(
        GradeInDB.id,
        GradeInDB.grade,
        GradeInDB.parallel,
        GradeInDB.curator_name,
        func.count(StudentInDB.id.distinct()).label("student_count"),
        func.avg(ScoresInDB.danger_level).label("avg_danger"),
        func.sum(case((ScoresInDB.danger_level >= 2, 1), else_=0)).label("at_risk_count")
    ).join(StudentInDB, StudentInDB.grade_id == GradeInDB.id) \
     .join(ScoresInDB, ScoresInDB.student_id == StudentInDB.id)
    
    if allowed_grade_ids is not None:
        problem_classes_query = problem_classes_query.filter(GradeInDB.id.in_(allowed_grade_ids))
    
    problem_classes = problem_classes_query.group_by(
        GradeInDB.id, GradeInDB.grade, GradeInDB.parallel, GradeInDB.curator_name
    ).having(func.avg(ScoresInDB.danger_level) >= 1.5) \
     .order_by(func.avg(ScoresInDB.danger_level).desc()) \
     .limit(5).all()
    
    problem_classes_list = [{
        "id": c.id,
        "class": f"{c.grade} {c.parallel}" if c.parallel else c.grade,
        "curator": c.curator_name or "Не назначен",
        "student_count": c.student_count,
        "avg_danger_level": round(float(c.avg_danger), 2),
        "at_risk_students": int(c.at_risk_count) if c.at_risk_count else 0,
        "attention_needed": "immediate" if c.avg_danger >= 2 else "monitor"
    } for c in problem_classes]
    
    # 3. Subject analysis - which subjects have most problems
    subject_query = db.query(
        ScoresInDB.subject_name,
        func.count(ScoresInDB.id).label("total_scores"),
        func.avg(ScoresInDB.danger_level).label("avg_danger"),
        func.avg(ScoresInDB.delta_percentage).label("avg_delta"),
        func.sum(case((ScoresInDB.danger_level >= 2, 1), else_=0)).label("problem_count")
    )
    
    if allowed_grade_ids is not None:
        subject_query = subject_query.filter(ScoresInDB.grade_id.in_(allowed_grade_ids))
    
    subject_stats = subject_query.filter(ScoresInDB.subject_name.isnot(None)) \
     .group_by(ScoresInDB.subject_name) \
     .order_by(func.avg(ScoresInDB.danger_level).desc()).all()
    
    subject_analysis = [{
        "subject": s.subject_name,
        "students_count": s.total_scores,
        "avg_danger_level": round(float(s.avg_danger), 2) if s.avg_danger else 0,
        "avg_performance_gap": round(float(s.avg_delta), 1) if s.avg_delta else 0,
        "problem_students": int(s.problem_count) if s.problem_count else 0,
        "status": "critical" if (s.avg_danger or 0) >= 2 else "warning" if (s.avg_danger or 0) >= 1.5 else "ok"
    } for s in subject_stats]
    
    # 4. Generate recommendations
    recommendations = []
    
    if at_risk_list:
        critical_count = len([s for s in at_risk_list if s["priority"] == "critical"])
        if critical_count > 0:
            recommendations.append({
                "type": "urgent",
                "title": "Критические случаи",
                "description": f"{critical_count} студентов требуют немедленного внимания. Рекомендуется связаться с родителями и организовать дополнительные занятия.",
                "action": "Просмотреть список студентов",
                "link": "/dashboard/students?danger=3"
            })
    
    if problem_classes_list:
        recommendations.append({
            "type": "warning", 
            "title": "Проблемные классы",
            "description": f"Обнаружено {len(problem_classes_list)} классов с повышенным уровнем риска. Необходимо проанализировать причины и разработать план коррекции.",
            "action": "Анализировать классы",
            "link": "/dashboard/classes"
        })
    
    # Subject-specific recommendations
    problem_subjects = [s for s in subject_analysis if s["status"] in ["critical", "warning"]]
    if problem_subjects:
        worst_subject = problem_subjects[0]
        recommendations.append({
            "type": "info",
            "title": f"Предмет требует внимания: {worst_subject['subject']}",
            "description": f"По предмету '{worst_subject['subject']}' средний уровень риска {worst_subject['avg_danger_level']}. {worst_subject['problem_students']} студентов испытывают трудности.",
            "action": "Провести анализ",
            "link": None
        })
    
    if not recommendations:
        recommendations.append({
            "type": "success",
            "title": "Всё под контролем",
            "description": "На данный момент критических проблем не обнаружено. Продолжайте мониторинг успеваемости.",
            "action": None,
            "link": None
        })
    
    # 5. Summary stats
    total_query = db.query(func.count(StudentInDB.id.distinct()))
    if allowed_grade_ids is not None:
        total_query = total_query.filter(StudentInDB.grade_id.in_(allowed_grade_ids))
    total_students = total_query.scalar() or 0
    
    at_risk_count_query = db.query(func.count(StudentInDB.id.distinct())) \
        .join(ScoresInDB, ScoresInDB.student_id == StudentInDB.id)
    if allowed_grade_ids is not None:
        at_risk_count_query = at_risk_count_query.filter(StudentInDB.grade_id.in_(allowed_grade_ids))
    # Count students with any danger level >= 2
    at_risk_total = at_risk_count_query.filter(ScoresInDB.danger_level >= 2).scalar() or 0
    critical_total = at_risk_count_query.filter(ScoresInDB.danger_level >= 3).scalar() or 0
    
    return {
        "at_risk_students": at_risk_list,
        "problem_classes": problem_classes_list,
        "subject_analysis": subject_analysis,
        "recommendations": recommendations,
        "summary": {
            "total_students": total_students,
            "at_risk_count": at_risk_total,
            "critical_count": critical_total,
            "at_risk_percentage": round((at_risk_total / total_students * 100), 1) if total_students > 0 else 0
        }
    }
