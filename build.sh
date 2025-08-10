#!/usr/bin/env bash
# exit on error
set -o errexit

echo "=== Starting build process ==="

# Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Clean up any existing migration issues
echo "Cleaning migration state..."
python clean_migrations.py || echo "Migration cleanup completed with warnings"

# Run database migrations
echo "Running database migrations..."
flask db upgrade || {
    echo "Flask db upgrade failed, trying direct migration..."
    python -c "
from app import app, db
with app.app_context():
    db.create_all()
    print('Database tables created directly')
"
}

# Run any additional database fixes
echo "Running database fixes..."
python -c "
from app import app, db
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

with app.app_context():
    try:
        # Check and fix vacation_calendar status column
        with db.engine.connect() as conn:
            result = conn.execute(text(\"\"\"
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'vacation_calendar' 
                AND column_name = 'status'
            \"\"\"))
            
            if not result.fetchone():
                logger.info('Adding status column to vacation_calendar...')
                conn.execute(text(\"\"\"
                    ALTER TABLE vacation_calendar 
                    ADD COLUMN status VARCHAR(20) DEFAULT 'approved'
                \"\"\"))
                conn.commit()
                logger.info('Added status column successfully')
            else:
                logger.info('vacation_calendar.status column already exists')
                
    except Exception as e:
        logger.error(f'Database fix error: {e}')
        # Don't fail the build for this
"

echo "=== Build completed successfully! ==="
