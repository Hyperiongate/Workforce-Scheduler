# app_fixed.py - Complete Working Application
"""
Main application file for Workforce Scheduler
This is the FIXED version - rename to app.py after backing up the old one
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file, session
from flask_login import LoginManager, login_required, login_user, logout_user, current_user 
from flask_migrate import Migrate
from werkzeug.security import check_password_hash
import os
from datetime import datetime, timedelta, date
import random
from sqlalchemy import and_, func, text, or_, inspect
from sqlalchemy.exc import ProgrammingError, OperationalError
from sqlalchemy.pool import NullPool
import logging
import traceback

# IMPORTANT: Import db from models FIRST before anything else
from models import db

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

# Setup upload folder
if os.environ.get('RENDER'):
    app.config['UPLOAD_FOLDER'] = '/tmp/upload_files'
else:
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'upload_files')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database - SIMPLE, NO RETRY LOGIC
db.init_app(app)
migrate = Migrate(app, db)

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

# Import models AFTER db initialization
from models import (
    Employee, TimeOffRequest, ShiftSwapRequest, ScheduleSuggestion, VacationCalendar, 
    Position, Skill, OvertimeHistory, Schedule, PositionCoverage,
    OvertimeOpportunity, OvertimeResponse, CoverageGap, EmployeeSkill,
    FatigueTracking, MandatoryOvertimeLog, ShiftPattern, CoverageNotificationResponse,
    FileUpload, CircadianProfile, SleepLog, PositionMessage, MessageReadReceipt,
    MaintenanceIssue, ShiftTradePost, ShiftTradeProposal, ShiftTrade, CasualWorker,
    CoverageRequest, CoverageNotification, CrewCoverageRequirement, Availability
)

@login_manager.user_loader
def load_user(user_id):
    try:
        return Employee.query.get(int(user_id))
    except Exception as e:
        logger.error(f"Error loading user: {str(e)}")
        return None

# Database error handler
def handle_db_errors(f):
    """Decorator to handle database errors"""
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except OperationalError as e:
            logger.error(f"Database operational error: {str(e)}")
            db.session.rollback()
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
    
    return decorated_function

# Import blueprints
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
        db.session.remove()
        db.engine.dispose()
    except Exception:
        pass
    return render_template('errors/500.html', 
                         message="Database connection error. Please try again."), 500

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

# Initialize database tables on first request
@app.before_first_request
def initialize_database():
    """Initialize database if needed"""
    try:
        # Check if tables exist
        inspector = inspect(db.engine)
        if not inspector.has_table('employee'):
            logger.info("Creating database tables...")
            db.create_all()
            logger.info("Database tables created successfully")
            
            # Add vacation_calendar status column if missing
            with db.engine.connect() as conn:
                try:
                    conn.execute(text("""
                        ALTER TABLE vacation_calendar 
                        ADD COLUMN status VARCHAR(20) DEFAULT 'approved'
                    """))
                    conn.commit()
                    logger.info("Added status column to vacation_calendar")
                except Exception:
                    pass  # Column might already exist
        else:
            logger.info("Database tables already exist")
            
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")

# Run the application
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
