#!/usr/bin/env python3
"""
Production Migration Script
===========================

This script helps safely apply migrations to production database.

Usage:
    python migrate_production.py --check    # Check current migration status
    python migrate_production.py --apply    # Apply migrations
    python migrate_production.py --rollback # Rollback last migration
"""

import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add backend to path
sys.path.append(str(Path(__file__).parent))

from alembic.config import Config
from alembic import command
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text

def get_database_url():
    """Get database URL from environment variables."""
    load_dotenv()
    return os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")

def check_migration_status():
    """Check current migration status."""
    print("🔍 Checking migration status...")
    
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
            
            if not alembic_exists:
                print("⚠️  Alembic version table doesn't exist. This is a fresh database.")
                return True
            
            # Get current version
            result = conn.execute(text("SELECT version_num FROM alembic_version;"))
            current_version = result.scalar()
            print(f"📊 Current migration version: {current_version}")
            
            # Check if tables exist
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
                ORDER BY table_name;
            """))
            tables = [row[0] for row in result]
            print(f"📋 Existing tables: {', '.join(tables)}")
            
            return True
            
    except Exception as e:
        print(f"❌ Error checking migration status: {e}")
        return False

def apply_migrations():
    """Apply pending migrations."""
    print("🚀 Applying migrations...")
    
    database_url = get_database_url()
    if not database_url:
        print("❌ No database URL found in environment variables")
        return False
    
    try:
        # Set up Alembic config
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", database_url)
        
        # Check current status first
        print("📊 Current migration status:")
        command.current(alembic_cfg)
        
        # Show what will be applied
        print("\n📋 Pending migrations:")
        command.history(alembic_cfg)
        
        # Ask for confirmation
        response = input("\n❓ Do you want to apply these migrations? (y/N): ")
        if response.lower() != 'y':
            print("❌ Migration cancelled by user")
            return False
        
        # Apply migrations
        command.upgrade(alembic_cfg, "head")
        print("✅ Migrations applied successfully!")
        
        return True
        
    except Exception as e:
        print(f"❌ Error applying migrations: {e}")
        return False

def rollback_migration():
    """Rollback last migration."""
    print("⏪ Rolling back last migration...")
    
    database_url = get_database_url()
    if not database_url:
        print("❌ No database URL found in environment variables")
        return False
    
    try:
        # Set up Alembic config
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", database_url)
        
        # Show current status
        print("📊 Current migration status:")
        command.current(alembic_cfg)
        
        # Ask for confirmation
        response = input("\n❓ Do you want to rollback the last migration? (y/N): ")
        if response.lower() != 'y':
            print("❌ Rollback cancelled by user")
            return False
        
        # Rollback
        command.downgrade(alembic_cfg, "-1")
        print("✅ Migration rolled back successfully!")
        
        return True
        
    except Exception as e:
        print(f"❌ Error rolling back migration: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Production Migration Tool")
    parser.add_argument("--check", action="store_true", help="Check migration status")
    parser.add_argument("--apply", action="store_true", help="Apply migrations")
    parser.add_argument("--rollback", action="store_true", help="Rollback last migration")
    
    args = parser.parse_args()
    
    if args.check:
        check_migration_status()
    elif args.apply:
        apply_migrations()
    elif args.rollback:
        rollback_migration()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
