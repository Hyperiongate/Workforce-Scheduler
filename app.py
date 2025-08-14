# app.py
"""
Main application file for Workforce Scheduler
Fixed version with proper startup database fixes
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

# Import your models FIRST
from models import db, Employee

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
    logger.info("🔧 Starting database schema check...")
    
    try:
        # Test if is_admin column exists
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
                
                # Set admin privileges
                db.session.execute(text("""
                    UPDATE employee 
                    SET is_admin = TRUE 
                    WHERE email = 'admin@workforce.com' 
                    OR email LIKE '%admin%'
                    OR is_supervisor = TRUE
                """))
                db.session.commit()
                logger.info("✅ Updated admin privileges")
                
            except Exception as fix_error:
                logger.error(f"❌ Could not fix database: {fix_error}")
                db.session.rollback()
        else:
            logger.error(f"❌ Database error: {e}")
        db.session.rollback()
    
    # Check for other potentially missing columns
    columns_to_check = [
        ("employee", "is_admin", "BOOLEAN DEFAULT FALSE"),
        ("employee", "max_hours_per_week", "INTEGER DEFAULT 48"),
        ("employee", "is_active", "BOOLEAN DEFAULT TRUE"),
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
                if 'already exists' not in str(e):
                    logger.error(f"❌ Could not add {column}: {e}")
                db.session.rollback()

# Create initial admin user if doesn't exist
def create_admin_user():
    """Create default admin user if it doesn't exist"""
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
                department='Administration'
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            logger.info("✅ Created default admin user (admin@workforce.com / admin123)")
        else:
            # Ensure existing admin has is_admin flag
            if not admin.is_admin:
                admin.is_admin = True
                db.session.commit()
                logger.info("✅ Updated admin user with is_admin flag")
    except Exception as e:
        logger.error(f"Could not create/update admin user: {e}")
        db.session.rollback()

# Run fixes before first request
@app.before_first_request
def initialize_database():
    """Initialize database on first request"""
    logger.info("=== Initializing Database ===")
    try:
        # Create all tables
        db.create_all()
        logger.info("✅ Database tables verified/created")
        
        # Fix schema
        fix_database_schema()
        
        # Create admin user
        create_admin_user()
        
        logger.info("=== Database initialization complete ===")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}")

# Import and register blueprints
try:
    from blueprints.auth import auth_bp
    app.register_blueprint(auth_bp)
    logger.info("✅ Auth blueprint loaded")
except ImportError as e:
    logger.error(f"❌ Could not import auth blueprint: {e}")

try:
    from blueprints.main import main_bp
    app.register_blueprint(main_bp)
    logger.info("✅ Main blueprint loaded")
except ImportError as e:
    logger.error(f"❌ Could not import main blueprint: {e}")

try:
    from blueprints.supervisor import supervisor_bp
    app.register_blueprint(supervisor_bp)
    logger.info("✅ Supervisor blueprint loaded")
except ImportError as e:
    logger.error(f"❌ Could not import supervisor blueprint: {e}")

try:
    from blueprints.employee import employee_bp
    app.register_blueprint(employee_bp)
    logger.info("✅ Employee blueprint loaded")
except ImportError as e:
    logger.error(f"❌ Could not import employee blueprint: {e}")

try:
    from blueprints.employee_import import employee_import_bp
    app.register_blueprint(employee_import_bp)
    logger.info("✅ Employee import blueprint loaded")
except ImportError as e:
    logger.error(f"❌ Could not import employee_import blueprint: {e}")

# Root route
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    return redirect(url_for('auth.login'))

# Health check route
@app.route('/health')
def health():
    try:
        # Test database connection
        db.session.execute(text('SELECT 1'))
        
        # Check if admin exists
        admin_exists = Employee.query.filter_by(email='admin@workforce.com').first() is not None
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'admin_exists': admin_exists,
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

# Database fix endpoint - manual trigger
@app.route('/fix-database')
def fix_database():
    """Manual endpoint to fix database issues"""
    if not request.args.get('confirm') == 'yes':
        return "Add ?confirm=yes to run database fixes", 400
    
    try:
        fix_database_schema()
        create_admin_user()
        return jsonify({
            'status': 'success',
            'message': 'Database fixes applied',
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    logger.warning(f"404 error: {request.url}")
    if current_user.is_authenticated:
        flash('Page not found', 'warning')
        return redirect(url_for('index'))
    return redirect(url_for('auth.login'))

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {error}")
    db.session.rollback()
    flash('An internal error occurred', 'danger')
    return redirect(url_for('index'))

# Context processor for templates
@app.context_processor
def inject_now():
    return {'now': datetime.utcnow}

if __name__ == '__main__':
    # Run the app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
