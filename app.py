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

@app.post("/login/", response_model=Token)
def login_for_access_token(user: UserLogin, db: Session = Depends(get_db)) -> Token:
    db_user = db.query(UserInDB).filter(UserInDB.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.email, "role": db_user.doctor_type},  # Use 'doctor_type' for user role
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
async def send_excel_as_csv_to_openai(grade: str = Form(...), curator: str = Form(...), file: UploadFile = File(...), token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
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

        headers = {
            "Content-Type": "application/json",
            "api-key": AZURE_API_KEY
        }

        data = {
            "messages": [
                {"role": "system", "content": "You are an assistant that processes CSV data and provides insights."},
                {"role": "user", "content": f"Here's the CSV data:\n{csv_text}\n You should provide feedback in json format: 'student_name': student name, 'score': score, 'teacher_score': teacher score. YOU SHOULD ONLY RETURN JSON, DONT WRITE ANY OTHER WORDS. I NEED PLAIN TEXT"}
            ],
            "max_tokens": 250,
            "temperature": 0.5
        }

        response = requests.post(AZURE_OPENAI_ENDPOINT, headers=headers, json=data)

        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response.json())

        gpt_response = response.json()["choices"][0]["message"]["content"].strip().replace("\n", "").replace('\\', "").replace("```json", "").replace("```", "")

        try:
            json_response = json.loads(gpt_response)
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="Error decoding GPT response.")

        for analysis_item in json_response:
            db_student = db.query(StudentInDB).filter(StudentInDB.name == analysis_item["student_name"]).first()

            score_difference = abs(analysis_item["score"] - analysis_item["teacher_score"])
            if analysis_item["teacher_score"] != 0:
                percentage_difference = (score_difference / analysis_item["teacher_score"]) * 100
            else:
                percentage_difference = 0 

            if percentage_difference < 5:
                danger_level = 0  # White
            elif 5 <= percentage_difference <= 10:
                danger_level = 1  # Green
            elif 10 < percentage_difference <= 15:
                danger_level = 2  # Yellow
            else:
                danger_level = 3  # Red

            if db_student:
                db_student.actual_score = analysis_item["score"]
                db_student.teacher_score = analysis_item["teacher_score"]
                db_student.danger_level = danger_level
            else:
                db_grade = db.query(GradeInDB).filter(GradeInDB.grade == grade, GradeInDB.curatorName == curator).first()

                user_id = db.query(UserInDB).filter(UserInDB.email == user_data["sub"]).first().id
                if not db_grade:
                    db_grade = GradeInDB(grade=grade, curatorName=curator, user_id=user_id)
                    db.add(db_grade)
                    db.commit()
                    db.refresh(db_grade)

                new_student = StudentInDB(
                    name=analysis_item["student_name"],
                    actual_score=analysis_item["score"],
                    teacher_score=analysis_item["teacher_score"],
                    danger_level=danger_level,  
                    delta_percentage= round(percentage_difference, 2),
                    grade_id=db_grade.id  
                )
                db.add(new_student)

        db.commit() 

        return {"analysis": json_response}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
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
                student_info_list.append({
                    "student_name": student.name,
                    "actual_score": student.actual_score,
                    "teacher_score": student.teacher_score,
                    "danger_level": student.danger_level,
                    "delta_percentage": student.delta_percentage,
                    "class_liter": grade.grade,
                })
                
            class_data.append({
                "curator_name": grade.curatorName,
                "grade_liter": grade.grade,
                "class": student_info_list
            })
        
        return {"class_data": class_data}

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="An error occurred while fetching class data")