# fix_all_database_issues.py
"""
Complete fix for all database schema issues in Workforce Scheduler
This script adds ALL missing columns based on the actual errors from the logs
"""

import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import ProgrammingError, OperationalError
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_database_url():
    """Get and fix database URL"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        logger.error("No DATABASE_URL environment variable found!")
        logger.info("Set it with: export DATABASE_URL='your-database-url'")
        sys.exit(1)
    
    # Fix postgres:// to postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    return database_url

def check_and_add_column(conn, table_name, column_name, column_definition):
    """Check if column exists and add if missing"""
    try:
        # Check if column exists
        result = conn.execute(text(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = :table_name AND column_name = :column_name
        """), {"table_name": table_name, "column_name": column_name})
        
        if result.fetchone() is None:
            # Column doesn't exist, add it
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"))
            conn.commit()
            logger.info(f"✓ Added {table_name}.{column_name}")
            return True
        else:
            logger.info(f"  {table_name}.{column_name} already exists")
            return False
    except Exception as e:
        logger.error(f"✗ Failed to add {table_name}.{column_name}: {str(e)}")
        conn.rollback()
        return False

def main():
    """Run all database fixes"""
    logger.info("Starting Complete Database Fix...")
    logger.info("="*60)
    
    # Get database connection
    database_url = get_database_url()
    engine = create_engine(database_url)
    
    fixes_applied = 0
    errors = 0
    
    with engine.connect() as conn:
        logger.info("\n1. Fixing position table...")
        if check_and_add_column(conn, "position", "requires_certification", "BOOLEAN DEFAULT FALSE"):
            fixes_applied += 1
        if check_and_add_column(conn, "position", "min_coverage", "INTEGER DEFAULT 0"):
            fixes_applied += 1
        if check_and_add_column(conn, "position", "department", "VARCHAR(100)"):
            fixes_applied += 1
        
        logger.info("\n2. Fixing time_off_request table...")
        if check_and_add_column(conn, "time_off_request", "type", "VARCHAR(50) DEFAULT 'vacation'"):
            fixes_applied += 1
        if check_and_add_column(conn, "time_off_request", "request_type", "VARCHAR(50) DEFAULT 'vacation'"):
            fixes_applied += 1
        if check_and_add_column(conn, "time_off_request", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"):
            fixes_applied += 1
        if check_and_add_column(conn, "time_off_request", "approved_by_id", "INTEGER REFERENCES employee(id)"):
            fixes_applied += 1
        if check_and_add_column(conn, "time_off_request", "approved_date", "TIMESTAMP"):
            fixes_applied += 1
        
        logger.info("\n3. Fixing shift_swap_request table...")
        # First check if table exists
        table_check = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'shift_swap_request'
            )
        """))
        
        if not table_check.scalar():
            # Create the table
            logger.info("  Creating shift_swap_request table...")
            try:
                conn.execute(text("""
                    CREATE TABLE shift_swap_request (
                        id SERIAL PRIMARY KEY,
                        requester_id INTEGER REFERENCES employee(id),
                        target_employee_id INTEGER REFERENCES employee(id),
                        requester_date DATE,
                        requester_shift VARCHAR(20),
                        target_date DATE,
                        target_shift VARCHAR(20),
                        status VARCHAR(20) DEFAULT 'pending',
                        reason TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        processed_at TIMESTAMP
                    )
                """))
                conn.commit()
                logger.info("✓ Created shift_swap_request table")
                fixes_applied += 1
            except Exception as e:
                logger.error(f"✗ Failed to create shift_swap_request table: {str(e)}")
                conn.rollback()
                errors += 1
        else:
            # Add missing columns
            if check_and_add_column(conn, "shift_swap_request", "requester_date", "DATE"):
                fixes_applied += 1
            if check_and_add_column(conn, "shift_swap_request", "requester_shift", "VARCHAR(20)"):
                fixes_applied += 1
            if check_and_add_column(conn, "shift_swap_request", "target_date", "DATE"):
                fixes_applied += 1
            if check_and_add_column(conn, "shift_swap_request", "target_shift", "VARCHAR(20)"):
                fixes_applied += 1
            if check_and_add_column(conn, "shift_swap_request", "target_employee_id", "INTEGER REFERENCES employee(id)"):
                fixes_applied += 1
        
        logger.info("\n4. Fixing employee table...")
        if check_and_add_column(conn, "employee", "is_active", "BOOLEAN DEFAULT TRUE"):
            fixes_applied += 1
        if check_and_add_column(conn, "employee", "is_admin", "BOOLEAN DEFAULT FALSE"):
            fixes_applied += 1
        if check_and_add_column(conn, "employee", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"):
            fixes_applied += 1
        if check_and_add_column(conn, "employee", "updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"):
            fixes_applied += 1
        if check_and_add_column(conn, "employee", "max_hours_per_week", "INTEGER DEFAULT 40"):
            fixes_applied += 1
        
        logger.info("\n5. Fixing coverage and schedule related tables...")
        # Check if coverage_gap table exists
        table_check = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'coverage_gap'
            )
        """))
        
        if not table_check.scalar():
            try:
                conn.execute(text("""
                    CREATE TABLE coverage_gap (
                        id SERIAL PRIMARY KEY,
                        date DATE NOT NULL,
                        position_id INTEGER REFERENCES position(id),
                        shift VARCHAR(20),
                        required_count INTEGER DEFAULT 1,
                        scheduled_count INTEGER DEFAULT 0,
                        is_filled BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                conn.commit()
                logger.info("✓ Created coverage_gap table")
                fixes_applied += 1
            except Exception as e:
                logger.error(f"✗ Failed to create coverage_gap table: {str(e)}")
                conn.rollback()
                errors += 1
        
        logger.info("\n6. Creating indexes for better performance...")
        indexes = [
            ("idx_employee_email", "employee(email)"),
            ("idx_employee_crew", "employee(crew)"),
            ("idx_time_off_status", "time_off_request(status)"),
            ("idx_shift_swap_status", "shift_swap_request(status)"),
            ("idx_position_name", "position(name)")
        ]
        
        for index_name, index_definition in indexes:
            try:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {index_definition}"))
                conn.commit()
                logger.info(f"✓ Created index {index_name}")
            except Exception as e:
                logger.warning(f"  Could not create index {index_name}: {str(e)}")
                conn.rollback()
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("SUMMARY")
    logger.info("="*60)
    logger.info(f"✓ Fixes applied: {fixes_applied}")
    if errors > 0:
        logger.error(f"✗ Errors: {errors}")
    logger.info("="*60)
    
    if errors == 0:
        logger.info("\n✓ All database fixes completed successfully!")
        logger.info("\nNext steps:")
        logger.info("1. Restart your Flask application")
        logger.info("2. Try accessing /supervisor/coverage-needs again")
        logger.info("3. Upload employee data at /upload-employees")
    else:
        logger.error("\n✗ Some fixes failed. Check the errors above.")
    
    return errors == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
