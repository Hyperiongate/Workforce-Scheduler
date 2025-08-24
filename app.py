#!/usr/bin/env python3
"""
Main application file for Workforce Scheduler
COMPLETE FILE - Fixed based on ACTUAL Employee model
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
    import tempfile
    app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

# Initialize extensions
from models import db
db.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'

# Import models after db initialization
from models import Employee, TimeOffRequest, ShiftSwapRequest

@login_manager.user_loader
def load_user(user_id):
    return Employee.query.get(int(user_id))

# PROPERLY FIXED DATABASE REPAIR ROUTE - Based on ACTUAL Employee model
@app.route('/fix-db-now')
def fix_db_now():
    """Database fix based on actual Employee model from models.py"""
    try:
        # First, rollback any failed transaction
        db.session.rollback()
        db.session.close()
        
        # Now do the fixes using text() for raw SQL
        with db.engine.begin() as conn:
            # Based on the Employee model in models.py, these are the ACTUAL columns:
            # id, email, password_hash, name, employee_id, phone, position_id, 
            # department, crew, is_supervisor, is_admin, hire_date, is_active, 
            # max_hours_per_week, created_at, updated_at
            
            # Add is_admin column if missing (CRITICAL for login)
            try:
                conn.execute(text("ALTER TABLE employee ADD COLUMN is_admin BOOLEAN DEFAULT FALSE"))
                logger.info("Added is_admin column")
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.error(f"Error adding is_admin: {e}")
            
            # Add other potentially missing columns from the model
            columns_to_add = [
                ('max_hours_per_week', 'INTEGER DEFAULT 48'),
                ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
                ('updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
                ('is_active', 'BOOLEAN DEFAULT TRUE'),
                ('hire_date', 'DATE'),
                ('position_id', 'INTEGER'),
                ('phone', 'VARCHAR(20)')
            ]
            
            for col_name, col_def in columns_to_add:
                try:
                    conn.execute(text(f"ALTER TABLE employee ADD COLUMN {col_name} {col_def}"))
                    logger.info(f"Added {col_name} column")
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        logger.error(f"Error adding {col_name}: {e}")
            
            # Create or update admin user
            password_hash = generate_password_hash('admin123')
            
            # Check if admin exists
            result = conn.execute(text("SELECT id FROM employee WHERE email = 'admin@workforce.com'"))
            admin_exists = result.fetchone()
            
            if admin_exists:
                # Update existing - only update fields that EXIST in the model
                conn.execute(text("""
                    UPDATE employee 
                    SET password_hash = :password_hash,
                        name = 'Admin User',
                        employee_id = 'ADMIN001',
                        is_supervisor = true,
                        is_admin = true,
                        is_active = true,
                        department = 'Administration',
                        crew = 'A'
                    WHERE email = 'admin@workforce.com'
                """), {'password_hash': password_hash})
                message = "Admin user updated"
            else:
                # Create new - only use fields that EXIST in the model
                conn.execute(text("""
                    INSERT INTO employee (
                        email, password_hash, name, employee_id,
                        is_supervisor, is_admin, is_active, 
                        department, crew
                    ) VALUES (
                        'admin@workforce.com', :password_hash, 'Admin User', 'ADMIN001',
                        true, true, true, 'Administration', 'A'
                    )
                """), {'password_hash': password_hash})
                message = "Admin user created"
        
        return f"""
        <html>
        <head>
            <title>Database Fix - Success</title>
            <style>
                body {{ 
                    font-family: Arial, sans-serif; 
                    padding: 40px; 
                    background: #f5f5f5;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                }}
                .container {{
                    background: white;
                    padding: 40px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    max-width: 500px;
                    width: 100%;
                }}
                h1 {{ 
                    color: #28a745; 
                    margin-bottom: 20px;
                }}
                .info-box {{
                    background: #e7f3ff;
                    border-left: 4px solid #2196F3;
                    padding: 20px;
                    margin: 20px 0;
                    border-radius: 4px;
                }}
                .info-box h3 {{
                    margin-top: 0;
                    color: #1976D2;
                }}
                .btn {{
                    display: inline-block;
                    padding: 12px 30px;
                    background: #007bff;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin-top: 20px;
                    font-weight: 500;
                    transition: background 0.3s;
                }}
                .btn:hover {{
                    background: #0056b3;
                }}
                .success-message {{
                    color: #155724;
                    background-color: #d4edda;
                    border: 1px solid #c3e6cb;
                    padding: 15px;
                    border-radius: 4px;
                    margin-bottom: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>✅ Database Fixed Successfully!</h1>
                
                <div class="success-message">
                    <strong>{message}</strong><br>
                    All required columns have been verified/added.
                </div>
                
                <div class="info-box">
                    <h3>Admin Login Credentials:</h3>
                    <p><strong>Email:</strong> admin@workforce.com<br>
                    <strong>Password:</strong> admin123</p>
                    <p style="color: #666; font-size: 14px; margin-top: 10px;">
                        <em>Please change this password after your first login!</em>
                    </p>
                </div>
                
                <a href="/login" class="btn">Go to Login Page →</a>
            </div>
        </body>
        </html>
        """
            
    except Exception as e:
        # Make sure to rollback on error
        db.session.rollback()
        logger.error(f"Fix DB error: {e}")
        
        return f"""
        <html>
        <head>
            <title>Database Fix - Error</title>
            <style>
                body {{ 
                    font-family: Arial, sans-serif; 
                    padding: 40px; 
                    background: #f5f5f5;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                }}
                .container {{
                    background: white;
                    padding: 40px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    max-width: 600px;
                    width: 100%;
                }}
                h1 {{ 
                    color: #dc3545; 
                    margin-bottom: 20px;
                }}
                pre {{
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 5px;
                    overflow-x: auto;
                    border: 1px solid #dee2e6;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                }}
                .btn {{
                    display: inline-block;
                    padding: 12px 30px;
                    background: #6c757d;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin-top: 20px;
                    font-weight: 500;
                }}
                .btn:hover {{
                    background: #5a6268;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>❌ Error Occurred</h1>
                <p>The following error occurred while fixing the database:</p>
                <pre>{str(e)}</pre>
                <p>Please check the server logs for more details.</p>
                <a href="/fix-db-now" class="btn">Try Again</a>
            </div>
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
from blueprints.reset_database import reset_db_bp

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(employee_bp)
app.register_blueprint(supervisor_bp)
app.register_blueprint(schedule_bp)
app.register_blueprint(employee_import_bp)
app.register_blueprint(reset_db_bp)

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
            result = conn.execute(text('SELECT 1'))
            result.fetchone()
        
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

# ==========================================
# AUTO-FIX DATABASE ON STARTUP
# ==========================================

print("Starting database schema check...")
with app.app_context():
    try:
        # First ensure all tables exist
        db.create_all()
        print("✓ Database tables verified/created")
        
        # Then run the column fixes
        try:
            from fix_db_columns import fix_database_schema
            print("Checking for missing columns...")
            fixes = fix_database_schema()
            if fixes > 0:
                print(f"✅ Applied {fixes} database fixes successfully!")
            else:
                print("✅ Database schema is up to date")
        except ImportError:
            print("⚠️  fix_db_columns.py not found - skipping database fixes")
        except Exception as e:
            print(f"⚠️  Could not run database fixes: {e}")
            print("The app will continue but some features may not work correctly")
            
    except Exception as e:
        print(f"⚠️  Could not run database fixes: {e}")
        print("The app will continue but some features may not work correctly")
        # Don't fail the app startup if fixes can't run

# ==========================================
# END OF DATABASE FIX SECTION
# ==========================================

# Run the application
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
