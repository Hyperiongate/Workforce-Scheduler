from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, date, timedelta
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect
from models import (db, Employee, Position, Schedule, Skill, TimeOffRequest, CoverageRequest, 
                   CasualWorker, CasualAssignment, ShiftSwapRequest, ScheduleSuggestion,
                   EmployeeSkill, PositionSkill)
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///workforce.db')
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database and login manager
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return Employee.query.get(int(user_id))

# Database initialization function
def init_database():
    """Initialize database with sample data if empty"""
    # Check if we need to add sample data
    try:
        employee_count = Employee.query.count()
        if employee_count > 0:
            return  # Database already has data
    except:
        return  # Table might not exist yet
    
    # Add sample positions
    positions = [
        Position(name='Cashier', description='Handle customer transactions'),
        Position(name='Stock Clerk', description='Manage inventory and restock shelves'),
        Position(name='Supervisor', description='Oversee daily operations'),
        Position(name='Customer Service', description='Assist customers with inquiries')
    ]
    for p in positions:
        db.session.add(p)
    
    # Add sample skills
    skills = [
        Skill(name='Cash Handling', description='Ability to handle cash transactions'),
        Skill(name='Forklift Operation', description='Certified forklift operator'),
        Skill(name='Customer Service', description='Excellent customer service skills'),
        Skill(name='Inventory Management', description='Track and manage inventory')
    ]
    for s in skills:
        db.session.add(s)
    
    # Add sample employees with passwords
    employees = [
        Employee(name='John Doe', email='john@example.com', phone='555-0101', crew='Day Shift', 
                is_supervisor=False, password_hash=generate_password_hash('password123')),
        Employee(name='Jane Smith', email='jane@example.com', phone='555-0102', crew='Day Shift', 
                is_supervisor=False, password_hash=generate_password_hash('password123')),
        Employee(name='Mike Johnson', email='mike@example.com', phone='555-0103', crew='Day Shift', 
                is_supervisor=True, password_hash=generate_password_hash('admin123')),
        Employee(name='Sarah Williams', email='sarah@example.com', phone='555-0104', crew='Night Shift', 
                is_supervisor=False, password_hash=generate_password_hash('password123')),
        Employee(name='Tom Brown', email='tom@example.com', phone='555-0105', crew='Night Shift', 
                is_supervisor=False, password_hash=generate_password_hash('password123'))
    ]
    for e in employees:
        db.session.add(e)
    
    db.session.commit()
    
    # Add employee skills
    john = Employee.query.filter_by(name='John Doe').first()
    jane = Employee.query.filter_by(name='Jane Smith').first()
    cash_skill = Skill.query.filter_by(name='Cash Handling').first()
    customer_skill = Skill.query.filter_by(name='Customer Service').first()
    
    if john and cash_skill and customer_skill:
        john_skills = [
            EmployeeSkill(employee_id=john.id, skill_id=cash_skill.id, proficiency=4),
            EmployeeSkill(employee_id=john.id, skill_id=customer_skill.id, proficiency=5)
        ]
        for es in john_skills:
            db.session.add(es)
    
    if jane and cash_skill and customer_skill:
        jane_skills = [
            EmployeeSkill(employee_id=jane.id, skill_id=cash_skill.id, proficiency=3),
            EmployeeSkill(employee_id=jane.id, skill_id=customer_skill.id, proficiency=4)
        ]
        for es in jane_skills:
            db.session.add(es)
    
    # Add sample schedules for today
    cashier = Position.query.filter_by(name='Cashier').first()
    stock = Position.query.filter_by(name='Stock Clerk').first()
    supervisor = Position.query.filter_by(name='Supervisor').first()
    mike = Employee.query.filter_by(name='Mike Johnson').first()
    
    from datetime import time
    today = date.today()
    
    if john and jane and mike and cashier and stock and supervisor:
        schedules = [
            Schedule(date=today, start_time=time(9, 0), end_time=time(17, 0), 
                    employee_id=john.id, position_id=cashier.id, status='confirmed'),
            Schedule(date=today, start_time=time(9, 0), end_time=time(17, 0), 
                    employee_id=jane.id, position_id=stock.id, status='confirmed'),
            Schedule(date=today, start_time=time(8, 0), end_time=time(18, 0), 
                    employee_id=mike.id, position_id=supervisor.id, status='confirmed')
        ]
        for s in schedules:
            s.calculate_hours()
            db.session.add(s)
    
    # Add sample casual workers
    casual_workers = [
        CasualWorker(
            name='Alex Rivera',
            email='alex.r@email.com',
            phone='555-0201',
            skills='Forklift certified, Customer service',
            availability='{"weekday_morning": true, "weekends": true, "short_notice": true}',
            rating=4.8
        ),
        CasualWorker(
            name='Pat Chen',
            email='pat.chen@email.com',
            phone='555-0202',
            skills='Food handling, Cash register',
            availability='{"weekday_afternoon": true, "weekday_evening": true}',
            rating=4.5
        ),
        CasualWorker(
            name='Jordan Taylor',
            email='j.taylor@email.com',
            phone='555-0203',
            skills='Heavy lifting, Warehouse experience',
            availability='{"weekends": true, "short_notice": true}',
            rating=5.0
        )
    ]
    for cw in casual_workers:
        db.session.add(cw)
    
    try:
        db.session.commit()
    except:
        db.session.rollback()

# Create tables and initialize database
with app.app_context():
    db.create_all()
    init_database()

# Migration route to update existing database
@app.route('/migrate-database')
def migrate_database():
    """Add missing columns to existing tables"""
    if not app.debug and not request.args.get('confirm') == 'yes':
        return "Add ?confirm=yes to the URL to run migration"
    
    try:
        with db.engine.connect() as conn:
            inspector = inspect(db.engine)
            
            # Check and add missing columns to Employee table
            employee_columns = [col['name'] for col in inspector.get_columns('employee')]
            
            if 'password_hash' not in employee_columns:
                conn.execute(db.text('ALTER TABLE employee ADD COLUMN password_hash VARCHAR(200)'))
                # Set default passwords for existing employees
                conn.execute(db.text("UPDATE employee SET password_hash = :hash"), 
                           {'hash': generate_password_hash('password123')})
                conn.commit()
            
            if 'overtime_eligible' not in employee_columns:
                conn.execute(db.text('ALTER TABLE employee ADD COLUMN overtime_eligible BOOLEAN DEFAULT TRUE'))
                conn.commit()
            
            if 'max_hours_per_week' not in employee_columns:
                conn.execute(db.text('ALTER TABLE employee ADD COLUMN max_hours_per_week INTEGER DEFAULT 40'))
                conn.commit()
            
            # Check and add missing columns to Schedule table
            schedule_columns = [col['name'] for col in inspector.get_columns('schedule')]
            
            if 'hours' not in schedule_columns:
                conn.execute(db.text('ALTER TABLE schedule ADD COLUMN hours FLOAT'))
                conn.commit()
            
            if 'is_overtime' not in schedule_columns:
                conn.execute(db.text('ALTER TABLE schedule ADD COLUMN is_overtime BOOLEAN DEFAULT FALSE'))
                conn.commit()
            
            # Check and add missing columns to CasualWorker table
            if 'casual_worker' in inspector.get_table_names():
                casual_columns = [col['name'] for col in inspector.get_columns('casual_worker')]
                
                if 'password_hash' not in casual_columns:
                    conn.execute(db.text('ALTER TABLE casual_worker ADD COLUMN password_hash VARCHAR(200)'))
                    conn.commit()
        
        # Create any missing tables
        db.create_all()
        
        # Initialize with sample data if needed
        init_database()
        
        return "Database migration completed successfully! <a href='/'>Go to home</a>"
        
    except Exception as e:
        return f"Migration error: {str(e)}"

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/test')
def test():
    return "Test route working! Deployment successful. <a href='/'>Go home</a>"

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        employee = Employee.query.filter_by(email=email).first()
        
        if employee and employee.password_hash and check_password_hash(employee.password_hash, password):
            login_user(employee, remember=remember)
            next_page = request.args.get('next')
            if employee.is_supervisor:
                return redirect(next_page) if next_page else redirect(url_for('dashboard'))
            else:
                return redirect(next_page) if next_page else redirect(url_for('employee_dashboard'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    if not current_user.is_supervisor:
        return redirect(url_for('employee_dashboard'))
    
    # Get open coverage requests
    coverage_requests = CoverageRequest.query.filter_by(status='open').all()
    
    # Get available casual workers
    casual_workers = CasualWorker.query.filter_by(status='available').limit(5).all()
    
    # Get today's schedules
    today = date.today()
    schedules = Schedule.query.filter_by(date=today).all()
    
    return render_template('dashboard.html', 
                         schedules=schedules,
                         coverage_requests=coverage_requests,
                         casual_workers=casual_workers)

# Employee Dashboard
@app.route('/employee-dashboard')
@login_required
def employee_dashboard():
    try:
        # Get employee's upcoming shifts
        today = date.today()
        upcoming_shifts = []
        weekly_hours = 0
        next_shift = None
        swap_requests = []
        recent_suggestions = []
        
        # Try to get upcoming shifts
        try:
            upcoming_shifts = Schedule.query.filter(
                Schedule.employee_id == current_user.id,
                Schedule.date >= today
            ).order_by(Schedule.date, Schedule.start_time).limit(10).all()
            
            # Make sure each schedule has hours calculated
            for shift in upcoming_shifts:
                if shift.hours is None:
                    shift.calculate_hours()
        except Exception as e:
            print(f"Error getting upcoming shifts: {e}")
        
        # Calculate weekly hours
        try:
            week_start = today - timedelta(days=today.weekday())
            week_end = week_start + timedelta(days=6)
            weekly_schedules = Schedule.query.filter(
                Schedule.employee_id == current_user.id,
                Schedule.date >= week_start,
                Schedule.date <= week_end
            ).all()
            
            # Calculate hours for each schedule if not already done
            for schedule in weekly_schedules:
                if schedule.hours is None:
                    schedule.calculate_hours()
            
            weekly_hours = sum(s.hours or 0 for s in weekly_schedules)
        except Exception as e:
            print(f"Error calculating weekly hours: {e}")
        
        # Get next shift
        try:
            next_shift = Schedule.query.filter(
                Schedule.employee_id == current_user.id,
                Schedule.date >= today
            ).order_by(Schedule.date, Schedule.start_time).first()
        except Exception as e:
            print(f"Error getting next shift: {e}")
        
        # Get pending swap requests
        try:
            swap_requests = ShiftSwapRequest.query.filter(
                (ShiftSwapRequest.target_employee_id == current_user.id) | 
                (ShiftSwapRequest.requester_id == current_user.id),
                ShiftSwapRequest.status == 'pending'
            ).all()
        except Exception as e:
            print(f"Error getting swap requests: {e}")
        
        # Get recent suggestions
        try:
            recent_suggestions = ScheduleSuggestion.query.filter_by(
                employee_id=current_user.id
            ).order_by(ScheduleSuggestion.created_at.desc()).limit(5).all()
        except Exception as e:
            print(f"Error getting suggestions: {e}")
        
        return render_template('employee_dashboard.html',
                             upcoming_shifts=upcoming_shifts,
                             weekly_hours=round(weekly_hours, 1),
                             next_shift=next_shift,
                             pending_swaps=len(swap_requests),
                             swap_requests=swap_requests,
                             recent_suggestions=recent_suggestions,
                             time_off_days=15,  # Placeholder
                             today=today,
                             current_date=today.strftime('%A, %B %d, %Y'),
                             current_user=current_user)
                             
    except Exception as e:
        print(f"Employee dashboard error: {str(e)}")
        flash('Error loading dashboard. Please try again.', 'error')
        return redirect(url_for('index'))

# Shift Swap Request
@app.route('/employee/request-swap', methods=['POST'])
@login_required
def request_swap():
    my_schedule_id = request.form.get('my_schedule_id')
    target_schedule_id = request.form.get('target_schedule_id')
    reason = request.form.get('reason', '')
    
    # Get schedules
    my_schedule = Schedule.query.get(my_schedule_id)
    target_schedule = Schedule.query.get(target_schedule_id)
    
    if my_schedule and target_schedule:
        swap_request = ShiftSwapRequest(
            requester_id=current_user.id,
            requester_schedule_id=my_schedule_id,
            target_employee_id=target_schedule.employee_id,
            target_schedule_id=target_schedule_id,
            reason=reason
        )
        db.session.add(swap_request)
        db.session.commit()
        
        flash('Swap request submitted successfully! Awaiting supervisor approval.', 'success')
    else:
        flash('Error submitting swap request.', 'error')
    
    return redirect(url_for('employee_dashboard'))

# Submit Suggestion
@app.route('/employee/submit-suggestion', methods=['POST'])
@login_required
def submit_suggestion():
    suggestion = ScheduleSuggestion(
        employee_id=current_user.id,
        suggestion_type=request.form.get('suggestion_type'),
        title=request.form.get('title'),
        description=request.form.get('description'),
        priority=request.form.get('priority', 'medium')
    )
    db.session.add(suggestion)
    db.session.commit()
    
    flash('Thank you for your suggestion! It will be reviewed by management.', 'success')
    return redirect(url_for('employee_dashboard'))

# Schedule Creation Page
@app.route('/schedule/create', methods=['GET', 'POST'])
@login_required
def create_schedule():
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'error')
        return redirect(url_for('employee_dashboard'))
    
    if request.method == 'POST':
        # Process schedule creation
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        shift_pattern = request.form.get('shift_pattern')
        auto_assign = request.form.get('auto_assign') == 'on'
        
        # Generate schedules based on parameters
        flash('Schedule created successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    # Get data for the form
    positions = Position.query.all()
    
    # Calculate employees near overtime
    employees = Employee.query.filter_by(is_active=True).all()
    employees_near_overtime = []
    overtime_eligible = []
    
    week_start = date.today() - timedelta(days=date.today().weekday())
    week_end = week_start + timedelta(days=6)
    
    for emp in employees:
        weekly_schedules = Schedule.query.filter(
            Schedule.employee_id == emp.id,
            Schedule.date >= week_start,
            Schedule.date <= week_end
        ).all()
        current_hours = sum(s.hours or 0 for s in weekly_schedules)
        
        emp.current_hours = round(current_hours, 1)
        
        if current_hours >= 35 and current_hours < 40:
            employees_near_overtime.append(emp)
        elif getattr(emp, 'overtime_eligible', True):
            overtime_eligible.append(emp)
    
    return render_template('schedule_input.html',
                         positions=positions,
                         employees_near_overtime=employees_near_overtime,
                         overtime_eligible=overtime_eligible)

# API endpoint for available swaps
@app.route('/api/available-swaps/<int:schedule_id>')
@login_required
def get_available_swaps(schedule_id):
    my_schedule = Schedule.query.get(schedule_id)
    if not my_schedule or my_schedule.employee_id != current_user.id:
        return jsonify({'error': 'Invalid schedule'}), 400
    
    # Find other employees' schedules that could be swapped
    # Look for schedules within 7 days of the requested shift
    date_range_start = my_schedule.date - timedelta(days=7)
    date_range_end = my_schedule.date + timedelta(days=7)
    
    potential_swaps = Schedule.query.filter(
        Schedule.employee_id != current_user.id,
        Schedule.date >= date_range_start,
        Schedule.date <= date_range_end,
        Schedule.status == 'confirmed'
    ).all()
    
    # Check skill compatibility
    available_shifts = []
    my_skills = [es.skill_id for es in current_user.skills]
    
    for swap in potential_swaps:
        employee = Employee.query.get(swap.employee_id)
        their_skills = [es.skill_id for es in employee.skills]
        
        # Check if skills match
        skills_match = any(skill in their_skills for skill in my_skills)
        
        available_shifts.append({
            'id': swap.id,
            'employee_name': employee.name,
            'date': swap.date.strftime('%m/%d/%Y'),
            'position': swap.position.name,
            'time': f"{swap.start_time.strftime('%I:%M %p')} - {swap.end_time.strftime('%I:%M %p')}",
            'skills_match': skills_match
        })
    
    return jsonify({'shifts': available_shifts})

# Casual Worker Registration
@app.route('/register-casual', methods=['GET', 'POST'])
def register_casual():
    if request.method == 'POST':
        try:
            worker = CasualWorker(
                name=request.form['name'],
                email=request.form['email'],
                phone=request.form['phone'],
                skills=request.form.get('skills', ''),
                availability=request.form.get('availability', '{}')
            )
            db.session.add(worker)
            db.session.commit()
            flash('Registration successful! We\'ll contact you when work is available.', 'success')
            return redirect(url_for('register_casual'))
        except Exception as e:
            flash('Registration failed. Email may already be registered.', 'error')
            return redirect(url_for('register_casual'))
    
    return render_template('register_casual.html')

# View all casual workers
@app.route('/casual-workers')
@login_required
def casual_workers():
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'error')
        return redirect(url_for('employee_dashboard'))
    
    workers = CasualWorker.query.all()
    return render_template('casual_workers.html', workers=workers)

# Request casual worker
@app.route('/request-casual', methods=['POST'])
@login_required
def request_casual():
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'error')
        return redirect(url_for('employee_dashboard'))
    
    try:
        # Create assignment
        assignment = CasualAssignment(
            worker_id=request.form['worker_id'],
            date=datetime.strptime(request.form['date'], '%Y-%m-%d').date(),
            start_time=datetime.strptime(request.form['start_time'], '%H:%M').time(),
            end_time=datetime.strptime(request.form['end_time'], '%H:%M').time(),
            position=request.form.get('position', 'General Labor')
        )
        db.session.add(assignment)
        
        # Update worker status
        worker = CasualWorker.query.get(request.form['worker_id'])
        if worker:
            worker.status = 'working'
            
            # In development, just print the notification
            print(f"NOTIFICATION TO {worker.name} ({worker.phone}): Work available on {assignment.date}")
        
        db.session.commit()
        flash(f'Work request sent to {worker.name}!', 'success')
    except Exception as e:
        flash('Failed to create work request.', 'error')
        print(f"Error: {e}")
    
    return redirect(url_for('dashboard'))

# Password reset route for debugging
@app.route('/reset-passwords')
def reset_passwords():
    """Reset all employee passwords to defaults - REMOVE IN PRODUCTION"""
    if not request.args.get('confirm') == 'yes':
        return "Add ?confirm=yes to reset all passwords. WARNING: This will reset ALL employee passwords!"
    
    try:
        # Reset employee passwords
        employees = Employee.query.all()
        for emp in employees:
            if emp.email == 'mike@example.com':
                emp.password_hash = generate_password_hash('admin123')
            else:
                emp.password_hash = generate_password_hash('password123')
        
        db.session.commit()
        
        # List all employees
        employee_list = "<h3>Passwords Reset! Login credentials:</h3><ul>"
        for emp in employees:
            if emp.email == 'mike@example.com':
                employee_list += f"<li>{emp.name} ({emp.email}) - Password: admin123 (Supervisor)</li>"
            else:
                employee_list += f"<li>{emp.name} ({emp.email}) - Password: password123</li>"
        employee_list += "</ul>"
        
        return employee_list + '<br><a href="/login">Go to Login</a>'
        
    except Exception as e:
        return f"Error resetting passwords: {str(e)}"

# Debug route to check employees
@app.route('/debug-employees')
def debug_employees():
    """Show all employees in database - REMOVE IN PRODUCTION"""
    try:
        employees = Employee.query.all()
        if not employees:
            return "No employees found in database! <br><a href='/'>Go home</a>"
        
        output = "<h3>Employees in Database:</h3><ul>"
        for emp in employees:
            has_password = "Yes" if emp.password_hash else "No"
            output += f"<li>{emp.name} - Email: {emp.email} - Has Password: {has_password} - Is Supervisor: {emp.is_supervisor}</li>"
        output += "</ul>"
        
        # If no passwords, offer to set them
        if not any(emp.password_hash for emp in employees):
            output += '<br><strong>No passwords set!</strong> <a href="/reset-passwords?confirm=yes">Click here to set passwords</a>'
        
        return output + '<br><a href="/login">Go to Login</a>'
        
    except Exception as e:
        return f"Error: {str(e)}"

# Development route to recreate database
@app.route('/recreate-db')
def recreate_db():
    if app.debug:  # Only works in debug mode
        db.drop_all()
        db.create_all()
        init_database()
        return "Database recreated! <a href='/'>Go home</a>"
    return "Only works in debug mode"

# API endpoint to get today's schedule
@app.route('/api/schedule/today')
def get_today_schedule():
    today = date.today()
    schedules = Schedule.query.filter_by(date=today).all()
    
    shifts = []
    for schedule in schedules:
        employee = Employee.query.get(schedule.employee_id)
        position = Position.query.get(schedule.position_id)
        
        shifts.append({
            'id': schedule.id,
            'position': position.name if position else 'Unknown',
            'time': f"{schedule.start_time.strftime('%I:%M %p')} - {schedule.end_time.strftime('%I:%M %p')}",
            'employee': employee.name if employee else 'Unassigned',
            'status': schedule.status
        })
    
    return jsonify({
        'success': True,
        'date': today.strftime('%Y-%m-%d'),
        'shifts': shifts
    })

# API endpoint to report absence
@app.route('/api/absence/report', methods=['POST'])
def report_absence():
    data = request.get_json()
    employee_name = data.get('employee', '')
    
    # Find the employee
    employee = Employee.query.filter_by(name=employee_name).first()
    if employee:
        # Find today's schedule for this employee
        today = date.today()
        schedule = Schedule.query.filter_by(
            employee_id=employee.id,
            date=today
        ).first()
        
        if schedule:
            # Update schedule status
            schedule.status = 'absent'
            
            # Create coverage request
            coverage = CoverageRequest(schedule_id=schedule.id)
            db.session.add(coverage)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Absence reported for {employee_name}. Coverage request sent to available staff.'
            })
    
    return jsonify({
        'success': False,
        'message': 'Employee not found or not scheduled today'
    })

# API endpoint to get employees
@app.route('/api/employees')
def get_employees():
    employees = Employee.query.filter_by(is_active=True).all()
    return jsonify({
        'success': True,
        'employees': [{
            'id': e.id,
            'name': e.name,
            'email': e.email,
            'crew': e.crew,
            'is_supervisor': e.is_supervisor
        } for e in employees]
    })

# API endpoint to get casual workers
@app.route('/api/casual-workers/available')
def get_available_casual_workers():
    workers = CasualWorker.query.filter_by(status='available').all()
    return jsonify({
        'success': True,
        'workers': [{
            'id': w.id,
            'name': w.name,
            'phone': w.phone,
            'skills': w.skills,
            'rating': w.rating,
            'availability': json.loads(w.availability) if w.availability else {}
        } for w in workers]
    })

# Supervisor: Review Swap Requests
@app.route('/supervisor/swap-requests')
@login_required
def review_swap_requests():
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'error')
        return redirect(url_for('employee_dashboard'))
    
    pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').all()
    return render_template('swap_requests.html', swap_requests=pending_swaps)

# Approve/Deny Swap Request
@app.route('/supervisor/swap-request/<int:request_id>/<action>', methods=['POST'])
@login_required
def handle_swap_request(request_id, action):
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'error')
        return redirect(url_for('employee_dashboard'))
    
    swap_request = ShiftSwapRequest.query.get(request_id)
    if swap_request:
        if action == 'approve':
            # Swap the schedules
            schedule1 = swap_request.requester_schedule
            schedule2 = swap_request.target_schedule
            
            # Swap employee IDs
            temp_employee = schedule1.employee_id
            schedule1.employee_id = schedule2.employee_id
            schedule2.employee_id = temp_employee
            
            swap_request.status = 'approved'
            flash('Swap request approved!', 'success')
        else:
            swap_request.status = 'denied'
            flash('Swap request denied.', 'info')
        
        swap_request.reviewed_at = datetime.utcnow()
        swap_request.reviewed_by = current_user.id
        swap_request.supervisor_notes = request.form.get('notes', '')
        
        db.session.commit()
    
    return redirect(url_for('review_swap_requests'))

# View All Suggestions
@app.route('/supervisor/suggestions')
@login_required
def view_suggestions():
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'error')
        return redirect(url_for('employee_dashboard'))
    
    suggestions = ScheduleSuggestion.query.order_by(ScheduleSuggestion.created_at.desc()).all()
    return render_template('suggestions.html', suggestions=suggestions)

# Update suggestion status
@app.route('/supervisor/suggestion/<int:suggestion_id>/update', methods=['POST'])
@login_required
def update_suggestion(suggestion_id):
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'error')
        return redirect(url_for('employee_dashboard'))
    
    suggestion = ScheduleSuggestion.query.get(suggestion_id)
    if suggestion:
        suggestion.status = request.form.get('status', 'under_review')
        suggestion.reviewer_notes = request.form.get('notes', '')
        suggestion.reviewed_at = datetime.utcnow()
        db.session.commit()
        flash('Suggestion updated!', 'success')
    
    return redirect(url_for('view_suggestions'))

# Overtime Algorithm
def calculate_overtime_eligibility(week_start, week_end):
    """
    Calculate which employees are eligible for overtime based on:
    1. Current hours worked
    2. Overtime eligibility flag
    3. Maximum hours per week setting
    """
    employees = Employee.query.filter_by(is_active=True).all()
    overtime_candidates = []
    
    for emp in employees:
        if not getattr(emp, 'overtime_eligible', True):
            continue
            
        # Calculate current week hours
        weekly_schedules = Schedule.query.filter(
            Schedule.employee_id == emp.id,
            Schedule.date >= week_start,
            Schedule.date <= week_end
        ).all()
        current_hours = sum(s.hours or 0 for s in weekly_schedules)
        
        max_hours = getattr(emp, 'max_hours_per_week', 40)
        
        # Check if employee can work more hours
        if current_hours < max_hours:
            overtime_candidates.append({
                'employee': emp,
                'current_hours': current_hours,
                'available_hours': max_hours - current_hours,
                'priority': 1 if current_hours < 40 else 2  # Prioritize those under 40 hours
            })
    
    # Sort by priority and available hours
    overtime_candidates.sort(key=lambda x: (x['priority'], -x['available_hours']))
    
    return overtime_candidates

# Schedule Generation Algorithm
def generate_schedule(start_date, end_date, position_requirements, options):
    """
    Generate schedule based on requirements and constraints
    """
    generated_schedules = []
    current_date = start_date
    
    while current_date <= end_date:
        # Skip weekends if not required
        if current_date.weekday() >= 5 and not options.get('include_weekends'):
            current_date += timedelta(days=1)
            continue
        
        for position_id, count in position_requirements.items():
            position = Position.query.get(position_id)
            if not position:
                continue
            
            # Find employees with required skills
            eligible_employees = []
            
            if options.get('skill_match'):
                # Get required skills for position
                required_skills = [ps.skill_id for ps in position.required_skills]
                
                for emp in Employee.query.filter_by(is_active=True).all():
                    emp_skills = [es.skill_id for es in emp.skills]
                    if all(skill in emp_skills for skill in required_skills):
                        eligible_employees.append(emp)
            else:
                eligible_employees = Employee.query.filter_by(is_active=True).all()
            
            # Check availability and assign
            for i in range(count):
                if i < len(eligible_employees):
                    # Create schedule entry
                    from datetime import time
                    schedule = Schedule(
                        date=current_date,
                        start_time=options.get('start_time', time(9, 0)),
                        end_time=options.get('end_time', time(17, 0)),
                        employee_id=eligible_employees[i].id,
                        position_id=position_id,
                        status='scheduled'
                    )
                    schedule.calculate_hours()
                    
                    # Check for overtime
                    if options.get('overtime_check'):
                        week_start = current_date - timedelta(days=current_date.weekday())
                        week_end = week_start + timedelta(days=6)
                        
                        weekly_hours = calculate_employee_weekly_hours(
                            eligible_employees[i].id, week_start, week_end
                        )
                        
                        if weekly_hours + schedule.hours > 40:
                            schedule.is_overtime = True
                    
                    generated_schedules.append(schedule)
        
        current_date += timedelta(days=1)
    
    return generated_schedules

def calculate_employee_weekly_hours(employee_id, week_start, week_end):
    """Calculate total hours for an employee in a given week"""
    schedules = Schedule.query.filter(
        Schedule.employee_id == employee_id,
        Schedule.date >= week_start,
        Schedule.date <= week_end
    ).all()
    return sum(s.hours or 0 for s in schedules)

if __name__ == '__main__':
    app.run(debug=True)
