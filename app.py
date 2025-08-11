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
from datetime import datetime, date, timedelta
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

# Emergency database fix function
def apply_emergency_database_fixes():
    """Apply critical database fixes for shift_swap_request table"""
    try:
        with app.app_context():
            inspector = inspect(db.engine)
            
            # Check if shift_swap_request table exists
            if inspector.has_table('shift_swap_request'):
                logger.info("Checking shift_swap_request table structure...")
                
                # Get existing columns
                existing_columns = [col['name'] for col in inspector.get_columns('shift_swap_request')]
                
                # Define required columns with their definitions
                required_columns = [
                    ('requester_id', 'INTEGER REFERENCES employee(id)'),
                    ('requested_with_id', 'INTEGER REFERENCES employee(id)'),
                    ('requester_schedule_id', 'INTEGER REFERENCES schedule(id)'),
                    ('requested_schedule_id', 'INTEGER REFERENCES schedule(id)'),
                    ('status', "VARCHAR(20) DEFAULT 'pending'"),
                    ('reason', 'TEXT'),
                    ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
                    ('reviewed_by_id', 'INTEGER REFERENCES employee(id)'),
                    ('reviewed_at', 'TIMESTAMP'),
                    ('reviewer_notes', 'TEXT')
                ]
                
                # Add missing columns
                with db.engine.connect() as conn:
                    for column_name, column_definition in required_columns:
                        if column_name not in existing_columns:
                            try:
                                conn.execute(text(f"""
                                    ALTER TABLE shift_swap_request 
                                    ADD COLUMN {column_name} {column_definition}
                                """))
                                conn.commit()
                                logger.info(f"✅ Added column shift_swap_request.{column_name}")
                            except Exception as e:
                                logger.warning(f"Could not add column {column_name}: {e}")
                                conn.rollback()
            else:
                # Create the table if it doesn't exist
                logger.info("Creating shift_swap_request table...")
                with db.engine.connect() as conn:
                    try:
                        conn.execute(text("""
                            CREATE TABLE shift_swap_request (
                                id SERIAL PRIMARY KEY,
                                requester_id INTEGER REFERENCES employee(id),
                                requested_with_id INTEGER REFERENCES employee(id),
                                requester_schedule_id INTEGER REFERENCES schedule(id),
                                requested_schedule_id INTEGER REFERENCES schedule(id),
                                status VARCHAR(20) DEFAULT 'pending',
                                reason TEXT,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                reviewed_by_id INTEGER REFERENCES employee(id),
                                reviewed_at TIMESTAMP,
                                reviewer_notes TEXT
                            )
                        """))
                        conn.commit()
                        logger.info("✅ Created shift_swap_request table")
                    except Exception as e:
                        logger.error(f"Could not create shift_swap_request table: {e}")
                        conn.rollback()
            
            logger.info("Database fixes applied successfully")
            
    except Exception as e:
        logger.error(f"Error applying database fixes: {e}")

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

try:
    from blueprints.schedule import schedule_bp
    app.register_blueprint(schedule_bp)
    logger.info("✅ Schedule blueprint loaded")
except ImportError as e:
    logger.error(f"❌ Could not import schedule blueprint: {e}")

# Routes
@app.route('/')
def home():
    """Root route - redirect based on authentication"""
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    return redirect(url_for('auth.login'))

@app.route('/health')
def health_check():
    """Health check endpoint"""
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
    """Initialize database tables"""
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

@app.route('/add-overtime-tables')
@login_required
def add_overtime_tables():
    """Add overtime management tables"""
    if not current_user.is_supervisor:
        flash('Only supervisors can modify database tables.', 'error')
        return redirect(url_for('main.index'))
    
    try:
        db.create_all()
        flash('Overtime tables added successfully!', 'success')
        return redirect(url_for('main.dashboard'))
    except Exception as e:
        flash(f'Error adding overtime tables: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

@app.route('/populate-crews')
@login_required
def populate_crews():
    """Populate database with test crew data"""
    if not current_user.is_supervisor:
        flash('Only supervisors can populate test data.', 'error')
        return redirect(url_for('main.index'))
    
    try:
        # Check if we already have data
        if Employee.query.count() > 5:
            flash('Database already contains employee data.', 'warning')
            return redirect(url_for('main.dashboard'))
        
        # Import models we need
        from models import Position, Skill
        
        # Create positions
        positions = [
            {'name': 'Operator', 'department': 'Production'},
            {'name': 'Maintenance Tech', 'department': 'Maintenance'},
            {'name': 'Lead Operator', 'department': 'Production'},
            {'name': 'Supervisor', 'department': 'Management'},
            {'name': 'Electrician', 'department': 'Maintenance'},
            {'name': 'Mechanic', 'department': 'Maintenance'}
        ]
        
        for pos_data in positions:
            position = Position.query.filter_by(name=pos_data['name']).first()
            if not position:
                position = Position(**pos_data)
                db.session.add(position)
        
        db.session.commit()
        
        # Create skills
        skills_list = [
            'Forklift Operation', 'Machine Setup', 'Quality Control',
            'Electrical Work', 'Welding', 'PLC Programming',
            'Hydraulics', 'Pneumatics', 'Safety Training'
        ]
        
        skills = []
        for skill_name in skills_list:
            skill = Skill.query.filter_by(name=skill_name).first()
            if not skill:
                skill = Skill(name=skill_name, description=f"Certified in {skill_name}")
                db.session.add(skill)
            skills.append(skill)
        
        db.session.commit()
        
        # Create employees for each crew
        crews = ['A', 'B', 'C', 'D']
        positions_list = Position.query.all()
        
        employee_names = [
            'John Smith', 'Jane Doe', 'Mike Johnson', 'Sarah Williams',
            'Tom Brown', 'Lisa Davis', 'Chris Wilson', 'Amy Martinez',
            'Robert Taylor', 'Jennifer Anderson', 'David Thomas', 'Maria Garcia',
            'James Rodriguez', 'Patricia Lee', 'Michael White', 'Linda Harris'
        ]
        
        for i, name in enumerate(employee_names):
            crew = crews[i % 4]
            position = positions_list[i % len(positions_list)]
            
            employee = Employee(
                employee_id=f'EMP{str(i+1).zfill(3)}',
                name=name,
                email=f'{name.lower().replace(" ", ".")}@company.com',
                crew=crew,
                position_id=position.id,
                is_supervisor=(i % 4 == 0),  # Every 4th employee is a supervisor
                vacation_days=10,
                sick_days=5,
                personal_days=2
            )
            employee.set_password('password123')  # Default password
            
            # Add some skills
            employee.skills.extend(skills[:3])
            
            db.session.add(employee)
        
        db.session.commit()
        flash('Test crew data populated successfully!', 'success')
        return redirect(url_for('main.dashboard'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error populating crews: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

@app.errorhandler(OperationalError)
def handle_db_error(error):
    logger.error(f"Database error: {error}")
    db.session.rollback()
    return render_template('500.html'), 500

# Context processors
@app.context_processor
def inject_user_permissions():
    return dict(
        is_supervisor=lambda: current_user.is_authenticated and current_user.is_supervisor,
        today=datetime.today(),
        now=datetime.now(),
        date=date,
        timedelta=timedelta,
        str=str,
        len=len,
        url_for=url_for
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
        
        # Apply emergency database fixes for shift_swap_request
        apply_emergency_database_fixes()
                
    except Exception as e:
        logger.error(f"Startup database error: {e}")
        # Don't prevent app from starting

# Run the application
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
