# migration_add_shift_preferences.py
"""
Database migration to add ShiftPreference table
Run this script to add the new table to your existing database
"""

from app import app, db
from models import Employee  # Import existing models
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey

def add_shift_preferences_table():
    """Add the shift_preferences table to the database"""
    
    with app.app_context():
        # Create the SQL for the new table
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS shift_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            shift_length_pref INTEGER DEFAULT 50,
            work_pattern_pref INTEGER DEFAULT 50,
            weekend_pref INTEGER DEFAULT 50,
            schedule_type_pref INTEGER DEFAULT 50,
            handover_time INTEGER DEFAULT 0,
            selected_schedule VARCHAR(50),
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            additional_preferences TEXT,
            comments TEXT,
            reviewed_by_id INTEGER,
            reviewed_at DATETIME,
            review_notes TEXT,
            FOREIGN KEY (employee_id) REFERENCES employees (id),
            FOREIGN KEY (reviewed_by_id) REFERENCES employees (id)
        );
        """
        
        # Execute the SQL
        try:
            db.session.execute(create_table_sql)
            db.session.commit()
            print("✅ Successfully created shift_preferences table")
            
            # Create an index for faster queries
            index_sql = """
            CREATE INDEX IF NOT EXISTS idx_shift_pref_employee 
            ON shift_preferences (employee_id, is_active);
            """
            db.session.execute(index_sql)
            db.session.commit()
            print("✅ Created index on shift_preferences table")
            
        except Exception as e:
            print(f"❌ Error creating table: {e}")
            db.session.rollback()
            return False
        
        # Verify the table was created
        try:
            result = db.session.execute("SELECT COUNT(*) FROM shift_preferences")
            count = result.scalar()
            print(f"✅ Table verified - current records: {count}")
            return True
        except Exception as e:
            print(f"❌ Table verification failed: {e}")
            return False

def populate_sample_preferences():
    """Optional: Add some sample preference data"""
    
    with app.app_context():
        try:
            # Get some employees
            employees = Employee.query.filter_by(is_supervisor=False, is_active=True).limit(5).all()
            
            if not employees:
                print("No employees found to create sample preferences")
                return
            
            sample_preferences = [
                {
                    'shift_length_pref': 70,  # Prefers 12-hour
                    'work_pattern_pref': 30,  # Prefers shorter stretches
                    'weekend_pref': 80,       # Wants full weekends
                    'schedule_type_pref': 20, # Prefers fixed
                    'selected_schedule': 'fixed_223_12'
                },
                {
                    'shift_length_pref': 30,  # Prefers 8-hour
                    'work_pattern_pref': 60,  # Balanced
                    'weekend_pref': 50,       # Balanced
                    'schedule_type_pref': 80, # Prefers rotating
                    'selected_schedule': 'southern_swing_8'
                },
                {
                    'shift_length_pref': 90,  # Strongly prefers 12-hour
                    'work_pattern_pref': 70,  # Prefers longer breaks
                    'weekend_pref': 100,      # Must have full weekends
                    'schedule_type_pref': 0,  # Must be fixed
                    'selected_schedule': 'pitman_12'
                }
            ]
            
            for i, emp in enumerate(employees[:3]):
                if i < len(sample_preferences):
                    pref_data = sample_preferences[i]
                    
                    insert_sql = """
                    INSERT INTO shift_preferences 
                    (employee_id, shift_length_pref, work_pattern_pref, weekend_pref, 
                     schedule_type_pref, selected_schedule, submitted_at, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    
                    db.session.execute(insert_sql, [
                        emp.id,
                        pref_data['shift_length_pref'],
                        pref_data['work_pattern_pref'],
                        pref_data['weekend_pref'],
                        pref_data['schedule_type_pref'],
                        pref_data['selected_schedule'],
                        datetime.now(),
                        True
                    ])
            
            db.session.commit()
            print(f"✅ Added sample preferences for {min(3, len(employees))} employees")
            
        except Exception as e:
            print(f"❌ Error adding sample preferences: {e}")
            db.session.rollback()

def verify_installation():
    """Verify the migration was successful"""
    
    with app.app_context():
        try:
            # Check table exists
            result = db.session.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='shift_preferences';
            """)
            
            if result.scalar():
                print("✅ shift_preferences table exists")
                
                # Check columns
                result = db.session.execute("PRAGMA table_info(shift_preferences)")
                columns = result.fetchall()
                print(f"✅ Table has {len(columns)} columns")
                
                # Check for data
                result = db.session.execute("SELECT COUNT(*) FROM shift_preferences")
                count = result.scalar()
                print(f"✅ Table contains {count} records")
                
                return True
            else:
                print("❌ shift_preferences table not found")
                return False
                
        except Exception as e:
            print(f"❌ Verification failed: {e}")
            return False

if __name__ == "__main__":
    print("=" * 50)
    print("SHIFT PREFERENCES TABLE MIGRATION")
    print("=" * 50)
    
    # Step 1: Create the table
    print("\n1. Creating shift_preferences table...")
    if add_shift_preferences_table():
        
        # Step 2: Optionally add sample data
        print("\n2. Adding sample preferences...")
        response = input("Do you want to add sample preference data? (y/n): ")
        if response.lower() == 'y':
            populate_sample_preferences()
        
        # Step 3: Verify installation
        print("\n3. Verifying installation...")
        verify_installation()
        
        print("\n" + "=" * 50)
        print("MIGRATION COMPLETE!")
        print("=" * 50)
        print("\nNext steps:")
        print("1. Add the ShiftPreference model to your models.py")
        print("2. Register the schedule_preferences blueprint in app.py")
        print("3. Add navigation link to the preferences tool")
        print("4. Test the new feature at /schedule/preferences")
    else:
        print("\n❌ Migration failed. Please check your database connection.")
