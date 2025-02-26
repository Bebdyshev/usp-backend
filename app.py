from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import init_db
from routes.auth import router as auth_router
from routes.grades import router as grades_router
from routes.dashboard import router as dashboard_router
from routes.classes import router as classes_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(grades_router, prefix="/grades", tags=["Grades"])
app.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(classes_router, prefix="/classes", tags=["Classes"])