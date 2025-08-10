# app.py - Proper implementation following the knowledge base structure
"""
Main application file for Workforce Scheduler
Follows the proper Flask structure with SQLAlchemy 2.0 compatibility
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
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
    # SQLAlchemy 2.0 configuration for production
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
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Setup upload folder
def setup_upload_folder():
    """Setup upload folder with proper error handling"""
    if os.environ.get('RENDER'):
        upload_path = '/tmp/upload_files'
    else:
        upload_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'upload_files')
    
    try:
        os.makedirs(upload_path, exist_ok=True)
        app.config['UPLOAD_FOLDER'] = upload_path
        logger.info(f"Upload folder configured: {upload_path}")
    except Exception as e:
        logger.error(f"Failed to create upload folder: {e}")
        app.config['UPLOAD_FOLDER'] = '/tmp'
    
    return app.config['UPLOAD_FOLDER']

# Initialize upload folder
upload_folder = setup_upload_folder()

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
    except Exception as e:
        logger.error(f"Error loading user {user_id}: {e}")
        return None

# Import and register blueprints
def register_blueprints():
    """Register all blueprints with error handling"""
    blueprints = [
        ('blueprints.auth', 'auth_bp', None),
        ('blueprints.main', 'main_bp', None),
        ('blueprints.supervisor', 'supervisor_bp', None),
        ('blueprints.employee', 'employee_bp', None),
        ('blueprints.schedule_management', 'schedule_bp', '/schedule'),
        ('blueprints.time_off_management', 'time_off_bp', '/time-off'),
        ('blueprints.shift_swap', 'shift_swap_bp', '/shift-swap'),
        ('blueprints.overtime_opportunities', 'overtime_bp', '/overtime'),
        ('blueprints.employee_dashboard', 'employee_dashboard_bp', '/employee'),
        ('blueprints.fatigue_tracking', 'fatigue_bp', '/fatigue'),
        ('blueprints.holiday_management', 'holiday_bp', '/holiday'),
        ('blueprints.position_messages', 'position_messages_bp', '/position-messages'),
        ('blueprints.sleep_tracking', 'sleep_tracking_bp', '/sleep'),
        ('blueprints.maintenance_issues', 'maintenance_bp', '/maintenance'),
        ('blueprints.shift_trade_board', 'shift_trade_bp', '/shift-trade'),
        ('blueprints.casual_workers', 'casual_workers_bp', '/casual-workers'),
        ('blueprints.employee_self_service', 'self_service_bp', '/self-service'),
        ('blueprints.crew_coverage', 'crew_coverage_bp', '/crew-coverage'),
        ('blueprints.employee_import', 'employee_import_bp', None),
        ('blueprints.availability_management', 'availability_bp', '/availability'),
    ]
    
    for module_name, blueprint_name, url_prefix in blueprints:
        try:
            module = __import__(module_name, fromlist=[blueprint_name])
            blueprint = getattr(module, blueprint_name)
            if url_prefix:
                app.register_blueprint(blueprint, url_prefix=url_prefix)
            else:
                app.register_blueprint(blueprint)
            logger.info(f"✓ Registered {blueprint_name}")
        except ImportError as e:
            logger.warning(f"✗ Could not import {module_name}: {e}")
        except AttributeError as e:
            logger.warning(f"✗ Could not find {blueprint_name} in {module_name}: {e}")
        except Exception as e:
            logger.error(f"✗ Error registering {blueprint_name}: {e}")

# Register all blueprints
register_blueprints()

# Routes
@app.route('/')
def home():
    """Home page - redirect based on authentication"""
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('employee.dashboard'))
    return render_template('home.html')

@app.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    try:
        # Test database connection with SQLAlchemy 2.0 syntax
        with db.engine.connect() as conn:
            result = conn.execute(text('SELECT 1'))
            result.scalar()
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'database': 'error',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 503

@app.route('/init-db')
@login_required
def init_db():
    """Initialize database tables - supervisor only"""
    if not current_user.is_supervisor:
        flash('Only supervisors can initialize the database.', 'error')
        return redirect(url_for('home'))
    
    try:
        db.create_all()
        
        # Fix vacation_calendar status column if needed
        with db.engine.connect() as conn:
            inspector = inspect(db.engine)
            if inspector.has_table('vacation_calendar'):
                columns = [col['name'] for col in inspector.get_columns('vacation_calendar')]
                if 'status' not in columns:
                    conn.execute(text("""
                        ALTER TABLE vacation_calendar 
                        ADD COLUMN status VARCHAR(20) DEFAULT 'approved'
                    """))
                    conn.commit()
                    logger.info("Added status column to vacation_calendar")
        
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
    logger.error(f"Internal error: {error}")
    return render_template('errors/500.html'), 500

@app.errorhandler(OperationalError)
def handle_db_error(error):
    logger.error(f"Database error: {error}")
    db.session.rollback()
    return render_template('errors/500.html', 
                         message="Database connection error. Please try again."), 500

# Context processors
@app.context_processor
def inject_user_permissions():
    """Inject common variables into all templates"""
    return dict(
        is_supervisor=lambda: current_user.is_authenticated and current_user.is_supervisor,
        today=datetime.today(),
        now=datetime.now()
    )

# Utility functions
def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Database initialization function
def initialize_database():
    """Initialize database tables on first run"""
    with app.app_context():
        try:
            # Check if tables exist
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            if not tables or 'employee' not in tables:
                logger.info("Creating database tables...")
                db.create_all()
                logger.info("Database tables created")
            
            # Always check for vacation_calendar.status column
            if 'vacation_calendar' in tables:
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
            logger.error(f"Database initialization error: {e}")

# Run initialization when module loads
if __name__ == '__main__':
    # Development server
    initialize_database()
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
else:
    # Production - initialize on first request
    @app.before_first_request
    def startup():
        initialize_database()
