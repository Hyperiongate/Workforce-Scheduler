# app.py
"""
Main application file for Workforce Scheduler
Clean implementation compatible with Flask 2.3 and SQLAlchemy 2.0
"""

from flask import Flask, render_template, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_required, current_user
from flask_migrate import Migrate
from models import db, Employee
import os
import logging
from datetime import datetime
from sqlalchemy import text, inspect
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import OperationalError

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

# Import and register blueprints
from blueprints.auth import auth_bp
from blueprints.main import main_bp
from blueprints.supervisor import supervisor_bp
from blueprints.employee import employee_bp
from blueprints.employee_import import employee_import_bp

app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(supervisor_bp)
app.register_blueprint(employee_bp)
app.register_blueprint(employee_import_bp)

logger.info("All blueprints registered successfully")

# Routes
@app.route('/')
def home():
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('employee.dashboard'))
    return render_template('home.html')

@app.route('/health')
def health_check():
    try:
        with db.engine.connect() as conn:
            result = conn.execute(text('SELECT 1'))
            result.scalar()
        return jsonify({'status': 'healthy', 'database': 'connected'}), 200
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 503

@app.route('/init-db')
@login_required
def init_db():
    if not current_user.is_supervisor:
        flash('Only supervisors can initialize the database.', 'error')
        return redirect(url_for('home'))
    
    try:
        db.create_all()
        flash('Database tables created successfully!', 'success')
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        flash(f'Error initializing database: {str(e)}', 'error')
    
    return redirect(url_for('supervisor.dashboard'))

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

@app.errorhandler(OperationalError)
def handle_db_error(error):
    logger.error(f"Database error: {error}")
    db.session.rollback()
    return render_template('errors/500.html'), 500

# Context processors
@app.context_processor
def inject_user_permissions():
    return dict(
        is_supervisor=lambda: current_user.is_authenticated and current_user.is_supervisor,
        today=datetime.today(),
        now=datetime.now()
    )

# Initialize database on startup
with app.app_context():
    try:
        # Create tables if they don't exist
        inspector = inspect(db.engine)
        if not inspector.has_table('employee'):
            logger.info("Creating database tables...")
            db.create_all()
            logger.info("Database tables created")
        
        # Fix vacation_calendar status column if needed
        if inspector.has_table('vacation_calendar'):
            columns = [col['name'] for col in inspector.get_columns('vacation_calendar')]
            if 'status' not in columns:
                with db.engine.connect() as conn:
                    conn.execute(text("""
                        ALTER TABLE vacation_calendar 
                        ADD COLUMN status VARCHAR(20) DEFAULT 'approved'
                    """))
                    conn.commit()
                logger.info("Added status column to vacation_calendar")
                
    except Exception as e:
        logger.error(f"Startup database error: {e}")
        # Don't prevent app from starting

# Run the application
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
