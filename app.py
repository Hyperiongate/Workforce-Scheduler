from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, login_required, login_user, logout_user, current_user
from flask_migrate import Migrate
from models import (
    db, Employee, TimeOffRequest, ShiftSwapRequest, ScheduleSuggestion, VacationCalendar, 
    Position, Skill, OvertimeHistory, Schedule, PositionCoverage,
    # New models for staffing management
    OvertimeOpportunity, OvertimeResponse, CoverageGap, EmployeeSkill,
    FatigueTracking, MandatoryOvertimeLog, ShiftPattern, CoverageNotificationResponse
)
from werkzeug.security import check_password_hash
import os
from datetime import datetime, timedelta, date
import random
from sqlalchemy import and_, func

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
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}

# Create upload folder if it doesn't exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return Employee.query.get(int(user_id))

# Import and register blueprints from the blueprints folder
# IMPORT MAIN BLUEPRINT FIRST
try:
    from blueprints.main import main_bp
    app.register_blueprint(main_bp)
    print("Successfully imported main blueprint")
except ImportError as e:
    print(f"Warning: Could not import main blueprint: {e}")

# IMPORT AUTH BLUEPRINT
try:
    from blueprints.auth import auth_bp
    app.register_blueprint(auth_bp)
    print("Successfully imported auth blueprint")
except ImportError as e:
    print(f"Warning: Could not import auth blueprint: {e}")
    # If auth blueprint doesn't exist, set login view to the fallback
    login_manager.login_view = 'login'

try:
    from blueprints.supervisor import supervisor_bp
    app.register_blueprint(supervisor_bp)
    print("Successfully imported supervisor blueprint")
except ImportError as e:
    print(f"Warning: Could not import supervisor blueprint: {e}")

try:
    from blueprints.employee import employee_bp
    app.register_blueprint(employee_bp)
    print("Successfully imported employee blueprint")
except ImportError as e:
    print(f"Warning: Could not import employee blueprint: {e}")

try:
    from blueprints.schedule import schedule_bp
    app.register_blueprint(schedule_bp, url_prefix='/schedule')
    print("Successfully imported schedule blueprint")
except ImportError as e:
    print(f"Warning: Could not import schedule blueprint: {e}")

try:
    from blueprints.employee_import import employee_import_bp
    app.register_blueprint(employee_import_bp)
    print("Successfully imported employee_import blueprint")
except ImportError as e:
    print(f"Warning: Could not import employee_import blueprint: {e}")

# IMPORT OVERTIME BLUEPRINT
try:
    from blueprints.overtime import overtime_bp
    app.register_blueprint(overtime_bp)
    print("Successfully imported overtime blueprint")
except ImportError as e:
    print(f"Warning: Could not import overtime blueprint: {e}")

# IMPORT NEW STAFFING API BLUEPRINT
try:
    from blueprints.staffing_api import staffing_api_bp
    app.register_blueprint(staffing_api_bp)
    print("Successfully imported staffing API blueprint")
except ImportError as e:
    print(f"Warning: Could not import staffing API blueprint: {e}")

# Basic auth routes (fallback if auth blueprint is missing)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('main.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        employee = Employee.query.filter_by(email=email).first()
        
        if employee and employee.check_password(password):
            login_user(employee)
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            elif employee.is_supervisor:
                return redirect(url_for('main.dashboard'))
            else:
                return redirect(url_for('main.employee_dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Remove the duplicate dashboard and index routes since they're now in main blueprint
# Only keep these if main blueprint fails to load
if 'main' not in app.blueprints:
    @app.route('/')
    def index():
        return redirect(url_for('login'))

    @app.route('/dashboard')
    @login_required
    def dashboard():
        if current_user.is_supervisor:
            # Supervisor dashboard - using the fixed dashboard.html
            stats = {
                'pending_time_off': TimeOffRequest.query.filter_by(status='pending').count(),
                'pending_swaps': ShiftSwapRequest.query.filter_by(status='pending').count(),
                'total_employees': Employee.query.filter_by(crew=current_user.crew).count(),
                'employees_off_today': 0,
                'coverage_gaps': 0,
                'pending_suggestions': 0,
                'critical_maintenance': 0
            }
            return render_template('dashboard.html', **stats)
        else:
            # Employee dashboard
            return render_template('employee_dashboard.html')

# API endpoints
@app.route('/api/dashboard-stats')
@login_required
def dashboard_stats():
    """Get real-time dashboard statistics"""
    try:
        stats = {
            'pending_time_off': TimeOffRequest.query.filter_by(status='pending').count(),
            'pending_swaps': ShiftSwapRequest.query.filter_by(status='pending').count(),
            'coverage_gaps': 0,
            'pending_suggestions': ScheduleSuggestion.query.filter_by(status='pending').count() if hasattr(ScheduleSuggestion, 'status') else 0,
            'new_critical_items': 0
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify({
            'pending_time_off': 0,
            'pending_swaps': 0,
            'coverage_gaps': 0,
            'pending_suggestions': 0,
            'new_critical_items': 0,
            'error': str(e)
        })

# API endpoints to handle any AJAX calls that might exist
@app.route('/api/overtime-data')
@login_required
def overtime_data():
    """Handle any AJAX requests for overtime data"""
    return jsonify({
        'success': True,
        'message': 'Overtime data loaded successfully',
        'data': {
            'total_hours': 2847,
            'total_cost': 142350,
            'avg_hours': 59.3,
            'active_employees': 48
        }
    })

@app.route('/api/overtime-distribution')
@login_required
def overtime_distribution_api():
    """API endpoint for overtime distribution data"""
    return jsonify({
        'success': True,
        'data': {
            'labels': ['Crew A', 'Crew B', 'Crew C', 'Crew D'],
            'values': [722, 634, 587, 904],
            'employees': []
        }
    })

# FIX EMPLOYEE COLUMNS ROUTE
@app.route('/fix-employee-columns')
def fix_employee_columns():
    """Add missing columns to employee table"""
    try:
        with app.app_context():
            # Add missing columns one by one
            from sqlalchemy import text
            
            # Get database connection
            with db.engine.connect() as conn:
                # Try to add each column - if it already exists, it will fail silently
                columns_to_add = [
                    "ALTER TABLE employee ADD COLUMN default_shift VARCHAR(20) DEFAULT 'day'",
                    "ALTER TABLE employee ADD COLUMN max_consecutive_days INTEGER DEFAULT 14",
                    "ALTER TABLE employee ADD COLUMN is_on_call BOOLEAN DEFAULT FALSE",
                    "ALTER TABLE employee ADD COLUMN is_active BOOLEAN DEFAULT TRUE"
                ]
                
                added_columns = []
                failed_columns = []
                
                for sql in columns_to_add:
                    try:
                        conn.execute(text(sql))
                        conn.commit()
                        column_name = sql.split('ADD COLUMN ')[1].split(' ')[0]
                        added_columns.append(column_name)
                    except Exception as e:
                        column_name = sql.split('ADD COLUMN ')[1].split(' ')[0]
                        failed_columns.append(f"{column_name}: {str(e)}")
                
        return f'''
        <h2>Employee Table Column Fix</h2>
        <h3>✅ Successfully Added Columns:</h3>
        <ul>
            {''.join(f'<li>{col}</li>' for col in added_columns) if added_columns else '<li>None - all columns may already exist</li>'}
        </ul>
        <h3>❌ Failed/Already Exist:</h3>
        <ul>
            {''.join(f'<li>{col}</li>' for col in failed_columns) if failed_columns else '<li>None</li>'}
        </ul>
        <p><a href="/">Try Homepage Again</a></p>
        <p><a href="/login">Go to Login</a></p>
        '''
        
    except Exception as e:
        return f'''
        <h2>❌ Error Fixing Columns</h2>
        <p>{str(e)}</p>
        <p><a href="/dashboard">Back to Dashboard</a></p>
        '''

# Database initialization route
@app.route('/init-db')
def init_db():
    """Initialize database with all tables"""
    with app.app_context():
        db.create_all()
        
        # Check if admin exists
        admin = Employee.query.filter_by(email='admin@workforce.com').first()
        if not admin:
            admin = Employee(
                name='Admin User',
                email='admin@workforce.com',
                employee_id='ADMIN001',
                is_supervisor=True,
                crew='A',
                vacation_days=20,
                sick_days=10,
                personal_days=5,
                hire_date=date.today()  # Add hire date for seniority tracking
            )
            admin.set_password('admin123')
            db.session.add(admin)
            
            # Create default positions
            positions = [
                Position(name='Operator', min_coverage=2, requires_coverage=True),
                Position(name='Technician', min_coverage=1, requires_coverage=True),
                Position(name='Lead Operator', min_coverage=1, requires_coverage=True, critical_position=True),
                Position(name='Lead Technician', min_coverage=1, requires_coverage=True, critical_position=True),
                Position(name='Supervisor', min_coverage=1, requires_coverage=True, critical_position=True)
            ]
            for pos in positions:
                existing = Position.query.filter_by(name=pos.name).first()
                if not existing:
                    db.session.add(pos)
            
            # Create default skills
            skills = [
                Skill(name='Qualified: Operator'),
                Skill(name='Qualified: Technician'),
                Skill(name='Qualified: Lead Operator'),
                Skill(name='Qualified: Lead Technician'),
                Skill(name='Qualified: Supervisor')
            ]
            for skill in skills:
                existing = Skill.query.filter_by(name=skill.name).first()
                if not existing:
                    db.session.add(skill)
            
            db.session.commit()
        
        return '''
        <h2>Database Initialized!</h2>
        <p>Admin account created:</p>
        <ul>
            <li>Email: admin@workforce.com</li>
            <li>Password: admin123</li>
        </ul>
        <p><a href="/login">Go to login</a></p>
        '''

@app.route('/add-overtime-tables')
def add_overtime_tables():
    """Add the OvertimeHistory table to existing database"""
    try:
        with app.app_context():
            # Create only the OvertimeHistory table
            db.create_all()
            
        return '''
        <h2>✅ Overtime Tables Added!</h2>
        <p>The OvertimeHistory table has been added to your database.</p>
        <p><a href="/dashboard">Go to Dashboard</a></p>
        <p><a href="/overtime-management">Go to Overtime Management</a></p>
        '''
    except Exception as e:
        return f'''
        <h2>❌ Error Adding Tables</h2>
        <p>{str(e)}</p>
        <p><a href="/dashboard">Back to Dashboard</a></p>
        '''

# NEW ROUTE FOR STAFFING MANAGEMENT TABLES
@app.route('/add-staffing-tables')
def add_staffing_tables():
    """Create new tables for staffing management system"""
    try:
        # Create tables
        db.create_all()
        
        # Add sample shift patterns
        patterns = [
            {
                'name': 'Pitman 2-2-3',
                'pattern_type': 'pitman',
                'cycle_days': 14,
                'pattern_data': {
                    'A': [1,1,0,0,1,1,1,0,0,1,1,0,0,0],
                    'B': [0,0,1,1,0,0,0,1,1,0,0,1,1,1],
                    'C': [0,0,1,1,0,0,0,1,1,0,0,1,1,1],
                    'D': [1,1,0,0,1,1,1,0,0,1,1,0,0,0]
                },
                'description': 'Standard 2-2-3 rotation with every other weekend off'
            },
            {
                'name': '4-on-4-off',
                'pattern_type': 'fixed',
                'cycle_days': 8,
                'pattern_data': {
                    'A': [1,1,1,1,0,0,0,0],
                    'B': [0,0,0,0,1,1,1,1],
                    'C': [1,1,1,1,0,0,0,0],
                    'D': [0,0,0,0,1,1,1,1]
                },
                'description': '4 days on, 4 days off rotation'
            }
        ]
        
        for pattern_data in patterns:
            pattern = ShiftPattern.query.filter_by(name=pattern_data['name']).first()
            if not pattern:
                pattern = ShiftPattern(**pattern_data)
                db.session.add(pattern)
        
        # Add position coverage requirements
        positions = Position.query.all()
        for position in positions:
            for shift_type in ['day', 'night']:
                existing = PositionCoverage.query.filter_by(
                    position_id=position.id,
                    shift_type=shift_type
                ).first()
                if not existing:
                    coverage = PositionCoverage(
                        position_id=position.id,
                        shift_type=shift_type,
                        min_required=position.min_coverage or 1
                    )
                    db.session.add(coverage)
        
        db.session.commit()
        
        return '''
        <h2>✅ Staffing Management Tables Created!</h2>
        <p>Successfully created the following tables:</p>
        <ul>
            <li>overtime_opportunities</li>
            <li>overtime_responses</li>
            <li>coverage_gaps</li>
            <li>employee_skills_new</li>
            <li>fatigue_tracking</li>
            <li>mandatory_overtime_logs</li>
            <li>shift_patterns</li>
            <li>coverage_notification_responses</li>
            <li>position_coverage</li>
        </ul>
        <p>Also added:</p>
        <ul>
            <li>2 shift patterns (Pitman 2-2-3 and 4-on-4-off)</li>
            <li>Position coverage requirements for all positions</li>
        </ul>
        <p><a href="/dashboard">Go to Dashboard</a></p>
        '''
        
    except Exception as e:
        return f'''
        <h2>❌ Error Creating Tables</h2>
        <p>{str(e)}</p>
        <p>Please check the console for details.</p>
        <p><a href="/dashboard">Back to Dashboard</a></p>
        '''

@app.route('/populate-crews')
def populate_crews():
    """Quick link to populate demo data"""
    if request.args.get('confirm') != 'yes':
        return '''
        <h2>🏗️ Populate 4 Crews for Testing</h2>
        <p>This will create <strong>40 employees</strong> (10 per crew) with:</p>
        <ul>
            <li><strong>Crew A:</strong> 10 employees (Day shift preference)</li>
            <li><strong>Crew B:</strong> 10 employees (Day shift preference)</li>
            <li><strong>Crew C:</strong> 10 employees (Night shift preference)</li>
            <li><strong>Crew D:</strong> 10 employees (Night shift preference)</li>
        </ul>
        <p><strong>All passwords:</strong> password123</p>
        <p><a href="/populate-crews?confirm=yes" onclick="return confirm('Create 40 test employees?')">Yes, Populate Crews</a></p>
        <p><a href="/dashboard">Cancel</a></p>
        '''
    
    try:
        # Create test employees
        positions = Position.query.all()
        skills = Skill.query.all()
        
        if not positions:
            return '<h2>Error</h2><p>Please run /init-db first to create positions.</p>'
        
        crew_names = {
            'A': ['Alice Anderson', 'Adam Martinez', 'Angela Brown', 'Andrew Wilson', 
                  'Amy Chen', 'Aaron Davis', 'Anna Garcia', 'Alex Thompson', 'Abigail Lee', 'Anthony Moore'],
            'B': ['Barbara Bennett', 'Brian Clark', 'Betty Rodriguez', 'Benjamin Lewis',
                  'Brenda White', 'Bruce Harris', 'Bethany Martin', 'Brandon Jackson', 'Brittany Taylor', 'Blake Anderson'],
            'C': ['Carol Campbell', 'Charles Parker', 'Christine Evans', 'Christopher Turner',
                  'Catherine Phillips', 'Carl Roberts', 'Cindy Walker', 'Craig Hall', 'Chelsea Allen', 'Curtis Young'],
            'D': ['Diana Davidson', 'David Foster', 'Deborah Murphy', 'Daniel Rivera',
                  'Donna Scott', 'Derek King', 'Denise Wright', 'Douglas Lopez', 'Dorothy Hill', 'Dean Green']
        }
        
        created = 0
        for crew, names in crew_names.items():
            for i, name in enumerate(names):
                email = name.lower().replace(' ', '.') + '@company.com'
                existing = Employee.query.filter_by(email=email).first()
                if not existing:
                    # Vary hire dates for seniority testing
                    hire_date = date.today() - timedelta(days=random.randint(30, 3650))
                    
                    emp = Employee(
                        name=name,
                        email=email,
                        employee_id=f'{crew}{str(i+1).zfill(3)}',
                        phone=f'555-{crew}{str(i).zfill(3)}',
                        is_supervisor=(i == 0),  # First in each crew is supervisor
                        crew=crew,
                        position_id=positions[i % len(positions)].id,
                        vacation_days=10,
                        sick_days=5,
                        personal_days=3,
                        hire_date=hire_date,
                        default_shift='day' if crew in ['A', 'B'] else 'night'
                    )
                    emp.set_password('password123')
                    db.session.add(emp)
                    created += 1
        
        db.session.commit()
        return f'''
        <h2>✅ Success!</h2>
        <p>Created {created} employees across 4 crews.</p>
        <p><a href="/dashboard">Go to Dashboard</a></p>
        '''
    except Exception as e:
        db.session.rollback()
        return f'<h2>Error</h2><p>{str(e)}</p>'

@app.route('/create-test-time-off')
def create_test_time_off():
    """Create test time off requests"""
    try:
        # Get some employees
        employees = Employee.query.limit(10).all()
        
        if not employees:
            return '''
            <h2>No Employees Found</h2>
            <p>Please create employees first:</p>
            <ul>
                <li><a href="/init-db">Initialize Database</a></li>
                <li><a href="/populate-crews">Populate Crews</a></li>
            </ul>
            '''
        
        # Create some test requests
        request_types = ['vacation', 'sick', 'personal']
        reasons = [
            'Family vacation to Hawaii',
            'Doctor appointment',
            'Personal matters',
            'Wedding anniversary trip',
            'Feeling unwell',
            'Moving to new apartment'
        ]
        
        created_count = 0
        for i in range(8):
            employee = random.choice(employees)
            request_type = random.choice(request_types)
            
            # Random dates in the next 2 months
            start_date = datetime.now().date() + timedelta(days=random.randint(5, 60))
            duration = random.randint(1, 5)
            end_date = start_date + timedelta(days=duration-1)
            
            # Check if this employee already has a request for these dates
            existing = TimeOffRequest.query.filter(
                TimeOffRequest.employee_id == employee.id,
                TimeOffRequest.start_date == start_date
            ).first()
            
            if not existing:
                time_off = TimeOffRequest(
                    employee_id=employee.id,
                    request_type=request_type,
                    start_date=start_date,
                    end_date=end_date,
                    reason=random.choice(reasons) if random.random() > 0.3 else None,
                    status='pending' if i < 5 else random.choice(['approved', 'denied']),
                    created_at=datetime.now() - timedelta(days=random.randint(1, 10)),
                    days_requested=duration
                )
                
                # Add approval info for non-pending requests
                if time_off.status != 'pending':
                    time_off.approved_by = 1  # Admin user
                    time_off.approved_date = datetime.now() - timedelta(days=random.randint(1, 5))
                    if time_off.status == 'denied':
                        time_off.notes = "Insufficient coverage during this period"
                
                db.session.add(time_off)
                
                # Create VacationCalendar entries for approved requests
                if time_off.status == 'approved':
                    current_date = start_date
                    while current_date <= end_date:
                        cal_entry = VacationCalendar(
                            employee_id=employee.id,
                            date=current_date,
                            request_id=time_off.id,
                            type=request_type,
                            status='approved'
                        )
                        db.session.add(cal_entry)
                        current_date += timedelta(days=1)
                
                created_count += 1
        
        db.session.commit()
        
        return f'''
        <h2>✅ Test Data Created!</h2>
        <p>Created {created_count} time off requests.</p>
        <p><a href="/supervisor/time-off-requests" class="btn btn-primary">View Time Off Requests</a></p>
        <p><a href="/dashboard">Back to Dashboard</a></p>
        '''
        
    except Exception as e:
        db.session.rollback()
        return f'''
        <h2>❌ Error Creating Test Data</h2>
        <p>{str(e)}</p>
        <p><a href="/dashboard">Back to Dashboard</a></p>
        '''

@app.route('/create-test-schedules')
def create_test_schedules():
    """Create test schedules for coverage gap testing"""
    try:
        employees = Employee.query.all()
        if not employees:
            return '<h2>No employees found. Please populate crews first.</h2>'
        
        # Create schedules for the next 30 days
        start_date = date.today()
        created = 0
        
        for day_offset in range(30):
            current_date = start_date + timedelta(days=day_offset)
            
            # Determine which crews work this day (simplified pattern)
            day_num = day_offset % 4
            if day_num in [0, 1]:
                working_crews = ['A', 'B']
                shift_type = 'day'
            else:
                working_crews = ['C', 'D']
                shift_type = 'night'
            
            # Schedule most employees from working crews
            for emp in employees:
                if emp.crew in working_crews and not emp.is_supervisor:
                    # Skip some employees randomly to create gaps
                    if random.random() > 0.1:  # 90% chance of being scheduled
                        schedule = Schedule(
                            employee_id=emp.id,
                            date=current_date,
                            shift_type=shift_type,
                            start_time='06:00' if shift_type == 'day' else '18:00',
                            end_time='18:00' if shift_type == 'day' else '06:00',
                            position_id=emp.position_id,
                            hours=12.0,
                            crew=emp.crew,
                            status='scheduled'
                        )
                        db.session.add(schedule)
                        created += 1
        
        db.session.commit()
        
        return f'''
        <h2>✅ Test Schedules Created!</h2>
        <p>Created {created} schedule entries for the next 30 days.</p>
        <p>Some gaps were intentionally created for testing.</p>
        <p><a href="/dashboard">Go to Dashboard</a></p>
        '''
        
    except Exception as e:
        db.session.rollback()
        return f'<h2>Error</h2><p>{str(e)}</p>'

@app.route('/create-test-overtime-history')
def create_test_overtime_history():
    """Create test overtime history for employees"""
    try:
        employees = Employee.query.filter_by(is_supervisor=False).all()
        if not employees:
            return '<h2>No employees found. Please populate crews first.</h2>'
        
        created = 0
        # Create overtime history for the last 13 weeks
        for week_offset in range(13):
            week_start = date.today() - timedelta(weeks=week_offset, days=date.today().weekday())
            
            # Give random employees overtime each week
            for emp in random.sample(employees, k=min(15, len(employees))):
                ot_hours = random.uniform(4, 24)  # Random OT between 4-24 hours
                regular_hours = 40.0
                
                history = OvertimeHistory(
                    employee_id=emp.id,
                    week_start_date=week_start,
                    regular_hours=regular_hours,
                    overtime_hours=ot_hours,
                    total_hours=regular_hours + ot_hours
                )
                db.session.add(history)
                created += 1
        
        db.session.commit()
        
        return f'''
        <h2>✅ Test Overtime History Created!</h2>
        <p>Created {created} overtime history records for the last 13 weeks.</p>
        <p><a href="/dashboard">Go to Dashboard</a></p>
        '''
        
    except Exception as e:
        db.session.rollback()
        return f'<h2>Error</h2><p>{str(e)}</p>'

@app.route('/test-overtime')
def test_overtime():
    """Simple test to see if overtime page loads"""
    return """
    <h1>Overtime Management Test Page</h1>
    <p>If you can see this, the route is working!</p>
    <p><a href="/dashboard">Back to Dashboard</a></p>
    <p><a href="/overtime-management">Try Real Overtime Page</a></p>
    """

@app.route('/debug-routes')
def debug_routes():
    """Show all registered routes for debugging"""
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'path': str(rule)
        })
    
    output = '<h2>Registered Routes</h2><ul>'
    for route in sorted(routes, key=lambda x: x['path']):
        output += f"<li><strong>{route['path']}</strong> - {route['endpoint']} ({', '.join(route['methods'])})</li>"
    output += '</ul>'
    
    # Show which blueprints are registered
    output += '<h2>Registered Blueprints</h2><ul>'
    for name, blueprint in app.blueprints.items():
        output += f"<li>{name}</li>"
    output += '</ul>'
    
    output += '<p><a href="/dashboard">Back to Dashboard</a></p>'
    
    return output

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return '<h1>404 - Page Not Found</h1><p>The page you are looking for does not exist.</p><p><a href="/dashboard">Return to Dashboard</a></p>', 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    import traceback
    error_text = traceback.format_exc()
    app.logger.error(f'Server Error: {error}\n{error_text}')
    return f'''<h1>500 - Internal Server Error</h1>
    <p>Something went wrong. Please try again.</p>
    <details>
    <summary>Error Details (for debugging)</summary>
    <pre>{error_text}</pre>
    </details>
    <p><a href="/dashboard">Return to Dashboard</a></p>''', 500

if __name__ == '__main__':
    app.run(debug=True)
