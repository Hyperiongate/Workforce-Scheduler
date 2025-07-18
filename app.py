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
