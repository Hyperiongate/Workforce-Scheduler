# app.py - Complete File with SSL Connection Fix
"""
Main application file for Workforce Scheduler
Includes database connection pooling and SSL fixes for Render deployment
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file, session
from flask_login import LoginManager, login_required, login_user, logout_user, current_user 
from flask_migrate import Migrate, stamp
from models import (
    db, Employee, TimeOffRequest, ShiftSwapRequest, ScheduleSuggestion, VacationCalendar, 
    Position, Skill, OvertimeHistory, Schedule, PositionCoverage,
    # Additional models
    OvertimeOpportunity, OvertimeResponse, CoverageGap, EmployeeSkill,
    FatigueTracking, MandatoryOvertimeLog, ShiftPattern, CoverageNotificationResponse,
    FileUpload, CircadianProfile, SleepLog, PositionMessage, MessageReadReceipt,
    MaintenanceIssue, ShiftTradePost, ShiftTradeProposal, ShiftTrade, CasualWorker,
    CoverageRequest, CoverageNotification, CrewCoverageRequirement, Availability
)
from werkzeug.security import check_password_hash
import os
import shutil
from datetime import datetime, timedelta, date
import random
from sqlalchemy import and_, func, text, or_, create_engine
from sqlalchemy.exc import ProgrammingError, OperationalError
from sqlalchemy.pool import NullPool
import logging
import traceback
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Database configuration with connection pooling and SSL fixes
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    # Add connection parameters for SSL and pooling
    # Use NullPool to prevent connection reuse issues
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,  # Verify connections before using
        'pool_recycle': 300,    # Recycle connections after 5 minutes
        'poolclass': NullPool,  # Don't maintain a pool - create new connections
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
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def setup_upload_folder(app):
    """
    Comprehensive upload folder setup with self-checking
    """
    # Use absolute path to avoid issues
    if os.environ.get('RENDER'):
        # On Render, use /tmp for temporary files
        upload_path = '/tmp/upload_files'
    else:
        # Local development
        upload_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'upload_files')
    
    app.config['UPLOAD_FOLDER'] = upload_path
    
    # Setup the folder
    if os.path.exists(upload_path):
        if os.path.isfile(upload_path):
            # If it's a file, rename it
            logger.warning(f"'{upload_path}' exists as a file, renaming...")
            os.rename(upload_path, f"{upload_path}.backup")
            os.makedirs(upload_path)
    else:
        # Create the directory
        os.makedirs(upload_path, exist_ok=True)
    
    # Verify write access
    test_file = os.path.join(upload_path, '.test_write')
    try:
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        logger.info(f"Upload folder configured successfully: {upload_path}")
    except Exception as e:
        logger.error(f"Cannot write to upload folder {upload_path}: {str(e)}")
        # Fallback to temp directory
        app.config['UPLOAD_FOLDER'] = '/tmp'
        logger.info("Using /tmp as fallback upload directory")
    
    return app.config['UPLOAD_FOLDER']

# Initialize database with retry logic
def init_db_with_retry(app, retries=3, delay=2):
    """Initialize database with retry logic for connection issues"""
    for attempt in range(retries):
        try:
            db.init_app(app)
            with app.app_context():
                # Test the connection
                db.engine.execute(text("SELECT 1"))
                logger.info("Database connection successful")
                return True
        except Exception as e:
            logger.error(f"Database connection attempt {attempt + 1} failed: {str(e)}")
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise
    return False

# Initialize extensions
init_db_with_retry(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

# Setup upload folder
upload_folder = setup_upload_folder(app)

# Database error handler decorator
def handle_db_errors(f):
    """Decorator to handle database connection errors"""
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except OperationalError as e:
            logger.error(f"Database operational error: {str(e)}")
            db.session.rollback()
            # Try to reconnect
            try:
                db.session.remove()
                db.engine.dispose()
                return f(*args, **kwargs)
            except Exception:
                flash('Database connection error. Please try again.', 'danger')
                return redirect(url_for('home'))
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            db.session.rollback()
            flash('An unexpected error occurred. Please try again.', 'danger')
            return redirect(url_for('home'))
    decorated_function.__name__ = f.__name__
    return decorated_function

@login_manager.user_loader
def load_user(user_id):
    try:
        return Employee.query.get(int(user_id))
    except Exception as e:
        logger.error(f"Error loading user: {str(e)}")
        return None

# Import blueprints (must be after db initialization)
from blueprints.auth import auth_bp
from blueprints.supervisor import supervisor_bp
from blueprints.schedule_management import schedule_bp
from blueprints.time_off_management import time_off_bp
from blueprints.shift_swap import shift_swap_bp
from blueprints.overtime_opportunities import overtime_bp
from blueprints.employee_dashboard import employee_bp
from blueprints.fatigue_tracking import fatigue_bp
from blueprints.holiday_management import holiday_bp
from blueprints.position_messages import position_messages_bp
from blueprints.sleep_tracking import sleep_tracking_bp
from blueprints.maintenance_issues import maintenance_bp
from blueprints.shift_trade_board import shift_trade_bp
from blueprints.casual_workers import casual_workers_bp
from blueprints.employee_self_service import self_service_bp
from blueprints.crew_coverage import crew_coverage_bp
from blueprints.employee_import import employee_import_bp
from blueprints.availability_management import availability_bp

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(supervisor_bp, url_prefix='/supervisor')
app.register_blueprint(schedule_bp, url_prefix='/schedule')
app.register_blueprint(time_off_bp, url_prefix='/time-off')
app.register_blueprint(shift_swap_bp, url_prefix='/shift-swap')
app.register_blueprint(overtime_bp, url_prefix='/overtime')
app.register_blueprint(employee_bp, url_prefix='/employee')
app.register_blueprint(fatigue_bp, url_prefix='/fatigue')
app.register_blueprint(holiday_bp, url_prefix='/holiday')
app.register_blueprint(position_messages_bp, url_prefix='/position-messages')
app.register_blueprint(sleep_tracking_bp, url_prefix='/sleep')
app.register_blueprint(maintenance_bp, url_prefix='/maintenance')
app.register_blueprint(shift_trade_bp, url_prefix='/shift-trade')
app.register_blueprint(casual_workers_bp, url_prefix='/casual-workers')
app.register_blueprint(self_service_bp, url_prefix='/self-service')
app.register_blueprint(crew_coverage_bp, url_prefix='/crew-coverage')
app.register_blueprint(employee_import_bp)
app.register_blueprint(availability_bp, url_prefix='/availability')

# Routes
@app.route('/')
@handle_db_errors
def home():
    if current_user.is_authenticated:
        return redirect(url_for('employee.dashboard'))
    return render_template('home.html')

@app.route('/dashboard')
@login_required
@handle_db_errors
def dashboard():
    return redirect(url_for('employee.dashboard'))

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

@app.errorhandler(OperationalError)
def handle_db_operational_error(error):
    logger.error(f"Database operational error: {str(error)}")
    db.session.rollback()
    try:
        # Try to reconnect
        db.session.remove()
        db.engine.dispose()
    except Exception:
        pass
    return render_template('errors/500.html', 
                         message="Database connection error. Please try again."), 500

# Utility function to check if uploaded file is allowed
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Initialize database schema on first run
def init_database():
    """Initialize database schema if needed"""
    with app.app_context():
        try:
            # Check if tables exist
            inspector = db.inspect(db.engine)
            if not inspector.has_table('employee'):
                logger.info("Creating database tables...")
                db.create_all()
                
                # Run any migrations
                try:
                    stamp()
                except Exception as e:
                    logger.warning(f"Migration stamp failed: {str(e)}")
                
                logger.info("Database tables created successfully")
            else:
                logger.info("Database tables already exist")
                
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}")
            raise

# Add template context processors
@app.context_processor
def inject_user_permissions():
    """Inject user permissions into all templates"""
    return dict(
        is_supervisor=lambda: current_user.is_authenticated and current_user.is_supervisor
    )

# Health check endpoint for Render
@app.route('/health')
def health_check():
    """Health check endpoint"""
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
        }), 503

# API endpoint for checking upload status
@app.route('/api/upload-status/<int:upload_id>')
@login_required
@handle_db_errors
def upload_status(upload_id):
    """Check the status of a file upload"""
    upload = FileUpload.query.get_or_404(upload_id)
    
    # Check permissions
    if not current_user.is_supervisor and upload.uploaded_by != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    return jsonify({
        'id': upload.id,
        'filename': upload.filename,
        'status': upload.status,
        'upload_type': upload.upload_type,
        'records_processed': upload.records_processed,
        'records_failed': upload.records_failed,
        'error_details': upload.error_details,
        'uploaded_at': upload.uploaded_at.isoformat() if upload.uploaded_at else None
    })

# Run the application
if __name__ == '__main__':
    # Initialize database on startup
    init_database()
    
    # Run the app
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    app.run(host='0.0.0.0', port=port, debug=debug)
