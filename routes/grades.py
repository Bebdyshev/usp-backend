from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body, Query
from sqlalchemy.orm import Session
from config import get_db
from schemas.models import *
from auth_utils import verify_access_token
from routes.auth import oauth2_scheme
import pandas as pd
from io import BytesIO, StringIO
from services.analyze import analyze_excel

router = APIRouter()

@router.post("/send/")
async def send_excel_as_csv_to_openai(
    grade: str = Form(...),
    curator: str = Form(...),
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
            db_grade = GradeInDB(grade=grade, curatorName=curator, user_id=user.id)
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

            # Ищем студента в БД
            db_student = db.query(StudentInDB).filter(StudentInDB.name == student_name).first()

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
            else:
                new_score = ScoresInDB(
                    subject_name=json_response.get("subject", "Неизвестный предмет"),
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

            for student in students:
                # Получаем записи с оценками для студента
                student_scores = db.query(ScoresInDB).filter(ScoresInDB.student_id == student.id).all()

                # Ищем студентов с уровнем опасности выше указанного
                for score in student_scores:
                    if score.danger_level == level:
                        student_info_list.append({
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
                    "subject_name": score.subject_name,
                    "grade_liter": grade.grade,
                    "class": student_info_list
                })
        
        if not class_data:
            raise HTTPException(status_code=404, detail="No students found with danger level greater than the specified value")

        return {"filtered_class_data": class_data}

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="An error occurred while fetching class data")
