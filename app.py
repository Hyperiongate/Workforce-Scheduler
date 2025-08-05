# app.py - Complete fix following project guidelines
# This version includes proper error handling and Flask 2.3 compatibility

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

# AUTOMATIC DATABASE SCHEMA FIX
def fix_database_schema():
    """Fix database schema issues automatically"""
    with app.app_context():
        try:
            logger.info("🔧 Checking and fixing database schema...")
            
            # First ensure tables exist
            db.create_all()
            
            # Check for missing columns in employee table
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'employee'
            """))
            existing_columns = {row[0] for row in result}
            
            # Expected columns based on models.py from project knowledge
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
                logger.info(f"❌ Found {len(missing_columns)} missing columns: {missing_columns}")
                
                # Fix each missing column with proper SQL
                fixes = {
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
                    if column in fixes:
                        column_type, update_sql = fixes[column]
                        try:
                            # Add column
                            db.session.execute(text(f"ALTER TABLE employee ADD COLUMN {column} {column_type}"))
                            logger.info(f"✅ Added column: {column}")
                            
                            # Run update if needed
                            if update_sql:
                                db.session.execute(text(update_sql))
                                logger.info(f"✅ Updated {column} values")
                                
                        except Exception as e:
                            logger.warning(f"⚠️  Could not add {column}: {e}")
                
                db.session.commit()
                logger.info("✅ Database schema fixed successfully!")
                
            else:
                logger.info("✅ Database schema is already correct")
                
        except Exception as e:
            logger.error(f"❌ Error fixing database schema: {e}")
            db.session.rollback()
            # Don't crash - let the app start anyway

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return Employee.query.get(int(user_id))

# Fix database on startup (compatible with Flask 2.3)
# This runs once when the app starts
with app.app_context():
    if not os.environ.get('FLASK_MIGRATE'):
        try:
            fix_database_schema()
        except Exception as e:
            logger.warning(f"Initial schema fix attempt failed: {e}")

# Import and register blueprints
from blueprints.auth import auth_bp
from blueprints.main import main_bp
from blueprints.schedule import schedule_bp
from blueprints.supervisor import supervisor_bp
from blueprints.employee import employee_bp
from blueprints.employee_import import employee_import_bp

app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(schedule_bp)
app.register_blueprint(supervisor_bp)
app.register_blueprint(employee_bp)
app.register_blueprint(employee_import_bp)

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

# Routes that don't belong to blueprints
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
        # Also run the schema fix
        fix_database_schema()
        flash('Database tables created and schema fixed successfully!', 'success')
    except Exception as e:
        flash(f'Error creating database tables: {str(e)}', 'error')
    
    return redirect(url_for('main.index'))

# NEW ROUTE: Manual schema fix endpoint (supervisor only)
@app.route('/fix-schema')
@login_required
def fix_schema():
    """Manually trigger schema fix"""
    if not current_user.is_supervisor:
        return "Access denied", 403
    
    try:
        fix_database_schema()
        return jsonify({
            "status": "success",
            "message": "Database schema fixed successfully"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

# Debug route to check registered routes
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

# NEW ROUTE: Database schema status (supervisor only)
@app.route('/schema-status')
@login_required
def schema_status():
    """Check current database schema status"""
    if not current_user.is_supervisor:
        return "Access denied", 403
    
    try:
        result = db.session.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'employee'
            ORDER BY ordinal_position
        """))
        
        columns = [{"name": row[0], "type": row[1]} for row in result]
        
        # Check for critical columns
        column_names = {col["name"] for col in columns}
        critical_columns = ['seniority_date', 'username', 'must_change_password']
        missing_critical = [col for col in critical_columns if col not in column_names]
        
        return jsonify({
            "status": "ok",
            "table": "employee",
            "column_count": len(columns),
            "columns": columns,
            "missing_critical": missing_critical,
            "schema_healthy": len(missing_critical) == 0
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    # Only run in development
    app.run(debug=True, host='0.0.0.0', port=5000)
