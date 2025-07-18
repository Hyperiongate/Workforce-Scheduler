from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Employee, Schedule, TimeOffRequest, ShiftSwapRequest, ScheduleSuggestion, Position, ShiftTradePost, CircadianProfile, CoverageNotification
from datetime import datetime, timedelta, date, time
from sqlalchemy import func, or_

main_bp = Blueprint('main', __name__)

def calculate_time_ago(timestamp):
    """Calculate how long ago a timestamp was"""
    if not timestamp:
        return "Unknown time"
    
    from datetime import datetime
    now = datetime.now()
    
    if hasattr(timestamp, 'date'):
        time_diff = now - timestamp
    else:
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

@main_bp.route('/dashboard')
@login_required
def dashboard():
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.')
        return redirect(url_for('main.employee_dashboard'))
    
    # Get crew filter
    selected_crew = request.args.get('crew', '')
    
    # Base query for employees
    employees_query = Employee.query
    if selected_crew:
        employees_query = employees_query.filter_by(crew=selected_crew)
    
    employees = employees_query.all()
    total_employees = len(employees)
    
    # Calculate on duty now
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
            'position_name': schedule.position.name if schedule.position else 'Unknown',
            'employee_name': schedule.employee.name,
            'start_time': schedule.start_time.strftime('%H:%M'),
            'end_time': schedule.end_time.strftime('%H:%M')
        })
    
    # Calculate coverage gaps
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
    
    # Get other supervisors
    supervisors = Employee.query.filter_by(is_supervisor=True).all()
    
    # Get positions
    positions = Position.query.all()
    
    # Get recent activities
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
    
    recent_activities = recent_activities[:10]
    
    # Count active users
    active_users = 1  # At least current user
    
    # Count active trades
    try:
        active_trades = ShiftTradePost.query.filter_by(status='active').count()
    except:
        active_trades = 0
    
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

@main_bp.route('/employee-dashboard')
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
