from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pydantic import BaseModel
from datetime import datetime

Base = declarative_base()

# Модель пользователя
class UserInDB(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    doctor_type = Column(String)

    # Связь с записями оценок
    grades = relationship("GradeInDB", back_populates="user")

# Модель оценок
class GradeInDB(Base):
    __tablename__ = "grades"

    id = Column(Integer, primary_key=True, index=True)
    grade = Column(String, index=True)
    curatorName = Column(String, index=True)
    createdAt = Column(DateTime, index=True, default=datetime.utcnow)

    # Внешний ключ для связи с пользователем
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("UserInDB", back_populates="grades")

    # Связь со студентами
    students = relationship("StudentInDB", back_populates="grade")

# Модель студента
class StudentInDB(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    actual_score = Column(Float, index=True)
    teacher_score = Column(Float, index=True)
    danger_level = Column(Integer, index=True)
    delta_percentage = Column(Float, index=True)
    
    # Внешний ключ для связи с оценками
    grade_id = Column(Integer, ForeignKey("grades.id"))
    grade = relationship("GradeInDB", back_populates="students")

# Модели для создания пользователей, записей и студентов
class CreateUser(BaseModel):
    name: str
    email: str
    password: str

class CreateRecord(BaseModel):
    grade: str
    curatorName: str

class CreateStudent(BaseModel):
    name: str
    email: str
    actual_score: float
    teacher_score: float
    predicted_score: float
    danger_level: int
    delta_percentage: float
# Модель для входа пользователя
class UserLogin(BaseModel):
    email: str
    password: str

# Модель токена
class Token(BaseModel):
    access_token: str
    token_type: str
