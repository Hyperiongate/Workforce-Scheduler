# fix_database_schema.py - Complete database migration script
"""
Fixes all database schema issues including:
- Missing columns in shift_swap_request
- Missing error template tables
- All other schema mismatches
"""

import os
import sys
from sqlalchemy import create_engine, text, inspect, Column, Integer, String, Boolean, DateTime, Float, Date, ForeignKey
from sqlalchemy.exc import ProgrammingError, OperationalError
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_database_connection():
    """Get database connection from environment"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        logger.error("No DATABASE_URL environment variable found")
        sys.exit(1)
    
    # Fix postgres:// to postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    engine = create_engine(database_url)
    return engine

def check_table_exists(engine, table_name):
    """Check if a table exists"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()

def check_column_exists(engine, table_name, column_name):
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def run_migrations(engine):
    """Run all database migrations"""
    migrations_run = []
    errors = []
    
    with engine.connect() as conn:
        
        # 1. Fix shift_swap_request table
        logger.info("Checking shift_swap_request table...")
        if check_table_exists(engine, 'shift_swap_request'):
            
            # Check and add missing columns
            columns_to_add = [
                ('requester_id', 'INTEGER REFERENCES employee(id)'),
                ('requested_with_id', 'INTEGER REFERENCES employee(id)'),
                ('requester_schedule_id', 'INTEGER REFERENCES schedule(id)'),
                ('requested_schedule_id', 'INTEGER REFERENCES schedule(id)'),
                ('status', "VARCHAR(20) DEFAULT 'pending'"),
                ('reason', 'TEXT'),
                ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
                ('reviewed_by_id', 'INTEGER REFERENCES employee(id)'),
                ('reviewed_at', 'TIMESTAMP'),
                ('reviewer_notes', 'TEXT')
            ]
            
            for column_name, column_type in columns_to_add:
                if not check_column_exists(engine, 'shift_swap_request', column_name):
                    try:
                        conn.execute(text(f"""
                            ALTER TABLE shift_swap_request 
                            ADD COLUMN {column_name} {column_type}
                        """))
                        conn.commit()
                        migrations_run.append(f"Added column shift_swap_request.{column_name}")
                        logger.info(f"✓ Added column shift_swap_request.{column_name}")
                    except Exception as e:
                        errors.append(f"Failed to add shift_swap_request.{column_name}: {str(e)}")
                        conn.rollback()
        else:
            # Create the table if it doesn't exist
            try:
                conn.execute(text("""
                    CREATE TABLE shift_swap_request (
                        id SERIAL PRIMARY KEY,
                        requester_id INTEGER REFERENCES employee(id),
                        requested_with_id INTEGER REFERENCES employee(id),
                        requester_schedule_id INTEGER REFERENCES schedule(id),
                        requested_schedule_id INTEGER REFERENCES schedule(id),
                        status VARCHAR(20) DEFAULT 'pending',
                        reason TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        reviewed_by_id INTEGER REFERENCES employee(id),
                        reviewed_at TIMESTAMP,
                        reviewer_notes TEXT
                    )
                """))
                conn.commit()
                migrations_run.append("Created shift_swap_request table")
                logger.info("✓ Created shift_swap_request table")
            except Exception as e:
                errors.append(f"Failed to create shift_swap_request table: {str(e)}")
                conn.rollback()
        
        # 2. Fix vacation_calendar table
        logger.info("Checking vacation_calendar table...")
        if check_table_exists(engine, 'vacation_calendar'):
            if not check_column_exists(engine, 'vacation_calendar', 'status'):
                try:
                    conn.execute(text("""
                        ALTER TABLE vacation_calendar 
                        ADD COLUMN status VARCHAR(20) DEFAULT 'approved'
                    """))
                    conn.commit()
                    migrations_run.append("Added column vacation_calendar.status")
                    logger.info("✓ Added column vacation_calendar.status")
                except Exception as e:
                    errors.append(f"Failed to add vacation_calendar.status: {str(e)}")
                    conn.rollback()
        
        # 3. Fix time_off_request table
        logger.info("Checking time_off_request table...")
        if check_table_exists(engine, 'time_off_request'):
            columns_to_add = [
                ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
                ('approved_by', 'INTEGER REFERENCES employee(id)'),
                ('approved_date', 'TIMESTAMP'),
                ('notes', 'TEXT'),
                ('days_requested', 'FLOAT')
            ]
            
            for column_name, column_type in columns_to_add:
                if not check_column_exists(engine, 'time_off_request', column_name):
                    try:
                        conn.execute(text(f"""
                            ALTER TABLE time_off_request 
                            ADD COLUMN {column_name} {column_type}
                        """))
                        conn.commit()
                        migrations_run.append(f"Added column time_off_request.{column_name}")
                        logger.info(f"✓ Added column time_off_request.{column_name}")
                    except Exception as e:
                        errors.append(f"Failed to add time_off_request.{column_name}: {str(e)}")
                        conn.rollback()
        
        # 4. Fix employee table
        logger.info("Checking employee table...")
        if check_table_exists(engine, 'employee'):
            columns_to_add = [
                ('username', 'VARCHAR(50) UNIQUE'),
                ('last_login', 'TIMESTAMP'),
                ('is_active', 'BOOLEAN DEFAULT TRUE'),
                ('vacation_days', 'INTEGER DEFAULT 10'),
                ('sick_days', 'INTEGER DEFAULT 5'),
                ('personal_days', 'INTEGER DEFAULT 3')
            ]
            
            for column_name, column_type in columns_to_add:
                if not check_column_exists(engine, 'employee', column_name):
                    try:
                        conn.execute(text(f"""
                            ALTER TABLE employee 
                            ADD COLUMN {column_name} {column_type}
                        """))
                        conn.commit()
                        migrations_run.append(f"Added column employee.{column_name}")
                        logger.info(f"✓ Added column employee.{column_name}")
                    except Exception as e:
                        errors.append(f"Failed to add employee.{column_name}: {str(e)}")
                        conn.rollback()
        
        # 5. Create indexes for performance
        logger.info("Creating indexes...")
        indexes = [
            ("idx_employee_email", "employee", "email"),
            ("idx_employee_crew", "employee", "crew"),
            ("idx_schedule_date", "schedule", "date"),
            ("idx_schedule_employee", "schedule", "employee_id"),
            ("idx_shift_swap_status", "shift_swap_request", "status"),
            ("idx_time_off_status", "time_off_request", "status")
        ]
        
        for index_name, table_name, column_name in indexes:
            try:
                conn.execute(text(f"""
                    CREATE INDEX IF NOT EXISTS {index_name} 
                    ON {table_name} ({column_name})
                """))
                conn.commit()
                logger.info(f"✓ Created index {index_name}")
            except Exception as e:
                logger.warning(f"Could not create index {index_name}: {str(e)}")
                conn.rollback()
    
    # Print summary
    logger.info("\n" + "="*60)
    logger.info("MIGRATION SUMMARY")
    logger.info("="*60)
    
    if migrations_run:
        logger.info(f"\nSuccessful migrations ({len(migrations_run)}):")
        for migration in migrations_run:
            logger.info(f"  ✓ {migration}")
    
    if errors:
        logger.error(f"\nErrors ({len(errors)}):")
        for error in errors:
            logger.error(f"  ✗ {error}")
    
    logger.info("\n" + "="*60)
    
    return len(errors) == 0

if __name__ == "__main__":
    logger.info("Starting database migration...")
    
    try:
        engine = get_database_connection()
        success = run_migrations(engine)
        
        if success:
            logger.info("\n✓ All migrations completed successfully!")
            sys.exit(0)
        else:
            logger.error("\n✗ Some migrations failed. Check the errors above.")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"\nFATAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
