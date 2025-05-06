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
    allow_origins=["http://localhost:3000", "http://http://10.10.10.232:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(grades_router, prefix="/grades", tags=["Grades"])
app.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(classes_router, prefix="/classes", tags=["Classes"])

@app.post("/data")
def get_data():
    return {
    "status": "success",
    "attendance_data": [
        {
            "name": "JAFAR",
            "date": "2025-04-06",
            "times": [
                "00:11",
                "00:12",
                "02:11",
                "03:15",
                "03:18",
                "03:20",
                "03:22",
                "03:23",
                "03:29",
                "07:42",
                "08:05",
                "08:06"
            ],
            "attendance_info": [
                {
                    "time": "00:11",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "00:12",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "02:11",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "03:15",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "03:18",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "03:20",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "03:22",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "03:23",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "03:29",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "07:42",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "08:05",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "08:06",
                    "class": 1,
                    "status": "before school"
                }
            ]
        },
        {
            "name": "KEREY",
            "date": "2025-04-06",
            "times": [
                "00:11"
            ],
            "attendance_info": [
                {
                    "time": "00:11",
                    "class": 1,
                    "status": "before school"
                }
            ]
        },
        {
            "name": "AZIZ",
            "date": "2025-04-06",
            "times": [
                "00:12",
                "02:02",
                "02:11",
                "02:16",
                "02:16",
                "02:17",
                "02:17",
                "02:31",
                "08:00",
                "08:00",
                "08:00",
                "08:01",
                "08:01",
                "08:09",
                "08:10"
            ],
            "attendance_info": [
                {
                    "time": "00:12",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "02:02",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "02:11",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "02:16",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "02:16",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "02:17",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "02:17",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "02:31",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "08:00",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "08:00",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "08:00",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "08:01",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "08:01",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "08:09",
                    "class": 1,
                    "status": "late"
                },
                {
                    "time": "08:10",
                    "class": 2,
                    "status": "on time"
                }
            ]
        },
        {
            "name": "MAKSIM",
            "date": "2025-04-06",
            "times": [
                "00:12",
                "02:11",
                "02:18",
                "03:05",
                "03:08",
                "03:08",
                "08:01",
                "08:01",
                "08:01",
                "08:10"
            ],
            "attendance_info": [
                {
                    "time": "00:12",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "02:11",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "02:18",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "03:05",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "03:08",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "03:08",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "08:01",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "08:01",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "08:01",
                    "class": 1,
                    "status": "before school"
                },
                {
                    "time": "08:10",
                    "class": 1,
                    "status": "before school"
                }
            ]
        }
    ]
}