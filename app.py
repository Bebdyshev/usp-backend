from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from config import init_db, get_db, reset_db
from routes.auth import router as auth_router
from routes.grades import router as grades_router
from routes.dashboard import router as dashboard_router
from routes.classes import router as classes_router
from routes.users import router as users_router
from routes.subjects import router as subjects_router
import os
import sys
import subprocess
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import text

load_dotenv()

# Автоматический запуск миграций при старте приложения
def run_migrations():
    """Запускает миграции Alembic при старте приложения"""
    try:
        if os.getenv("RUN_MIGRATIONS", "false").lower() == "true":
            print("Running database migrations...")
            result = subprocess.run(["alembic", "upgrade", "head"], 
                                  capture_output=True, text=True, check=True)
            print("Migrations completed successfully!")
            print(result.stdout)
        else:
            print("Migrations skipped (RUN_MIGRATIONS not set to true)")
    except subprocess.CalledProcessError as e:
        print(f"Migration failed: {e}")
        print(f"Error output: {e.stderr}")
        # Не останавливаем приложение, если миграции не удались
    except Exception as e:
        print(f"Unexpected error during migration: {e}")

# Запускаем миграции при старте
run_migrations()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(grades_router, prefix="/grades", tags=["Grades"])
app.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(classes_router, prefix="/classes", tags=["Classes"])
app.include_router(users_router, prefix="/users", tags=["Users"])
app.include_router(subjects_router, prefix="/subjects", tags=["Subjects"])

# Import settings router
from routes.settings import router as settings_router
app.include_router(settings_router, prefix="/settings", tags=["Settings"])

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "message": "USP Backend is running",
        "version": "2.1.0",
        "update": 15
    }