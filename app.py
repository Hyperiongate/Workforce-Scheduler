from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, date, timedelta
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text, extract
from models import (db, Employee, Position, Schedule, Skill, TimeOffRequest, CoverageRequest, 
                   CasualWorker, CasualAssignment, ShiftSwapRequest, ScheduleSuggestion,
                   EmployeeSkill, PositionSkill, VacationCalendar, Availability)
import json
import calendar

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
    
    # Add sample employees with passwords and vacation days
    employees = [
        Employee(name='John Doe', email='john@example.com', phone='555-0101', crew='Day Shift', 
                is_supervisor=False, password_hash=generate_password_hash('password123'),
                vacation_days_total=14, sick_days_total=7, personal_days_total=3),
        Employee(name='Jane Smith', email='jane@example.com', phone='555-0102', crew='Day Shift', 
                is_supervisor=False, password_hash=generate_password_hash('password123'),
                vacation_days_total=14, sick_days_total=7, personal_days_total=3),
        Employee(name='Mike Johnson', email='mike@example.com', phone='555-0103', crew='Day Shift', 
                is_supervisor=True, password_hash=generate_password_hash('admin123'),
                vacation_days_total=21, sick_days_total=10, personal_days_total=5),
        Employee(name='Sarah Williams', email='sarah@example.com', phone='555-0104', crew='Night Shift', 
                is_supervisor=False, password_hash=generate_password_hash('password123'),
                vacation_days_total=14, sick_days_total=7, personal_days_total=3),
        Employee(name='Tom Brown', email='tom@example.com', phone='555-0105', crew='Night Shift', 
                is_supervisor=False, password_hash=generate_password_hash('password123'),
                vacation_days_total=14, sick_days_total=7, personal_days_total=3)
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
                conn.execute(text('ALTER TABLE employee ADD COLUMN password_hash VARCHAR(200)'))
                # Set default passwords for existing employees
                conn.execute(text("UPDATE employee SET password_hash = :hash"), 
                           {'hash': generate_password_hash('password123')})
                conn.commit()
            
            if 'overtime_eligible' not in employee_columns:
                conn.execute(text('ALTER TABLE employee ADD COLUMN overtime_eligible BOOLEAN DEFAULT TRUE'))
                conn.commit()
            
            if 'max_hours_per_week' not in employee_columns:
                conn.execute(text('ALTER TABLE employee ADD COLUMN max_hours_per_week INTEGER DEFAULT 40'))
                conn.commit()
                
            if 'overtime_hours' not in employee_columns:
                conn.execute(text('ALTER TABLE employee ADD COLUMN overtime_hours FLOAT DEFAULT 0'))
                conn.commit()
            
            # Add vacation tracking columns
            if 'vacation_days_total' not in employee_columns:
                conn.execute(text('ALTER TABLE employee ADD COLUMN vacation_days_total FLOAT DEFAULT 14'))
                conn.commit()
                
            if 'vacation_days_used' not in employee_columns:
                conn.execute(text('ALTER TABLE employee ADD COLUMN vacation_days_used FLOAT DEFAULT 0'))
                conn.commit()
                
            if 'sick_days_total' not in employee_columns:
                conn.execute(text('ALTER TABLE employee ADD COLUMN sick_days_total FLOAT DEFAULT 7'))
                conn.commit()
                
            if 'sick_days_used' not in employee_columns:
                conn.execute(text('ALTER TABLE employee ADD COLUMN sick_days_used FLOAT DEFAULT 0'))
                conn.commit()
                
            if 'personal_days_total' not in employee_columns:
                conn.execute(text('ALTER TABLE employee ADD COLUMN personal_days_total FLOAT DEFAULT 3'))
                conn.commit()
                
            if 'personal_days_used' not in employee_columns:
                conn.execute(text('ALTER TABLE employee ADD COLUMN personal_days_used FLOAT DEFAULT 0'))
                conn.commit()
            
            # Check and add missing columns to Schedule table
            schedule_columns = [col['name'] for col in inspector.get_columns('schedule')]
            
            if 'hours' not in schedule_columns:
                conn.execute(text('ALTER TABLE schedule ADD COLUMN hours FLOAT'))
                conn.commit()
            
            if 'is_overtime' not in schedule_columns:
                conn.execute(text('ALTER TABLE schedule ADD COLUMN is_overtime BOOLEAN DEFAULT FALSE'))
                conn.commit()
            
            # Check and add missing columns to TimeOffRequest table
            time_off_columns = [col['name'] for col in inspector.get_columns('time_off_request')]
            
            if 'leave_type' not in time_off_columns:
                conn.execute(text('ALTER TABLE time_off_request ADD COLUMN leave_type VARCHAR(20)'))
                conn.commit()
                
            if 'days_requested' not in time_off_columns:
                conn.execute(text('ALTER TABLE time_off_request ADD COLUMN days_requested FLOAT DEFAULT 0'))
                conn.commit()
                
            if 'approved_by' not in time_off_columns:
                conn.execute(text('ALTER TABLE time_off_request ADD COLUMN approved_by INTEGER'))
                conn.commit()
                
            if 'approved_at' not in time_off_columns:
                conn.execute(text('ALTER TABLE time_off_request ADD COLUMN approved_at TIMESTAMP'))
                conn.commit()
                
            if 'supervisor_notes' not in time_off_columns:
                conn.execute(text('ALTER TABLE time_off_request ADD COLUMN supervisor_notes TEXT'))
                conn.commit()
                
            if 'requires_coverage' not in time_off_columns:
                conn.execute(text('ALTER TABLE time_off_request ADD COLUMN requires_coverage BOOLEAN DEFAULT TRUE'))
                conn.commit()
                
            if 'coverage_arranged' not in time_off_columns:
                conn.execute(text('ALTER TABLE time_off_request ADD COLUMN coverage_arranged BOOLEAN DEFAULT FALSE'))
                conn.commit()
                
            if 'coverage_notes' not in time_off_columns:
                conn.execute(text('ALTER TABLE time_off_request ADD COLUMN coverage_notes TEXT'))
                conn.commit()
            
            # Check and add missing columns to CasualWorker table
            if 'casual_worker' in inspector.get_table_names():
                casual_columns = [col['name'] for col in inspector.get_columns('casual_worker')]
                
                if 'password_hash' not in casual_columns:
                    conn.execute(text('ALTER TABLE casual_worker ADD COLUMN password_hash VARCHAR(200)'))
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
            
            # Force check supervisor status from database
            fresh_employee = Employee.query.get(employee.id)
            if fresh_employee.is_supervisor == True:
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
    # Force refresh user data from database
    current_user_id = current_user.id
    fresh_user = db.session.query(Employee).filter_by(id=current_user_id).first()
    
    # Check fresh data from database
    if not fresh_user or fresh_user.is_supervisor != True:
        return redirect(url_for('employee_dashboard'))
    
    # Get pending time off requests
    pending_time_off = TimeOffRequest.query.filter_by(status='pending').all()
    
    # Get open coverage requests
    coverage_requests = CoverageRequest.query.filter_by(status='open').all()
    
    # Get pending swap requests
    pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').all()
    
    # Get recent suggestions
    recent_suggestions = ScheduleSuggestion.query.order_by(ScheduleSuggestion.created_at.desc()).limit(5).all()
    
    # Get available casual workers
    casual_workers = CasualWorker.query.filter_by(status='available').limit(5).all()
    
    # Get today's schedules
    today = date.today()
    schedules = Schedule.query.filter_by(date=today).all()
    
    # Get employees near overtime
    employees = Employee.query.filter_by(is_active=True).all()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    
    for emp in employees:
        schedules_week = Schedule.query.filter(
            Schedule.employee_id == emp.id,
            Schedule.date >= week_start,
            Schedule.date <= week_end
        ).all()
        emp.weekly_hours = sum((s.hours or 0) for s in schedules_week)
    
    return render_template('dashboard.html', 
                         schedules=schedules,
                         coverage_requests=coverage_requests,
                         casual_workers=casual_workers,
                         pending_time_off=pending_time_off,
                         pending_swaps=pending_swaps,
                         recent_suggestions=recent_suggestions,
                         employees=employees)

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
        
        # Get time off requests
        my_time_off_requests = TimeOffRequest.query.filter_by(
            employee_id=current_user.id
        ).order_by(TimeOffRequest.created_at.desc()).limit(5).all()
        
        return render_template('employee_dashboard.html',
                             upcoming_shifts=upcoming_shifts,
                             weekly_hours=round(weekly_hours, 1),
                             next_shift=next_shift,
                             pending_swaps=len(swap_requests),
                             swap_requests=swap_requests,
                             recent_suggestions=recent_suggestions,
                             time_off_requests=my_time_off_requests,
                             vacation_days=current_user.vacation_days_remaining,
                             sick_days=current_user.sick_days_remaining,
                             personal_days=current_user.personal_days_remaining,
                             today=today,
                             current_date=today.strftime('%A, %B %d, %Y'),
                             current_user=current_user)
                             
    except Exception as e:
        print(f"Employee dashboard error: {str(e)}")
        flash('Error loading dashboard. Please try again.', 'error')
        return redirect(url_for('index'))

# Vacation Request Form
@app.route('/vacation/request', methods=['GET', 'POST'])
@login_required
def request_vacation():
    if request.method == 'POST':
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        leave_type = request.form.get('leave_type')
        reason = request.form.get('reason', '')
        
        # Create time off request
        time_off_request = TimeOffRequest(
            employee_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
            leave_type=leave_type,
            reason=reason,
            status='pending'
        )
        
        # Calculate days requested (excluding weekends)
        time_off_request.calculate_days()
        
        # Check if employee has enough days
        available_days = current_user.get_time_off_balance(leave_type)
        if time_off_request.days_requested > available_days:
            flash(f'You only have {available_days} {leave_type} days available.', 'error')
            return redirect(url_for('request_vacation'))
        
        db.session.add(time_off_request)
        db.session.commit()
        
        flash('Time off request submitted successfully!', 'success')
        return redirect(url_for('employee_dashboard'))
    
    return render_template('vacation_request.html', current_user=current_user)

# Vacation Calendar View
@app.route('/vacation/calendar')
@login_required
def vacation_calendar():
    # Get current month or from query params
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    # Get all approved time off for the month
    start_date = datetime(year, month, 1).date()
    if month == 12:
        end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1).date() - timedelta(days=1)
    
    # Get all vacation calendar entries for the month
    calendar_entries = VacationCalendar.query.filter(
        VacationCalendar.date >= start_date,
        VacationCalendar.date <= end_date
    ).all()
    
    # Organize by date
    vacation_by_date = {}
    for entry in calendar_entries:
        date_str = entry.date.strftime('%Y-%m-%d')
        if date_str not in vacation_by_date:
            vacation_by_date[date_str] = []
        vacation_by_date[date_str].append({
            'employee_name': entry.employee.name,
            'leave_type': entry.leave_type
        })
    
    # Get calendar data
    cal = calendar.monthcalendar(year, month)
    month_name = calendar.month_name[month]
    
    return render_template('vacation_calendar.html',
                         calendar=cal,
                         year=year,
                         month=month,
                         month_name=month_name,
                         vacation_by_date=vacation_by_date,
                         today=date.today(),
                         datetime=datetime)

# Supervisor: Review Time Off Requests
@app.route('/supervisor/time-off-requests')
@login_required
def review_time_off_requests():
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'error')
        return redirect(url_for('employee_dashboard'))
    
    pending_requests = TimeOffRequest.query.filter_by(status='pending').all()
    
    # For each request, check coverage needs
    for req in pending_requests:
        # Get schedules that would be affected
        affected_schedules = Schedule.query.filter(
            Schedule.employee_id == req.employee_id,
            Schedule.date >= req.start_date,
            Schedule.date <= req.end_date
        ).all()
        req.affected_shifts = len(affected_schedules)
        
        # Check if any shifts need coverage
        req.coverage_needed = any(s.status == 'confirmed' for s in affected_schedules)
    
    return render_template('time_off_requests.html', requests=pending_requests)

# Approve/Deny Time Off Request
@app.route('/supervisor/time-off/<int:request_id>/<action>', methods=['POST'])
@login_required
def handle_time_off_request(request_id, action):
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'error')
        return redirect(url_for('employee_dashboard'))
    
    time_off_request = TimeOffRequest.query.get(request_id)
    if time_off_request:
        if action == 'approve':
            # Update request status
            time_off_request.status = 'approved'
            time_off_request.approved_by = current_user.id
            time_off_request.approved_at = datetime.utcnow()
            time_off_request.supervisor_notes = request.form.get('notes', '')
            
            # Update employee's time off balance
            employee = time_off_request.employee
            if time_off_request.leave_type == 'vacation':
                employee.vacation_days_used += time_off_request.days_requested
            elif time_off_request.leave_type == 'sick':
                employee.sick_days_used += time_off_request.days_requested
            elif time_off_request.leave_type == 'personal':
                employee.personal_days_used += time_off_request.days_requested
            
            # Create vacation calendar entries
            current_date = time_off_request.start_date
            while current_date <= time_off_request.end_date:
                # Skip weekends
                if current_date.weekday() < 5:
                    calendar_entry = VacationCalendar(
                        employee_id=time_off_request.employee_id,
                        date=current_date,
                        leave_type=time_off_request.leave_type,
                        time_off_request_id=time_off_request.id
                    )
                    db.session.add(calendar_entry)
                current_date += timedelta(days=1)
            
            # Handle coverage if needed
            if time_off_request.requires_coverage and not time_off_request.coverage_arranged:
                # Get affected schedules
                affected_schedules = Schedule.query.filter(
                    Schedule.employee_id == time_off_request.employee_id,
                    Schedule.date >= time_off_request.start_date,
                    Schedule.date <= time_off_request.end_date
                ).all()
                
                # Create coverage requests for each affected shift
                for schedule in affected_schedules:
                    coverage = CoverageRequest(
                        schedule_id=schedule.id,
                        status='open'
                    )
                    db.session.add(coverage)
                    
                    # Update schedule status
                    schedule.status = 'needs_coverage'
            
            flash(f'Time off request approved for {employee.name}!', 'success')
            
        else:  # deny
            time_off_request.status = 'denied'
            time_off_request.supervisor_notes = request.form.get('notes', '')
            flash('Time off request denied.', 'info')
        
        db.session.commit()
    
    return redirect(url_for('review_time_off_requests'))

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
        
        # Gather position requirements
        position_requirements = {}
        for position in Position.query.all():
            count = int(request.form.get(f'position_{position.id}_count', 0))
            if count > 0:
                position_requirements[position.id] = count
        
        # Gather shift times
        shifts = []
        shift_num = 1
        while f'shift{shift_num}_start' in request.form:
            shift_name = request.form.get(f'shift{shift_num}_name', f'Shift {shift_num}')
            start_time = datetime.strptime(request.form.get(f'shift{shift_num}_start'), '%H:%M').time()
            end_time = datetime.strptime(request.form.get(f'shift{shift_num}_end'), '%H:%M').time()
            shifts.append({
                'name': shift_name,
                'start_time': start_time,
                'end_time': end_time
            })
            shift_num += 1
        
        # Special handling for 4-crew rotation
        if shift_pattern == 'four_crew':
            crew_rotation = request.form.get('crew_rotation', '2-2-3')
            generated_schedules = generate_four_crew_schedule(
                start_date, end_date, position_requirements, crew_rotation
            )
        else:
            # Regular schedule generation
            options = {
                'shifts': shifts,
                'auto_assign': auto_assign,
                'fair_rotation': request.form.get('fair_rotation') == 'on',
                'skill_match': request.form.get('skill_match') == 'on',
                'overtime_check': request.form.get('overtime_check') == 'on',
                'respect_time_off': request.form.get('respect_time_off') == 'on'
            }
            generated_schedules = generate_schedule_with_shifts(
                start_date, end_date, position_requirements, options
            )
        
        # Save schedules to database
        try:
            for schedule in generated_schedules:
                db.session.add(schedule)
            db.session.commit()
            flash(f'Schedule created successfully! {len(generated_schedules)} shifts scheduled.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating schedule: {str(e)}', 'error')
        
        return redirect(url_for('dashboard'))
    
    # Get data for the form
    positions = Position.query.all()
    
    # Calculate employees near overtime and organize by crew
    employees = Employee.query.filter_by(is_active=True).all()
    employees_near_overtime = []
    overtime_eligible = []
    employees_by_crew = {}
    
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
        
        # Organize by crew
        crew = emp.crew or 'Unassigned'
        if crew not in employees_by_crew:
            employees_by_crew[crew] = []
        employees_by_crew[crew].append(emp)
    
    return render_template('schedule_input.html',
                         positions=positions,
                         employees=employees,
                         employees_near_overtime=employees_near_overtime,
                         overtime_eligible=overtime_eligible,
                         employees_by_crew=employees_by_crew)

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
                emp.set_password('admin123')
            else:
                emp.set_password('password123')
        
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
            output += f"<li>{emp.name} - Email: {emp.email} - Has Password: {has_password} - Is Supervisor: {emp.is_supervisor} - Vacation Days: {emp.vacation_days_remaining}/{emp.vacation_days_total}</li>"
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

def generate_schedule_with_shifts(start_date, end_date, position_requirements, options):
    """Generate schedule with multiple shifts per day"""
    generated_schedules = []
    current_date = start_date
    shifts = options.get('shifts', [])
    
    while current_date <= end_date:
        # Skip weekends if not required
        if current_date.weekday() >= 5 and not options.get('include_weekends'):
            current_date += timedelta(days=1)
            continue
        
        # Check for approved time off
        if options.get('respect_time_off'):
            employees_on_vacation = VacationCalendar.query.filter_by(date=current_date).all()
            vacation_employee_ids = [v.employee_id for v in employees_on_vacation]
        else:
            vacation_employee_ids = []
        
        # For each shift
        for shift in shifts:
            # For each position requirement
            for position_id, count in position_requirements.items():
                position = Position.query.get(position_id)
                if not position:
                    continue
                
                # Find eligible employees
                eligible_employees = []
                
                if options.get('skill_match'):
                    # Get required skills for position
                    required_skills = [ps.skill_id for ps in position.required_skills]
                    
                    for emp in Employee.query.filter_by(is_active=True).all():
                        # Skip employees on vacation
                        if emp.id in vacation_employee_ids:
                            continue
                        
                        emp_skills = [es.skill_id for es in emp.skills]
                        if all(skill in emp_skills for skill in required_skills):
                            eligible_employees.append(emp)
                else:
                    eligible_employees = [
                        emp for emp in Employee.query.filter_by(is_active=True).all()
                        if emp.id not in vacation_employee_ids
                    ]
                
                # Assign employees to shifts
                for i in range(count):
                    if i < len(eligible_employees):
                        schedule = Schedule(
                            date=current_date,
                            start_time=shift['start_time'],
                            end_time=shift['end_time'],
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

def generate_four_crew_schedule(start_date, end_date, position_requirements, rotation_pattern='2-2-3'):
    """
    Generate 4-crew 24/7 rotation schedule
    Rotation patterns:
    - '2-2-3': 2 on, 2 off, 3 on, 2 off, 2 on, 3 off (Pitman schedule)
    - '4-4': 4 days on, 4 days off
    - 'dupont': DuPont schedule (complex 28-day cycle)
    """
    generated_schedules = []
    
    # Define crew assignments - organize employees into 4 crews
    crews = organize_employees_into_crews()
    
    # Define shift times for 12-hour shifts
    day_shift = {'start_time': datetime.strptime('07:00', '%H:%M').time(), 
                 'end_time': datetime.strptime('19:00', '%H:%M').time()}
    night_shift = {'start_time': datetime.strptime('19:00', '%H:%M').time(), 
                   'end_time': datetime.strptime('07:00', '%H:%M').time()}
    
    # Generate rotation pattern
    if rotation_pattern == '2-2-3':
        # Pitman schedule: 2-2-3-2-2-3 pattern
        pattern = generate_pitman_pattern(start_date, end_date)
    elif rotation_pattern == '4-4':
        # Simple 4 on, 4 off
        pattern = generate_four_four_pattern(start_date, end_date)
    else:  # dupont
        pattern = generate_dupont_pattern(start_date, end_date)
    
    current_date = start_date
    day_index = 0
    
    while current_date <= end_date:
        crew_assignments = pattern[day_index % len(pattern)]
        
        # Assign day shift crews
        if crew_assignments['day_crews']:
            for crew_letter in crew_assignments['day_crews']:
                crew_employees = crews.get(crew_letter, [])
                
                for position_id, count in position_requirements.items():
                    position = Position.query.get(position_id)
                    if not position:
                        continue
                    
                    # Get employees from this crew with required skills
                    eligible_employees = get_eligible_crew_members(crew_employees, position_id)
                    
                    for i in range(min(count, len(eligible_employees))):
                        schedule = Schedule(
                            date=current_date,
                            start_time=day_shift['start_time'],
                            end_time=day_shift['end_time'],
                            employee_id=eligible_employees[i].id,
                            position_id=position_id,
                            status='scheduled'
                        )
                        schedule.calculate_hours()
                        generated_schedules.append(schedule)
        
        # Assign night shift crews
        if crew_assignments['night_crews']:
            for crew_letter in crew_assignments['night_crews']:
                crew_employees = crews.get(crew_letter, [])
                
                for position_id, count in position_requirements.items():
                    position = Position.query.get(position_id)
                    if not position:
                        continue
                    
                    eligible_employees = get_eligible_crew_members(crew_employees, position_id)
                    
                    for i in range(min(count, len(eligible_employees))):
                        schedule = Schedule(
                            date=current_date,
                            start_time=night_shift['start_time'],
                            end_time=night_shift['end_time'],
                            employee_id=eligible_employees[i].id,
                            position_id=position_id,
                            status='scheduled'
                        )
                        schedule.calculate_hours()
                        generated_schedules.append(schedule)
        
        current_date += timedelta(days=1)
        day_index += 1
    
    return generated_schedules

def organize_employees_into_crews():
    """Organize employees into 4 crews based on their current crew assignment"""
    crews = {'A': [], 'B': [], 'C': [], 'D': []}
    
    # First, use existing crew assignments
    employees = Employee.query.filter_by(is_active=True).all()
    unassigned = []
    
    for emp in employees:
        if emp.crew and emp.crew.upper() in crews:
            crews[emp.crew.upper()].append(emp)
        elif 'Crew A' in (emp.crew or ''):
            crews['A'].append(emp)
        elif 'Crew B' in (emp.crew or ''):
            crews['B'].append(emp)
        elif 'Crew C' in (emp.crew or ''):
            crews['C'].append(emp)
        elif 'Crew D' in (emp.crew or ''):
            crews['D'].append(emp)
        else:
            unassigned.append(emp)
    
    # Distribute unassigned employees evenly
    crew_letters = ['A', 'B', 'C', 'D']
    for i, emp in enumerate(unassigned):
        crew_letter = crew_letters[i % 4]
        crews[crew_letter].append(emp)
        # Update employee's crew assignment
        emp.crew = f'Crew {crew_letter}'
    
    return crews

def get_eligible_crew_members(crew_employees, position_id):
    """Get crew members eligible for a specific position"""
    position = Position.query.get(position_id)
    if not position:
        return []
    
    required_skills = [ps.skill_id for ps in position.required_skills]
    
    if not required_skills:
        return crew_employees
    
    eligible = []
    for emp in crew_employees:
        emp_skills = [es.skill_id for es in emp.skills]
        if all(skill in emp_skills for skill in required_skills):
            eligible.append(emp)
    
    return eligible

def generate_pitman_pattern(start_date, end_date):
    """Generate 2-2-3 Pitman rotation pattern"""
    # Pattern repeats every 2 weeks (14 days)
    # Week 1: Crew A&B work days, C&D work nights
    # Week 2: Crews rotate
    pattern = [
        # Week 1
        {'day_crews': ['A', 'B'], 'night_crews': ['C', 'D']},  # Day 1
        {'day_crews': ['A', 'B'], 'night_crews': ['C', 'D']},  # Day 2
        {'day_crews': [], 'night_crews': []},                   # Day 3 (off)
        {'day_crews': [], 'night_crews': []},                   # Day 4 (off)
        {'day_crews': ['A', 'B'], 'night_crews': ['C', 'D']},  # Day 5
        {'day_crews': ['A', 'B'], 'night_crews': ['C', 'D']},  # Day 6
        {'day_crews': ['A', 'B'], 'night_crews': ['C', 'D']},  # Day 7
        # Week 2
        {'day_crews': ['C', 'D'], 'night_crews': ['A', 'B']},  # Day 8
        {'day_crews': ['C', 'D'], 'night_crews': ['A', 'B']},  # Day 9
        {'day_crews': [], 'night_crews': []},                   # Day 10 (off)
        {'day_crews': [], 'night_crews': []},                   # Day 11 (off)
        {'day_crews': ['C', 'D'], 'night_crews': ['A', 'B']},  # Day 12
        {'day_crews': ['C', 'D'], 'night_crews': ['A', 'B']},  # Day 13
        {'day_crews': ['C', 'D'], 'night_crews': ['A', 'B']},  # Day 14
    ]
    
    return pattern

def generate_four_four_pattern(start_date, end_date):
    """Generate 4-on-4-off rotation pattern"""
    # Simple 4 days on, 4 days off for each crew
    pattern = []
    
    # 16-day cycle (each crew works 4, off 4, twice)
    for i in range(16):
        day_pattern = {'day_crews': [], 'night_crews': []}
        
        # Crew A: Days 1-4, 9-12
        if 0 <= i % 16 <= 3 or 8 <= i % 16 <= 11:
            day_pattern['day_crews'].append('A')
        
        # Crew B: Days 5-8, 13-16
        if 4 <= i % 16 <= 7 or 12 <= i % 16 <= 15:
            day_pattern['day_crews'].append('B')
        
        # Crew C: Nights 1-4, 9-12
        if 0 <= i % 16 <= 3 or 8 <= i % 16 <= 11:
            day_pattern['night_crews'].append('C')
        
        # Crew D: Nights 5-8, 13-16
        if 4 <= i % 16 <= 7 or 12 <= i % 16 <= 15:
            day_pattern['night_crews'].append('D')
        
        pattern.append(day_pattern)
    
    return pattern

def generate_dupont_pattern(start_date, end_date):
    """Generate DuPont rotation pattern (28-day cycle)"""
    # This is a simplified version of the DuPont schedule
    # Real DuPont has a complex 28-day rotation with varying shifts
    pattern = []
    
    # Simplified: 4 nights, 3 off, 3 days, 1 off, 3 nights, 3 off, 4 days, 7 off
    dupont_cycle = [
        # 4 nights (Crew A)
        {'day_crews': ['B'], 'night_crews': ['A']},
        {'day_crews': ['B'], 'night_crews': ['A']},
        {'day_crews': ['B'], 'night_crews': ['A']},
        {'day_crews': ['B'], 'night_crews': ['A']},
        # 3 off
        {'day_crews': ['C'], 'night_crews': ['D']},
        {'day_crews': ['C'], 'night_crews': ['D']},
        {'day_crews': ['C'], 'night_crews': ['D']},
        # 3 days (Crew A)
        {'day_crews': ['A'], 'night_crews': ['B']},
        {'day_crews': ['A'], 'night_crews': ['B']},
        {'day_crews': ['A'], 'night_crews': ['B']},
        # 1 off
        {'day_crews': ['D'], 'night_crews': ['C']},
        # 3 nights (Crew A)
        {'day_crews': ['D'], 'night_crews': ['A']},
        {'day_crews': ['D'], 'night_crews': ['A']},
        {'day_crews': ['D'], 'night_crews': ['A']},
        # Continue pattern...
    ]
    
    # Extend pattern to 28 days
    while len(pattern) < 28:
        pattern.extend(dupont_cycle)
    
    return pattern[:28]

if __name__ == '__main__':
    app.run(debug=True)
