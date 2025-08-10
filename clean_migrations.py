#!/usr/bin/env python3
"""
Clean up migration issues before running flask db upgrade
Fixed for SQLAlchemy 2.0 compatibility
"""
import os
import sys
from sqlalchemy import create_engine, text

def clean_alembic_version():
    """Clean up the alembic_version table"""
    # Get database URL from environment
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("No DATABASE_URL found in environment")
        return
        
    # Fix postgres:// to postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    try:
        # Create engine directly without Flask app
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={
                'sslmode': 'require',
                'keepalives': 1,
                'keepalives_idle': 30,
                'keepalives_interval': 10,
                'keepalives_count': 5,
            }
        )
        
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
                print("No alembic_version table found - creating it")
                conn.execute(text("""
                    CREATE TABLE alembic_version (
                        version_num VARCHAR(32) NOT NULL,
                        CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                    )
                """))
                conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('001_initial')"))
                conn.commit()
                print("Created alembic_version table and set initial version")
                
    except Exception as e:
        print(f"Error cleaning migrations: {e}")
        # Don't fail - let Flask-Migrate handle it
        sys.exit(1)

if __name__ == "__main__":
    print("Cleaning migration state...")
    clean_alembic_version()
    print("Done!")
