from flask import Flask, render_template
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

# Database initialization routes (keep these in main app.py for now)
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
