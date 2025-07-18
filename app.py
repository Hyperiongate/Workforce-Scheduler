from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta, date
import os
from sqlalchemy import inspect, case, and_, or_, func
from models import db, Employee, Position, Skill, Schedule, Availability, TimeOffRequest, VacationCalendar, CoverageRequest, CasualWorker, CasualAssignment, ShiftSwapRequest, ScheduleSuggestion, CircadianProfile, SleepLog, SleepRecommendation, ShiftTransitionPlan, CoverageNotification, OvertimeOpportunity, ShiftTradePost, ShiftTradeProposal, ShiftTrade, TradeMatchPreference, SupervisorMessage, PositionMessage, PositionMessageRead, MaintenanceIssue, MaintenanceUpdate, MaintenanceManager
from circadian_advisor import CircadianAdvisor
import json
import pandas as pd
from io import BytesIO

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here') 

# Fixed database URL configuration
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # Handle Render's PostgreSQL URL format
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Fallback to SQLite for local development
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workforce.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}

# Create upload folder if it doesn't exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return Employee.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# ==================== HELPER FUNCTIONS ====================

def get_coverage_gaps(crew='ALL', days_ahead=7):
    """Get coverage gaps for the specified crew and time period"""
    gaps = []
    start_date = date.today()
    end_date = start_date + timedelta(days=days_ahead)
    
    current = start_date
    while current <= end_date:
        # Check each shift type
        for shift_type in ['day', 'evening', 'night']:
            scheduled_query = Schedule.query.filter(
                Schedule.date == current,
                Schedule.shift_type == shift_type
            )
            
            if crew != 'ALL':
                scheduled_query = scheduled_query.filter(Schedule.crew == crew)
            
            scheduled_count = scheduled_query.count()
            
            # Define minimum coverage requirements
            min_coverage = {
                'day': 4,
                'evening': 3,
                'night': 2
            }
            
            if scheduled_count < min_coverage.get(shift_type, 2):
                gaps.append({
                    'date': current,
                    'shift_type': shift_type,
                    'scheduled': scheduled_count,
                    'required': min_coverage.get(shift_type, 2),
                    'gap': min_coverage.get(shift_type, 2) - scheduled_count,
                    'crew': crew
                })
    
        current += timedelta(days=1)
    
    return gaps

def get_off_duty_crews(schedule_date, shift_type):
    """Determine which crews are off duty for a given date and shift"""
    # This is a simplified version - in reality, you'd check the actual rotation pattern
    off_crews = []
    
    # Example logic: based on date, determine which crews are off
    day_number = (schedule_date - date(2024, 1, 1)).days % 4
    
    if shift_type == 'day':
        if day_number in [0, 1]:
            off_crews = ['C', 'D']
        else:
            off_crews = ['A', 'B']
    elif shift_type == 'night':
        if day_number in [0, 1]:
            off_crews = ['A', 'B']
        else:
            off_crews = ['C', 'D']
    
    return off_crews

def update_circadian_profile_on_schedule_change(employee_id, shift_type):
    """Update circadian profile when schedule changes"""
    profile = CircadianProfile.query.filter_by(employee_id=employee_id).first()
    if not profile:
        profile = CircadianProfile(
            employee_id=employee_id,
            chronotype='intermediate',
            current_shift_type=shift_type
        )
        db.session.add(profile)
    
    profile.current_shift_type = shift_type
    profile.last_shift_change = datetime.now()

def calculate_trade_compatibility(user, trade_post):
    """Calculate compatibility score for a trade"""
    schedule = trade_post.schedule
    
    # Check position match
    if user.position_id == schedule.position_id:
        return 'high'
    
    # Check skill match
    if schedule.position:
        required_skills = [s.id for s in schedule.position.required_skills]
        user_skills = [s.id for s in user.skills]
        if all(skill in user_skills for skill in required_skills):
            return 'medium'
    
    return 'low'

def get_trade_history(employee_id, limit=10):
    """Get trade history for an employee"""
    trades = ShiftTrade.query.filter(
        or_(
            ShiftTrade.employee1_id == employee_id,
            ShiftTrade.employee2_id == employee_id
        ),
        ShiftTrade.status == 'completed'
    ).order_by(ShiftTrade.completed_at.desc()).limit(limit).all()
    
    return trades

def get_overtime_opportunities():
    """Get upcoming overtime opportunities"""
    # This would typically query from a dedicated table or calculate based on gaps
    opportunities = []
    gaps = get_coverage_gaps('ALL', 14)
    
    for gap in gaps:
        if gap['gap'] > 0:
            opportunities.append({
                'id': f"{gap['date']}_{gap['shift_type']}",
                'date': gap['date'],
                'shift_type': gap['shift_type'],
                'positions_needed': gap['gap'],
                'start_time': datetime.strptime('07:00', '%H:%M').time() if gap['shift_type'] == 'day' else datetime.strptime('19:00', '%H:%M').time(),
                'end_time': datetime.strptime('19:00', '%H:%M').time() if gap['shift_type'] == 'day' else datetime.strptime('07:00', '%H:%M').time(),
                'hours': 12
            })
    
    return opportunities[:10]  # Return first 10

def get_overtime_eligible_employees():
    """Get employees eligible for overtime"""
    # Get employees with less than 40 hours this week
    week_start = date.today() - timedelta(days=date.today().weekday())
    week_end = week_start + timedelta(days=6)
    
    employees = Employee.query.filter_by(is_supervisor=False).all()
    eligible = []
    
    for emp in employees:
        week_hours = db.session.query(func.sum(Schedule.hours)).filter(
            Schedule.employee_id == emp.id,
            Schedule.date >= week_start,
            Schedule.date <= week_end
        ).scalar() or 0
        
        if week_hours < 60:  # Eligible if under 60 hours
            eligible.append({
                'employee': emp,
                'current_hours': week_hours,
                'available_hours': 60 - week_hours
            })
    
    return eligible

def is_eligible_for_overtime(employee, opportunity):
    """Check if employee is eligible for specific overtime"""
    # Check weekly hours limit
    week_start = opportunity['date'] - timedelta(days=opportunity['date'].weekday())
    week_end = week_start + timedelta(days=6)
    
    current_hours = db.session.query(func.sum(Schedule.hours)).filter(
        Schedule.employee_id == employee.id,
        Schedule.date >= week_start,
        Schedule.date <= week_end
    ).scalar() or 0
    
    if current_hours + opportunity['hours'] > 60:
        return False
    
    # Check if already scheduled that day
    existing = Schedule.query.filter_by(
        employee_id=employee.id,
        date=opportunity['date']
    ).first()
    
    return existing is None

def execute_shift_trade(trade):
    """Execute an approved shift trade"""
    schedule1 = Schedule.query.get(trade.schedule1_id)
    schedule2 = Schedule.query.get(trade.schedule2_id)
    
    # Swap employee assignments
    temp_employee = schedule1.employee_id
    schedule1.employee_id = schedule2.employee_id
    schedule2.employee_id = temp_employee
    
    # Update trade status
    trade.status = 'completed'
    trade.completed_at = datetime.now()

# ==================== AUTHENTICATION ROUTES ====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        employee = Employee.query.filter_by(email=email).first()
        
        if employee and employee.check_password(password):
            login_user(employee)
            flash(f'Welcome back, {employee.name}!', 'success')
            
            # Redirect based on role
            if employee.is_supervisor:
                return redirect(url_for('dashboard'))
            else:
                return redirect(url_for('employee_dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('index'))

# ==================== DASHBOARD ROUTES ====================

# Replace the existing dashboard route in app.py with this updated version

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'supervisor':
        flash('Access denied. Supervisors only.')
        return redirect(url_for('employee_dashboard'))
    
    # Get crew filter
    selected_crew = request.args.get('crew', '')
    
    # Base query for employees
    employees_query = Employee.query
    if selected_crew:
        employees_query = employees_query.filter_by(crew=selected_crew)
    
    employees = employees_query.all()
    total_employees = len(employees)
    
    # Calculate on duty now (employees currently working)
    from datetime import datetime, time
    current_time = datetime.now().time()
    current_date = datetime.now().date()
    
    on_duty_now = 0
    todays_shifts = []
    
    # Get today's schedules
    schedules = Schedule.query.filter(
        Schedule.date == current_date
    ).all()
    
    for schedule in schedules:
        if selected_crew and schedule.employee.crew != selected_crew:
            continue
            
        # Check if shift is currently active
        if schedule.start_time <= current_time <= schedule.end_time:
            on_duty_now += 1
        
        # Add to today's shifts
        todays_shifts.append({
            'position_name': schedule.position.name,
            'employee_name': schedule.employee.name,
            'start_time': schedule.start_time.strftime('%H:%M'),
            'end_time': schedule.end_time.strftime('%H:%M')
        })
    
    # Calculate coverage gaps (unfilled positions for next 7 days)
    coverage_gaps = 0
    upcoming_gaps = []
    
    for days_ahead in range(7):
        check_date = current_date + timedelta(days=days_ahead)
        
        # Get all positions
        positions = Position.query.all()
        for position in positions:
            # Check each shift type
            for shift_name, shift_times in [
                ('Morning', (time(7, 0), time(15, 0))),
                ('Afternoon', (time(15, 0), time(23, 0))),
                ('Night', (time(23, 0), time(7, 0)))
            ]:
                # Check if position is filled for this shift
                scheduled = Schedule.query.filter(
                    Schedule.date == check_date,
                    Schedule.position_id == position.id,
                    Schedule.start_time == shift_times[0]
                ).first()
                
                if not scheduled:
                    coverage_gaps += 1
                    if len(upcoming_gaps) < 5:  # Only show first 5
                        upcoming_gaps.append({
                            'id': f"{position.id}_{check_date}_{shift_name}",
                            'position': position.name,
                            'date': check_date.strftime('%Y-%m-%d'),
                            'shift': shift_name
                        })
    
    # Calculate pending requests
    pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
    pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
    pending_suggestions = ScheduleSuggestion.query.filter_by(status='pending').count()
    pending_requests = pending_time_off + pending_swaps + pending_suggestions
    
    # Get other supervisors for quick message
    supervisors = Employee.query.filter_by(role='supervisor').all()
    
    # Get positions for announcements
    positions = Position.query.all()
    
    # Get recent activities (last 10 actions)
    recent_activities = []
    
    # Add recent time off approvals
    recent_time_offs = TimeOffRequest.query.filter(
        TimeOffRequest.status.in_(['approved', 'denied'])
    ).order_by(TimeOffRequest.id.desc()).limit(5).all()
    
    for req in recent_time_offs:
        time_ago = calculate_time_ago(req.created_at)
        recent_activities.append({
            'description': f"{req.employee.name} - Time off {req.status}",
            'time_ago': time_ago
        })
    
    # Add recent swap requests
    recent_swaps = ShiftSwapRequest.query.filter(
        ShiftSwapRequest.status != 'pending'
    ).order_by(ShiftSwapRequest.id.desc()).limit(5).all()
    
    for swap in recent_swaps:
        time_ago = calculate_time_ago(swap.created_at)
        recent_activities.append({
            'description': f"Shift swap {swap.status} - {swap.requester.name}",
            'time_ago': time_ago
        })
    
    # Sort activities by recency (would need timestamp tracking for accurate sorting)
    recent_activities = recent_activities[:10]
    
    # Count active users (simplified - count logins in last hour)
    active_users = 1  # At least current user
    
    # Count active trades in marketplace
    active_trades = ShiftTradePost.query.filter_by(status='active').count() if 'ShiftTradePost' in globals() else 0
    
    return render_template('dashboard.html',
        employees=employees,
        total_employees=total_employees,
        selected_crew=selected_crew,
        on_duty_now=on_duty_now,
        coverage_gaps=coverage_gaps,
        pending_requests=pending_requests,
        pending_time_off=pending_time_off,
        pending_swaps=pending_swaps,
        pending_suggestions=pending_suggestions,
        todays_shifts=todays_shifts,
        upcoming_gaps=upcoming_gaps,
        recent_activities=recent_activities,
        supervisors=supervisors,
        positions=positions,
        active_users=active_users,
        active_trades=active_trades,
        last_sync='Just now'
    )

# Helper function to calculate time ago
def calculate_time_ago(timestamp):
    if not timestamp:
        return "Unknown time"
    
    from datetime import datetime
    now = datetime.now()
    
    # If timestamp is a date, convert to datetime
    if hasattr(timestamp, 'date'):
        time_diff = now - timestamp
    else:
        # Assume it's a date object, add time component
        time_diff = now.date() - timestamp
        return f"{time_diff.days} days ago" if time_diff.days > 0 else "Today"
    
    seconds = time_diff.total_seconds()
    
    if seconds < 60:
        return "Just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"

# Helper function to calculate time ago
def calculate_time_ago(timestamp):
    if not timestamp:
        return "Unknown time"
    
    from datetime import datetime
    now = datetime.now()
    
    # If timestamp is a date, convert to datetime
    if hasattr(timestamp, 'date'):
        time_diff = now - timestamp
    else:
        # Assume it's a date object, add time component
        time_diff = now.date() - timestamp
        return f"{time_diff.days} days ago" if time_diff.days > 0 else "Today"
    
    seconds = time_diff.total_seconds()
    
    if seconds < 60:
        return "Just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"

@app.route('/employee-dashboard')
@login_required
def employee_dashboard():
    """Employee dashboard with schedules, requests, and sleep health info"""
    employee = Employee.query.get(current_user.id)
    
    # Get upcoming schedules
    schedules = Schedule.query.filter(
        Schedule.employee_id == employee.id,
        Schedule.date >= date.today()
    ).order_by(Schedule.date, Schedule.start_time).limit(7).all()
    
    # Calculate this week's hours
    week_start = date.today() - timedelta(days=date.today().weekday())
    week_end = week_start + timedelta(days=6)
    
    week_schedules = Schedule.query.filter(
        Schedule.employee_id == employee.id,
        Schedule.date >= week_start,
        Schedule.date <= week_end
    ).all()
    
    weekly_hours = sum(s.hours or 8 for s in week_schedules if not s.is_overtime)
    overtime_hours = sum(s.hours or 0 for s in week_schedules if s.is_overtime)
    
    # Get pending requests
    swap_requests = ShiftSwapRequest.query.filter(
        or_(
            ShiftSwapRequest.requester_id == employee.id,
            ShiftSwapRequest.target_employee_id == employee.id
        ),
        ShiftSwapRequest.status == 'pending'
    ).all()
    
    time_off_requests = TimeOffRequest.query.filter_by(
        employee_id=employee.id,
        status='pending'
    ).all()
    
    # Get sleep profile
    sleep_profile = CircadianProfile.query.filter_by(employee_id=employee.id).first()
    
    # Check for coverage notifications
    unread_notifications = CoverageNotification.query.filter(
        CoverageNotification.sent_to_employee_id == employee.id,
        CoverageNotification.read_at.is_(None)
    ).count()
    
    return render_template('employee_dashboard.html',
                         employee=employee,
                         schedules=schedules,
                         weekly_hours=weekly_hours,
                         overtime_hours=overtime_hours,
                         swap_requests=swap_requests,
                         time_off_requests=time_off_requests,
                         sleep_profile=sleep_profile,
                         unread_notifications=unread_notifications)

# ==================== COVERAGE GAP ROUTES ====================

@app.route('/supervisor/coverage-gaps')
@login_required
def coverage_gaps():
    """View detailed coverage gaps analysis"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Get filter parameters
    selected_crew = request.args.get('crew', 'ALL')
    days_ahead = int(request.args.get('days_ahead', 7))
    shift_type = request.args.get('shift_type', '')
    
    # Get coverage gaps
    gaps = get_coverage_gaps(selected_crew, days_ahead)
    
    # Filter by shift type if specified
    if shift_type:
        gaps = [g for g in gaps if g['shift_type'] == shift_type]
    
    # Get positions for filter
    positions = Position.query.all()
    
    # Calculate dates for statistics
    today = date.today()
    week_end = today + timedelta(days=7)
    
    return render_template('coverage_gaps.html',
                         coverage_gaps=gaps,
                         selected_crew=selected_crew,
                         days_ahead=days_ahead,
                         shift_type=shift_type,
                         positions=positions,
                         today=today,
                         week_end=week_end)

@app.route('/supervisor/fill-gap')
@login_required
def fill_gap():
    """Fill a specific coverage gap"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Get gap details from query params
    gap_date = request.args.get('date')
    if gap_date:
        gap_date = datetime.strptime(gap_date, '%Y-%m-%d').date()
    else:
        gap_date = date.today()
    
    shift_type = request.args.get('shift_type', 'day')
    crew = request.args.get('crew', 'ALL')
    
    # Get available employees (not already scheduled for this date/shift)
    available_employees = []
    all_employees = Employee.query.filter_by(is_supervisor=False).all()
    
    for emp in all_employees:
        # Check if already scheduled
        existing_schedule = Schedule.query.filter_by(
            employee_id=emp.id,
            date=gap_date,
            shift_type=shift_type
        ).first()
        
        if not existing_schedule:
            # Check current week hours
            week_start = gap_date - timedelta(days=gap_date.weekday())
            week_end = week_start + timedelta(days=6)
            
            current_hours = db.session.query(func.sum(Schedule.hours)).filter(
                Schedule.employee_id == emp.id,
                Schedule.date >= week_start,
                Schedule.date <= week_end
            ).scalar() or 0
            
            # Check if on time off
            time_off = VacationCalendar.query.filter_by(
                employee_id=emp.id,
                date=gap_date
            ).first()
            
            emp.current_hours = current_hours
            emp.is_available = time_off is None
            emp.conflict_reason = 'Time Off' if time_off else None
            
            # Determine skills match (simplified)
            emp.skills_match = 'full' if emp.skills else 'basic'
            
            available_employees.append(emp)
    
    # Get casual workers
    casual_workers = CasualWorker.query.filter_by(is_active=True).all()
    
    # Get scheduled count for this gap
    scheduled_count = Schedule.query.filter(
        Schedule.date == gap_date,
        Schedule.shift_type == shift_type
    ).count()
    
    # Define minimum requirements
    min_coverage = {'day': 4, 'evening': 3, 'night': 2}
    required_count = min_coverage.get(shift_type, 2)
    gap_count = required_count - scheduled_count
    
    # Get positions
    positions = Position.query.all()
    
    return render_template('fill_gap.html',
                         gap_date=gap_date,
                         shift_type=shift_type,
                         crew=crew,
                         available_employees=available_employees,
                         casual_workers=casual_workers,
                         scheduled_count=scheduled_count,
                         required_count=required_count,
                         gap_count=gap_count,
                         positions=positions)

@app.route('/supervisor/todays-schedule')
@login_required
def todays_schedule():
    """Redirect to schedule view for today"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Redirect to schedule view with today's date
    return redirect(url_for('view_schedules', 
                          start_date=date.today().strftime('%Y-%m-%d'),
                          end_date=date.today().strftime('%Y-%m-%d'),
                          crew=current_user.crew or 'ALL'))

@app.route('/supervisor/create-schedule')
@login_required
def supervisor_create_schedule():
    """Redirect to schedule creation"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    return redirect(url_for('create_schedule'))

# ==================== VACATION/TIME OFF ROUTES ====================

@app.route('/vacation/request', methods=['GET', 'POST'])
@login_required
def vacation_request():
    """Request time off"""
    if request.method == 'POST':
        request_type = request.form.get('request_type')
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        reason = request.form.get('reason', '')
        
        # Calculate days (excluding weekends)
        days_requested = 0
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:  # Monday = 0, Friday = 4
                days_requested += 1
            current += timedelta(days=1)
        
        # Check balance
        if request_type == 'vacation' and days_requested > current_user.vacation_days:
            flash('Insufficient vacation days available.', 'danger')
            return redirect(url_for('vacation_request'))
        elif request_type == 'sick' and days_requested > current_user.sick_days:
            flash('Insufficient sick days available.', 'danger')
            return redirect(url_for('vacation_request'))
        elif request_type == 'personal' and days_requested > current_user.personal_days:
            flash('Insufficient personal days available.', 'danger')
            return redirect(url_for('vacation_request'))
        
        # Create request
        time_off = TimeOffRequest(
            employee_id=current_user.id,
            request_type=request_type,
            start_date=start_date,
            end_date=end_date,
            days_requested=days_requested,
            reason=reason,
            status='pending'
        )
        
        db.session.add(time_off)
        db.session.commit()
        
        flash('Time off request submitted successfully!', 'success')
        return redirect(url_for('employee_dashboard'))
    
    return render_template('vacation_request.html',
                         vacation_days=current_user.vacation_days,
                         sick_days=current_user.sick_days,
                         personal_days=current_user.personal_days)

@app.route('/supervisor/time-off-requests')
@login_required
def time_off_requests():
    """Review and manage time off requests"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Get pending requests
    pending_requests = TimeOffRequest.query.filter_by(status='pending').order_by(TimeOffRequest.submitted_date.desc()).all()
    
    # Get recently processed requests
    recent_requests = TimeOffRequest.query.filter(
        TimeOffRequest.status.in_(['approved', 'denied'])
    ).order_by(TimeOffRequest.submitted_date.desc()).limit(20).all()
    
    return render_template('time_off_requests.html',
                         pending_requests=pending_requests,
                         recent_requests=recent_requests)

@app.route('/time-off/<int:request_id>/approve', methods=['POST'])
@login_required
def approve_time_off(request_id):
    """Approve a time off request"""
    if not current_user.is_supervisor:
        flash('Access denied.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    time_off = TimeOffRequest.query.get_or_404(request_id)
    
    if time_off.status != 'pending':
        flash('This request has already been processed.', 'warning')
        return redirect(url_for('time_off_requests'))
    
    # Update status
    time_off.status = 'approved'
    time_off.reviewed_date = datetime.now()
    time_off.reviewed_by_id = current_user.id
    
    # Update employee balances
    if time_off.request_type == 'vacation':
        time_off.employee.vacation_days -= time_off.days_requested
    elif time_off.request_type == 'sick':
        time_off.employee.sick_days -= time_off.days_requested
    elif time_off.request_type == 'personal':
        time_off.employee.personal_days -= time_off.days_requested
    
    # Add to vacation calendar
    current = time_off.start_date
    while current <= time_off.end_date:
        if current.weekday() < 5:  # Weekdays only
            calendar_entry = VacationCalendar(
                employee_id=time_off.employee_id,
                date=current,
                type=time_off.request_type,
                request_id=time_off.id
            )
            db.session.add(calendar_entry)
        current += timedelta(days=1)
    
    db.session.commit()
    
    flash(f'Time off request for {time_off.employee.name} has been approved!', 'success')
    return redirect(url_for('time_off_requests'))

@app.route('/time-off/<int:request_id>/deny', methods=['POST'])
@login_required
def deny_time_off(request_id):
    """Deny a time off request"""
    if not current_user.is_supervisor:
        flash('Access denied.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    time_off = TimeOffRequest.query.get_or_404(request_id)
    
    if time_off.status != 'pending':
        flash('This request has already been processed.', 'warning')
        return redirect(url_for('time_off_requests'))
    
    # Update status
    time_off.status = 'denied'
    time_off.reviewed_date = datetime.now()
    time_off.reviewed_by_id = current_user.id
    
    db.session.commit()
    
    flash(f'Time off request for {time_off.employee.name} has been denied.', 'info')
    return redirect(url_for('time_off_requests'))

@app.route('/vacation-calendar')
@login_required
def vacation_calendar():
    """View team vacation calendar"""
    # Get month and year from query params, default to current month
    import calendar
    from datetime import datetime, date, timedelta
    
    # Get month/year from query params or use current
    month = request.args.get('month', type=int, default=date.today().month)
    year = request.args.get('year', type=int, default=date.today().year)
    
    # Create calendar date
    calendar_date = date(year, month, 1)
    
    # Calculate previous and next month/year
    if month == 1:
        prev_month = 12
        prev_year = year - 1
    else:
        prev_month = month - 1
        prev_year = year
    
    if month == 12:
        next_month = 1
        next_year = year + 1
    else:
        next_month = month + 1
        next_year = year
    
    # Get calendar entries for the month
    month_start = date(year, month, 1)
    # Get last day of month
    if month == 12:
        month_end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(year, month + 1, 1) - timedelta(days=1)
    
    # Get all vacation calendar entries for the month
    monthly_entries = VacationCalendar.query.filter(
        VacationCalendar.date >= month_start,
        VacationCalendar.date <= month_end
    ).order_by(VacationCalendar.date).all()
    
    # Create calendar grid
    cal = calendar.monthcalendar(year, month)
    calendar_data = []
    
    for week in cal:
        week_data = []
        for day in week:
            if day == 0:
                week_data.append((0, []))
            else:
                day_date = date(year, month, day)
                # Get entries for this specific day
                day_entries = [
                    entry for entry in monthly_entries 
                    if entry.date == day_date
                ]
                week_data.append((day, day_entries))
        calendar_data.append(week_data)
    
    # Get today's date for highlighting
    today = date.today()
    
    return render_template('vacation_calendar.html',
                         calendar_data=calendar_data,
                         calendar_date=calendar_date,
                         month=month,
                         year=year,
                         prev_month=prev_month,
                         prev_year=prev_year,
                         next_month=next_month,
                         next_year=next_year,
                         today=today,
                         monthly_entries=monthly_entries)

# ==================== SUGGESTIONS ROUTES ====================

@app.route('/supervisor/suggestions')
@login_required
def suggestions():
    """View employee suggestions"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Get all suggestions
    all_suggestions = ScheduleSuggestion.query.order_by(ScheduleSuggestion.submitted_date.desc()).all()
    
    return render_template('suggestions.html', suggestions=all_suggestions)

# ==================== CASUAL WORKER ROUTES ====================

@app.route('/register-casual')
def register_casual():
    """Casual worker registration form"""
    skills = Skill.query.all()
    return render_template('register_casual.html', skills=skills)

@app.route('/register-casual', methods=['POST'])
def register_casual_post():
    """Process casual worker registration"""
    try:
        # Create casual worker
        casual = CasualWorker(
            name=request.form.get('name'),
            email=request.form.get('email'),
            phone=request.form.get('phone'),
            skills=json.dumps(request.form.getlist('skills')),
            availability=json.dumps({
                'days': request.form.getlist('availability_days'),
                'shifts': request.form.getlist('availability_shifts')
            }),
            preferred_crews=request.form.get('preferred_crews', '')
        )
        
        db.session.add(casual)
        db.session.commit()
        
        flash('Registration successful! You will be contacted when shifts are available.', 'success')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error during registration: {str(e)}', 'danger')
        return redirect(url_for('register_casual'))

@app.route('/casual-workers')
@login_required
def casual_workers():
    """View and manage casual workers"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Get all casual workers
    casuals = CasualWorker.query.filter_by(is_active=True).all()
    inactive_casuals = CasualWorker.query.filter_by(is_active=False).all()
    
    return render_template('casual_workers.html',
                         casuals=casuals,
                         inactive_casuals=inactive_casuals)

# ==================== COVERAGE MANAGEMENT ROUTES ====================

@app.route('/supervisor/coverage-needs')
@login_required
def coverage_needs():
    """View all coverage needs and gaps"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Get open coverage requests
    open_requests = CoverageRequest.query.filter_by(status='open').all()
    
    # Get coverage gaps for next 14 days
    coverage_gaps = get_coverage_gaps(crew='ALL', days_ahead=14)
    
    # Get available casual workers
    casual_workers = CasualWorker.query.filter_by(is_active=True).all()
    
    return render_template('coverage_needs.html',
                         open_requests=open_requests,
                         coverage_gaps=coverage_gaps,
                         casual_workers=casual_workers)

@app.route('/coverage/push/<int:request_id>', methods=['POST'])
@login_required
def push_coverage(request_id):
    """Push coverage request to employees"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    coverage = CoverageRequest.query.get_or_404(request_id)
    
    push_to = request.form.get('push_to')
    message = request.form.get('message', '')
    
    notifications_sent = 0
    
    if push_to == 'my_crew':
        # Push to supervisor's crew only
        employees = Employee.query.filter_by(
            crew=current_user.crew,
            is_supervisor=False
        ).all()
    elif push_to == 'off_crews':
        # Find crews that are off during this shift
        schedule_date = coverage.schedule.date
        off_crews = get_off_duty_crews(schedule_date, coverage.schedule.shift_type)
        employees = Employee.query.filter(
            Employee.crew.in_(off_crews),
            Employee.is_supervisor == False
        ).all()
    elif push_to == 'specific_crew':
        crew = request.form.get('specific_crew')
        employees = Employee.query.filter_by(
            crew=crew,
            is_supervisor=False
        ).all()
    elif push_to == 'supervisors':
        # Push to other supervisors
        employees = Employee.query.filter(
            Employee.is_supervisor == True,
            Employee.id != current_user.id
        ).all()
    else:
        employees = []
    
    # Filter by required skills if specified
    if coverage.position_required:
        position = Position.query.get(coverage.position_required)
        required_skills = [s.id for s in position.required_skills]
        
        qualified_employees = []
        for emp in employees:
            emp_skills = [s.id for s in emp.skills]
            if all(skill in emp_skills for skill in required_skills):
                qualified_employees.append(emp)
        employees = qualified_employees
    
    # Send notifications
    for employee in employees:
        # Check if employee is already working that day
        existing_schedule = Schedule.query.filter_by(
            employee_id=employee.id,
            date=coverage.schedule.date
        ).first()
        
        if not existing_schedule:  # Only notify if not already scheduled
            notification = CoverageNotification(
                coverage_request_id=coverage.id,
                sent_to_type='individual',
                sent_to_employee_id=employee.id,
                sent_by_id=current_user.id,
                message=message or f"Coverage needed for {coverage.schedule.date} {coverage.schedule.shift_type} shift"
            )
            db.session.add(notification)
            notifications_sent += 1
    
    # Update coverage request
    coverage.pushed_to_crews = push_to
    coverage.push_message = message
    
    db.session.commit()
    
    flash(f'Coverage request sent to {notifications_sent} qualified employees!', 'success')
    return redirect(url_for('coverage_needs'))

@app.route('/api/coverage-notifications')
@login_required
def get_coverage_notifications():
    """Get coverage notifications for current user"""
    notifications = CoverageNotification.query.filter_by(
        sent_to_employee_id=current_user.id,
        read_at=None
    ).order_by(CoverageNotification.sent_at.desc()).all()
    
    return jsonify({
        'notifications': [{
            'id': n.id,
            'message': n.message,
            'sent_at': n.sent_at.strftime('%Y-%m-%d %H:%M'),
            'coverage_id': n.coverage_request_id
        } for n in notifications]
    })

@app.route('/coverage/respond/<int:notification_id>', methods=['POST'])
@login_required
def respond_to_coverage(notification_id):
    """Respond to a coverage notification"""
    notification = CoverageNotification.query.get_or_404(notification_id)
    
    if notification.sent_to_employee_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    response = request.form.get('response')  # 'accept' or 'decline'
    
    notification.read_at = datetime.now()
    notification.responded_at = datetime.now()
    notification.response = response
    
    if response == 'accept':
        # Assign the coverage
        coverage = notification.coverage_request
        coverage.filled_by_id = current_user.id
        coverage.filled_at = datetime.now()
        coverage.status = 'filled'
        
        # Create schedule entry
        original_schedule = coverage.schedule
        new_schedule = Schedule(
            employee_id=current_user.id,
            date=original_schedule.date,
            shift_type=original_schedule.shift_type,
            start_time=original_schedule.start_time,
            end_time=original_schedule.end_time,
            position_id=original_schedule.position_id,
            hours=original_schedule.hours,
            is_overtime=True,  # Coverage is usually overtime
            crew=current_user.crew
        )
        db.session.add(new_schedule)
        
        flash('You have accepted the coverage shift!', 'success')
    else:
        flash('You have declined the coverage request.', 'info')
    
    db.session.commit()
    return redirect(url_for('employee_dashboard'))

# ==================== EXCEL IMPORT ROUTES ====================

@app.route('/import-employees', methods=['GET', 'POST'])
@login_required
def import_employees():
    """Import employees from Excel file"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            
            try:
                # Read Excel file
                df = pd.read_excel(file)
                
                # Expected columns: Name, Email, Phone, Hire Date, Crew, Position, Skills
                required_columns = ['Name', 'Email', 'Phone']
                
                if not all(col in df.columns for col in required_columns):
                    flash(f'Excel file must contain columns: {", ".join(required_columns)}', 'danger')
                    return redirect(request.url)
                
                imported_count = 0
                errors = []
                
                for idx, row in df.iterrows():
                    try:
                        # Check if employee already exists
                        existing = Employee.query.filter_by(email=row['Email']).first()
                        if existing:
                            errors.append(f"Row {idx+2}: Employee {row['Email']} already exists")
                            continue
                        
                        # Create new employee
                        employee = Employee(
                            name=row['Name'],
                            email=row['Email'],
                            phone=str(row.get('Phone', '')),
                            hire_date=pd.to_datetime(row.get('Hire Date', date.today())).date() if pd.notna(row.get('Hire Date')) else date.today(),
                            crew=str(row.get('Crew', 'A'))[:1],  # Ensure single character
                            is_supervisor=False,
                            vacation_days=10,
                            sick_days=5,
                            personal_days=3
                        )
                        
                        # Set default password
                        employee.set_password('password123')
                        
                        # Handle position
                        if 'Position' in row and pd.notna(row['Position']):
                            position = Position.query.filter_by(name=row['Position']).first()
                            if position:
                                employee.position_id = position.id
                        
                        # Handle skills (comma-separated)
                        if 'Skills' in row and pd.notna(row['Skills']):
                            skill_names = [s.strip() for s in str(row['Skills']).split(',')]
                            for skill_name in skill_names:
                                skill = Skill.query.filter_by(name=skill_name).first()
                                if not skill:
                                    # Create new skill if it doesn't exist
                                    skill = Skill(name=skill_name, category='General')
                                    db.session.add(skill)
                                employee.skills.append(skill)
                        
                        db.session.add(employee)
                        imported_count += 1
                        
                    except Exception as e:
                        errors.append(f"Row {idx+2}: {str(e)}")
                
                db.session.commit()
                
                flash(f'Successfully imported {imported_count} employees!', 'success')
                if errors:
                    flash(f'Errors encountered: {"; ".join(errors[:5])}{"..." if len(errors) > 5 else ""}', 'warning')
                
                return redirect(url_for('dashboard'))
                
            except Exception as e:
                flash(f'Error reading file: {str(e)}', 'danger')
                return redirect(request.url)
    
    # GET request - show upload form
    return render_template('import_employees.html')

@app.route('/export-template')
@login_required
def export_template():
    """Download Excel template for employee import"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Create template DataFrame
    template_data = {
        'Name': ['John Doe', 'Jane Smith'],
        'Email': ['john.doe@example.com', 'jane.smith@example.com'],
        'Phone': ['555-0123', '555-0124'],
        'Hire Date': [date.today(), date.today()],
        'Crew': ['A', 'B'],
        'Position': ['Nurse', 'Security Officer'],
        'Skills': ['CPR Certified, Emergency Response', 'Security, First Aid']
    }
    
    df = pd.DataFrame(template_data)
    
    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Employees', index=False)
        
        # Add instructions sheet
        instructions = pd.DataFrame({
            'Instructions': [
                'Fill in employee data in the Employees sheet',
                'Required fields: Name, Email, Phone',
                'Optional fields: Hire Date, Crew (A/B/C/D), Position, Skills',
                'Skills should be comma-separated',
                'All employees will be created with password: password123',
                'Employees will need to change their password on first login'
            ]
        })
        instructions.to_excel(writer, sheet_name='Instructions', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='employee_import_template.xlsx'
    )

# ==================== OVERTIME DISTRIBUTION ROUTES ====================

@app.route('/supervisor/overtime-distribution')
@login_required
def overtime_distribution():
    """Smart overtime distribution interface"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Get upcoming overtime opportunities
    overtime_opportunities = get_overtime_opportunities()
    
    # Get eligible employees for overtime
    eligible_employees = get_overtime_eligible_employees()
    
    return render_template('overtime_distribution.html',
                         opportunities=overtime_opportunities,
                         eligible_employees=eligible_employees)

@app.route('/overtime/assign', methods=['POST'])
@login_required
def assign_overtime():
    """Assign overtime to qualified employees"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    opportunity_id = request.form.get('opportunity_id')
    employee_ids = request.form.getlist('employee_ids')
    
    # Parse opportunity ID to get date and shift type
    parts = opportunity_id.split('_')
    opp_date = datetime.strptime(parts[0], '%Y-%m-%d').date()
    shift_type = parts[1]
    
    opportunity = {
        'date': opp_date,
        'shift_type': shift_type,
        'hours': 12,
        'start_time': datetime.strptime('07:00', '%H:%M').time() if shift_type == 'day' else datetime.strptime('19:00', '%H:%M').time(),
        'end_time': datetime.strptime('19:00', '%H:%M').time() if shift_type == 'day' else datetime.strptime('07:00', '%H:%M').time()
    }
    
    assignments_made = 0
    
    for emp_id in employee_ids:
        employee = Employee.query.get(emp_id)
        
        # Verify employee is eligible
        if not is_eligible_for_overtime(employee, opportunity):
            continue
        
        # Create overtime schedule
        schedule = Schedule(
            employee_id=employee.id,
            date=opportunity['date'],
            shift_type=opportunity['shift_type'],
            start_time=opportunity['start_time'],
            end_time=opportunity['end_time'],
            position_id=employee.position_id,
            hours=opportunity['hours'],
            is_overtime=True,
            crew=employee.crew
        )
        db.session.add(schedule)
        assignments_made += 1
    
    db.session.commit()
    
    flash(f'Overtime assigned to {assignments_made} employees!', 'success')
    return redirect(url_for('overtime_distribution'))

# ==================== ENHANCED SHIFT SWAP ROUTES ====================

@app.route('/employee/swap-request', methods=['POST'])
@login_required
def create_swap_request():
    """Create a shift swap request"""
    schedule_id = request.form.get('schedule_id')
    reason = request.form.get('reason', '')
    
    schedule = Schedule.query.get_or_404(schedule_id)
    
    if schedule.employee_id != current_user.id:
        flash('You can only request swaps for your own shifts.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Create swap request
    swap_request = ShiftSwapRequest(
        requester_id=current_user.id,
        original_schedule_id=schedule_id,
        reason=reason,
        status='pending'
    )
    
    db.session.add(swap_request)
    db.session.commit()
    
    flash('Shift swap request submitted! Both supervisors will need to approve.', 'success')
    return redirect(url_for('employee_dashboard'))

@app.route('/supervisor/swap-requests')
@login_required
def swap_requests():
    """View and manage shift swap requests"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Get pending swap requests that need this supervisor's approval
    pending_swaps = ShiftSwapRequest.query.filter(
        ShiftSwapRequest.status == 'pending'
    ).all()
    
    # Filter to show only relevant swaps for this supervisor
    relevant_swaps = []
    for swap in pending_swaps:
        requester = Employee.query.get(swap.requester_id)
        target = Employee.query.get(swap.target_employee_id) if swap.target_employee_id else None
        
        # Check if this supervisor oversees either employee
        if requester.crew == current_user.crew or (target and target.crew == current_user.crew):
            relevant_swaps.append(swap)
    
    recent_swaps = ShiftSwapRequest.query.filter(
        ShiftSwapRequest.status.in_(['approved', 'denied'])
    ).order_by(ShiftSwapRequest.created_at.desc()).limit(10).all()
    
    return render_template('swap_requests.html',
                         pending_swaps=relevant_swaps,
                         recent_swaps=recent_swaps)

@app.route('/swap-request/<int:swap_id>/<action>', methods=['POST'])
@login_required
def handle_swap_request(swap_id, action):
    """Handle swap request with dual supervisor approval"""
    if not current_user.is_supervisor:
        flash('Access denied.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    swap = ShiftSwapRequest.query.get_or_404(swap_id)
    
    # Determine which approval this supervisor is giving
    requester = Employee.query.get(swap.requester_id)
    target = Employee.query.get(swap.target_employee_id) if swap.target_employee_id else None
    
    is_requester_supervisor = requester.crew == current_user.crew
    is_target_supervisor = target and target.crew == current_user.crew
    
    if action == 'approve':
        if is_requester_supervisor and not swap.requester_supervisor_approved:
            swap.requester_supervisor_approved = True
            swap.requester_supervisor_id = current_user.id
            swap.requester_supervisor_date = datetime.now()
            flash('Approved for requester!', 'success')
        
        if is_target_supervisor and not swap.target_supervisor_approved:
            swap.target_supervisor_approved = True
            swap.target_supervisor_id = current_user.id
            swap.target_supervisor_date = datetime.now()
            flash('Approved for target employee!', 'success')
        
        # Check if both supervisors have approved
        if swap.requester_supervisor_approved and (not target or swap.target_supervisor_approved):
            # Execute the swap
            original_schedule = Schedule.query.get(swap.original_schedule_id)
            
            if swap.target_schedule_id:
                target_schedule = Schedule.query.get(swap.target_schedule_id)
                # Swap employee assignments
                original_employee_id = original_schedule.employee_id
                original_schedule.employee_id = target_schedule.employee_id
                target_schedule.employee_id = original_employee_id
            
            swap.status = 'approved'
            flash('Shift swap fully approved and executed!', 'success')
    
    elif action == 'deny':
        swap.status = 'denied'
        if is_requester_supervisor:
            swap.requester_supervisor_approved = False
            swap.requester_supervisor_id = current_user.id
            swap.requester_supervisor_date = datetime.now()
        if is_target_supervisor:
            swap.target_supervisor_approved = False
            swap.target_supervisor_id = current_user.id
            swap.target_supervisor_date = datetime.now()
        
        flash('Shift swap denied.', 'info')
    
    db.session.commit()
    return redirect(url_for('swap_requests'))

# ==================== SCHEDULE MANAGEMENT ROUTES ====================

def create_standard_schedule(start_date, end_date, shift_pattern):
    """Create standard schedule patterns"""
    if shift_pattern == 'standard':
        # Standard 5-day work week
        shift_type = 'day'
        start_hour = 9
        end_hour = 17
        work_days = [0, 1, 2, 3, 4]  # Monday to Friday
    elif shift_pattern == '2_shift':
        # 2-shift pattern
        shift_type = 'day'  # Will alternate
        start_hour = 6
        end_hour = 14
        work_days = [0, 1, 2, 3, 4]
    elif shift_pattern == '3_shift':
        # 3-shift pattern
        shift_type = 'day'  # Will rotate
        start_hour = 6
        end_hour = 14
        work_days = [0, 1, 2, 3, 4]
    else:
        flash('Invalid shift pattern selected.', 'danger')
        return redirect(url_for('create_schedule'))
    
    # Get all non-supervisor employees
    employees = Employee.query.filter_by(is_supervisor=False).all()
    
    if not employees:
        flash('No employees found. Please add employees first.', 'warning')
        return redirect(url_for('create_schedule'))
    
    schedules_created = 0
    current_date = start_date
    
    while current_date <= end_date:
        # Skip weekends for standard pattern
        if shift_pattern == 'standard' and current_date.weekday() not in work_days:
            current_date += timedelta(days=1)
            continue
        
        # Create schedules for applicable employees
        for i, employee in enumerate(employees):
            # For 2-shift pattern, alternate between day and evening
            if shift_pattern == '2_shift':
                if i % 2 == 0:
                    shift_type = 'day'
                    start_hour = 6
                    end_hour = 14
                else:
                    shift_type = 'evening'
                    start_hour = 14
                    end_hour = 22
            
            # For 3-shift pattern, rotate through shifts
            elif shift_pattern == '3_shift':
                shift_num = i % 3
                if shift_num == 0:
                    shift_type = 'day'
                    start_hour = 6
                    end_hour = 14
                elif shift_num == 1:
                    shift_type = 'evening'
                    start_hour = 14
                    end_hour = 22
                else:
                    shift_type = 'night'
                    start_hour = 22
                    end_hour = 6
            
            # Check for time off
            has_time_off = VacationCalendar.query.filter_by(
                employee_id=employee.id,
                date=current_date.date()
            ).first()
            
            if not has_time_off and current_date.weekday() in work_days:
                schedule = create_shift(
                    employee, 
                    current_date, 
                    shift_type, 
                    start_hour, 
                    end_hour, 
                    employee.crew or 'U'
                )
                db.session.add(schedule)
                schedules_created += 1
        
        current_date += timedelta(days=1)
    
    db.session.commit()
    flash(f'Successfully created {schedules_created} schedules!', 'success')
    return redirect(url_for('view_schedules', 
                          start_date=start_date.strftime('%Y-%m-%d'),
                          end_date=end_date.strftime('%Y-%m-%d')))

@app.route('/schedule/create', methods=['GET', 'POST'])
@login_required
def create_schedule():
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    if request.method == 'POST':
        schedule_type = request.form.get('schedule_type')
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
        
        if schedule_type == '4_crew_rotation':
            rotation_pattern = request.form.get('rotation_pattern')
            rotation_type = request.form.get('rotation_type', 'rotating')
            
            # Route to appropriate creation function based on pattern
            if rotation_pattern == 'pitman':
                return create_pitman_schedule(start_date, end_date, request.form)
            elif rotation_pattern == 'southern_swing':
                return create_southern_swing_schedule(start_date, end_date)
            elif rotation_pattern == 'fixed_fixed':
                return create_fixed_fixed_schedule(start_date, end_date, request.form)
            elif rotation_pattern == 'dupont':
                return create_dupont_schedule(start_date, end_date)
            elif rotation_pattern == 'five_and_two':
                return create_five_and_two_schedule(start_date, end_date)
            elif rotation_pattern == 'four_on_four_off':
                return create_four_on_four_off_schedule(start_date, end_date, request.form)
            elif rotation_pattern == 'three_on_three_off':
                return create_three_on_three_off_schedule(start_date, end_date, request.form)
            elif rotation_pattern == 'alternating_fixed':
                return create_alternating_fixed_schedule(start_date, end_date, request.form)
            else:
                flash('Invalid rotation pattern selected.', 'danger')
                return redirect(url_for('create_schedule'))
        else:
            # Standard schedule creation
            shift_pattern = request.form.get('shift_pattern')
            return create_standard_schedule(start_date, end_date, shift_pattern)
    
    employees = Employee.query.filter_by(is_supervisor=False).all()
    positions = Position.query.all()
    
    # Group employees by crew for display
    employees_by_crew = {}
    for emp in employees:
        crew = emp.crew or 'Unassigned'
        if crew not in employees_by_crew:
            employees_by_crew[crew] = []
        employees_by_crew[crew].append(emp)
    
    # Calculate employees near overtime
    week_start = date.today() - timedelta(days=date.today().weekday())
    week_end = week_start + timedelta(days=6)
    
    employees_near_overtime = []
    for emp in employees:
        current_hours = db.session.query(func.sum(Schedule.hours)).filter(
            Schedule.employee_id == emp.id,
            Schedule.date >= week_start,
            Schedule.date <= week_end
        ).scalar() or 0
        
        if current_hours >= 35:  # Near overtime threshold
            emp.current_hours = current_hours
            employees_near_overtime.append(emp)
    
    return render_template('schedule_input.html',
                         employees=employees,
                         positions=positions,
                         employees_by_crew=employees_by_crew,
                         employees_near_overtime=employees_near_overtime)

def get_crews():
    """Get employees organized by crew"""
    crews = {'A': [], 'B': [], 'C': [], 'D': []}
    
    for crew in crews:
        crews[crew] = Employee.query.filter_by(crew=crew, is_supervisor=False).all()
    
    # Check if we have employees in all crews
    empty_crews = [crew for crew, employees in crews.items() if not employees]
    if empty_crews:
        flash(f'No employees assigned to crew(s): {", ".join(empty_crews)}. Please assign employees to crews first.', 'danger')
        return None
    
    return crews

def create_pitman_schedule(start_date, end_date, form_data):
    """Create Pitman (2-2-3) schedule with variations"""
    crews = get_crews()
    if not crews:
        return redirect(url_for('create_schedule'))
    
    variation = form_data.get('pitman_variation', 'fixed')
    
    # Base Pitman pattern (2-2-3)
    # Starting on Sunday minimizes overtime
    base_pattern = {
        'A': [1, 1, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0],  # Week 1: Sun-Mon on, Tue-Wed off, Thu-Sat on; Week 2: Sun-Mon on, Tue-Fri off
        'B': [0, 0, 1, 1, 0, 0, 0, 1, 1, 0, 0, 1, 1, 1],  # Opposite of A
        'C': [0, 0, 1, 1, 0, 0, 0, 1, 1, 0, 0, 1, 1, 1],  # Same as B for nights
        'D': [1, 1, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0],  # Same as A for nights
    }
    
    if variation == 'fixed':
        # Fixed shifts - allow different patterns for day/night if specified
        day_pattern_type = form_data.get('day_crews_pattern', 'pitman')
        night_pattern_type = form_data.get('night_crews_pattern', 'pitman')
        
        # For now, we'll use Pitman for both, but this structure allows expansion
        shift_assignments = {
            'A': ('day', 7, 19), 'B': ('day', 7, 19),
            'C': ('night', 19, 7), 'D': ('night', 19, 7)
        }
        return create_pattern_schedule(start_date, end_date, crews, base_pattern, shift_assignments, 14)
    
    elif variation == 'rapid':
        # Rapid rotation - change shifts after every break
        # This requires a 4-week cycle
        rapid_pattern = {}
        rapid_assignments = {}
        
        # Week 1-2: A&B days, C&D nights
        # Week 3-4: A&B nights, C&D days
        for week in range(4):
            week_offset = week * 14
            for day in range(14):
                for crew in ['A', 'B', 'C', 'D']:
                    if week < 2:
                        # First 2 weeks: A&B days, C&D nights
                        rapid_assignments[crew] = ('day', 7, 19) if crew in ['A', 'B'] else ('night', 19, 7)
                    else:
                        # Last 2 weeks: A&B nights, C&D days
                        rapid_assignments[crew] = ('night', 19, 7) if crew in ['A', 'B'] else ('day', 7, 19)
        
        # Use base pattern but with changing shifts
        return create_pattern_schedule_rotating(start_date, end_date, crews, base_pattern, rapid_assignments, 28, 'rapid')
    
    elif variation in ['2_week', '4_week']:
        # Standard rotation - crews work same shift for 2 or 4 weeks then rotate
        weeks = 2 if variation == '2_week' else 4
        cycle_days = weeks * 2 * 7  # Full cycle is double the rotation period
        
        shift_assignments = {
            'A': ('day', 7, 19), 'B': ('day', 7, 19),
            'C': ('night', 19, 7), 'D': ('night', 19, 7)
        }
        
        return create_pattern_schedule_rotating(start_date, end_date, crews, base_pattern, shift_assignments, cycle_days, variation)

def create_southern_swing_schedule(start_date, end_date):
    """Create Southern Swing schedule (8-hour shifts, 4-week rotation)"""
    crews = get_crews()
    if not crews:
        return redirect(url_for('create_schedule'))
    
    # Southern Swing is a 4-week cycle rotating through all 3 shifts
    # Week 1: Mon-Fri days, weekend off
    # Week 2: Mon-Tue off, Wed-Sun evenings  
    # Week 3: Mon-Tue evenings, Wed off, Thu-Sun nights
    # Week 4: Mon-Wed nights, Thu-Fri off, Sat-Sun days
    
    # 28-day pattern for each crew (4 weeks x 7 days)
    # 1 = work, 0 = off
    southern_pattern = {
        'A': [
            # Week 1 (Days): Mon-Fri on, Sat-Sun off
            0, 1, 1, 1, 1, 1, 0,
            # Week 2 (Evenings): Mon-Tue off, Wed-Sun on
            0, 0, 1, 1, 1, 1, 1,
            # Week 3 (Nights transition): Mon-Tue eve, Wed off, Thu-Sun nights
            1, 1, 0, 1, 1, 1, 1,
            # Week 4 (Back to days): Mon-Wed nights, Thu-Fri off, Sat-Sun days
            1, 1, 1, 0, 0, 1, 1
        ]
    }
    
    # Other crews start at different points in the cycle
    southern_pattern['B'] = southern_pattern['A'][7:] + southern_pattern['A'][:7]
    southern_pattern['C'] = southern_pattern['A'][14:] + southern_pattern['A'][:14]
    southern_pattern['D'] = southern_pattern['A'][21:] + southern_pattern['A'][:21]
    
    # Create schedules
    current_date = start_date
    schedules_created = 0
    
    while current_date <= end_date:
        day_in_cycle = (current_date - start_date).days % 28
        week_in_cycle = day_in_cycle // 7
        
        for crew_name, crew_employees in crews.items():
            if southern_pattern[crew_name][day_in_cycle] == 1:
                # Determine shift type based on week and crew offset
                crew_week = (week_in_cycle + {'A': 0, 'B': 1, 'C': 2, 'D': 3}[crew_name]) % 4
                
                if crew_week == 0:
                    shift_type, start_hour, end_hour = 'day', 7, 15
                elif crew_week == 1:
                    shift_type, start_hour, end_hour = 'evening', 15, 23
                elif crew_week == 2:
                    # Transition week - first part evening, later nights
                    if day_in_cycle % 7 < 2:  # Mon-Tue
                        shift_type, start_hour, end_hour = 'evening', 15, 23
                    else:  # Thu-Sun (Wed is off)
                        shift_type, start_hour, end_hour = 'night', 23, 7
                else:  # crew_week == 3
                    # Transition week - first part nights, later days
                    if day_in_cycle % 7 < 3:  # Mon-Wed
                        shift_type, start_hour, end_hour = 'night', 23, 7
                    else:  # Sat-Sun (Thu-Fri off)
                        shift_type, start_hour, end_hour = 'day', 7, 15
                
                for employee in crew_employees:
                    # Check for time off
                    has_time_off = VacationCalendar.query.filter_by(
                        employee_id=employee.id,
                        date=current_date.date()
                    ).first()
                    
                    if not has_time_off:
                        schedule = create_shift(employee, current_date, shift_type, start_hour, end_hour, crew_name)
                        db.session.add(schedule)
                        schedules_created += 1
        
        current_date += timedelta(days=1)
    
    db.session.commit()
    flash(f'Successfully created {schedules_created} schedules using Southern Swing pattern!', 'success')
    return redirect(url_for('view_schedules'))

def create_fixed_fixed_schedule(start_date, end_date, form_data):
    """Create Fixed-Fixed schedule (Mon-Thu vs Fri-Sun crews)"""
    crews = get_crews()
    if not crews:
        return redirect(url_for('create_schedule'))
    
    shift_hours = int(form_data.get('fixed_fixed_hours', '12'))
    
    # Fixed assignments:
    # Crews A & B: Monday-Thursday (4 days)
    # Crews C & D: Friday-Sunday (3 days)
    
    current_date = start_date
    schedules_created = 0
    
    while current_date <= end_date:
        weekday = current_date.weekday()  # 0=Monday, 6=Sunday
        
        # Determine which crews work today
        if weekday < 4:  # Monday-Thursday
            working_crews = ['A', 'B']
        elif weekday >= 4:  # Friday-Sunday
            working_crews = ['C', 'D']
        else:
            working_crews = []
        
        # Assign shifts
        for crew_name in working_crews:
            # Determine if day or night crew (A&C = days, B&D = nights)
            if crew_name in ['A', 'C']:
                shift_type = 'day'
                start_hour = 6 if shift_hours == 12 else 7
                end_hour = start_hour + shift_hours
            else:  # B, D
                shift_type = 'night'
                start_hour = 18 if shift_hours == 12 else 19
                end_hour = start_hour + shift_hours
            
            for employee in crews[crew_name]:
                # Check for time off
                has_time_off = VacationCalendar.query.filter_by(
                    employee_id=employee.id,
                    date=current_date.date()
                ).first()
                
                if not has_time_off:
                    schedule = create_shift(employee, current_date, shift_type, start_hour, end_hour, crew_name)
                    db.session.add(schedule)
                    schedules_created += 1
        
        current_date += timedelta(days=1)
    
    db.session.commit()
    flash(f'Successfully created {schedules_created} schedules using Fixed-Fixed pattern!', 'success')
    return redirect(url_for('view_schedules'))

def create_dupont_schedule(start_date, end_date):
    """Create DuPont schedule (complex 4-week cycle with 7 consecutive days off)"""
    crews = get_crews()
    if not crews:
        return redirect(url_for('create_schedule'))
    
    # DuPont pattern - 4 week cycle (28 days)
    # Each crew gets 7 consecutive days off
    # Pattern: 4 nights, 3 off, 3 days, 1 off, 3 nights, 1 off, 3 days, 7 off
    dupont_pattern = {
        'A': [
            # Week 1: 4 nights on, 3 off
            1, 1, 1, 1, 0, 0, 0,
            # Week 2: 3 days on, 1 off, 3 nights on
            1, 1, 1, 0, 1, 1, 1,
            # Week 3: 1 off, 3 days on, 3 off
            0, 1, 1, 1, 0, 0, 0,
            # Week 4: 7 off
            0, 0, 0, 0, 0, 0, 0
        ]
    }
    
    # Shift types for each day (N=night, D=day)
    dupont_shifts = {
        'A': [
            # Week 1: nights
            'N', 'N', 'N', 'N', '', '', '',
            # Week 2: days then nights
            'D', 'D', 'D', '', 'N', 'N', 'N',
            # Week 3: days
            '', 'D', 'D', 'D', '', '', '',
            # Week 4: off
            '', '', '', '', '', '', ''
        ]
    }
    
    # Other crews are offset by 1 week each
    for i, crew in enumerate(['B', 'C', 'D']):
        offset = (i + 1) * 7
        dupont_pattern[crew] = dupont_pattern['A'][offset:] + dupont_pattern['A'][:offset]
        dupont_shifts[crew] = dupont_shifts['A'][offset:] + dupont_shifts['A'][:offset]
    
    # Create schedules
    current_date = start_date
    schedules_created = 0
    
    while current_date <= end_date:
        day_in_cycle = (current_date - start_date).days % 28
        
        for crew_name, crew_employees in crews.items():
            if dupont_pattern[crew_name][day_in_cycle] == 1:
                shift_code = dupont_shifts[crew_name][day_in_cycle]
                
                if shift_code == 'D':
                    shift_type, start_hour, end_hour = 'day', 7, 19
                elif shift_code == 'N':
                    shift_type, start_hour, end_hour = 'night', 19, 7
                else:
                    continue
                
                for employee in crew_employees:
                    # Check for time off
                    has_time_off = VacationCalendar.query.filter_by(
                        employee_id=employee.id,
                        date=current_date.date()
                    ).first()
                    
                    if not has_time_off:
                        schedule = create_shift(employee, current_date, shift_type, start_hour, end_hour, crew_name)
                        db.session.add(schedule)
                        schedules_created += 1
        
        current_date += timedelta(days=1)
    
    db.session.commit()
    flash(f'Successfully created {schedules_created} schedules using DuPont pattern!', 'success')
    return redirect(url_for('view_schedules'))

def create_five_and_two_schedule(start_date, end_date):
    """Create 5&2 schedule (complex pattern with 5 on, 2 off variations)"""
    crews = get_crews()
    if not crews:
        return redirect(url_for('create_schedule'))
    
    # 5&2 has 4 different 2-week patterns
    # Pattern 1 (Crew A - Days): 5 on, 2 off, 5 on, 2 off
    # Pattern 2 (Crew B - Days): 2 off, 5 on, 2 off, 5 on  
    # Pattern 3 (Crew C - Nights): 5 on, 2 off, 5 on, 2 off
    # Pattern 4 (Crew D - Nights): 2 off, 5 on, 2 off, 5 on
    
    five_two_pattern = {
        'A': [1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 0, 0],  # 5 on, 2 off pattern
        'B': [0, 0, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1],  # Offset by 2 days
        'C': [1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 0, 0],  # Same as A but nights
        'D': [0, 0, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1],  # Same as B but nights
    }
    
    shift_assignments = {
        'A': ('day', 7, 19), 'B': ('day', 7, 19),
        'C': ('night', 19, 7), 'D': ('night', 19, 7)
    }
    
    return create_pattern_schedule(start_date, end_date, crews, five_two_pattern, shift_assignments, 14)

def create_four_on_four_off_schedule(start_date, end_date, form_data):
    """Create 4-on-4-off schedule with variations"""
    crews = get_crews()
    if not crews:
        return redirect(url_for('create_schedule'))
    
    variation = form_data.get('four_variation', 'basic')
    shift_type_option = form_data.get('four_shift_type', 'fixed')
    
    if variation == 'basic':
        # Basic 4-on-4-off pattern
        pattern = {
            'A': [1, 1, 1, 1, 0, 0, 0, 0],
            'B': [0, 0, 0, 0, 1, 1, 1, 1],
            'C': [1, 1, 1, 1, 0, 0, 0, 0],
            'D': [0, 0, 0, 0, 1, 1, 1, 1],
        }
        cycle_days = 8
        
    elif variation == 'split':
        # Split shift (2D-2N) - 2 days, 24hr break, 2 nights, 4 off
        # This requires special handling
        return create_split_four_schedule(start_date, end_date, crews)
        
    elif variation == 'modified':
        # Modified for full weekends - irregular pattern
        # 16-day cycle to align weekends
        pattern = {
            'A': [1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0],
            'B': [0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 1, 1],
            'C': [0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1],
            'D': [1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 1, 1, 0, 0],
        }
        cycle_days = 16
    
    if shift_type_option == 'fixed':
        shift_assignments = {
            'A': ('day', 7, 19), 'B': ('day', 7, 19),
            'C': ('night', 19, 7), 'D': ('night', 19, 7)
        }
    else:
        # Rotating - will need to implement rotation logic
        shift_assignments = {
            'A': ('day', 7, 19), 'B': ('day', 7, 19),
            'C': ('night', 19, 7), 'D': ('night', 19, 7)
        }
    
    return create_pattern_schedule(start_date, end_date, crews, pattern, shift_assignments, cycle_days)

def create_split_four_schedule(start_date, end_date, crews):
    """Create split 4-on-4-off (2D-2N) schedule"""
    # Special pattern: 2 days, 24hr off, 2 nights, 4 days off
    # 8-day cycle but with mid-cycle break
    
    current_date = start_date
    schedules_created = 0
    
    while current_date <= end_date:
        for crew_name, crew_employees in crews.items():
            # Calculate position in 8-day cycle
            crew_offset = {'A': 0, 'B': 4, 'C': 0, 'D': 4}[crew_name]
            day_in_cycle = ((current_date - start_date).days + crew_offset) % 8
            
            # Determine if working and what shift
            if day_in_cycle in [0, 1]:  # First 2 days
                shift_type, start_hour, end_hour = 'day', 7, 19
            elif day_in_cycle == 2:  # 24-hour break
                continue
            elif day_in_cycle in [3, 4]:  # 2 nights
                shift_type, start_hour, end_hour = 'night', 19, 7
            else:  # days 5-7 off
                continue
            
            for employee in crew_employees:
                # Check for time off
                has_time_off = VacationCalendar.query.filter_by(
                    employee_id=employee.id,
                    date=current_date.date()
                ).first()
                
                if not has_time_off:
                    schedule = create_shift(employee, current_date, shift_type, start_hour, end_hour, crew_name)
                    db.session.add(schedule)
                    schedules_created += 1
        
        current_date += timedelta(days=1)
    
    db.session.commit()
    flash(f'Successfully created {schedules_created} schedules using Split 4-on-4-off (2D-2N) pattern!', 'success')
    return redirect(url_for('view_schedules'))

def create_three_on_three_off_schedule(start_date, end_date, form_data):
    """Create 3-on-3-off schedule with variations"""
    crews = get_crews()
    if not crews:
        return redirect(url_for('create_schedule'))
    
    variation = form_data.get('three_variation', 'basic')
    shift_type_option = form_data.get('three_shift_type', 'fixed')
    
    if variation == 'basic':
        # Basic 3-on-3-off pattern - 6 day cycle
        pattern = {
            'A': [1, 1, 1, 0, 0, 0],
            'B': [0, 0, 0, 1, 1, 1],
            'C': [1, 1, 1, 0, 0, 0],
            'D': [0, 0, 0, 1, 1, 1],
        }
        cycle_days = 6
        
    else:  # modified for full weekends
        # Modified pattern - 12 day cycle to align weekends better
        pattern = {
            'A': [1, 1, 0, 0, 1, 1, 1, 0, 0, 0, 1, 1],
            'B': [0, 0, 1, 1, 0, 0, 0, 1, 1, 1, 0, 0],
            'C': [1, 0, 0, 0, 1, 1, 1, 0, 0, 1, 1, 1],
            'D': [0, 1, 1, 1, 0, 0, 0, 1, 1, 0, 0, 0],
        }
        cycle_days = 12
    
    if shift_type_option == 'fixed':
        shift_assignments = {
            'A': ('day', 7, 19), 'B': ('day', 7, 19),
            'C': ('night', 19, 7), 'D': ('night', 19, 7)
        }
    else:
        shift_assignments = {
            'A': ('day', 7, 19), 'B': ('day', 7, 19),
            'C': ('night', 19, 7), 'D': ('night', 19, 7)
        }
    
    return create_pattern_schedule(start_date, end_date, crews, pattern, shift_assignments, cycle_days)

def create_alternating_fixed_schedule(start_date, end_date, form_data):
    """Create Alternating Fixed (3-4-3-4) schedule"""
    crews = get_crews()
    if not crews:
        return redirect(url_for('create_schedule'))
    
    shift_type_option = form_data.get('alt_shift_type', 'fixed')
    
    # Pattern: Each crew works 3 core days + alternating 4th day
    # Crews A & C: Sun-Mon-Tue + alternating Wed
    # Crews B & D: Thu-Fri-Sat + alternating Wed
    # 14-day cycle
    
    pattern = {
        # A works Sun-Mon-Tue + Wed of week 1
        'A': [1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0],
        # B works Thu-Fri-Sat + Wed of week 2  
        'B': [0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1],
        # C works Sun-Mon-Tue + Wed of week 2
        'C': [1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0],
        # D works Thu-Fri-Sat + Wed of week 1
        'D': [0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1],
    }
    
    if shift_type_option == 'fixed':
        shift_assignments = {
            'A': ('day', 7, 19), 'B': ('day', 7, 19),
            'C': ('night', 19, 7), 'D': ('night', 19, 7)
        }
    else:
        # Rotating implementation would go here
        shift_assignments = {
            'A': ('day', 7, 19), 'B': ('day', 7, 19),
            'C': ('night', 19, 7), 'D': ('night', 19, 7)
        }
    
    return create_pattern_schedule(start_date, end_date, crews, pattern, shift_assignments, 14)

# Helper functions for pattern-based schedule creation
# ==================== SCHEDULE WIZARD ROUTES ====================

@app.route('/schedule/select')
@login_required
def schedule_select():
    """Schedule pattern selection page"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    return render_template('schedule_selection.html')

@app.route('/schedule/wizard/<pattern>')
@login_required
def schedule_wizard(pattern):
    """Pattern-specific schedule creation wizard"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Validate pattern
    valid_patterns = ['pitman', 'southern_swing', 'fixed_fixed', 'dupont', 
                      'five_and_two', 'four_on_four_off', 'three_on_three_off', 
                      'alternating_fixed']
    
    if pattern not in valid_patterns:
        flash('Invalid schedule pattern selected.', 'danger')
        return redirect(url_for('schedule_select'))
    
    # Get data for wizard
    employees = Employee.query.filter_by(is_supervisor=False).order_by(Employee.name).all()
    positions = Position.query.order_by(Position.name).all()
    
    # Group employees by current crew
    employees_by_crew = {}
    unassigned_employees = []
    
    for emp in employees:
        if emp.crew:
            if emp.crew not in employees_by_crew:
                employees_by_crew[emp.crew] = []
            employees_by_crew[emp.crew].append(emp)
        else:
            unassigned_employees.append(emp)
    
    # Get crew statistics
    crew_stats = {}
    for crew in ['A', 'B', 'C', 'D']:
        crew_stats[crew] = {
            'count': len(employees_by_crew.get(crew, [])),
            'positions': {}
        }
        # Count positions in each crew
        for emp in employees_by_crew.get(crew, []):
            if emp.position:
                pos_name = emp.position.name
                crew_stats[crew]['positions'][pos_name] = crew_stats[crew]['positions'].get(pos_name, 0) + 1
    
    return render_template('schedule_wizard.html',
                         pattern=pattern,
                         employees=employees,
                         positions=positions,
                         employees_by_crew=employees_by_crew,
                         unassigned_employees=unassigned_employees,
                         crew_stats=crew_stats)

@app.route('/export-crew-template')
@login_required
def export_crew_template():
    """Download Excel template for crew assignments"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Get all employees
    employees = Employee.query.filter_by(is_supervisor=False).order_by(Employee.name).all()
    
    # Create DataFrame
    data = []
    for emp in employees:
        data.append({
            'Employee ID': emp.id,
            'Name': emp.name,
            'Current Position': emp.position.name if emp.position else '',
            'Current Crew': emp.crew or '',
            'New Crew Assignment': emp.crew or '',  # Pre-fill with current crew
            'Notes': ''
        })
    
    df = pd.DataFrame(data)
    
    # Create Excel file
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Write main data
        df.to_excel(writer, sheet_name='Crew Assignments', index=False)
        
        # Add instructions sheet
        instructions_data = {
            'Instructions': [
                'Assign each employee to a crew (A, B, C, or D)',
                'Leave "New Crew Assignment" blank to keep current crew',
                'Use Notes column for any special instructions',
                'Save and upload this file when complete',
                '',
                'IMPORTANT:',
                '- Each crew should have similar numbers of employees',
                '- Balance skills and positions across crews',
                '- Consider employee preferences if known'
            ]
        }
        instructions_df = pd.DataFrame(instructions_data)
        instructions_df.to_excel(writer, sheet_name='Instructions', index=False)
        
        # Get the workbook and format
        workbook = writer.book
        worksheet = writer.sheets['Crew Assignments']
        
        # Auto-adjust column widths
        for column in df:
            column_length = max(df[column].astype(str).map(len).max(), len(column))
            col_idx = df.columns.get_loc(column)
            worksheet.column_dimensions[chr(65 + col_idx)].width = min(column_length + 2, 50)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'crew_assignments_{date.today().strftime("%Y%m%d")}.xlsx'
    )

@app.route('/import-crew-roster', methods=['POST'])
@login_required
def import_crew_roster():
    """Upload completed crew assignments from Excel"""
    if not current_user.is_supervisor:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})
    
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Invalid file type. Please upload an Excel file.'})
    
    try:
        # Read Excel file
        df = pd.read_excel(file, sheet_name='Crew Assignments')
        
        # Validate columns
        required_columns = ['Employee ID', 'New Crew Assignment']
        if not all(col in df.columns for col in required_columns):
            return jsonify({'success': False, 'error': 'Invalid file format. Missing required columns.'})
        
        # Process assignments
        updated_count = 0
        errors = []
        crew_counts = {'A': 0, 'B': 0, 'C': 0, 'D': 0}
        
        for idx, row in df.iterrows():
            try:
                emp_id = int(row['Employee ID'])
                new_crew = str(row['New Crew Assignment']).strip().upper()
                
                # Skip if no new assignment
                if pd.isna(new_crew) or new_crew == '':
                    continue
                
                # Validate crew
                if new_crew not in ['A', 'B', 'C', 'D']:
                    errors.append(f"Row {idx+2}: Invalid crew '{new_crew}'. Must be A, B, C, or D.")
                    continue
                
                # Update employee
                employee = Employee.query.get(emp_id)
                if not employee:
                    errors.append(f"Row {idx+2}: Employee ID {emp_id} not found.")
                    continue
                
                employee.crew = new_crew
                crew_counts[new_crew] += 1
                updated_count += 1
                
            except Exception as e:
                errors.append(f"Row {idx+2}: {str(e)}")
        
        # Commit changes
        db.session.commit()
        
        # Prepare response
        response = {
            'success': True,
            'updated': updated_count,
            'crew_counts': crew_counts,
            'message': f'Successfully updated {updated_count} crew assignments.'
        }
        
        if errors:
            response['warnings'] = errors[:5]  # Limit to first 5 errors
            if len(errors) > 5:
                response['warnings'].append(f'... and {len(errors) - 5} more errors')
        
        return jsonify(response)
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Error processing file: {str(e)}'})

@app.route('/api/crew-status')
@login_required
def get_crew_status():
    """Get current crew assignments and statistics"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    crews = {'A': [], 'B': [], 'C': [], 'D': [], 'Unassigned': []}
    
    employees = Employee.query.filter_by(is_supervisor=False).all()
    
    for emp in employees:
        crew_key = emp.crew if emp.crew else 'Unassigned'
        emp_data = {
            'id': emp.id,
            'name': emp.name,
            'position': emp.position.name if emp.position else 'No position',
            'skills': [s.name for s in emp.skills]
        }
        crews[crew_key].append(emp_data)
    
    # Calculate statistics
    stats = {}
    for crew, members in crews.items():
        if crew != 'Unassigned':
            stats[crew] = {
                'count': len(members),
                'positions': {},
                'skills': {}
            }
            for member in members:
                # Count positions
                pos = member['position']
                stats[crew]['positions'][pos] = stats[crew]['positions'].get(pos, 0) + 1
                # Count skills
                for skill in member['skills']:
                    stats[crew]['skills'][skill] = stats[crew]['skills'].get(skill, 0) + 1
    
    return jsonify({
        'crews': crews,
        'stats': stats,
        'total_employees': len(employees),
        'unassigned_count': len(crews['Unassigned'])
    })

@app.route('/schedule/create-pitman', methods=['POST'])
@login_required
def create_pitman_from_wizard():
    """Create Pitman schedule from wizard data"""
    if not current_user.is_supervisor:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        # Get form data
        data = request.get_json()
        
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d')
        end_date = datetime.strptime(data['end_date'], '%Y-%m-%d')
        variation = data['variation']
        
        # Validate crews are assigned
        crews = get_crews()
        if not crews:
            return jsonify({'success': False, 'error': 'Please assign employees to crews first.'})
        
        # Check crew balance
        crew_sizes = [len(crews[c]) for c in ['A', 'B', 'C', 'D']]
        if max(crew_sizes) - min(crew_sizes) > 2:
            return jsonify({
                'success': False, 
                'error': 'Crew sizes are unbalanced. Please redistribute employees more evenly.'
            })
        
        # Create the schedule using existing function
        # This will handle the redirect internally
        result = create_pitman_schedule(start_date, end_date, {'pitman_variation': variation})
        
        # If we get here without redirect, it was successful
        return jsonify({
            'success': True,
            'message': 'Schedule created successfully!',
            'redirect': url_for('view_schedules', 
                              start_date=start_date.strftime('%Y-%m-%d'),
                              end_date=end_date.strftime('%Y-%m-%d'))
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})
def create_pattern_schedule(start_date, end_date, crews, pattern, shift_assignments, cycle_days):
    """Generic pattern-based schedule creator for fixed shifts"""
    current_date = start_date
    schedules_created = 0
    
    while current_date <= end_date:
        day_in_cycle = (current_date - start_date).days % cycle_days
        
        for crew_name, crew_employees in crews.items():
            if pattern[crew_name][day_in_cycle] == 1:  # Working day
                shift_type, start_hour, end_hour = shift_assignments[crew_name]
                
                for employee in crew_employees:
                    # Check for time off
                    has_time_off = VacationCalendar.query.filter_by(
                        employee_id=employee.id,
                        date=current_date.date()
                    ).first()
                    
                    if not has_time_off:
                        schedule = create_shift(employee, current_date, shift_type, start_hour, end_hour, crew_name)
                        db.session.add(schedule)
                        schedules_created += 1
                        
                        # Update circadian profile
                        update_circadian_profile_on_schedule_change(employee.id, shift_type)
        
        current_date += timedelta(days=1)
    
    db.session.commit()
    flash(f'Successfully created {schedules_created} schedules!', 'success')
    return redirect(url_for('view_schedules'))

def create_pattern_schedule_rotating(start_date, end_date, crews, pattern, base_assignments, cycle_days, rotation_type):
    """Pattern-based schedule creator for rotating shifts"""
    current_date = start_date
    schedules_created = 0
    
    while current_date <= end_date:
        day_in_cycle = (current_date - start_date).days % cycle_days
        
        # Determine current rotation phase
        if rotation_type == 'rapid':
            # Change after each break (complex logic based on pattern)
            phase = determine_rapid_rotation_phase(day_in_cycle, pattern)
        elif rotation_type == '2_week':
            phase = (day_in_cycle // 14) % 2
        elif rotation_type == '4_week':
            phase = (day_in_cycle // 28) % 2
        else:
            phase = 0
        
        for crew_name, crew_employees in crews.items():
            pattern_cycle = len(pattern[crew_name])
            pattern_day = day_in_cycle % pattern_cycle
            
            if pattern[crew_name][pattern_day] == 1:  # Working day
                # Determine shift based on rotation phase
                if phase == 0:
                    shift_type, start_hour, end_hour = base_assignments[crew_name]
                else:
                    # Swap day/night crews
                    if crew_name in ['A', 'B']:
                        shift_type, start_hour, end_hour = ('night', 19, 7)
                    else:
                        shift_type, start_hour, end_hour = ('day', 7, 19)
                
                for employee in crew_employees:
                    # Check for time off
                    has_time_off = VacationCalendar.query.filter_by(
                        employee_id=employee.id,
                        date=current_date.date()
                    ).first()
                    
                    if not has_time_off:
                        schedule = create_shift(employee, current_date, shift_type, start_hour, end_hour, crew_name)
                        db.session.add(schedule)
                        schedules_created += 1
                        
                        # Update circadian profile
                        update_circadian_profile_on_schedule_change(employee.id, shift_type)
        
        current_date += timedelta(days=1)
    
    db.session.commit()
    flash(f'Successfully created {schedules_created} schedules with {rotation_type} rotation!', 'success')
    return redirect(url_for('view_schedules'))

def determine_rapid_rotation_phase(day_in_cycle, pattern):
    """Determine rotation phase for rapid rotation (after each break)"""
    # This is simplified - in reality would need more complex logic
    # based on analyzing the pattern for break periods
    return (day_in_cycle // 7) % 2

def create_shift(employee, date, shift_type, start_hour, end_hour, crew):
    """Create a single shift schedule entry"""
    start_time = date.replace(hour=start_hour, minute=0, second=0)
    end_time = date.replace(hour=end_hour, minute=0, second=0)
    
    # Handle overnight shifts
    if end_hour < start_hour:
        end_time += timedelta(days=1)
    
    # Calculate hours
    hours = (end_time - start_time).total_seconds() / 3600
    
    schedule = Schedule(
        employee_id=employee.id,
        date=date.date(),
        shift_type=shift_type,
        start_time=start_time.time(),
        end_time=end_time.time(),
        position_id=employee.position_id,
        hours=hours,
        crew=crew
    )
    
    return schedule

@app.route('/schedule/view')
@login_required
def view_schedules():
    """View schedules with crew filtering"""
    # Get crew filter
    crew = request.args.get('crew', 'ALL')
    
    # Get date range
    start_date = request.args.get('start_date', date.today())
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    end_date = request.args.get('end_date', start_date + timedelta(days=13))
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Build query
    query = Schedule.query.filter(
        Schedule.date >= start_date,
        Schedule.date <= end_date
    )
    
    if crew != 'ALL':
        query = query.filter(Schedule.crew == crew)
    
    schedules = query.order_by(Schedule.date, Schedule.shift_type, Schedule.start_time).all()
    
    # Get all employees for the schedule grid
    employees_query = Employee.query.filter_by(is_supervisor=False)
    if crew != 'ALL':
        employees_query = employees_query.filter_by(crew=crew)
    employees = employees_query.order_by(Employee.crew, Employee.name).all()
    
    # Create date range
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)
    
    # Create schedule dictionary for easy lookup
    schedule_dict = {}
    for schedule in schedules:
        key = (schedule.employee_id, schedule.date.strftime('%Y-%m-%d'))
        schedule_dict[key] = schedule
    
    # Calculate previous and next dates for navigation
    prev_start = start_date - timedelta(days=14)
    prev_end = end_date - timedelta(days=14)
    next_start = start_date + timedelta(days=14)
    next_end = end_date + timedelta(days=14)
    
    return render_template('crew_schedule.html',
                         employees=employees,
                         dates=dates,
                         schedules=schedule_dict,
                         start_date=start_date,
                         end_date=end_date,
                         selected_crew=crew,
                         prev_start=prev_start.strftime('%Y-%m-%d'),
                         prev_end=prev_end.strftime('%Y-%m-%d'),
                         next_start=next_start.strftime('%Y-%m-%d'),
                         next_end=next_end.strftime('%Y-%m-%d'),
                         today=date.today())
    
@app.route('/supervisor/messages')
@login_required
def supervisor_messages():
    """View and send messages to other supervisors"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Get inbox messages
    inbox = SupervisorMessage.query.filter_by(
        recipient_id=current_user.id,
        archived=False
    ).order_by(SupervisorMessage.sent_at.desc()).all()
    
    # Get sent messages
    sent = SupervisorMessage.query.filter_by(
        sender_id=current_user.id,
        archived=False
    ).order_by(SupervisorMessage.sent_at.desc()).limit(10).all()
    
    # Get other supervisors for new message dropdown
    other_supervisors = Employee.query.filter(
        Employee.is_supervisor == True,
        Employee.id != current_user.id
    ).order_by(Employee.name).all()
    
    # Count unread messages
    unread_count = SupervisorMessage.query.filter_by(
        recipient_id=current_user.id,
        read_at=None
    ).count()
    
    return render_template('supervisor_messages.html',
                         inbox=inbox,
                         sent=sent,
                         other_supervisors=other_supervisors,
                         unread_count=unread_count)

@app.route('/supervisor/messages/send', methods=['POST'])
@login_required
def send_supervisor_message():
    """Send a message to another supervisor"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    recipient_id = request.form.get('recipient_id')
    subject = request.form.get('subject')
    message_text = request.form.get('message')
    priority = request.form.get('priority', 'normal')
    category = request.form.get('category', 'general')
    
    # Validate recipient is a supervisor
    recipient = Employee.query.get_or_404(recipient_id)
    if not recipient.is_supervisor:
        flash('Recipient must be a supervisor.', 'danger')
        return redirect(url_for('supervisor_messages'))
    
    # Create message
    message = SupervisorMessage(
        sender_id=current_user.id,
        recipient_id=recipient_id,
        subject=subject,
        message=message_text,
        priority=priority,
        category=category
    )
    
    db.session.add(message)
    db.session.commit()
    
    flash(f'Message sent to {recipient.name}!', 'success')
    return redirect(url_for('supervisor_messages'))

@app.route('/supervisor/messages/<int:message_id>')
@login_required
def view_supervisor_message(message_id):
    """View a specific supervisor message"""
    message = SupervisorMessage.query.get_or_404(message_id)
    
    # Check authorization
    if not current_user.is_supervisor or (message.recipient_id != current_user.id and message.sender_id != current_user.id):
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Mark as read if recipient
    if message.recipient_id == current_user.id and not message.read_at:
        message.read_at = datetime.now()
        db.session.commit()
    
    # Get thread messages
    thread_messages = []
    if message.parent_message_id:
        # Get parent and all replies
        parent = SupervisorMessage.query.get(message.parent_message_id)
        thread_messages = SupervisorMessage.query.filter_by(
            parent_message_id=parent.id
        ).order_by(SupervisorMessage.sent_at).all()
        thread_messages.insert(0, parent)
    else:
        # This is parent, get all replies
        thread_messages = SupervisorMessage.query.filter_by(
            parent_message_id=message.id
        ).order_by(SupervisorMessage.sent_at).all()
        thread_messages.insert(0, message)
    
    return render_template('view_supervisor_message.html',
                         message=message,
                         thread_messages=thread_messages)

@app.route('/supervisor/messages/<int:message_id>/reply', methods=['POST'])
@login_required
def reply_supervisor_message(message_id):
    """Reply to a supervisor message"""
    original = SupervisorMessage.query.get_or_404(message_id)
    
    # Check authorization
    if not current_user.is_supervisor or (original.recipient_id != current_user.id and original.sender_id != current_user.id):
        return jsonify({'error': 'Unauthorized'}), 403
    
    reply_text = request.form.get('reply')
    
    # Determine recipient (other person in conversation)
    recipient_id = original.sender_id if original.recipient_id == current_user.id else original.recipient_id
    
    # Create reply
    reply = SupervisorMessage(
        sender_id=current_user.id,
        recipient_id=recipient_id,
        subject=f"Re: {original.subject}",
        message=reply_text,
        priority=original.priority,
        category=original.category,
        parent_message_id=original.parent_message_id or original.id
    )
    
    db.session.add(reply)
    db.session.commit()
    
    flash('Reply sent!', 'success')
    return redirect(url_for('view_supervisor_message', message_id=message_id))

@app.route('/position/messages')
@login_required
def position_messages():
    """View messages for employee's position"""
    if not current_user.position_id:
        flash('You must be assigned to a position to view position messages.', 'warning')
        return redirect(url_for('employee_dashboard'))
    
    # Get messages for user's position
    messages_query = PositionMessage.query.filter_by(
        position_id=current_user.position_id
    ).filter(
        or_(
            PositionMessage.expires_at.is_(None),
            PositionMessage.expires_at > datetime.now()
        )
    )
    
    # Filter by shift if specified
    shift_filter = request.args.get('shift', 'all')
    if shift_filter != 'all':
        messages_query = messages_query.filter(
            or_(
                PositionMessage.target_shifts == 'all',
                PositionMessage.target_shifts.contains(shift_filter)
            )
        )
    
    # Get pinned messages first, then others by date
    pinned_messages = messages_query.filter_by(pinned=True).all()
    recent_messages = messages_query.filter_by(pinned=False).order_by(
        PositionMessage.sent_at.desc()
    ).limit(50).all()
    
    # Mark messages as read
    for message in pinned_messages + recent_messages:
        if not message.is_read_by(current_user.id):
            message.mark_read_by(current_user.id)
    
    db.session.commit()
    
    # Get colleagues in same position but different shifts
    colleagues = Employee.query.filter(
        Employee.position_id == current_user.position_id,
        Employee.id != current_user.id,
        Employee.crew != current_user.crew
    ).all()
    
    return render_template('position_messages.html',
                         pinned_messages=pinned_messages,
                         recent_messages=recent_messages,
                         colleagues=colleagues,
                         current_position=current_user.position,
                         shift_filter=shift_filter)

@app.route('/position/messages/send', methods=['POST'])
@login_required
def send_position_message():
    """Send a message to colleagues in same position"""
    if not current_user.position_id:
        return jsonify({'error': 'No position assigned'}), 403
    
    subject = request.form.get('subject')
    message_text = request.form.get('message')
    category = request.form.get('category', 'general')
    target_shifts = request.form.getlist('target_shifts')
    expires_days = request.form.get('expires_days')
    
    # Handle target shifts
    if 'all' in target_shifts or not target_shifts:
        target_shifts_str = 'all'
    else:
        target_shifts_str = ','.join(target_shifts)
    
    # Calculate expiration
    expires_at = None
    if expires_days and expires_days.isdigit():
        expires_at = datetime.now() + timedelta(days=int(expires_days))
    
    # Create message
    message = PositionMessage(
        sender_id=current_user.id,
        position_id=current_user.position_id,
        subject=subject,
        message=message_text,
        category=category,
        target_shifts=target_shifts_str,
        expires_at=expires_at
    )
    
    db.session.add(message)
    db.session.commit()
    
    flash('Message sent to position colleagues!', 'success')
    return redirect(url_for('position_messages'))

@app.route('/position/messages/<int:message_id>')
@login_required
def view_position_message(message_id):
    """View a specific position message and its replies"""
    message = PositionMessage.query.get_or_404(message_id)
    
    # Check authorization
    if current_user.position_id != message.position_id:
        flash('You cannot view messages for other positions.', 'danger')
        return redirect(url_for('position_messages'))
    
    # Mark as read
    if not message.is_read_by(current_user.id):
        message.mark_read_by(current_user.id)
        db.session.commit()
    
    # Get replies
    replies = PositionMessage.query.filter_by(
        parent_message_id=message.id
    ).order_by(PositionMessage.sent_at).all()
    
    return render_template('view_position_message.html',
                         message=message,
                         replies=replies)

@app.route('/position/messages/<int:message_id>/reply', methods=['POST'])
@login_required
def reply_position_message(message_id):
    """Reply to a position message"""
    original = PositionMessage.query.get_or_404(message_id)
    
    # Check authorization
    if current_user.position_id != original.position_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    reply_text = request.form.get('reply')
    
    # Create reply
    reply = PositionMessage(
        sender_id=current_user.id,
        position_id=current_user.position_id,
        subject=f"Re: {original.subject}",
        message=reply_text,
        category=original.category,
        target_shifts=original.target_shifts,
        parent_message_id=original.id
    )
    
    db.session.add(reply)
    db.session.commit()
    
    flash('Reply posted!', 'success')
    return redirect(url_for('view_position_message', message_id=message_id))

@app.route('/maintenance/report', methods=['GET', 'POST'])
@login_required
def report_maintenance():
    """Report a maintenance issue"""
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            description = request.form.get('description')
            location = request.form.get('location')
            category = request.form.get('category', 'general')
            priority = request.form.get('priority', 'normal')
            safety_issue = request.form.get('safety_issue') == 'on'
            
            # Create issue
            issue = MaintenanceIssue(
                reporter_id=current_user.id,
                title=title,
                description=description,
                location=location,
                category=category,
                priority=priority,
                safety_issue=safety_issue,
                status='open',  # Explicitly set status
                reported_at=datetime.now()  # Explicitly set timestamp
            )
            
            # Try to auto-assign to primary maintenance manager if exists
            try:
                primary_manager = MaintenanceManager.query.filter_by(is_primary=True).first()
                if primary_manager:
                    issue.assigned_to_id = primary_manager.employee_id
            except:
                # If MaintenanceManager table doesn't exist or query fails, continue without assignment
                pass
            
            db.session.add(issue)
            db.session.flush()  # Flush to get the issue ID
            
            # Create initial update
            try:
                update = MaintenanceUpdate(
                    issue_id=issue.id,
                    author_id=current_user.id,
                    update_type='comment',
                    message=f"Issue reported: {description}",
                    created_at=datetime.now()  # Explicitly set timestamp
                )
                db.session.add(update)
            except:
                # If update fails, still continue (issue is more important)
                pass
            
            db.session.commit()
            
            flash('Maintenance issue reported successfully!', 'success')
            return redirect(url_for('view_maintenance_issue', issue_id=issue.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error reporting issue: {str(e)}', 'danger')
            app.logger.error(f'Maintenance report error: {str(e)}')
            return redirect(url_for('report_maintenance'))
    
    # GET request - show form
    return render_template('report_maintenance.html')

@app.route('/maintenance/issues')
@login_required
def maintenance_issues():
    """View all maintenance issues (for maintenance managers and employees)"""
    # Check if user is a maintenance manager
    is_manager = False
    try:
        manager_check = MaintenanceManager.query.filter_by(employee_id=current_user.id).first()
        is_manager = manager_check is not None
    except:
        is_manager = False
    
    # Base query
    if is_manager:
        # Managers see all issues
        issues_query = MaintenanceIssue.query
    else:
        # Regular employees see only their reported issues
        issues_query = MaintenanceIssue.query.filter_by(reporter_id=current_user.id)
    
    # Apply filters
    status_filter = request.args.get('status', 'active')
    if status_filter == 'active':
        issues_query = issues_query.filter(
            MaintenanceIssue.status.in_(['open', 'acknowledged', 'in_progress'])
        )
    elif status_filter != 'all':
        issues_query = issues_query.filter_by(status=status_filter)
    
    # Sort by priority and date
    issues = issues_query.order_by(
        case(
            (MaintenanceIssue.priority == 'critical', 1),
            (MaintenanceIssue.priority == 'high', 2),
            (MaintenanceIssue.priority == 'normal', 3),
            (MaintenanceIssue.priority == 'low', 4)
        ),
        MaintenanceIssue.reported_at.desc()
    ).all()
    
    # Get statistics for managers - ensure stats is always defined
    stats = {
        'open': 0,
        'in_progress': 0,
        'resolved': 0,
        'critical': 0
    }
    
    if is_manager:
        try:
            stats['open'] = MaintenanceIssue.query.filter_by(status='open').count()
            stats['in_progress'] = MaintenanceIssue.query.filter_by(status='in_progress').count()
            stats['resolved'] = MaintenanceIssue.query.filter_by(status='resolved').count()
            stats['critical'] = MaintenanceIssue.query.filter_by(priority='critical', status='open').count()
        except:
            # If queries fail, keep default values
            pass
    
    return render_template('maintenance_issues.html',
                         issues=issues,
                         is_manager=is_manager,
                         stats=stats,
                         status_filter=status_filter)

@app.route('/maintenance/issues/<int:issue_id>')
@login_required
def view_maintenance_issue(issue_id):
    """View a specific maintenance issue"""
    issue = MaintenanceIssue.query.get_or_404(issue_id)
    
    # Check authorization
    is_manager = False
    try:
        manager_check = MaintenanceManager.query.filter_by(employee_id=current_user.id).first()
        is_manager = manager_check is not None
    except:
        # If MaintenanceManager table doesn't exist, assume not a manager
        is_manager = False
    
    if not is_manager and issue.reporter_id != current_user.id:
        flash('You can only view issues you reported.', 'danger')
        return redirect(url_for('maintenance_issues'))
    
    # Get updates
    try:
        updates_query = MaintenanceUpdate.query.filter_by(issue_id=issue_id)
        if not is_manager:
            updates_query = updates_query.filter_by(is_internal=False)
        updates = updates_query.order_by(MaintenanceUpdate.created_at).all()
    except:
        updates = []
    
    # Get available maintenance staff for assignment (managers only)
    maintenance_staff = []
    if is_manager:
        try:
            # Get all employees who are maintenance managers
            maintenance_staff = Employee.query.join(
                MaintenanceManager, 
                Employee.id == MaintenanceManager.employee_id
            ).all()
        except:
            maintenance_staff = []
    
    return render_template('view_maintenance_issue.html',
                         issue=issue,
                         updates=updates,
                         is_manager=is_manager,
                         maintenance_staff=maintenance_staff)

@app.route('/maintenance/issues/<int:issue_id>/update', methods=['POST'])
@login_required
def update_maintenance_issue(issue_id):
    """Update a maintenance issue"""
    issue = MaintenanceIssue.query.get_or_404(issue_id)
    
    # Check authorization
    is_manager = MaintenanceManager.query.filter_by(employee_id=current_user.id).first() is not None
    if not is_manager and issue.reporter_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    update_text = request.form.get('update')
    is_internal = request.form.get('is_internal') == 'on'
    
    # Create update
    update = MaintenanceUpdate(
        issue_id=issue.id,
        author_id=current_user.id,
        update_type='comment',
        message=update_text,
        is_internal=is_internal and is_manager
    )
    
    db.session.add(update)
    db.session.commit()
    
    flash('Update added to maintenance issue.', 'success')
    return redirect(url_for('view_maintenance_issue', issue_id=issue_id))

@app.route('/maintenance/issues/<int:issue_id>/status', methods=['POST'])
@login_required
def change_maintenance_status(issue_id):
    """Change the status of a maintenance issue (managers only)"""
    # Check if user is a maintenance manager
    if not MaintenanceManager.query.filter_by(employee_id=current_user.id).first():
        return jsonify({'error': 'Unauthorized'}), 403
    
    issue = MaintenanceIssue.query.get_or_404(issue_id)
    new_status = request.form.get('status')
    resolution = request.form.get('resolution')
    
    # Validate status
    valid_statuses = ['open', 'acknowledged', 'in_progress', 'resolved', 'closed']
    if new_status not in valid_statuses:
        flash('Invalid status.', 'danger')
        return redirect(url_for('view_maintenance_issue', issue_id=issue_id))
    
    # Update timestamps
    old_status = issue.status
    if new_status == 'acknowledged' and not issue.acknowledged_at:
        issue.acknowledged_at = datetime.now()
    elif new_status == 'resolved' and not issue.resolved_at:
        issue.resolved_at = datetime.now()
        if resolution:
            issue.resolution = resolution
    elif new_status == 'closed' and not issue.closed_at:
        issue.closed_at = datetime.now()
    
    issue.status = new_status
    
    # Create status update
    update = MaintenanceUpdate(
        issue_id=issue.id,
        author_id=current_user.id,
        update_type='status_change',
        message=f"Status changed from {old_status} to {new_status}",
        old_status=old_status,
        new_status=new_status
    )
    
    db.session.add(update)
    db.session.commit()
    
    flash(f'Issue status updated to {new_status}.', 'success')
    return redirect(url_for('view_maintenance_issue', issue_id=issue_id))

@app.route('/maintenance/issues/<int:issue_id>/assign', methods=['POST'])
@login_required
def assign_maintenance_issue(issue_id):
    """Assign a maintenance issue to staff (managers only)"""
    # Check if user is a maintenance manager with assignment privileges
    manager = MaintenanceManager.query.filter_by(employee_id=current_user.id).first()
    if not manager or not manager.can_assign:
        return jsonify({'error': 'Unauthorized'}), 403
    
    issue = MaintenanceIssue.query.get_or_404(issue_id)
    assignee_id = request.form.get('assignee_id')
    
    # Validate assignee is maintenance staff
    assignee = Employee.query.join(MaintenanceManager).filter(
        Employee.id == assignee_id
    ).first()
    
    if not assignee:
        flash('Invalid assignee selected.', 'danger')
        return redirect(url_for('view_maintenance_issue', issue_id=issue_id))
    
    # Update assignment
    old_assignee = issue.assigned_to
    issue.assigned_to_id = assignee_id
    
    # Create assignment update
    update = MaintenanceUpdate(
        issue_id=issue.id,
        author_id=current_user.id,
        update_type='assignment',
        message=f"Assigned to {assignee.name}" + (f" (was: {old_assignee.name})" if old_assignee else "")
    )
    
    db.session.add(update)
    db.session.commit()
    
    flash(f'Issue assigned to {assignee.name}.', 'success')
    return redirect(url_for('view_maintenance_issue', issue_id=issue_id))

# ==================== API ROUTES FOR COMMUNICATION ====================

@app.route('/api/supervisor-messages/unread-count')
@login_required
def supervisor_messages_unread_count():
    """Get count of unread supervisor messages"""
    if not current_user.is_supervisor:
        return jsonify({'count': 0})
    
    count = SupervisorMessage.query.filter_by(
        recipient_id=current_user.id,
        read_at=None
    ).count()
    
    return jsonify({'count': count})

@app.route('/api/position-messages/unread-count')
@login_required
def position_messages_unread_count():
    """Get count of unread position messages"""
    if not current_user.position_id:
        return jsonify({'count': 0})
    
    # Get messages for user's position that they haven't read
    messages = PositionMessage.query.filter_by(
        position_id=current_user.position_id
    ).filter(
        or_(
            PositionMessage.expires_at.is_(None),
            PositionMessage.expires_at > datetime.now()
        )
    ).all()
    
    unread_count = sum(1 for msg in messages if not msg.is_read_by(current_user.id))
    
    return jsonify({'count': unread_count})

@app.route('/api/maintenance/my-issues-count')
@login_required
def my_maintenance_issues_count():
    """Get count of user's open maintenance issues"""
    # For managers, count assigned issues
    is_manager = MaintenanceManager.query.filter_by(employee_id=current_user.id).first()
    
    if is_manager:
        count = MaintenanceIssue.query.filter(
            MaintenanceIssue.assigned_to_id == current_user.id,
            MaintenanceIssue.status.in_(['open', 'acknowledged', 'in_progress'])
        ).count()
    else:
        # For regular employees, count their reported issues
        count = MaintenanceIssue.query.filter(
            MaintenanceIssue.reporter_id == current_user.id,
            MaintenanceIssue.status.in_(['open', 'acknowledged', 'in_progress'])
        ).count()
    
    return jsonify({'count': count})

# ==================== QUICK ACCESS ROUTES ====================

@app.route('/quick/supervisor-message', methods=['POST'])
@login_required
def quick_supervisor_message():
    """Quick send supervisor message from dashboard"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    recipient_id = request.form.get('recipient_id')
    message_text = request.form.get('message')
    
    # Create quick message
    message = SupervisorMessage(
        sender_id=current_user.id,
        recipient_id=recipient_id,
        subject='Quick Message',
        message=message_text,
        priority='normal',
        category='general'
    )
    
    db.session.add(message)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Message sent!'})

@app.route('/quick/position-broadcast', methods=['POST'])
@login_required
def quick_position_broadcast():
    """Quick broadcast to position colleagues"""
    if not current_user.position_id:
        return jsonify({'error': 'No position assigned'}), 403
    
    message_text = request.form.get('message')
    
    # Create broadcast
    message = PositionMessage(
        sender_id=current_user.id,
        position_id=current_user.position_id,
        subject='Quick Update',
        message=message_text,
        category='alert',
        target_shifts='all',
        expires_at=datetime.now() + timedelta(days=1)  # Expires in 24 hours
    )
    
    db.session.add(message)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Broadcast sent!'})

# ==================== SHIFT TRADE MARKETPLACE ROUTES ====================

@app.route('/shift-marketplace')
@login_required
def shift_marketplace():
    """Main shift trade marketplace view"""
    # Get filters from query params
    filters = {
        'start_date': request.args.get('start_date', date.today().strftime('%Y-%m-%d')),
        'end_date': request.args.get('end_date', (date.today() + timedelta(days=30)).strftime('%Y-%m-%d')),
        'shift_type': request.args.get('shift_type', ''),
        'position': request.args.get('position', ''),
        'compatibility': request.args.get('compatibility', '')
    }
    
    # Get available trades (exclude user's own posts)
    available_trades_query = ShiftTradePost.query.filter(
        ShiftTradePost.status == 'active',
        ShiftTradePost.poster_id != current_user.id
    ).join(Schedule)
    
    # Apply filters
    if filters['start_date']:
        available_trades_query = available_trades_query.filter(
            Schedule.date >= datetime.strptime(filters['start_date'], '%Y-%m-%d').date()
        )
    if filters['end_date']:
        available_trades_query = available_trades_query.filter(
            Schedule.date <= datetime.strptime(filters['end_date'], '%Y-%m-%d').date()
        )
    if filters['shift_type']:
        available_trades_query = available_trades_query.filter(
            Schedule.shift_type == filters['shift_type']
        )
    if filters['position']:
        available_trades_query = available_trades_query.filter(
            Schedule.position_id == int(filters['position'])
        )
    
    available_trades = available_trades_query.order_by(Schedule.date).all()
    
    # Calculate compatibility for each trade
    for trade in available_trades:
        trade.compatibility = calculate_trade_compatibility(current_user, trade)
    
    # Filter by compatibility if specified
    if filters['compatibility']:
        available_trades = [t for t in available_trades if t.compatibility == filters['compatibility']]
    
    # Get user's posted shifts
    my_posts = ShiftTradePost.query.filter_by(
        poster_id=current_user.id,
        status='active'
    ).all()
    
    # Get user's active trades
    my_trades = ShiftTrade.query.filter(
        or_(
            ShiftTrade.employee1_id == current_user.id,
            ShiftTrade.employee2_id == current_user.id
        ),
        ShiftTrade.status.in_(['pending', 'approved'])
    ).all()
    
    # Get trade history
    trade_history = get_trade_history(current_user.id)
    
    # Get upcoming shifts for posting
    my_upcoming_shifts = Schedule.query.filter(
        Schedule.employee_id == current_user.id,
        Schedule.date >= date.today(),
        Schedule.date <= date.today() + timedelta(days=60)
    ).order_by(Schedule.date).all()
    
    # Get positions for filter
    positions = Position.query.all()
    
    # Calculate statistics
    stats = {
        'available_trades': len(available_trades),
        'my_posted_shifts': len(my_posts),
        'my_active_trades': len(my_trades),
        'pending_trades': len([t for t in my_trades if t.status == 'pending']),
        'completed_trades': ShiftTrade.query.filter(
            or_(
                ShiftTrade.employee1_id == current_user.id,
                ShiftTrade.employee2_id == current_user.id
            ),
            ShiftTrade.status == 'completed'
        ).count()
    }
    
    return render_template('shift_marketplace.html',
                         available_trades=available_trades,
                         my_posts=my_posts,
                         my_trades=my_trades,
                         trade_history=trade_history,
                         my_upcoming_shifts=my_upcoming_shifts,
                         positions=positions,
                         filters=filters,
                         stats=stats)

@app.route('/shift-marketplace/post', methods=['POST'])
@login_required
def post_shift_for_trade():
    """Post a shift for trade"""
    schedule_id = request.form.get('schedule_id')
    
    # Verify ownership
    schedule = Schedule.query.get_or_404(schedule_id)
    if schedule.employee_id != current_user.id:
        flash('You can only post your own shifts for trade.', 'danger')
        return redirect(url_for('shift_marketplace'))
    
    # Check if already posted
    existing_post = ShiftTradePost.query.filter_by(
        schedule_id=schedule_id,
        status='active'
    ).first()
    
    if existing_post:
        flash('This shift is already posted for trade.', 'warning')
        return redirect(url_for('shift_marketplace'))
    
    # Create trade post
    trade_post = ShiftTradePost(
        poster_id=current_user.id,
        schedule_id=schedule_id,
        preferred_start_date=request.form.get('preferred_start_date') or None,
        preferred_end_date=request.form.get('preferred_end_date') or None,
        preferred_shift_types=','.join(request.form.getlist('preferred_shifts')),
        notes=request.form.get('notes', ''),
        auto_approve=request.form.get('auto_approve') == 'on',
        expires_at=datetime.now() + timedelta(days=30)
    )
    
    db.session.add(trade_post)
    db.session.commit()
    
    flash('Your shift has been posted to the trade marketplace!', 'success')
    return redirect(url_for('shift_marketplace'))

@app.route('/api/trade-post/<int:post_id>')
@login_required
def get_trade_post_details(post_id):
    """Get details of a trade post"""
    post = ShiftTradePost.query.get_or_404(post_id)
    
    # Increment view count
    post.view_count += 1
    db.session.commit()
    
    # Get schedule details
    schedule = post.schedule
    
    return jsonify({
        'id': post.id,
        'position': schedule.position.name if schedule.position else 'Unknown',
        'date': schedule.date.strftime('%A, %B %d, %Y'),
        'start_time': schedule.start_time.strftime('%I:%M %p'),
        'end_time': schedule.end_time.strftime('%I:%M %p'),
        'shift_type': schedule.shift_type,
        'notes': post.notes,
        'poster': post.poster.name
    })

@app.route('/api/my-compatible-shifts/<int:post_id>')
@login_required
def get_my_compatible_shifts(post_id):
    """Get user's shifts compatible with a trade post"""
    post = ShiftTradePost.query.get_or_404(post_id)
    schedule = post.schedule
    
    # Get user's upcoming shifts
    my_shifts_query = Schedule.query.filter(
        Schedule.employee_id == current_user.id,
        Schedule.date >= date.today(),
        Schedule.date != schedule.date  # Can't trade for same date
    )
    
    # Apply preferences if any
    if post.preferred_start_date:
        my_shifts_query = my_shifts_query.filter(
            Schedule.date >= post.preferred_start_date
        )
    if post.preferred_end_date:
        my_shifts_query = my_shifts_query.filter(
            Schedule.date <= post.preferred_end_date
        )
    if post.preferred_shift_types:
        preferred_types = post.preferred_shift_types.split(',')
        my_shifts_query = my_shifts_query.filter(
            Schedule.shift_type.in_(preferred_types)
        )
    
    my_shifts = my_shifts_query.order_by(Schedule.date).all()
    
    # Calculate compatibility for each shift
    shifts_data = []
    for shift in my_shifts:
        compatibility = 'high'
        if shift.position_id != schedule.position_id:
            compatibility = 'medium'
        if shift.shift_type != schedule.shift_type:
            compatibility = 'low' if compatibility == 'medium' else 'medium'
        
        shifts_data.append({
            'id': shift.id,
            'date': shift.date.strftime('%m/%d/%Y'),
            'position': shift.position.name if shift.position else 'TBD',
            'start_time': shift.start_time.strftime('%I:%M %p'),
            'end_time': shift.end_time.strftime('%I:%M %p'),
            'shift_type': shift.shift_type,
            'compatibility': compatibility
        })
    
    return jsonify(shifts_data)

@app.route('/api/trade-proposal/create', methods=['POST'])
@login_required
def create_trade_proposal():
    """Create a trade proposal"""
    trade_post_id = request.form.get('trade_post_id')
    offered_schedule_id = request.form.get('offered_schedule_id')
    message = request.form.get('message', '')
    
    # Verify trade post exists and is active
    trade_post = ShiftTradePost.query.get_or_404(trade_post_id)
    if trade_post.status != 'active':
        return jsonify({'success': False, 'message': 'This trade post is no longer active.'})
    
    # Verify ownership of offered schedule
    offered_schedule = Schedule.query.get_or_404(offered_schedule_id)
    if offered_schedule.employee_id != current_user.id:
        return jsonify({'success': False, 'message': 'You can only offer your own shifts.'})
    
    # Check if already proposed
    existing_proposal = ShiftTradeProposal.query.filter_by(
        trade_post_id=trade_post_id,
        proposer_id=current_user.id,
        status='pending'
    ).first()
    
    if existing_proposal:
        return jsonify({'success': False, 'message': 'You already have a pending proposal for this trade.'})
    
    # Create proposal
    proposal = ShiftTradeProposal(
        trade_post_id=trade_post_id,
        proposer_id=current_user.id,
        offered_schedule_id=offered_schedule_id,
        message=message
    )
    
    db.session.add(proposal)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Trade proposal sent successfully!'})

@app.route('/api/trade-proposals/<int:post_id>')
@login_required
def get_trade_proposals(post_id):
    """Get proposals for a trade post"""
    post = ShiftTradePost.query.get_or_404(post_id)
    
    # Verify ownership
    if post.poster_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    proposals = ShiftTradeProposal.query.filter_by(
        trade_post_id=post_id,
        status='pending'
    ).all()
    
    proposals_data = []
    for proposal in proposals:
        offered_shift = proposal.offered_schedule
        proposals_data.append({
            'id': proposal.id,
            'proposer_name': proposal.proposer.name,
            'offered_shift': f"{offered_shift.date.strftime('%m/%d')} - {offered_shift.position.name if offered_shift.position else 'TBD'} ({offered_shift.shift_type})",
            'message': proposal.message,
            'created_at': proposal.created_at.strftime('%m/%d %I:%M %p')
        })
    
    return jsonify(proposals_data)

@app.route('/api/trade-proposal/<int:proposal_id>/accept', methods=['POST'])
@login_required
def accept_trade_proposal(proposal_id):
    """Accept a trade proposal"""
    proposal = ShiftTradeProposal.query.get_or_404(proposal_id)
    
    # Verify ownership
    if proposal.trade_post.poster_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    if proposal.status != 'pending':
        return jsonify({'success': False, 'message': 'This proposal is no longer pending.'})
    
    # Update proposal status
    proposal.status = 'accepted'
    proposal.responded_at = datetime.now()
    
    # Update trade post status
    proposal.trade_post.status = 'matched'
    
    # Reject other proposals for this post
    other_proposals = ShiftTradeProposal.query.filter(
        ShiftTradeProposal.trade_post_id == proposal.trade_post_id,
        ShiftTradeProposal.id != proposal_id,
        ShiftTradeProposal.status == 'pending'
    ).all()
    
    for other in other_proposals:
        other.status = 'rejected'
        other.responded_at = datetime.now()
    
    # Create shift trade record
    trade = ShiftTrade(
        employee1_id=proposal.trade_post.poster_id,
        employee2_id=proposal.proposer_id,
        schedule1_id=proposal.trade_post.schedule_id,
        schedule2_id=proposal.offered_schedule_id,
        trade_post_id=proposal.trade_post_id,
        trade_proposal_id=proposal_id,
        status='pending' if not proposal.trade_post.auto_approve else 'approved',
        requires_approval=not proposal.trade_post.auto_approve
    )
    
    db.session.add(trade)
    
    # If auto-approve, execute the trade immediately
    if proposal.trade_post.auto_approve:
        execute_shift_trade(trade)
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Trade proposal accepted!'})

@app.route('/api/trade-proposal/<int:proposal_id>/reject', methods=['POST'])
@login_required
def reject_trade_proposal(proposal_id):
    """Reject a trade proposal"""
    proposal = ShiftTradeProposal.query.get_or_404(proposal_id)
    
    # Verify ownership
    if proposal.trade_post.poster_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    proposal.status = 'rejected'
    proposal.responded_at = datetime.now()
    
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/trade-post/<int:post_id>/cancel', methods=['POST'])
@login_required
def cancel_trade_post(post_id):
    """Cancel a trade post"""
    post = ShiftTradePost.query.get_or_404(post_id)
    
    # Verify ownership
    if post.poster_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    post.status = 'cancelled'
    
    # Reject all pending proposals
    proposals = ShiftTradeProposal.query.filter_by(
        trade_post_id=post_id,
        status='pending'
    ).all()
    
    for proposal in proposals:
        proposal.status = 'rejected'
        proposal.responded_at = datetime.now()
    
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/trade/<int:trade_id>/cancel', methods=['POST'])
@login_required
def cancel_trade(trade_id):
    """Cancel a pending trade"""
    trade = ShiftTrade.query.get_or_404(trade_id)
    
    # Verify participant
    if current_user.id not in [trade.employee1_id, trade.employee2_id]:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    if trade.status != 'pending':
        return jsonify({'success': False, 'message': 'Only pending trades can be cancelled.'})
    
    trade.status = 'cancelled'
    
    # Reactivate the trade post if it was from marketplace
    if trade.trade_post:
        trade.trade_post.status = 'active'
    
    db.session.commit()
    
    return jsonify({'success': True})

# ==================== DATABASE INITIALIZATION ROUTES ====================

@app.route('/init-db')
def init_db():
    """Initialize database with all tables"""
    with app.app_context():
        # Create all tables first
        db.create_all()
        
        # Now check if admin exists
        admin = Employee.query.filter_by(email='admin@workforce.com').first()
        if not admin:
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
            
            # Create some default positions
            positions = [
                Position(name='Nurse', department='Healthcare', min_coverage=2),
                Position(name='Security Officer', department='Security', min_coverage=1),
                Position(name='Technician', department='Operations', min_coverage=3),
                Position(name='Customer Service', department='Support', min_coverage=2)
            ]
            for pos in positions:
                db.session.add(pos)
            
            # Create some default skills
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

@app.route('/populate-crews')
def populate_crews():
    """Populate database with 4 complete crews for development"""
    if request.args.get('confirm') != 'yes':
        return '''
        <h2>🏗️ Populate 4 Crews for Development</h2>
        <p>This will create <strong>40 employees</strong> (10 per crew) with:</p>
        <ul>
            <li><strong>Crew A:</strong> 10 employees (Day shift preference)</li>
            <li><strong>Crew B:</strong> 10 employees (Day shift preference)</li>
            <li><strong>Crew C:</strong> 10 employees (Night shift preference)</li>
            <li><strong>Crew D:</strong> 10 employees (Night shift preference)</li>
        </ul>
        <p>Each crew will have:</p>
        <ul>
            <li>1 Crew Lead (supervisor)</li>
            <li>3 Nurses</li>
            <li>2 Security Officers</li>
            <li>2 Technicians</li>
            <li>2 Customer Service Representatives</li>
        </ul>
        <p><strong>Login credentials:</strong></p>
        <ul>
            <li>Email format: [name].[lastname]@company.com</li>
            <li>Password: password123 (for all)</li>
        </ul>
        <p><a href="/populate-crews?confirm=yes" class="btn btn-primary" onclick="return confirm('Create 40 employees across 4 crews?')">Yes, Populate Crews</a></p>
        <p><a href="/dashboard" class="btn btn-secondary">Cancel</a></p>
        '''
    
    try:
        # Get positions (assuming they exist from init-db)
        nurse = Position.query.filter_by(name='Nurse').first()
        security = Position.query.filter_by(name='Security Officer').first()
        tech = Position.query.filter_by(name='Technician').first()
        customer_service = Position.query.filter_by(name='Customer Service').first()
        
        # Get skills
        skills = {
            'cpr': Skill.query.filter_by(name='CPR Certified').first(),
            'first_aid': Skill.query.filter_by(name='First Aid').first(),
            'security': Skill.query.filter_by(name='Security Clearance').first(),
            'emergency': Skill.query.filter_by(name='Emergency Response').first(),
            'equipment': Skill.query.filter_by(name='Equipment Operation').first()
        }
        
        # Employee data for each crew
        crew_templates = {
            'A': {
                'shift_preference': 'day',
                'employees': [
                    {'name': 'Alice Anderson', 'email': 'alice.anderson@company.com', 'position': nurse, 'is_supervisor': True, 'skills': ['cpr', 'first_aid', 'emergency']},
                    {'name': 'Adam Martinez', 'email': 'adam.martinez@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid']},
                    {'name': 'Angela Brown', 'email': 'angela.brown@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid', 'emergency']},
                    {'name': 'Andrew Wilson', 'email': 'andrew.wilson@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid']},
                    {'name': 'Amanda Davis', 'email': 'amanda.davis@company.com', 'position': security, 'skills': ['security', 'emergency']},
                    {'name': 'Aaron Johnson', 'email': 'aaron.johnson@company.com', 'position': security, 'skills': ['security', 'first_aid']},
                    {'name': 'Anna Miller', 'email': 'anna.miller@company.com', 'position': tech, 'skills': ['equipment', 'emergency']},
                    {'name': 'Alex Thompson', 'email': 'alex.thompson@company.com', 'position': tech, 'skills': ['equipment']},
                    {'name': 'Amy Garcia', 'email': 'amy.garcia@company.com', 'position': customer_service, 'skills': ['emergency']},
                    {'name': 'Anthony Lee', 'email': 'anthony.lee@company.com', 'position': customer_service, 'skills': ['first_aid']}
                ]
            },
            'B': {
                'shift_preference': 'day',
                'employees': [
                    {'name': 'Barbara Bennett', 'email': 'barbara.bennett@company.com', 'position': nurse, 'is_supervisor': True, 'skills': ['cpr', 'first_aid', 'emergency']},
                    {'name': 'Brian Clark', 'email': 'brian.clark@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid']},
                    {'name': 'Betty Rodriguez', 'email': 'betty.rodriguez@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid', 'emergency']},
                    {'name': 'Benjamin Lewis', 'email': 'benjamin.lewis@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid']},
                    {'name': 'Brenda Walker', 'email': 'brenda.walker@company.com', 'position': security, 'skills': ['security', 'emergency']},
                    {'name': 'Blake Hall', 'email': 'blake.hall@company.com', 'position': security, 'skills': ['security', 'first_aid']},
                    {'name': 'Bonnie Allen', 'email': 'bonnie.allen@company.com', 'position': tech, 'skills': ['equipment', 'emergency']},
                    {'name': 'Bruce Young', 'email': 'bruce.young@company.com', 'position': tech, 'skills': ['equipment']},
                    {'name': 'Brittany King', 'email': 'brittany.king@company.com', 'position': customer_service, 'skills': ['emergency']},
                    {'name': 'Bradley Wright', 'email': 'bradley.wright@company.com', 'position': customer_service, 'skills': ['first_aid']}
                ]
            },
            'C': {
                'shift_preference': 'night',
                'employees': [
                    {'name': 'Carol Campbell', 'email': 'carol.campbell@company.com', 'position': nurse, 'is_supervisor': True, 'skills': ['cpr', 'first_aid', 'emergency']},
                    {'name': 'Charles Parker', 'email': 'charles.parker@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid']},
                    {'name': 'Christine Evans', 'email': 'christine.evans@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid', 'emergency']},
                    {'name': 'Christopher Turner', 'email': 'christopher.turner@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid']},
                    {'name': 'Cynthia Collins', 'email': 'cynthia.collins@company.com', 'position': security, 'skills': ['security', 'emergency']},
                    {'name': 'Craig Edwards', 'email': 'craig.edwards@company.com', 'position': security, 'skills': ['security', 'first_aid']},
                    {'name': 'Catherine Stewart', 'email': 'catherine.stewart@company.com', 'position': tech, 'skills': ['equipment', 'emergency']},
                    {'name': 'Carl Sanchez', 'email': 'carl.sanchez@company.com', 'position': tech, 'skills': ['equipment']},
                    {'name': 'Cheryl Morris', 'email': 'cheryl.morris@company.com', 'position': customer_service, 'skills': ['emergency']},
                    {'name': 'Chad Rogers', 'email': 'chad.rogers@company.com', 'position': customer_service, 'skills': ['first_aid']}
                ]
            },
            'D': {
                'shift_preference': 'night',
                'employees': [
                    {'name': 'Diana Davidson', 'email': 'diana.davidson@company.com', 'position': nurse, 'is_supervisor': True, 'skills': ['cpr', 'first_aid', 'emergency']},
                    {'name': 'David Foster', 'email': 'david.foster@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid']},
                    {'name': 'Deborah Murphy', 'email': 'deborah.murphy@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid', 'emergency']},
                    {'name': 'Daniel Rivera', 'email': 'daniel.rivera@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid']},
                    {'name': 'Donna Cook', 'email': 'donna.cook@company.com', 'position': security, 'skills': ['security', 'emergency']},
                    {'name': 'Dennis Morgan', 'email': 'dennis.morgan@company.com', 'position': security, 'skills': ['security', 'first_aid']},
                    {'name': 'Dorothy Peterson', 'email': 'dorothy.peterson@company.com', 'position': tech, 'skills': ['equipment', 'emergency']},
                    {'name': 'Douglas Cooper', 'email': 'douglas.cooper@company.com', 'position': tech, 'skills': ['equipment']},
                    {'name': 'Denise Bailey', 'email': 'denise.bailey@company.com', 'position': customer_service, 'skills': ['emergency']},
                    {'name': 'Derek Reed', 'email': 'derek.reed@company.com', 'position': customer_service, 'skills': ['first_aid']}
                ]
            }
        }
        
        created_count = 0
        
        for crew_letter, crew_data in crew_templates.items():
            for emp_data in crew_data['employees']:
                # Check if employee already exists
                existing = Employee.query.filter_by(email=emp_data['email']).first()
                if existing:
                    continue
                
                # Create employee
                employee = Employee(
                    name=emp_data['name'],
                    email=emp_data['email'],
                    phone=f'555-{crew_letter}{str(created_count).zfill(3)}',
                    is_supervisor=emp_data.get('is_supervisor', False),
                    position_id=emp_data['position'].id if emp_data['position'] else None,
                    crew=crew_letter,
                    shift_pattern=crew_data['shift_preference'],
                    hire_date=date.today() - timedelta(days=365),  # 1 year ago
                    vacation_days=10,
                    sick_days=5,
                    personal_days=3
                )
                
                # Set password
                employee.set_password('password123')
                
                # Add skills
                for skill_key in emp_data.get('skills', []):
                    if skill_key in skills and skills[skill_key]:
                        employee.skills.append(skills[skill_key])
                
                db.session.add(employee)
                db.session.flush()  # This assigns the ID to the employee
                created_count += 1
                
                # Create circadian profile after employee has ID
                profile = CircadianProfile(
                    employee_id=employee.id,
                    chronotype='morning' if crew_data['shift_preference'] == 'day' else 'evening',
                    current_shift_type=crew_data['shift_preference']
                )
                db.session.add(profile)
        
        db.session.commit()
        
        return f'''
        <h2>✅ Crews Populated Successfully!</h2>
        <p><strong>{created_count} employees</strong> have been created across 4 crews.</p>
        
        <h3>Crew Supervisors (can approve requests):</h3>
        <ul>
            <li><strong>Crew A:</strong> Alice Anderson (alice.anderson@company.com)</li>
            <li><strong>Crew B:</strong> Barbara Bennett (barbara.bennett@company.com)</li>
            <li><strong>Crew C:</strong> Carol Campbell (carol.campbell@company.com)</li>
            <li><strong>Crew D:</strong> Diana Davidson (diana.davidson@company.com)</li>
        </ul>
        
        <h3>Sample Regular Employees:</h3>
        <ul>
            <li><strong>Nurse:</strong> Adam Martinez (adam.martinez@company.com)</li>
            <li><strong>Security:</strong> Amanda Davis (amanda.davis@company.com)</li>
            <li><strong>Technician:</strong> Anna Miller (anna.miller@company.com)</li>
            <li><strong>Customer Service:</strong> Amy Garcia (amy.garcia@company.com)</li>
        </ul>
        
        <p><strong>All passwords:</strong> password123</p>
        
        <h3>Next Steps:</h3>
        <ol>
            <li><a href="/schedule/create" class="btn btn-primary">Create Schedules</a> - Set up shifts for your crews</li>
            <li><a href="/schedule/view" class="btn btn-info">View Schedules</a> - See crew assignments</li>
            <li><a href="/logout" class="btn btn-warning">Logout</a> - Try logging in as an employee</li>
        </ol>
        
        <p><a href="/dashboard" class="btn btn-success">Return to Dashboard</a></p>
        '''
        
    except Exception as e:
        db.session.rollback()
        return f'''
        <h2>❌ Error Populating Crews</h2>
        <p>An error occurred: {str(e)}</p>
        <p>Make sure you've run <a href="/init-db">/init-db</a> first to create positions and skills.</p>
        <p><a href="/dashboard" class="btn btn-secondary">Return to Dashboard</a></p>
        '''
@app.route('/crews')
@login_required
def view_crews():
    """View all crews and their members"""
    # Get all employees grouped by crew
    crews = {}
    employees = Employee.query.filter(Employee.crew != None).order_by(Employee.crew, Employee.name).all()
    
    for employee in employees:
        if employee.crew not in crews:
            crews[employee.crew] = []
        crews[employee.crew].append(employee)
    
    # Get supervisor for each crew
    crew_supervisors = {}
    for crew in crews:
        supervisor = Employee.query.filter_by(crew=crew, is_supervisor=True).first()
        crew_supervisors[crew] = supervisor
    
    # Get statistics for each crew
    crew_stats = {}
    for crew, members in crews.items():
        crew_stats[crew] = {
            'total': len(members),
            'supervisors': len([e for e in members if e.is_supervisor]),
            'operators': len([e for e in members if not e.is_supervisor]),
            'positions': len(set([e.position.name for e in members if e.position]))
        }
    
    return render_template('view_crews.html', 
                         crews=crews, 
                         crew_supervisors=crew_supervisors,
                         crew_stats=crew_stats)
# ==================== ADDITIONAL DATABASE ROUTES ====================

@app.route('/add-communication-tables')
def add_communication_tables():
    """Add the new communication tables to the database"""
    if request.args.get('confirm') != 'yes':
        return '''
        <h2>Add Communication Tables</h2>
        <p>This will add the following new communication features to your database:</p>
        <h3>Feature 1: Supervisor-to-Supervisor Messages</h3>
        <ul>
            <li>Direct messaging between shift supervisors</li>
            <li>Priority levels and categories</li>
            <li>Thread support for conversations</li>
            <li>Read receipts</li>
        </ul>
        <h3>Feature 2: Position-Based Communication</h3>
        <ul>
            <li>Message board for employees in the same position</li>
            <li>Share tips, handoff notes, and alerts</li>
            <li>Target specific shifts or all shifts</li>
            <li>Message expiration and pinning</li>
        </ul>
        <h3>Feature 3: Maintenance Issue Tracking</h3>
        <ul>
            <li>Report equipment and facility issues</li>
            <li>Priority-based tracking</li>
            <li>Assignment to maintenance staff</li>
            <li>Progress updates and resolution tracking</li>
            <li>Safety issue flagging</li>
        </ul>
        <p>New tables to be added:</p>
        <ul>
            <li>SupervisorMessage - Messages between supervisors</li>
            <li>PositionMessage - Messages between position colleagues</li>
            <li>PositionMessageRead - Read receipts for position messages</li>
            <li>MaintenanceIssue - Maintenance issue reports</li>
            <li>MaintenanceUpdate - Updates on maintenance issues</li>
            <li>MaintenanceManager - Designate maintenance managers</li>
        </ul>
        <p><a href="/add-communication-tables?confirm=yes" class="btn btn-primary">Click here to add communication features</a></p>
        <p><a href="/" class="btn btn-secondary">Cancel</a></p>
        '''
    
    try:
        # Create all tables (this will only add new ones)
        db.create_all()
        
        # Check if we have a maintenance manager
        if not MaintenanceManager.query.first():
            # Make the admin a maintenance manager by default
            admin = Employee.query.filter_by(email='admin@workforce.com').first()
            if admin:
                mm = MaintenanceManager(
                    employee_id=admin.id,
                    is_primary=True,
                    can_assign=True
                )
                db.session.add(mm)
                db.session.commit()
        
        return '''
        <h2>✅ Success!</h2>
        <p>Communication tables have been added to the database.</p>
        <h3>New features now available:</h3>
        <ol>
            <li><strong>Supervisor Messages:</strong> Supervisors can now communicate directly with other shift supervisors</li>
            <li><strong>Position Communication:</strong> Employees can share information with colleagues in the same position across all shifts</li>
            <li><strong>Maintenance Tracking:</strong> Anyone can report maintenance issues and track their resolution</li>
        </ol>
        <h3>Next Steps:</h3>
        <ul>
            <li>Supervisors will see a "Supervisor Messages" button in their dashboard</li>
            <li>Employees will see a "Position Board" in their dashboard</li>
            <li>Everyone can report maintenance issues from their dashboard</li>
            <li>The admin account has been designated as the primary maintenance manager</li>
        </ul>
        <p><a href="/" class="btn btn-primary">Return to home</a></p>
        '''
    except Exception as e:
        return f'''
        <h2>❌ Error</h2>
        <p>Failed to add communication tables: {str(e)}</p>
        <p>Please ensure your database connection is working and try again.</p>
        <p><a href="/" class="btn btn-secondary">Return to home</a></p>
        '''

@app.route('/add-coverage-tables')
def add_coverage_tables():
    """Add the new coverage notification and overtime tables"""
    if request.args.get('confirm') != 'yes':
        return '''
        <h2>Add Coverage Tables</h2>
        <p>This will add the CoverageNotification and OvertimeOpportunity tables to your database.</p>
        <p>These tables enable:</p>
        <ul>
            <li>Push notifications for coverage needs</li>
            <li>Smart overtime distribution</li>
            <li>Employee response tracking</li>
        </ul>
        <p><a href="/add-coverage-tables?confirm=yes" class="btn btn-primary">Click here to confirm</a></p>
        '''
    
    try:
        # Create all tables (this will only add new ones)
        db.create_all()
        return '''
        <h2>Success!</h2>
        <p>Coverage notification and overtime tables have been added to the database.</p>
        <p>New features available:</p>
        <ul>
            <li>Coverage push notifications</li>
            <li>Overtime opportunity management</li>
            <li>Smart crew distribution</li>
        </ul>
        <p><a href="/">Return to home</a></p>
        '''
    except Exception as e:
        return f'<h2>Error</h2><p>Failed to add tables: {str(e)}</p>'

@app.route('/add-marketplace-tables')
def add_marketplace_tables():
    """Add the shift trade marketplace tables"""
    if request.args.get('confirm') != 'yes':
        return '''
        <h2>Add Shift Trade Marketplace Tables</h2>
        <p>This will add the new shift trade marketplace tables to your database.</p>
        <p>New tables to be added:</p>
        <ul>
            <li>ShiftTradePost - Posts of shifts available for trade</li>
            <li>ShiftTradeProposal - Trade proposals from employees</li>
            <li>ShiftTrade - Completed or pending trades</li>
            <li>TradeMatchPreference - Employee trade preferences</li>
        </ul>
        <p>Features enabled:</p>
        <ul>
            <li>Post shifts for trade in marketplace</li>
            <li>Browse and filter available trades</li>
            <li>Smart compatibility matching</li>
            <li>Trade history tracking</li>
            <li>Auto-approval options</li>
        </ul>
        <p><a href="/add-marketplace-tables?confirm=yes" class="btn btn-primary">Click here to confirm</a></p>
        '''
    
    try:
        # Create all tables (this will only add new ones)
        db.create_all()
        return '''
        <h2>Success!</h2>
        <p>Shift trade marketplace tables have been added to the database.</p>
        <p>New features available:</p>
        <ul>
            <li>Shift Trade Marketplace - Employees can now post and trade shifts</li>
            <li>Smart Matching - System suggests compatible trades</li>
            <li>Trade History - Track all completed trades</li>
        </ul>
        <p>Employees can access the marketplace from their dashboard.</p>
        <p><a href="/">Return to home</a></p>
        '''
    except Exception as e:
        return f'<h2>Error</h2><p>Failed to add marketplace tables: {str(e)}</p>'

@app.route('/reset-db')
def reset_db():
    """Reset database - WARNING: This will delete all data!"""
    if request.args.get('confirm') != 'yes':
        return '''
        <h2>⚠️ WARNING: Reset Database</h2>
        <p style="color: red;"><strong>This will DELETE ALL DATA in the database!</strong></p>
        <p>Only use this for initial setup or if you're sure you want to start over.</p>
        <p><a href="/reset-db?confirm=yes" onclick="return confirm('Are you SURE you want to delete all data?')" style="background: red; color: white; padding: 10px; text-decoration: none;">Yes, reset the database</a></p>
        <p><a href="/" style="background: green; color: white; padding: 10px; text-decoration: none;">Cancel and go back</a></p>
        '''
    
    try:
        with app.app_context():
            # For PostgreSQL, we need to drop tables with CASCADE
            from sqlalchemy import text
            
            # Get the database engine
            engine = db.engine
            
            # Drop all tables using raw SQL with CASCADE
            with engine.connect() as conn:
                # First, drop all tables in the public schema
                conn.execute(text("DROP SCHEMA public CASCADE"))
                conn.execute(text("CREATE SCHEMA public"))
                conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
                conn.commit()
            
            # Now recreate all tables with correct schema
            db.create_all()
            
        return '''
        <h2>✅ Database Reset Complete!</h2>
        <p>All tables have been dropped and recreated with the correct schema.</p>
        <p><a href="/init-db" style="background: blue; color: white; padding: 10px; text-decoration: none;">Now initialize the database with default data</a></p>
        '''
    except Exception as e:
        return f'<h2>Error</h2><p>Failed to reset database: {str(e)}</p>'

@app.route('/create-demo-data')
def create_demo_data():
    """Create demo employees for testing"""
    if request.args.get('confirm') != 'yes':
        return '''
        <h2>Create Demo Data</h2>
        <p>This will create demo employees in each crew for testing.</p>
        <p><a href="/create-demo-data?confirm=yes">Click here to confirm</a></p>
        '''
    
    try:
        from create_custom_demo_database import populate_demo_data
        populate_demo_data()
        return '<h2>Success!</h2><p>Demo data created!</p><p><a href="/dashboard">Go to dashboard</a></p>'
    except ImportError:
        # If the demo script doesn't exist, create basic demo data
        crews = ['A', 'B', 'C', 'D']
        positions = Position.query.all()
        
        for i, crew in enumerate(crews):
            for j in range(3):  # 3 employees per crew
                emp = Employee(
                    name=f'{crew} Employee {j+1}',
                    email=f'{crew.lower()}{j+1}@workforce.com',
                    crew=crew,
                    position_id=positions[j % len(positions)].id if positions else None,
                    is_supervisor=False,
                    vacation_days=10,
                    sick_days=5,
                    personal_days=3
                )
                emp.set_password('password123')
                db.session.add(emp)
        
        db.session.commit()
        return '<h2>Success!</h2><p>Basic demo data created!</p><p><a href="/dashboard">Go to dashboard</a></p>'

@app.route('/debug-employees')
def debug_employees():
    """Debug employee data"""
    employees = Employee.query.all()
    return f'''
    <h2>Employee Debug Info</h2>
    <p>Total employees: {len(employees)}</p>
    <h3>Employee List:</h3>
    <ul>
    {''.join([f'<li>{e.name} ({e.email}) - Crew: {e.crew}, Supervisor: {e.is_supervisor}</li>' for e in employees])}
    </ul>
    <p><a href="/dashboard">Back to dashboard</a></p>
    '''

@app.route('/reset-passwords')
def reset_passwords():
    """Reset all passwords to password123"""
    if request.args.get('confirm') != 'yes':
        return '''
        <h2>Reset All Passwords</h2>
        <p>This will reset ALL employee passwords to 'password123'.</p>
        <p><a href="/reset-passwords?confirm=yes">Click here to confirm</a></p>
        '''
    
    employees = Employee.query.all()
    for emp in employees:
        emp.set_password('password123')
    db.session.commit()
    
    return f'<h2>Success!</h2><p>Reset passwords for {len(employees)} employees.</p><p><a href="/dashboard">Back to dashboard</a></p>'

@app.route('/migrate-database')
def migrate_database():
    """Migrate database with new schema"""
    if request.args.get('confirm') != 'yes':
        return '''
        <h2>Migrate Database</h2>
        <p>This will update the database schema to include all new tables.</p>
        <p><strong>Warning:</strong> This will preserve existing data but add new tables.</p>
        <p><a href="/migrate-database?confirm=yes">Click here to confirm</a></p>
        '''
    
    try:
        db.create_all()
        return '<h2>Success!</h2><p>Database migrated successfully!</p><p><a href="/dashboard">Back to dashboard</a></p>'
    except Exception as e:
        return f'<h2>Error</h2><p>Migration failed: {str(e)}</p>'

# ==================== ADMIN ROUTES ====================

@app.route('/admin/maintenance-managers')
@login_required
def manage_maintenance_managers():
    """Admin page to manage maintenance managers"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get all maintenance managers
    managers = MaintenanceManager.query.all()
    
    # Get employees who could be maintenance managers
    potential_managers = Employee.query.filter(
        ~Employee.id.in_([m.employee_id for m in managers])
    ).order_by(Employee.name).all()
    
    return render_template('admin_maintenance_managers.html',
                         managers=managers,
                         potential_managers=potential_managers)

@app.route('/admin/maintenance-managers/add', methods=['POST'])
@login_required
def add_maintenance_manager():
    """Add a new maintenance manager"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    employee_id = request.form.get('employee_id')
    is_primary = request.form.get('is_primary') == 'on'
    can_assign = request.form.get('can_assign') == 'on'
    
    # Check if already a manager
    existing = MaintenanceManager.query.filter_by(employee_id=employee_id).first()
    if existing:
        flash('Employee is already a maintenance manager.', 'warning')
        return redirect(url_for('manage_maintenance_managers'))
    
    # If setting as primary, unset other primaries
    if is_primary:
        MaintenanceManager.query.update({'is_primary': False})
    
    # Create maintenance manager
    manager = MaintenanceManager(
        employee_id=employee_id,
        is_primary=is_primary,
        can_assign=can_assign
    )
    
    db.session.add(manager)
    db.session.commit()
    
    employee = Employee.query.get(employee_id)
    flash(f'{employee.name} added as maintenance manager!', 'success')
    return redirect(url_for('manage_maintenance_managers'))

@app.route('/admin/maintenance-managers/<int:manager_id>/remove', methods=['POST'])
@login_required
def remove_maintenance_manager(manager_id):
    """Remove a maintenance manager"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    manager = MaintenanceManager.query.get_or_404(manager_id)
    employee_name = manager.employee.name
    
    db.session.delete(manager)
    db.session.commit()
    
    flash(f'{employee_name} removed from maintenance managers.', 'success')
    return redirect(url_for('manage_maintenance_managers'))

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# ==================== MAIN ====================

if __name__ == '__main__':
    app.run(debug=True)
