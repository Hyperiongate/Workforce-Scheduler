# add_hours_to_schedule.py - Database Migration Script
"""
Add hours field to Schedule table
Run this script to safely add the hours field to your existing Schedule table
COMPLETE MIGRATION SCRIPT WITH ERROR HANDLING
"""

from flask import Flask
from models import db
from sqlalchemy import text, inspect
from sqlalchemy.exc import OperationalError, ProgrammingError
import os
import logging
import sys
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_app():
    """Create Flask app for migration"""
    app = Flask(__name__)
    
    # Database configuration - same as your main app
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'connect_args': {
                'sslmode': 'require',
                'keepalives': 1,
                'keepalives_idle': 30,
                'keepalives_interval': 5,
                'keepalives_count': 5
            }
        }
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workforce.db'
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize database
    db.init_app(app)
    
    return app

def check_column_exists(connection, table_name, column_name):
    """Check if a column exists in a table"""
    try:
        inspector = inspect(connection)
        columns = inspector.get_columns(table_name)
        return any(col['name'] == column_name for col in columns)
    except Exception as e:
        logger.error(f"Error checking column existence: {e}")
        return False

def add_hours_field():
    """Add hours field to Schedule table with comprehensive error handling"""
    
    logger.info("=" * 60)
    logger.info("STARTING SCHEDULE TABLE MIGRATION")
    logger.info("Adding 'hours' field to Schedule table")
    logger.info("=" * 60)
    
    app = create_app()
    
    with app.app_context():
        try:
            # Test database connection first
            logger.info("Testing database connection...")
            with db.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                logger.info("✅ Database connection successful")
                
                # Check if Schedule table exists
                inspector = inspect(connection)
                tables = inspector.get_table_names()
                
                if 'schedule' not in tables:
                    logger.error("❌ Schedule table does not exist!")
                    logger.error("Please ensure your database is properly initialized")
                    return False
                
                logger.info("✅ Schedule table found")
                
                # Check if hours column already exists
                logger.info("Checking if 'hours' column already exists...")
                if check_column_exists(connection, 'schedule', 'hours'):
                    logger.warning("⚠️  'hours' column already exists in Schedule table")
                    logger.info("Migration not needed - column already present")
                    return True
                
                logger.info("✅ 'hours' column does not exist - migration needed")
                
                # Get current schedule records count
                result = connection.execute(text("SELECT COUNT(*) as count FROM schedule"))
                current_records = result.fetchone()[0]
                logger.info(f"📊 Current schedule records: {current_records}")
                
                # Begin transaction for migration
                logger.info("🔄 Starting migration transaction...")
                
                # Add the hours column
                logger.info("Adding 'hours' column to schedule table...")
                connection.execute(text(
                    "ALTER TABLE schedule ADD COLUMN hours FLOAT DEFAULT 8.0"
                ))
                logger.info("✅ Successfully added 'hours' column")
                
                # Update existing records with appropriate default hours based on shift_type
                logger.info("Updating existing records with appropriate hours...")
                
                # Set 12 hours for day and night shifts (assuming 12-hour shifts)
                connection.execute(text("""
                    UPDATE schedule 
                    SET hours = 12.0 
                    WHERE shift_type IN ('day', 'night') AND hours IS NULL
                """))
                
                # Set 8 hours for evening shifts (assuming 8-hour shifts)
                connection.execute(text("""
                    UPDATE schedule 
                    SET hours = 8.0 
                    WHERE shift_type = 'evening' AND hours IS NULL
                """))
                
                # Set 8.0 as default for any remaining NULL values
                connection.execute(text("""
                    UPDATE schedule 
                    SET hours = 8.0 
                    WHERE hours IS NULL
                """))
                
                # Verify the updates
                result = connection.execute(text("""
                    SELECT shift_type, AVG(hours) as avg_hours, COUNT(*) as count 
                    FROM schedule 
                    GROUP BY shift_type
                """))
                
                logger.info("📊 Updated records summary:")
                for row in result:
                    logger.info(f"   {row.shift_type}: {row.count} records, avg {row.avg_hours} hours")
                
                # Add position_id and created_by_id columns if they don't exist
                # (These are referenced in the schedule_pattern_engine.py)
                logger.info("Checking for additional required columns...")
                
                if not check_column_exists(connection, 'schedule', 'position_id'):
                    logger.info("Adding 'position_id' column...")
                    connection.execute(text(
                        "ALTER TABLE schedule ADD COLUMN position_id INTEGER"
                    ))
                    # Add foreign key constraint if using PostgreSQL
                    try:
                        connection.execute(text(
                            "ALTER TABLE schedule ADD CONSTRAINT fk_schedule_position "
                            "FOREIGN KEY (position_id) REFERENCES position(id)"
                        ))
                        logger.info("✅ Added position_id foreign key constraint")
                    except Exception as e:
                        logger.warning(f"⚠️  Could not add foreign key constraint for position_id: {e}")
                
                if not check_column_exists(connection, 'schedule', 'created_by_id'):
                    logger.info("Adding 'created_by_id' column...")
                    connection.execute(text(
                        "ALTER TABLE schedule ADD COLUMN created_by_id INTEGER"
                    ))
                    # Add foreign key constraint if using PostgreSQL
                    try:
                        connection.execute(text(
                            "ALTER TABLE schedule ADD CONSTRAINT fk_schedule_created_by "
                            "FOREIGN KEY (created_by_id) REFERENCES employee(id)"
                        ))
                        logger.info("✅ Added created_by_id foreign key constraint")
                    except Exception as e:
                        logger.warning(f"⚠️  Could not add foreign key constraint for created_by_id: {e}")
                
                # Add timestamp columns if they don't exist
                if not check_column_exists(connection, 'schedule', 'created_at'):
                    logger.info("Adding 'created_at' column...")
                    connection.execute(text(
                        f"ALTER TABLE schedule ADD COLUMN created_at TIMESTAMP DEFAULT '{datetime.utcnow()}'"
                    ))
                
                if not check_column_exists(connection, 'schedule', 'updated_at'):
                    logger.info("Adding 'updated_at' column...")
                    connection.execute(text(
                        f"ALTER TABLE schedule ADD COLUMN updated_at TIMESTAMP DEFAULT '{datetime.utcnow()}'"
                    ))
                
                # Commit the transaction
                connection.commit()
                
                logger.info("✅ Migration completed successfully!")
                logger.info("=" * 60)
                logger.info("MIGRATION SUMMARY:")
                logger.info(f"✅ Added 'hours' column to Schedule table")
                logger.info(f"✅ Updated {current_records} existing records")
                logger.info(f"✅ Added supporting columns (position_id, created_by_id, timestamps)")
                logger.info("✅ All changes committed to database")
                logger.info("=" * 60)
                
                return True
                
        except OperationalError as e:
            logger.error(f"❌ Database operational error: {e}")
            logger.error("This might be a connection or permissions issue")
            return False
            
        except ProgrammingError as e:
            logger.error(f"❌ Database programming error: {e}")
            logger.error("This might be a SQL syntax or schema issue")
            return False
            
        except Exception as e:
            logger.error(f"❌ Unexpected error during migration: {e}")
            logger.error("Rolling back changes...")
            try:
                db.session.rollback()
            except:
                pass
            return False

def verify_migration():
    """Verify that the migration was successful"""
    logger.info("🔍 Verifying migration...")
    
    app = create_app()
    
    with app.app_context():
        try:
            with db.engine.connect() as connection:
                # Check if hours column exists and has data
                result = connection.execute(text("""
                    SELECT 
                        COUNT(*) as total_records,
                        COUNT(hours) as records_with_hours,
                        AVG(hours) as avg_hours,
                        MIN(hours) as min_hours,
                        MAX(hours) as max_hours
                    FROM schedule
                """))
                
                stats = result.fetchone()
                
                logger.info("📊 MIGRATION VERIFICATION:")
                logger.info(f"   Total schedule records: {stats.total_records}")
                logger.info(f"   Records with hours: {stats.records_with_hours}")
                logger.info(f"   Average hours: {stats.avg_hours:.2f}")
                logger.info(f"   Hours range: {stats.min_hours} - {stats.max_hours}")
                
                if stats.total_records == stats.records_with_hours:
                    logger.info("✅ Migration verification PASSED")
                    return True
                else:
                    logger.error("❌ Migration verification FAILED - some records missing hours")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Error during verification: {e}")
            return False

def main():
    """Main migration function"""
    try:
        logger.info("🚀 Starting Schedule table migration process...")
        
        # Run migration
        success = add_hours_field()
        
        if success:
            # Verify migration
            verify_success = verify_migration()
            
            if verify_success:
                logger.info("🎉 MIGRATION COMPLETED SUCCESSFULLY!")
                logger.info("Your Schedule table now has the 'hours' field")
                logger.info("The schedule pattern engine will now work correctly")
                return 0
            else:
                logger.error("❌ Migration verification failed")
                return 1
        else:
            logger.error("❌ Migration failed")
            return 1
            
    except KeyboardInterrupt:
        logger.warning("⚠️  Migration interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"❌ Unexpected error in main: {e}")
        return 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
