from flask import Flask, render_template, request
from flask_login import LoginManager
from models import db, Employee
import os

# Import blueprints
from blueprints.auth import auth_bp
from blueprints.main import main_bp
from blueprints.schedule import schedule_bp
from blueprints.supervisor import supervisor_bp
from blueprints.employee import employee_bp

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

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return Employee.query.get(int(user_id))

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(schedule_bp)
app.register_blueprint(supervisor_bp)
app.register_blueprint(employee_bp)

# Database initialization routes
@app.route('/init-db')
def init_db():
    """Initialize database with all tables"""
    with app.app_context():
        db.create_all()
        
        # Check if admin exists
        admin = Employee.query.filter_by(email='admin@workforce.com').first()
        if not admin:
            from models import Position, Skill
            
            admin = Employee(
                name='Admin User',
                email='admin@workforce.com',
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
                Position(name='Nurse', department='Healthcare', min_coverage=2),
                Position(name='Security Officer', department='Security', min_coverage=1),
                Position(name='Technician', department='Operations', min_coverage=3),
                Position(name='Customer Service', department='Support', min_coverage=2)
            ]
            for pos in positions:
                db.session.add(pos)
            
            # Create default skills
            skills = [
                Skill(name='CPR Certified', category='Medical', requires_certification=True),
                Skill(name='First Aid', category='Medical', requires_certification=True),
                Skill(name='Security Clearance', category='Security', requires_certification=True),
                Skill(name='Emergency Response', category='General'),
                Skill(name='Equipment Operation', category='Technical')
            ]
            for skill in skills:
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

@app.route('/fix-database-emergency')
def fix_database():
    """Emergency database fix - remove this after running once"""
    try:
        from sqlalchemy import text
        
        results = []
        results.append("<h2>🔧 Database Fix Results</h2>")
        
        # Check current column names
        check_query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'time_off_request'
        """)
        
        try:
            current_columns = db.session.execute(check_query).fetchall()
            column_names = [col[0] for col in current_columns]
            results.append(f"<p><strong>Current columns:</strong> {', '.join(column_names)}</p>")
        except:
            results.append("<p>Could not check current columns</p>")
        
        # List of SQL commands to fix the table
        fixes = [
            # Try to rename columns first
            ("ALTER TABLE time_off_request RENAME COLUMN submitted_date TO created_at", "Rename submitted_date to created_at"),
            ("ALTER TABLE time_off_request RENAME COLUMN reviewed_by_id TO approved_by", "Rename reviewed_by_id to approved_by"),
            ("ALTER TABLE time_off_request RENAME COLUMN reviewed_date TO approved_date", "Rename reviewed_date to approved_date"),
            ("ALTER TABLE time_off_request RENAME COLUMN reviewer_notes TO notes", "Rename reviewer_notes to notes"),
        ]
        
        # Try to add columns if they don't exist
        adds = [
            ("ALTER TABLE time_off_request ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "Add created_at column"),
            ("ALTER TABLE time_off_request ADD COLUMN approved_by INTEGER", "Add approved_by column"),
            ("ALTER TABLE time_off_request ADD COLUMN approved_date TIMESTAMP", "Add approved_date column"),
            ("ALTER TABLE time_off_request ADD COLUMN notes TEXT", "Add notes column"),
        ]
        
        results.append("<h3>Attempting column renames:</h3><ul>")
        
        # Try renaming first
        for fix_sql, description in fixes:
            try:
                db.session.execute(text(fix_sql))
                db.session.commit()
                results.append(f"<li>✅ Success: {description}</li>")
            except Exception as e:
                db.session.rollback()
                error_msg = str(e).split('\n')[0]  # Get first line of error
                results.append(f"<li>❌ Failed: {description}<br><small>{error_msg}</small></li>")
        
        results.append("</ul><h3>Attempting to add missing columns:</h3><ul>")
        
        # Then try adding
        for add_sql, description in adds:
            try:
                db.session.execute(text(add_sql))
                db.session.commit()
                results.append(f"<li>✅ Success: {description}</li>")
            except Exception as e:
                db.session.rollback()
                error_msg = str(e).split('\n')[0]  # Get first line of error
                results.append(f"<li>❌ Failed: {description}<br><small>{error_msg}</small></li>")
        
        results.append("</ul>")
        
        # Check final column names
        try:
            final_columns = db.session.execute(check_query).fetchall()
            column_names = [col[0] for col in final_columns]
            results.append(f"<p><strong>Final columns:</strong> {', '.join(column_names)}</p>")
        except:
            pass
        
        results.append('<hr><p><a href="/dashboard" class="btn btn-primary">Go to Dashboard</a></p>')
        results.append('<p><small>Note: This fix route should be removed after successful repair.</small></p>')
        
        return "".join(results)
        
    except Exception as e:
        return f"""
        <h2>❌ Database Fix Error</h2>
        <p>An error occurred while trying to fix the database:</p>
        <pre>{str(e)}</pre>
        <p><a href="/dashboard">Try Dashboard Anyway</a></p>
        """

@app.route('/add-overtime-tables')
def add_overtime_tables():
    """Add the new overtime and skill tracking tables"""
    if request.args.get('confirm') != 'yes':
        return '''
        <h2>Add Overtime and Skill Tracking Tables</h2>
        <p>This will add the following new tables to your database:</p>
        <ul>
            <li><strong>OvertimeHistory</strong> - Track weekly overtime hours for each employee</li>
            <li><strong>SkillRequirement</strong> - Define skill requirements for shifts</li>
            <li><strong>EmployeeSkill</strong> - Track employee skill certifications</li>
            <li><strong>FileUpload</strong> - Track uploaded Excel files</li>
        </ul>
        <p><a href="/add-overtime-tables?confirm=yes" class="btn btn-primary">Click here to add tables</a></p>
        '''
    
    try:
        db.create_all()
        return '''
        <h2>✅ Success!</h2>
        <p>Overtime and skill tracking tables have been added to the database.</p>
        <p>You can now:</p>
        <ul>
            <li>Upload Excel files with overtime data</li>
            <li>Track 13-week overtime history</li>
            <li>Manage employee skill certifications</li>
            <li>Define skill requirements for different shifts</li>
        </ul>
        <p><a href="/dashboard">Return to Dashboard</a></p>
        '''
    except Exception as e:
        return f'<h2>❌ Error</h2><p>Failed to add tables: {str(e)}</p>'

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
        from models import Position, Skill
        positions = Position.query.all()
        skills = Skill.query.all()
        
        if not positions:
            return '<h2>Error</h2><p>Please run /init-db first to create positions.</p>'
        
        crew_names = {
            'A': ['Alice Anderson', 'Adam Martinez', 'Angela Brown', 'Andrew Wilson'],
            'B': ['Barbara Bennett', 'Brian Clark', 'Betty Rodriguez', 'Benjamin Lewis'],
            'C': ['Carol Campbell', 'Charles Parker', 'Christine Evans', 'Christopher Turner'],
            'D': ['Diana Davidson', 'David Foster', 'Deborah Murphy', 'Daniel Rivera']
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
    from datetime import datetime, timedelta
    import random
    
    try:
        # Get some employees
        employees = Employee.query.limit(5).all()
        
        if not employees:
            return '''
            <h2>No Employees Found</h2>
            <p>Please create employees first:</p>
            <ul>
                <li><a href="/init-db">Initialize Database</a></li>
                <li><a href="/populate-crews">Populate Crews</a></li>
            </ul>
            '''
        
        # Import TimeOffRequest model
        from models import TimeOffRequest
        
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
        <p><a href="/fix-database-emergency">Try fixing database first</a></p>
        '''

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
    output += '</ul><p><a href="/dashboard">Back to Dashboard</a></p>'
    
    return output

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=True)
