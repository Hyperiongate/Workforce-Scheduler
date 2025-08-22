#!/usr/bin/env python3
"""
Database Schema Fix Script
Fixes missing columns in the database that are causing errors
Run this script to add missing columns to existing tables
"""

from app import app, db
from sqlalchemy import text, inspect
from sqlalchemy.exc import ProgrammingError
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_and_add_column(table_name, column_name, column_type, default_value=None):
    """Check if a column exists and add it if missing"""
    try:
        # Check if column exists
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        
        if column_name not in columns:
            logger.info(f"Adding missing column {column_name} to {table_name}")
            
            # Build the ALTER TABLE statement
            alter_stmt = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            if default_value is not None:
                alter_stmt += f" DEFAULT {default_value}"
            
            # Execute the statement
            with db.engine.connect() as conn:
                conn.execute(text(alter_stmt))
                conn.commit()
            
            logger.info(f"✓ Successfully added {column_name} to {table_name}")
            return True
        else:
            logger.info(f"✓ Column {column_name} already exists in {table_name}")
            return False
            
    except Exception as e:
        logger.error(f"Error adding column {column_name} to {table_name}: {e}")
        return False

def fix_database_schema():
    """Fix all missing columns in the database"""
    with app.app_context():
        logger.info("Starting database schema fix...")
        
        fixes_applied = []
        
        # Fix 1: Add is_training column to schedule table
        if check_and_add_column('schedule', 'is_training', 'BOOLEAN', 'FALSE'):
            fixes_applied.append("Added is_training to schedule table")
        
        # Fix 2: Add type column to time_off_request table (alias for request_type)
        # First check if request_type exists
        inspector = inspect(db.engine)
        time_off_columns = [col['name'] for col in inspector.get_columns('time_off_request')]
        
        if 'type' not in time_off_columns:
            if 'request_type' in time_off_columns:
                # Create a computed column or view that aliases request_type as type
                logger.info("Creating type column as alias for request_type")
                try:
                    with db.engine.connect() as conn:
                        # Add type column that mirrors request_type
                        conn.execute(text("""
                            ALTER TABLE time_off_request 
                            ADD COLUMN type VARCHAR(50);
                        """))
                        # Copy existing data
                        conn.execute(text("""
                            UPDATE time_off_request 
                            SET type = request_type 
                            WHERE type IS NULL;
                        """))
                        conn.commit()
                    fixes_applied.append("Added type column to time_off_request table")
                except Exception as e:
                    logger.warning(f"Could not add type column: {e}")
            else:
                # Add both columns
                check_and_add_column('time_off_request', 'type', 'VARCHAR(50)', "'vacation'")
                check_and_add_column('time_off_request', 'request_type', 'VARCHAR(50)', "'vacation'")
                fixes_applied.append("Added type and request_type columns to time_off_request table")
        
        # Fix 3: Ensure all required columns exist in overtime_history
        overtime_columns = [
            ('overtime_hours', 'NUMERIC', '0'),
            ('hours', 'NUMERIC', '0'),
            ('regular_hours', 'NUMERIC', '40'),
            ('total_hours', 'NUMERIC', '40'),
            ('week_start_date', 'DATE', 'NULL'),
            ('is_current', 'BOOLEAN', 'FALSE')
        ]
        
        for col_name, col_type, default in overtime_columns:
            if check_and_add_column('overtime_history', col_name, col_type, default):
                fixes_applied.append(f"Added {col_name} to overtime_history table")
        
        # Fix 4: Ensure FileUpload table has all required columns
        file_upload_columns = [
            ('total_records', 'INTEGER', '0'),
            ('successful_records', 'INTEGER', '0'),
            ('failed_records', 'INTEGER', '0'),
            ('error_details', 'JSON', 'NULL')
        ]
        
        for col_name, col_type, default in file_upload_columns:
            if check_and_add_column('file_upload', col_name, col_type, default):
                fixes_applied.append(f"Added {col_name} to file_upload table")
        
        # Fix 5: Add any other missing columns that might be needed
        employee_columns = [
            ('department', 'VARCHAR(100)', 'NULL'),
            ('position_name', 'VARCHAR(100)', 'NULL'),
            ('hire_date', 'DATE', 'NULL'),
            ('is_active', 'BOOLEAN', 'TRUE'),
            ('vacation_days', 'NUMERIC', '0'),
            ('sick_days', 'NUMERIC', '0'),
            ('personal_days', 'NUMERIC', '0')
        ]
        
        for col_name, col_type, default in employee_columns:
            if check_and_add_column('employee', col_name, col_type, default):
                fixes_applied.append(f"Added {col_name} to employee table")
        
        # Summary
        logger.info("\n" + "="*50)
        logger.info("DATABASE SCHEMA FIX COMPLETE")
        logger.info("="*50)
        
        if fixes_applied:
            logger.info(f"Applied {len(fixes_applied)} fixes:")
            for fix in fixes_applied:
                logger.info(f"  - {fix}")
        else:
            logger.info("No fixes needed - all columns already exist!")
        
        logger.info("\nDatabase schema is now up to date!")

if __name__ == "__main__":
    fix_database_schema()
