# app.py - COMPLETE FILE WITH ALL FIXES
"""
Main application file with comprehensive database schema management
Fixes all table schema issues and upload folder configuration
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, login_required, login_user, logout_user, current_user 
from flask_migrate import Migrate, stamp
from models import (
    db, Employee, TimeOffRequest, ShiftSwapRequest, ScheduleSuggestion, VacationCalendar, 
    Position, Skill, OvertimeHistory, Schedule, PositionCoverage,
    # New models for staffing management
    OvertimeOpportunity, OvertimeResponse, CoverageGap, EmployeeSkill,
    FatigueTracking, MandatoryOvertimeLog, ShiftPattern, CoverageNotificationResponse,
    FileUpload  # Added FileUpload model
)
from werkzeug.security import check_password_hash
import os
from datetime import datetime, timedelta, date
import random
from sqlalchemy import and_, func, text
from sqlalchemy.exc import ProgrammingError, OperationalError
import logging

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

# ============================================
# UPLOAD FOLDER CONFIGURATION - COMPLETE FIX
# ============================================

# Set upload configuration
app.config['UPLOAD_FOLDER'] = 'upload_files'
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create upload folder with proper error handling
def ensure_upload_folder():
    """Ensure upload folder exists with proper permissions"""
    upload_folder = app.config['UPLOAD_FOLDER']
    
    # Convert to absolute path
    if not os.path.isabs(upload_folder):
        upload_folder = os.path.join(app.root_path, upload_folder)
    
    # Update config with absolute path
    app.config['UPLOAD_FOLDER'] = upload_folder
    
    try:
        # Create directory if it doesn't exist
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder, mode=0o755)
            logger.info(f"✅ Created upload folder: {upload_folder}")
        else:
            logger.info(f"✅ Upload folder exists: {upload_folder}")
            
        # Test write permissions
        test_file = os.path.join(upload_folder, '.test_write')
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            logger.info("✅ Upload folder is writable")
        except Exception as e:
            logger.error(f"❌ Upload folder not writable: {e}")
            # Try to fix permissions
            try:
                os.chmod(upload_folder, 0o755)
                logger.info("✅ Fixed upload folder permissions")
            except:
                logger.error("❌ Could not fix upload folder permissions")
                
    except Exception as e:
        logger.error(f"❌ Could not create upload folder: {e}")
        # Fallback to temp directory
        import tempfile
        temp_dir = tempfile.gettempdir()
        app.config['UPLOAD_FOLDER'] = temp_dir
        logger.warning(f"⚠️ Using temp directory for uploads: {temp_dir}")

# Call this function after app configuration
ensure_upload_folder()

# ============================================
# HELPER FUNCTIONS FOR FILE UPLOADS
# ============================================

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def secure_upload_file(file, subfolder=None):
    """Securely save an uploaded file"""
    if file and allowed_file(file.filename):
        # Secure the filename
        from werkzeug.utils import secure_filename
        filename = secure_filename(file.filename)
        
        # Add timestamp to prevent collisions
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        name, ext = os.path.splitext(filename)
        filename = f"{name}_{timestamp}{ext}"
        
        # Determine save path
        upload_folder = app.config['UPLOAD_FOLDER']
        if subfolder:
            upload_folder = os.path.join(upload_folder, subfolder)
            os.makedirs(upload_folder, exist_ok=True)
            
        filepath = os.path.join(upload_folder, filename)
        
        # Save file
        file.save(filepath)
        
        return filename, filepath
    
    return None, None

def cleanup_old_uploads(days=7):
    """Remove upload files older than specified days"""
    upload_folder = app.config['UPLOAD_FOLDER']
    cutoff_time = datetime.now() - timedelta(days=days)
    
    try:
        for filename in os.listdir(upload_folder):
            filepath = os.path.join(upload_folder, filename)
            if os.path.isfile(filepath):
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                if file_time < cutoff_time:
                    try:
                        os.remove(filepath)
                        logger.info(f"🗑️ Cleaned up old file: {filename}")
                    except Exception as e:
                        logger.error(f"Could not delete {filename}: {e}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

# Initialize database
db.init_app(app)
migrate = Migrate(app, db)

# COMPREHENSIVE DATABASE SCHEMA FIXES
class DatabaseSchemaManager:
    """Manages all database schema fixes"""
    
    def __init__(self, app, db):
        self.app = app
        self.db = db
        self.fixes_applied = []
        self.issues_found = []
    
    def run_all_fixes(self):
        """Run all schema fixes"""
        with self.app.app_context():
            try:
                logger.info("🔧 Starting comprehensive database schema check...")
                
                # Create all tables first
                self.db.create_all()
                logger.info("✅ All tables created/verified")
                
                # Fix shift_swap_request column names
                self._fix_shift_swap_columns()
                
                # Fix file_upload table
                self._fix_file_upload_table()
                
                # Add any missing columns
                self._add_missing_columns()
                
                # Create indexes
                self._create_indexes()
                
                logger.info(f"✅ Database schema fixes complete. Applied {len(self.fixes_applied)} fixes")
                
                if self.issues_found:
                    logger.warning(f"⚠️ Found {len(self.issues_found)} issues that may need attention")
                    for issue in self.issues_found:
                        logger.warning(f"  - {issue}")
                        
                return True
                
            except Exception as e:
                logger.error(f"❌ Schema fix failed: {e}")
                return False
    
    def _fix_shift_swap_columns(self):
        """Fix shift_swap_request column naming issues"""
        try:
            # Check and rename columns
            with self.db.engine.connect() as conn:
                # Get current column names
                result = conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'shift_swap_request'"
                ))
                columns = [row[0] for row in result]
                
                # Fix requester_employee_id
                if 'requester_id' in columns and 'requester_employee_id' not in columns:
                    conn.execute(text(
                        "ALTER TABLE shift_swap_request "
                        "RENAME COLUMN requester_id TO requester_employee_id"
                    ))
                    self.fixes_applied.append("Renamed requester_id to requester_employee_id")
                    conn.commit()
                
                # Fix requested_employee_id  
                if 'requested_with_id' in columns and 'requested_employee_id' not in columns:
                    conn.execute(text(
                        "ALTER TABLE shift_swap_request "
                        "RENAME COLUMN requested_with_id TO requested_employee_id"
                    ))
                    self.fixes_applied.append("Renamed requested_with_id to requested_employee_id")
                    conn.commit()
                    
        except Exception as e:
            # Table might not exist or be using SQLite
            if "no such table" not in str(e).lower():
                logger.warning(f"Could not fix shift_swap columns: {e}")
    
    def _fix_file_upload_table(self):
        """Ensure file_upload table exists with correct schema"""
        try:
            # Check if table exists
            inspector = self.db.inspect(self.db.engine)
            if 'file_upload' not in inspector.get_table_names():
                # Create the table
                FileUpload.__table__.create(self.db.engine)
                self.fixes_applied.append("Created file_upload table")
                
        except Exception as e:
            logger.warning(f"Could not check/create file_upload table: {e}")
    
    def _add_missing_columns(self):
        """Add any missing columns to existing tables"""
        try:
            with self.db.engine.connect() as conn:
                # Add is_lead to employee if missing
                try:
                    conn.execute(text(
                        "ALTER TABLE employee ADD COLUMN is_lead BOOLEAN DEFAULT FALSE"
                    ))
                    self.fixes_applied.append("Added is_lead column to employee")
                    conn.commit()
                except:
                    pass  # Column already exists
                    
                # Add created_at to tables that need it
                tables_needing_created_at = [
                    'overtime_opportunity', 'coverage_gap', 'fatigue_tracking'
                ]
                
                for table in tables_needing_created_at:
                    try:
                        conn.execute(text(
                            f"ALTER TABLE {table} ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                        ))
                        self.fixes_applied.append(f"Added created_at to {table}")
                        conn.commit()
                    except:
                        pass  # Column already exists
                        
        except Exception as e:
            logger.warning(f"Could not add missing columns: {e}")
    
    def _create_indexes(self):
        """Create performance indexes"""
        indexes = [
            ("idx_employee_crew", "employee", "crew"),
            ("idx_employee_active", "employee", "is_active"),
            ("idx_schedule_date", "schedule", "date"),
            ("idx_overtime_history_date", "overtime_history", "week_start_date"),
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

@app.route('/test-upload-folder')
@login_required
def test_upload_folder():
    """Test route to verify upload folder configuration"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Supervisor access required'}), 403
    
    upload_folder = app.config.get('UPLOAD_FOLDER')
    
    tests = {
        'configured': bool(upload_folder),
        'absolute_path': os.path.isabs(upload_folder) if upload_folder else False,
        'exists': os.path.exists(upload_folder) if upload_folder else False,
        'writable': False,
        'path': upload_folder
    }
    
    # Test write permissions
    if tests['exists']:
        test_file = os.path.join(upload_folder, '.write_test')
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            tests['writable'] = True
        except:
            tests['writable'] = False
    
    return jsonify(tests)

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
        flash('Only supervisors can modify the database.', 'error')
        return redirect(url_for('main.index'))
    
    try:
        # Tables are created automatically by db.create_all()
        db.create_all()
        
        # Add some sample overtime history
        employees = Employee.query.all()
        for employee in employees[:5]:  # Add for first 5 employees
            for i in range(13):  # 13 weeks of history
                week_start = date.today() - timedelta(weeks=12-i)
                hours = random.randint(0, 20)  # Random hours 0-20
                
                history = OvertimeHistory(
                    employee_id=employee.id,
                    week_start_date=week_start,
                    hours_worked=hours
                )
                db.session.add(history)
        
        db.session.commit()
        flash('Overtime tables added successfully with sample data!', 'success')
        return redirect(url_for('main.dashboard'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding overtime tables: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

@app.route('/populate-crews')
@login_required
def populate_crews():
    """Populate employee crews if missing"""
    if not current_user.is_supervisor:
        flash('Only supervisors can modify crew assignments.', 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        # Get employees without crews
        employees_without_crews = Employee.query.filter(
            (Employee.crew == None) | (Employee.crew == '')
        ).all()
        
        if not employees_without_crews:
            flash('All employees already have crew assignments.', 'info')
            return redirect(url_for('main.dashboard'))
        
        # Assign crews evenly
        crews = ['A', 'B', 'C', 'D']
        for idx, employee in enumerate(employees_without_crews):
            employee.crew = crews[idx % 4]
        
        db.session.commit()
        
        flash(f'Successfully assigned crews to {len(employees_without_crews)} employees.', 'success')
        return redirect(url_for('main.dashboard'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error assigning crews: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

# Main entry point
if __name__ == '__main__':
    app.run(debug=True)
