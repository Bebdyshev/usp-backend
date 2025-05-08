from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from config import init_db, get_db, reset_db
from routes.auth import router as auth_router
from routes.grades import router as grades_router
from routes.dashboard import router as dashboard_router
from routes.classes import router as classes_router
from routes.users import router as users_router
import os
import sys
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import text

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

app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(grades_router, prefix="/grades", tags=["Grades"])
app.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(classes_router, prefix="/classes", tags=["Classes"])
app.include_router(users_router, prefix="/users", tags=["Users"])