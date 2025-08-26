#!/usr/bin/env python3
"""
Main application file for Workforce Scheduler
COMPLETE FILE with PITMAN SCHEDULE ROUTES
"""

from flask import Flask, render_template, redirect, url_for, flash, jsonify, request
from flask_login import LoginManager, login_required, current_user, login_user
from flask_migrate import Migrate
import os
import logging
from datetime import datetime, date, timedelta
from sqlalchemy import text, inspect
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import OperationalError, ProgrammingError
from werkzeug.security import generate_password_hash, check_password_hash

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

# Ensure upload folder exists
try:
    if os.path.exists(app.config['UPLOAD_FOLDER']):
        if not os.path.isdir(app.config['UPLOAD_FOLDER']):
            os.remove(app.config['UPLOAD_FOLDER'])
            os.makedirs(app.config['UPLOAD_FOLDER'])
    else:
        os.makedirs(app.config['UPLOAD_FOLDER'])
except Exception as e:
    logger.warning(f"Could not create upload folder: {e}")
    import tempfile
    app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

# Initialize extensions
from models import db
db.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'

# Import models after db initialization
from models import Employee, Schedule, Position, TimeOffRequest, ShiftSwapRequest, OvertimeHistory

@login_manager.user_loader
def load_user(user_id):
    return Employee.query.get(int(user_id))

# Import blueprints
try:
    from blueprints.auth import auth_bp
    from blueprints.main import main_bp
    from blueprints.employee import employee_bp
    from blueprints.supervisor import supervisor_bp
    from blueprints.schedule import schedule_bp
    from blueprints.employee_import import employee_import_bp
    from blueprints.reset_database import reset_db_bp
    
    logger.info("All blueprints imported successfully")
except ImportError as e:
    logger.error(f"Error importing blueprints: {e}")
    # Create minimal fallback routes if blueprints fail
    
# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(employee_bp)
app.register_blueprint(supervisor_bp)
app.register_blueprint(schedule_bp)
app.register_blueprint(employee_import_bp)
app.register_blueprint(reset_db_bp)

# Import Pitman schedule functionality
try:
    from utils.real_pitman_schedule import RealPitmanSchedule, generate_pitman_for_production
    PITMAN_AVAILABLE = True
    logger.info("Pitman schedule system loaded successfully")
except ImportError as e:
    PITMAN_AVAILABLE = False
    logger.warning(f"Pitman schedule system not available: {e}")

# ==========================================
# PITMAN SCHEDULE ROUTES
# ==========================================

@app.route('/schedule/pitman/preview')
@login_required
def pitman_preview():
    """Preview Pitman pattern before generating"""
    try:
        if not current_user.is_supervisor:
            flash('Access denied. Supervisors only.', 'danger')
            return redirect(url_for('main.employee_dashboard'))
        
        if not PITMAN_AVAILABLE:
            flash('Pitman schedule system is not available', 'error')
            return redirect(url_for('supervisor.dashboard'))
        
        pitman = RealPitmanSchedule()
        
        # Get current crew status
        crew_employees = pitman._get_crew_employees()
        validation = pitman._validate_crews(crew_employees)
        
        # Generate pattern preview
        preview_text = pitman.preview_schedule_pattern(28)
        
        return render_template('pitman_preview.html', 
                             crew_employees=crew_employees,
                             validation=validation,
                             preview_text=preview_text,
                             datetime=datetime,
                             timedelta=timedelta)
                             
    except Exception as e:
        logger.error(f"Error loading Pitman preview: {e}")
        flash('Error loading Pitman schedule preview', 'error')
        return redirect(url_for('supervisor.dashboard'))

@app.route('/schedule/pitman/generate', methods=['POST'])
@login_required  
def generate_pitman():
    """Generate actual Pitman schedules"""
    try:
        if not current_user.is_supervisor:
            return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
        
        if not PITMAN_AVAILABLE:
            return jsonify({'success': False, 'error': 'Pitman schedule system is not available'}), 503
        
        # Get parameters from form
        start_date = request.form.get('start_date')
        weeks = int(request.form.get('weeks', 4))
        variation = request.form.get('variation', 'fixed')
        replace_existing = request.form.get('replace_existing') == 'on'
        
        logger.info(f"Generating Pitman schedule: {start_date}, {weeks} weeks, {variation}, replace={replace_existing}")
        
        # Validate start date
        if not start_date:
            return jsonify({'success': False, 'error': 'Start date is required'})
        
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format'})
        
        # Check if start date is in the past (allow today)
        if start_date_obj < date.today():
            return jsonify({'success': False, 'error': 'Start date cannot be in the past'})
        
        # Validate weeks
        if weeks < 2 or weeks > 52:
            return jsonify({'success': False, 'error': 'Number of weeks must be between 2 and 52'})
        
        # Generate schedules
        results = generate_pitman_for_production(
            start_date_str=start_date,
            weeks=weeks,
            variation=variation,
            supervisor_id=current_user.id
        )
        
        # Check validation
        if not results['validation']['valid']:
            return jsonify({
                'success': False, 
                'error': 'Schedule validation failed',
                'issues': results['validation']['issues']
            })
        
        # Check for warnings
        if results['validation']['warnings']:
            logger.warning(f"Schedule warnings: {results['validation']['warnings']}")
        
        # Save to database
        pitman = RealPitmanSchedule()
        save_results = pitman.commit_schedules_to_database(
            results['schedules'], 
            replace_existing=replace_existing
        )
        
        if save_results['success']:
            logger.info(f"Successfully generated {save_results['schedules_saved']} Pitman schedules")
            
            return jsonify({
                'success': True,
                'schedules_created': save_results['schedules_saved'],
                'statistics': results['statistics'],
                'date_range': save_results['date_range'],
                'validation': results['validation'],
                'pattern_info': results['pattern_info']
            })
        else:
            logger.error(f"Failed to save schedules: {save_results['error']}")
            return jsonify({'success': False, 'error': f"Failed to save schedules: {save_results['error']}"})
            
    except ValueError as e:
        logger.error(f"Validation error in Pitman generation: {e}")
        return jsonify({'success': False, 'error': str(e)})
    except Exception as e:
        logger.error(f"Unexpected error generating Pitman schedule: {e}")
        return jsonify({'success': False, 'error': f"Unexpected error: {str(e)}"})

@app.route('/schedule/pitman/test')
@login_required
def test_pitman():
    """Test route to check Pitman setup"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    if not PITMAN_AVAILABLE:
        return jsonify({'error': 'Pitman schedule system not available'}), 503
    
    try:
        pitman = RealPitmanSchedule()
        
        # Get crew info
        crew_employees = pitman._get_crew_employees()
        validation = pitman._validate_crews(crew_employees)
        
        # Generate a small preview
        test_start = date.today() + timedelta(days=7)
        test_end = test_start + timedelta(days=13)  # 2 weeks
        
        test_results = pitman.generate_pitman_schedule(
            start_date=test_start,
            end_date=test_end,
            variation='fixed',
            created_by_id=current_user.id
        )
        
        return jsonify({
            'crew_employees': {k: len(v) for k, v in crew_employees.items()},
            'validation': validation,
            'test_schedules_count': len(test_results['schedules']),
            'test_statistics': test_results['statistics'],
            'pattern_preview': pitman.preview_schedule_pattern(14)
        })
        
    except Exception as e:
        logger.error(f"Error in Pitman test: {e}")
        return jsonify({'error': str(e)})

@app.route('/schedule/view')
@login_required
def view_schedule():
    """View generated schedules"""
    try:
        if not current_user.is_supervisor:
            # Redirect regular employees to their personal schedule
            return redirect(url_for('employee.my_schedule'))
        
        # Get date range from query params
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not start_date:
            # Default to current week
            today = date.today()
            days_to_monday = today.weekday()
            start_date = today - timedelta(days=days_to_monday)
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        
        if not end_date:
            end_date = start_date + timedelta(days=13)  # 2 weeks
        else:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Get schedules in date range
        schedules = Schedule.query.filter(
            Schedule.date >= start_date,
            Schedule.date <= end_date
        ).join(Employee).order_by(Schedule.date, Employee.crew, Employee.name).all()
        
        # Group by date and crew
        schedule_grid = {}
        for schedule in schedules:
            date_key = schedule.date.strftime('%Y-%m-%d')
            if date_key not in schedule_grid:
                schedule_grid[date_key] = {'A': [], 'B': [], 'C': [], 'D': []}
            
            crew = schedule.employee.crew if schedule.employee.crew in ['A', 'B', 'C', 'D'] else 'Unassigned'
            if crew in schedule_grid[date_key]:
                schedule_grid[date_key][crew].append(schedule)
        
        # Sort date keys
        date_range = sorted(schedule_grid.keys())
        
        return render_template('schedule_view.html',
                             schedule_grid=schedule_grid,
                             start_date=start_date,
                             end_date=end_date,
                             date_range=date_range,
                             datetime=datetime,
                             timedelta=timedelta,
                             date=date)
                             
    except Exception as e:
        logger.error(f"Error viewing schedule: {e}")
        flash('Error loading schedule view', 'error')
        return redirect(url_for('supervisor.dashboard'))

@app.route('/api/crew-summary')
@login_required
def crew_summary():
    """API endpoint to get crew summary data"""
    try:
        if not current_user.is_supervisor:
            return jsonify({'error': 'Unauthorized'}), 403
        
        if not PITMAN_AVAILABLE:
            return jsonify({'error': 'Pitman schedule system not available'}), 503
        
        pitman = RealPitmanSchedule()
        crew_employees = pitman._get_crew_employees()
        validation = pitman._validate_crews(crew_employees)
        
        return jsonify({
            'crews': {k: len(v) for k, v in crew_employees.items()},
            'validation': validation,
            'total_employees': validation.get('total_employees', 0)
        })
        
    except Exception as e:
        logger.error(f"Error getting crew summary: {e}")
        return jsonify({'error': str(e)})

@app.route('/quick/pitman')
@login_required
def quick_pitman():
    """Quick access to Pitman generator from dashboard"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    return redirect(url_for('pitman_preview'))

# ==========================================
# ERROR HANDLERS
# ==========================================

@app.errorhandler(404)
def not_found_error(error):
    logger.warning(f"404 error: {request.url}")
    if request.endpoint and 'api' in request.endpoint:
        return jsonify({'error': 'Not found'}), 404
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {error}")
    db.session.rollback()
    if request.endpoint and 'api' in request.endpoint:
        return jsonify({'error': 'Internal server error'}), 500
    return render_template('500.html'), 500

# ==========================================
# UTILITY FUNCTIONS
# ==========================================

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# ==========================================
# CONTEXT PROCESSORS
# ==========================================

@app.context_processor
def inject_user_permissions():
    """Inject user permissions into all templates"""
    return dict(
        is_supervisor=lambda: current_user.is_authenticated and current_user.is_supervisor,
        show_pitman_nav=current_user.is_authenticated and current_user.is_supervisor and PITMAN_AVAILABLE
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

# ==========================================
# HEALTH CHECK
# ==========================================

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
            'pitman_available': PITMAN_AVAILABLE,
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 503

# ==========================================
# DATABASE INITIALIZATION
# ==========================================

print("Starting database schema check...")
with app.app_context():
    try:
        # First ensure all tables exist
        db.create_all()
        print("✓ Database tables verified/created")
        
        # Then run the column fixes if available
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
            
    except Exception as e:
        print(f"⚠️  Could not run database fixes: {e}")
        print("The app will continue but some features may not work correctly")

# ==========================================
# RUN APPLICATION
# ==========================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
