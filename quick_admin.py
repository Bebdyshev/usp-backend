#!/usr/bin/env python3
"""
Quick Admin Creation
===================

Quick script to create admin user with minimal setup.
Usage: python quick_admin.py [email] [password] [name]
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add backend to path
sys.path.append(str(Path(__file__).parent))

from schemas.models import UserInDB
from auth_utils import hash_password

def quick_admin():
    """Quick admin creation."""
    # Get parameters from command line or use defaults
    admin_email = sys.argv[1] if len(sys.argv) > 1 else "beder_a@akb.nis.edu.kz"
    admin_password = sys.argv[2] if len(sys.argv) > 2 else "123"
    admin_name = sys.argv[3] if len(sys.argv) > 3 else "Beder Askar Almatuly"
    
    print(f"Creating admin: {admin_email}")
    
    # Get database URL
    load_dotenv()
    database_url = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
    
    if not database_url:
        print("❌ No database URL found. Set POSTGRES_URL or DATABASE_URL")
        return False
    
    try:
        # Connect to database
        engine = create_engine(database_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # Check if admin exists
        existing = db.query(UserInDB).filter(UserInDB.email == admin_email).first()
        if existing:
            print(f"⚠️  Admin already exists: {admin_email}")
            return True
        
        # Create admin
        admin = UserInDB(
            name=admin_name,
            first_name="Admin",
            last_name="System", 
            email=admin_email,
            hashed_password=hash_password(admin_password),
            type="admin",
            is_active=1
        )
        
        db.add(admin)
        db.commit()
        print(f"✅ Admin created: {admin_email}")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        try:
            db.close()
        except:
            pass

if __name__ == "__main__":
    quick_admin()
