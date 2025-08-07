# database_migration.py
# Enhanced version with vacation_calendar fix and comprehensive migration system

from app import app, db
from models import Employee, UploadHistory, VacationCalendar, TimeOffRequest
from datetime import datetime
from sqlalchemy import text, inspect
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseMigrationManager:
    """Manages all database migrations in a systematic way"""
    
    def __init__(self):
        self.migrations_run = []
        self.errors = []
        
    def run_all_migrations(self):
        """Run all migrations in order"""
        with app.app_context():
            logger.info("="*60)
            logger.info("Starting comprehensive database migration...")
            logger.info("="*60)
            
            # Run migrations in order
            self.add_vacation_calendar_status()
            self.add_authentication_fields()
            self.add_time_off_request_fields()
            self.create_upload_history_table()
            self.create_missing_indexes()
            self.update_existing_employees()
            self.create_test_supervisor()
            
            # Report results
            self.print_summary()
            
    def add_vacation_calendar_status(self):
        """Fix the vacation_calendar status column issue"""
        try:
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('vacation_calendar')]
            
            if 'status' not in columns:
                logger.info("Adding status column to vacation_calendar...")
                db.session.execute(text("""
                    ALTER TABLE vacation_calendar 
                    ADD COLUMN status VARCHAR(20) DEFAULT 'approved'
                """))
                
                db.session.execute(text("""
                    UPDATE vacation_calendar 
                    SET status = 'approved' 
                    WHERE status IS NULL
                """))
                
                db.session.commit()
                self.migrations_run.append("✓ Added status column to vacation_calendar")
            else:
                self.migrations_run.append("✓ vacation_calendar.status already exists")
                
        except Exception as e:
            self.errors.append(f"✗ Error with vacation_calendar.status: {str(e)}")
            db.session.rollback()

    def add_authentication_fields(self):
        """Add authentication fields to Employee table"""
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('employee')]
        
        # Define fields to add
        fields_to_add = {
            'username': "VARCHAR(50) UNIQUE",
            'must_change_password': "BOOLEAN DEFAULT TRUE",
            'first_login': "BOOLEAN DEFAULT TRUE",
            'account_active': "BOOLEAN DEFAULT TRUE",
            'account_created_date': "TIMESTAMP",
            'last_password_change': "TIMESTAMP",
            'last_login': "TIMESTAMP",
            'login_attempts': "INTEGER DEFAULT 0",
            'locked_until': "TIMESTAMP",
            'reset_token': "VARCHAR(100)",
            'reset_token_expires': "TIMESTAMP"
        }
        
        for field, definition in fields_to_add.items():
            if field not in columns:
                try:
                    sql = f"ALTER TABLE employee ADD COLUMN {field} {definition};"
                    db.session.execute(text(sql))
                    self.migrations_run.append(f"✓ Added employee.{field}")
                except Exception as e:
                    if "already exists" not in str(e):
                        self.errors.append(f"✗ Error adding employee.{field}: {str(e)}")
                        
        # Create index on username
        try:
            db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_employee_username ON employee(username);"))
            self.migrations_run.append("✓ Created index on employee.username")
        except Exception as e:
            if "already exists" not in str(e):
                self.errors.append(f"✗ Error creating username index: {str(e)}")
                
        db.session.commit()

    def add_time_off_request_fields(self):
        """Ensure TimeOffRequest has all required fields"""
        try:
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('time_off_request')]
            
            fields_to_add = {
                'created_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                'approved_by': "INTEGER REFERENCES employee(id)",
                'approved_date': "TIMESTAMP",
                'notes': "TEXT",
                'days_requested': "FLOAT"
            }
            
            for field, definition in fields_to_add.items():
                if field not in columns:
                    try:
                        sql = f"ALTER TABLE time_off_request ADD COLUMN {field} {definition};"
                        db.session.execute(text(sql))
                        self.migrations_run.append(f"✓ Added time_off_request.{field}")
                    except Exception as e:
                        if "already exists" not in str(e):
                            self.errors.append(f"✗ Error adding time_off_request.{field}: {str(e)}")
                            
            db.session.commit()
            
        except Exception as e:
            self.errors.append(f"✗ Error updating time_off_request: {str(e)}")
            db.session.rollback()

    def create_upload_history_table(self):
        """Create upload_history table if it doesn't exist"""
        inspector = inspect(db.engine)
        
        if 'upload_history' not in inspector.get_table_names():
            try:
                UploadHistory.__table__.create(db.engine)
                self.migrations_run.append("✓ Created upload_history table")
            except Exception as e:
                self.errors.append(f"✗ Error creating upload_history: {str(e)}")
        else:
            self.migrations_run.append("✓ upload_history table already exists")

    def create_missing_indexes(self):
        """Create performance indexes"""
        indexes_to_create = [
            ("idx_schedule_date_crew", "schedule", "date, crew"),
            ("idx_schedule_employee_date", "schedule", "employee_id, date"),
            ("idx_vacation_calendar_employee_date", "vacation_calendar", "employee_id, date"),
            ("idx_time_off_request_status", "time_off_request", "status"),
            ("idx_overtime_history_employee_week", "overtime_history", "employee_id, week_start_date")
        ]
        
        for index_name, table, columns in indexes_to_create:
            try:
                sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({columns});"
                db.session.execute(text(sql))
                self.migrations_run.append(f"✓ Created index {index_name}")
            except Exception as e:
                if "already exists" not in str(e):
                    self.errors.append(f"✗ Error creating index {index_name}: {str(e)}")
                    
        db.session.commit()

    def update_existing_employees(self):
        """Update existing employees with default values"""
        try:
            employees = Employee.query.all()
            updated = 0
            
            for emp in employees:
                if not emp.email:
                    emp.email = f"{emp.employee_id.lower()}@company.local"
                    
                if not hasattr(emp, 'account_active') or emp.account_active is None:
                    emp.account_active = True
                    
                updated += 1
                
            db.session.commit()
            self.migrations_run.append(f"✓ Updated {updated} existing employees")
            
        except Exception as e:
            self.errors.append(f"✗ Error updating employees: {str(e)}")
            db.session.rollback()

    def create_test_supervisor(self):
        """Create a test supervisor account for initial access"""
        supervisor = Employee.query.filter_by(is_supervisor=True).filter(Employee.username != None).first()
        
        if not supervisor:
            supervisor = Employee.query.filter_by(is_supervisor=True).first()
            
            if supervisor:
                supervisor.username = 'supervisor'
                supervisor.set_password('TempPass123!')
                supervisor.must_change_password = True
                supervisor.first_login = True
                supervisor.account_created_date = datetime.utcnow()
                
                db.session.commit()
                self.migrations_run.append("✓ Updated existing supervisor with login credentials")
                
                logger.info("\n" + "="*50)
                logger.info("SUPERVISOR ACCOUNT READY")
                logger.info("Username: supervisor")
                logger.info("Password: TempPass123!")
                logger.info("="*50 + "\n")
            else:
                # Create new supervisor if none exists
                supervisor = Employee(
                    employee_id='SUP001',
                    name='Test Supervisor',
                    email='supervisor@company.local',
                    is_supervisor=True,
                    crew='A',
                    department='Management',
                    hire_date=datetime.now().date(),
                    username='supervisor'
                )
                supervisor.set_password('TempPass123!')
                supervisor.must_change_password = True
                supervisor.first_login = True
                supervisor.account_created_date = datetime.utcnow()
                
                db.session.add(supervisor)
                db.session.commit()
                self.migrations_run.append("✓ Created test supervisor account")
                
                logger.info("\n" + "="*50)
                logger.info("CREATED TEST SUPERVISOR")
                logger.info("Username: supervisor")
                logger.info("Password: TempPass123!")
                logger.info("="*50 + "\n")
        else:
            self.migrations_run.append(f"✓ Supervisor account already exists: {supervisor.username}")

    def print_summary(self):
        """Print migration summary"""
        logger.info("\n" + "="*60)
        logger.info("MIGRATION SUMMARY")
        logger.info("="*60)
        
        if self.migrations_run:
            logger.info(f"\nSuccessful Migrations ({len(self.migrations_run)}):")
            for migration in self.migrations_run:
                logger.info(f"  {migration}")
                
        if self.errors:
            logger.info(f"\nErrors ({len(self.errors)}):")
            for error in self.errors:
                logger.info(f"  {error}")
        else:
            logger.info("\n✓ All migrations completed successfully!")
            
        logger.info("\n" + "="*60)

# Add this function to run migrations on app startup
def run_migrations_on_startup(app, db):
    """Run this in your app.py after db.init_app(app)"""
    with app.app_context():
        try:
            manager = DatabaseMigrationManager()
            manager.run_all_migrations()
        except Exception as e:
            logger.error(f"Migration error: {str(e)}")

if __name__ == '__main__':
    # Run migrations when script is executed directly
    manager = DatabaseMigrationManager()
    manager.run_all_migrations()
    
    print("\nNext steps:")
    print("1. Deploy this updated migration script")
    print("2. Run: python database_migration.py")
    print("3. All database issues will be fixed automatically")
    print("4. The vacation_calendar.status error will be resolved")
