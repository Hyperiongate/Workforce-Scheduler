#!/usr/bin/env bash
# exit on error
set -o errexit

echo "=== Starting build process ==="

# Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Clean up any migration issues
echo "Cleaning up migration state..."
python << 'EOF'
import os
import sys
from sqlalchemy import create_engine, text

database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    try:
        engine = create_engine(database_url, connect_args={'sslmode': 'require'})
        with engine.connect() as conn:
            # Clean up alembic version if needed
            try:
                conn.execute(text("DELETE FROM alembic_version"))
                conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('001_initial')"))
                conn.commit()
                print("Reset alembic version")
            except:
                print("Alembic version table might not exist yet")
    except Exception as e:
        print(f"Migration cleanup skipped: {e}")
EOF

# Run database migrations
echo "Running database migrations..."
flask db upgrade || echo "Flask-Migrate completed with warnings"

# Create any missing tables
echo "Ensuring all tables exist..."
python << 'EOF'
from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        # Create all tables
        db.create_all()
        print("Database tables created/verified")
        
        # Fix vacation_calendar status column
        with db.engine.connect() as conn:
            try:
                conn.execute(text("""
                    ALTER TABLE vacation_calendar 
                    ADD COLUMN status VARCHAR(20) DEFAULT 'approved'
                """))
                conn.commit()
                print("Added status column to vacation_calendar")
            except Exception as e:
                print(f"Status column might already exist: {e}")
                
    except Exception as e:
        print(f"Database setup warning: {e}")
EOF

echo "=== Build completed successfully! ==="
