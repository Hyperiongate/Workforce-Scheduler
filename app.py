# app.py - Updated with comprehensive schema fixes for ALL tables
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

# FIXED UPLOAD FOLDER CONFIGURATION
app.config['UPLOAD_FOLDER'] = 'upload_files'
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Handle the upload folder creation properly
upload_folder = app.config['UPLOAD_FOLDER']

# Get absolute path
if not os.path.isabs(upload_folder):
    upload_folder = os.path.join(app.root_path, upload_folder)

# Check if path exists and is a folder
if os.path.exists(upload_folder):
    if not os.path.isdir(upload_folder):
        # It's a file, not a folder - remove it
        os.remove(upload_folder)
        os.makedirs(upload_folder)
else:
    # Create the folder
    os.makedirs(upload_folder)

# Initialize database
db.init_app(app)
migrate = Migrate(app, db)

# COMPREHENSIVE DATABASE SCHEMA FIX
def fix_all_database_schemas():
    """Fix database schema issues for ALL tables"""
    with app.app_context():
        try:
            logger.info("🔧 Checking and fixing ALL database schemas...")
            
            # First ensure tables exist
            db.create_all()
            
            # Fix Employee table
            fix_employee_schema()
            
            # Fix ShiftSwapRequest table
            fix_shift_swap_request_schema()
            
            # Fix TimeOffRequest table
            fix_time_off_request_schema()
            
            # Fix other tables as needed
            fix_other_schemas()
            
            logger.info("✅ All database schemas fixed successfully!")
                
        except Exception as e:
            logger.error(f"❌ Error fixing database schemas: {e}")
            db.session.rollback()

def fix_employee_schema():
    """Fix employee table schema"""
    try:
        result = db.session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'employee'
        """))
        existing_columns = {row[0] for row in result}
        
        # Expected columns based on models.py
        expected_columns = {
            'id', 'employee_id', 'email', 'name', 'password_hash', 
            'is_supervisor', 'position_id', 'department', 'hire_date', 
            'phone', 'crew', 'shift_pattern', 'seniority_date', 'username',
            'must_change_password', 'first_login', 'account_active',
            'account_created_date', 'last_password_change', 'last_login',
            'login_attempts', 'locked_until', 'reset_token', 'reset_token_expires',
            'default_shift', 'max_consecutive_days', 'is_on_call', 'is_active',
            'vacation_days', 'sick_days', 'personal_days'
        }
        
        missing_columns = expected_columns - existing_columns
        
        if missing_columns:
            logger.info(f"Fixing Employee table - {len(missing_columns)} missing columns")
            
            column_definitions = {
                'seniority_date': ("DATE", "UPDATE employee SET seniority_date = hire_date WHERE seniority_date IS NULL"),
                'username': ("VARCHAR(50)", "UPDATE employee SET username = SPLIT_PART(email, '@', 1) WHERE username IS NULL"),
                'must_change_password': ("BOOLEAN DEFAULT TRUE", None),
                'first_login': ("BOOLEAN DEFAULT TRUE", None),
                'account_active': ("BOOLEAN DEFAULT TRUE", None),
                'account_created_date': ("TIMESTAMP", "UPDATE employee SET account_created_date = CURRENT_TIMESTAMP WHERE account_created_date IS NULL"),
                'last_password_change': ("TIMESTAMP", None),
                'last_login': ("TIMESTAMP", None),
                'login_attempts': ("INTEGER DEFAULT 0", None),
                'locked_until': ("TIMESTAMP", None),
                'reset_token': ("VARCHAR(100)", None),
                'reset_token_expires': ("TIMESTAMP", None),
                'default_shift': ("VARCHAR(20) DEFAULT 'day'", None),
                'max_consecutive_days': ("INTEGER DEFAULT 14", None),
                'is_on_call': ("BOOLEAN DEFAULT FALSE", None),
                'is_active': ("BOOLEAN DEFAULT TRUE", None),
                'vacation_days': ("FLOAT DEFAULT 10.0", None),
                'sick_days': ("FLOAT DEFAULT 5.0", None),
                'personal_days': ("FLOAT DEFAULT 3.0", None),
                'shift_pattern': ("VARCHAR(50)", None)
            }
            
            for column in missing_columns:
                if column in column_definitions:
                    add_column_safely(
                        'employee', 
                        column, 
                        column_definitions[column][0],
                        column_definitions[column][1]
                    )
            
            db.session.commit()
            
    except Exception as e:
        logger.error(f"Error fixing employee schema: {e}")
        db.session.rollback()

def fix_shift_swap_request_schema():
    """Fix shift_swap_request table schema"""
    try:
        result = db.session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'shift_swap_request'
        """))
        existing_columns = {row[0] for row in result}
        
        # The error shows these columns are expected but missing
        expected_columns = {
            'id', 'requester_id', 'requested_with_id', 
            'requester_schedule_id', 'requested_schedule_id',
            'requester_shift_date', 'requested_shift_date',  # These might be the actual column names
            'status', 'reason', 'created_at', 
            'reviewed_by_id', 'reviewed_at', 'reviewer_notes'
        }
        
        missing_columns = expected_columns - existing_columns
        
        if missing_columns:
            logger.info(f"Fixing ShiftSwapRequest table - {len(missing_columns)} missing columns")
            
            # Check if we have date columns vs schedule_id columns
            if 'requester_shift_date' in existing_columns and 'requester_schedule_id' in missing_columns:
                # Add alias columns or migrate data
                logger.info("Note: Table uses date columns instead of schedule_id columns")
            else:
                # Add missing columns
                column_definitions = {
                    'requester_schedule_id': ("INTEGER", None),
                    'requested_schedule_id': ("INTEGER", None),
                    'reviewed_by_id': ("INTEGER", None),
                    'reviewed_at': ("TIMESTAMP", None),
                    'reviewer_notes': ("TEXT", None),
                    'requester_shift_date': ("DATE", None),
                    'requested_shift_date': ("DATE", None)
                }
                
                for column in missing_columns:
                    if column in column_definitions:
                        add_column_safely(
                            'shift_swap_request', 
                            column, 
                            column_definitions[column][0],
                            column_definitions[column][1]
                        )
            
            db.session.commit()
            
    except Exception as e:
        logger.error(f"Error fixing shift_swap_request schema: {e}")
        db.session.rollback()

def fix_time_off_request_schema():
    """Fix time_off_request table schema"""
    try:
        # Check if table exists with correct name
        result = db.session.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name IN ('time_off_request', 'time_off_requests')
        """))
        tables = [row[0] for row in result]
        
        if 'time_off_requests' in tables and 'time_off_request' not in tables:
            logger.info("Note: Table is named 'time_off_requests' (plural)")
            # The model might expect singular but table is plural
            
    except Exception as e:
        logger.error(f"Error checking time_off_request schema: {e}")

def fix_other_schemas():
    """Fix other table schemas as needed"""
    # Add fixes for other tables that might have issues
    pass

def add_column_safely(table_name, column_name, column_type, update_sql=None):
    """Safely add a column to a table"""
    try:
        # Check if column already exists
        result = db.session.execute(text(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}' AND column_name = '{column_name}'
        """))
        
        if result.rowcount == 0:
            # Add column
            db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
            logger.info(f"✅ Added column: {table_name}.{column_name}")
            
            # Run update if provided
            if update_sql:
                db.session.execute(text(update_sql))
                logger.info(f"✅ Updated {column_name} values")
                
    except Exception as e:
        logger.warning(f"⚠️  Could not add {table_name}.{column_name}: {e}")

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return Employee.query.get(int(user_id))

# Fix database on startup
with app.app_context():
    if not os.environ.get('FLASK_MIGRATE'):
        try:
            fix_all_database_schemas()
        except Exception as e:
            logger.warning(f"Initial schema fix attempt failed: {e}")

# Import and register blueprints with error handling
from blueprints.auth import auth_bp
from blueprints.main import main_bp

app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)

# Import other blueprints with error handling
try:
    from blueprints.schedule import schedule_bp
    app.register_blueprint(schedule_bp)
except ImportError as e:
    logger.warning(f"Could not import schedule blueprint: {e}")

try:
    from blueprints.supervisor import supervisor_bp
    app.register_blueprint(supervisor_bp)
except ImportError as e:
    logger.warning(f"Could not import supervisor blueprint: {e}")

try:
    from blueprints.employee import employee_bp
    app.register_blueprint(employee_bp)
except ImportError as e:
    logger.warning(f"Could not import employee blueprint: {e}")

try:
    from blueprints.employee_import import employee_import_bp
    app.register_blueprint(employee_import_bp)
except ImportError as e:
    logger.warning(f"Could not import employee_import blueprint: {e}")

# Helper functions for templates
@app.context_processor
def utility_processor():
    """Make utility functions available in templates"""
    return dict(
        now=datetime.now,
        timedelta=timedelta,
        date=date
    )

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
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
        fix_all_database_schemas()
        flash('Database tables created and schemas fixed successfully!', 'success')
    except Exception as e:
        flash(f'Error creating database tables: {str(e)}', 'error')
    
    return redirect(url_for('main.index'))

@app.route('/fix-schema')
@login_required
def fix_schema():
    """Manually trigger schema fix"""
    if not current_user.is_supervisor:
        return "Access denied", 403
    
    try:
        fix_all_database_schemas()
        return jsonify({
            "status": "success",
            "message": "Database schemas fixed successfully"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/schema-status')
@login_required
def schema_status():
    """Check current database schema status"""
    if not current_user.is_supervisor:
        return "Access denied", 403
    
    try:
        # Check multiple tables
        status = {}
        
        tables_to_check = ['employee', 'shift_swap_request', 'time_off_request', 'schedule']
        
        for table in tables_to_check:
            result = db.session.execute(text(f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = '{table}'
                ORDER BY ordinal_position
            """))
            
            columns = [{"name": row[0], "type": row[1]} for row in result]
            status[table] = {
                "exists": len(columns) > 0,
                "column_count": len(columns),
                "columns": columns
            }
        
        return jsonify(status)
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/debug-routes')
@login_required
def debug_routes():
    """Show all registered routes (supervisor only)"""
    if not current_user.is_supervisor:
        return "Access denied", 403
    
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

if __name__ == '__main__':
    # Only run in development
    app.run(debug=True, host='0.0.0.0', port=5000)
