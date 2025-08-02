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

# FIXED UPLOAD FOLDER CONFIGURATION
app.config['UPLOAD_FOLDER'] = 'upload_files'  # Changed from 'uploads' to 'upload_files'
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Handle the upload folder creation properly
upload_folder = app.config['UPLOAD_FOLDER']

# Get absolute path
if not os.path.isabs(upload_folder):
    upload_folder = os.path.join(app.root_path, upload_folder)

# Check if path exists and is a file (not directory)
if os.path.exists(upload_folder) and os.path.isfile(upload_folder):
    # If 'upload_files' exists as a file, use a different name
    print(f"Warning: {upload_folder} exists as a file, using alternative directory")
    app.config['UPLOAD_FOLDER'] = 'temp_uploads'
    upload_folder = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])

# Create the directory if it doesn't exist
try:
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder, exist_ok=True)
        print(f"Created upload folder: {upload_folder}")
    elif not os.path.isdir(upload_folder):
        # If it exists but is not a directory, try to remove and recreate
        os.remove(upload_folder)
        os.makedirs(upload_folder, exist_ok=True)
        print(f"Recreated upload folder: {upload_folder}")
except Exception as e:
    print(f"Warning: Could not create upload folder: {e}")
    # Fall back to using temp directory
    import tempfile
    app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()
    print(f"Using temp directory: {app.config['UPLOAD_FOLDER']}")

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return Employee.query.get(int(user_id))

# NEW FUNCTION: Initialize database with migration fix
def init_db_with_migration_fix():
    """Initialize database with migration fix for multiple heads"""
    with app.app_context():
        try:
            # Try to create tables if they don't exist
            db.create_all()
            
            # Check if we need to stamp the database
            from alembic import command
            from alembic.config import Config
            
            # Get alembic config - check if migrations folder exists
            if os.path.exists('migrations/alembic.ini'):
                config = Config("migrations/alembic.ini")
                
                try:
                    # Try to get current revision
                    from alembic.runtime.migration import MigrationContext
                    from sqlalchemy import create_engine
                    
                    engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])
                    conn = engine.connect()
                    context = MigrationContext.configure(conn)
                    current_rev = context.get_current_revision()
                    
                    if current_rev is None:
                        # No revision set, stamp with latest
                        stamp(revision='head')
                        print("Database stamped with initial revision")
                        
                except Exception as e:
                    print(f"Migration check error: {e}")
                    # If there's an error, try to stamp anyway
                    try:
                        stamp(revision='head')
                    except:
                        pass
                    
        except Exception as e:
            print(f"Database initialization error: {e}")

# Initialize the database with migration fix
with app.app_context():
    init_db_with_migration_fix()

# Import and register blueprints from the blueprints folder
# IMPORT MAIN BLUEPRINT FIRST
try:
    from blueprints.main import main_bp
    app.register_blueprint(main_bp)
    print("Successfully imported main blueprint")
except ImportError as e:
    print(f"Warning: Could not import main blueprint: {e}")

# IMPORT AUTH BLUEPRINT
try:
    from blueprints.auth import auth_bp
    app.register_blueprint(auth_bp)
    print("Successfully imported auth blueprint")
except ImportError as e:
    print(f"Warning: Could not import auth blueprint: {e}")
    # If auth blueprint doesn't exist, set login view to the fallback
    login_manager.login_view = 'login'

try:
    from blueprints.supervisor import supervisor_bp
    app.register_blueprint(supervisor_bp)
    print("Successfully imported supervisor blueprint")
except ImportError as e:
    print(f"Warning: Could not import supervisor blueprint: {e}")

try:
    from blueprints.employee import employee_bp
    app.register_blueprint(employee_bp)
    print("Successfully imported employee blueprint")
except ImportError as e:
    print(f"Warning: Could not import employee blueprint: {e}")

try:
    from blueprints.schedule import schedule_bp
    app.register_blueprint(schedule_bp, url_prefix='/schedule')
    print("Successfully imported schedule blueprint")
except ImportError as e:
    print(f"Warning: Could not import schedule blueprint: {e}")

try:
    from blueprints.employee_import import employee_import_bp
    app.register_blueprint(employee_import_bp)
    print("Successfully imported employee_import blueprint")
except ImportError as e:
    print(f"Warning: Could not import employee_import blueprint: {e}")

# IMPORT OVERTIME BLUEPRINT
try:
    from blueprints.overtime import overtime_bp
    app.register_blueprint(overtime_bp)
    print("Successfully imported overtime blueprint")
except ImportError as e:
    print(f"Warning: Could not import overtime blueprint: {e}")

# IMPORT NEW STAFFING API BLUEPRINT
try:
    from blueprints.staffing_api import staffing_api_bp
    app.register_blueprint(staffing_api_bp)
    print("Successfully imported staffing API blueprint")
except ImportError as e:
    print(f"Warning: Could not import staffing API blueprint: {e}")
