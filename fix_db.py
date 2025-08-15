#!/usr/bin/env python3
"""
Database Fix Script
Fixes missing columns including is_admin
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
            
            # CRITICAL FIX: Check employee table for is_admin column
            if 'employee' in inspector.get_table_names():
                print("\n=== Fixing Employee Table ===")
                columns = [col['name'] for col in inspector.get_columns('employee')]
                print(f"Current columns in employee table: {columns}")
                
                # Add is_admin column if missing
                if 'is_admin' not in columns:
                    print("CRITICAL: Adding is_admin column to employee table...")
                    try:
                        db.session.execute(text("""
                            ALTER TABLE employee 
                            ADD COLUMN is_admin BOOLEAN DEFAULT FALSE
                        """))
                        db.session.commit()
                        print("✅ is_admin column added successfully!")
                    except Exception as e:
                        print(f"Error adding is_admin column: {e}")
                        db.session.rollback()
                else:
                    print("✅ is_admin column already exists")
                
                # Update admin privileges
                print("Updating admin privileges...")
                try:
                    db.session.execute(text("""
                        UPDATE employee 
                        SET is_admin = TRUE 
                        WHERE email = 'admin@workforce.com' 
                        OR email = 'admin@example.com'
                        OR is_supervisor = TRUE
                    """))
                    db.session.commit()
                    print("✅ Admin privileges updated")
                except Exception as e:
                    print(f"Error updating admin privileges: {e}")
                    db.session.rollback()
            
            # Check if schedule table exists
            if 'schedule' in inspector.get_table_names():
                print("\nSchedule table exists, checking columns...")
                
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
            
            if 'employee' in tables:
                columns = [col['name'] for col in inspector.get_columns('employee')]
                print(f"Employee table columns: {columns}")
                if 'is_admin' in columns:
                    print("✅ VERIFIED: is_admin column exists!")
                
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
            
            # First check for admin@workforce.com
            admin = Employee.query.filter_by(email='admin@workforce.com').first()
            if not admin:
                print("\nCreating admin@workforce.com...")
                admin = Employee(
                    email='admin@workforce.com',
                    name='Admin User',
                    employee_id='ADMIN001',
                    is_supervisor=True,
                    is_admin=True,
                    is_active=True,
                    department='Administration'
                )
                admin.set_password('admin123')
                db.session.add(admin)
                db.session.commit()
                print("✅ Created admin: admin@workforce.com / admin123")
            else:
                print(f"\n✅ Admin user exists: {admin.email}")
                # Ensure they have admin privileges
                if not admin.is_admin:
                    admin.is_admin = True
                    db.session.commit()
                    print("✅ Updated admin privileges")
                
        except Exception as e:
            print(f"Error checking/creating admin: {e}")
            db.session.rollback()

if __name__ == "__main__":
    print("Workforce Scheduler Database Fix Script")
    print("=" * 50)
    
    fix_database()
    check_and_create_admin()
    
    print("\nScript completed!")
    print("\nYou should now be able to login with:")
    print("Email: admin@workforce.com")
    print("Password: admin123")
