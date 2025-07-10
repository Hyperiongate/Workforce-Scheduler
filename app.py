from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, date, timedelta
from flask_sqlalchemy import SQLAlchemy
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

# Create tables
with app.app_context():
    db.create_all()
    
    # Add some sample data if database is empty
    if Employee.query.count() == 0:
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
        
        john_skills = [
            EmployeeSkill(employee_id=john.id, skill_id=cash_skill.id, proficiency=4),
            EmployeeSkill(employee_id=john.id, skill_id=customer_skill.id, proficiency=5)
        ]
        jane_skills = [
            EmployeeSkill(employee_id=jane.id, skill_id=cash_skill.id, proficiency=3),
            EmployeeSkill(employee_id=jane.id, skill_id=customer_skill.id, proficiency=4)
        ]
        for es in john_skills + jane_skills:
            db.session.add(es)
        
        # Add sample schedules for today
        cashier = Position.query.filter_by(name='Cashier').first()
        stock = Position.query.filter_by(name='Stock Clerk').first()
        supervisor = Position.query.filter_by(name='Supervisor').first()
        
        mike = Employee.query.filter_by(name='Mike Johnson').first()
        
        from datetime import time
        today = date.today()
        
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
        
        db.session.commit()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        employee = Employee.query.filter_by(email=email).first()
        
        if employee and check_password_hash(employee.password_hash, password):
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
@app.route('/employee/dashboard')
@login_required
def employee_dashboard():
    # Get employee's upcoming shifts
    today = date.today()
    upcoming_shifts = Schedule.query.filter(
        Schedule.employee_id == current_user.id,
        Schedule.date >= today
    ).order_by(Schedule.date, Schedule.start_time).limit(10).all()
    
    # Calculate weekly hours
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    weekly_schedules = Schedule.query.filter(
        Schedule.employee_id == current_user.id,
        Schedule.date >= week_start,
        Schedule.date <= week_end
    ).all()
    weekly_hours = sum(s.hours or 0 for s in weekly_schedules)
    
    # Get next shift
    next_shift = Schedule.query.filter(
        Schedule.employee_id == current_user.id,
        Schedule.date >= today
    ).order_by(Schedule.date, Schedule.start_time).first()
    
    # Get pending swap requests
    swap_requests = ShiftSwapRequest.query.filter(
        (ShiftSwapRequest.target_employee_id == current_user.id) | 
        (ShiftSwapRequest.requester_id == current_user.id),
        ShiftSwapRequest.status == 'pending'
    ).all()
    
    # Get recent suggestions
    recent_suggestions = ScheduleSuggestion.query.filter_by(
        employee_id=current_user.id
    ).order_by(ScheduleSuggestion.created_at.desc()).limit(5).all()
    
    return render_template('employee_dashboard.html',
                         upcoming_shifts=upcoming_shifts,
                         weekly_hours=round(weekly_hours, 1),
                         next_shift=next_shift,
                         pending_swaps=len(swap_requests),
                         swap_requests=swap_requests,
                         recent_suggestions=recent_suggestions,
                         time_off_days=15,  # Placeholder
                         today=today,
                         current_date=today.strftime('%A, %B %d, %Y'))

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
        elif emp.overtime_eligible:
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
            return redirect(url_
