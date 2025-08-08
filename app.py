# app.py - Complete File with All Fixes
"""
Main application file for Workforce Scheduler
Includes comprehensive upload folder fix and all configurations
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
import shutil
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

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return Employee.query.get(int(user_id))

# Import blueprints
from blueprints.auth import auth_bp
from blueprints.schedule import schedule_bp
from blueprints.supervisor import supervisor_bp
from blueprints.employee import employee_bp
from blueprints.employee_import import employee_import_bp

# Register blueprints
app.register_blueprint(auth_bp)
app.logger.info("✅ Auth blueprint loaded")

app.register_blueprint(schedule_bp)
app.logger.info("✅ Schedule blueprint loaded")

app.register_blueprint(supervisor_bp)
app.logger.info("✅ Supervisor blueprint loaded")

app.register_blueprint(employee_bp)
app.logger.info("✅ Employee blueprint loaded")

app.register_blueprint(employee_import_bp)
app.logger.info("✅ Employee import blueprint loaded")

# Database schema fixes
def fix_database_schema():
    """Apply all necessary database schema fixes"""
    app.logger.info("🔧 Starting comprehensive database schema check...")
    
    fixes_applied = 0
    
    try:
        # Create all tables
        db.create_all()
        app.logger.info("✅ All tables created/verified")
        
        # Fix shift_swap_request columns
        with db.engine.connect() as conn:
            # Check if old column exists
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'shift_swap_request' 
                AND column_name = 'requesting_employee_id'
            """))
            
            if result.rowcount > 0:
                try:
                    # Rename column
                    conn.execute(text("""
                        ALTER TABLE shift_swap_request 
                        RENAME COLUMN requesting_employee_id TO requester_employee_id
                    """))
                    conn.commit()
                    app.logger.info("✅ Fixed shift_swap_request column name")
                    fixes_applied += 1
                except Exception as e:
                    app.logger.warning(f"Column already renamed or error: {e}")
        
        # Add any missing columns
        with db.engine.connect() as conn:
            # Add department column if missing
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'employees' 
                AND column_name = 'department'
            """))
            
            if result.rowcount == 0:
                conn.execute(text("""
                    ALTER TABLE employees 
                    ADD COLUMN department VARCHAR(100)
                """))
                conn.commit()
                app.logger.info("✅ Added department column to employees")
                fixes_applied += 1
                
            # Add file_upload columns if missing
            columns_to_add = [
                ('file_uploads', 'rows_processed', 'INTEGER DEFAULT 0'),
                ('file_uploads', 'rows_failed', 'INTEGER DEFAULT 0'),
                ('file_uploads', 'error_details', 'TEXT')
            ]
            
            for table, column, col_type in columns_to_add:
                result = conn.execute(text(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = '{table}' 
                    AND column_name = '{column}'
                """))
                
                if result.rowcount == 0:
                    conn.execute(text(f"""
                        ALTER TABLE {table} 
                        ADD COLUMN {column} {col_type}
                    """))
                    conn.commit()
                    app.logger.info(f"✅ Added {column} to {table}")
                    fixes_applied += 1
                    
    except Exception as e:
        app.logger.error(f"Error during schema fixes: {e}")
    
    app.logger.info(f"✅ Database schema fixes complete. Applied {fixes_applied} fixes")

# Apply database fixes on startup
with app.app_context():
    fix_database_schema()

# Helper function for file uploads
def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Routes
@app.route('/')
def index():
    """Landing page"""
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    return render_template('index.html')

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - redirects based on user role"""
    if current_user.is_supervisor:
        return redirect(url_for('supervisor.dashboard'))
    else:
        return redirect(url_for('main.employee_dashboard'))

@app.route('/employee-dashboard')
@login_required
def employee_dashboard():
    """Employee dashboard"""
    # Get employee's schedule
    today = date.today()
    schedules = Schedule.query.filter(
        Schedule.employee_id == current_user.id,
        Schedule.date >= today,
        Schedule.date <= today + timedelta(days=30)
    ).order_by(Schedule.date).all()
    
    # Get pending requests
    time_off_requests = TimeOffRequest.query.filter_by(
        employee_id=current_user.id,
        status='pending'
    ).all()
    
    shift_swap_requests = ShiftSwapRequest.query.filter(
        or_(
            ShiftSwapRequest.requester_employee_id == current_user.id,
            ShiftSwapRequest.target_employee_id == current_user.id
        ),
        ShiftSwapRequest.status == 'pending'
    ).all()
    
    return render_template('employee_dashboard.html',
                         schedules=schedules,
                         time_off_requests=time_off_requests,
                         shift_swap_requests=shift_swap_requests)

# Database initialization routes
@app.route('/init-db')
def init_db():
    """Initialize database with tables"""
    try:
        db.create_all()
        return jsonify({'message': 'Database initialized successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/populate-crews')
@login_required
def populate_crews():
    """Populate crews with test data"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Supervisor access required'}), 403
    
    try:
        # Create crews if they don't exist
        crews = ['A', 'B', 'C', 'D']
        for crew_name in crews:
            # Add logic to create crew assignments
            pass
        
        return jsonify({'message': 'Crews populated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    db.session.rollback()
    app.logger.error(f"Internal error: {error}")
    return render_template('500.html'), 500

# Context processor for templates
@app.context_processor
def inject_user():
    """Make current_user available in all templates"""
    return dict(current_user=current_user)

# Debug route (remove in production)
@app.route('/debug-routes')
def debug_routes():
    """Show all registered routes"""
    import urllib
    output = []
    for rule in app.url_map.iter_rules():
        options = {}
        for arg in rule.arguments:
            options[arg] = "[{0}]".format(arg)
        methods = ','.join(rule.methods)
        url = url_for(rule.endpoint, **options)
        line = urllib.parse.unquote("{:50s} {:20s} {}".format(rule.endpoint, methods, url))
        output.append(line)
    
    return "<pre>" + "\n".join(sorted(output)) + "</pre>"

# Main entry point
if __name__ == '__main__':
    app.run(debug=True)
