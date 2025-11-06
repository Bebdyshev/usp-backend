from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from config import get_db
from schemas.models import *
from sqlalchemy import or_
from auth_utils import verify_access_token
from routes.auth import oauth2_scheme
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
        db_grade = db.query(GradeInDB).filter(GradeInDB.grade == grade, GradeInDB.curatorName == curator).first()

        if not db_grade:
            db_grade = GradeInDB(
                grade=grade, 
                curatorName=curator, 
                user_id=user.id,
                parallel=None,
                shanyrak=None,
                studentcount=0
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

            # Обновляем или создаем запись с оценками
            db_score = db.query(ScoresInDB).filter(ScoresInDB.student_id == db_student.id).first()
            if db_score:
                db_score.actual_scores = actual_score
                db_score.predicted_scores = predicted_scores
                db_score.danger_level = danger_level
                db_score.delta_percentage = round(percentage_difference, 1)
                db_score.subject_name = subject
            else:
                new_score = ScoresInDB(
                    subject_name=subject,
                    actual_scores=actual_score,
                    predicted_scores=predicted_scores,
                    danger_level=danger_level,
                    delta_percentage=round(percentage_difference, 1),
                    student_id=db_student.id,
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
def get_class_data(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        user_data = verify_access_token(token)  
        if not user_data:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        user = db.query(UserInDB).filter(UserInDB.email == user_data["sub"]).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        db_grades = db.query(GradeInDB).filter(GradeInDB.user_id == user.id).all()
        
        if not db_grades:
            raise HTTPException(status_code=404, detail="No grades found for the user")

        class_data = []
        
        for grade in db_grades:
            students = db.query(StudentInDB).filter(StudentInDB.grade_id == grade.id).all()
            student_info_list = []
            subject_name = None  # Инициализируем переменную
            
            for student in students:
                student_scores = db.query(ScoresInDB).filter(ScoresInDB.student_id == student.id).all()

                actual_scores = []
                predicted_scores = []
                previous_class_score = None
                teacher_percent = None
                danger_level = None
                delta_percentage = None

                for score in student_scores:
                    # Get the latest score record for this student
                    if score.actual_scores:
                        actual_scores = score.actual_scores if isinstance(score.actual_scores, list) else []
                    if score.predicted_scores:
                        predicted_scores = score.predicted_scores if isinstance(score.predicted_scores, list) else []
                    if score.previous_class_score is not None:
                        previous_class_score = score.previous_class_score
                    danger_level = score.danger_level  
                    delta_percentage = score.delta_percentage
                    subject_name = score.subject_name

                student_info_list.append({
                    "id": student.id,
                    "student_name": student.name,
                    "previous_class_score": previous_class_score,
                    "actual_scores": actual_scores,
                    "predicted_scores": predicted_scores,
                    "danger_level": danger_level,
                    "delta_percentage": delta_percentage,
                    "class_liter": grade.grade,  
                })
                
            class_data.append({
                "curator_name": grade.curator_name,
                "subject_name": subject_name,
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

        user = db.query(UserInDB).filter(UserInDB.email == user_data["sub"]).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Получаем все классы пользователя
        db_grades = db.query(GradeInDB).filter(GradeInDB.user_id == user.id).all()
        if not db_grades:
            raise HTTPException(status_code=404, detail="No grades found for the user")

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
                    "curator_name": grade.curatorName,
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
    """Get information about all grades/classes"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Get all grades
    grades = db.query(GradeInDB).all()
    
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
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create classes")
    
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
    
    # Специальная обработка для studentCount -> studentcount
    if "studentCount" in update_dict:
        grade.studentcount = update_dict.pop("studentCount")
    
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
        "curatorName": grade.curatorName,
        "shanyrak": grade.shanyrak,
        "studentcount": grade.studentcount
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
    grade.studentcount = student_count
    
    db.commit()
    db.refresh(grade)
    
    return {
        "message": "Student count updated successfully",
        "grade": grade.grade,
        "studentCount": grade.studentcount
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

@router.get("/subjects", response_model=List[str])
async def get_subjects(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get list of all unique subjects"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Get unique subjects from scores table
    subjects = db.query(ScoresInDB.subject_name).distinct().all()
    subject_list = [subject[0] for subject in subjects if subject[0] is not None]
    
    return subject_list

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

@router.get("/students/{grade_id}", response_model=List[dict])
async def get_students_by_grade(
    grade_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get all students in a specific grade"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    grade = db.query(GradeInDB).filter(GradeInDB.id == grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    
    students = db.query(StudentInDB).filter(StudentInDB.grade_id == grade_id).all()

    result = []
    for student in students:
        # Latest score entry for this student in this grade (any subject), by updated_at
        latest_score = db.query(ScoresInDB).filter(
            ScoresInDB.student_id == student.id,
            ScoresInDB.grade_id == grade_id
        ).order_by(ScoresInDB.updated_at.desc()).first()

        average_percentage = None
        predicted_average = None
        previous_class_score = None
        actual_scores = []
        predicted_scores = []
        danger_level = None
        delta_percentage = None
        subject_name = None
        semester = None

        if latest_score:
            try:
                actual_list = latest_score.actual_scores or []
                predicted_list = latest_score.predicted_scores or []
                if isinstance(actual_list, list):
                    actual_scores = actual_list
                    if len(actual_list) > 0:
                        average_percentage = round(sum(actual_list) / len(actual_list), 1)
                if isinstance(predicted_list, list):
                    predicted_scores = predicted_list
                    if len(predicted_list) > 0:
                        predicted_average = round(sum(predicted_list) / len(predicted_list), 1)
            except Exception:
                pass
            previous_class_score = latest_score.previous_class_score
            danger_level = latest_score.danger_level
            delta_percentage = latest_score.delta_percentage
            subject_name = latest_score.subject_name
            semester = latest_score.semester

        result.append({
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
        })
    
    return result

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
        # Verify admin access
        user_data = verify_access_token(token)
        if not user_data:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        if user_data.get("type") != "admin":
            raise HTTPException(status_code=403, detail="Only admins can upload grades")
        
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
                
                # Calculate danger level using existing logic
                # Compare only completed quarters (where actual score is not 0.0)
                valid_comparisons = []
                for i, (actual, predicted) in enumerate(zip(actual_scores, predicted_scores)):
                    # Only compare if we have actual data (not placeholder 0.0)
                    if actual > 0:
                        valid_comparisons.append(abs(actual - predicted))
                
                if valid_comparisons:
                    total_score_difference = sum(valid_comparisons)
                    avg_predicted = sum(predicted_scores[:len(valid_comparisons)]) / len(valid_comparisons) if valid_comparisons else 0
                    percentage_difference = (total_score_difference / max(avg_predicted * len(valid_comparisons), 1)) * 100
                else:
                    percentage_difference = 0
                
                # Determine danger_level (новая логика)
                # меньше 10% - умеренный (1)
                # 10-20% - повышенный (2)
                # больше 20% - критический (3)
                if percentage_difference < 10:
                    danger_level = 1
                elif 10 <= percentage_difference <= 20:
                    danger_level = 2
                else:
                    danger_level = 3
                
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

@router.get("/template")
async def download_excel_template(
    token: str = Depends(oauth2_scheme)
):
    """Download Excel template for grade upload"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can download template")
    
    try:
        template_content = generate_excel_template()
        
        from fastapi.responses import Response
        
        return Response(
            content=template_content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=grades_template.xlsx"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating template: {str(e)}")
