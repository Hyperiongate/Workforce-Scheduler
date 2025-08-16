# fix_database_columns.py
"""
Script to fix missing database columns
Run this to fix the supervisor dashboard 500 error
"""

from app import app, db
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    try:
        result = db.session.execute(text(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}' 
            AND column_name = '{column_name}'
        """))
        return result.rowcount > 0
    except Exception as e:
        logger.error(f"Error checking column {table_name}.{column_name}: {e}")
        return False

def add_column_if_missing(table_name, column_name, column_type):
    """Add a column if it doesn't exist"""
    try:
        if not check_column_exists(table_name, column_name):
            logger.info(f"Adding column {table_name}.{column_name}")
            db.session.execute(text(f"""
                ALTER TABLE {table_name} 
                ADD COLUMN {column_name} {column_type}
            """))
            db.session.commit()
            logger.info(f"Successfully added {table_name}.{column_name}")
            return True
        else:
            logger.info(f"Column {table_name}.{column_name} already exists")
            return False
    except Exception as e:
        logger.error(f"Error adding column {table_name}.{column_name}: {e}")
        db.session.rollback()
        return False

def fix_database_schema():
    """Fix all missing columns"""
    with app.app_context():
        logger.info("Starting database schema fix...")
        
        fixes_applied = 0
        
        # Fix TimeOffRequest table
        logger.info("Checking time_off_request table...")
        
        # The model expects 'type' but it might be missing
        if add_column_if_missing('time_off_request', 'type', "VARCHAR(20) DEFAULT 'vacation'"):
            fixes_applied += 1
        
        # Add other potentially missing columns
        if add_column_if_missing('time_off_request', 'request_type', "VARCHAR(20) DEFAULT 'vacation'"):
            fixes_applied += 1
            
        if add_column_if_missing('time_off_request', 'created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'):
            fixes_applied += 1
            
        if add_column_if_missing('time_off_request', 'approved_date', 'DATE'):
            fixes_applied += 1
        
        # Fix ShiftSwapRequest table
        logger.info("Checking shift_swap_request table...")
        
        if add_column_if_missing('shift_swap_request', 'requester_date', 'DATE'):
            fixes_applied += 1
            
        if add_column_if_missing('shift_swap_request', 'requester_shift', 'VARCHAR(20)'):
            fixes_applied += 1
            
        if add_column_if_missing('shift_swap_request', 'target_date', 'DATE'):
            fixes_applied += 1
            
        if add_column_if_missing('shift_swap_request', 'target_shift', 'VARCHAR(20)'):
            fixes_applied += 1
        
        # Ensure status columns exist and have defaults
        logger.info("Ensuring status columns have proper defaults...")
        
        try:
            # Set default for existing records with NULL status
            db.session.execute(text("""
                UPDATE time_off_request 
                SET status = 'pending' 
                WHERE status IS NULL
            """))
            db.session.commit()
        except Exception as e:
            logger.warning(f"Could not update time_off_request status defaults: {e}")
            db.session.rollback()
        
        try:
            db.session.execute(text("""
                UPDATE shift_swap_request 
                SET status = 'pending' 
                WHERE status IS NULL
            """))
            db.session.commit()
        except Exception as e:
            logger.warning(f"Could not update shift_swap_request status defaults: {e}")
            db.session.rollback()
        
        logger.info(f"Database schema fix completed. {fixes_applied} fixes applied.")
        
        # Verify the fixes
        logger.info("Verifying fixes...")
        
        try:
            # Test time off query
            count = db.session.execute(text(
                "SELECT COUNT(*) FROM time_off_request WHERE status = 'pending'"
            )).scalar()
            logger.info(f"✓ Time off requests query works. Found {count} pending requests.")
        except Exception as e:
            logger.error(f"✗ Time off requests query still failing: {e}")
        
        try:
            # Test shift swap query
            count = db.session.execute(text(
                "SELECT COUNT(*) FROM shift_swap_request WHERE status = 'pending'"
            )).scalar()
            logger.info(f"✓ Shift swap requests query works. Found {count} pending swaps.")
        except Exception as e:
            logger.error(f"✗ Shift swap requests query still failing: {e}")
        
        return fixes_applied

if __name__ == '__main__':
    fixes = fix_database_schema()
    if fixes > 0:
        print(f"\n✅ Successfully applied {fixes} database fixes!")
        print("The supervisor dashboard should now work properly.")
    else:
        print("\n✅ No database fixes were needed. Schema appears to be up to date.")
        print("If you're still having issues, check the logs for errors.")
