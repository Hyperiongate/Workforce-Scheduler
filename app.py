# app.py - Complete Flask application with all features

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date
import os
from models import db, Employee, Position, Skill, Schedule, EmployeeSkill, PositionSkill, Availability, TimeOffRequest, VacationCalendar, CoverageRequest, CasualWorker, CasualAssignment, ShiftSwapRequest, ScheduleSuggestion, CircadianProfile, SleepLog, SleepRecommendation, ShiftTransitionPlan
from circadian_advisor import CircadianAdvisor
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///workforce.db')
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return Employee.query.get(int(user_id))

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
        
        if employee and check_password_hash(employee.password, password):
            login_user(employee)
            flash(f'Welcome back, {employee.name}!', 'success')
            
            # Redirect based on role
            if employee.role == 'supervisor':
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

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'supervisor':
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Get pending items for supervisor dashboard
    pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
    pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
    pending_suggestions = ScheduleSuggestion.query.filter_by(status='pending').count()
    
    # Get upcoming schedules
    upcoming_schedules = Schedule.query.filter(
        Schedule.start_time >= datetime.now()
    ).order_by(Schedule.start_time).limit(10).all()
    
    # Get recent time off requests
    recent_time_off = TimeOffRequest.query.order_by(
        TimeOffRequest.submitted_at.desc()
    ).limit(5).all()
    
    return render_template('dashboard.html',
                         pending_swaps=pending_swaps,
                         pending_time_off=pending_time_off,
                         pending_suggestions=pending_suggestions,
                         upcoming_schedules=upcoming_schedules,
                         recent_time_off=recent_time_off)

@app.route('/employee-dashboard')
@login_required
def employee_dashboard():
    """Employee dashboard with schedules, requests, and sleep health info"""
    if current_user.role != 'employee':
        flash('Access denied. This page is for employees only.', 'danger')
        return redirect(url_for('dashboard'))
    
    employee = Employee.query.get(current_user.id)
    
    # Get upcoming schedules
    upcoming_schedules = Schedule.query.filter(
        Schedule.employee_id == employee.id,
        Schedule.start_time >= datetime.now()
    ).order_by(Schedule.start_time).limit(5).all()
    
    # Get recent schedules for hours calculation
    week_ago = datetime.now() - timedelta(days=7)
    recent_schedules = Schedule.query.filter(
        Schedule.employee_id == employee.id,
        Schedule.start_time >= week_ago,
        Schedule.end_time <= datetime.now()
    ).all()
    
    # Calculate hours worked
    total_hours = sum((s.end_time - s.start_time).total_seconds() / 3600 for s in recent_schedules)
    overtime_hours = max(0, total_hours - 40)
    
    # Get pending requests
    pending_swaps = ShiftSwapRequest.query.filter_by(
        requesting_employee_id=employee.id,
        status='pending'
    ).count()
    
    pending_suggestions = ScheduleSuggestion.query.filter_by(
        employee_id=employee.id,
        status='pending'
    ).count()
    
    # Get time off balance
    vacation_remaining = employee.vacation_days_total - employee.vacation_days_used
    sick_remaining = employee.sick_days_total - employee.sick_days_used
    personal_remaining = employee.personal_days_total - employee.personal_days_used
    
    # Get sleep health data
    circadian_profile = CircadianProfile.query.filter_by(employee_id=employee.id).first()
    has_circadian_profile = circadian_profile is not None
    
    if circadian_profile:
        # Get circadian adaptation score
        advisor = CircadianAdvisor(employee, circadian_profile)
        phase_info = advisor.calculate_circadian_phase()
        circadian_adaptation = phase_info['adaptation']
        
        # Count unread recommendations
        unread_recommendations = SleepRecommendation.query.filter_by(
            circadian_profile_id=circadian_profile.id,
            was_viewed=False
        ).filter(
            SleepRecommendation.valid_until > datetime.now()
        ).count()
    else:
        circadian_adaptation = 0
        unread_recommendations = 0
    
    return render_template('employee_dashboard.html',
                         employee=employee,
                         upcoming_schedules=upcoming_schedules,
                         total_hours=round(total_hours, 1),
                         overtime_hours=round(overtime_hours, 1),
                         pending_swaps=pending_swaps,
                         pending_suggestions=pending_suggestions,
                         vacation_remaining=vacation_remaining,
                         sick_remaining=sick_remaining,
                         personal_remaining=personal_remaining,
                         has_circadian_profile=has_circadian_profile,
                         circadian_profile=circadian_profile,
                         circadian_adaptation=circadian_adaptation,
                         unread_recommendations=unread_recommendations)

# ==================== SCHEDULE MANAGEMENT ROUTES ====================

@app.route('/schedule/create', methods=['GET', 'POST'])
@login_required
def create_schedule():
    if current_user.role != 'supervisor':
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    if request.method == 'POST':
        schedule_type = request.form.get('schedule_type')
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
        
        if schedule_type == '4_crew_rotation':
            rotation_pattern = request.form.get('rotation_pattern')
            return create_4_crew_schedule(start_date, end_date, rotation_pattern)
        else:
            # Standard schedule creation
            shift_pattern = request.form.get('shift_pattern')
            return create_standard_schedule(start_date, end_date, shift_pattern)
    
    employees = Employee.query.filter_by(role='employee').all()
    return render_template('schedule_input.html', employees=employees)

def create_4_crew_schedule(start_date, end_date, rotation_pattern):
    """Create schedules for 4-crew rotation patterns"""
    crews = {'A': [], 'B': [], 'C': [], 'D': []}
    
    # Get employees by crew
    for crew in crews:
        crews[crew] = Employee.query.filter_by(crew=crew, role='employee').all()
    
    # Check if we have employees in all crews
    empty_crews = [crew for crew, employees in crews.items() if not employees]
    if empty_crews:
        flash(f'No employees assigned to crew(s): {", ".join(empty_crews)}. Please assign employees to crews first.', 'danger')
        return redirect(url_for('create_schedule'))
    
    # Define rotation patterns
    if rotation_pattern == '2_2_3':
        # 2-2-3 (Pitman) schedule
        cycle_days = 14
        pattern = {
            'A': [1, 1, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0],  # Day shifts
            'B': [0, 0, 1, 1, 0, 0, 0, 1, 1, 0, 0, 1, 1, 1],  # Day shifts (opposite A)
            'C': [0, 0, 1, 1, 0, 0, 0, 1, 1, 0, 0, 1, 1, 1],  # Night shifts
            'D': [1, 1, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0],  # Night shifts (opposite C)
        }
        shift_times = {
            'A': ('day', 7, 19), 'B': ('day', 7, 19),
            'C': ('night', 19, 7), 'D': ('night', 19, 7)
        }
    elif rotation_pattern == '4_on_4_off':
        # 4 on, 4 off pattern
        cycle_days = 16
        pattern = {
            'A': [1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0],
            'B': [0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1],
            'C': [1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0],
            'D': [0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1],
        }
        shift_times = {
            'A': ('day', 7, 19), 'B': ('day', 7, 19),
            'C': ('night', 19, 7), 'D': ('night', 19, 7)
        }
    else:  # DuPont
        # DuPont schedule
        cycle_days = 28
        # This is a simplified version - actual DuPont is more complex
        pattern = {
            'A': [1,1,1,1,0,0,0,1,1,1,0,0,0,0,0,1,1,1,1,0,0,0,1,1,1,0,0,0],
            'B': [0,0,0,1,1,1,1,0,0,0,1,1,1,0,0,0,0,1,1,1,1,0,0,0,1,1,1,0],
            'C': [1,0,0,0,0,1,1,1,1,0,0,0,1,1,1,0,0,0,0,1,1,1,1,0,0,0,1,1],
            'D': [1,1,0,0,0,0,1,1,1,1,0,0,0,1,1,1,0,0,0,0,1,1,1,1,0,0,0,1],
        }
        shift_times = {
            'A': ('day', 7, 19), 'B': ('day', 7, 19),
            'C': ('night', 19, 7), 'D': ('night', 19, 7)
        }
    
    # Create schedules
    current_date = start_date
    schedules_created = 0
    
    while current_date <= end_date:
        day_in_cycle = (current_date - start_date).days % cycle_days
        
        for crew_name, crew_employees in crews.items():
            if pattern[crew_name][day_in_cycle] == 1:  # Working day
                shift_type, start_hour, end_hour = shift_times[crew_name]
                
                for employee in crew_employees:
                    # Check for time off
                    has_time_off = VacationCalendar.query.filter_by(
                        employee_id=employee.id,
                        date=current_date.date()
                    ).first()
                    
                    if not has_time_off:
                        start_time = current_date.replace(hour=start_hour, minute=0, second=0)
                        end_time = current_date.replace(hour=end_hour, minute=0, second=0)
                        
                        # Handle overnight shifts
                        if end_hour < start_hour:
                            end_time += timedelta(days=1)
                        
                        schedule = Schedule(
                            employee_id=employee.id,
                            start_time=start_time,
                            end_time=end_time,
                            shift_type=shift_type,
                            position_id=employee.position_id
                        )
                        db.session.add(schedule)
                        schedules_created += 1
                        
                        # Update circadian profile
                        update_circadian_profile_on_schedule_change(employee.id, shift_type)
        
        current_date += timedelta(days=1)
    
    db.session.commit()
    flash(f'Successfully created {schedules_created} schedules using {rotation_pattern} pattern!', 'success')
    return redirect(url_for('view_schedules'))

def create_standard_schedule(start_date, end_date, shift_pattern):
    """Create standard schedules"""
    employees = Employee.query.filter_by(role='employee').all()
    schedules_created = 0
    
    # Define shift times based on pattern
    shift_times = {
        'standard': [('day', 9, 17)],
        'retail': [('day', 10, 18), ('evening', 14, 22)],
        '2_shift': [('day', 7, 15), ('evening', 15, 23)],
        '3_shift': [('day', 7, 15), ('evening', 15, 23), ('night', 23, 7)]
    }
    
    shifts = shift_times.get(shift_pattern, [('day', 9, 17)])
    
    current_date = start_date
    while current_date <= end_date:
        # Skip weekends for standard pattern
        if shift_pattern == 'standard' and current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue
        
        # Assign employees to shifts
        for i, employee in enumerate(employees):
            # Check for time off
            has_time_off = VacationCalendar.query.filter_by(
                employee_id=employee.id,
                date=current_date.date()
            ).first()
            
            if not has_time_off:
                # Rotate through available shifts
                shift_type, start_hour, end_hour = shifts[i % len(shifts)]
                
                start_time = current_date.replace(hour=start_hour, minute=0, second=0)
                end_time = current_date.replace(hour=end_hour, minute=0, second=0)
                
                # Handle overnight shifts
                if end_hour < start_hour:
                    end_time += timedelta(days=1)
                
                schedule = Schedule(
                    employee_id=employee.id,
                    start_time=start_time,
                    end_time=end_time,
                    shift_type=shift_type,
                    position_id=employee.position_id
                )
                db.session.add(schedule)
                schedules_created += 1
                
                # Update circadian profile
                update_circadian_profile_on_schedule_change(employee.id, shift_type)
        
        current_date += timedelta(days=1)
    
    db.session.commit()
    flash(f'Successfully created {schedules_created} schedules!', 'success')
    return redirect(url_for('view_schedules'))

@app.route('/schedules')
@login_required
def view_schedules():
    # Get date range from query params
    start_date = request.args.get('start_date', datetime.now().date())
    end_date = request.args.get('end_date', (datetime.now() + timedelta(days=7)).date())
    
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Get schedules for the date range
    schedules = Schedule.query.filter(
        Schedule.start_time >= start_date,
        Schedule.start_time <= end_date
    ).order_by(Schedule.start_time).all()
    
    return render_template('view_schedules.html', 
                         schedules=schedules,
                         start_date=start_date,
                         end_date=end_date)

# ==================== TIME OFF MANAGEMENT ROUTES ====================

@app.route('/vacation/request', methods=['GET', 'POST'])
@login_required
def vacation_request():
    if request.method == 'POST':
        employee = Employee.query.get(current_user.id)
        
        # Parse form data
        leave_type = request.form.get('leave_type')
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        reason = request.form.get('reason')
        
        # Calculate days requested (excluding weekends)
        days_requested = 0
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:  # Monday = 0, Friday = 4
                days_requested += 1
            current += timedelta(days=1)
        
        # Check available balance
        if leave_type == 'vacation':
            available = employee.vacation_days_total - employee.vacation_days_used
        elif leave_type == 'sick':
            available = employee.sick_days_total - employee.sick_days_used
        else:  # personal
            available = employee.personal_days_total - employee.personal_days_used
        
        if days_requested > available:
            flash(f'Insufficient {leave_type} days. You have {available} days available.', 'danger')
            return redirect(url_for('vacation_request'))
        
        # Check for scheduling conflicts
        conflicts = Schedule.query.filter(
            Schedule.employee_id == employee.id,
            Schedule.start_time >= datetime.combine(start_date, datetime.min.time()),
            Schedule.start_time <= datetime.combine(end_date, datetime.max.time())
        ).all()
        
        # Create request
        time_off = TimeOffRequest(
            employee_id=employee.id,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            leave_type=leave_type,
            days_requested=days_requested,
            requires_coverage=len(conflicts) > 0
        )
        
        db.session.add(time_off)
        db.session.commit()
        
        flash(f'Time off request submitted for {days_requested} days!', 'success')
        return redirect(url_for('employee_dashboard'))
    
    employee = Employee.query.get(current_user.id)
    return render_template('vacation_request.html', employee=employee)

@app.route('/supervisor/time-off-requests')
@login_required
def time_off_requests():
    if current_user.role != 'supervisor':
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Get all pending requests
    pending_requests = TimeOffRequest.query.filter_by(status='pending').order_by(TimeOffRequest.submitted_at.desc()).all()
    
    # Get recently reviewed requests
    recent_requests = TimeOffRequest.query.filter(
        TimeOffRequest.status.in_(['approved', 'denied'])
    ).order_by(TimeOffRequest.reviewed_at.desc()).limit(10).all()
    
    return render_template('time_off_requests.html',
                         pending_requests=pending_requests,
                         recent_requests=recent_requests)

@app.route('/time-off-request/<int:request_id>/<action>', methods=['POST'])
@login_required
def handle_time_off_request(request_id, action):
    if current_user.role != 'supervisor':
        flash('Access denied.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    time_off = TimeOffRequest.query.get_or_404(request_id)
    
    if action == 'approve':
        time_off.status = 'approved'
        time_off.approved_by = current_user.id
        time_off.approved_at = datetime.now()
        time_off.reviewed_at = datetime.now()
        
        # Update employee's balance
        employee = Employee.query.get(time_off.employee_id)
        if time_off.leave_type == 'vacation':
            employee.vacation_days_used += time_off.days_requested
        elif time_off.leave_type == 'sick':
            employee.sick_days_used += time_off.days_requested
        else:
            employee.personal_days_used += time_off.days_requested
        
        # Add to vacation calendar
        current = time_off.start_date
        while current <= time_off.end_date:
            if current.weekday() < 5:  # Weekday
                calendar_entry = VacationCalendar(
                    employee_id=time_off.employee_id,
                    date=current,
                    leave_type=time_off.leave_type,
                    time_off_request_id=time_off.id
                )
                db.session.add(calendar_entry)
            current += timedelta(days=1)
        
        flash(f'Time off request approved for {employee.name}!', 'success')
    
    elif action == 'deny':
        time_off.status = 'denied'
        time_off.reviewed_at = datetime.now()
        supervisor_notes = request.form.get('notes', '')
        if supervisor_notes:
            time_off.supervisor_notes = supervisor_notes
        
        flash('Time off request denied.', 'info')
    
    db.session.commit()
    return redirect(url_for('time_off_requests'))

@app.route('/vacation/calendar')
@login_required
def vacation_calendar():
    # Get month from query params
    month = request.args.get('month', datetime.now().month, type=int)
    year = request.args.get('year', datetime.now().year, type=int)
    
    # Calculate date range
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)
    
    # Get all vacation calendar entries for the month
    calendar_entries = VacationCalendar.query.filter(
        VacationCalendar.date >= start_date,
        VacationCalendar.date <= end_date
    ).all()
    
    # Organize by date and employee
    calendar_data = {}
    for entry in calendar_entries:
        if entry.date not in calendar_data:
            calendar_data[entry.date] = []
        calendar_data[entry.date].append({
            'employee': entry.employee,
            'leave_type': entry.leave_type
        })
    
    return render_template('vacation_calendar.html',
                         month=month,
                         year=year,
                         calendar_data=calendar_data,
                         start_date=start_date,
                         end_date=end_date)

# ==================== SHIFT SWAP ROUTES ====================

@app.route('/swap-request', methods=['GET', 'POST'])
@login_required
def swap_request():
    if request.method == 'POST':
        employee = Employee.query.get(current_user.id)
        
        # Get form data
        requested_schedule_id = request.form.get('requested_schedule_id')
        offering_schedule_id = request.form.get('offering_schedule_id')
        target_employee_id = request.form.get('target_employee_id')
        reason = request.form.get('reason')
        
        # Validate schedules belong to correct employees
        requested_schedule = Schedule.query.get(requested_schedule_id)
        offering_schedule = Schedule.query.get(offering_schedule_id)
        
        if offering_schedule.employee_id != employee.id:
            flash('You can only offer your own shifts for swapping.', 'danger')
            return redirect(url_for('swap_request'))
        
        # Create swap request
        swap = ShiftSwapRequest(
            requesting_employee_id=employee.id,
            requested_schedule_id=requested_schedule_id,
            offering_schedule_id=offering_schedule_id,
            target_employee_id=target_employee_id if target_employee_id else requested_schedule.employee_id,
            reason=reason
        )
        
        db.session.add(swap)
        db.session.commit()
        
        flash('Swap request submitted for supervisor approval!', 'success')
        return redirect(url_for('employee_dashboard'))
    
    # GET request
    employee = Employee.query.get(current_user.id)
    
    # Get employee's upcoming schedules they can offer
    my_schedules = Schedule.query.filter(
        Schedule.employee_id == employee.id,
        Schedule.start_time > datetime.now()
    ).order_by(Schedule.start_time).all()
    
    # Get other employees' schedules they might want
    other_schedules = Schedule.query.filter(
        Schedule.employee_id != employee.id,
        Schedule.start_time > datetime.now()
    ).order_by(Schedule.start_time).all()
    
    return render_template('swap_request_form.html',
                         my_schedules=my_schedules,
                         other_schedules=other_schedules)

@app.route('/supervisor/swap-requests')
@login_required
def swap_requests():
    if current_user.role != 'supervisor':
        flash('Access denied.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').all()
    recent_swaps = ShiftSwapRequest.query.filter(
        ShiftSwapRequest.status.in_(['approved', 'denied'])
    ).order_by(ShiftSwapRequest.reviewed_at.desc()).limit(10).all()
    
    return render_template('swap_requests.html',
                         pending_swaps=pending_swaps,
                         recent_swaps=recent_swaps)

@app.route('/swap-request/<int:swap_id>/<action>', methods=['POST'])
@login_required
def handle_swap_request(swap_id, action):
    if current_user.role != 'supervisor':
        flash('Access denied.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    swap = ShiftSwapRequest.query.get_or_404(swap_id)
    
    if action == 'approve':
        # Swap the employee IDs in the schedules
        requested_schedule = Schedule.query.get(swap.requested_schedule_id)
        offering_schedule = Schedule.query.get(swap.offering_schedule_id)
        
        # Store original employee IDs
        requested_emp_id = requested_schedule.employee_id
        offering_emp_id = offering_schedule.employee_id
        
        # Perform the swap
        requested_schedule.employee_id = offering_emp_id
        offering_schedule.employee_id = requested_emp_id
        
        swap.status = 'approved'
        swap.reviewed_at = datetime.now()
        swap.reviewed_by = current_user.id
        
        flash('Shift swap approved!', 'success')
    
    elif action == 'deny':
        swap.status = 'denied'
        swap.reviewed_at = datetime.now()
        swap.reviewed_by = current_user.id
        
        flash('Shift swap denied.', 'info')
    
    db.session.commit()
    return redirect(url_for('swap_requests'))

# ==================== SUGGESTIONS ROUTES ====================

@app.route('/submit-suggestion', methods=['GET', 'POST'])
@login_required
def submit_suggestion():
    if request.method == 'POST':
        suggestion = ScheduleSuggestion(
            employee_id=current_user.id,
            suggestion_type=request.form.get('suggestion_type'),
            description=request.form.get('description'),
            priority=request.form.get('priority', 'medium')
        )
        
        db.session.add(suggestion)
        db.session.commit()
        
        flash('Thank you for your suggestion! A supervisor will review it soon.', 'success')
        return redirect(url_for('employee_dashboard'))
    
    return render_template('submit_suggestion.html')

@app.route('/supervisor/suggestions')
@login_required
def view_suggestions():
    if current_user.role != 'supervisor':
        flash('Access denied.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    pending_suggestions = ScheduleSuggestion.query.filter_by(status='pending').order_by(
        ScheduleSuggestion.submitted_at.desc()
    ).all()
    
    reviewed_suggestions = ScheduleSuggestion.query.filter(
        ScheduleSuggestion.status.in_(['implemented', 'rejected', 'reviewing'])
    ).order_by(ScheduleSuggestion.reviewed_at.desc()).limit(20).all()
    
    return render_template('suggestions.html',
                         pending_suggestions=pending_suggestions,
                         reviewed_suggestions=reviewed_suggestions)

@app.route('/suggestion/<int:suggestion_id>/<action>', methods=['POST'])
@login_required
def handle_suggestion(suggestion_id, action):
    if current_user.role != 'supervisor':
        flash('Access denied.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    suggestion = ScheduleSuggestion.query.get_or_404(suggestion_id)
    
    if action in ['reviewing', 'implemented', 'rejected']:
        suggestion.status = action
        suggestion.reviewed_at = datetime.now()
        suggestion.reviewed_by = current_user.id
        
        response = request.form.get('response')
        if response:
            suggestion.response = response
        
        db.session.commit()
        flash(f'Suggestion marked as {action}.', 'success')
    
    return redirect(url_for('view_suggestions'))

# ==================== CASUAL WORKER ROUTES ====================

@app.route('/register-casual', methods=['GET', 'POST'])
def register_casual():
    if request.method == 'POST':
        # Check if email already exists
        existing = CasualWorker.query.filter_by(email=request.form.get('email')).first()
        if existing:
            flash('Email already registered!', 'danger')
            return redirect(url_for('register_casual'))
        
        casual = CasualWorker(
            name=request.form.get('name'),
            email=request.form.get('email'),
            phone=request.form.get('phone'),
            skills=request.form.get('skills'),
            availability=request.form.get('availability'),
            hourly_rate=float(request.form.get('hourly_rate', 15.0))
        )
        
        db.session.add(casual)
        db.session.commit()
        
        flash('Registration successful! A supervisor will contact you about available shifts.', 'success')
        return redirect(url_for('index'))
    
    return render_template('register_casual.html')

@app.route('/casual-workers')
@login_required
def casual_workers():
    if current_user.role != 'supervisor':
        flash('Access denied.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    workers = CasualWorker.query.filter_by(is_active=True).all()
    return render_template('casual_workers.html', workers=workers)

# ==================== SLEEP AND CIRCADIAN RHYTHM ROUTES ====================

@app.route('/sleep-dashboard')
@login_required
def sleep_dashboard():
    """Display personalized sleep and circadian rhythm dashboard"""
    employee = Employee.query.get(current_user.id)
    
    # Get or create circadian profile
    profile = CircadianProfile.query.filter_by(employee_id=employee.id).first()
    if not profile:
        # Create new profile - in production, this would be after a questionnaire
        profile = CircadianProfile(
            employee_id=employee.id,
            chronotype='intermediate',  # Default, should be assessed
            chronotype_score=0.0,
            current_shift_type='day',  # Should detect from schedule
            days_on_current_pattern=0
        )
        db.session.add(profile)
        db.session.commit()
    
    # Initialize advisor
    advisor = CircadianAdvisor(employee, profile)
    
    # Get circadian phase information
    phase_info = advisor.calculate_circadian_phase()
    
    # Get recent sleep logs for debt calculation
    recent_logs = SleepLog.query.filter_by(
        circadian_profile_id=profile.id
    ).order_by(SleepLog.sleep_date.desc()).limit(7).all()
    
    sleep_debt = advisor.calculate_sleep_debt(recent_logs)
    
    # Calculate average sleep quality
    if recent_logs:
        avg_sleep_quality = sum(log.sleep_quality or 0 for log in recent_logs) / len(recent_logs)
    else:
        avg_sleep_quality = 0
    
    # Get or generate recommendations
    existing_recs = SleepRecommendation.query.filter_by(
        circadian_profile_id=profile.id,
        was_viewed=False
    ).filter(
        SleepRecommendation.valid_until > datetime.now()
    ).all()
    
    if len(existing_recs) < 3:
        # Generate new recommendations
        new_recs = advisor.generate_sleep_recommendations()
        for rec_data in new_recs:
            if not any(r.title == rec_data['title'] for r in existing_recs):
                rec = SleepRecommendation(
                    circadian_profile_id=profile.id,
                    recommendation_type=rec_data['type'],
                    priority=rec_data['priority'],
                    title=rec_data['title'],
                    description=rec_data['description'],
                    action_items=rec_data['action_items'],
                    valid_from=datetime.now(),
                    valid_until=datetime.now() + timedelta(days=7)
                )
                db.session.add(rec)
        db.session.commit()
        
        # Re-fetch recommendations
        existing_recs = SleepRecommendation.query.filter_by(
            circadian_profile_id=profile.id
        ).filter(
            SleepRecommendation.valid_until > datetime.now()
        ).order_by(
            db.case(
                (SleepRecommendation.priority == 'critical', 1),
                (SleepRecommendation.priority == 'high', 2),
                (SleepRecommendation.priority == 'medium', 3),
                (SleepRecommendation.priority == 'low', 4),
                else_=5
            )
        ).limit(5).all()
    
    # Get next shift
    next_shift = Schedule.query.filter(
        Schedule.employee_id == employee.id,
        Schedule.start_time > datetime.now()
    ).order_by(Schedule.start_time).first()
    
    # Calculate hours until next shift and sleep recommendations
    if next_shift:
        hours_until_shift = (next_shift.start_time - datetime.now()).total_seconds() / 3600
        
        # Calculate recommended sleep times based on shift
        if next_shift.shift_type == 'night':
            recommended_bedtime = "3:00 PM"
            recommended_wake_time = "10:30 PM"
            nap_recommended = True
            nap_time = "7:00 PM - 8:30 PM"
            nap_duration = 90
        elif next_shift.shift_type == 'evening':
            recommended_bedtime = "2:00 AM"
            recommended_wake_time = "10:00 AM"
            nap_recommended = True
            nap_time = "1:00 PM - 1:30 PM"
            nap_duration = 30
        else:  # day shift
            recommended_bedtime = "10:00 PM"
            recommended_wake_time = "6:00 AM"
            nap_recommended = False
            nap_time = None
            nap_duration = None
    else:
        hours_until_shift = None
        recommended_bedtime = None
        recommended_wake_time = None
        nap_recommended = False
        nap_time = None
        nap_duration = None
    
    return render_template('sleep_dashboard.html',
                         employee=employee,
                         profile=profile,
                         phase_info=phase_info,
                         sleep_debt=sleep_debt,
                         avg_sleep_quality=round(avg_sleep_quality, 1),
                         recommendations=existing_recs,
                         next_shift=next_shift,
                         hours_until_shift=round(hours_until_shift, 1) if hours_until_shift else None,
                         recommended_bedtime=recommended_bedtime,
                         recommended_wake_time=recommended_wake_time,
                         nap_recommended=nap_recommended,
                         nap_time=nap_time,
                         nap_duration=nap_duration)

@app.route('/sleep-log', methods=['GET', 'POST'])
@login_required
def sleep_log():
    """Log sleep data"""
    employee = Employee.query.get(current_user.id)
    profile = CircadianProfile.query.filter_by(employee_id=employee.id).first()
    
    if not profile:
        flash('Please complete your sleep profile first.', 'warning')
        return redirect(url_for('sleep_profile'))
    
    if request.method == 'POST':
        # Parse form data
        sleep_date = datetime.strptime(request.form['sleep_date'], '%Y-%m-%d').date()
        bedtime = datetime.strptime(f"{request.form['sleep_date']} {request.form['bedtime']}", '%Y-%m-%d %H:%M')
        wake_time = datetime.strptime(f"{request.form['wake_date']} {request.form['wake_time']}", '%Y-%m-%d %H:%M')
        
        # Calculate duration
        duration = (wake_time - bedtime).total_seconds() / 3600
        if duration < 0:  # Crossed midnight
            duration += 24
        
        # Create sleep log
        log = SleepLog(
            circadian_profile_id=profile.id,
            sleep_date=sleep_date,
            bedtime=bedtime,
            wake_time=wake_time,
            sleep_duration=duration,
            sleep_quality=int(request.form['sleep_quality']),
            sleep_efficiency=float(request.form.get('sleep_efficiency', 85)),
            pre_sleep_light_exposure=request.form.get('light_exposure', 'moderate'),
            took_nap=request.form.get('took_nap') == 'on',
            nap_duration=int(request.form.get('nap_duration', 0)) if request.form.get('took_nap') == 'on' else None
        )
        
        # Check if worked before sleep
        last_shift = Schedule.query.filter(
            Schedule.employee_id == employee.id,
            Schedule.end_time < bedtime,
            Schedule.end_time > bedtime - timedelta(hours=24)
        ).order_by(Schedule.end_time.desc()).first()
        
        if last_shift:
            log.worked_before_sleep = True
            log.shift_type_before_sleep = last_shift.shift_type
            log.hours_since_last_shift = (bedtime - last_shift.end_time).total_seconds() / 3600
        
        db.session.add(log)
        
        # Update circadian profile sleep debt
        advisor = CircadianAdvisor(employee, profile)
        recent_logs = SleepLog.query.filter_by(
            circadian_profile_id=profile.id
        ).order_by(SleepLog.sleep_date.desc()).limit(7).all()
        
        profile.cumulative_sleep_debt = advisor.calculate_sleep_debt(recent_logs)
        profile.last_sleep_debt_update = datetime.now()
        
        db.session.commit()
        flash('Sleep log recorded successfully!', 'success')
        return redirect(url_for('sleep_dashboard'))
    
    # GET request - show form
    return render_template('sleep_log_form.html', employee=employee)

@app.route('/sleep-profile', methods=['GET', 'POST'])
@login_required
def sleep_profile():
    """Initial sleep profile assessment"""
    employee = Employee.query.get(current_user.id)
    
    if request.method == 'POST':
        # Process chronotype assessment
        morning_preference = int(request.form['morning_preference'])
        energy_peak = request.form['energy_peak']
        natural_bedtime = int(request.form['natural_bedtime'])
        
        # Create advisor temporarily to assess chronotype
        temp_profile = CircadianProfile(employee_id=employee.id)
        advisor = CircadianAdvisor(employee, temp_profile)
        
        chronotype, score = advisor.assess_chronotype(
            morning_preference, energy_peak, natural_bedtime
        )
        
        # Create or update profile
        profile = CircadianProfile.query.filter_by(employee_id=employee.id).first()
        if not profile:
            profile = CircadianProfile(employee_id=employee.id)
        
        profile.chronotype = chronotype
        profile.chronotype_score = score
        
        # Detect current shift pattern from recent schedules
        recent_shift = Schedule.query.filter(
            Schedule.employee_id == employee.id,
            Schedule.start_time < datetime.now(),
            Schedule.end_time > datetime.now() - timedelta(days=7)
        ).order_by(Schedule.start_time.desc()).first()
        
        if recent_shift:
            profile.current_shift_type = recent_shift.shift_type
        
        db.session.add(profile)
        db.session.commit()
        
        flash(f'Profile created! You are {chronotype} chronotype.', 'success')
        return redirect(url_for('sleep_dashboard'))
    
    return render_template('sleep_profile_form.html', employee=employee)

@app.route('/sleep-recommendation/<int:rec_id>/viewed', methods=['POST'])
@login_required
def mark_recommendation_viewed(rec_id):
    """Mark a recommendation as viewed"""
    rec = SleepRecommendation.query.get_or_404(rec_id)
    
    # Verify ownership
    profile = CircadianProfile.query.filter_by(employee_id=current_user.id).first()
    if rec.circadian_profile_id != profile.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    rec.was_viewed = True
    rec.viewed_at = datetime.now()
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/sleep-transition-plan', methods=['GET', 'POST'])
@login_required
def sleep_transition_plan():
    """Create a plan for transitioning between shift types"""
    employee = Employee.query.get(current_user.id)
    profile = CircadianProfile.query.filter_by(employee_id=employee.id).first()
    
    if not profile:
        flash('Please complete your sleep profile first.', 'warning')
        return redirect(url_for('sleep_profile'))
    
    if request.method == 'POST':
        from_shift = request.form['from_shift']
        to_shift = request.form['to_shift']
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
        
        # Generate transition plan
        advisor = CircadianAdvisor(employee, profile)
        plan_data = advisor.generate_transition_plan(from_shift, to_shift, start_date)
        
        # Save plan
        plan = ShiftTransitionPlan(
            circadian_profile_id=profile.id,
            from_shift_type=from_shift,
            to_shift_type=to_shift,
            transition_start_date=start_date.date(),
            transition_duration_days=plan_data['duration_days'],
            plan_data=plan_data
        )
        
        db.session.add(plan)
        db.session.commit()
        
        flash('Transition plan created! Follow the daily recommendations.', 'success')
        return redirect(url_for('view_transition_plan', plan_id=plan.id))
    
    return render_template('transition_plan_form.html', employee=employee, profile=profile)

@app.route('/transition-plan/<int:plan_id>')
@login_required
def view_transition_plan(plan_id):
    """View a specific transition plan"""
    plan = ShiftTransitionPlan.query.get_or_404(plan_id)
    
    # Verify ownership
    profile = CircadianProfile.query.filter_by(employee_id=current_user.id).first()
    if plan.circadian_profile_id != profile.id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('sleep_dashboard'))
    
    employee = Employee.query.get(current_user.id)
    
    # Calculate current progress
    days_elapsed = (datetime.now().date() - plan.transition_start_date).days
    plan.completion_percentage = min(100, (days_elapsed / plan.transition_duration_days) * 100)
    db.session.commit()
    
    return render_template('view_transition_plan.html', 
                         employee=employee, 
                         plan=plan,
                         days_elapsed=days_elapsed,
                         timedelta=timedelta)

@app.route('/api/critical-sleep-alerts')
@login_required
def critical_sleep_alerts():
    """API endpoint to get count of critical sleep recommendations"""
    profile = CircadianProfile.query.filter_by(employee_id=current_user.id).first()
    
    if not profile:
        return jsonify({'critical_count': 0})
    
    critical_count = SleepRecommendation.query.filter_by(
        circadian_profile_id=profile.id,
        priority='critical',
        was_viewed=False
    ).filter(
        SleepRecommendation.valid_until > datetime.now()
    ).count()
    
    return jsonify({'critical_count': critical_count})

# ==================== HELPER FUNCTIONS ====================

def update_circadian_profile_on_schedule_change(employee_id, new_shift_type):
    """Helper function to update circadian profile when schedule changes"""
    profile = CircadianProfile.query.filter_by(employee_id=employee_id).first()
    if profile:
        if profile.current_shift_type != new_shift_type:
            profile.last_shift_change = datetime.now()
            profile.current_shift_type = new_shift_type
            profile.days_on_current_pattern = 0
            profile.circadian_adaptation_score = 0.0
        else:
            profile.days_on_current_pattern += 1
            # Update adaptation score
            advisor = CircadianAdvisor(Employee.query.get(employee_id), profile)
            phase_info = advisor.calculate_circadian_phase()
            profile.circadian_adaptation_score = phase_info['adaptation']
        
        profile.updated_at = datetime.now()
        db.session.commit()

# ==================== DEBUG AND UTILITY ROUTES ====================

@app.route('/debug-employees')
@login_required
def debug_employees():
    if current_user.role != 'supervisor':
        flash('Access denied.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    employees = Employee.query.all()
    return render_template('debug_employees.html', employees=employees)

@app.route('/reset-passwords')
def reset_passwords():
    """Reset all passwords to 'password123' for testing"""
    if request.args.get('confirm') != 'yes':
        return 'Add ?confirm=yes to reset all passwords'
    
    employees = Employee.query.all()
    for emp in employees:
        emp.password = generate_password_hash('password123')
    
    db.session.commit()
    return f'Reset {len(employees)} passwords to "password123"'

@app.route('/migrate-database')
def migrate_database():
    """Create/update database schema"""
    if request.args.get('confirm') != 'yes':
        return 'Add ?confirm=yes to migrate database'
    
    with app.app_context():
        # Drop all tables and recreate
        db.drop_all()
        db.create_all()
        
        # Create default positions
        positions = [
            Position(name='Nurse', department='Healthcare'),
            Position(name='Doctor', department='Healthcare'),
            Position(name='Security Officer', department='Security'),
            Position(name='Maintenance Tech', department='Facilities'),
            Position(name='Customer Service Rep', department='Support')
        ]
        for pos in positions:
            db.session.add(pos)
        
        # Create default skills
        skills = [
            Skill(name='CPR Certified', description='Current CPR certification'),
            Skill(name='Forklift Operator', description='Licensed forklift operator'),
            Skill(name='Bilingual', description='Fluent in multiple languages'),
            Skill(name='Leadership', description='Team leadership experience'),
            Skill(name='Emergency Response', description='Emergency response training')
        ]
        for skill in skills:
            db.session.add(skill)
        
        db.session.commit()
        
        # Create supervisor account
        supervisor = Employee(
            name='Mike Supervisor',
            email='mike@example.com',
            password=generate_password_hash('admin123'),
            role='supervisor',
            position_id=1,
            department='Management',
            hire_date=date(2020, 1, 15),
            phone='555-0100'
        )
        db.session.add(supervisor)
        
        # Create test employees with different crews
        employees = [
            ('John Smith', 'john@example.com', 'A'),
            ('Jane Doe', 'jane@example.com', 'B'),
            ('Bob Wilson', 'bob@example.com', 'C'),
            ('Alice Johnson', 'alice@example.com', 'D'),
            ('Charlie Brown', 'charlie@example.com', 'A'),
            ('Diana Prince', 'diana@example.com', 'B'),
            ('Eve Adams', 'eve@example.com', 'C'),
            ('Frank Castle', 'frank@example.com', 'D')
        ]
        
        for i, (name, email, crew) in enumerate(employees):
            emp = Employee(
                name=name,
                email=email,
                password=generate_password_hash('password123'),
                role='employee',
                position_id=(i % 5) + 1,
                department=['Healthcare', 'Security', 'Facilities', 'Support'][i % 4],
                hire_date=date(2021, (i % 12) + 1, 15),
                phone=f'555-{1000 + i}',
                crew=crew,
                vacation_days_total=15,
                vacation_days_used=0,
                sick_days_total=10,
                sick_days_used=0,
                personal_days_total=3,
                personal_days_used=0
            )
            db.session.add(emp)
        
        db.session.commit()
        
        # Add some sample schedules
        employees = Employee.query.filter_by(role='employee').all()
        start_date = datetime.now().replace(hour=7, minute=0, second=0, microsecond=0)
        
        for i, emp in enumerate(employees):
            # Create a week of schedules
            for day in range(7):
                if day < 5:  # Weekdays only for now
                    shift_start = start_date + timedelta(days=day)
                    shift_end = shift_start + timedelta(hours=8)
                    
                    schedule = Schedule(
                        employee_id=emp.id,
                        start_time=shift_start,
                        end_time=shift_end,
                        shift_type='day',
                        position_id=emp.position_id
                    )
                    db.session.add(schedule)
        
        db.session.commit()
        
        return 'Database migrated successfully! Supervisor: mike@example.com / admin123, Employee: john@example.com / password123'

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
    with app.app_context():
        db.create_all()
    app.run(debug=True)
