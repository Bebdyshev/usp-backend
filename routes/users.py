from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import and_
from auth_utils import hash_password, verify_password, create_access_token, verify_access_token
from config import get_db
from schemas.models import *
from datetime import timedelta
from typing import List, Optional, Tuple
import re
from routes.auth import oauth2_scheme

router = APIRouter()

@router.get("/", response_model=List[dict])
async def get_all_users(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get all users"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Check if the user is an admin
    if user_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can view all users")
    
    users = db.query(UserInDB).all()
    
    result = []
    for user in users:
        # Не включаем хэш пароля в ответ
        result.append({
            "id": user.id,
            "name": user.name,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "type": user.type,
            "company_name": user.company_name,
            "shanyrak": user.shanyrak,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "updated_at": user.updated_at
        })
    
    return result

@router.get("/by-type/{user_type}", response_model=List[dict])
async def get_users_by_type(
    user_type: str,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get users by type (curator, teacher, admin, etc.)"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Validate user type
    valid_types = ['admin', 'curator', 'teacher', 'user']
    if user_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid user type. Must be one of: {valid_types}")
    
    users = db.query(UserInDB).filter(
        UserInDB.type == user_type,
        UserInDB.is_active == 1
    ).all()
    
    result = []
    for user in users:
        # Get additional info based on user type
        additional_info = {}
        
        if user_type == 'curator':
            # Count assigned grades
            grade_count = db.query(GradeInDB).filter(GradeInDB.curator_id == user.id).count()
            additional_info['assigned_grades_count'] = grade_count
        
        elif user_type == 'teacher':
            # Count teaching assignments
            assignment_count = db.query(TeacherAssignmentInDB).filter(
                TeacherAssignmentInDB.teacher_id == user.id,
                TeacherAssignmentInDB.is_active == 1
            ).count()
            additional_info['assignment_count'] = assignment_count
        
        result.append({
            "id": user.id,
            "name": user.name,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "type": user.type,
            "company_name": user.company_name,
            "shanyrak": user.shanyrak,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            **additional_info
        })
    
    return result

@router.get("/{user_id}", response_model=dict)
async def get_user(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get user by ID"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Admins can view any user, regular users can only view themselves
    if user_data.get("type") != "admin" and user_data.get("id") != user_id:
        raise HTTPException(status_code=403, detail="You can only view your own data")
    
    user = db.query(UserInDB).filter(UserInDB.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "type": user.type
    }

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    type: str

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Create a new user"""
    admin_data = verify_access_token(token)
    if not admin_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Only admins can create users
    if admin_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create users")
    
    # Check if email already exists
    existing_user = db.query(UserInDB).filter(UserInDB.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user
    hashed_password = hash_password(user_data.password)
    
    new_user = UserInDB(
        name=user_data.name,
        email=user_data.email,
        hashed_password=hashed_password,
        type=user_data.type
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {
        "id": new_user.id,
        "message": "User created successfully"
    }

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    type: Optional[str] = None

@router.put("/{user_id}", status_code=status.HTTP_200_OK)
async def update_user(
    user_id: int,
    update_data: UserUpdate,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Update user by ID"""
    user_data = verify_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Admins can update any user, regular users can only update themselves and not change their type
    if user_data.get("type") != "admin":
        if user_data.get("id") != user_id:
            raise HTTPException(status_code=403, detail="You can only update your own data")
        if update_data.type is not None:
            raise HTTPException(status_code=403, detail="You cannot change your user type")
    
    user = db.query(UserInDB).filter(UserInDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update email if provided and not already taken
    if update_data.email is not None and update_data.email != user.email:
        existing_user = db.query(UserInDB).filter(UserInDB.email == update_data.email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        user.email = update_data.email
    
    # Update name if provided
    if update_data.name is not None:
        user.name = update_data.name
    
    # Update type if provided (admin only)
    if update_data.type is not None and user_data.get("type") == "admin":
        user.type = update_data.type
    
    # Update password if provided
    if update_data.password is not None:
        user.hashed_password = hash_password(update_data.password)
    
    db.commit()
    db.refresh(user)
    
    return {
        "message": "User updated successfully"
    }

@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Delete user by ID"""
    admin_data = verify_access_token(token)
    if not admin_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Only admins can delete users
    if admin_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete users")
    
    # Prevent admin from deleting themselves
    if admin_data.get("id") == user_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    
    user = db.query(UserInDB).filter(UserInDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(user)
    db.commit()
    
    return {
        "message": "User deleted successfully"
    }

from fastapi import File, UploadFile
import openpyxl
import io

class BulkUploadRowResult(BaseModel):
    row: int
    status: str  # "created" | "updated" | "skipped"
    message: str
    teacher_name: Optional[str] = None
    class_name: Optional[str] = None
    subject_name: Optional[str] = None
    subject_group_name: Optional[str] = None


class BulkUploadResult(BaseModel):
    success: bool
    total_processed: int
    created_count: int
    updated_count: int
    error_count: int
    errors: List[dict]
    created_users: List[dict]
    row_results: List[BulkUploadRowResult] = []


def _parse_class_cell(cell_val) -> Tuple[Optional[str], Optional[str]]:
    """Parse class cell (e.g. '11A', '10B') into (grade, parallel). Returns (None, None) if invalid."""
    if cell_val is None or str(cell_val).strip() == "":
        return None, None
    s = str(cell_val).strip()
    m = re.match(r"^(\d{1,2})\s*([A-Za-zА-Яа-яІі]?)\s*$", s)
    if m:
        grade = m.group(1)
        parallel = m.group(2) if m.group(2) else "A"
        return grade, parallel
    if re.match(r"^\d{1,2}$", s):
        return s, "A"
    return None, None


def _parse_class_list_cell(cell_val) -> Tuple[List[Tuple[str, str]], List[str]]:
    """
    Parse a class cell that may contain multiple classes separated by commas.
    Example: "11A, 11B, 12A" -> [("11","A"), ("11","B"), ("12","A")]
    Returns (valid_classes, invalid_tokens)
    """
    if cell_val is None or str(cell_val).strip() == "":
        return [], []

    raw_value = str(cell_val).strip()
    tokens = [t.strip() for t in raw_value.split(",") if t and t.strip()]
    valid_classes: List[Tuple[str, str]] = []
    invalid_tokens: List[str] = []

    for token in tokens:
        grade_str, parallel_str = _parse_class_cell(token)
        if grade_str and parallel_str:
            valid_classes.append((grade_str, parallel_str))
        else:
            invalid_tokens.append(token)

    return valid_classes, invalid_tokens


def _get_or_create_grade(db: Session, grade_str: str, parallel: str, user_id: int) -> Optional[GradeInDB]:
    existing = db.query(GradeInDB).filter(
        GradeInDB.grade == grade_str,
        GradeInDB.parallel == parallel
    ).first()
    if existing:
        return existing
    new_grade = GradeInDB(
        grade=grade_str,
        parallel=parallel,
        user_id=user_id,
        student_count=0
    )
    db.add(new_grade)
    db.commit()
    db.refresh(new_grade)
    return new_grade


def _get_or_create_subject(db: Session, name: str) -> Optional[SubjectInDB]:
    if not name or not str(name).strip():
        return None
    existing = db.query(SubjectInDB).filter(SubjectInDB.name == name.strip()).first()
    if existing:
        return existing
    new_subject = SubjectInDB(
        name=name.strip(),
        applicable_parallels=[],
        is_active=1
    )
    db.add(new_subject)
    db.commit()
    db.refresh(new_subject)
    return new_subject


def _get_or_create_subject_group(db: Session, grade_id: int, subject_id: int, name: str) -> Optional[object]:
    from schemas.models import SubjectGroupInDB
    if not name or not str(name).strip():
        return None
    existing = db.query(SubjectGroupInDB).filter(
        SubjectGroupInDB.grade_id == grade_id,
        SubjectGroupInDB.subject_id == subject_id,
        SubjectGroupInDB.name == name.strip(),
        SubjectGroupInDB.is_active == 1
    ).first()
    if existing:
        return existing
    new_group = SubjectGroupInDB(
        grade_id=grade_id,
        subject_id=subject_id,
        name=name.strip(),
        is_active=1
    )
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    return new_group


@router.post("/bulk-upload-teachers", response_model=BulkUploadResult)
async def bulk_upload_teachers(
    file: UploadFile = File(...),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Bulk upload teachers from Excel file. Supports: ФИО, Должность, Email, Класс(ы), Предмет, Предметная группа (11-12). Классы можно указывать через запятую."""
    admin_data = verify_access_token(token)
    if not admin_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if admin_data.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can bulk upload users")

    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="File must be an Excel file (.xlsx or .xls)")

    creator_user = db.query(UserInDB).filter(UserInDB.email == admin_data.get("sub")).first()
    if not creator_user:
        creator_user = db.query(UserInDB).filter(UserInDB.id == admin_data.get("id")).first()
    creator_id = creator_user.id if creator_user else admin_data.get("id", 1)

    try:
        contents = await file.read()
        workbook = openpyxl.load_workbook(io.BytesIO(contents))
        sheet = workbook.active

        created_users = []
        errors = []
        row_results = []
        total_processed = 0

        for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            if not row or all(cell is None or str(cell).strip() == "" for cell in row):
                continue

            total_processed += 1
            fio, position, email, class_cell, subject_cell, group_cell = None, None, None, None, None, None

            if len(row) >= 7:
                fio = str(row[1]).strip() if row[1] else None
                position = str(row[2]).strip() if row[2] else None
                email = str(row[3]).strip() if row[3] else None
                class_cell = row[4]
                subject_cell = str(row[5]).strip() if row[5] else None
                group_cell = str(row[6]).strip() if row[6] else None
            elif len(row) >= 6:
                fio = str(row[1]).strip() if row[1] else None
                position = str(row[2]).strip() if row[2] else None
                email = str(row[3]).strip() if row[3] else None
                class_cell = row[4]
                subject_cell = str(row[5]).strip() if row[5] else None
            elif len(row) >= 4:
                fio = str(row[1]).strip() if row[1] else None
                position = str(row[2]).strip() if row[2] else None
                email = str(row[3]).strip() if row[3] else None
            elif len(row) >= 3:
                fio = str(row[0]).strip() if row[0] else None
                position = str(row[1]).strip() if row[1] else None
                email = str(row[2]).strip() if row[2] else None

            if not fio or not email:
                err = {"row": row_idx, "error": "Missing required fields (ФИО or Email)", "data": {"fio": fio, "email": email}}
                errors.append(err)
                row_results.append(BulkUploadRowResult(row=row_idx, status="skipped", message=err["error"]))
                continue

            class_pairs, invalid_class_tokens = _parse_class_list_cell(class_cell)
            if invalid_class_tokens:
                err = {
                    "row": row_idx,
                    "error": f"Некорректные классы: {', '.join(invalid_class_tokens)}",
                    "data": {"class_cell": class_cell}
                }
                errors.append(err)
                row_results.append(BulkUploadRowResult(row=row_idx, status="skipped", message=err["error"]))
                continue

            subject_name = subject_cell
            if not subject_name and position:
                subject_keywords = {
                    "англ": "Английский язык", "химии": "Химия", "биологии": "Биология", "каз": "Казахский язык",
                    "рус": "Русский язык", "матем": "Математика", "физики": "Физика", "истории": "История",
                    "географии": "География", "физ.культуры": "Физическая культура", "искусства": "Искусство",
                    "НВП": "НВП", "ГиП": "Графика и проектирование", "информатик": "Информатика",
                }
                position_lower = position.lower()
                for kw, full in subject_keywords.items():
                    if kw in position_lower:
                        subject_name = full
                        break

            if group_cell and class_pairs:
                has_invalid_for_group = False
                for grade_str, _ in class_pairs:
                    try:
                        if int(grade_str) not in (11, 12):
                            has_invalid_for_group = True
                            break
                    except (ValueError, TypeError):
                        has_invalid_for_group = True
                        break
                if has_invalid_for_group:
                    err = {"row": row_idx, "error": "Предметная группа допускается только для 11-12 классов", "data": {}}
                    errors.append(err)
                    row_results.append(BulkUploadRowResult(row=row_idx, status="skipped", message=err["error"]))
                    continue

            try:
                existing_user = db.query(UserInDB).filter(UserInDB.email == email).first()
                if existing_user:
                    teacher = existing_user
                    if teacher.type != "teacher":
                        teacher.type = "teacher"
                        db.commit()
                else:
                    fio_parts = fio.split()
                    last_name = fio_parts[0] if fio_parts else ""
                    first_name = fio_parts[1] if len(fio_parts) > 1 else ""
                    hashed_password = hash_password("123")
                    teacher = UserInDB(
                        name=fio,
                        first_name=first_name,
                        last_name=last_name,
                        email=email,
                        hashed_password=hashed_password,
                        type="teacher",
                    )
                    db.add(teacher)
                    db.commit()
                    db.refresh(teacher)
                    created_users.append({"id": teacher.id, "name": fio, "email": email, "position": position, "subject": subject_name})

                subject_id = None
                class_display = ",".join([f"{g}{p}" for g, p in class_pairs]) if class_pairs else None

                if subject_name:
                    subj = _get_or_create_subject(db, subject_name)
                    if subj:
                        subject_id = subj.id

                if subject_id:
                    # If no class specified, keep backward-compatible subject-only assignment
                    if not class_pairs:
                        filters = [
                            TeacherAssignmentInDB.teacher_id == teacher.id,
                            TeacherAssignmentInDB.subject_id == subject_id,
                            TeacherAssignmentInDB.is_active == 1,
                            TeacherAssignmentInDB.subgroup_id.is_(None),
                            TeacherAssignmentInDB.grade_id.is_(None),
                            TeacherAssignmentInDB.subject_group_id.is_(None),
                        ]
                        existing_assignment = db.query(TeacherAssignmentInDB).filter(and_(*filters)).first()
                        if not existing_assignment:
                            new_assignment = TeacherAssignmentInDB(
                                teacher_id=teacher.id,
                                subject_id=subject_id,
                                grade_id=None,
                                subject_group_id=None,
                                subgroup_id=None,
                                is_active=1,
                            )
                            db.add(new_assignment)
                            db.commit()
                    else:
                        for grade_str, parallel_str in class_pairs:
                            db_grade = _get_or_create_grade(db, grade_str, parallel_str, creator_id)
                            if not db_grade:
                                continue

                            grade_id = db_grade.id
                            subject_group_id = None
                            if group_cell:
                                try:
                                    if int(grade_str) in (11, 12):
                                        sg = _get_or_create_subject_group(db, grade_id, subject_id, group_cell)
                                        if sg:
                                            subject_group_id = sg.id
                                except (ValueError, TypeError):
                                    subject_group_id = None

                            filters = [
                                TeacherAssignmentInDB.teacher_id == teacher.id,
                                TeacherAssignmentInDB.subject_id == subject_id,
                                TeacherAssignmentInDB.is_active == 1,
                                TeacherAssignmentInDB.subgroup_id.is_(None),
                                TeacherAssignmentInDB.grade_id == grade_id,
                            ]
                            filters.append(
                                TeacherAssignmentInDB.subject_group_id == subject_group_id
                                if subject_group_id
                                else TeacherAssignmentInDB.subject_group_id.is_(None)
                            )
                            existing_assignment = db.query(TeacherAssignmentInDB).filter(and_(*filters)).first()
                            if not existing_assignment:
                                new_assignment = TeacherAssignmentInDB(
                                    teacher_id=teacher.id,
                                    subject_id=subject_id,
                                    grade_id=grade_id,
                                    subject_group_id=subject_group_id,
                                    subgroup_id=None,
                                    is_active=1,
                                )
                                db.add(new_assignment)
                                db.commit()

                status_msg = "updated" if existing_user else "created"
                row_results.append(BulkUploadRowResult(
                    row=row_idx,
                    status=status_msg,
                    message="OK",
                    teacher_name=fio,
                    class_name=class_display,
                    subject_name=subject_name,
                    subject_group_name=group_cell if group_cell else None,
                ))

            except Exception as e:
                db.rollback()
                err = {"row": row_idx, "error": str(e), "data": {"fio": fio, "email": email}}
                errors.append(err)
                row_results.append(BulkUploadRowResult(row=row_idx, status="skipped", message=str(e)))

        updated_count = sum(1 for r in row_results if r.status == "updated")
        return BulkUploadResult(
            success=len(errors) == 0,
            total_processed=total_processed,
            created_count=len(created_users),
            updated_count=updated_count,
            error_count=len(errors),
            errors=errors,
            created_users=created_users,
            row_results=row_results,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process Excel file: {str(e)}")


