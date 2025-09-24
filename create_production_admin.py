#!/usr/bin/env python3
"""
Create Production Admin
======================

This script creates an admin user for production deployment.
It can be run independently to create or update admin credentials.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add backend to path
sys.path.append(str(Path(__file__).parent))

from schemas.models import UserInDB, Base
from auth_utils import hash_password

def get_database_url():
    """Get database URL from environment variables."""
    load_dotenv()
    return os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")

def create_admin_user():
    """Create or update admin user in production database."""
    print("🔧 Creating production admin user...")
    
    # Get database connection
    database_url = get_database_url()
    if not database_url:
        print("❌ No database URL found in environment variables")
        print("   Please set POSTGRES_URL or DATABASE_URL")
        return False
    
    try:
        # Create database connection
        engine = create_engine(database_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # Get admin credentials from environment or use defaults
        admin_email = os.getenv("ADMIN_EMAIL", "admin@school.kz")
        admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
        admin_name = os.getenv("ADMIN_NAME", "System Administrator")
        admin_first_name = os.getenv("ADMIN_FIRST_NAME", "Admin")
        admin_last_name = os.getenv("ADMIN_LAST_NAME", "System")
        
        print(f"📧 Admin Email: {admin_email}")
        print(f"👤 Admin Name: {admin_name}")
        print(f"🔑 Password: {'*' * len(admin_password)}")
        
        # Check if admin already exists
        existing_admin = db.query(UserInDB).filter(UserInDB.email == admin_email).first()
        
        if existing_admin:
            print(f"⚠️  Admin user already exists: {admin_email}")
            
            # Ask if user wants to update password
            update_password = input("Do you want to update the password? (y/N): ").lower().strip()
            if update_password == 'y':
                existing_admin.hashed_password = hash_password(admin_password)
                existing_admin.name = admin_name
                existing_admin.first_name = admin_first_name
                existing_admin.last_name = admin_last_name
                db.commit()
                print("✅ Admin user updated successfully!")
            else:
                print("ℹ️  Admin user not modified")
        else:
            # Create new admin user
            new_admin = UserInDB(
                name=admin_name,
                first_name=admin_first_name,
                last_name=admin_last_name,
                email=admin_email,
                hashed_password=hash_password(admin_password),
                type="admin",
                is_active=1
            )
            
            db.add(new_admin)
            db.commit()
            print("✅ Admin user created successfully!")
        
        # Verify admin user
        admin_user = db.query(UserInDB).filter(UserInDB.email == admin_email).first()
        if admin_user:
            print(f"✅ Admin user verified: {admin_user.name} ({admin_user.email})")
            print(f"   Type: {admin_user.type}")
            print(f"   Active: {admin_user.is_active}")
            print(f"   Created: {admin_user.created_at}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating admin user: {e}")
        return False
    finally:
        try:
            db.close()
        except Exception:
            pass

def main():
    """Main function."""
    print("🚀 Production Admin Creation Script")
    print("=" * 40)
    
    # Check if we're in production
    if not os.getenv("POSTGRES_URL") and not os.getenv("DATABASE_URL"):
        print("⚠️  Warning: No database URL found in environment variables")
        print("   Make sure to set POSTGRES_URL or DATABASE_URL")
        print()
    
    # Create admin user
    success = create_admin_user()
    
    if success:
        print("\n🎉 Admin user setup completed!")
        print("\n📋 Next steps:")
        print("   1. Start your backend server")
        print("   2. Access the admin panel")
        print("   3. Configure system settings")
        print("   4. Create classes and subjects")
    else:
        print("\n❌ Admin user setup failed!")
        print("   Check your database connection and try again")
        sys.exit(1)

if __name__ == "__main__":
    main()
