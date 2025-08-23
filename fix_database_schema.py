# fix_database_schema.py
"""
Complete database schema fix script
Run this to fix all database schema issues properly
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, inspect
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

# Database configuration
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workforce.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

def check_table_exists(table_name):
    """Check if a table exists in the database"""
    inspector = inspect(db.engine)
    return table_name in inspector.get_table_names()

def check_column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    inspector = inspect(db.engine)
    if not check_table_exists(table_name):
        return False
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def fix_file_upload_table():
    """Fix the file_upload table schema"""
    logger.info("Checking file_upload table...")
    
    with app.app_context():
        try:
            # Check if table exists
            if not check_table_exists('file_upload'):
                logger.info("Creating file_upload table...")
                db.session.execute(text("""
                    CREATE TABLE file_upload (
                        id SERIAL PRIMARY KEY,
                        filename VARCHAR(255) NOT NULL,
                        upload_type VARCHAR(50),
                        file_type VARCHAR(50),
                        uploaded_by_id INTEGER REFERENCES employee(id),
                        total_records INTEGER DEFAULT 0,
                        successful_records INTEGER DEFAULT 0,
                        failed_records INTEGER DEFAULT 0,
                        records_processed INTEGER DEFAULT 0,
                        records_failed INTEGER DEFAULT 0,
                        error_details TEXT,
                        status VARCHAR(50) DEFAULT 'pending',
                        file_path VARCHAR(255),
                        file_size INTEGER,
                        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                db.session.commit()
                logger.info("✓ Created file_upload table")
            else:
                # Add missing columns
                missing_columns = [
                    ("total_records", "INTEGER DEFAULT 0"),
                    ("successful_records", "INTEGER DEFAULT 0"),
                    ("failed_records", "INTEGER DEFAULT 0"),
                    ("records_processed", "INTEGER DEFAULT 0"),
                    ("records_failed", "INTEGER DEFAULT 0"),
                    ("error_details", "TEXT"),
                    ("status", "VARCHAR(50) DEFAULT 'pending'"),
                    ("file_path", "VARCHAR(255)"),
                    ("file_size", "INTEGER")
                ]
                
                for column_name, column_type in missing_columns:
                    if not check_column_exists('file_upload', column_name):
                        try:
                            db.session.execute(text(f"""
                                ALTER TABLE file_upload 
                                ADD COLUMN {column_name} {column_type}
                            """))
                            db.session.commit()
                            logger.info(f"✓ Added column: file_upload.{column_name}")
                        except Exception as e:
                            db.session.rollback()
                            logger.error(f"✗ Error adding {column_name}: {e}")
                    else:
                        logger.info(f"- Column file_upload.{column_name} already exists")
                        
        except Exception as e:
            logger.error(f"Error fixing file_upload table: {e}")
            db.session.rollback()

def fix_employee_table():
    """Fix the employee table schema"""
    logger.info("Checking employee table...")
    
    with app.app_context():
        try:
            if check_table_exists('employee'):
                # Add missing columns
                missing_columns = [
                    ("first_name", "VARCHAR(100)"),
                    ("last_name", "VARCHAR(100)"),
                    ("employee_id", "VARCHAR(50) UNIQUE"),
                    ("crew", "VARCHAR(10)"),
                    ("position_id", "INTEGER REFERENCES position(id)"),
                    ("department", "VARCHAR(100)"),
                    ("hire_date", "DATE"),
                    ("phone", "VARCHAR(20)"),
                    ("is_active", "BOOLEAN DEFAULT TRUE"),
                    ("email", "VARCHAR(255) UNIQUE"),
                    ("password_hash", "VARCHAR(255)"),
                    ("name", "VARCHAR(255)"),
                    ("is_supervisor", "BOOLEAN DEFAULT FALSE"),
                    ("is_admin", "BOOLEAN DEFAULT FALSE"),
                    ("max_hours_per_week", "INTEGER DEFAULT 40"),
                    ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
                    ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                ]
                
                for column_name, column_type in missing_columns:
                    if not check_column_exists('employee', column_name):
                        try:
                            # Special handling for email - might not need UNIQUE constraint
                            if column_name == 'email':
                                db.session.execute(text(f"""
                                    ALTER TABLE employee 
                                    ADD COLUMN {column_name} VARCHAR(255)
                                """))
                            else:
                                db.session.execute(text(f"""
                                    ALTER TABLE employee 
                                    ADD COLUMN {column_name} {column_type}
                                """))
                            db.session.commit()
                            logger.info(f"✓ Added column: employee.{column_name}")
                        except Exception as e:
                            db.session.rollback()
                            logger.error(f"✗ Error adding employee.{column_name}: {e}")
                    else:
                        logger.info(f"- Column employee.{column_name} already exists")
                        
        except Exception as e:
            logger.error(f"Error fixing employee table: {e}")
            db.session.rollback()

def fix_position_table():
    """Create or fix the position table"""
    logger.info("Checking position table...")
    
    with app.app_context():
        try:
            if not check_table_exists('position'):
                logger.info("Creating position table...")
                db.session.execute(text("""
                    CREATE TABLE position (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(100) UNIQUE NOT NULL,
                        description TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                db.session.commit()
                logger.info("✓ Created position table")
                
                # Add default positions
                default_positions = [
                    'Operator',
                    'Senior Operator',
                    'Lead Operator',
                    'Maintenance Technician',
                    'Electrician',
                    'Mechanic',
                    'Control Room Operator',
                    'Shift Supervisor',
                    'Process Engineer',
                    'Safety Coordinator'
                ]
                
                for pos in default_positions:
                    try:
                        db.session.execute(text("""
                            INSERT INTO position (name) VALUES (:name)
                            ON CONFLICT (name) DO NOTHING
                        """), {"name": pos})
                    except:
                        pass
                db.session.commit()
                logger.info("✓ Added default positions")
                
        except Exception as e:
            logger.error(f"Error fixing position table: {e}")
            db.session.rollback()

def fix_overtime_history_table():
    """Create or fix the overtime_history table"""
    logger.info("Checking overtime_history table...")
    
    with app.app_context():
        try:
            if not check_table_exists('overtime_history'):
                logger.info("Creating overtime_history table...")
                db.session.execute(text("""
                    CREATE TABLE overtime_history (
                        id SERIAL PRIMARY KEY,
                        employee_id INTEGER REFERENCES employee(id),
                        week_starting DATE NOT NULL,
                        hours DECIMAL(5,2) DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(employee_id, week_starting)
                    )
                """))
                db.session.commit()
                logger.info("✓ Created overtime_history table")
            else:
                # Check for missing columns
                if not check_column_exists('overtime_history', 'hours'):
                    db.session.execute(text("""
                        ALTER TABLE overtime_history 
                        ADD COLUMN hours DECIMAL(5,2) DEFAULT 0
                    """))
                    db.session.commit()
                    logger.info("✓ Added hours column to overtime_history")
                    
        except Exception as e:
            logger.error(f"Error fixing overtime_history table: {e}")
            db.session.rollback()

def fix_time_off_request_table():
    """Fix the time_off_request table"""
    logger.info("Checking time_off_request table...")
    
    with app.app_context():
        try:
            if check_table_exists('time_off_request'):
                # The error shows it's looking for 'type' column which doesn't exist
                # but 'request_type' does. Let's add 'type' as an alias
                if not check_column_exists('time_off_request', 'type') and check_column_exists('time_off_request', 'request_type'):
                    try:
                        db.session.execute(text("""
                            ALTER TABLE time_off_request 
                            ADD COLUMN type VARCHAR(50)
                        """))
                        db.session.execute(text("""
                            UPDATE time_off_request 
                            SET type = request_type
                        """))
                        db.session.commit()
                        logger.info("✓ Added type column to time_off_request")
                    except Exception as e:
                        db.session.rollback()
                        logger.info(f"- Could not add type column: {e}")
                        
        except Exception as e:
            logger.error(f"Error fixing time_off_request table: {e}")
            db.session.rollback()

def verify_schema():
    """Verify the schema is correct"""
    logger.info("\nVerifying database schema...")
    
    with app.app_context():
        inspector = inspect(db.engine)
        
        # Check file_upload table
        if check_table_exists('file_upload'):
            columns = [col['name'] for col in inspector.get_columns('file_upload')]
            required_columns = ['id', 'filename', 'upload_type', 'uploaded_by_id', 
                              'total_records', 'successful_records', 'failed_records',
                              'status', 'uploaded_at']
            missing = [col for col in required_columns if col not in columns]
            if missing:
                logger.warning(f"file_upload table missing columns: {missing}")
            else:
                logger.info("✓ file_upload table has all required columns")
        
        # Check employee table
        if check_table_exists('employee'):
            columns = [col['name'] for col in inspector.get_columns('employee')]
            required_columns = ['id', 'employee_id', 'first_name', 'last_name', 
                              'email', 'crew', 'position_id']
            missing = [col for col in required_columns if col not in columns]
            if missing:
                logger.warning(f"employee table missing columns: {missing}")
            else:
                logger.info("✓ employee table has all required columns")

def main():
    """Run all fixes"""
    logger.info("Starting database schema fixes...")
    
    try:
        # Fix tables in order
        fix_position_table()      # Create position table first (referenced by employee)
        fix_employee_table()      # Fix employee table
        fix_file_upload_table()   # Fix file_upload table
        fix_overtime_history_table()  # Fix overtime_history table
        fix_time_off_request_table()  # Fix time_off_request table
        
        # Verify everything
        verify_schema()
        
        logger.info("\n✅ Database schema fixes completed!")
        logger.info("You can now try uploading your employee data again.")
        
    except Exception as e:
        logger.error(f"\n❌ Error during schema fixes: {e}")
        logger.error("Please check your database connection and try again.")

if __name__ == "__main__":
    main()
