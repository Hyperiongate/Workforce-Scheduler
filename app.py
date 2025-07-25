from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, login_required, login_user, logout_user, current_user
from flask_migrate import Migrate
from models import db, Employee, TimeOffRequest, ShiftSwapRequest, ScheduleSuggestion, VacationCalendar, Position, Skill, OvertimeHistory
from werkzeug.security import check_password_hash
import os
from datetime import datetime, timedelta
import random

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
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return Employee.query.get(int(user_id))

# Import and register blueprints from the blueprints folder
try:
    from blueprints.supervisor import supervisor_bp
    app.register_blueprint(supervisor_bp)
except ImportError:
    print("Warning: Could not import supervisor blueprint")

try:
    from blueprints.employee import employee_bp
    app.register_blueprint(employee_bp)
except ImportError:
    print("Warning: Could not import employee blueprint")

try:
    from blueprints.schedule import schedule_bp
    app.register_blueprint(schedule_bp, url_prefix='/schedule')
except ImportError:
    print("Warning: Could not import schedule blueprint")

try:
    from blueprints.employee_import import employee_import_bp
    app.register_blueprint(employee_import_bp)
except ImportError:
    print("Warning: Could not import employee_import blueprint")

# Basic auth routes (since auth blueprint is missing)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        employee = Employee.query.filter_by(email=email).first()
        
        if employee and employee.check_password(password):
            login_user(employee)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Main routes
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
                personal_days=5
            )
            admin.set_password('admin123')
            db.session.add(admin)
            
            # Create default positions
            positions = [
                Position(name='Operator', min_coverage=2),
                Position(name='Technician', min_coverage=1),
                Position(name='Lead Operator', min_coverage=1),
                Position(name='Lead Technician', min_coverage=1),
                Position(name='Supervisor', min_coverage=1)
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
                        personal_days=3
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
                    type=request_type,
                    start_date=start_date,
                    end_date=end_date,
                    reason=random.choice(reasons) if random.random() > 0.3 else None,
                    status='pending' if i < 5 else random.choice(['approved', 'denied']),
                    created_at=datetime.now() - timedelta(days=random.randint(1, 10))
                )
                
                # Add approval info for non-pending requests
                if time_off.status != 'pending':
                    time_off.approved_by = 1  # Admin user
                    time_off.approved_date = datetime.now() - timedelta(days=random.randint(1, 5))
                    if time_off.status == 'denied':
                        time_off.notes = "Insufficient coverage during this period"
                
                db.session.add(time_off)
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

@app.route('/api/overtime-distribution')
@login_required
def overtime_distribution_api():
    """API endpoint for overtime distribution data"""
    try:
        # Return simple data to prevent the error
        return jsonify({
            'success': True,
            'data': {
                'labels': ['Crew A', 'Crew B', 'Crew C', 'Crew D'],
                'values': [0, 0, 0, 0],
                'employees': []
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/overtime-management')
@login_required
def overtime_management():
    """Overtime tracking and distribution view"""
    if not current_user.is_supervisor:
        flash('You must be a supervisor to access this page.', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        # Get all active employees
        employees = Employee.query.filter_by(is_active=True).order_by(Employee.crew, Employee.name).all()
        
        # Add default overtime attributes
        for emp in employees:
            emp.overtime_hours = 0
            emp.last_overtime_date = None
        
        # Basic statistics with safe defaults
        return render_template('overtime_management.html',
                             employees=employees,
                             all_employees=employees,
                             total_overtime_hours=0,
                             employees_with_overtime=0,
                             avg_overtime=0,
                             high_overtime_count=0,
                             max_overtime=10,
                             crew_overtime_data=[0, 0, 0, 0],
                             overtime_history=[])

@app.route('/api/overtime-distribution')
@login_required
def overtime_distribution_api():
    """API endpoint for overtime distribution data"""
    try:
        # Return simple data to prevent the error
        return jsonify({
            'success': True,
            'data': {
                'labels': ['Crew A', 'Crew B', 'Crew C', 'Crew D'],
                'values': [0, 0, 0, 0],
                'employees': []
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/test-overtime')
def test_overtime():
    """Simple test to see if overtime page loads"""
    return """
    <h1>Overtime Management Test Page</h1>
    <p>If you can see this, the route is working!</p>
    <p><a href="/dashboard">Back to Dashboard</a></p>
    <p><a href="/overtime-management">Try Real Overtime Page</a></p>
    """
                             
    except Exception as e:
        print(f"Error in overtime_management: {str(e)}")
        # If there's any error, return the template with empty data
        return render_template('overtime_management.html',
                             employees=[],
                             all_employees=[],
                             total_overtime_hours=0,
                             employees_with_overtime=0,
                             avg_overtime=0,
                             high_overtime_count=0,
                             max_overtime=10,
                             crew_overtime_data=[0, 0, 0, 0],
                             overtime_history=[])

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

@app.route('/overtime-management')
@login_required
def overtime_management():
    """Overtime tracking and distribution view"""
    if not current_user.is_supervisor:
        flash('You must be a supervisor to access this page.', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        # Get all active employees
        employees = Employee.query.filter_by(is_active=True).order_by(Employee.crew, Employee.name).all()
        
        # Add default overtime attributes
        for emp in employees:
            emp.overtime_hours = 0
            emp.last_overtime_date = None
        
        # Basic statistics with safe defaults
        return render_template('overtime_management.html',
                             employees=employees,
                             all_employees=employees,
                             total_overtime_hours=0,
                             employees_with_overtime=0,
                             avg_overtime=0,
                             high_overtime_count=0,
                             max_overtime=10,
                             crew_overtime_data=[0, 0, 0, 0],
                             overtime_history=[])
                             
    except Exception as e:
        print(f"Error in overtime_management: {str(e)}")
        # If there's any error, return the template with empty data
        return render_template('overtime_management.html',
                             employees=[],
                             all_employees=[],
                             total_overtime_hours=0,
                             employees_with_overtime=0,
                             avg_overtime=0,
                             high_overtime_count=0,
                             max_overtime=10,
                             crew_overtime_data=[0, 0, 0, 0],
                             overtime_history=[])

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
