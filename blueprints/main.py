from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from models import db, Employee, TimeOffRequest, ShiftSwapRequest, ScheduleSuggestion, MaintenanceIssue, Schedule, VacationCalendar, PositionMessage, PositionMessageRead
from datetime import date, timedelta
from sqlalchemy import func
from utils.helpers import get_coverage_gaps

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Redirect to appropriate dashboard based on user role"""
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('main.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    return redirect(url_for('auth.login'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Supervisor dashboard with real statistics"""
    if not current_user.is_supervisor:
        return redirect(url_for('main.employee_dashboard'))
    
    # Calculate pending time off requests
    pending_time_off = TimeOffRequest.query.filter_by(
        status='pending'
    ).count()
    
    # Calculate pending swap requests
    pending_swaps = ShiftSwapRequest.query.filter_by(
        status='pending'
    ).count()
    
    # Calculate coverage gaps for the next 7 days
    gaps = get_coverage_gaps('ALL', 7)
    coverage_gaps = len(gaps)
    
    # Calculate pending suggestions
    pending_suggestions = ScheduleSuggestion.query.filter_by(
        status='new'
    ).count()
    
    # Get total employee count
    total_employees = Employee.query.count()
    
    # Get critical maintenance issues
    critical_maintenance = MaintenanceIssue.query.filter_by(
        status='open',
        priority='critical'
    ).count()
    
    # Get today's schedule statistics
    today_scheduled = Schedule.query.filter_by(
        date=date.today()
    ).count()
    
    # Get employees on leave today
    today_on_leave = VacationCalendar.query.filter_by(
        date=date.today()
    ).count()
    
    return render_template('dashboard.html',
                         pending_time_off=pending_time_off,
                         pending_swaps=pending_swaps,
                         coverage_gaps=coverage_gaps,
                         pending_suggestions=pending_suggestions,
                         total_employees=total_employees,
                         critical_maintenance=critical_maintenance,
                         today_scheduled=today_scheduled,
                         today_on_leave=today_on_leave)

@main_bp.route('/employee-dashboard')
@login_required
def employee_dashboard():
    """Employee dashboard"""
    if current_user.is_supervisor:
        return redirect(url_for('main.dashboard'))
    
    # Get employee's upcoming schedule
    upcoming_schedules = Schedule.query.filter(
        Schedule.employee_id == current_user.id,
        Schedule.date >= date.today(),
        Schedule.date <= date.today() + timedelta(days=14)
    ).order_by(Schedule.date).all()
    
    # Get pending requests
    pending_time_off = TimeOffRequest.query.filter_by(
        employee_id=current_user.id,
        status='pending'
    ).count()
    
    pending_swaps = ShiftSwapRequest.query.filter_by(
        requester_id=current_user.id,
        status='pending'
    ).count()
    
    # Get time off balances
    balances = {
        'vacation': current_user.vacation_days,
        'sick': current_user.sick_days,
        'personal': current_user.personal_days
    }
    
    # Get next shift
    next_shift = Schedule.query.filter(
        Schedule.employee_id == current_user.id,
        Schedule.date >= date.today()
    ).order_by(Schedule.date).first()
    
    # Get overtime stats
    current_week_ot = current_user.current_week_overtime
    avg_weekly_ot = current_user.average_weekly_overtime
    
    # Check for unread messages
    unread_messages = 0
    if current_user.position_id:
        position_messages = PositionMessage.query.filter_by(
            position_id=current_user.position_id
        ).all()
        
        for msg in position_messages:
            if not msg.is_read_by(current_user.id):
                unread_messages += 1
    
    return render_template('employee_dashboard.html',
                         upcoming_schedules=upcoming_schedules,
                         pending_time_off=pending_time_off,
                         pending_swaps=pending_swaps,
                         balances=balances,
                         next_shift=next_shift,
                         current_week_ot=current_week_ot,
                         avg_weekly_ot=avg_weekly_ot,
                         unread_messages=unread_messages)

# ========== REDIRECT OLD ROUTES ==========

@main_bp.route('/upload-employees')
@login_required
def old_upload_redirect():
    """Redirect old upload route to new employee management"""
    if current_user.is_supervisor:
        return redirect(url_for('supervisor.employee_management'))
    else:
        return redirect(url_for('main.dashboard'))

@main_bp.route('/employees/upload')
@login_required
def old_upload_redirect2():
    """Redirect another old upload route to new employee management"""
    if current_user.is_supervisor:
        return redirect(url_for('supervisor.employee_management'))
    else:
        return redirect(url_for('main.dashboard'))

# ========== OTHER UTILITY ROUTES ==========

@main_bp.route('/view-employees-crews')
@login_required
def view_employees_crews():
    """Redirect to crew management"""
    if current_user.is_supervisor:
        return redirect(url_for('supervisor.crew_management'))
    else:
        # Non-supervisors can view but not edit
        employees = Employee.query.order_by(Employee.crew, Employee.name).all()
        return render_template('view_employees_crews.html', employees=employees)
