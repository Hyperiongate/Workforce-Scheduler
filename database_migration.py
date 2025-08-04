# database_migration.py
# Run this script to add the new fields to your database

from app import app, db
from models import Employee, UploadHistory
from datetime import datetime

def add_authentication_fields():
    """Add authentication fields to Employee table"""
    with app.app_context():
        # Check if columns already exist
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('employee')]
        
        # SQL commands to add missing columns
        sql_commands = []
        
        if 'username' not in columns:
            sql_commands.append("ALTER TABLE employee ADD COLUMN username VARCHAR(50) UNIQUE;")
        if 'password' not in columns:
            sql_commands.append("ALTER TABLE employee ADD COLUMN password VARCHAR(200);")
        if 'must_change_password' not in columns:
            sql_commands.append("ALTER TABLE employee ADD COLUMN must_change_password BOOLEAN DEFAULT TRUE;")
        if 'first_login' not in columns:
            sql_commands.append("ALTER TABLE employee ADD COLUMN first_login BOOLEAN DEFAULT TRUE;")
        if 'account_active' not in columns:
            sql_commands.append("ALTER TABLE employee ADD COLUMN account_active BOOLEAN DEFAULT TRUE;")
        if 'account_created_date' not in columns:
            sql_commands.append("ALTER TABLE employee ADD COLUMN account_created_date DATETIME;")
        if 'last_password_change' not in columns:
            sql_commands.append("ALTER TABLE employee ADD COLUMN last_password_change DATETIME;")
        if 'last_login' not in columns:
            sql_commands.append("ALTER TABLE employee ADD COLUMN last_login DATETIME;")
        if 'login_attempts' not in columns:
            sql_commands.append("ALTER TABLE employee ADD COLUMN login_attempts INTEGER DEFAULT 0;")
        if 'locked_until' not in columns:
            sql_commands.append("ALTER TABLE employee ADD COLUMN locked_until DATETIME;")
        if 'reset_token' not in columns:
            sql_commands.append("ALTER TABLE employee ADD COLUMN reset_token VARCHAR(100);")
        if 'reset_token_expires' not in columns:
            sql_commands.append("ALTER TABLE employee ADD COLUMN reset_token_expires DATETIME;")
            
        # Execute SQL commands
        for sql in sql_commands:
            try:
                db.session.execute(db.text(sql))
                print(f"Executed: {sql}")
            except Exception as e:
                print(f"Error executing {sql}: {str(e)}")
                
        # Create index on username
        try:
            db.session.execute(db.text("CREATE INDEX idx_employee_username ON employee(username);"))
            print("Created index on username")
        except:
            print("Index on username may already exist")
            
        # Commit changes
        db.session.commit()
        print("Authentication fields added successfully!")

def create_upload_history_table():
    """Create upload_history table if it doesn't exist"""
    with app.app_context():
        # Check if table exists
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        
        if 'upload_history' not in inspector.get_table_names():
            # Create the table
            UploadHistory.__table__.create(db.engine)
            print("Created upload_history table")
        else:
            print("upload_history table already exists")

def update_existing_employees():
    """Update existing employees with default values"""
    with app.app_context():
        employees = Employee.query.all()
        updated = 0
        
        for emp in employees:
            # Set default email if missing
            if not emp.email:
                emp.email = f"{emp.employee_id.lower()}@company.com"
                
            # Set name if missing (for older records)
            if not hasattr(emp, 'name') or not emp.name:
                emp.name = f"Employee {emp.employee_id}"
                
            # Set account_active if not set
            if not hasattr(emp, 'account_active'):
                emp.account_active = True
                
            updated += 1
            
        db.session.commit()
        print(f"Updated {updated} existing employees with default values")

def create_test_supervisor():
    """Create a test supervisor account for initial access"""
    with app.app_context():
        # Check if any supervisor exists
        supervisor = Employee.query.filter_by(is_supervisor=True).first()
        
        if not supervisor:
            # Create test supervisor
            from utils.account_generator import AccountGenerator
            
            supervisor = Employee(
                employee_id='SUP001',
                name='Test Supervisor',
                email='supervisor@company.com',
                is_supervisor=True,
                crew='A',
                department='Management',
                hire_date=datetime.now().date()
            )
            
            # Set login credentials
            supervisor.username = 'supervisor'
            supervisor.set_password('TempPass123!')
            supervisor.must_change_password = True
            supervisor.first_login = True
            supervisor.account_created_date = datetime.utcnow()
            
            db.session.add(supervisor)
            db.session.commit()
            
            print("\n" + "="*50)
            print("CREATED TEST SUPERVISOR ACCOUNT")
            print("Username: supervisor")
            print("Password: TempPass123!")
            print("You will be required to change this password on first login")
            print("="*50 + "\n")
        else:
            print("Supervisor account already exists")

if __name__ == '__main__':
    print("Starting database migration...")
    
    # Add authentication fields
    add_authentication_fields()
    
    # Create upload history table
    create_upload_history_table()
    
    # Update existing employees
    update_existing_employees()
    
    # Create test supervisor
    create_test_supervisor()
    
    print("\nDatabase migration completed!")
    print("\nNext steps:")
    print("1. Restart your Flask application")
    print("2. Log in with the supervisor account")
    print("3. Upload employee data and create accounts")
