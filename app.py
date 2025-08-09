# app.py - Complete File with All Fixes
"""
Main application file for Workforce Scheduler
Includes comprehensive upload folder fix and all configurations
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file, session
from flask_login import LoginManager, login_required, login_user, logout_user, current_user 
from flask_migrate import Migrate, stamp
from models import (
    db, Employee, TimeOffRequest, ShiftSwapRequest, ScheduleSuggestion, VacationCalendar, 
    Position, Skill, OvertimeHistory, Schedule, PositionCoverage,
    # Additional models
    OvertimeOpportunity, OvertimeResponse, CoverageGap, EmployeeSkill,
    FatigueTracking, MandatoryOvertimeLog, ShiftPattern, CoverageNotificationResponse,
    FileUpload, CircadianProfile, SleepLog, PositionMessage, MessageReadReceipt,
    MaintenanceIssue, ShiftTradePost, ShiftTradeProposal, ShiftTrade, CasualWorker,
    CoverageRequest, CoverageNotification, CrewCoverageRequirement, Availability
)
from werkzeug.security import check_password_hash
import os
import shutil
from datetime import datetime, timedelta, date
import random
from sqlalchemy import and_, func, text, or_
from sqlalchemy.exc import ProgrammingError, OperationalError
import logging
import traceback

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Database configuration
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workforce.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File upload configuration
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def setup_upload_folder(app):
    """
    Comprehensive upload folder setup with self-checking
    
    Fix Implementation:
    1. Check if upload_files exists
    2. If it's a file, rename it and create directory
    3. Ensure proper permissions
    4. Verify write access
    5. Create test file to confirm
    """
    
    upload_path = os.path.join(app.root_path, 'upload_files')
    
    # Step 1: Initial Analysis
    app.logger.info(f"🔍 Checking upload folder: {upload_path}")
    
    # Step 2: Check current state
    if os.path.exists(upload_path):
        if os.path.isfile(upload_path):
            # It's a file, not a directory - fix this
            app.logger.warning(f"⚠️ {upload_path} is a file, not a directory")
            
            # Rename the file
            backup_name = f"{upload_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.move(upload_path, backup_name)
            app.logger.info(f"📦 Moved file to: {backup_name}")
    
    # Step 3: Create directory if it doesn't exist
    if not os.path.exists(upload_path):
        try:
            os.makedirs(upload_path, exist_ok=True)
            app.logger.info(f"✅ Created upload directory: {upload_path}")
        except Exception as e:
            app.logger.error(f"❌ Failed to create upload directory: {str(e)}")
            # Fallback to temp directory
            upload_path = os.path.join('/tmp', 'workforce_uploads')
            os.makedirs(upload_path, exist_ok=True)
            app.logger.info(f"📁 Using fallback directory: {upload_path}")
    
    # Step 4: Verify it's a directory
    if not os.path.isdir(upload_path):
        app.logger.error(f"❌ {upload_path} is not a directory")
        raise RuntimeError(f"Upload path {upload_path} is not a directory")
    
    # Step 5: Set permissions (Unix-like systems)
    try:
        os.chmod(upload_path, 0o755)
        app.logger.info("✅ Set directory permissions to 755")
    except Exception as e:
        app.logger.warning(f"⚠️ Could not set permissions: {str(e)}")
    
    # Step 6: Test write access
    test_file = os.path.join(upload_path, '.write_test')
    try:
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        app.logger.info("✅ Upload directory is writable")
    except Exception as e:
        app.logger.error(f"❌ Upload directory not writable: {str(e)}")
        raise RuntimeError(f"Upload directory {upload_path} is not writable")
    
    # Step 7: Create subdirectories for organization
    subdirs = ['employees', 'overtime', 'temp', 'archives']
    for subdir in subdirs:
        subdir_path = os.path.join(upload_path, subdir)
        os.makedirs(subdir_path, exist_ok=True)
        app.logger.info(f"📁 Created subdirectory: {subdir}")
    
    # Step 8: Set the upload folder in app config
    app.config['UPLOAD_FOLDER'] = upload_path
    
    # Step 9: Final verification
    app.logger.info(f"✅ Upload folder setup complete: {upload_path}")
    
    # Step 10: Return diagnostics
    return {
        'path': upload_path,
        'exists': os.path.exists(upload_path),
        'is_directory': os.path.isdir(upload_path),
        'is_writable': os.access(upload_path, os.W_OK),
        'subdirectories': [d for d in subdirs if os.path.exists(os.path.join(upload_path, d))]
    }

# Set up upload folder
try:
    upload_diagnostics = setup_upload_folder(app)
    app.logger.info(f"📊 Upload folder diagnostics: {upload_diagnostics}")
except Exception as e:
    app.logger.error(f"❌ Critical error setting up upload folder: {str(e)}")
    # Don't let this stop the app from starting
    app.config['UPLOAD_FOLDER'] = '/tmp/workforce_uploads'
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database
db.init_app(app)
migrate = Migrate(app, db)

# Database Schema Manager
class DatabaseSchemaManager:
    """Handle database schema migrations and fixes"""
    def __init__(self, app, db):
        self.app = app
        self.db = db
        self.fixes_applied = []
        self.issues_found = []
    
    def run_all_fixes(self):
        """Run all database schema fixes"""
        logger.info("🔧 Starting comprehensive database schema check...")
        
        try:
            # Create all tables first
            self.db.create_all()
            logger.info("✅ All tables created/verified")
            
            # Run specific fixes
            self.fix_missing_columns()
            self.fix_shift_swap_columns()
            self.fix_file_upload_table()
            self.create_indexes()
            
            logger.info(f"✅ Database schema fixes complete. Applied {len(self.fixes_applied)} fixes")
            
        except Exception as e:
            logger.error(f"Error during schema fixes: {e}")
            self.db.session.rollback()
    
    def fix_missing_columns(self):
        """Add missing columns to existing tables"""
        # FIXED: Changed 'employees' to 'employee' (singular)
        alterations = [
            ("employee", "department", "VARCHAR(100)"),
            ("employee", "seniority_date", "DATE"),
            ("employee", "default_shift", "VARCHAR(20) DEFAULT 'day'"),
            ("employee", "max_consecutive_days", "INTEGER DEFAULT 14"),
            ("employee", "vacation_days", "FLOAT DEFAULT 10.0"),
            ("employee", "sick_days", "FLOAT DEFAULT 5.0"),
            ("employee", "personal_days", "FLOAT DEFAULT 3.0"),
            ("position", "default_skills", "TEXT"),
            ("schedule", "notes", "TEXT"),
            ("schedule", "overtime_reason", "VARCHAR(200)"),
            ("schedule", "is_overtime", "BOOLEAN DEFAULT FALSE"),
            ("schedule", "original_employee_id", "INTEGER REFERENCES employee(id)"),
            ("overtime_history", "reason", "VARCHAR(200)"),
            ("overtime_history", "approved_by_id", "INTEGER REFERENCES employee(id)"),
            ("overtime_history", "approved_date", "TIMESTAMP"),
            ("overtime_opportunity", "reason", "TEXT"),
            ("overtime_opportunity", "max_hours", "FLOAT"),
            ("overtime_opportunity", "priority", "VARCHAR(20) DEFAULT 'normal'"),
            ("coverage_request", "priority", "VARCHAR(20) DEFAULT 'normal'"),
            ("coverage_request", "reason", "TEXT"),
            ("coverage_request", "incentive_offered", "VARCHAR(200)"),
            ("time_off_request", "coverage_arranged", "BOOLEAN DEFAULT FALSE"),
            ("time_off_request", "coverage_notes", "TEXT"),
            ("file_upload", "processed", "BOOLEAN DEFAULT FALSE"),
            ("file_upload", "error_details", "TEXT")
        ]
        
        for table_name, column_name, column_type in alterations:
            try:
                # Check if column exists first
                check_query = text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = :table_name 
                    AND column_name = :column_name
                """)
                
                result = self.db.session.execute(
                    check_query,
                    {"table_name": table_name, "column_name": column_name}
                ).fetchone()
                
                if not result:
                    # Column doesn't exist, add it
                    alter_query = text(f"""
                        ALTER TABLE {table_name} 
                        ADD COLUMN {column_name} {column_type}
                    """)
                    self.db.session.execute(alter_query)
                    self.fixes_applied.append(f"Added {column_name} to {table_name}")
                    
            except Exception as e:
                # Log the error but continue with other columns
                if "does not exist" not in str(e):
                    logger.warning(f"Could not add {column_name} to {table_name}: {e}")
        
        self.db.session.commit()
    
    def fix_shift_swap_columns(self):
        """Fix shift swap request column naming"""
        try:
            # Check if old column exists
            result = self.db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'shift_swap_request' 
                AND column_name = 'requesting_employee_id'
            """)).fetchone()
            
            if result:
                # Rename column
                self.db.session.execute(text("""
                    ALTER TABLE shift_swap_request 
                    RENAME COLUMN requesting_employee_id TO requester_employee_id
                """))
                self.fixes_applied.append("Renamed requesting_employee_id to requester_employee_id")
            
            self.db.session.commit()
        except Exception as e:
            logger.warning(f"Shift swap column fix skipped: {e}")
    
    def fix_file_upload_table(self):
        """Ensure file_upload table has all required columns"""
        columns = [
            ("rows_processed", "INTEGER DEFAULT 0"),
            ("rows_failed", "INTEGER DEFAULT 0"),
            ("error_details", "TEXT"),
            ("upload_type", "VARCHAR(50)"),
            ("status", "VARCHAR(20) DEFAULT 'pending'")
        ]
        
        for column_name, column_type in columns:
            try:
                result = self.db.session.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'file_upload' 
                    AND column_name = :column_name
                """), {"column_name": column_name}).fetchone()
                
                if not result:
                    self.db.session.execute(text(f"""
                        ALTER TABLE file_upload 
                        ADD COLUMN {column_name} {column_type}
                    """))
                    self.fixes_applied.append(f"Added {column_name} to file_upload")
                    
            except Exception as e:
                logger.warning(f"Could not add {column_name} to file_upload: {e}")
        
        self.db.session.commit()
    
    def create_indexes(self):
        """Create performance indexes"""
        indexes = [
            ("idx_employee_email", "employee", "email"),
            ("idx_employee_crew", "employee", "crew"),
            ("idx_schedule_date", "schedule", "date"),
            ("idx_schedule_employee", "schedule", "employee_id"),
            ("idx_time_off_request_employee", "time_off_request", "employee_id"),
            ("idx_time_off_request_status", "time_off_request", "status"),
            ("idx_file_upload_date", "file_upload", "upload_date")
        ]
        
        for index_name, table_name, columns in indexes:
            try:
                self.db.session.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns})"))
                self.fixes_applied.append(f"Created index {index_name}")
            except Exception as e:
                # Index might already exist or table might not exist
                pass
        
        self.db.session.commit()

# Initialize schema manager
schema_manager = DatabaseSchemaManager(app, db)

# Run fixes on startup
with app.app_context():
    if not os.environ.get('FLASK_MIGRATE'):
        try:
            schema_manager.run_all_fixes()
        except Exception as e:
            logger.warning(f"Schema fix failed: {e}")

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return Employee.query.get(int(user_id))

# Import and register blueprints
from blueprints.auth import auth_bp
from blueprints.main import main_bp

app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)

# Import other blueprints with error handling
try:
    from blueprints.schedule import schedule_bp
    app.register_blueprint(schedule_bp)
    logger.info("✅ Schedule blueprint loaded")
except ImportError as e:
    logger.warning(f"⚠️  Could not import schedule blueprint: {e}")

try:
    from blueprints.supervisor import supervisor_bp
    app.register_blueprint(supervisor_bp)
    logger.info("✅ Supervisor blueprint loaded")
except ImportError as e:
    logger.warning(f"⚠️  Could not import supervisor blueprint: {e}")

try:
    from blueprints.employee import employee_bp
    app.register_blueprint(employee_bp)
    logger.info("✅ Employee blueprint loaded")
except ImportError as e:
    logger.warning(f"⚠️  Could not import employee blueprint: {e}")

try:
    from blueprints.employee_import import employee_import_bp
    app.register_blueprint(employee_import_bp)
    logger.info("✅ Employee import blueprint loaded")
except ImportError as e:
    logger.warning(f"⚠️  Could not import employee_import blueprint: {e}")

# Helper functions for templates
@app.context_processor
def utility_processor():
    """Make utility functions available in templates"""
    return dict(
        now=datetime.now,
        timedelta=timedelta,
        date=date,
        str=str,
        len=len
    )

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    logger.error(f"Internal error: {error}")
    return render_template('500.html'), 500

# Routes
@app.route('/ping')
def ping():
    """Health check endpoint"""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

@app.route('/init-db')
@login_required
def init_db():
    """Initialize database with tables"""
    if not current_user.is_supervisor:
        flash('Only supervisors can initialize the database.', 'error')
        return redirect(url_for('main.index'))
    
    try:
        db.create_all()
        schema_manager.run_all_fixes()
        flash('Database tables created and schemas fixed successfully!', 'success')
        return redirect(url_for('main.dashboard'))
    except Exception as e:
        flash(f'Error initializing database: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

@app.route('/add-overtime-tables')
@login_required
def add_overtime_tables():
    """Add overtime management tables"""
    if not current_user.is_supervisor:
        flash('Only supervisors can modify database tables.', 'error')
        return redirect(url_for('main.index'))
    
    try:
        db.create_all()
        flash('Overtime tables added successfully!', 'success')
        return redirect(url_for('main.dashboard'))
    except Exception as e:
        flash(f'Error adding overtime tables: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

@app.route('/populate-crews')
@login_required
def populate_crews():
    """Populate database with test crew data"""
    if not current_user.is_supervisor:
        flash('Only supervisors can populate test data.', 'error')
        return redirect(url_for('main.index'))
    
    try:
        # Check if we already have data
        if Employee.query.count() > 5:
            flash('Database already contains employee data.', 'warning')
            return redirect(url_for('main.dashboard'))
        
        # Create positions
        positions = [
            {'name': 'Operator', 'department': 'Production'},
            {'name': 'Maintenance Tech', 'department': 'Maintenance'},
            {'name': 'Lead Operator', 'department': 'Production'},
            {'name': 'Supervisor', 'department': 'Management'},
            {'name': 'Electrician', 'department': 'Maintenance'},
            {'name': 'Mechanic', 'department': 'Maintenance'}
        ]
        
        for pos_data in positions:
            position = Position.query.filter_by(name=pos_data['name']).first()
            if not position:
                position = Position(**pos_data)
                db.session.add(position)
        
        db.session.commit()
        
        # Create skills
        skills_list = [
            'Forklift Operation', 'Machine Setup', 'Quality Control',
            'Electrical Work', 'Welding', 'PLC Programming',
            'Hydraulics', 'Pneumatics', 'Safety Training'
        ]
        
        skills = []
        for skill_name in skills_list:
            skill = Skill.query.filter_by(name=skill_name).first()
            if not skill:
                skill = Skill(name=skill_name, description=f"Certified in {skill_name}")
                db.session.add(skill)
            skills.append(skill)
        
        db.session.commit()
        
        # Create employees for each crew
        crews = ['A', 'B', 'C', 'D']
        test_employees = [
            # Crew A
            {
                'name': 'John Smith',
                'email': 'john.smith@company.com',
                'crew': 'A',
                'is_supervisor': True,
                'position': 'Supervisor'
            },
            {
                'name': 'Jane Doe',
                'email': 'jane.doe@company.com',
                'crew': 'A',
                'is_supervisor': False,
                'position': 'Lead Operator'
            },
            {
                'name': 'Mike Johnson',
                'email': 'mike.johnson@company.com',
                'crew': 'A',
                'is_supervisor': False,
                'position': 'Operator'
            },
            # Crew B
            {
                'name': 'Sarah Williams',
                'email': 'sarah.williams@company.com',
                'crew': 'B',
                'is_supervisor': True,
                'position': 'Supervisor'
            },
            {
                'name': 'Tom Brown',
                'email': 'tom.brown@company.com',
                'crew': 'B',
                'is_supervisor': False,
                'position': 'Maintenance Tech'
            },
            # Crew C
            {
                'name': 'Emily Davis',
                'email': 'emily.davis@company.com',
                'crew': 'C',
                'is_supervisor': True,
                'position': 'Supervisor'
            },
            {
                'name': 'Chris Wilson',
                'email': 'chris.wilson@company.com',
                'crew': 'C',
                'is_supervisor': False,
                'position': 'Electrician'
            },
            # Crew D
            {
                'name': 'Lisa Martinez',
                'email': 'lisa.martinez@company.com',
                'crew': 'D',
                'is_supervisor': True,
                'position': 'Supervisor'
            },
            {
                'name': 'David Garcia',
                'email': 'david.garcia@company.com',
                'crew': 'D',
                'is_supervisor': False,
                'position': 'Mechanic'
            },
            # Admin users
            {
                'name': 'Admin User',
                'email': 'admin@company.com',
                'crew': 'A',
                'is_supervisor': True,
                'position': 'Supervisor'
            },
            {
                'name': 'Test Supervisor',
                'email': 'supervisor.a@company.com',
                'crew': 'A',
                'is_supervisor': True,
                'position': 'Supervisor'
            },
            {
                'name': 'Test Supervisor B',
                'email': 'supervisor.b@company.com',
                'crew': 'B',
                'is_supervisor': True,
                'position': 'Supervisor'
            },
            {
                'name': 'Test Supervisor C',
                'email': 'supervisor.c@company.com',
                'crew': 'C',
                'is_supervisor': True,
                'position': 'Supervisor'
            },
            {
                'name': 'Test Supervisor D',
                'email': 'supervisor.d@company.com',
                'crew': 'D',
                'is_supervisor': True,
                'position': 'Supervisor'
            }
        ]
        
        # Add test employees
        for emp_data in test_employees:
            position = Position.query.filter_by(name=emp_data['position']).first()
            
            employee = Employee(
                name=emp_data['name'],
                email=emp_data['email'],
                employee_id=f"EMP{random.randint(1000, 9999)}",
                crew=emp_data['crew'],
                is_supervisor=emp_data['is_supervisor'],
                position_id=position.id if position else None,
                department=position.department if position else 'Production',
                hire_date=date.today() - timedelta(days=random.randint(365, 3650)),
                is_active=True,
                vacation_days=10,
                sick_days=5,
                personal_days=3
            )
            
            # Set password
            employee.set_password('admin123')
            
            # Add some skills
            employee.skills.append(random.choice(skills))
            
            db.session.add(employee)
        
        db.session.commit()
        
        flash('Test data populated successfully!', 'success')
        return redirect(url_for('main.dashboard'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error populating test data: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

if __name__ == '__main__':
    # Only run in development
    app.run(debug=True, host='0.0.0.0', port=5000)
