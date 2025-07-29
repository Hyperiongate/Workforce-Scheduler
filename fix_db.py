#!/usr/bin/env python3
"""
Database Fix Script
Fixes missing columns and migration issues
"""

import os
import sys
from app import app, db
from sqlalchemy import text, inspect
from flask_migrate import stamp, init, migrate, upgrade

def fix_database():
    """Fix database issues"""
    with app.app_context():
        print("Starting database fix...")
        
        try:
            # Get database inspector
            inspector = inspect(db.engine)
            
            # Check if schedule table exists
            if 'schedule' in inspector.get_table_names():
                print("Schedule table exists, checking columns...")
                
                # Get columns in schedule table
                columns = [col['name'] for col in inspector.get_columns('schedule')]
                print(f"Current columns in schedule table: {columns}")
                
                # Check if overtime_reason column exists
                if 'overtime_reason' not in columns:
                    print("Adding overtime_reason column to schedule table...")
                    try:
                        db.session.execute(text("""
                            ALTER TABLE schedule 
                            ADD COLUMN overtime_reason VARCHAR(200)
                        """))
                        db.session.commit()
                        print("Column added successfully!")
                    except Exception as e:
                        print(f"Error adding column: {e}")
                        db.session.rollback()
                else:
                    print("overtime_reason column already exists")
                
                # Check other potentially missing columns
                if 'is_overtime' not in columns:
                    print("Adding is_overtime column to schedule table...")
                    try:
                        db.session.execute(text("""
                            ALTER TABLE schedule 
                            ADD COLUMN is_overtime BOOLEAN DEFAULT FALSE
                        """))
                        db.session.commit()
                        print("is_overtime column added successfully!")
                    except Exception as e:
                        print(f"Error adding is_overtime column: {e}")
                        db.session.rollback()
                
                if 'original_employee_id' not in columns:
                    print("Adding original_employee_id column to schedule table...")
                    try:
                        db.session.execute(text("""
                            ALTER TABLE schedule 
                            ADD COLUMN original_employee_id INTEGER REFERENCES employee(id)
                        """))
                        db.session.commit()
                        print("original_employee_id column added successfully!")
                    except Exception as e:
                        print(f"Error adding original_employee_id column: {e}")
                        db.session.rollback()
            else:
                print("Schedule table does not exist!")
                
            # Fix migration issues
            print("\nFixing migration state...")
            
            # Check if migrations folder exists
            if not os.path.exists('migrations'):
                print("Initializing migrations...")
                init()
            
            # Try to stamp the database with current head
            try:
                # First, check if alembic_version table exists
                if 'alembic_version' in inspector.get_table_names():
                    # Get current revision
                    result = db.session.execute(text("SELECT version_num FROM alembic_version"))
                    current_rev = result.fetchone()
                    if current_rev:
                        print(f"Current migration revision: {current_rev[0]}")
                    else:
                        print("No migration revision found, stamping with head...")
                        stamp(revision='head')
                else:
                    print("No alembic_version table, creating and stamping...")
                    stamp(revision='head')
                    
                print("Migration state fixed!")
                
            except Exception as e:
                print(f"Error fixing migrations: {e}")
                # Try to create alembic_version table manually
                try:
                    db.session.execute(text("""
                        CREATE TABLE IF NOT EXISTS alembic_version (
                            version_num VARCHAR(32) NOT NULL,
                            CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                        )
                    """))
                    db.session.commit()
                    print("Created alembic_version table")
                except:
                    pass
                    
            # Create any missing tables
            print("\nCreating any missing tables...")
            db.create_all()
            print("All tables created/verified!")
            
            # Final check
            print("\nFinal verification...")
            tables = inspector.get_table_names()
            print(f"Tables in database: {tables}")
            
            if 'schedule' in tables:
                columns = [col['name'] for col in inspector.get_columns('schedule')]
                print(f"Schedule table columns: {columns}")
                
        except Exception as e:
            print(f"Error during database fix: {e}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            
        print("\nDatabase fix completed!")

def check_and_create_admin():
    """Check and create admin user if needed"""
    with app.app_context():
        try:
            from models import Employee
            
            # Check if any admin exists
            admin = Employee.query.filter_by(is_supervisor=True).first()
            if not admin:
                print("\nNo admin user found, creating default admin...")
                admin = Employee(
                    email='admin@example.com',
                    name='Admin User',
                    is_supervisor=True,
                    department='Management'
                )
                admin.set_password('admin123')
                db.session.add(admin)
                db.session.commit()
                print("Default admin created: admin@example.com / admin123")
            else:
                print(f"\nAdmin user exists: {admin.email}")
                
        except Exception as e:
            print(f"Error checking/creating admin: {e}")
            db.session.rollback()

if __name__ == "__main__":
    print("Workforce Scheduler Database Fix Script")
    print("=" * 50)
    
    fix_database()
    check_and_create_admin()
    
    print("\nScript completed!")
