from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from config import init_db, get_db, reset_db
from routes.auth import router as auth_router
from routes.grades import router as grades_router
from routes.dashboard import router as dashboard_router
from routes.classes import router as classes_router
from routes.users import router as users_router
from routes.subjects import router as subjects_router
from routes.subgroups import router as subgroups_router
from routes.assignments import router as assignments_router
from routes.curators import router as curators_router
from routes.discipline import router as discipline_router
from routes.achievements import router as achievements_router
import os
import sys
import subprocess
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import text
from auth_utils import hash_password
from schemas.models import UserInDB

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

# Ensure default admin account exists so the operator can log in
def ensure_default_admin():
    try:
        # Use dependency to get a DB session
        db_gen = get_db()
        db: Session = next(db_gen)

        admin_email = os.getenv("ADMIN_EMAIL", "admin@gmail.com")
        admin_password = os.getenv("ADMIN_PASSWORD", "admin12345")
        admin_name = os.getenv("ADMIN_NAME", "Administrator")

        existing_admin = db.query(UserInDB).filter(UserInDB.email == admin_email).first()
        if not existing_admin:
            new_admin = UserInDB(
                name=admin_name,
                email=admin_email,
                hashed_password=hash_password(admin_password),
                type="admin",
            )
            db.add(new_admin)
            db.commit()
            print(f"Default admin created: {admin_email}")
        else:
            print(f"Default admin already exists: {admin_email}")
    except Exception as e:
        print(f"Failed to ensure default admin: {e}")
    finally:
        try:
            db.close()
        except Exception:
            pass

# Create default admin on startup (configurable via env)
ensure_default_admin()

app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(grades_router, prefix="/grades", tags=["Grades"])
app.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(classes_router, prefix="/classes", tags=["Classes"])
app.include_router(users_router, prefix="/users", tags=["Users"])
app.include_router(subjects_router, prefix="/subjects", tags=["Subjects"])
app.include_router(subgroups_router, prefix="/subgroups", tags=["Subgroups"])
app.include_router(assignments_router, prefix="/assignments", tags=["Teacher Assignments"])
app.include_router(curators_router, prefix="/curators", tags=["Curators"])
app.include_router(discipline_router, prefix="/discipline", tags=["Discipline"])
app.include_router(achievements_router, prefix="/achievements", tags=["Achievements"])

# Import settings router
from routes.settings import router as settings_router
app.include_router(settings_router, prefix="/settings", tags=["Settings"])

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "message": "USP Backend is running",
        "version": "2.3.0",
        "update": 20
    }