#!/usr/bin/env python3
"""
Fix FileUpload table by adding missing columns
Run this to fix the database schema issues
"""

from app import app, db
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_file_upload_table():
    """Add missing columns to file_upload table"""
    with app.app_context():
        try:
            logger.info("Fixing file_upload table...")
            
            # List of columns to add
            columns_to_add = [
                ('total_records', 'INTEGER DEFAULT 0'),
                ('successful_records', 'INTEGER DEFAULT 0'),
                ('failed_records', 'INTEGER DEFAULT 0'),
                ('records_processed', 'INTEGER DEFAULT 0'),
                ('records_failed', 'INTEGER DEFAULT 0'),
                ('file_type', 'VARCHAR(50)'),
                ('file_path', 'VARCHAR(255)'),
                ('file_size', 'INTEGER'),
                ('error_details', 'JSON')
            ]
            
            for column_name, column_def in columns_to_add:
                try:
                    with db.engine.connect() as conn:
                        # Check if column exists
                        result = conn.execute(text(f"""
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name='file_upload' AND column_name='{column_name}'
                        """))
                        
                        if not result.fetchone():
                            # Add column
                            conn.execute(text(f"ALTER TABLE file_upload ADD COLUMN {column_name} {column_def}"))
                            conn.commit()
                            logger.info(f"✓ Added column {column_name}")
                        else:
                            logger.info(f"✓ Column {column_name} already exists")
                            
                except Exception as e:
                    logger.warning(f"Could not add column {column_name}: {e}")
            
            # Also fix other tables
            logger.info("\nFixing other tables...")
            
            # Fix schedule table
            try:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE schedule ADD COLUMN IF NOT EXISTS is_training BOOLEAN DEFAULT FALSE"))
                    conn.commit()
                    logger.info("✓ Fixed schedule.is_training")
            except Exception as e:
                logger.warning(f"Could not fix schedule table: {e}")
            
            # Fix time_off_request table
            try:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE time_off_request ADD COLUMN IF NOT EXISTS type VARCHAR(50)"))
                    conn.execute(text("UPDATE time_off_request SET type = request_type WHERE type IS NULL"))
                    conn.commit()
                    logger.info("✓ Fixed time_off_request.type")
            except Exception as e:
                logger.warning(f"Could not fix time_off_request table: {e}")
            
            logger.info("\n✅ Database fixes complete!")
            
        except Exception as e:
            logger.error(f"Error fixing database: {e}")

if __name__ == "__main__":
    fix_file_upload_table()
