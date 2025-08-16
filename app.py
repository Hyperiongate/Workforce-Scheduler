# app.py
"""
Main application file for Workforce Scheduler
FIXED VERSION - With context processor for pending counts
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

# Import models that ACTUALLY EXIST in your models.py
from models import db, Employee, Position, Skill, EmployeeSkill, Schedule
from models import TimeOffRequest, Availability, ShiftSwapRequest, ShiftTradePost
from models import OvertimeHistory, CoverageGap, SupervisorMessage, PositionMessage
from models import PositionMessageReadReceipt, CommunicationCategory, CommunicationMessage
from models import CommunicationReadReceipt, CommunicationAttachment, Equipment
from models import MaintenanceIssue, MaintenanceComment, CircadianProfile, SleepLog
from models import CasualWorker, CoverageRequest, FileUpload, CrewCoverageRequirement
from models import VacationCalendar, UploadHistory, SkillRequirement, MaintenanceUpdate
from models import MessageReadReceipt

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

# EMERGENCY DATABASE FIX ROUTE - MUST BE FIRST
@app.route('/fix-db-now')
def fix_db_now():
    """Simple database fix without authentication"""
    try:
        with db.engine.connect() as conn:
            # Add is_admin column if missing
            try:
                conn.execute(text("ALTER TABLE employee ADD COLUMN is_admin BOOLEAN DEFAULT FALSE"))
                conn.commit()
            except:
                pass
            
            # Add other potentially missing columns
            try:
                conn.execute(text("ALTER TABLE employee ADD COLUMN max_hours_per_week INTEGER DEFAULT 40"))
                conn.commit()
            except:
                pass
            
            try:
                conn.execute(text("ALTER TABLE employee ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                conn.commit()
            except:
                pass
            
            try:
                conn.execute(text("ALTER TABLE employee ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                conn.commit()
            except:
                pass
            
            # Create or update admin user
            password_hash = generate_password_hash('admin123')
            
            # Check if admin exists
            result = conn.execute(text("SELECT id FROM employee WHERE email = 'admin@workforce.com'"))
            if result.fetchone():
                # Update existing
                conn.execute(text("""
                    UPDATE employee 
                    SET is_admin = TRUE, 
                        is_supervisor = TRUE,
                        password_hash = :pwd,
                        is_active = TRUE
                    WHERE email = 'admin@workforce.com'
                """), {'pwd': password_hash})
            else:
                # Create new admin user
                conn.execute(text("""
                    INSERT INTO employee (
                        email, password_hash, name, employee_id, 
                        is_supervisor, is_admin, department, crew, is_active
                    ) VALUES (
                        'admin@workforce.com', :pwd, 'Admin User', 'ADMIN001',
                        TRUE, TRUE, 'Management', 'A', TRUE
                    )
                """), {'pwd': password_hash})
            
            conn.commit()
            
            return """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Database Fixed!</title>
                <style>
                    body { 
                        font-family: Arial, sans-serif; 
                        padding: 40px; 
                        background-color: #f5f5f5;
                    }
                    .container {
                        max-width: 600px;
                        margin: 0 auto;
                        background: white;
                        padding: 30px;
                        border-radius: 10px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    }
                    h1 { color: #28a745; }
                    .success { 
                        background: #d4edda; 
                        border: 1px solid #c3e6cb;
                        color: #155724;
                        padding: 15px;
                        border-radius: 5px;
                        margin: 20px 0;
                    }
                    .credentials {
                        background: #e9ecef;
                        padding: 20px;
                        border-radius: 5px;
                        margin: 20px 0;
                    }
                    .btn { 
                        display: inline-block; 
                        margin-top: 20px; 
                        padding: 12px 30px; 
                        background: #007bff; 
                        color: white; 
                        text-decoration: none; 
                        border-radius: 5px;
                        font-size: 16px;
                    }
                    .btn:hover { background: #0056b3; }
                    code {
                        background: #f8f9fa;
                        padding: 2px 6px;
                        border-radius: 3px;
                        font-family: monospace;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>✅ Database Successfully Fixed!</h1>
                    
                    <div class="success">
                        <h3>The following operations completed successfully:</h3>
                        <ul>
                            <li>Added <code>is_admin</code> column to employee table</li>
                            <li>Added <code>max_hours_per_week</code> column</li>
                            <li>Added <code>created_at</code> and <code>updated_at</code> timestamps</li>
                            <li>Created/updated admin user account</li>
                        </ul>
                    </div>
                    
                    <div class="credentials">
                        <h3>Login Credentials:</h3>
                        <p><strong>Email:</strong> <code>admin@workforce.com</code></p>
                        <p><strong>Password:</strong> <code>admin123</code></p>
                        <p style="color: #856404; margin-top: 10px;">
                            <strong>⚠️ Important:</strong> Please change this password after your first login!
                        </p>
                    </div>
                    
                    <a href="/login" class="btn">Go to Login Page →</a>
                </div>
            </body>
            </html>
            """
            
    except Exception as e:
        return f"""
        <html>
        <body style="font-family: Arial; padding: 40px;">
            <h1 style="color: red;">❌ Error Occurred</h1>
            <pre style="background: #f8f9fa; padding: 20px; border-radius: 5px;">
{str(e)}
            </pre>
            <p>Please check the server logs for more details.</p>
        </body>
        </html>
        """

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

@app.context_processor
def inject_pending_counts():
    """Inject pending counts into all templates for navbar"""
    pending_time_off = 0
    pending_swaps = 0
    
    if current_user.is_authenticated and current_user.is_supervisor:
        try:
            pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        except Exception as e:
            logger.warning(f"Could not get pending time off count: {e}")
            
        try:
            pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        except Exception as e:
            logger.warning(f"Could not get pending swaps count: {e}")
    
    return dict(
        pending_time_off=pending_time_off,
        pending_swaps=pending_swaps
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
