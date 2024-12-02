from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Body
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from models import *
from config import get_db, init_db
from auth_utils import hash_password, verify_password, create_access_token, verify_access_token
from fastapi.middleware.cors import CORSMiddleware
from datetime import timedelta
import httpx
import pandas as pd
import requests
from io import BytesIO, StringIO
import json
import os
from dotenv import load_dotenv
import numpy as np

load_dotenv()

app = FastAPI()

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_KEY = os.getenv("AZURE_API_KEY")

init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Or specify specific domains
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, DELETE, etc.)
    allow_headers=["*"],  # Allow all headers
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def analyze_excel(csv_text):
    # headers = {
    #         "Content-Type": "application/json",
    #         "api-key": AZURE_API_KEY
    # }
    # data = {
    #     "messages": [
    #         {
    #             "role": "system", 
    #             "content": "You are an assistant that processes CSV data and provides insights."
    #         },
    #         {
    #             "role": "user",
    #             "content": f"Here's the CSV data:\n{csv_text}\nYou should provide feedback in JSON format like this: \n[{{'student_name': 'student_name', 'actual_score': [1score, 2score, 3score, 4score, total_score], 'predicted_score': [1score, 2score, 3score, 4score, total_score]}}]\n. PLEASE ONLY RETURN JSON, DO NOT WRITE ANY OTHER WORDS. I NEED PLAIN TEXT."
    #         }
    #     ],
    #     "max_tokens": 500,
    #     "temperature": 0.5
    # }

    # response = requests.post(AZURE_OPENAI_ENDPOINT, headers=headers, json=data)
    # print(response)
    # if response.status_code != 200:
    #     raise HTTPException(status_code=response.status_code, detail=response.json())

    # gpt_response = response.json()["choices"][0]["message"]["content"].strip().replace("\n", "").replace('\\', "").replace("```json", "").replace("```", "")
    # print(gpt_response)

    #csv analyze

    df = pd.read_csv(StringIO(csv_text))

    result = []

    for index, row in df.iterrows():

        if row.isna().all():
            continue
        student_name = str(row[0]).split(',')[0].strip()  
        
        try:
            actual_scores = [None if pd.isna(score) else float(score) for score in row[1:5].tolist()]
        except ValueError:
            continue  

        try:
            predicted_scores = [None if pd.isna(score) else float(score) for score in row[5:9].tolist()]
        except ValueError:
            continue  
        actual_scores.append(0.0)
    
        predicted_scores.append(0.0)
        
        student_data = {
            "student_name": student_name,
            "actual_score": actual_scores,
            "predicted_score": predicted_scores
        }

        result.append(student_data)

    print(result)

    try:
        return result
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Error decoding GPT response.")

def replace_nan_with_zero(scores):
    return [score if score is not None else 0.0 for score in scores]

@app.post("/login/", response_model=Token)
def login_for_access_token(user: UserLogin, db: Session = Depends(get_db)) -> Token:
    db_user = db.query(UserInDB).filter(UserInDB.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.email, "role": db_user.doctor_type},  
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "role": db_user.doctor_type}

@app.post("/register/", response_model=Token)
def register_user(user: CreateUser, db: Session = Depends(get_db)) -> Token:
    db_user = db.query(UserInDB).filter(UserInDB.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = hash_password(user.password)
    new_user = UserInDB(email=user.email, hashed_password=hashed_password, name=user.name, doctor_type="default") 
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": new_user.email, "role": new_user.doctor_type}, 
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "role": new_user.doctor_type}

@app.delete("/users/", response_model=dict)
def delete_all_users(db: Session = Depends(get_db)):
    try:
        db.query(UserInDB).delete()
        db.commit()  
        return {"message": "All users deleted successfully."}
    except Exception as e:
        db.rollback() 
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/users/me")
def get_me(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = verify_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_email = payload.get("sub")
    user = db.query(UserInDB).filter(UserInDB.email == user_email).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.post("/send/")
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
        df = pd.read_excel(excel_data)
        csv_data = StringIO()
        df.to_csv(csv_data, index=False)
        csv_text = csv_data.getvalue()
        print("csv text:", csv_text)

        json_response = analyze_excel(csv_text)

        print(json_response)

        user = db.query(UserInDB).filter(UserInDB.email == user_data["sub"]).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        db_grade = db.query(GradeInDB).filter(GradeInDB.grade == grade, GradeInDB.curatorName == curator).first()

        if not db_grade:
            db_grade = GradeInDB(grade=grade, curatorName=curator, user_id=user.id)
            db.add(db_grade)
            db.commit()
            db.refresh(db_grade)

        print("pre for")
        for analysis_item in json_response:
            student_name = analysis_item["student_name"]
            print(student_name)
            actual_score = [score if score is not None else 0.0 for score in analysis_item['actual_score']]
            print(actual_score)
            predicted_scores = [score if score is not None else 0.0 for score in analysis_item['predicted_score']]
            print(predicted_scores)


            # Check lengths
            if len(actual_score) != len(predicted_scores):
                raise HTTPException(status_code=400, detail="Actual scores and predicted scores must have the same length.")

            # Calculate score differences, ensuring no NaN values
            score_differences = [abs(a - p) for a, p in zip(actual_score, predicted_scores)]  # Subtracting individual elements
            total_score_difference = sum(score_differences)

            total_predicted_score = sum(predicted_scores)
            percentage_difference = (total_score_difference / total_predicted_score * 100) if total_predicted_score != 0 else 0

            # Adjust danger level logic based on percentage difference
            if percentage_difference < 5:
                danger_level = 0  # White
            elif 5 <= percentage_difference <= 10:
                danger_level = 1  # Green
            elif 10 < percentage_difference <= 15:
                danger_level = 2  # Yellow
            else:
                danger_level = 3  # Red
            print('danger level', danger_level)

            db_student = db.query(StudentInDB).filter(StudentInDB.name == student_name).first()

            if not db_student:
                # Add grade_id to the new student
                db_student = StudentInDB(name=student_name, grade_id=db_grade.id)  # Assign grade_id
                db.add(db_student)
                db.commit()
                db.refresh(db_student)

            db_score = db.query(ScoresInDB).filter(ScoresInDB.student_id == db_student.id).first()
            print(actual_score, predicted_scores)
            if db_score:
                print("its inside of if")
                db_score.actual_scores = actual_score
                print("actual score")
                db_score.predicted_scores = predicted_scores
                print("predicted score")
                db_score.danger_level = danger_level
                print("danger score")
                db_score.delta_percentage = round(percentage_difference, 1)
                print("delta score")
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
            print(db_score)

        db.commit()

        return {"analysis": json_response}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

@app.get("/get_class")
def get_class_data(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        # Verify the token and get user data
        user_data = verify_access_token(token)  
        if not user_data:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        # Get user by email (sub)
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
                # Assuming ScoresInDB stores the actual and teacher scores
                student_scores = db.query(ScoresInDB).filter(ScoresInDB.student_id == student.id).all()

                # Initialize score values
                actual_score = []
                teacher_score = []
                danger_level = None
                delta_percentage = None

                for score in student_scores:
                    actual_score.extend(score.actual_scores)
                    teacher_score.extend(score.predicted_scores)
                    danger_level = score.danger_level  # assuming all have same danger level
                    delta_percentage = score.delta_percentage  # assuming same for all
                    subject_name = score.subject_name

                student_info_list.append({
                    "student_name": student.name,
                    "actual_score": actual_score,
                    "predicted_score": teacher_score,
                    "danger_level": danger_level,
                    "delta_percentage": delta_percentage,
                    "class_liter": grade.grade,  # This is the grade name
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
    
@app.delete("/delete_all/")
def delete_all(db: Session = Depends(get_db)):
    try:
        db.query(ScoresInDB).delete()
        db.query(StudentInDB).delete()
        db.query(GradeInDB).delete()
        
        db.commit()  
        return {"message": "All users, grades, students, and scores deleted successfully."}
    except Exception as e:
        db.rollback() 
        raise HTTPException(status_code=500, detail=str(e))
