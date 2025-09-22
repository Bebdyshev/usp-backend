from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from config import get_db
from schemas.models import *
from auth_utils import verify_access_token
from routes.auth import oauth2_scheme
import pandas as pd
from io import BytesIO, StringIO
from services.analyze import analyze_excel
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

            # Определяем danger_level
            if percentage_difference < 5:
                danger_level = 0  
            elif 5 <= percentage_difference <= 10:
                danger_level = 1  
            elif 10 < percentage_difference <= 15:
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

                actual_score = []
                teacher_score = []
                danger_level = None
                delta_percentage = None

                for score in student_scores:
                    actual_score.extend(score.actual_scores)
                    teacher_score.extend(score.predicted_scores)
                    danger_level = score.danger_level  
                    delta_percentage = score.delta_percentage
                    subject_name = score.subject_name

                student_info_list.append({
                    "id": student.id,
                    "student_name": student.name,
                    "actual_score": actual_score,
                    "predicted_score": teacher_score,
                    "danger_level": danger_level,
                    "delta_percentage": delta_percentage,
                    "class_liter": grade.grade,  
                })
                
            class_data.append({
                "curator_name": grade.curatorName,
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
        
        result.append({
            "id": grade.id,
            "grade": grade.grade,
            "parallel": grade.parallel,
            "curatorName": grade.curatorName,
            "shanyrak": grade.shanyrak,
            "studentCount": grade.studentcount,
            "actualStudentCount": actual_student_count
        })
    
    return result

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_grade(
    record: CreateRecord,
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
    
    db_grade = GradeInDB(
        grade=record.grade,
        parallel=record.parallel,
        curatorName=record.curatorName,
        shanyrak=record.shanyrak,
        studentcount=record.studentCount,
        user_id=user_data.get("id")
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
        result.append({
            "id": student.id,
            "name": student.name,
            "email": student.email,
            "grade_id": student.grade_id
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
