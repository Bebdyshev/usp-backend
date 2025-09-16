from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Dict, Any

Base = declarative_base()

class UserInDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    type = Column(String(50), nullable=False, index=True, default='user')
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=True)
    is_active = Column(Integer, default=1, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    grades = relationship("GradeInDB", back_populates="user", cascade="all, delete-orphan")

class GradeInDB(Base):
    __tablename__ = "grades"

    id = Column(Integer, primary_key=True, index=True)
    grade = Column(String(50), nullable=False, index=True)
    parallel = Column(String(50), nullable=False, index=True)
    curator_name = Column(String(255), nullable=False, index=True)
    shanyrak = Column(String(255), nullable=True)
    student_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user = relationship("UserInDB", back_populates="grades")

    students = relationship("StudentInDB", back_populates="grade", cascade="all, delete-orphan")
    scores = relationship("ScoresInDB", back_populates="grade", cascade="all, delete-orphan")

    # Composite index for better query performance
    __table_args__ = (
        Index('ix_grades_grade_parallel', 'grade', 'parallel'),
    )

class StudentInDB(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    email = Column(String(255), nullable=True, index=True)
    student_id_number = Column(String(50), nullable=True, unique=True, index=True)
    phone = Column(String(20), nullable=True)
    parent_contact = Column(String(255), nullable=True)
    is_active = Column(Integer, default=1, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    grade_id = Column(Integer, ForeignKey("grades.id", ondelete="CASCADE"), nullable=False)
    grade = relationship("GradeInDB", back_populates="students")

    scores = relationship("ScoresInDB", back_populates="student", cascade="all, delete-orphan")

class ScoresInDB(Base):
    __tablename__ = "scores"

    id = Column(Integer, primary_key=True, index=True)
    teacher_name = Column(String(255), nullable=False, index=True)
    subject_name = Column(String(100), nullable=False, index=True)
    actual_scores = Column(JSONB, nullable=True)  # Changed from JSON to JSONB, removed index
    predicted_scores = Column(JSONB, nullable=True)  # Changed from JSON to JSONB, removed index
    danger_level = Column(Integer, nullable=False, index=True)
    delta_percentage = Column(Float, nullable=True, index=True)
    semester = Column(Integer, nullable=False, index=True, default=1)
    academic_year = Column(String(10), nullable=False, index=True, default="2024-2025")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    student = relationship("StudentInDB", back_populates="scores")
    
    grade_id = Column(Integer, ForeignKey("grades.id", ondelete="CASCADE"), nullable=False)
    grade = relationship("GradeInDB", back_populates="scores")

    # GIN indexes for JSONB columns (better for JSON queries)
    __table_args__ = (
        Index('ix_scores_actual_scores_gin', 'actual_scores', postgresql_using='gin'),
        Index('ix_scores_predicted_scores_gin', 'predicted_scores', postgresql_using='gin'),
        Index('ix_scores_student_subject', 'student_id', 'subject_name'),
        Index('ix_scores_grade_semester', 'grade_id', 'semester'),
    )

# ==================== PYDANTIC MODELS ====================

class CreateUser(BaseModel):
    name: str
    email: str
    password: str
    type: str = "user"
    company_name: Optional[str] = None

class UpdateUser(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    type: Optional[str] = None
    company_name: Optional[str] = None
    is_active: Optional[int] = None

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    type: str
    company_name: Optional[str] = None
    is_active: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class CreateGrade(BaseModel):
    grade: str
    parallel: str
    curator_name: str = "Unknown Curator"
    shanyrak: Optional[str] = None
    student_count: Optional[int] = 0

class UpdateGrade(BaseModel):
    grade: Optional[str] = None
    parallel: Optional[str] = None
    curator_name: Optional[str] = None
    shanyrak: Optional[str] = None
    student_count: Optional[int] = None

class GradeResponse(BaseModel):
    id: int
    grade: str
    parallel: str
    curator_name: str
    shanyrak: Optional[str] = None
    student_count: int
    created_at: datetime
    updated_at: datetime
    user_id: int

    class Config:
        from_attributes = True

class CreateStudent(BaseModel):
    name: str
    email: Optional[str] = None
    student_id_number: Optional[str] = None
    phone: Optional[str] = None
    parent_contact: Optional[str] = None
    grade_id: int

class UpdateStudent(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    student_id_number: Optional[str] = None
    phone: Optional[str] = None
    parent_contact: Optional[str] = None
    is_active: Optional[int] = None

class StudentResponse(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    student_id_number: Optional[str] = None
    phone: Optional[str] = None
    parent_contact: Optional[str] = None
    is_active: int
    created_at: datetime
    updated_at: datetime
    grade_id: int

    class Config:
        from_attributes = True

class CreateScore(BaseModel):
    teacher_name: str
    subject_name: str
    actual_scores: Optional[Dict[str, Any]] = None
    predicted_scores: Optional[Dict[str, Any]] = None
    danger_level: int
    delta_percentage: Optional[float] = None
    semester: int = 1
    academic_year: str = "2024-2025"
    student_id: int
    grade_id: int

class UpdateScore(BaseModel):
    teacher_name: Optional[str] = None
    subject_name: Optional[str] = None
    actual_scores: Optional[Dict[str, Any]] = None
    predicted_scores: Optional[Dict[str, Any]] = None
    danger_level: Optional[int] = None
    delta_percentage: Optional[float] = None
    semester: Optional[int] = None
    academic_year: Optional[str] = None

class ScoreResponse(BaseModel):
    id: int
    teacher_name: str
    subject_name: str
    actual_scores: Optional[Dict[str, Any]] = None
    predicted_scores: Optional[Dict[str, Any]] = None
    danger_level: int
    delta_percentage: Optional[float] = None
    semester: int
    academic_year: str
    created_at: datetime
    updated_at: datetime
    student_id: int
    grade_id: int

    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    email: str
    password: str

class UserSignup(BaseModel):
    email: str
    password: str
    company_name: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    email: Optional[str] = None

# ==================== LEGACY MODELS (for backward compatibility) ====================

# Keep these for backward compatibility with existing code
CreateRecord = CreateGrade  # Alias for backward compatibility
