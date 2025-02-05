from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

Base = declarative_base()

class UserInDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    type = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)

    grades = relationship("GradeInDB", back_populates="user")

class GradeInDB(Base):
    __tablename__ = "grades"

    id = Column(Integer, primary_key=True, index=True)
    grade = Column(String, index=True)
    curatorName = Column(String, index=True)
    createdAt = Column(DateTime, index=True, default=datetime.utcnow)

    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("UserInDB", back_populates="grades")

    students = relationship("StudentInDB", back_populates="grade")

class StudentInDB(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, index=True)

    grade_id = Column(Integer, ForeignKey("grades.id"))
    grade = relationship("GradeInDB", back_populates="students")

    scores = relationship("ScoresInDB", back_populates="student")

class ScoresInDB(Base):
    __tablename__ = "scores"

    id = Column(Integer, primary_key=True, index=True)
    teacher_name = Column(String, index=True)
    subject_name = Column(String, index=True)
    actual_scores = Column(JSON, index=True)
    predicted_scores = Column(JSON, index=True)
    danger_level = Column(Integer, index=True)
    delta_percentage = Column(Float, index=True)

    student_id = Column(Integer, ForeignKey("students.id"))
    student = relationship("StudentInDB", back_populates="scores")

class CreateUser(BaseModel):
    name: str
    email: str
    password: str
    type: str

class CreateRecord(BaseModel):
    grade: str
    curatorName: Optional[str] = "Unknown Curator"

class CreateStudent(BaseModel):
    name: str
    email: str

class CreateScore(BaseModel):
    subject_name: str
    actual_scores: list[float]
    predicted_scores: list[float]
    danger_level: int 
    delta_percentage: float
    student_id: int

class UserLogin(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    type: str
