# ========================================
# FILE 2: app.py - Complete with all schema fixes
# ========================================
"""
Main application file with comprehensive database schema management
Handles all tables, not just employee table
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
    
    def fix_employee_table(self):
        """Fix employee table schema"""
        logger.info("Checking employee table...")
        
        # Define all columns that should exist
        columns = {
            'seniority_date': ("DATE", "UPDATE employee SET seniority_date = hire_date WHERE seniority_date IS NULL"),
            'username': ("VARCHAR(50)", "UPDATE employee SET username = SPLIT_PART(email, '@', 1) WHERE username IS NULL"),
            'must_change_password': ("BOOLEAN DEFAULT TRUE", None),
            'first_login': ("BOOLEAN DEFAULT TRUE", None),
            'account_active': ("BOOLEAN DEFAULT TRUE", None),
            'account_created_date': ("TIMESTAMP", "UPDATE employee SET account_created_date = CURRENT_TIMESTAMP WHERE account_created_date IS NULL"),
            'last_password_change': ("TIMESTAMP", None),
            'last_login': ("TIMESTAMP", None),
            'login_attempts': ("INTEGER DEFAULT 0", None),
            'locked_until': ("TIMESTAMP", None),
            'reset_token': ("VARCHAR(100)", None),
            'reset_token_expires': ("TIMESTAMP", None),
            'default_shift': ("VARCHAR(20) DEFAULT 'day'", None),
            'max_consecutive_days': ("INTEGER DEFAULT 14", None),
            'is_on_call': ("BOOLEAN DEFAULT FALSE", None),
            'is_active': ("BOOLEAN DEFAULT TRUE", None),
            'vacation_days': ("FLOAT DEFAULT 10.0", None),
            'sick_days': ("FLOAT DEFAULT 5.0", None),
            'personal_days': ("FLOAT DEFAULT 3.0", None),
            'shift_pattern': ("VARCHAR(50)", None),
            'employee_id': ("VARCHAR(50)", None),
            'position_id': ("INTEGER", None),
            'department': ("VARCHAR(100)", None),
            'phone': ("VARCHAR(20)", None),
            'crew': ("VARCHAR(1)", None),
            'hire_date': ("DATE", None)
        }
        
        for column_name, (column_type, after_sql) in columns.items():
            self.add_column('employee', column_name, column_type, after_sql)
        
        self.db.session.commit()
    
    def fix_shift_swap_request_table(self):
        """Fix shift_swap_request table schema"""
        logger.info("Checking shift_swap_request table...")
        
        # Check if table uses schedule_id or shift_date columns
        has_schedule_id = self.check_column_exists('shift_swap_request', 'requester_schedule_id')
        has_shift_date = self.check_column_exists('shift_swap_request', 'requester_shift_date')
        
        if not has_schedule_id and not has_shift_date:
            # Add the date-based columns as fallback
            self.add_column('shift_swap_request', 'requester_shift_date', 'DATE', None)
            self.add_column('shift_swap_request', 'requested_shift_date', 'DATE', None)
        
        # Add other potentially missing columns
        columns = {
            'requester_schedule_id': "INTEGER",
            'requested_schedule_id': "INTEGER",
            'reviewed_by_id': "INTEGER",
            'reviewed_at': "TIMESTAMP",
            'reviewer_notes': "TEXT",
            'created_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            'status': "VARCHAR(20) DEFAULT 'pending'"
        }
        
        for column_name, column_type in columns.items():
            self.add_column('shift_swap_request', column_name, column_type)
        
        self.db.session.commit()
    
    def fix_time_off_request_table(self):
        """Fix time_off_request/time_off_requests table schema"""
        logger.info("Checking time_off_request table...")
        
        # Handle potential plural table name
        table_name = 'time_off_request'
        if not self.check_table_exists('time_off_request'):
            if self.check_table_exists('time_off_requests'):
                table_name = 'time_off_requests'
                self.issues_found.append("Table is named 'time_off_requests' (plural)")
        
        # Add potentially missing columns
        columns = {
            'created_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            'approved_by': "INTEGER",
            'approved_date': "TIMESTAMP",
            'notes': "TEXT",
            'days_requested': "FLOAT"
        }
        
        for column_name, column_type in columns.items():
            self.add_column(table_name, column_name, column_type)
        
        self.db.session.commit()
    
    def fix_schedule_table(self):
        """Fix schedule table schema"""
        logger.info("Checking schedule table...")
        
        columns = {
            'is_overtime': "BOOLEAN DEFAULT FALSE",
            'overtime_reason': "VARCHAR(200)",
            'original_employee_id': "INTEGER",
            'position_id': "INTEGER",
            'hours': "FLOAT",
            'crew': "VARCHAR(1)",
            'status': "VARCHAR(20) DEFAULT 'scheduled'"
        }
        
        for column_name, column_type in columns.items():
            self.add_column('schedule', column_name, column_type)
        
        self.db.session.commit()
    
    def fix_overtime_history_table(self):
        """Fix overtime_history table schema"""
        logger.info("Checking overtime_history table...")
        
        columns = {
            'regular_hours': "FLOAT DEFAULT 40",
            'overtime_type': "VARCHAR(20)",
            'reason': "TEXT",
            'approved_by_id': "INTEGER",
            'approved_date': "TIMESTAMP",
            'week_start': "DATE",
            'created_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        }
        
        for column_name, column_type in columns.items():
            self.add_column('overtime_history', column_name, column_type)
        
        self.db.session.commit()
    
    def fix_position_message_table(self):
        """Fix position_message table schema"""
        logger.info("Checking position_message table...")
        
        columns = {
            'priority': "VARCHAR(10) DEFAULT 'normal'",
            'crew_specific': "BOOLEAN DEFAULT FALSE",
            'target_crew': "VARCHAR(1)",
            'sent_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            'expires_at': "TIMESTAMP"
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
    
    def check_table_exists(self, table_name):
        """Check if a table exists"""
        try:
            result = self.db.session.execute(text(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = '{table_name}'
                )
            """))
            return result.scalar()
        except:
            return False
    
    def create_indexes(self):
        """Create performance indexes"""
        logger.info("Creating indexes...")
        
        indexes = [
            ("idx_employee_email", "employee", "email"),
            ("idx_employee_username", "employee", "username"),
            ("idx_employee_crew", "employee", "crew"),
            ("idx_schedule_date_crew", "schedule", "date, crew"),
            ("idx_schedule_employee_date", "schedule", "employee_id, date"),
            ("idx_overtime_history_employee", "overtime_history", "employee_id"),
            ("idx_time_off_request_employee", "time_off_request", "employee_id"),
            ("idx_shift_swap_request_status", "shift_swap_request", "status")
        ]
        
        for index_name, table_name, columns in indexes:
            try:
                self.db.session.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns})"))
                self.fixes_applied.append(f"Created index {index_name}")
            except Exception as e:
                # Index might already exist
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

# Import and register blueprints
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

# Helper functions for templates
@app.context_processor
def utility_processor():
    """Make utility functions available in templates"""
    return dict(
        now=datetime.now,
        timedelta=timedelta,
        date=date,
        str=str,
        len=len
    )

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
                    "exists": len(columns) > 0,
                    "column_count": len(columns),
                    "columns": columns
                }
            except Exception as e:
                status[table] = {
                    "exists": False,
                    "error": str(e)
                }
        
        # Check for critical issues
        critical_issues = []
        
        # Employee table must have login fields
        if 'employee' in status and status['employee']['exists']:
            employee_cols = [c['name'] for c in status['employee']['columns']]
            required_cols = ['email', 'password_hash', 'seniority_date', 'username']
            missing = [col for col in required_cols if col not in employee_cols]
            if missing:
                critical_issues.append(f"Employee table missing: {', '.join(missing)}")
        
        return jsonify({
            "status": "healthy" if not critical_issues else "issues",
            "tables": status,
            "critical_issues": critical_issues,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/debug-routes')
@login_required
def debug_routes():
    """Show all registered routes (supervisor only)"""
    if not current_user.is_supervisor:
        return "Access denied", 403
    
    import urllib
    output = ["<h2>All Registered Routes</h2>", "<pre>"]
    
    rules = []
    for rule in app.url_map.iter_rules():
        options = {}
        for arg in rule.arguments:
            options[arg] = f"[{arg}]"
        
        methods = ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
        
        if rule.endpoint != 'static':
            url = urllib.parse.unquote(str(rule))
            endpoint = rule.endpoint
            rules.append((endpoint, methods, url))
    
    # Sort by endpoint name
    rules.sort(key=lambda x: x[0])
    
    # Format output
    for endpoint, methods, url in rules:
        output.append(f"{endpoint:50s} {methods:20s} {url}")
    
    output.append("</pre>")
    output.append(f"<p>Total routes: {len(rules)}</p>")
    
    return '\n'.join(output)

@app.route('/test-db')
@login_required
def test_db():
    """Test database connectivity"""
    if not current_user.is_supervisor:
        return "Access denied", 403
    
    try:
        # Test basic query
        result = db.session.execute(text("SELECT 1"))
        
        # Count tables
        table_count = db.session.execute(text("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)).scalar()
        
        # Count employees
        employee_count = Employee.query.count()
        
        return jsonify({
            "status": "ok",
            "database": "connected",
            "table_count": table_count,
            "employee_count": employee_count,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

# Populate test data endpoint
@app.route('/populate-test-data')
@login_required
def populate_test_data():
    """Populate database with test data"""
    if not current_user.is_supervisor:
        return "Access denied", 403
    
    try:
        # Check if already populated
        if Position.query.count() > 0:
            flash('Database already contains data. Clear it first if you want to repopulate.', 'warning')
            return redirect(url_for('main.dashboard'))
        
        # Create positions
        positions = [
            Position(name='Operator', department='Production', is_active=True),
            Position(name='Senior Operator', department='Production', is_active=True),
            Position(name='Lead Operator', department='Production', is_active=True),
            Position(name='Technician', department='Maintenance', is_active=True),
            Position(name='Electrician', department='Maintenance', is_active=True),
            Position(name='Mechanic', department='Maintenance', is_active=True),
            Position(name='Quality Control', department='Quality', is_active=True),
            Position(name='Material Handler', department='Warehouse', is_active=True),
            Position(name='Supervisor', department='Production', is_active=True)
        ]
        
        for pos in positions:
            db.session.add(pos)
        
        # Create skills
        skills = [
            Skill(name='Forklift Operation', description='Certified forklift operator'),
            Skill(name='Electrical Work', description='Basic electrical maintenance'),
            Skill(name='Welding', description='Certified welder'),
            Skill(name='First Aid', description='First aid certified'),
            Skill(name='Hazmat', description='Hazmat handling certified'),
            Skill(name='Quality Inspection', description='Quality control certified'),
            Skill(name='Machine Operation', description='General machine operator'),
            Skill(name='Leadership', description='Team leadership experience')
        ]
        
        for skill in skills:
            db.session.add(skill)
        
        db.session.commit()
        
        # Create some test employees
        test_employees = [
            {
                'name': 'John Supervisor A',
                'email': 'supervisor.a@company.com',
                'crew': 'A',
                'is_supervisor': True,
                'position': 'Supervisor'
            },
            {
                'name': 'Jane Supervisor B',
                'email': 'supervisor.b@company.com',
                'crew': 'B',
                'is_supervisor': True,
                'position': 'Supervisor'
            },
            {
                'name': 'Mike Supervisor C',
                'email': 'supervisor.c@company.com',
                'crew': 'C',
                'is_supervisor': True,
                'position': 'Supervisor'
            },
            {
                'name': 'Sarah Supervisor D',
                'email': 'supervisor.d@company.com',
                'crew': 'D',
                'is_supervisor': True,
                'position': 'Supervisor'
            }
        ]
        
        # Add test employees
        for emp_data in test_employees:
            position = Position.query.filter_by(name=emp_data['position']).first()
            
            employee = Employee(
                name=emp_data['name'],
                email=emp_data['email'],
                employee_id=f"EMP{random.randint(1000, 9999)}",
                crew=emp_data['crew'],
                is_supervisor=emp_data['is_supervisor'],
                position_id=position.id if position else None,
                department=position.department if position else 'Production',
                hire_date=date.today() - timedelta(days=random.randint(365, 3650)),
                is_active=True,
                vacation_days=10,
                sick_days=5,
                personal_days=3
            )
            
            # Set password
            employee.set_password('admin123')
            
            # Add some skills
            employee.skills.append(random.choice(skills))
            
            db.session.add(employee)
        
        db.session.commit()
        
        flash('Test data populated successfully!', 'success')
        return redirect(url_for('main.dashboard'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error populating test data: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

if __name__ == '__main__':
    # Only run in development
    app.run(debug=True, host='0.0.0.0', port=5000)
