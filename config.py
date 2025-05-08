from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from schemas.models import Base
import os
from dotenv import load_dotenv

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("POSTGRES_URL")
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    print("Initializing the database...")
    Base.metadata.create_all(bind=engine)
    
    # Run migrations
    with engine.connect() as conn:
        try:
            # Check if columns exist in grades table
            result = conn.execute(text(
                """
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'grades' AND column_name IN ('parallel', 'shanyrak', 'studentcount')
                """
            ))
            columns = [row[0] for row in result]
            
            # Add columns if they don't exist
            if 'parallel' not in columns:
                conn.execute(text("ALTER TABLE grades ADD COLUMN parallel VARCHAR;"))
                print("Added parallel column to grades table")
            
            if 'shanyrak' not in columns:
                conn.execute(text("ALTER TABLE grades ADD COLUMN shanyrak VARCHAR;"))
                print("Added shanyrak column to grades table")
                
            if 'studentcount' not in columns:
                conn.execute(text("ALTER TABLE grades ADD COLUMN studentcount INTEGER DEFAULT 0;"))
                print("Added studentCount column to grades table")
            
            # Create GIN indexes for JSONB columns
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_scores_actual_gin ON scores USING GIN (actual_scores jsonb_path_ops);"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_scores_predicted_gin ON scores USING GIN (predicted_scores jsonb_path_ops);"
            ))
            conn.commit()
            print("GIN indexes created for JSONB columns.")
        except Exception as e:
            print(f"Warning: Could not complete migrations: {e}")
    
    print("Database initialized successfully.")

def reset_db():
    """Drop all tables and recreate them"""
    print("Resetting the database...")
    Base.metadata.drop_all(bind=engine)
    init_db()
    print("Database has been reset.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()