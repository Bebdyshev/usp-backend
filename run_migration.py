#!/usr/bin/env python3
"""Run alembic migrations with automatic .env loading"""

import os
import sys
from dotenv import load_dotenv
from alembic import command
from alembic.config import Config

# Load environment variables
load_dotenv()

# Check if DATABASE_URL is set
database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("ERROR: DATABASE_URL not found in .env file")
    sys.exit(1)

print(f"Using database: {database_url.split('@')[1] if '@' in database_url else 'unknown'}")

# Configure alembic
alembic_cfg = Config("alembic.ini")
alembic_cfg.set_main_option("sqlalchemy.url", database_url)

# Run upgrade
try:
    command.upgrade(alembic_cfg, "head")
    print("\n✅ Migration completed successfully!")
except Exception as e:
    print(f"\n❌ Migration failed: {e}")
    sys.exit(1)
