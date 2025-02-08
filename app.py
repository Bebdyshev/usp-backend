from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import init_db
from routes.auth import router
from routes.grades import router as grades_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

app.include_router(router, prefix="/auth", tags=["Auth"])
app.include_router(grades_router, prefix="/grades", tags=["Grades"])