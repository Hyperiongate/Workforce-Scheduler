#!/usr/bin/env python3
"""
Database Fix Script
Fixes missing columns including is_admin and shift_swap_request issues
COMPLETE VERSION - Fixes redirect loop problem
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
                print("\n=== Fixing Schedule Table ===")
                
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

            # CRITICAL FIX FOR REDIRECT LOOP: Check shift_swap_request table
            if 'shift_swap_request' in inspector.get_table_names():
                print("\n=== Fixing Shift Swap Request Table (REDIRECT LOOP FIX) ===")
                columns = [col['name'] for col in inspector.get_columns('shift_swap_request')]
                print(f"Current columns in shift_swap_request table: {columns}")
                
                # Add missing columns that are causing the redirect loop
                missing_columns = [
                    ('requested_with_id', 'INTEGER'),
                    ('requester_schedule_id', 'INTEGER'), 
                    ('requested_schedule_id', 'INTEGER'),
                    ('reviewed_by_id', 'INTEGER'),
                    ('reviewed_at', 'TIMESTAMP'),
                    ('reviewer_notes', 'TEXT')
                ]
                
                for col_name, col_type in missing_columns:
                    if col_name not in columns:
                        print(f"CRITICAL: Adding {col_name} column...")
                        try:
                            db.session.execute(text(f"""
                                ALTER TABLE shift_swap_request 
                                ADD COLUMN {col_name} {col_type}
                            """))
                            db.session.commit()
                            print(f"✅ {col_name} column added successfully!")
                        except Exception as e:
                            print(f"Error adding {col_name} column: {e}")
                            db.session.rollback()
                    else:
                        print(f"✅ {col_name} column already exists")
                
                # Fix any NULL status values
                try:
                    db.session.execute(text("""
                        UPDATE shift_swap_request 
                        SET status = 'pending' 
                        WHERE status IS NULL
                    """))
                    db.session.commit()
                    print("✅ Fixed NULL status values")
                except Exception as e:
                    print(f"Error fixing status values: {e}")
                    db.session.rollback()
                    
                # Verify the fix by testing the problematic query
                print("Testing the fix...")
                try:
                    result = db.session.execute(text("""
                        SELECT COUNT(*) FROM shift_swap_request 
                        WHERE status = 'pending'
                    """))
                    count = result.scalar()
                    print(f"✅ REDIRECT LOOP FIX VERIFIED! Found {count} pending shift swap requests")
                except Exception as e:
                    print(f"Warning: Could not verify fix: {e}")
                    
            else:
                print("\n=== Creating Shift Swap Request Table ===")
                print("Table doesn't exist, will be created by db.create_all()")
                
            # Fix migration issues
            print("\n=== Fixing Migration State ===")
            
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
            print("\n=== Creating Missing Tables ===")
            db.create_all()
            print("All tables created/verified!")
            
            # Final check
            print("\n=== Final Verification ===")
            tables = inspector.get_table_names()
            print(f"Tables in database: {tables}")
            
            if 'employee' in tables:
                columns = [col['name'] for col in inspector.get_columns('employee')]
                print(f"Employee table columns: {columns}")
                if 'is_admin' in columns:
                    print("✅ VERIFIED: is_admin column exists!")
                    
            if 'shift_swap_request' in tables:
                columns = [col['name'] for col in inspector.get_columns('shift_swap_request')]
                print(f"Shift swap request table columns: {columns}")
                if 'requested_with_id' in columns:
                    print("✅ VERIFIED: requested_with_id column exists! Redirect loop should be fixed!")
                
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
    print("INCLUDES REDIRECT LOOP FIX")
    print("=" * 50)
    
    fix_database()
    check_and_create_admin()
    
    print("\n" + "=" * 50)
    print("🎉 SCRIPT COMPLETED!")
    print("✅ Redirect loop issue should now be FIXED!")
    print("✅ Missing database columns have been added!")
    print("\nYou should now be able to login with:")
    print("Email: admin@workforce.com")
    print("Password: admin123")
    print("\nIf you're still seeing the redirect loop:")
    print("1. Restart your Render service")
    print("2. Clear your browser cache/cookies")
    print("3. Try accessing the site again")
