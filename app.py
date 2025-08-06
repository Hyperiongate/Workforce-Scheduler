# app.py - COMPLETE FILE WITH FIX
"""
Main application file with comprehensive database schema management
Fixes all table schema issues including shift_swap_request column naming
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, login_required, login_user, logout_user, current_user 
from flask_migrate import Migrate, stamp
from models import (
    db, Employee, TimeOffRequest, ShiftSwapRequest, ScheduleSuggestion, VacationCalendar, 
    Position, Skill, OvertimeHistory, Schedule, PositionCoverage,
    # New models for staffing management
    OvertimeOpportunity, OvertimeResponse, CoverageGap, EmployeeSkill,
    FatigueTracking, MandatoryOvertimeLog, ShiftPattern, CoverageNotificationResponse,
    FileUpload  # Added FileUpload model
)
from werkzeug.security import check_password_hash
import os
from datetime import datetime, timedelta, date
import random
from sqlalchemy import and_, func, text
from sqlalchemy.exc import ProgrammingError, OperationalError
import logging

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
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workforce.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# FIXED UPLOAD FOLDER CONFIGURATION
app.config['UPLOAD_FOLDER'] = 'upload_files'
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Handle the upload folder creation properly
upload_folder = app.config['UPLOAD_FOLDER']

# Get absolute path
if not os.path.isabs(upload_folder):
    upload_folder = os.path.join(app.root_path, upload_folder)

# Create upload folder if it doesn't exist
try:
    os.makedirs(upload_folder, exist_ok=True)
except Exception as e:
    logger.warning(f"Could not create upload folder: {e}")

# Initialize database
db.init_app(app)
migrate = Migrate(app, db)

# COMPREHENSIVE DATABASE SCHEMA FIXES
class DatabaseSchemaManager:
    """Manages all database schema fixes"""
    
    def __init__(self, app, db):
        self.app = app
        self.db = db
        self.fixes_applied = []
        self.issues_found = []
    
    def run_all_fixes(self):
        """Run all schema fixes"""
        with self.app.app_context():
            try:
                logger.info("🔧 Starting comprehensive database schema check...")
                
                # Create all tables first
                self.db.create_all()
                logger.info("✅ Base tables created/verified")
                
                # Fix each table
                self.fix_employee_table()
                self.fix_shift_swap_request_table()
                self.fix_time_off_request_table()
                self.fix_schedule_table()
                self.fix_overtime_history_table()
                self.fix_position_message_table()
                self.fix_maintenance_issue_table()
                self.fix_file_upload_table()
                self.fix_all_other_tables()
                
                # Create indexes
                self.create_indexes()
                
                # Report results
                logger.info("="*60)
                logger.info("📊 SCHEMA CHECK COMPLETE")
                logger.info("="*60)
                
                if self.fixes_applied:
                    logger.info(f"✅ Fixes Applied ({len(self.fixes_applied)}):")
                    for fix in self.fixes_applied:
                        logger.info(f"  - {fix}")
                
                if self.issues_found:
                    logger.info(f"⚠️  Issues Found ({len(self.issues_found)}):")
                    for issue in self.issues_found:
                        logger.info(f"  - {issue}")
                else:
                    logger.info("✅ No issues found - database schema is correct!")
                
                logger.info("="*60)
                
                return True
                
            except Exception as e:
                logger.error(f"❌ Error during schema check: {e}")
                return False
    
    def check_column_exists(self, table_name, column_name):
        """Check if a column exists in a table"""
        try:
            result = self.db.session.execute(text(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = '{table_name}' 
                AND column_name = '{column_name}'
            """))
            return result.rowcount > 0
        except:
            return False
    
    def add_column(self, table_name, column_name, column_type, after_sql=None):
        """Safely add a column to a table"""
        try:
            if not self.check_column_exists(table_name, column_name):
                self.db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
                self.fixes_applied.append(f"Added {table_name}.{column_name}")
                
                if after_sql:
                    self.db.session.execute(text(after_sql))
                    self.fixes_applied.append(f"Updated {table_name}.{column_name} values")
                
                return True
        except Exception as e:
            self.issues_found.append(f"Could not add {table_name}.{column_name}: {str(e)}")
            return False
    
    def check_table_exists(self, table_name):
        """Check if a table exists"""
        try:
            result = self.db.session.execute(text(f"""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name = '{table_name}'
            """))
            return result.rowcount > 0
        except:
            return False
    
    def fix_employee_table(self):
        """Fix employee table schema"""
        logger.info("Checking employee table...")
        
        columns = {
            'username': 'VARCHAR(50)',
            'must_change_password': "BOOLEAN DEFAULT FALSE",
            'first_login': "BOOLEAN DEFAULT TRUE",
            'last_password_change': "TIMESTAMP",
            'phone': "VARCHAR(20)",
            'emergency_contact': "VARCHAR(100)",
            'emergency_phone': "VARCHAR(20)",
            'skills': "TEXT",
            'is_active': "BOOLEAN DEFAULT TRUE"
        }
        
        for column_name, column_type in columns.items():
            self.add_column('employee', column_name, column_type)
        
        self.db.session.commit()
    
    def fix_shift_swap_request_table(self):
        """Fix shift_swap_request table schema"""
        logger.info("Checking shift_swap_request table...")
        
        columns = {
            'supervisor_comments': 'TEXT',
            'approved_by_id': 'INTEGER',
            'approved_at': 'TIMESTAMP',
            'notification_sent': "BOOLEAN DEFAULT FALSE"
        }
        
        for column_name, column_type in columns.items():
            self.add_column('shift_swap_request', column_name, column_type)
        
        self.db.session.commit()
    
    def fix_time_off_request_table(self):
        """Fix time_off_request table schema"""
        logger.info("Checking time_off_request table...")
        
        columns = {
            'request_type': "VARCHAR(20) DEFAULT 'vacation'",
            'approved_by_id': 'INTEGER',
            'approved_at': 'TIMESTAMP',
            'coverage_notes': 'TEXT',
            'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
        }
        
        for column_name, column_type in columns.items():
            self.add_column('time_off_request', column_name, column_type)
        
        self.db.session.commit()
    
    def fix_schedule_table(self):
        """Fix schedule table schema"""
        logger.info("Checking schedule table...")
        
        if self.check_table_exists('schedule'):
            columns = {
                'original_employee_id': 'INTEGER',
                'is_overtime': 'BOOLEAN DEFAULT FALSE',
                'is_cross_crew': 'BOOLEAN DEFAULT FALSE',
                'notes': 'TEXT'
            }
            
            for column_name, column_type in columns.items():
                self.add_column('schedule', column_name, column_type)
            
            self.db.session.commit()
    
    def fix_overtime_history_table(self):
        """Fix overtime_history table schema"""
        logger.info("Checking overtime_history table...")
        
        columns = {
            'voluntary_ot': 'FLOAT DEFAULT 0',
            'mandatory_ot': 'FLOAT DEFAULT 0',
            'refused_ot': 'FLOAT DEFAULT 0',
            'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
        }
        
        for column_name, column_type in columns.items():
            self.add_column('overtime_history', column_name, column_type)
        
        self.db.session.commit()
    
    def fix_position_message_table(self):
        """Fix position_message table schema"""
        logger.info("Checking position_message table...")
        
        columns = {
            'priority': "VARCHAR(10) DEFAULT 'normal'",
            'expires_at': 'TIMESTAMP',
            'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
        }
        
        for column_name, column_type in columns.items():
            self.add_column('position_message', column_name, column_type)
        
        self.db.session.commit()
    
    def fix_maintenance_issue_table(self):
        """Fix maintenance_issue table schema"""
        logger.info("Checking maintenance_issue table...")
        
        columns = {
            'priority': "VARCHAR(10) DEFAULT 'normal'",
            'status': "VARCHAR(20) DEFAULT 'new'",
            'created_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            'resolved_at': "TIMESTAMP",
            'resolved_by_id': "INTEGER",
            'resolution_notes': "TEXT",
            'equipment_id': "INTEGER",
            'category': "VARCHAR(50) DEFAULT 'general'"
        }
        
        for column_name, column_type in columns.items():
            self.add_column('maintenance_issue', column_name, column_type)
        
        self.db.session.commit()

    def fix_file_upload_table(self):
        """Create or fix file_upload table"""
        logger.info("Checking file_upload table...")
        
        if not self.check_table_exists('file_upload'):
            try:
                self.db.session.execute(text("""
                    CREATE TABLE file_upload (
                        id INTEGER PRIMARY KEY,
                        filename VARCHAR(255) NOT NULL,
                        upload_type VARCHAR(50) NOT NULL,
                        uploaded_by_id INTEGER NOT NULL,
                        upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        status VARCHAR(20) DEFAULT 'completed',
                        records_processed INTEGER DEFAULT 0,
                        records_failed INTEGER DEFAULT 0,
                        error_details TEXT,
                        file_path VARCHAR(500),
                        FOREIGN KEY (uploaded_by_id) REFERENCES employee(id)
                    )
                """))
                self.db.session.commit()
                self.fixes_applied.append("Created file_upload table")
            except Exception as e:
                self.issues_found.append(f"Could not create file_upload table: {str(e)}")
    
    def fix_all_other_tables(self):
        """Fix any other tables that might have issues"""
        logger.info("Checking other tables...")
        
        # ShiftTradePost
        if self.check_table_exists('shift_trade_post'):
            columns = {
                'status': "VARCHAR(20) DEFAULT 'open'",
                'created_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                'preferred_dates': "TEXT",
                'requirements': "TEXT"
            }
            for column_name, column_type in columns.items():
                self.add_column('shift_trade_post', column_name, column_type)
        
        # ShiftTradeProposal
        if self.check_table_exists('shift_trade_proposal'):
            columns = {
                'status': "VARCHAR(20) DEFAULT 'pending'",
                'created_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                'responded_at': "TIMESTAMP",
                'message': "TEXT"
            }
            for column_name, column_type in columns.items():
                self.add_column('shift_trade_proposal', column_name, column_type)
        
        # OvertimeOpportunity
        if self.check_table_exists('overtime_opportunity'):
            columns = {
                'status': "VARCHAR(20) DEFAULT 'open'",
                'created_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                'filled_at': "TIMESTAMP",
                'filled_by_id': "INTEGER"
            }
            for column_name, column_type in columns.items():
                self.add_column('overtime_opportunity', column_name, column_type)
        
        self.db.session.commit()
    
    def create_indexes(self):
        """Create performance indexes"""
        logger.info("Creating/verifying indexes...")
        
        indexes = [
            ("idx_employee_email", "employee", "email"),
            ("idx_employee_username", "employee", "username"),
            ("idx_schedule_date", "schedule", "date"),
            ("idx_schedule_employee", "schedule", "employee_id"),
            ("idx_overtime_history_employee", "overtime_history", "employee_id"),
            ("idx_overtime_history_week", "overtime_history", "week_starting"),
            ("idx_shift_swap_request_status", "shift_swap_request", "status"),
            ("idx_time_off_request_status", "time_off_request", "status"),
            ("idx_file_upload_date", "file_upload", "upload_date")
        ]
        
        for index_name, table_name, columns in indexes:
            try:
                self.db.session.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns})"))
                self.fixes_applied.append(f"Created index {index_name}")
            except Exception as e:
                # Index might already exist or table might not exist
                pass
        
        self.db.session.commit()

# Initialize schema manager
schema_manager = DatabaseSchemaManager(app, db)

# Run fixes on startup
with app.app_context():
    if not os.environ.get('FLASK_MIGRATE'):
        try:
            schema_manager.run_all_fixes()
        except Exception as e:
            logger.warning(f"Schema fix failed: {e}")

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return Employee.query.get(int(user_id))

# CRITICAL FIX: Define context processor BEFORE importing blueprints
@app.context_processor
def utility_processor():
    """Make utility functions available in templates"""
    return dict(
        now=datetime.now,
        timedelta=timedelta,
        date=date,
        str=str,
        len=len,
        int=int,
        float=float,
        enumerate=enumerate,
        zip=zip,
        range=range
    )

# NOW import and register blueprints (AFTER context processor)
from blueprints.auth import auth_bp
from blueprints.main import main_bp

app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)

# Import other blueprints with error handling
try:
    from blueprints.schedule import schedule_bp
    app.register_blueprint(schedule_bp)
    logger.info("✅ Schedule blueprint loaded")
except ImportError as e:
    logger.warning(f"⚠️  Could not import schedule blueprint: {e}")

try:
    from blueprints.supervisor import supervisor_bp
    app.register_blueprint(supervisor_bp)
    logger.info("✅ Supervisor blueprint loaded")
except ImportError as e:
    logger.warning(f"⚠️  Could not import supervisor blueprint: {e}")

try:
    from blueprints.employee import employee_bp
    app.register_blueprint(employee_bp)
    logger.info("✅ Employee blueprint loaded")
except ImportError as e:
    logger.warning(f"⚠️  Could not import employee blueprint: {e}")

try:
    from blueprints.employee_import import employee_import_bp
    app.register_blueprint(employee_import_bp)
    logger.info("✅ Employee import blueprint loaded")
except ImportError as e:
    logger.warning(f"⚠️  Could not import employee_import blueprint: {e}")

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    logger.error(f"Internal error: {error}")
    return render_template('500.html'), 500

# Routes
@app.route('/ping')
def ping():
    """Health check endpoint"""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

@app.route('/init-db')
@login_required
def init_db():
    """Initialize database with tables"""
    if not current_user.is_supervisor:
        flash('Only supervisors can initialize the database.', 'error')
        return redirect(url_for('main.index'))
    
    try:
        db.create_all()
        schema_manager.run_all_fixes()
        flash('Database tables created and schemas fixed successfully!', 'success')
    except Exception as e:
        flash(f'Error creating database tables: {str(e)}', 'error')
    
    return redirect(url_for('main.index'))

@app.route('/fix-schema')
@login_required
def fix_schema():
    """Manually trigger schema fix"""
    if not current_user.is_supervisor:
        return "Access denied", 403
    
    try:
        success = schema_manager.run_all_fixes()
        return jsonify({
            "status": "success" if success else "partial",
            "message": "Database schemas fixed",
            "fixes_applied": schema_manager.fixes_applied,
            "issues_found": schema_manager.issues_found
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/schema-status')
@login_required
def schema_status():
    """Check current database schema status"""
    if not current_user.is_supervisor:
        return "Access denied", 403
    
    try:
        status = {}
        
        # Check key tables
        tables_to_check = [
            'employee', 'shift_swap_request', 'time_off_request', 
            'schedule', 'overtime_history', 'position_message',
            'maintenance_issue', 'shift_trade_post'
        ]
        
        for table in tables_to_check:
            try:
                result = db.session.execute(text(f"""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns 
                    WHERE table_name = '{table}'
                    ORDER BY ordinal_position
                """))
                
                columns = []
                for row in result:
                    columns.append({
                        "name": row[0],
                        "type": row[1],
                        "nullable": row[2],
                        "default": row[3]
                    })
                
                status[table] = {
                    "exists": True,
                    "columns": columns,
                    "column_count": len(columns)
                }
            except Exception as e:
                status[table] = {
                    "exists": False,
                    "error": str(e)
                }
        
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/populate-sample-data')
@login_required
def populate_sample_data():
    """Populate database with sample data for testing"""
    if not current_user.is_supervisor:
        return "Access denied", 403
    
    try:
        # Create positions if they don't exist
        positions = ['Operator', 'Supervisor', 'Technician', 'Lead Operator', 'Maintenance']
        for pos_name in positions:
            if not Position.query.filter_by(name=pos_name).first():
                position = Position(name=pos_name)
                db.session.add(position)
        
        # Create skills if they don't exist
        skills = ['Forklift', 'Safety', 'First Aid', 'Leadership', 'Welding', 'Electrical']
        for skill_name in skills:
            if not Skill.query.filter_by(name=skill_name).first():
                skill = Skill(name=skill_name)
                db.session.add(skill)
        
        db.session.commit()
        
        flash('Sample data populated successfully!', 'success')
        return redirect(url_for('main.dashboard'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error populating data: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

@app.route('/debug-routes')
@login_required
def debug_routes():
    """Show all registered routes - debug only"""
    if not current_user.is_supervisor:
        return "Access denied", 403
    
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'path': str(rule)
        })
    
    return jsonify(sorted(routes, key=lambda x: x['path']))

@app.route('/test-context')
@login_required
def test_context():
    """Test endpoint to verify context processor is working"""
    return jsonify({
        "now_available": 'now' in app.jinja_env.globals,
        "datetime_available": 'datetime' in app.jinja_env.globals,
        "context_keys": list(app.jinja_env.globals.keys())
    })

# Create default admin if none exists
def create_default_admin():
    """Create default admin user if none exists"""
    with app.app_context():
        try:
            admin = Employee.query.filter_by(is_supervisor=True).first()
            if not admin:
                admin = Employee(
                    email='admin@example.com',
                    first_name='Admin',
                    last_name='User',
                    name='Admin User',
                    is_supervisor=True,
                    crew='A',
                    department='Management'
                )
                admin.set_password('admin123')
                db.session.add(admin)
                db.session.commit()
                logger.info("✅ Default admin created: admin@example.com / admin123")
            else:
                logger.info(f"✅ Admin exists: {admin.email}")
        except Exception as e:
            logger.error(f"Error creating default admin: {e}")
            db.session.rollback()

# Main execution
if __name__ == '__main__':
    # Development mode
    with app.app_context():
        try:
            db.create_all()
            create_default_admin()
        except Exception as e:
            logger.error(f"Startup error: {e}")
    
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('FLASK_ENV') == 'development'
    )
else:
    # Production mode (gunicorn)
    with app.app_context():
        try:
            # Ensure tables exist
            db.create_all()
            create_default_admin()
            logger.info("✅ Application started in production mode")
        except Exception as e:
            logger.error(f"Production startup error: {e}")
