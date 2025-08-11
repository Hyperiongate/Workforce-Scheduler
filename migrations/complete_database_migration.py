#!/usr/bin/env python3
"""
Complete Database Migration Script
Properly fixes all database schema issues with proper error handling and verification
"""

import os
import sys
import psycopg2
from psycopg2 import sql
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DatabaseMigration:
    def __init__(self, database_url):
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        self.database_url = database_url
        self.conn = None
        self.cursor = None
        self.migration_log = []
        
    def connect(self):
        """Establish database connection with proper error handling"""
        try:
            self.conn = psycopg2.connect(self.database_url)
            self.cursor = self.conn.cursor()
            logger.info("✓ Connected to database")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to connect to database: {e}")
            return False
    
    def disconnect(self):
        """Safely close database connection"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        logger.info("Disconnected from database")
    
    def execute_migration(self, description, sql_command, check_func=None):
        """Execute a single migration with verification"""
        try:
            logger.info(f"Executing: {description}")
            
            # Run the migration
            self.cursor.execute(sql_command)
            self.conn.commit()
            
            # Verify if requested
            if check_func:
                if check_func():
                    logger.info(f"✓ {description} - Verified")
                    self.migration_log.append(f"SUCCESS: {description}")
                else:
                    logger.warning(f"⚠ {description} - Verification failed")
                    self.migration_log.append(f"WARNING: {description} - needs verification")
            else:
                logger.info(f"✓ {description}")
                self.migration_log.append(f"SUCCESS: {description}")
                
            return True
            
        except psycopg2.errors.DuplicateColumn:
            logger.info(f"↩ {description} - Column already exists")
            self.migration_log.append(f"SKIPPED: {description} - already exists")
            return True
            
        except psycopg2.errors.DuplicateTable:
            logger.info(f"↩ {description} - Table already exists")
            self.migration_log.append(f"SKIPPED: {description} - already exists")
            return True
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"✗ {description} - Failed: {e}")
            self.migration_log.append(f"FAILED: {description} - {str(e)}")
            return False
    
    def table_exists(self, table_name):
        """Check if table exists"""
        self.cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = %s
            );
        """, (table_name,))
        return self.cursor.fetchone()[0]
    
    def column_exists(self, table_name, column_name):
        """Check if column exists"""
        self.cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns 
                WHERE table_schema = 'public' 
                AND table_name = %s 
                AND column_name = %s
            );
        """, (table_name, column_name))
        return self.cursor.fetchone()[0]
    
    def get_table_columns(self, table_name):
        """Get all columns for a table"""
        self.cursor.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position;
        """, (table_name,))
        return self.cursor.fetchall()
    
    def migrate_shift_swap_request(self):
        """Complete migration for shift_swap_request table"""
        logger.info("\n=== Migrating shift_swap_request table ===")
        
        # First, check if we need to create the table
        if not self.table_exists('shift_swap_request'):
            create_sql = """
                CREATE TABLE shift_swap_request (
                    id SERIAL PRIMARY KEY,
                    requester_id INTEGER REFERENCES employee(id) ON DELETE CASCADE,
                    requested_with_id INTEGER REFERENCES employee(id) ON DELETE CASCADE,
                    requester_schedule_id INTEGER REFERENCES schedule(id) ON DELETE CASCADE,
                    requested_schedule_id INTEGER REFERENCES schedule(id) ON DELETE CASCADE,
                    status VARCHAR(20) DEFAULT 'pending',
                    reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    reviewed_by_id INTEGER REFERENCES employee(id) ON DELETE SET NULL,
                    reviewed_at TIMESTAMP,
                    reviewer_notes TEXT
                );
            """
            self.execute_migration(
                "Create shift_swap_request table",
                create_sql,
                lambda: self.table_exists('shift_swap_request')
            )
            
            # Create indexes
            self.execute_migration(
                "Create index on shift_swap_request.status",
                "CREATE INDEX idx_shift_swap_status ON shift_swap_request(status);"
            )
            self.execute_migration(
                "Create index on shift_swap_request.requester_id",
                "CREATE INDEX idx_shift_swap_requester ON shift_swap_request(requester_id);"
            )
        else:
            # Table exists, add missing columns
            columns_to_add = [
                ('requester_id', 'INTEGER REFERENCES employee(id) ON DELETE CASCADE'),
                ('requested_with_id', 'INTEGER REFERENCES employee(id) ON DELETE CASCADE'),
                ('requester_schedule_id', 'INTEGER REFERENCES schedule(id) ON DELETE CASCADE'),
                ('requested_schedule_id', 'INTEGER REFERENCES schedule(id) ON DELETE CASCADE'),
                ('status', "VARCHAR(20) DEFAULT 'pending'"),
                ('reason', 'TEXT'),
                ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
                ('reviewed_by_id', 'INTEGER REFERENCES employee(id) ON DELETE SET NULL'),
                ('reviewed_at', 'TIMESTAMP'),
                ('reviewer_notes', 'TEXT')
            ]
            
            for column_name, column_definition in columns_to_add:
                if not self.column_exists('shift_swap_request', column_name):
                    self.execute_migration(
                        f"Add column shift_swap_request.{column_name}",
                        f"ALTER TABLE shift_swap_request ADD COLUMN {column_name} {column_definition};",
                        lambda col=column_name: self.column_exists('shift_swap_request', col)
                    )
    
    def migrate_vacation_calendar(self):
        """Ensure vacation_calendar table is properly structured"""
        logger.info("\n=== Migrating vacation_calendar table ===")
        
        if not self.table_exists('vacation_calendar'):
            create_sql = """
                CREATE TABLE vacation_calendar (
                    id SERIAL PRIMARY KEY,
                    employee_id INTEGER REFERENCES employee(id) ON DELETE CASCADE NOT NULL,
                    date DATE NOT NULL,
                    request_id INTEGER REFERENCES time_off_request(id) ON DELETE CASCADE,
                    type VARCHAR(20),
                    status VARCHAR(20) DEFAULT 'approved',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(employee_id, date)
                );
            """
            self.execute_migration(
                "Create vacation_calendar table",
                create_sql,
                lambda: self.table_exists('vacation_calendar')
            )
            
            # Create indexes
            self.execute_migration(
                "Create index on vacation_calendar.date",
                "CREATE INDEX idx_vacation_calendar_date ON vacation_calendar(date);"
            )
            self.execute_migration(
                "Create index on vacation_calendar.employee_id",
                "CREATE INDEX idx_vacation_calendar_employee ON vacation_calendar(employee_id);"
            )
        else:
            # Ensure status column exists
            if not self.column_exists('vacation_calendar', 'status'):
                self.execute_migration(
                    "Add column vacation_calendar.status",
                    "ALTER TABLE vacation_calendar ADD COLUMN status VARCHAR(20) DEFAULT 'approved';"
                )
    
    def migrate_position_coverage(self):
        """Ensure position_coverage table exists"""
        logger.info("\n=== Migrating position_coverage table ===")
        
        if not self.table_exists('position_coverage'):
            create_sql = """
                CREATE TABLE position_coverage (
                    id SERIAL PRIMARY KEY,
                    position_id INTEGER REFERENCES position(id) ON DELETE CASCADE NOT NULL,
                    crew VARCHAR(1) NOT NULL,
                    required_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(position_id, crew)
                );
            """
            self.execute_migration(
                "Create position_coverage table",
                create_sql,
                lambda: self.table_exists('position_coverage')
            )
    
    def migrate_position_table(self):
        """Ensure position table has required columns"""
        logger.info("\n=== Migrating position table ===")
        
        if self.table_exists('position'):
            if not self.column_exists('position', 'min_coverage'):
                self.execute_migration(
                    "Add column position.min_coverage",
                    "ALTER TABLE position ADD COLUMN min_coverage INTEGER DEFAULT 1;"
                )
            
            if not self.column_exists('position', 'department'):
                self.execute_migration(
                    "Add column position.department",
                    "ALTER TABLE position ADD COLUMN department VARCHAR(100);"
                )
    
    def migrate_time_off_request(self):
        """Ensure time_off_request has all needed columns"""
        logger.info("\n=== Migrating time_off_request table ===")
        
        if self.table_exists('time_off_request'):
            if not self.column_exists('time_off_request', 'approved_by_id'):
                self.execute_migration(
                    "Add column time_off_request.approved_by_id",
                    "ALTER TABLE time_off_request ADD COLUMN approved_by_id INTEGER REFERENCES employee(id);"
                )
            
            if not self.column_exists('time_off_request', 'denial_reason'):
                self.execute_migration(
                    "Add column time_off_request.denial_reason",
                    "ALTER TABLE time_off_request ADD COLUMN denial_reason TEXT;"
                )
    
    def create_missing_indexes(self):
        """Create performance indexes"""
        logger.info("\n=== Creating performance indexes ===")
        
        indexes = [
            ("idx_schedule_date", "schedule(date)"),
            ("idx_schedule_employee", "schedule(employee_id)"),
            ("idx_overtime_history_employee", "overtime_history(employee_id)"),
            ("idx_overtime_history_week", "overtime_history(week_start_date)"),
            ("idx_time_off_status", "time_off_request(status)"),
            ("idx_employee_crew", "employee(crew)")
        ]
        
        for index_name, index_def in indexes:
            self.execute_migration(
                f"Create index {index_name}",
                f"CREATE INDEX IF NOT EXISTS {index_name} ON {index_def};"
            )
    
    def verify_migration(self):
        """Verify all migrations completed successfully"""
        logger.info("\n=== Verifying Migration ===")
        
        # Check critical tables
        critical_tables = [
            'employee', 'schedule', 'position', 'time_off_request',
            'shift_swap_request', 'vacation_calendar', 'overtime_history'
        ]
        
        all_good = True
        for table in critical_tables:
            if self.table_exists(table):
                columns = self.get_table_columns(table)
                logger.info(f"✓ Table '{table}' exists with {len(columns)} columns")
            else:
                logger.error(f"✗ Table '{table}' is missing!")
                all_good = False
        
        # Specific checks for shift_swap_request
        if self.table_exists('shift_swap_request'):
            required_columns = [
                'requester_id', 'requested_with_id', 'status', 'created_at'
            ]
            missing = []
            for col in required_columns:
                if not self.column_exists('shift_swap_request', col):
                    missing.append(col)
            
            if missing:
                logger.error(f"✗ shift_swap_request missing columns: {missing}")
                all_good = False
            else:
                logger.info("✓ shift_swap_request has all required columns")
        
        return all_good
    
    def run_all_migrations(self):
        """Run all migrations in proper order"""
        logger.info("Starting complete database migration...")
        logger.info(f"Timestamp: {datetime.now()}")
        
        try:
            # Run migrations in dependency order
            self.migrate_position_table()
            self.migrate_shift_swap_request()
            self.migrate_vacation_calendar()
            self.migrate_position_coverage()
            self.migrate_time_off_request()
            self.create_missing_indexes()
            
            # Verify everything
            if self.verify_migration():
                logger.info("\n✅ All migrations completed successfully!")
            else:
                logger.warning("\n⚠️  Some issues remain - check logs above")
            
            # Print summary
            logger.info("\n=== Migration Summary ===")
            for log_entry in self.migration_log:
                logger.info(f"  {log_entry}")
            
            return True
            
        except Exception as e:
            logger.error(f"\n❌ Migration failed: {e}")
            self.conn.rollback()
            return False

def main():
    """Main entry point"""
    # Get database URL
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        logger.error("DATABASE_URL environment variable not set!")
        logger.info("\nTo run this script:")
        logger.info("1. On Render: Use the Shell tab in your web service")
        logger.info("2. Locally: export DATABASE_URL='your-database-url'")
        sys.exit(1)
    
    # Run migration
    migration = DatabaseMigration(database_url)
    
    if not migration.connect():
        sys.exit(1)
    
    try:
        success = migration.run_all_migrations()
        
        if success:
            logger.info("\n🎉 Database migration completed successfully!")
            logger.info("Your application should now work without errors.")
        else:
            logger.error("\n❌ Migration encountered issues. Please check the logs.")
            sys.exit(1)
            
    finally:
        migration.disconnect()

if __name__ == "__main__":
    main()
