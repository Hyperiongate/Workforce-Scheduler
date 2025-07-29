#!/usr/bin/env python3
"""
Clean up migration issues before running flask db upgrade
"""
import os
from sqlalchemy import create_engine, text
from app import app, db

def clean_alembic_version():
    """Clean up the alembic_version table"""
    with app.app_context():
        try:
            # Direct database connection
            engine = db.engine
            
            with engine.connect() as conn:
                # Check if alembic_version table exists
                result = conn.execute(text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'alembic_version'
                """))
                
                if result.fetchone():
                    print("Found alembic_version table")
                    
                    # Check current version
                    result = conn.execute(text("SELECT version_num FROM alembic_version"))
                    current = result.fetchone()
                    if current:
                        print(f"Current version: {current[0]}")
                    
                    # Clear the table
                    conn.execute(text("DELETE FROM alembic_version"))
                    conn.commit()
                    print("Cleared alembic_version table")
                    
                    # Set to our new version
                    conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('001_initial')"))
                    conn.commit()
                    print("Set version to 001_initial")
                else:
                    print("No alembic_version table found")
                    
        except Exception as e:
            print(f"Error cleaning migrations: {e}")
            # Don't fail - let Flask-Migrate handle it

if __name__ == "__main__":
    print("Cleaning migration state...")
    clean_alembic_version()
    print("Done!")
