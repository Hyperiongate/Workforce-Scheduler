#!/usr/bin/env python3
"""
Database Fix Script for Shift Swap Request Table
Fixes the missing requested_with_id column and other required columns
COMPLETE DEPLOYMENT-READY SCRIPT
"""

import os
import sys
import logging
from datetime import datetime
from flask import Flask
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import ProgrammingError, OperationalError

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('database_fix.log')
    ]
)
logger = logging.getLogger(__name__)

class DatabaseFixer:
    """Complete database schema fixer for shift swap functionality"""
    
    def __init__(self):
        self.engine = None
        self.connection = None
        self.fixes_applied = 0
        
    def create_engine(self):
        """Create database engine with proper configuration"""
        database_url = os.environ.get('DATABASE_URL')
        
        if not database_url:
            logger.error("❌ DATABASE_URL environment variable not found!")
            return False
            
        # Fix postgres:// to postgresql://
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
            
        try:
            self.engine = create_engine(
                database_url,
                pool_pre_ping=True,
                pool_recycle=300,
                connect_args={'sslmode': 'require'} if 'render.com' in database_url else {}
            )
            logger.info("✅ Database engine created successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create database engine: {e}")
            return False
    
    def test_connection(self):
        """Test database connection"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                logger.info("✅ Database connection test successful")
                return True
        except Exception as e:
            logger.error(f"❌ Database connection test failed: {e}")
            return False
    
    def table_exists(self, table_name):
        """Check if a table exists"""
        try:
            with self.engine.connect() as conn:
                inspector = inspect(conn)
                tables = inspector.get_table_names()
                exists = table_name in tables
                logger.info(f"{'✅' if exists else '❌'} Table '{table_name}' {'exists' if exists else 'does not exist'}")
                return exists
        except Exception as e:
            logger.error(f"❌ Error checking table {table_name}: {e}")
            return False
    
    def column_exists(self, table_name, column_name):
        """Check if a column exists in a table"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_schema = 'public' 
                        AND table_name = :table_name 
                        AND column_name = :column_name
                    );
                """), {'table_name': table_name, 'column_name': column_name})
                exists = result.scalar()
                logger.info(f"{'✅' if exists else '❌'} Column '{table_name}.{column_name}' {'exists' if exists else 'missing'}")
                return exists
        except Exception as e:
            logger.error(f"❌ Error checking column {table_name}.{column_name}: {e}")
            return False
    
    def execute_sql(self, description, sql, params=None):
        """Execute SQL with error handling"""
        try:
            with self.engine.connect() as conn:
                with conn.begin():
                    if params:
                        conn.execute(text(sql), params)
                    else:
                        conn.execute(text(sql))
                logger.info(f"✅ {description} - SUCCESS")
                self.fixes_applied += 1
                return True
        except Exception as e:
            logger.error(f"❌ {description} - FAILED: {e}")
            return False
    
    def create_shift_swap_table(self):
        """Create the shift_swap_request table if it doesn't exist"""
        if self.table_exists('shift_swap_request'):
            logger.info("ℹ️ shift_swap_request table already exists, checking columns...")
            return True
            
        logger.info("Creating shift_swap_request table...")
        
        sql = """
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
        
        return self.execute_sql("Create shift_swap_request table", sql)
    
    def add_missing_columns(self):
        """Add any missing columns to shift_swap_request table"""
        logger.info("Checking and adding missing columns...")
        
        # Define all required columns with their definitions
        required_columns = [
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
        
        for column_name, column_definition in required_columns:
            if not self.column_exists('shift_swap_request', column_name):
                sql = f"ALTER TABLE shift_swap_request ADD COLUMN {column_name} {column_definition};"
                self.execute_sql(f"Add column {column_name}", sql)
            else:
                logger.info(f"ℹ️ Column '{column_name}' already exists")
    
    def create_indexes(self):
        """Create performance indexes"""
        logger.info("Creating database indexes...")
        
        indexes = [
            ("idx_shift_swap_status", "CREATE INDEX IF NOT EXISTS idx_shift_swap_status ON shift_swap_request(status);"),
            ("idx_shift_swap_requester", "CREATE INDEX IF NOT EXISTS idx_shift_swap_requester ON shift_swap_request(requester_id);"),
            ("idx_shift_swap_requested_with", "CREATE INDEX IF NOT EXISTS idx_shift_swap_requested_with ON shift_swap_request(requested_with_id);"),
            ("idx_shift_swap_created", "CREATE INDEX IF NOT EXISTS idx_shift_swap_created ON shift_swap_request(created_at);")
        ]
        
        for index_name, sql in indexes:
            self.execute_sql(f"Create index {index_name}", sql)
    
    def verify_fix(self):
        """Verify that the fix worked by testing a query"""
        logger.info("Verifying the database fix...")
        
        try:
            with self.engine.connect() as conn:
                # Test the exact query that was failing
                result = conn.execute(text("""
                    SELECT COUNT(*) as count_1 
                    FROM (
                        SELECT shift_swap_request.id AS shift_swap_request_id, 
                               shift_swap_request.requester_id AS shift_swap_request_requester_id, 
                               shift_swap_request.requested_with_id AS shift_swap_request_requested_with_id, 
                               shift_swap_request.requester_schedule_id AS shift_swap_request_requester_schedule_id, 
                               shift_swap_request.requested_schedule_id AS shift_swap_request_requested_schedule_id, 
                               shift_swap_request.status AS shift_swap_request_status, 
                               shift_swap_request.reason AS shift_swap_request_reason, 
                               shift_swap_request.created_at AS shift_swap_request_created_at, 
                               shift_swap_request.reviewed_by_id AS shift_swap_request_reviewed_by_id, 
                               shift_swap_request.reviewed_at AS shift_swap_request_reviewed_at, 
                               shift_swap_request.reviewer_notes AS shift_swap_request_reviewer_notes 
                        FROM shift_swap_request 
                        WHERE shift_swap_request.status = 'pending'
                    ) AS anon_1
                """))
                
                count = result.scalar()
                logger.info(f"✅ Verification successful! Found {count} pending shift swap requests")
                return True
                
        except Exception as e:
            logger.error(f"❌ Verification failed: {e}")
            return False
    
    def run_complete_fix(self):
        """Run the complete database fix process"""
        logger.info("=" * 80)
        logger.info("STARTING COMPLETE DATABASE FIX FOR SHIFT SWAP REQUESTS")
        logger.info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80)
        
        # Step 1: Create database engine
        if not self.create_engine():
            logger.error("❌ CRITICAL: Could not create database engine. Aborting.")
            return False
        
        # Step 2: Test connection
        if not self.test_connection():
            logger.error("❌ CRITICAL: Could not connect to database. Aborting.")
            return False
        
        # Step 3: Create table if needed
        if not self.create_shift_swap_table():
            logger.error("❌ CRITICAL: Could not create shift_swap_request table. Aborting.")
            return False
        
        # Step 4: Add missing columns
        self.add_missing_columns()
        
        # Step 5: Create indexes
        self.create_indexes()
        
        # Step 6: Verify the fix
        if not self.verify_fix():
            logger.error("❌ CRITICAL: Database fix verification failed!")
            return False
        
        # Success summary
        logger.info("=" * 80)
        logger.info("✅ DATABASE FIX COMPLETED SUCCESSFULLY!")
        logger.info(f"Applied {self.fixes_applied} database fixes")
        logger.info(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80)
        
        return True

def main():
    """Main execution function"""
    print("🔧 Workforce Scheduler Database Fix Tool")
    print("Fixing missing shift_swap_request.requested_with_id column...")
    print("-" * 60)
    
    fixer = DatabaseFixer()
    
    try:
        success = fixer.run_complete_fix()
        
        if success:
            print("\n🎉 SUCCESS! Database has been fixed.")
            print("The supervisor dashboard should now work without redirect loops.")
            print("\nNext steps:")
            print("1. Restart your application")
            print("2. Test the /supervisor/dashboard route")
            print("3. Verify shift swap functionality works")
            
        else:
            print("\n❌ FAILED! Database fix was not successful.")
            print("Please check the logs and try running the script again.")
            print("If the problem persists, contact support.")
            
    except KeyboardInterrupt:
        print("\n\n🛑 Database fix interrupted by user.")
        print("No changes were committed.")
        
    except Exception as e:
        logger.error(f"❌ CRITICAL ERROR: {e}")
        print(f"\n❌ CRITICAL ERROR: {e}")
        print("Please check the logs for details.")

if __name__ == "__main__":
    main()
