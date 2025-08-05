# database_schema_manager.py
"""
Comprehensive Database Schema Management System
This module handles all database schema synchronization automatically
"""

import os
import sys
from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, inspect, MetaData
from sqlalchemy.exc import ProgrammingError, OperationalError
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseSchemaManager:
    """Manages database schema synchronization and migrations"""
    
    def __init__(self, app, db):
        self.app = app
        self.db = db
        self.issues_found = []
        self.fixes_applied = []
        
    def get_column_definition(self, column_name, column_type):
        """Generate SQL column definition based on column name and type"""
        definitions = {
            # String columns
            'email': "VARCHAR(120) UNIQUE",
            'name': "VARCHAR(100)",
            'employee_id': "VARCHAR(50) UNIQUE",
            'username': "VARCHAR(50) UNIQUE",
            'password_hash': "VARCHAR(255)",
            'phone': "VARCHAR(20)",
            'crew': "VARCHAR(1)",
            'department': "VARCHAR(100)",
            'shift_pattern': "VARCHAR(50)",
            'reset_token': "VARCHAR(100)",
            'default_shift': "VARCHAR(20) DEFAULT 'day'",
            
            # Boolean columns
            'is_supervisor': "BOOLEAN DEFAULT FALSE",
            'must_change_password': "BOOLEAN DEFAULT TRUE",
            'first_login': "BOOLEAN DEFAULT TRUE",
            'account_active': "BOOLEAN DEFAULT TRUE",
            'is_on_call': "BOOLEAN DEFAULT FALSE",
            'is_active': "BOOLEAN DEFAULT TRUE",
            
            # Date columns
            'hire_date': "DATE",
            'seniority_date': "DATE",
            
            # Datetime columns
            'account_created_date': "TIMESTAMP",
            'last_password_change': "TIMESTAMP",
            'last_login': "TIMESTAMP",
            'locked_until': "TIMESTAMP",
            'reset_token_expires': "TIMESTAMP",
            
            # Integer columns
            'position_id': "INTEGER",
            'login_attempts': "INTEGER DEFAULT 0",
            'max_consecutive_days': "INTEGER DEFAULT 14",
            
            # Float columns
            'vacation_days': "FLOAT DEFAULT 10.0",
            'sick_days': "FLOAT DEFAULT 5.0",
            'personal_days': "FLOAT DEFAULT 3.0",
        }
        
        return definitions.get(column_name, "VARCHAR(255)")
    
    def get_model_columns(self, model_class):
        """Extract column information from SQLAlchemy model"""
        columns = {}
        for column in model_class.__table__.columns:
            columns[column.name] = {
                'type': str(column.type),
                'nullable': column.nullable,
                'default': column.default,
                'unique': column.unique,
                'primary_key': column.primary_key
            }
        return columns
    
    def check_table_exists(self, table_name):
        """Check if a table exists in the database"""
        try:
            result = self.db.session.execute(text(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = '{table_name}'
                )
            """))
            return result.scalar()
        except Exception:
            return False
    
    def get_database_columns(self, table_name):
        """Get current columns from database"""
        try:
            inspector = inspect(self.db.engine)
            columns = {}
            for col in inspector.get_columns(table_name):
                columns[col['name']] = {
                    'type': str(col['type']),
                    'nullable': col['nullable'],
                    'default': col['default']
                }
            return columns
        except Exception as e:
            logger.error(f"Error getting columns for {table_name}: {e}")
            return {}
    
    def fix_employee_table(self):
        """Specifically fix the employee table schema"""
        logger.info("🔧 Checking employee table schema...")
        
        if not self.check_table_exists('employee'):
            logger.error("❌ Employee table does not exist!")
            return False
        
        # Get current database columns
        db_columns = self.get_database_columns('employee')
        
        # Define all expected columns for employee table
        expected_columns = {
            'id': 'INTEGER PRIMARY KEY',
            'employee_id': 'VARCHAR(50) UNIQUE',
            'email': 'VARCHAR(120) UNIQUE',
            'name': 'VARCHAR(100)',
            'password_hash': 'VARCHAR(255)',
            'is_supervisor': 'BOOLEAN DEFAULT FALSE',
            'position_id': 'INTEGER',
            'department': 'VARCHAR(100)',
            'hire_date': 'DATE',
            'phone': 'VARCHAR(20)',
            'crew': 'VARCHAR(1)',
            'shift_pattern': 'VARCHAR(50)',
            'seniority_date': 'DATE',
            'username': 'VARCHAR(50) UNIQUE',
            'must_change_password': 'BOOLEAN DEFAULT TRUE',
            'first_login': 'BOOLEAN DEFAULT TRUE',
            'account_active': 'BOOLEAN DEFAULT TRUE',
            'account_created_date': 'TIMESTAMP',
            'last_password_change': 'TIMESTAMP',
            'last_login': 'TIMESTAMP',
            'login_attempts': 'INTEGER DEFAULT 0',
            'locked_until': 'TIMESTAMP',
            'reset_token': 'VARCHAR(100)',
            'reset_token_expires': 'TIMESTAMP',
            'default_shift': 'VARCHAR(20) DEFAULT \'day\'',
            'max_consecutive_days': 'INTEGER DEFAULT 14',
            'is_on_call': 'BOOLEAN DEFAULT FALSE',
            'is_active': 'BOOLEAN DEFAULT TRUE',
            'vacation_days': 'FLOAT DEFAULT 10.0',
            'sick_days': 'FLOAT DEFAULT 5.0',
            'personal_days': 'FLOAT DEFAULT 3.0'
        }
        
        # Find missing columns
        missing_columns = set(expected_columns.keys()) - set(db_columns.keys())
        
        if missing_columns:
            logger.info(f"❌ Found {len(missing_columns)} missing columns: {missing_columns}")
            
            for column in missing_columns:
                try:
                    column_def = self.get_column_definition(column, expected_columns[column])
                    
                    # Add the column
                    logger.info(f"Adding column: {column}")
                    self.db.session.execute(text(f"ALTER TABLE employee ADD COLUMN {column} {column_def}"))
                    
                    # Handle special cases
                    if column == 'seniority_date':
                        self.db.session.execute(text("UPDATE employee SET seniority_date = hire_date WHERE seniority_date IS NULL"))
                    elif column == 'username':
                        self.db.session.execute(text("UPDATE employee SET username = SPLIT_PART(email, '@', 1) WHERE username IS NULL"))
                    elif column == 'account_created_date':
                        self.db.session.execute(text("UPDATE employee SET account_created_date = CURRENT_TIMESTAMP WHERE account_created_date IS NULL"))
                    
                    self.fixes_applied.append(f"Added column {column} to employee table")
                    logger.info(f"✅ Successfully added column: {column}")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to add column {column}: {e}")
                    self.issues_found.append(f"Could not add column {column}: {str(e)}")
            
            try:
                self.db.session.commit()
                logger.info("✅ All changes committed successfully")
            except Exception as e:
                self.db.session.rollback()
                logger.error(f"❌ Failed to commit changes: {e}")
                return False
        else:
            logger.info("✅ No missing columns in employee table")
        
        return True
    
    def fix_all_tables(self):
        """Check and fix all tables in the database"""
        tables_to_check = [
            'employee', 'position', 'skill', 'schedule', 'availability',
            'time_off_requests', 'shift_swap_requests', 'coverage_requests',
            'overtime_history', 'schedule_suggestions', 'vacation_calendar',
            'overtime_opportunities', 'overtime_responses', 'coverage_gaps',
            'employee_skills_new', 'fatigue_tracking', 'mandatory_overtime_logs',
            'shift_patterns', 'coverage_notification_responses', 'file_uploads'
        ]
        
        for table in tables_to_check:
            if self.check_table_exists(table):
                logger.info(f"✅ Table {table} exists")
            else:
                logger.warning(f"⚠️  Table {table} does not exist")
                self.issues_found.append(f"Table {table} is missing")
    
    def create_indexes(self):
        """Create missing indexes for better performance"""
        indexes = [
            ("idx_employee_email", "employee", "email"),
            ("idx_employee_username", "employee", "username"),
            ("idx_employee_crew", "employee", "crew"),
            ("idx_schedule_date_crew", "schedule", "date, crew"),
            ("idx_schedule_employee_date", "schedule", "employee_id, date"),
        ]
        
        for index_name, table_name, columns in indexes:
            try:
                self.db.session.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns})"))
                self.fixes_applied.append(f"Created index {index_name}")
            except Exception as e:
                logger.warning(f"Could not create index {index_name}: {e}")
    
    def run_full_check(self):
        """Run complete database schema check and fix"""
        logger.info("="*60)
        logger.info("🔍 Starting comprehensive database schema check...")
        logger.info("="*60)
        
        with self.app.app_context():
            # First, fix the employee table (most critical)
            success = self.fix_employee_table()
            
            if success:
                # Check other tables
                self.fix_all_tables()
                
                # Create indexes
                self.create_indexes()
                
                # Generate report
                logger.info("\n" + "="*60)
                logger.info("📊 SCHEMA CHECK COMPLETE")
                logger.info("="*60)
                
                if self.fixes_applied:
                    logger.info(f"\n✅ Fixes Applied ({len(self.fixes_applied)}):")
                    for fix in self.fixes_applied:
                        logger.info(f"  - {fix}")
                
                if self.issues_found:
                    logger.info(f"\n⚠️  Issues Found ({len(self.issues_found)}):")
                    for issue in self.issues_found:
                        logger.info(f"  - {issue}")
                else:
                    logger.info("\n✅ No issues found - database schema is correct!")
                
                logger.info("\n" + "="*60)
                
                return True
            else:
                logger.error("❌ Failed to fix employee table schema")
                return False


def init_schema_manager(app, db):
    """Initialize schema manager and run checks"""
    manager = DatabaseSchemaManager(app, db)
    return manager.run_full_check()


# Standalone script functionality
if __name__ == '__main__':
    # This allows running the script directly
    from flask import Flask
    from flask_sqlalchemy import SQLAlchemy
    
    app = Flask(__name__)
    
    # Database configuration
    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db = SQLAlchemy(app)
    
    # Run the schema check
    manager = DatabaseSchemaManager(app, db)
    manager.run_full_check()
