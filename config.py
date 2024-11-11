from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

SQLALCHEMY_DATABASE_URL = "sqlite:///./data.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    print("Initializing the database...")
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()