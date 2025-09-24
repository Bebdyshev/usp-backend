#!/usr/bin/env python3
"""
Fix Alembic version table
========================

This script fixes the alembic_version table when there's a missing revision.
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

def fix_alembic_version():
    """Fix the alembic_version table."""
    print("🔧 Fixing Alembic version table...")
    
    database_url = get_database_url()
    if not database_url:
        print("❌ No database URL found in environment variables")
        return False
    
    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            # Check if alembic_version table exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'alembic_version'
                );
            """))
            alembic_exists = result.scalar()
            
            if alembic_exists:
                print("📊 Current alembic_version table:")
                result = conn.execute(text("SELECT version_num FROM alembic_version;"))
                current_version = result.scalar()
                print(f"   Current version: {current_version}")
                
                # Delete the problematic version
                print("🗑️  Deleting problematic version...")
                conn.execute(text("DELETE FROM alembic_version;"))
                conn.commit()
                print("✅ Alembic version table cleared")
            else:
                print("ℹ️  Alembic version table doesn't exist")
            
            return True
            
    except Exception as e:
        print(f"❌ Error fixing alembic version: {e}")
        return False

if __name__ == "__main__":
    fix_alembic_version()
