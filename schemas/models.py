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
    name = Column(String(255), nullable=False, index=True)  # Full name for backward compatibility
    first_name = Column(String(100), nullable=True, index=True)
    last_name = Column(String(100), nullable=True, index=True)
    type = Column(String(50), nullable=False, index=True, default='user')
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=True)
    shanyrak = Column(String(255), nullable=True)  # For curators
    is_active = Column(Integer, default=1, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    grades = relationship("GradeInDB", foreign_keys="GradeInDB.user_id", back_populates="user", cascade="all, delete-orphan")
    curated_grades = relationship("GradeInDB", foreign_keys="GradeInDB.curator_id", back_populates="curator")
    teacher_assignments = relationship("TeacherAssignmentInDB", foreign_keys="TeacherAssignmentInDB.teacher_id", back_populates="teacher")

class GradeInDB(Base):
    __tablename__ = "grades"

    id = Column(Integer, primary_key=True, index=True)
    grade = Column(String(50), nullable=False, index=True)
    parallel = Column(String(50), nullable=False, index=True)
    curator_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    curator_name = Column(String(255), nullable=True, index=True)  # Keep for backward compatibility
    student_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user = relationship("UserInDB", foreign_keys=[user_id], back_populates="grades")
    curator = relationship("UserInDB", foreign_keys=[curator_id], back_populates="curated_grades")

    students = relationship("StudentInDB", back_populates="grade", cascade="all, delete-orphan")
    scores = relationship("ScoresInDB", back_populates="grade", cascade="all, delete-orphan")
    subgroups = relationship("SubgroupInDB", back_populates="grade", cascade="all, delete-orphan")
    curator_assignments = relationship("CuratorGradeInDB", foreign_keys="CuratorGradeInDB.grade_id")

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
    subgroup_id = Column(Integer, ForeignKey("subgroups.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # For student login accounts
    subgroup = relationship("SubgroupInDB", back_populates="students")
    user_account = relationship("UserInDB", foreign_keys="StudentInDB.user_id")
    disciplinary_actions = relationship("DisciplinaryActionInDB", back_populates="student", cascade="all, delete-orphan")
    achievements = relationship("AchievementInDB", back_populates="student", cascade="all, delete-orphan")

    scores = relationship("ScoresInDB", back_populates="student", cascade="all, delete-orphan")

class ScoresInDB(Base):
    __tablename__ = "scores"

    id = Column(Integer, primary_key=True, index=True)
    teacher_name = Column(String(255), nullable=False, index=True)
    subject_name = Column(String(100), nullable=False, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True, index=True)  # New relation to subjects
    previous_class_score = Column(Float, nullable=True)
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

    subject = relationship("SubjectInDB", back_populates="scores")  # New relationship
    subgroup_id = Column(Integer, ForeignKey("subgroups.id"), nullable=True)
    subgroup = relationship("SubgroupInDB")

    # GIN indexes for JSONB columns (better for JSON queries)
    __table_args__ = (
        Index('ix_scores_actual_scores_gin', 'actual_scores', postgresql_using='gin'),
        Index('ix_scores_predicted_scores_gin', 'predicted_scores', postgresql_using='gin'),
        Index('ix_scores_student_subject', 'student_id', 'subject_name'),
        Index('ix_scores_grade_semester', 'grade_id', 'semester'),
    )

class SubjectInDB(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    applicable_parallels = Column(JSONB, nullable=False, default=[])
    is_active = Column(Integer, default=1, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    scores = relationship("ScoresInDB", back_populates="subject")

class PredictionSettings(Base):
    __tablename__ = "prediction_settings"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True) # e.g., "default_weights"
    weights = Column(JSONB, nullable=False) # e.g., {"previous_class": 0.3, "teacher": 0.2, "quarters": 0.5}
    is_active = Column(Integer, default=1, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ExcelColumnMapping(Base):
    __tablename__ = "excel_column_mapping"

    id = Column(Integer, primary_key=True, index=True)
    field_name = Column(String(100), unique=True, nullable=False, index=True) # e.g., "student_name", "q1", "previous_class_score"
    column_aliases = Column(JSONB, nullable=False) # e.g., ["ФИО", "Student Name", "Name"]
    is_active = Column(Integer, default=1, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SystemSettingsInDB(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    min_grade = Column(Integer, nullable=False, default=7)
    max_grade = Column(Integer, nullable=False, default=12)
    class_letters = Column(JSONB, nullable=False, default=['A', 'B', 'C', 'D', 'E', 'F'])
    school_name = Column(String(255), nullable=True, default="Школа")
    academic_year = Column(String(20), nullable=False, default="2024-2025")
    is_active = Column(Integer, default=1, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ==================== PYDANTIC MODELS ====================

class CreateUser(BaseModel):
    name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: str
    password: str
    type: str = "user"
    company_name: Optional[str] = None
    shanyrak: Optional[str] = None

class UpdateUser(BaseModel):
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    type: Optional[str] = None
    company_name: Optional[str] = None
    shanyrak: Optional[str] = None
    is_active: Optional[int] = None

class UserResponse(BaseModel):
    id: int
    name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: str
    type: str
    company_name: Optional[str] = None
    shanyrak: Optional[str] = None
    is_active: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class CreateGrade(BaseModel):
    grade: str
    parallel: str
    curator_id: Optional[int] = None
    curator_name: Optional[str] = None  # Keep for backward compatibility
    student_count: Optional[int] = 0

class UpdateGrade(BaseModel):
    grade: Optional[str] = None
    parallel: Optional[str] = None
    curator_id: Optional[int] = None
    curator_name: Optional[str] = None
    student_count: Optional[int] = None

class GradeResponse(BaseModel):
    id: int
    grade: str
    parallel: str
    curator_id: Optional[int] = None
    curator_name: Optional[str] = None
    student_count: int
    created_at: datetime
    updated_at: datetime
    user_id: int
    curator_info: Optional[dict] = None  # Will include curator details

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

class CreateSubject(BaseModel):
    name: str
    description: Optional[str] = None
    applicable_parallels: List[int] = []

class UpdateSubject(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[int] = None
    applicable_parallels: Optional[List[int]] = None

class SubjectResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    applicable_parallels: List[int]
    is_active: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class CreateSystemSettings(BaseModel):
    min_grade: int = 7
    max_grade: int = 12
    class_letters: List[str] = ['A', 'B', 'C', 'D', 'E', 'F']
    school_name: Optional[str] = "Школа"
    academic_year: str = "2024-2025"

class UpdateSystemSettings(BaseModel):
    min_grade: Optional[int] = None
    max_grade: Optional[int] = None
    class_letters: Optional[List[str]] = None
    school_name: Optional[str] = None
    academic_year: Optional[str] = None

class SystemSettingsResponse(BaseModel):
    id: int
    min_grade: int
    max_grade: int
    class_letters: List[str]
    school_name: Optional[str]
    academic_year: str
    is_active: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class AvailableClassesResponse(BaseModel):
    classes: List[str]
    grades: List[int]

# ==================== NEW MODELS FOR ENHANCED SCHOOL MANAGEMENT ====================

class SubgroupInDB(Base):
    __tablename__ = "subgroups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)  # e.g., "Подгруппа А", "Подгруппа Б"
    grade_id = Column(Integer, ForeignKey("grades.id", ondelete="CASCADE"), nullable=False)
    is_active = Column(Integer, default=1, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    grade = relationship("GradeInDB", back_populates="subgroups")
    students = relationship("StudentInDB", back_populates="subgroup")
    teacher_assignments = relationship("TeacherAssignmentInDB", back_populates="subgroup")

class CuratorGradeInDB(Base):
    __tablename__ = "curator_grades"

    id = Column(Integer, primary_key=True, index=True)
    curator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    grade_id = Column(Integer, ForeignKey("grades.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    curator = relationship("UserInDB", foreign_keys=[curator_id])
    grade = relationship("GradeInDB", foreign_keys=[grade_id])

    # Unique constraint: one curator per grade
    __table_args__ = (
        Index('ix_curator_grades_unique', 'curator_id', 'grade_id', unique=True),
    )

class TeacherAssignmentInDB(Base):
    __tablename__ = "teacher_assignments"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    grade_id = Column(Integer, ForeignKey("grades.id", ondelete="CASCADE"), nullable=True)
    subgroup_id = Column(Integer, ForeignKey("subgroups.id", ondelete="CASCADE"), nullable=True)
    is_active = Column(Integer, default=1, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    teacher = relationship("UserInDB", foreign_keys=[teacher_id])
    subject = relationship("SubjectInDB", foreign_keys=[subject_id])
    grade = relationship("GradeInDB", foreign_keys=[grade_id])
    subgroup = relationship("SubgroupInDB", foreign_keys=[subgroup_id])

    # Unique constraint: one teacher per subject per subgroup (or grade if no subgroup)
    __table_args__ = (
        Index('ix_teacher_assignment_unique', 'teacher_id', 'subject_id', 'grade_id', 'subgroup_id', unique=True),
    )

class DisciplinaryActionInDB(Base):
    __tablename__ = "disciplinary_actions"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    action_type = Column(String(100), nullable=False, index=True)  # "warning", "suspension", etc.
    description = Column(Text, nullable=False)
    severity_level = Column(Integer, nullable=False, index=True, default=1)  # 1-5 scale
    issued_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    action_date = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    is_resolved = Column(Integer, default=0, index=True)
    resolution_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student = relationship("StudentInDB", back_populates="disciplinary_actions")
    issuer = relationship("UserInDB", foreign_keys=[issued_by])

class AchievementInDB(Base):
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=False, index=True)  # "academic", "sports", "arts", etc.
    achievement_date = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    awarded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    points = Column(Integer, default=0, index=True)  # Achievement points/score
    certificate_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student = relationship("StudentInDB", back_populates="achievements")
    awarder = relationship("UserInDB", foreign_keys=[awarded_by])

# Update existing models to add new relationships
# Add to GradeInDB
GradeInDB.subgroups = relationship("SubgroupInDB", back_populates="grade", cascade="all, delete-orphan")
GradeInDB.curator_assignments = relationship("CuratorGradeInDB", foreign_keys="CuratorGradeInDB.grade_id")

# Add to StudentInDB
StudentInDB.subgroup_id = Column(Integer, ForeignKey("subgroups.id"), nullable=True)
StudentInDB.user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # For student login accounts
StudentInDB.subgroup = relationship("SubgroupInDB", back_populates="students")
StudentInDB.user_account = relationship("UserInDB", foreign_keys="StudentInDB.user_id")
StudentInDB.disciplinary_actions = relationship("DisciplinaryActionInDB", back_populates="student", cascade="all, delete-orphan")
StudentInDB.achievements = relationship("AchievementInDB", back_populates="student", cascade="all, delete-orphan")

# Add to ScoresInDB
ScoresInDB.subgroup_id = Column(Integer, ForeignKey("subgroups.id"), nullable=True)
ScoresInDB.subgroup = relationship("SubgroupInDB")

# ==================== PYDANTIC MODELS FOR NEW ENTITIES ====================

class CreateSubgroup(BaseModel):
    name: str
    grade_id: int

class UpdateSubgroup(BaseModel):
    name: Optional[str] = None
    is_active: Optional[int] = None

class SubgroupResponse(BaseModel):
    id: int
    name: str
    grade_id: int
    is_active: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class CreateCuratorAssignment(BaseModel):
    curator_id: int
    grade_id: int

class CuratorAssignmentResponse(BaseModel):
    id: int
    curator_id: int
    grade_id: int
    created_at: datetime
    curator_name: Optional[str] = None
    grade_name: Optional[str] = None

    class Config:
        from_attributes = True

class CreateTeacherAssignment(BaseModel):
    teacher_id: int
    subject_id: int
    grade_id: Optional[int] = None
    subgroup_id: Optional[int] = None

class UpdateTeacherAssignment(BaseModel):
    is_active: Optional[int] = None

class TeacherAssignmentResponse(BaseModel):
    id: int
    teacher_id: int
    subject_id: int
    grade_id: Optional[int] = None
    subgroup_id: Optional[int] = None
    is_active: int
    created_at: datetime
    updated_at: datetime
    teacher_name: Optional[str] = None
    subject_name: Optional[str] = None
    grade_name: Optional[str] = None
    subgroup_name: Optional[str] = None

    class Config:
        from_attributes = True

class CreateDisciplinaryAction(BaseModel):
    student_id: int
    action_type: str
    description: str
    severity_level: int = 1
    action_date: Optional[datetime] = None

class UpdateDisciplinaryAction(BaseModel):
    action_type: Optional[str] = None
    description: Optional[str] = None
    severity_level: Optional[int] = None
    is_resolved: Optional[int] = None
    resolution_notes: Optional[str] = None

class DisciplinaryActionResponse(BaseModel):
    id: int
    student_id: int
    action_type: str
    description: str
    severity_level: int
    issued_by: int
    action_date: datetime
    is_resolved: int
    resolution_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    student_name: Optional[str] = None
    issuer_name: Optional[str] = None

    class Config:
        from_attributes = True

class CreateAchievement(BaseModel):
    student_id: int
    title: str
    description: Optional[str] = None
    category: str
    achievement_date: Optional[datetime] = None
    points: int = 0
    certificate_url: Optional[str] = None

class UpdateAchievement(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    achievement_date: Optional[datetime] = None
    points: Optional[int] = None
    certificate_url: Optional[str] = None

class AchievementResponse(BaseModel):
    id: int
    student_id: int
    title: str
    description: Optional[str] = None
    category: str
    achievement_date: datetime
    awarded_by: int
    points: int
    certificate_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    student_name: Optional[str] = None
    awarder_name: Optional[str] = None

    class Config:
        from_attributes = True

class ExcelUploadRequest(BaseModel):
    grade_id: int
    subject_id: int
    teacher_name: str
    semester: int = 1
    subgroup_id: Optional[int] = None

class ExcelUploadResponse(BaseModel):
    success: bool
    message: str
    imported_count: int
    warnings: List[str] = []
    errors: List[str] = []
    danger_distribution: Dict[str, int] = {}

class PredictionWeightsResponse(BaseModel):
    id: int
    name: str
    weights: Dict[str, float]
    is_active: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class UpdatePredictionWeights(BaseModel):
    weights: Dict[str, float]
    name: Optional[str] = None

class ExcelColumnMappingResponse(BaseModel):
    id: int
    field_name: str
    column_aliases: List[str]
    is_active: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class CreateExcelColumnMapping(BaseModel):
    field_name: str
    column_aliases: List[str]

class UpdateExcelColumnMapping(BaseModel):
    column_aliases: Optional[List[str]] = None
    is_active: Optional[int] = None

# ==================== LEGACY MODELS (for backward compatibility) ====================

# Keep these for backward compatibility with existing code
CreateRecord = CreateGrade  # Alias for backward compatibility
