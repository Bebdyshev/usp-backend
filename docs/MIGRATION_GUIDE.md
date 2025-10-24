# 🚀 Production Migration Guide

## 📋 Overview

This guide explains how to safely apply database migrations to your production environment.

## 🔧 Prerequisites

1. **Backup your production database** before applying any migrations
2. Ensure you have access to the production database
3. Set up the correct environment variables

## 📝 Environment Setup

Create a `.env` file on your production server with the production database URL:

```bash
# Production Database
POSTGRES_URL=postgresql://username:password@production-host:5432/database_name

# JWT Configuration
SECRET_KEY=your-production-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

## 🛠️ Migration Commands

### 1. Check Current Status
```bash
python migrate_production.py --check
```

### 2. Apply Migrations
```bash
python migrate_production.py --apply
```

### 3. Rollback if Needed
```bash
python migrate_production.py --rollback
```

## 📊 Manual Alembic Commands

If you prefer to use Alembic directly:

```bash
# Check current status
alembic current

# Show migration history
alembic history

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Rollback to specific version
alembic downgrade <revision_id>
```

## ⚠️ Important Notes

### For Fresh Production Database:
If your production database is completely fresh (no existing tables):

1. **Skip the first migration** (4edab55ad5f6) - it's for local development
2. **Apply only the production-safe migrations**:
   ```bash
   alembic upgrade a055c33aee96  # Add missing columns
   alembic upgrade 93262454752a  # Fix JSON columns
   ```

### For Existing Production Database:
If you have existing data in production:

1. **Apply all migrations in order**:
   ```bash
   alembic upgrade head
   ```

## 🔍 Migration Details

### Migration 1: `a055c33aee96` - Add Missing Columns
- Adds new columns to existing tables
- Safe for production (allows NULL values)
- Includes proper indexes

### Migration 2: `93262454752a` - Fix JSON Columns
- Converts JSON to JSONB for better performance
- Adds GIN indexes for JSONB columns
- Creates composite indexes for better query performance

## 🚨 Troubleshooting

### Common Issues:

1. **"Table already exists" error**:
   - This means the first migration was already applied
   - Skip to the next migration

2. **"Column already exists" error**:
   - Some columns might already exist
   - The migration uses `IF NOT EXISTS` where possible

3. **Permission errors**:
   - Ensure your database user has ALTER TABLE permissions
   - Check that the user can create indexes

### Recovery Steps:

1. **Check migration status**:
   ```bash
   alembic current
   ```

2. **View migration history**:
   ```bash
   alembic history --verbose
   ```

3. **Manual rollback if needed**:
   ```bash
   alembic downgrade <previous_revision>
   ```

## 📞 Support

If you encounter issues:
1. Check the migration logs
2. Verify database permissions
3. Ensure all environment variables are set correctly
4. Test migrations on a staging environment first

## 🔒 Security Notes

- Never commit production database URLs to version control
- Use environment variables for all sensitive configuration
- Always backup before applying migrations
- Test migrations on staging environment first
