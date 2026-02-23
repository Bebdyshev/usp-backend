from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from config import get_db
from schemas.models import *
from sqlalchemy import or_
from auth_utils import verify_access_token
from routes.auth import oauth2_scheme
from role_utils import get_user_allowed_grade_ids, check_grade_access
import pandas as pd
from io import BytesIO, StringIO
from services.analyze import analyze_excel
from services.excel_parser import parse_excel_grades, generate_excel_template
from typing import Optional, List

router = APIRouter()

@router.post("/send/")
async def send_excel_as_csv_to_openai(
    grade: str = Form(...),
    curator: str = Form(...),
    subject: str = Form(...),
    file: UploadFile = File(...),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    try:
        user_data = verify_access_token(token)
        if not user_data:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        contents = await file.read()
        excel_data = BytesIO(contents)

        # Читаем только первый лист
        df = pd.read_excel(excel_data, sheet_name=0)

        # Конвертируем в CSV
        csv_data = StringIO()
        df.to_csv(csv_data, index=False)
        csv_text = csv_data.getvalue()
        print("csv text:", csv_text)

        # Анализируем CSV
        json_response = analyze_excel(csv_text)
        print(json_response)

        user = db.query(UserInDB).filter(UserInDB.email == user_data["sub"]).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Ищем класс по grade и curator
        db_grade = db.query(GradeInDB).filter(GradeInDB.grade == grade, GradeInDB.curator_name == curator).first()

        if not db_grade:
            db_grade = GradeInDB(
                grade=grade, 
                curator_name=curator, 
                user_id=user.id,
                parallel="",
                student_count=0
            )
            db.add(db_grade)
            db.commit()
            db.refresh(db_grade)

        # Обработка данных студентов
        for analysis_item in json_response['students']:
            student_name = analysis_item["student_name"]
            print(student_name)

            actual_score = [score if score is not None else 0.0 for score in analysis_item['actual_score']]
            predicted_scores = [score if score is not None else 0.0 for score in analysis_item['predicted_score']]

            if len(actual_score) != len(predicted_scores):
                raise HTTPException(status_code=400, detail="Actual scores and predicted scores must have the same length.")

            # Разница между оценками
            score_differences = [abs(a - p) for a, p in zip(actual_score, predicted_scores)]
            total_score_difference = sum(score_differences)

            total_predicted_score = sum(predicted_scores)
            percentage_difference = (total_score_difference / max(total_predicted_score, 1)) * 100  # Защита от деления на 0

            # Определяем danger_level (новая логика)
            # меньше 10% - умеренный (1)
            # 10-20% - повышенный (2)
            # больше 20% - критический (3)
            if percentage_difference < 10:
                danger_level = 1  
            elif 10 <= percentage_difference <= 20:
                danger_level = 2  
            else:
                danger_level = 3 
            print('danger level', danger_level)

            # Ищем студента в БД по имени и классу
            db_student = db.query(StudentInDB).filter(
                StudentInDB.name == student_name, 
                StudentInDB.grade_id == db_grade.id
            ).first()

            if not db_student:
                db_student = StudentInDB(name=student_name, grade_id=db_grade.id) 
                db.add(db_student)
                db.commit()
                db.refresh(db_student)

            # Обновляем или создаем запись с оценками ПО ПРЕДМЕТУ
            db_score = db.query(ScoresInDB).filter(
                ScoresInDB.student_id == db_student.id,
                ScoresInDB.subject_name == subject
            ).first()
            if db_score:
                db_score.actual_scores = actual_score
                db_score.predicted_scores = predicted_scores
                db_score.danger_level = danger_level
                db_score.delta_percentage = round(percentage_difference, 1)
            else:
                new_score = ScoresInDB(
                    subject_name=subject,
                    actual_scores=actual_score,
                    predicted_scores=predicted_scores,
                    danger_level=danger_level,
                    delta_percentage=round(percentage_difference, 1),
                    student_id=db_student.id,
                    grade_id=db_grade.id,
                )
                print(new_score)

                db.add(new_score)

            if db_score:
                print(db_score)

        db.commit()

        return {"analysis": json_response}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


@router.get("/get_class")
def get_class_data(
    subject: Optional[str] = Query(None, description="Filter by subject name"),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        user_data = verify_access_token(token)  
        if not user_data:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        allowed_grade_ids = get_user_allowed_grade_ids(user_data, db)
        
        grades_query = db.query(GradeInDB)
        if allowed_grade_ids is not None:
            if not allowed_grade_ids:
                return {"class_data": []}
            grades_query = grades_query.filter(GradeInDB.id.in_(allowed_grade_ids))
        
        db_grades = grades_query.all()
        
        if not db_grades:
            return {"class_data": []}

        class_data = []
        
        for grade in db_grades:
            students = db.query(StudentInDB).filter(StudentInDB.grade_id == grade.id).all()
            student_info_list = []
            
            for student in students:
                scores_query = db.query(ScoresInDB).filter(ScoresInDB.student_id == student.id)
                if subject:
                    scores_query = scores_query.filter(ScoresInDB.subject_name == subject)
                student_scores = scores_query.all()

                all_valid_scores = []
                overall_danger_level = 0
                danger_count = 0
                
                actual_scores = []
                predicted_scores = []
                previous_class_score = None
                danger_level = None
                delta_percentage = None

                for score in student_scores:
                    if score.actual_scores and isinstance(score.actual_scores, list):
                        valid_scores = [s for s in score.actual_scores if s is not None and s > 0]
                        all_valid_scores.extend(valid_scores)
                    
                    if score.danger_level is not None:
                        overall_danger_level += score.danger_level
                        danger_count += 1
                    
                    if score.actual_scores:
                        actual_scores = score.actual_scores if isinstance(score.actual_scores, list) else []
                    if score.predicted_scores:
                        predicted_scores = score.predicted_scores if isinstance(score.predicted_scores, list) else []
                    if score.previous_class_score is not None:
                        previous_class_score = score.previous_class_score
                    danger_level = score.danger_level  
                    delta_percentage = score.delta_percentage
                
                avg_percentage = None
                if all_valid_scores:
                    avg_percentage = round(sum(all_valid_scores) / len(all_valid_scores), 1)
                
                if danger_count > 0:
                    danger_level = round(overall_danger_level / danger_count)

                student_info_list.append({
                    "id": student.id,
                    "student_name": student.name,
                    "email": student.email,
                    "previous_class_score": previous_class_score,
                    "actual_score": actual_scores,
                    "actual_scores": actual_scores,
                    "predicted_scores": predicted_scores,
                    "avg_percentage": avg_percentage,
                    "danger_level": danger_level,
                    "delta_percentage": delta_percentage,
                    "class_liter": grade.grade,  
                })
                
            class_data.append({
                "curator_name": grade.curator_name,
                "subject_name": subject,
                "grade_liter": grade.grade,
                "class": student_info_list
            })
        
        return {"class_data": class_data}

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="An error occurred while fetching class data")

@router.get("/get_students_danger")
def get_students_by_danger_level(
    level: int = Query(...),  # Change to Query
    token: str = Depends(oauth2_scheme),  # Токен пользователя для авторизации
    db: Session = Depends(get_db)  # Сессия базы данных
):
    try:
        # Проверяем токен
        user_data = verify_access_token(token)
        if not user_data:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        # Get allowed grade IDs for role-based filtering
        allowed_grade_ids = get_user_allowed_grade_ids(user_data, db)
        
        # Build query with role-based filtering
        grades_query = db.query(GradeInDB)
        if allowed_grade_ids is not None:  # Not admin
            if not allowed_grade_ids:  # Empty set - no access
                return {"filtered_class_data": []}
            grades_query = grades_query.filter(GradeInDB.id.in_(allowed_grade_ids))
        
        db_grades = grades_query.all()
        if not db_grades:
            return {"filtered_class_data": []}

        class_data = []

        for grade in db_grades:
            # Получаем студентов в классе
            students = db.query(StudentInDB).filter(StudentInDB.grade_id == grade.id).all()
            student_info_list = []
            subject_name = None  # Инициализируем переменную

            for student in students:
                # Получаем записи с оценками для студента
                student_scores = db.query(ScoresInDB).filter(ScoresInDB.student_id == student.id).all()

                # Ищем студентов с уровнем опасности выше указанного
                for score in student_scores:
                    if score.danger_level == level:
                        subject_name = score.subject_name  # Обновляем subject_name
                        student_info_list.append({
                            "id": student.id,
                            "student_name": student.name,
                            "actual_score": score.actual_scores,
                            "predicted_score": score.predicted_scores,
                            "danger_level": score.danger_level,
                            "delta_percentage": score.delta_percentage,
                            "class_liter": grade.grade,
                        })
            
            if student_info_list:
                class_data.append({
                    "curator_name": grade.curator_name,
                    "subject_name": subject_name,
                    "grade_liter": grade.grade,
                    "class": student_info_list
                })
        
        if not class_data:
            class_data = []

        return {"filtered_class_data": class_data}

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="An error occurred while fetching class data")

@router.get("/all", response_model=List[dict])
async def get_all_grades(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get information about all grades/classes (filtered by user role)"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Get allowed grade IDs for role-based filtering
    allowed_grade_ids = get_user_allowed_grade_ids(user_data, db)
    
    # Build query with optional filtering
    grades_query = db.query(GradeInDB)
    if allowed_grade_ids is not None:  # Not admin
        if not allowed_grade_ids:  # Empty set - no access
            return []
        grades_query = grades_query.filter(GradeInDB.id.in_(allowed_grade_ids))
    
    grades = grades_query.all()
    
    result = []
    for grade in grades:
        # Count actual students in this grade
        actual_student_count = db.query(func.count(StudentInDB.id)).filter(StudentInDB.grade_id == grade.id).scalar()
        
        # Get curator information if assigned
        curator_info = None
        if grade.curator_id:
            curator = db.query(UserInDB).filter(UserInDB.id == grade.curator_id).first()
            if curator:
                curator_info = {
                    "id": curator.id,
                    "name": curator.name,
                    "first_name": curator.first_name,
                    "last_name": curator.last_name,
                    "email": curator.email,
                    "shanyrak": curator.shanyrak
                }
        
        result.append({
            "id": grade.id,
            "grade": grade.grade,
            "parallel": grade.parallel,
            "curator_id": grade.curator_id,
            "curator_name": grade.curator_name,
            "student_count": grade.student_count,
            "actual_student_count": actual_student_count,
            "curator_info": curator_info
        })
    
    return result

@router.get("/curators", response_model=List[dict])
async def get_available_curators(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get list of users who can be assigned as curators"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    curators = db.query(UserInDB).filter(
        UserInDB.type.in_(['curator', 'admin']),
        UserInDB.is_active == 1
    ).all()
    
    result = []
    for curator in curators:
        # Count how many grades this curator is assigned to
        grade_count = db.query(GradeInDB).filter(
            GradeInDB.curator_id == curator.id
        ).count()
        
        result.append({
            "id": curator.id,
            "name": curator.name,
            "first_name": curator.first_name,
            "last_name": curator.last_name,
            "email": curator.email,
            "type": curator.type,
            "shanyrak": curator.shanyrak,
            "assigned_grades_count": grade_count
        })
    
    return result

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_grade(
    record: CreateGrade,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Create a new grade/class"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create classes")
    
    existing = db.query(GradeInDB).filter(GradeInDB.grade == record.grade).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Класс '{record.grade}' уже существует"
        )
    
    # Resolve current user (creator) id
    creator_user = db.query(UserInDB).filter(UserInDB.email == user_data.get("sub")).first()
    if not creator_user:
        # fallback to id from token if present
        creator_id = user_data.get("id")
    else:
        creator_id = creator_user.id

    # Validate curator if provided
    curator_name = None
    if record.curator_id:
        curator = db.query(UserInDB).filter(
            UserInDB.id == record.curator_id,
            UserInDB.type.in_(['curator', 'admin']),
            UserInDB.is_active == 1
        ).first()
        if not curator:
            raise HTTPException(status_code=404, detail="Curator not found or not valid")
        curator_name = curator.name
    
    db_grade = GradeInDB(
        grade=record.grade,
        parallel=record.parallel,
        curator_id=record.curator_id,
        curator_name=curator_name or record.curator_name,
        student_count=record.student_count or 0,
        user_id=creator_id
    )
    
    db.add(db_grade)
    db.commit()
    db.refresh(db_grade)
    
    return {"id": db_grade.id, "message": "Grade created successfully"}

@router.get("/subjects", response_model=List[str])
async def get_subjects(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get list of all unique subjects"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    subjects = db.query(SubjectInDB.name).filter(SubjectInDB.is_active == 1).all()
    subject_list = [s[0] for s in subjects if s[0] is not None]
    
    if not subject_list:
        scores_subjects = db.query(ScoresInDB.subject_name).distinct().all()
        subject_list = [s[0] for s in scores_subjects if s[0] is not None]
    
    return sorted(subject_list)

@router.get("/parallels", response_model=List[str])
async def get_parallels(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get list of all unique parallels/grades"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Get unique grades from grades table
    parallels = db.query(GradeInDB.grade).distinct().all()
    parallel_list = [parallel[0] for parallel in parallels if parallel[0] is not None]
    
    return parallel_list

def enrich_student_data(student: StudentInDB, db: Session, subject: Optional[str] = None):
    average_percentage = None
    predicted_average = None
    danger_level = None
    delta_percentage = None
    subject_name = "Все" if not subject else subject
    semester = None
    actual_scores = []
    predicted_scores = []
    previous_class_score = None
    score_id = None

    if subject:
        # Fetch specific subject score
        score = db.query(ScoresInDB).filter(
            ScoresInDB.student_id == student.id,
            ScoresInDB.subject_name == subject
        ).first()

        if score:
            score_id = score.id
            actual_scores = score.actual_scores or []
            predicted_scores = score.predicted_scores or []
            previous_class_score = score.previous_class_score
            delta_percentage = score.delta_percentage
            danger_level = score.danger_level
            subject_name = score.subject_name
            semester = score.semester

            # Calculate averages for this subject
            valid_actual_scores = []
            if isinstance(actual_scores, list):
                valid_actual_scores = [s for s in actual_scores if s is not None and s > 0]
                if valid_actual_scores:
                    average_percentage = round(sum(valid_actual_scores) / len(valid_actual_scores), 1)
            
            if isinstance(predicted_scores, list):
                    num_completed = len(valid_actual_scores)
                    if num_completed > 0 and len(predicted_scores) >= num_completed:
                        predicted_average = round(sum(predicted_scores[:num_completed]) / num_completed, 1)
                    elif predicted_scores:
                        predicted_average = round(sum(predicted_scores) / len(predicted_scores), 1)
    else:
        # Aggregated logic
        all_scores = db.query(ScoresInDB).filter(
            ScoresInDB.student_id == student.id
        ).all()

        all_valid_scores = []
        overall_danger_level = 0
        danger_count = 0
        
        for score in all_scores:
            if score.actual_scores and isinstance(score.actual_scores, list):
                valid_scores = [s for s in score.actual_scores if s is not None and s > 0]
                all_valid_scores.extend(valid_scores)
            
            if score.danger_level is not None:
                overall_danger_level += score.danger_level
                danger_count += 1
        
        if all_valid_scores:
            average_percentage = round(sum(all_valid_scores) / len(all_valid_scores), 1)
        
        if danger_count > 0:
            danger_level = round(overall_danger_level / danger_count)

        # Get latest score for displaying 'last_subject' if no subject filter is applied
        latest_score = db.query(ScoresInDB).filter(
            ScoresInDB.student_id == student.id
        ).order_by(ScoresInDB.updated_at.desc()).first()
        
        if latest_score:
            subject_name = latest_score.subject_name
            semester = latest_score.semester

    return {
        "id": student.id,
        "name": student.name,
        "email": student.email,
        "grade_id": student.grade_id,
        "previous_class_score": previous_class_score,
        "actual_scores": actual_scores,
        "predicted_scores": predicted_scores,
        "avg_percentage": average_percentage,
        "predicted_avg": predicted_average,
        "danger_level": danger_level,
        "delta_percentage": delta_percentage,
        "last_subject": subject_name,
        "last_semester": semester,
        "score_id": score_id
    }

@router.get("/students-list")
async def get_students_unified(
    grade_id: Optional[int] = Query(None),
    parallel: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid token")

    allowed_grade_ids = get_user_allowed_grade_ids(user_data, db)
    
    query = db.query(StudentInDB).join(GradeInDB)
    
    if allowed_grade_ids is not None:
        query = query.filter(GradeInDB.id.in_(allowed_grade_ids))
        
    if grade_id:
        query = query.filter(StudentInDB.grade_id == grade_id)
    elif parallel:
         # Filter by parallel
         query = query.filter(
             (GradeInDB.grade == parallel) | 
             (GradeInDB.grade.like(f"{parallel} %")) | 
             (GradeInDB.grade.like(f"{parallel}_%"))
        )
    
    students = query.all()
    
    if subject:
        return [enrich_student_data(student, db, subject) for student in students]
    
    summary = []
    details = []
    for student in students:
        # Summary row (aggregated)
        summary.append(enrich_student_data(student, db, None))
        
        # Detail rows (one per subject)
        student_scores = db.query(ScoresInDB.subject_name).filter(
            ScoresInDB.student_id == student.id
        ).distinct().all()
        
        for (subj_name,) in student_scores:
            if subj_name:
                details.append(enrich_student_data(student, db, subj_name))
    
    return {
        "summary": summary,
        "details": details
    }

@router.get("/{grade_id}/subjects", response_model=List[str])
async def get_grade_subjects(
    grade_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get all subjects available in the system"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check access
    if not check_grade_access(user_data, grade_id, db):
        raise HTTPException(status_code=403, detail="Access denied")

    # Return ALL subjects from the system if available
    subjects = db.query(SubjectInDB.name).filter(SubjectInDB.is_active == 1).all()
    if subjects:
        return [s[0] for s in subjects]

    # Fallback to distinct subjects for this grade via students -> scores
    subjects_fallback = db.query(ScoresInDB.subject_name).distinct() \
        .join(StudentInDB, StudentInDB.id == ScoresInDB.student_id) \
        .filter(StudentInDB.grade_id == grade_id) \
        .filter(ScoresInDB.subject_name.isnot(None)) \
        .all()
    
    return [s[0] for s in subjects_fallback]

@router.get("/students/{grade_id}", response_model=List[dict])
async def get_students_by_grade(
    grade_id: int,
    subject: Optional[str] = Query(None),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get all students in a specific grade with optional subject filtering"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check role-based access
    if not check_grade_access(user_data, grade_id, db):
        raise HTTPException(status_code=403, detail="You don't have access to this grade")
    
    grade = db.query(GradeInDB).filter(GradeInDB.id == grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    
    students = db.query(StudentInDB).filter(StudentInDB.grade_id == grade_id).all()

    return [enrich_student_data(student, db, subject) for student in students]

@router.get("/template")
async def download_excel_template(
    token: str = Depends(oauth2_scheme)
):
    """Download Excel template for grade upload"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Allow both admin and teacher to download template
    if user_data.get("type") not in ["admin", "teacher"]:
        raise HTTPException(status_code=403, detail="Only admins and teachers can download template")
    
    try:
        template_content = generate_excel_template()
        
        return Response(
            content=template_content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=grades_template.xlsx"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating template: {str(e)}")

@router.get("/{grade_id}", response_model=dict)
async def get_grade_by_id(
    grade_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get a grade/class by ID"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check role-based access
    if not check_grade_access(user_data, grade_id, db):
        raise HTTPException(status_code=403, detail="You don't have access to this grade")
    
    grade = db.query(GradeInDB).filter(GradeInDB.id == grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    
    # Get curator information if assigned
    curator_info = None
    if grade.curator_id:
        curator = db.query(UserInDB).filter(UserInDB.id == grade.curator_id).first()
        if curator:
            curator_info = {
                "id": curator.id,
                "name": curator.name,
                "first_name": curator.first_name,
                "last_name": curator.last_name,
                "email": curator.email,
                "shanyrak": curator.shanyrak
            }
            
    # Count actual students
    actual_student_count = db.query(func.count(StudentInDB.id)).filter(StudentInDB.grade_id == grade.id).scalar()
    
    return {
        "id": grade.id,
        "grade": grade.grade,
        "parallel": grade.parallel,
        "curator_id": grade.curator_id,
        "curator_name": grade.curator_name,
        "student_count": grade.student_count,
        "actual_student_count": actual_student_count,
        "curator_info": curator_info,
        "created_at": grade.created_at,
        "updated_at": grade.updated_at,
        "user_id": grade.user_id
    }

@router.put("/{grade_id}", status_code=status.HTTP_200_OK)
async def update_grade(
    grade_id: int,
    update_data: UpdateGrade,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Update a grade/class by ID"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can update classes")
    
    grade = db.query(GradeInDB).filter(GradeInDB.id == grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    
    # Update only the fields that are provided
    update_dict = update_data.dict(exclude_unset=True)
    
    # Специальная обработка для studentCount -> student_count
    if "studentCount" in update_dict:
        grade.student_count = update_dict.pop("studentCount")
    
    for key, value in update_dict.items():
        # Проверяем, что мы обновляем только существующие атрибуты
        if hasattr(grade, key):
                setattr(grade, key, value)
        else:
            print(f"Warning: Grade has no attribute {key}")
    
    db.commit()
    db.refresh(grade)
    
    print("Updated grade data:", {
        "id": grade.id,
        "grade": grade.grade,
        "parallel": grade.parallel,
        "curator_name": grade.curator_name,
        "student_count": grade.student_count
    })
    
    return {"message": "Grade updated successfully"}

@router.delete("/{grade_id}", status_code=status.HTTP_200_OK)
async def delete_grade(
    grade_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Delete a grade/class by ID"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete classes")
    
    grade = db.query(GradeInDB).filter(GradeInDB.id == grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    
    # Delete the grade
    db.delete(grade)
    db.commit()
    
    return {"message": "Grade deleted successfully"}

@router.put("/{grade_id}/student-count", status_code=status.HTTP_200_OK)
async def update_student_count(
    grade_id: int,
    student_count: int = Body(..., embed=True),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Update student count for a grade/class"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can update classes")
    
    grade = db.query(GradeInDB).filter(GradeInDB.id == grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    
    # Update student count
    grade.student_count = student_count
    
    db.commit()
    db.refresh(grade)
    
    return {
        "message": "Student count updated successfully",
        "grade": grade.grade,
        "studentCount": grade.studentcount
    }

@router.put("/students/{student_id}", status_code=status.HTTP_200_OK)
async def update_student(
    student_id: int,
    update_data: UpdateStudent,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Update a student by ID"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can update students")
    
    student = db.query(StudentInDB).filter(StudentInDB.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # Update only the fields that are provided
    update_dict = update_data.dict(exclude_unset=True)
    for key, value in update_dict.items():
        if hasattr(student, key):
            setattr(student, key, value)
    
    db.commit()
    db.refresh(student)
    
    return {
        "message": "Student updated successfully",
        "student": {
            "id": student.id,
            "name": student.name,
            "email": student.email,
            "student_id_number": student.student_id_number,
            "phone": student.phone,
            "parent_contact": student.parent_contact,
            "grade_id": student.grade_id,
            "is_active": student.is_active
        }
    }

@router.delete("/students/{student_id}", status_code=status.HTTP_200_OK)
async def delete_student(
    student_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Delete a student by ID"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete students")
    
    student = db.query(StudentInDB).filter(StudentInDB.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # Delete associated scores first
    db.query(ScoresInDB).filter(ScoresInDB.student_id == student_id).delete()
    
    # Delete the student
    db.delete(student)
    db.commit()
    
    return {"message": "Student deleted successfully"}

@router.get("/debug/students-grades", response_model=dict)
async def debug_students_grades(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Debug endpoint to check student-grade relationships"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Get all grades with their student counts
    grades = db.query(GradeInDB).all()
    grades_info = []
    for grade in grades:
        student_count = db.query(func.count(StudentInDB.id)).filter(StudentInDB.grade_id == grade.id).scalar()
        grades_info.append({
            "id": grade.id,
            "grade": grade.grade,
            "parallel": grade.parallel,
            "student_count_in_db": student_count,
            "student_count_field": grade.student_count
        })
    
    # Get all students with their grade_ids
    students = db.query(StudentInDB).all()
    students_info = []
    for student in students:
        grade_exists = db.query(GradeInDB).filter(GradeInDB.id == student.grade_id).first()
        students_info.append({
            "id": student.id,
            "name": student.name,
            "grade_id": student.grade_id,
            "grade_exists": grade_exists is not None,
            "grade_name": grade_exists.grade if grade_exists else None
        })
    
    # Find orphan students (students with grade_id that doesn't exist)
    orphan_students = [s for s in students_info if not s["grade_exists"]]
    
    return {
        "total_grades": len(grades_info),
        "total_students": len(students_info),
        "orphan_students_count": len(orphan_students),
        "grades": grades_info,
        "students_sample": students_info[:20],  # First 20 students
        "orphan_students": orphan_students
    }






@router.post("/students/", status_code=status.HTTP_201_CREATED)
async def create_student(
    student_data: CreateStudent,
    grade_id: int = Body(...),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Create a new student in a specific grade"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create students")
    
    # Check if grade exists
    grade = db.query(GradeInDB).filter(GradeInDB.id == grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    
    # Check if student with this name already exists in this grade
    existing_student = db.query(StudentInDB).filter(
        StudentInDB.name == student_data.name,
        StudentInDB.grade_id == grade_id
    ).first()
    
    if existing_student:
        raise HTTPException(status_code=400, detail="Student with this name already exists in this grade")
    
    # Create new student
    db_student = StudentInDB(
        name=student_data.name,
        email=student_data.email,
        grade_id=grade_id
    )
    
    db.add(db_student)
    db.commit()
    db.refresh(db_student)
    
    return {
        "id": db_student.id,
        "message": "Student created successfully",
        "student": {
            "id": db_student.id,
            "name": db_student.name,
            "email": db_student.email,
            "grade_id": db_student.grade_id
        }
    }

@router.get("/student/{student_id}", response_model=dict)
async def get_student_by_id(
    student_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get a student by ID"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    student = db.query(StudentInDB).filter(StudentInDB.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
        
    return {
        "id": student.id,
        "name": student.name,
        "email": student.email,
        "student_id_number": student.student_id_number,
        "phone": student.phone,
        "parent_contact": student.parent_contact,
        "grade_id": student.grade_id,
        "subgroup_id": student.subgroup_id,
        "is_active": student.is_active,
        "created_at": student.created_at,
        "updated_at": student.updated_at
    }

@router.get("/student/{student_id}/scores", response_model=List[dict])
async def get_student_scores(
    student_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get scores for a specific student"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
        
    student = db.query(StudentInDB).filter(StudentInDB.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
        
    scores = db.query(ScoresInDB).filter(ScoresInDB.student_id == student_id).all()
    
    result = []
    for score in scores:
        result.append({
            "id": score.id,
            "teacher_name": score.teacher_name,
            "subject_name": score.subject_name,
            "actual_scores": score.actual_scores,
            "predicted_scores": score.predicted_scores,
            "danger_level": score.danger_level,
            "delta_percentage": score.delta_percentage,
            "semester": score.semester,
            "academic_year": score.academic_year,
            "created_at": score.created_at,
            "updated_at": score.updated_at,
            "student_id": score.student_id,
            "grade_id": score.grade_id,
            "previous_class_score": score.previous_class_score
        })
        
    return result

@router.put("/scores/{score_id}", status_code=status.HTTP_200_OK)
async def update_score(
    score_id: int,
    update_data: UpdateScore,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Update a score by ID - for admins or assigned teachers"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    score = db.query(ScoresInDB).filter(ScoresInDB.id == score_id).first()
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")
    
    user_type = user_data.get("type")
    user_email = user_data.get("sub")
    
    # Get user_id from email
    user = db.query(UserInDB).filter(UserInDB.email == user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check permissions
    if user_type == "admin":
        # Admins can edit any score
        pass
    elif user_type == "teacher":
        # Teachers can only edit scores for their assigned subjects/groups
        assignment = db.query(TeacherAssignmentInDB).filter(
            TeacherAssignmentInDB.teacher_id == user.id,
            TeacherAssignmentInDB.subject_id == score.subject_id,
            TeacherAssignmentInDB.is_active == 1,
            or_(
                TeacherAssignmentInDB.grade_id == score.grade_id,
                TeacherAssignmentInDB.grade_id == None
            )
        ).first()
        
        if not assignment:
            # Check if they have subgroup assignment
            if score.subgroup_id:
                assignment = db.query(TeacherAssignmentInDB).filter(
                    TeacherAssignmentInDB.teacher_id == user.id,
                    TeacherAssignmentInDB.subject_id == score.subject_id,
                    TeacherAssignmentInDB.subgroup_id == score.subgroup_id,
                    TeacherAssignmentInDB.is_active == 1
                ).first()
        
        if not assignment:
            raise HTTPException(status_code=403, detail="You don't have permission to edit this score")
    else:
        raise HTTPException(status_code=403, detail="Only admins and teachers can edit scores")
    
    # Update only provided fields
    update_dict = update_data.dict(exclude_unset=True)
    
    # Handle actual_scores format conversion (dict to list)
    if 'actual_scores' in update_dict and update_dict['actual_scores']:
        scores_data = update_dict['actual_scores']
        if isinstance(scores_data, dict):
            # Convert dict {q1: val, q2: val, ...} to list [val, val, ...]
            scores_list = []
            for i in range(1, 5):
                key = f'q{i}'
                val = scores_data.get(key, 0)
                scores_list.append(float(val) if val is not None else 0.0)
            update_dict['actual_scores'] = scores_list
    
    for key, value in update_dict.items():
        if hasattr(score, key):
            setattr(score, key, value)
    
    # Recalculate danger level if actual_scores changed
    if 'actual_scores' in update_dict and score.actual_scores:
        actual = score.actual_scores
        predicted = score.predicted_scores or []
        
        # Calculate average of actual scores (now it's a list)
        if isinstance(actual, list):
            actual_values = [v for v in actual if isinstance(v, (int, float)) and v > 0]
        else:
            actual_values = [v for v in actual.values() if isinstance(v, (int, float)) and v > 0]
        
        if isinstance(predicted, list):
            predicted_values = [v for v in predicted if isinstance(v, (int, float)) and v > 0]
        else:
            predicted_values = [v for v in predicted.values() if isinstance(v, (int, float)) and v > 0]
        
        if actual_values:
            avg_actual = sum(actual_values) / len(actual_values)
            avg_predicted = sum(predicted_values) / len(predicted_values) if predicted_values else avg_actual
            
            delta = avg_actual - avg_predicted
            score.delta_percentage = round(delta, 2)
            
            # Calculate danger level based on delta
            if delta >= -5:
                score.danger_level = 0  # Low risk
            elif delta >= -15:
                score.danger_level = 1  # Moderate risk
            elif delta >= -25:
                score.danger_level = 2  # High risk
            else:
                score.danger_level = 3  # Critical
    
    db.commit()
    db.refresh(score)
    
    return {
        "message": "Score updated successfully",
        "score": {
            "id": score.id,
            "teacher_name": score.teacher_name,
            "subject_name": score.subject_name,
            "actual_scores": score.actual_scores,
            "predicted_scores": score.predicted_scores,
            "danger_level": score.danger_level,
            "delta_percentage": score.delta_percentage,
            "student_id": score.student_id,
            "grade_id": score.grade_id
        }
    }

@router.post("/scores", status_code=status.HTTP_201_CREATED)
async def create_score(
    student_id: int = Body(...),
    subject_id: int = Body(...),
    actual_scores: dict = Body(default=None),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Create a new score record for a student - for admins or assigned teachers"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Get student
    student = db.query(StudentInDB).filter(StudentInDB.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # Get subject
    subject = db.query(SubjectInDB).filter(SubjectInDB.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    user_type = user_data.get("type")
    user_email = user_data.get("sub")
    
    # Get user_id from email
    user = db.query(UserInDB).filter(UserInDB.email == user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check permissions
    if user_type == "admin":
        # Admins can create any score
        teacher_name = user.name or user.email
    elif user_type == "teacher":
        # Teachers can only create scores for their assigned subjects/groups
        assignment = db.query(TeacherAssignmentInDB).filter(
            TeacherAssignmentInDB.teacher_id == user.id,
            TeacherAssignmentInDB.subject_id == subject_id,
            TeacherAssignmentInDB.is_active == 1,
            or_(
                TeacherAssignmentInDB.grade_id == student.grade_id,
                TeacherAssignmentInDB.grade_id == None
            )
        ).first()
        
        if not assignment:
            raise HTTPException(status_code=403, detail="You don't have permission to create scores for this student/subject")
        
        teacher_name = user.name or user.email
    else:
        raise HTTPException(status_code=403, detail="Only admins and teachers can create scores")
    
    # Check if score already exists
    existing_score = db.query(ScoresInDB).filter(
        ScoresInDB.student_id == student_id,
        ScoresInDB.subject_id == subject_id,
        ScoresInDB.grade_id == student.grade_id
    ).first()
    
    if existing_score:
        # If score exists, update it instead of creating new
        scores_list = [0.0, 0.0, 0.0, 0.0]
        if actual_scores:
            for i in range(1, 5):
                key = f'q{i}'
                val = actual_scores.get(key, 0)
                scores_list[i-1] = float(val) if val is not None else 0.0
        
        existing_score.actual_scores = scores_list
        existing_score.teacher_name = teacher_name
        db.commit()
        db.refresh(existing_score)
        
        return {
            "message": "Score updated successfully",
            "score": {
                "id": existing_score.id,
                "teacher_name": existing_score.teacher_name,
                "subject_name": existing_score.subject_name,
                "actual_scores": existing_score.actual_scores,
                "predicted_scores": existing_score.predicted_scores,
                "danger_level": existing_score.danger_level,
                "delta_percentage": existing_score.delta_percentage,
                "student_id": existing_score.student_id,
                "grade_id": existing_score.grade_id,
                "subject_id": existing_score.subject_id
            }
        }
    
    # Convert actual_scores dict to list
    scores_list = [0.0, 0.0, 0.0, 0.0]
    if actual_scores:
        for i in range(1, 5):
            key = f'q{i}'
            val = actual_scores.get(key, 0)
            scores_list[i-1] = float(val) if val is not None else 0.0
    
    # Create new score
    new_score = ScoresInDB(
        teacher_name=teacher_name,
        subject_name=subject.name,
        subject_id=subject_id,
        student_id=student_id,
        grade_id=student.grade_id,
        actual_scores=scores_list,
        predicted_scores=[0.0, 0.0, 0.0, 0.0],
        danger_level=0,
        delta_percentage=0.0,
        semester=1,
        academic_year="2024-2025"
    )
    
    db.add(new_score)
    db.commit()
    db.refresh(new_score)
    
    return {
        "message": "Score created successfully",
        "score": {
            "id": new_score.id,
            "teacher_name": new_score.teacher_name,
            "subject_name": new_score.subject_name,
            "actual_scores": new_score.actual_scores,
            "predicted_scores": new_score.predicted_scores,
            "danger_level": new_score.danger_level,
            "delta_percentage": new_score.delta_percentage,
            "student_id": new_score.student_id,
            "grade_id": new_score.grade_id,
            "subject_id": new_score.subject_id
        }
    }

@router.get("/teacher/my-assignments")
async def get_teacher_assignments(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get assignments for the current teacher"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    user_email = user_data.get("sub")
    user_type = user_data.get("type")
    
    if user_type not in ["teacher", "admin"]:
        raise HTTPException(status_code=403, detail="Only teachers can access this endpoint")
    
    # Get user_id from email
    user = db.query(UserInDB).filter(UserInDB.email == user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    assignments = db.query(TeacherAssignmentInDB).filter(
        TeacherAssignmentInDB.teacher_id == user.id,
        TeacherAssignmentInDB.is_active == 1
    ).all()
    
    result = []
    for assignment in assignments:
        subject = db.query(SubjectInDB).filter(SubjectInDB.id == assignment.subject_id).first()
        grade = db.query(GradeInDB).filter(GradeInDB.id == assignment.grade_id).first() if assignment.grade_id else None
        subgroup = db.query(SubgroupInDB).filter(SubgroupInDB.id == assignment.subgroup_id).first() if assignment.subgroup_id else None
        
        result.append({
            "id": assignment.id,
            "subject_id": assignment.subject_id,
            "subject_name": subject.name if subject else None,
            "grade_id": assignment.grade_id,
            "grade_name": grade.grade if grade else "Все классы",
            "subgroup_id": assignment.subgroup_id,
            "subgroup_name": subgroup.name if subgroup else None
        })
    
    return result

@router.get("/teacher/students")
async def get_teacher_students(
    subject_id: int = Query(...),
    grade_id: Optional[int] = Query(None),
    subgroup_id: Optional[int] = Query(None),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get students that a teacher can grade for a specific subject/grade/subgroup"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    user_email = user_data.get("sub")
    user_type = user_data.get("type")
    
    # Get user_id from email
    user = db.query(UserInDB).filter(UserInDB.email == user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if teacher has assignment for this subject/grade/subgroup
    if user_type == "teacher":
        assignment_query = db.query(TeacherAssignmentInDB).filter(
            TeacherAssignmentInDB.teacher_id == user.id,
            TeacherAssignmentInDB.subject_id == subject_id,
            TeacherAssignmentInDB.is_active == 1
        )
        
        if grade_id:
            assignment_query = assignment_query.filter(
                or_(
                    TeacherAssignmentInDB.grade_id == grade_id,
                    TeacherAssignmentInDB.grade_id == None
                )
            )
        
        if subgroup_id:
            assignment_query = assignment_query.filter(
                or_(
                    TeacherAssignmentInDB.subgroup_id == subgroup_id,
                    TeacherAssignmentInDB.subgroup_id == None
                )
            )
        
        assignment = assignment_query.first()
        if not assignment:
            raise HTTPException(status_code=403, detail="You don't have permission to view these students")
    elif user_type != "admin":
        raise HTTPException(status_code=403, detail="Only teachers and admins can access this endpoint")
    
    # Get students based on filters
    student_query = db.query(StudentInDB).filter(StudentInDB.is_active == 1)
    
    if grade_id:
        student_query = student_query.filter(StudentInDB.grade_id == grade_id)
    
    if subgroup_id:
        student_query = student_query.filter(StudentInDB.subgroup_id == subgroup_id)
    
    students = student_query.all()
    
    # Get subject info
    subject = db.query(SubjectInDB).filter(SubjectInDB.id == subject_id).first()
    
    result = []
    for student in students:
        # Get existing score for this student and subject
        score = db.query(ScoresInDB).filter(
            ScoresInDB.student_id == student.id,
            ScoresInDB.subject_id == subject_id
        ).first()
        
        grade = db.query(GradeInDB).filter(GradeInDB.id == student.grade_id).first()
        
        result.append({
            "id": student.id,
            "name": student.name,
            "grade_id": student.grade_id,
            "grade_name": grade.grade if grade else None,
            "subgroup_id": student.subgroup_id,
            "score_id": score.id if score else None,
            "actual_scores": score.actual_scores if score else None,
            "predicted_scores": score.predicted_scores if score else None,
            "danger_level": score.danger_level if score else None,
            "subject_name": subject.name if subject else None
        })
    
    return result

@router.post("/upload", response_model=ExcelUploadResponse)
async def upload_excel_grades(
    grade_id: int = Form(...),
    subject_id: int = Form(...),
    teacher_name: str = Form(...),
    semester: int = Form(1),
    subgroup_id: Optional[int] = Form(None),
    file: UploadFile = File(...),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """
    Upload Excel file with student grades
    Requires: grade_id, subject_id, teacher_name, file
    Optional: semester (default 1), subgroup_id
    """
    try:
        # Verify access (admin or teacher)
        user_data = verify_access_token(token)
        if not user_data:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        user_type = user_data.get("type")
        user_email = user_data.get("sub")
        
        if user_type not in ["admin", "teacher"]:
            raise HTTPException(status_code=403, detail="Only admins and teachers can upload grades")
        
        # Get user_id for teacher permission check
        user = db.query(UserInDB).filter(UserInDB.email == user_email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # If teacher, check if they have assignment for this subject/grade
        if user_type == "teacher":
            assignment = db.query(TeacherAssignmentInDB).filter(
                TeacherAssignmentInDB.teacher_id == user.id,
                TeacherAssignmentInDB.subject_id == subject_id,
                TeacherAssignmentInDB.is_active == 1,
                or_(
                    TeacherAssignmentInDB.grade_id == grade_id,
                    TeacherAssignmentInDB.grade_id == None
                )
            ).first()
            
            if not assignment:
                raise HTTPException(
                    status_code=403, 
                    detail="You don't have permission to upload grades for this subject and class"
                )
        
        # Validate file type
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            raise HTTPException(status_code=400, detail="Only Excel files (.xlsx, .xls) are allowed")
        
        # Validate grade exists
        grade = db.query(GradeInDB).filter(GradeInDB.id == grade_id).first()
        if not grade:
            raise HTTPException(status_code=404, detail="Grade not found")
        
        # Validate subject exists
        subject = db.query(SubjectInDB).filter(SubjectInDB.id == subject_id).first()
        if not subject:
            raise HTTPException(status_code=404, detail="Subject not found")

        # Validate subject applicable for grade parallel
        try:
            grade_parallel_int = int(grade.parallel)
        except Exception:
            grade_parallel_int = None
        if grade_parallel_int is not None:
            applicable = subject.applicable_parallels or []
            if len(applicable) > 0 and grade_parallel_int not in applicable:
                raise HTTPException(status_code=400, detail=f"Subject '{subject.name}' is not applicable for parallel {grade.parallel}")
        
        # Validate subgroup if provided
        subgroup = None
        if subgroup_id:
            subgroup = db.query(SubgroupInDB).filter(
                SubgroupInDB.id == subgroup_id,
                SubgroupInDB.grade_id == grade_id
            ).first()
            if not subgroup:
                raise HTTPException(status_code=404, detail="Subgroup not found or doesn't belong to the specified grade")
        
        # Load prediction weights from database
        prediction_settings = db.query(PredictionSettings).filter(
            PredictionSettings.is_active == 1
        ).first()
        
        weights = {
            'previous_class': 0.3,
            'teacher': 0.2,
            'quarters': 0.5
        }
        if prediction_settings and prediction_settings.weights:
            weights = prediction_settings.weights
        
        # Load Excel column mappings from database
        column_mappings = db.query(ExcelColumnMapping).filter(
            ExcelColumnMapping.is_active == 1
        ).all()
        
        expected_columns = {
            'name': ['фио', 'имя', 'name', 'student', 'студент', 'ученик'],
            'previous_class': ['процент за 1 предыдущий класс', 'previous class', 'previous year', 'предыдущий класс', 'предыдущий год', 'prev class'],
            'q1': ['q1', 'четверть 1', 'quarter 1', '1 четверть', 'ч1'],
            'q2': ['q2', 'четверть 2', 'quarter 2', '2 четверть', 'ч2'],
            'q3': ['q3', 'четверть 3', 'quarter 3', '3 четверть', 'ч3'],
            'q4': ['q4', 'четверть 4', 'quarter 4', '4 четверть', 'ч4'],
            'teacher': ['учитель', 'teacher', 'преподаватель', 'препод']
        }
        
        # Override with database mappings if available
        for mapping in column_mappings:
            if mapping.field_name in expected_columns and mapping.column_aliases:
                expected_columns[mapping.field_name] = mapping.column_aliases
        
        # Read and parse Excel file
        file_content = await file.read()
        parsed_data = parse_excel_grades(file_content, expected_columns, weights)
        
        # Process students data
        imported_count = 0
        warnings = parsed_data.get('warnings', [])
        errors = parsed_data.get('errors', [])
        danger_distribution = {0: 0, 1: 0, 2: 0, 3: 0}
        
        for student_data in parsed_data['students']:
            try:
                student_name = student_data["student_name"]
                actual_scores = student_data["actual_scores"]
                predicted_scores = student_data["predicted_scores"]
                previous_class_score = student_data.get("previous_class_score")
                
                # Calculate danger level correctly
                # Compare only completed quarters (where actual score is not None/0)
                
                actual_completed = [s for s in actual_scores if s is not None and s > 0]
                num_completed = len(actual_completed)
                
                danger_level = 0 # Default to Normal
                percentage_difference = 0.0

                if num_completed > 0 and len(predicted_scores) >= num_completed:
                    predicted_for_completed = predicted_scores[:num_completed]
                    
                    avg_actual = sum(actual_completed) / num_completed
                    avg_predicted = sum(predicted_for_completed) / num_completed
                    
                    delta = avg_actual - avg_predicted
                    
                    if delta < -15:
                        danger_level = 3  # Критический
                    elif delta < -10:
                        danger_level = 2  # Повышенный
                    elif delta < -5:
                        danger_level = 1  # Умеренный
                    else:
                        danger_level = 0 # Нормальный

                    # Also calculate a delta percentage for reference if needed
                    if avg_predicted > 0:
                        percentage_difference = (delta / avg_predicted) * 100

                danger_distribution[danger_level] += 1
                
                # Find or create student
                db_student = db.query(StudentInDB).filter(
                    StudentInDB.name == student_name,
                    StudentInDB.grade_id == grade_id
                ).first()
                
                if not db_student:
                    db_student = StudentInDB(
                        name=student_name,
                        grade_id=grade_id,
                        subgroup_id=subgroup_id
                    )
                    db.add(db_student)
                    db.commit()
                    db.refresh(db_student)
                else:
                    # Update subgroup if provided
                    if subgroup_id and db_student.subgroup_id != subgroup_id:
                        db_student.subgroup_id = subgroup_id
                
                # Find existing score record for this student/subject/semester
                db_score = db.query(ScoresInDB).filter(
                    ScoresInDB.student_id == db_student.id,
                    ScoresInDB.subject_id == subject_id,
                    ScoresInDB.semester == semester
                ).first()
                
                if db_score:
                    # Update existing record
                    db_score.teacher_name = teacher_name
                    db_score.subject_name = subject.name
                    db_score.previous_class_score = previous_class_score
                    db_score.actual_scores = actual_scores
                    db_score.predicted_scores = predicted_scores
                    db_score.danger_level = danger_level
                    db_score.delta_percentage = round(percentage_difference, 1)
                    db_score.grade_id = grade_id
                    db_score.subgroup_id = subgroup_id
                else:
                    # Create new record
                    new_score = ScoresInDB(
                        teacher_name=teacher_name,
                        subject_name=subject.name,
                        subject_id=subject_id,
                        previous_class_score=previous_class_score,
                        actual_scores=actual_scores,
                        predicted_scores=predicted_scores,
                        danger_level=danger_level,
                        delta_percentage=round(percentage_difference, 1),
                        semester=semester,
                        academic_year="2024-2025",  # TODO: Make this configurable
                        student_id=db_student.id,
                        grade_id=grade_id,
                        subgroup_id=subgroup_id
                    )
                    db.add(new_score)
                
                imported_count += 1
                
            except Exception as e:
                errors.append(f"Error processing student {student_data.get('student_name', 'Unknown')}: {str(e)}")
                continue
        
        db.commit()
        
        # Prepare response
        success = imported_count > 0
        message = f"Successfully imported {imported_count} student records"
        if warnings:
            message += f" with {len(warnings)} warnings"
        if errors:
            message += f" and {len(errors)} errors"
        
        return ExcelUploadResponse(
            success=success,
            message=message,
            imported_count=imported_count,
            warnings=warnings,
            errors=errors,
            danger_distribution={str(k): v for k, v in danger_distribution.items()}
        )
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred during upload: {str(e)}")


