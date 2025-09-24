#!/usr/bin/env python3
"""
Fix migration conflicts
======================

This script handles migration conflicts by checking what's already applied
and setting the correct alembic version.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Add backend to path
sys.path.append(str(Path(__file__).parent))

def get_database_url():
    """Get database URL from environment variables."""
    load_dotenv()
    return os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")

def check_existing_columns():
    """Check what columns already exist in the database."""
    print("🔍 Checking existing database structure...")
    
    database_url = get_database_url()
    if not database_url:
        print("❌ No database URL found in environment variables")
        return False
    
    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            # Check users table columns
            result = conn.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                ORDER BY column_name;
            """))
            users_columns = {row[0]: row[1] for row in result}
            print(f"📋 Users table columns: {list(users_columns.keys())}")
            
            # Check if specific columns exist
            has_company_name = 'company_name' in users_columns
            has_first_name = 'first_name' in users_columns
            has_last_name = 'last_name' in users_columns
            has_shanyrak = 'shanyrak' in users_columns
            has_curator_id = 'curator_id' in users_columns
            
            print(f"   company_name: {'✅' if has_company_name else '❌'}")
            print(f"   first_name: {'✅' if has_first_name else '❌'}")
            print(f"   last_name: {'✅' if has_last_name else '❌'}")
            print(f"   shanyrak: {'✅' if has_shanyrak else '❌'}")
            print(f"   curator_id: {'✅' if has_curator_id else '❌'}")
            
            # Check subjects table
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'subjects'
                );
            """))
            has_subjects = result.scalar()
            print(f"   subjects table: {'✅' if has_subjects else '❌'}")
            
            # Determine which migration to stamp
            if has_company_name and has_first_name and has_last_name and has_shanyrak and has_curator_id and has_subjects:
                print("🎯 Database appears to be fully migrated")
                return "a2c672f37bbf"  # Latest migration
            elif has_company_name and has_first_name and has_last_name and has_shanyrak and has_curator_id:
                print("🎯 Database has user profile fields")
                return "a2c672f37bbf"
            elif has_company_name:
                print("🎯 Database has company_name")
                return "a055c33aee96"
            else:
                print("🎯 Database appears to be at base migration")
                return "4edab55ad5f6"
            
    except Exception as e:
        print(f"❌ Error checking database: {e}")
        return False

def stamp_correct_version(version):
    """Stamp the correct alembic version."""
    print(f"🏷️  Stamping version {version}...")
    
    try:
        from alembic.config import Config
        from alembic import command
        
        database_url = get_database_url()
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", database_url)
        
        command.stamp(alembic_cfg, version)
        print(f"✅ Stamped version {version}")
        return True
        
    except Exception as e:
        print(f"❌ Error stamping version: {e}")
        return False

def main():
    print("🔧 Fixing migration conflicts...")
    
    # Check what's already in the database
    correct_version = check_existing_columns()
    
    if correct_version:
        # Stamp the correct version
        if stamp_correct_version(correct_version):
            print("✅ Migration conflicts fixed!")
            print("🚀 You can now run: python migrate_production.py --apply")
        else:
            print("❌ Failed to stamp correct version")
    else:
        print("❌ Could not determine correct version")

if __name__ == "__main__":
    main()
