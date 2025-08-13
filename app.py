# app.py
"""
Main application file for Workforce Scheduler
Fixed version that works with your models.py and auto-fixes database issues
"""

from flask import Flask, render_template, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_required, current_user
from flask_migrate import Migrate
import os
import logging
from datetime import datetime, date, timedelta
from sqlalchemy import text, inspect
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import OperationalError, ProgrammingError

# Import your models
from models import db, Employee

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
            'keepalives_interval': 10,
            'keepalives_count': 5,
        }
    }
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workforce.db'
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {}

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File upload configuration
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = '/tmp/upload_files' if os.environ.get('RENDER') else 'upload_files'

# Create upload folder
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    try:
        return Employee.query.get(int(user_id))
    except:
        return None

# AUTOMATIC DATABASE FIX FUNCTION
def fix_database_schema():
    """Automatically fix missing columns in database"""
    with app.app_context():
        try:
            # Test if is_admin column exists by trying to query it
            db.session.execute(text("SELECT is_admin FROM employee LIMIT 1"))
            logger.info("✅ is_admin column already exists")
        except (OperationalError, ProgrammingError) as e:
            if 'is_admin' in str(e):
                logger.info("🔧 Missing is_admin column detected, fixing...")
                try:
                    # Add the missing column
                    db.session.execute(text("ALTER TABLE employee ADD COLUMN is_admin BOOLEAN DEFAULT FALSE"))
                    db.session.commit()
                    logger.info("✅ Added is_admin column")
                    
                    # Set admin privileges for admin user
                    db.session.execute(text("UPDATE employee SET is_admin = TRUE WHERE email = 'admin@workforce.com'"))
                    db.session.commit()
                    logger.info("✅ Updated admin privileges")
                    
                except Exception as fix_error:
                    logger.error(f"❌ Could not fix database: {fix_error}")
                    db.session.rollback()
            else:
                logger.error(f"❌ Database error: {e}")
        
        # Check for other potentially missing columns
        try:
            # List of columns that might be missing
            columns_to_check = [
                ("employee", "is_admin", "BOOLEAN DEFAULT FALSE"),
                ("employee", "max_hours_per_week", "INTEGER DEFAULT 48"),
                ("employee", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
                ("employee", "updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            ]
            
            for table, column, col_type in columns_to_check:
                try:
                    db.session.execute(text(f"SELECT {column} FROM {table} LIMIT 1"))
                except (OperationalError, ProgrammingError):
                    logger.info(f"🔧 Adding missing column: {table}.{column}")
                    try:
                        db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                        db.session.commit()
                        logger.info(f"✅ Added {column} column to {table}")
                    except Exception as e:
                        logger.error(f"❌ Could not add {column}: {e}")
                        db.session.rollback()
        except Exception as e:
            logger.error(f"❌ Error checking columns: {e}")

# Import and register blueprints
blueprints_to_register = [
    ('blueprints.auth', 'auth_bp', 'Auth'),
    ('blueprints.main', 'main_bp', 'Main'),
    ('blueprints.supervisor', 'supervisor_bp', 'Supervisor'),
    ('blueprints.employee_import', 'bp', 'Employee import'),
    ('blueprints.schedule_management', 'schedule_bp', 'Schedule management'),
    ('blueprints.overtime_management', 'overtime_bp', 'Overtime management'),
    ('blueprints.leave_management', 'leave_bp', 'Leave management'),
    ('blueprints.timeoff_requests', 'timeoff_bp', 'Time-off requests'),
    ('blueprints.shift_swap', 'shift_swap_bp', 'Shift swap'),
    ('blueprints.communications', 'communications_bp', 'Communications'),
    ('blueprints.maintenance', 'maintenance_bp', 'Maintenance'),
    ('blueprints.circadian', 'circadian_bp', 'Circadian'),
    ('blueprints.coverage_gaps', 'coverage_bp', 'Coverage gaps'),
]

for module_name, blueprint_name, description in blueprints_to_register:
    try:
        module = __import__(module_name, fromlist=[blueprint_name])
        blueprint = getattr(module, blueprint_name)
        app.register_blueprint(blueprint)
        logger.info(f"✅ {description} blueprint loaded")
    except ImportError as e:
        logger.warning(f"⚠️  Could not import {description} blueprint: {e}")
    except AttributeError as e:
        logger.warning(f"⚠️  {description} blueprint not found in module: {e}")

# Root route
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('main.supervisor_dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    return redirect(url_for('auth.login'))

# Health check route
@app.route('/health')
def health():
    try:
        # Test database connection
        db.session.execute(text('SELECT 1'))
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
        }), 500

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    logger.warning(f"404 error: {request.url}")
    if current_user.is_authenticated:
        # Create a simple 404 page if template doesn't exist
        return """
        <html>
        <head><title>Page Not Found</title></head>
        <body style="text-align: center; margin-top: 50px;">
            <h1>404 - Page Not Found</h1>
            <p>The page you're looking for doesn't exist.</p>
            <a href="/">Go Home</a>
        </body>
        </html>
        """, 404
    return redirect(url_for('auth.login'))

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {error}")
    db.session.rollback()
    if current_user.is_authenticated:
        # Create a simple 500 page if template doesn't exist
        return """
        <html>
        <head><title>Server Error</title></head>
        <body style="text-align: center; margin-top: 50px;">
            <h1>500 - Internal Server Error</h1>
            <p>Something went wrong. Please try again later.</p>
            <a href="/">Go Home</a>
        </body>
        </html>
        """, 500
    return redirect(url_for('auth.login'))

# Context processor for templates
@app.context_processor
def inject_now():
    return {'now': datetime.utcnow}

# Create initial admin user if doesn't exist
def create_admin_user():
    """Create default admin user if it doesn't exist"""
    with app.app_context():
        try:
            admin = Employee.query.filter_by(email='admin@workforce.com').first()
            if not admin:
                logger.info("Creating default admin user...")
                admin = Employee(
                    email='admin@workforce.com',
                    name='Admin User',
                    employee_id='ADMIN001',
                    is_supervisor=True,
                    is_admin=True,
                    is_active=True,
                    department='Administration',
                    crew='A'
                )
                admin.set_password('admin123')  # Change this password!
                db.session.add(admin)
                db.session.commit()
                logger.info("✅ Created default admin user (admin@workforce.com / admin123)")
        except Exception as e:
            logger.error(f"Could not create admin user: {e}")
            db.session.rollback()

# Run database fixes and initialization
with app.app_context():
    try:
        # First, try to create all tables
        db.create_all()
        logger.info("✅ Database tables verified/created")
        
        # Then fix any schema issues
        fix_database_schema()
        
        # Create admin user if needed
        create_admin_user()
        
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}")

# Import global to avoid circular imports
from flask import request

if __name__ == '__main__':
    # Additional startup checks
    with app.app_context():
        logger.info("=== Workforce Scheduler Starting ===")
        logger.info(f"Database: {'PostgreSQL' if 'postgresql' in str(db.engine.url) else 'SQLite'}")
        logger.info(f"Upload folder: {app.config['UPLOAD_FOLDER']}")
        
        # List registered routes
        logger.info("Registered routes:")
        for rule in app.url_map.iter_rules():
            logger.info(f"  {rule.endpoint}: {rule.rule}")
    
    # Run the app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
