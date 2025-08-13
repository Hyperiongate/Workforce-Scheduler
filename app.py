# app.py
"""
Main application file for Workforce Scheduler
This version automatically fixes the missing is_admin column issue
"""

from flask import Flask, render_template, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_required, current_user
from flask_migrate import Migrate
from models import db, Employee
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
                    
                    # Set admin privileges
                    db.session.execute(text("UPDATE employee SET is_admin = TRUE WHERE email = 'admin@workforce.com' OR is_supervisor = TRUE"))
                    db.session.commit()
                    logger.info("✅ Updated admin privileges")
                    
                except Exception as fix_error:
                    logger.error(f"❌ Could not fix database: {fix_error}")
                    db.session.rollback()
            else:
                logger.error(f"❌ Database error: {e}")
                
        # Also check for upload_history table
        try:
            db.session.execute(text("SELECT * FROM upload_history LIMIT 1"))
            logger.info("✅ upload_history table exists")
        except (OperationalError, ProgrammingError):
            logger.info("🔧 Creating upload_history table...")
            try:
                db.session.execute(text("""
                    CREATE TABLE IF NOT EXISTS upload_history (
                        id SERIAL PRIMARY KEY,
                        upload_type VARCHAR(50) NOT NULL,
                        filename VARCHAR(255) NOT NULL,
                        uploaded_by INTEGER REFERENCES employee(id),
                        upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        status VARCHAR(50) DEFAULT 'completed',
                        records_processed INTEGER DEFAULT 0,
                        records_failed INTEGER DEFAULT 0,
                        error_details TEXT,
                        details TEXT
                    )
                """))
                db.session.commit()
                logger.info("✅ Created upload_history table")
            except Exception as e:
                logger.error(f"❌ Could not create upload_history table: {e}")
                db.session.rollback()

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
    from blueprints.employee_import import bp as employee_import_bp
    app.register_blueprint(employee_import_bp)
    logger.info("✅ Employee import blueprint loaded")
except ImportError as e:
    logger.error(f"❌ Could not import employee import blueprint: {e}")

try:
    from blueprints.schedule_management import schedule_bp
    app.register_blueprint(schedule_bp)
    logger.info("✅ Schedule management blueprint loaded")
except ImportError as e:
    logger.error(f"❌ Could not import schedule management blueprint: {e}")

try:
    from blueprints.overtime_management import overtime_bp
    app.register_blueprint(overtime_bp)
    logger.info("✅ Overtime management blueprint loaded")
except ImportError as e:
    logger.error(f"❌ Could not import overtime management blueprint: {e}")

try:
    from blueprints.leave_management import leave_bp
    app.register_blueprint(leave_bp)
    logger.info("✅ Leave management blueprint loaded")
except ImportError as e:
    logger.error(f"❌ Could not import leave management blueprint: {e}")

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
    if current_user.is_authenticated:
        return render_template('errors/404.html'), 404
    return redirect(url_for('auth.login'))

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    if current_user.is_authenticated:
        return render_template('errors/500.html'), 500
    return redirect(url_for('auth.login'))

# Context processor for templates
@app.context_processor
def inject_now():
    return {'now': datetime.utcnow}

# Create default templates if they don't exist
def create_error_templates():
    """Create basic error templates if they don't exist"""
    error_dir = os.path.join(app.root_path, 'templates', 'errors')
    os.makedirs(error_dir, exist_ok=True)
    
    # 404 template
    error_404 = os.path.join(error_dir, '404.html')
    if not os.path.exists(error_404):
        with open(error_404, 'w') as f:
            f.write('''
{% extends "base.html" %}
{% block title %}Page Not Found{% endblock %}
{% block content %}
<div class="container mt-5">
    <div class="row justify-content-center">
        <div class="col-md-6 text-center">
            <h1 class="display-1">404</h1>
            <h2>Page Not Found</h2>
            <p>The page you're looking for doesn't exist.</p>
            <a href="{{ url_for('index') }}" class="btn btn-primary">Go Home</a>
        </div>
    </div>
</div>
{% endblock %}
''')
    
    # 500 template
    error_500 = os.path.join(error_dir, '500.html')
    if not os.path.exists(error_500):
        with open(error_500, 'w') as f:
            f.write('''
{% extends "base.html" %}
{% block title %}Server Error{% endblock %}
{% block content %}
<div class="container mt-5">
    <div class="row justify-content-center">
        <div class="col-md-6 text-center">
            <h1 class="display-1">500</h1>
            <h2>Internal Server Error</h2>
            <p>Something went wrong on our end. Please try again later.</p>
            <a href="{{ url_for('index') }}" class="btn btn-primary">Go Home</a>
        </div>
    </div>
</div>
{% endblock %}
''')

# Run the automatic database fix when the app starts
with app.app_context():
    fix_database_schema()
    create_error_templates()

if __name__ == '__main__':
    # Additional startup checks
    with app.app_context():
        try:
            # Create tables if they don't exist
            db.create_all()
            logger.info("✅ Database tables verified")
        except Exception as e:
            logger.error(f"❌ Database initialization error: {e}")
    
    # Run the app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
