# app.py
"""
Main application file for Workforce Scheduler
WITH EMERGENCY DATABASE FIX INCLUDED
"""

from flask import Flask, render_template, redirect, url_for, flash, jsonify, request
from flask_login import LoginManager, login_required, current_user
from flask_migrate import Migrate
import os
import logging
from datetime import datetime, date, timedelta
from sqlalchemy import text, inspect
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import OperationalError, ProgrammingError
from werkzeug.security import generate_password_hash

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
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'poolclass': NullPool,
        'connect_args': {
            'sslmode': 'require',
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 5,
            'keepalives_count': 5
        }
    }
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workforce.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Upload configuration
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'upload_files')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'xls', 'xlsx'}

# Ensure upload folder exists (handle case where it might be a file)
try:
    if os.path.exists(app.config['UPLOAD_FOLDER']):
        if not os.path.isdir(app.config['UPLOAD_FOLDER']):
            # It exists but is not a directory, remove it
            os.remove(app.config['UPLOAD_FOLDER'])
            os.makedirs(app.config['UPLOAD_FOLDER'])
    else:
        os.makedirs(app.config['UPLOAD_FOLDER'])
except Exception as e:
    logger.warning(f"Could not create upload folder: {e}")
    # Use temp directory as fallback
    app.config['UPLOAD_FOLDER'] = '/tmp/upload_files'
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Import models and initialize database
from models import db, Employee, Position, Skill, EmployeeSkill, Schedule, ShiftTemplate
from models import TimeOffRequest, Availability, ScheduleSwapRequest, Message, Notification
from models import OvertimeRecord, TrainingRecord, Certificate, PositionRequirement
from models import SkillRequirement, PositionMessage, MessageReadReceipt, VacationCalendar

# Initialize database with app
db.init_app(app)
migrate = Migrate(app, db)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'

@login_manager.user_loader
def load_user(user_id):
    return Employee.query.get(int(user_id))

# Import blueprints
from blueprints.auth import auth_bp
from blueprints.main import main_bp
from blueprints.employee import employee_bp
from blueprints.supervisor import supervisor_bp
from blueprints.schedule import schedule_bp
from blueprints.employee_import import employee_import_bp

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(employee_bp)
app.register_blueprint(supervisor_bp)
app.register_blueprint(schedule_bp)
app.register_blueprint(employee_import_bp)

# EMERGENCY DATABASE FIX ROUTE
@app.route('/emergency-db-fix')
def emergency_db_fix():
    """Emergency route to fix database issues"""
    results = []
    
    try:
        with app.app_context():
            # Check if is_admin column exists
            with db.engine.connect() as conn:
                # Check columns in employee table
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'employee'
                """))
                columns = [row[0] for row in result]
                results.append(f"Current employee columns: {columns}")
                
                # Add is_admin column if missing
                if 'is_admin' not in columns:
                    results.append("Adding is_admin column...")
                    conn.execute(text("""
                        ALTER TABLE employee 
                        ADD COLUMN is_admin BOOLEAN DEFAULT FALSE
                    """))
                    conn.commit()
                    results.append("✅ Added is_admin column")
                else:
                    results.append("✅ is_admin column already exists")
                
                # Add other potentially missing columns
                if 'max_hours_per_week' not in columns:
                    results.append("Adding max_hours_per_week column...")
                    conn.execute(text("""
                        ALTER TABLE employee 
                        ADD COLUMN max_hours_per_week INTEGER DEFAULT 40
                    """))
                    conn.commit()
                    results.append("✅ Added max_hours_per_week column")
                
                if 'created_at' not in columns:
                    results.append("Adding created_at column...")
                    conn.execute(text("""
                        ALTER TABLE employee 
                        ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    """))
                    conn.commit()
                    results.append("✅ Added created_at column")
                
                if 'updated_at' not in columns:
                    results.append("Adding updated_at column...")
                    conn.execute(text("""
                        ALTER TABLE employee 
                        ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    """))
                    conn.commit()
                    results.append("✅ Added updated_at column")
                
                # Set admin user
                results.append("Setting admin privileges...")
                conn.execute(text("""
                    UPDATE employee 
                    SET is_admin = TRUE, is_supervisor = TRUE 
                    WHERE email = 'admin@workforce.com'
                """))
                conn.commit()
                results.append("✅ Updated admin privileges")
                
                # Check if admin exists
                result = conn.execute(text("""
                    SELECT id, email, name 
                    FROM employee 
                    WHERE email = 'admin@workforce.com'
                """))
                admin = result.fetchone()
                
                if not admin:
                    results.append("Creating admin user...")
                    # Hash the password
                    password_hash = generate_password_hash('admin123')
                    
                    conn.execute(text("""
                        INSERT INTO employee (
                            email, password_hash, name, employee_id, 
                            is_supervisor, is_admin, department, crew, is_active
                        ) VALUES (
                            'admin@workforce.com', :password_hash, 'Admin User', 'ADMIN001',
                            TRUE, TRUE, 'Management', 'A', TRUE
                        )
                    """), {'password_hash': password_hash})
                    conn.commit()
                    results.append("✅ Created admin user (admin@workforce.com / admin123)")
                else:
                    results.append(f"✅ Admin user exists: {admin[1]}")
                
                # Final verification
                result = conn.execute(text("""
                    SELECT email, is_admin, is_supervisor 
                    FROM employee 
                    WHERE email = 'admin@workforce.com'
                """))
                final_check = result.fetchone()
                if final_check:
                    results.append(f"✅ Final check - Admin: {final_check[0]}, is_admin: {final_check[1]}, is_supervisor: {final_check[2]}")
                
    except Exception as e:
        results.append(f"❌ Error: {str(e)}")
        results.append("Please check logs for details")
    
    # Return results as HTML
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Database Fix Results</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            h1 { color: #333; }
            .result { margin: 10px 0; padding: 10px; background: #f5f5f5; border-radius: 5px; }
            .success { color: green; }
            .error { color: red; }
            .btn { 
                display: inline-block; 
                margin-top: 20px; 
                padding: 10px 20px; 
                background: #007bff; 
                color: white; 
                text-decoration: none; 
                border-radius: 5px; 
            }
            .btn:hover { background: #0056b3; }
        </style>
    </head>
    <body>
        <h1>Database Fix Results</h1>
        <div>
    """
    
    for result in results:
        css_class = 'success' if '✅' in result else 'error' if '❌' in result else ''
        html += f'<div class="result {css_class}">{result}</div>'
    
    html += """
        </div>
        <a href="/login" class="btn">Try Login Now</a>
    </body>
    </html>
    """
    
    return html

# Add 404 handler
@app.errorhandler(404)
def not_found_error(error):
    logger.warning(f"404 error: {request.url}")
    if request.endpoint and 'api' in request.endpoint:
        return jsonify({'error': 'Not found'}), 404
    return render_template('404.html'), 404

# Add 500 handler
@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {error}")
    db.session.rollback()
    if request.endpoint and 'api' in request.endpoint:
        return jsonify({'error': 'Internal server error'}), 500
    return render_template('500.html'), 500

# Health check endpoint
@app.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        with db.engine.connect() as conn:
            conn.execute(text('SELECT 1'))
            conn.commit()
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 503

# Context processors
@app.context_processor
def inject_user_permissions():
    """Inject user permissions into all templates"""
    return dict(
        is_supervisor=lambda: current_user.is_authenticated and current_user.is_supervisor
    )

# Utility functions
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Run the application
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
