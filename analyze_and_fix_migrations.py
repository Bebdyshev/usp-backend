#!/usr/bin/env python3
"""
Analyze and Fix Migration Conflicts
===================================

This script analyzes the current database state and determines the correct
migration version to stamp, avoiding conflicts with existing structures.
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

def analyze_database_structure():
    """Analyze the current database structure in detail."""
    print("🔍 Analyzing database structure...")
    
    database_url = get_database_url()
    if not database_url:
        print("❌ No database URL found in environment variables")
        return None
    
    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            # Get all tables
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name;
            """))
            tables = [row[0] for row in result]
            print(f"📋 Existing tables: {tables}")
            
            # Check users table structure
            users_columns = {}
            if 'users' in tables:
                result = conn.execute(text("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns 
                    WHERE table_name = 'users' 
                    ORDER BY column_name;
                """))
                users_columns = {row[0]: {'type': row[1], 'nullable': row[2]} for row in result}
                print(f"👤 Users table columns: {list(users_columns.keys())}")
            
            # Check subjects table structure
            subjects_columns = {}
            if 'subjects' in tables:
                result = conn.execute(text("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns 
                    WHERE table_name = 'subjects' 
                    ORDER BY column_name;
                """))
                subjects_columns = {row[0]: {'type': row[1], 'nullable': row[2]} for row in result}
                print(f"📚 Subjects table columns: {list(subjects_columns.keys())}")
            
            # Check grades table structure
            grades_columns = {}
            if 'grades' in tables:
                result = conn.execute(text("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns 
                    WHERE table_name = 'grades' 
                    ORDER BY column_name;
                """))
                grades_columns = {row[0]: {'type': row[1], 'nullable': row[2]} for row in result}
                print(f"🎓 Grades table columns: {list(grades_columns.keys())}")
            
            # Check for specific new tables
            new_tables = [
                'subgroups', 'teacher_assignments', 'curator_assignments', 
                'disciplinary_actions', 'achievements'
            ]
            existing_new_tables = [table for table in new_tables if table in tables]
            print(f"🆕 New management tables: {existing_new_tables}")
            
            return {
                'tables': tables,
                'users_columns': users_columns,
                'subjects_columns': subjects_columns,
                'grades_columns': grades_columns,
                'new_tables': existing_new_tables
            }
            
    except Exception as e:
        print(f"❌ Error analyzing database: {e}")
        return None

def determine_migration_version(analysis):
    """Determine the correct migration version based on database analysis."""
    if not analysis:
        return None
    
    print("\n🎯 Determining migration version...")
    
    # Check for latest features
    has_applicable_parallels = 'applicable_parallels' in analysis.get('subjects_columns', {})
    has_curator_id = 'curator_id' in analysis.get('grades_columns', {})
    has_user_profile_fields = all(field in analysis.get('users_columns', {}) 
                                 for field in ['first_name', 'last_name', 'shanyrak'])
    has_new_tables = len(analysis.get('new_tables', [])) > 0
    
    print(f"   applicable_parallels in subjects: {'✅' if has_applicable_parallels else '❌'}")
    print(f"   curator_id in grades: {'✅' if has_curator_id else '❌'}")
    print(f"   user profile fields: {'✅' if has_user_profile_fields else '❌'}")
    print(f"   new management tables: {'✅' if has_new_tables else '❌'}")
    
    # Determine version based on what's implemented
    if has_applicable_parallels:
        print("🎯 Database appears to be at latest version (812064162958)")
        return "812064162958"
    elif has_curator_id and has_user_profile_fields:
        print("🎯 Database has user profile fields and curator relationship (a2c672f37bbf)")
        return "a2c672f37bbf"
    elif has_new_tables:
        print("🎯 Database has new management tables (f9283a28ea65)")
        return "f9283a28ea65"
    elif 'subjects' in analysis.get('tables', []):
        print("🎯 Database has subjects table (a055c33aee96)")
        return "a055c33aee96"
    elif 'company_name' in analysis.get('users_columns', {}):
        print("🎯 Database has company_name (93262454752a)")
        return "93262454752a"
    else:
        print("🎯 Database appears to be at base version (4edab55ad5f6)")
        return "4edab55ad5f6"

def stamp_migration_version(version):
    """Stamp the determined migration version."""
    print(f"\n🏷️  Stamping version {version}...")
    
    try:
        from alembic.config import Config
        from alembic import command
        
        database_url = get_database_url()
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", database_url)
        
        command.stamp(alembic_cfg, version)
        print(f"✅ Successfully stamped version {version}")
        return True
        
    except Exception as e:
        print(f"❌ Error stamping version: {e}")
        return False

def check_pending_migrations():
    """Check what migrations are pending after stamping."""
    print("\n📋 Checking pending migrations...")
    
    try:
        from alembic.config import Config
        from alembic import command
        
        database_url = get_database_url()
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", database_url)
        
        # Get current version
        result = command.current(alembic_cfg)
        print(f"📍 Current version: {result}")
        
        # Get pending migrations
        command.heads(alembic_cfg)
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking migrations: {e}")
        return False

def main():
    print("🔧 Analyzing and fixing migration conflicts...")
    print("=" * 50)
    
    # Step 1: Analyze database structure
    analysis = analyze_database_structure()
    if not analysis:
        print("❌ Failed to analyze database")
        return
    
    # Step 2: Determine correct version
    version = determine_migration_version(analysis)
    if not version:
        print("❌ Could not determine migration version")
        return
    
    # Step 3: Stamp the version
    if stamp_migration_version(version):
        print(f"\n✅ Successfully set database to version {version}")
        
        # Step 4: Check what's pending
        if check_pending_migrations():
            print("\n🚀 You can now run: python migrate_production.py --apply")
            print("   This will apply only the remaining migrations safely.")
        else:
            print("\n🎉 Database is up to date! No migrations needed.")
    else:
        print("❌ Failed to stamp migration version")

if __name__ == "__main__":
    main()
