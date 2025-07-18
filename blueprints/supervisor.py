from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, Employee, Position, Skill, Schedule, TimeOffRequest, VacationCalendar, CoverageRequest, ShiftSwapRequest, ScheduleSuggestion
from datetime import datetime, timedelta, date
from sqlalchemy import func

supervisor_bp = Blueprint('supervisor', __name__, url_prefix='/supervisor')

def check_supervisor():
    """Check if current user is a supervisor"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return False
    return True

@supervisor_bp.route('/coverage-needs')
@login_required
def coverage_needs():
    """View and adjust coverage needs"""
    if not check_supervisor():
        return redirect(url_for('main.employee_dashboard'))
    
    # Get date range
    start_date = request.args.get('start_date', date.today())
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    end_date = start_date + timedelta(days=30)
    
    # Get all positions and their requirements
    positions = Position.query.all()
    
    # Get all skills
    skills = Skill.query.all()
    
    # Calculate coverage for each position
    coverage_data = []
    current = start_date
    while current <= end_date:
        for position in positions:
            # Count scheduled employees for this position and date
            scheduled = Schedule.query.filter_by(
                position_id=position.id,
                date=current
            ).count()
            
            coverage_data.append({
                'date': current,
                'position': position,
                'scheduled': scheduled,
                'required': position.min_coverage or 2,
                'gap': (position.min_coverage or 2) - scheduled
            })
        current += timedelta(days=1)
    
    # Get open coverage requests
    open_requests = CoverageRequest.query.filter_by(status='open').all()
    
    # Get casual workers
    from models import CasualWorker
    casual_workers = CasualWorker.query.filter_by(is_active=True).all()
    
    return render_template('adjust_coverage.html',
                         positions=positions,
                         skills=skills,
                         coverage_data=coverage_data,
                         start_date=start_date,
                         end_date=end_date,
                         open_requests=open_requests,
                         casual_workers=casual_workers)

@supervisor_bp.route('/time-off-requests')
@login_required
def time_off_requests():
    """Review and manage time off requests"""
    if not check_supervisor():
        return redirect(url_for('main.employee_dashboard'))
    
    # Get pending requests
    pending_requests = TimeOffRequest.query.filter_by(status='pending').order_by(TimeOffRequest.submitted_date.desc()).all()
    
    # Get recently processed requests
    recent_requests = TimeOffRequest.query.filter(
        TimeOffRequest.status.in_(['approved', 'denied'])
    ).order_by(TimeOffRequest.submitted_date.desc()).limit(20).all()
    
    return render_template('time_off_requests.html',
                         pending_requests=pending_requests,
                         recent_requests=recent_requests)

@supervisor_bp.route('/swap-requests')
@login_required
def swap_requests():
    """View and manage shift swap requests"""
    if not check_supervisor():
        return redirect(url_for('main.employee_dashboard'))
    
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

@supervisor_bp.route('/suggestions')
@login_required
def suggestions():
    """View employee suggestions"""
    if not check_supervisor():
        return redirect(url_for('main.employee_dashboard'))
    
    # Get all suggestions
    all_suggestions = ScheduleSuggestion.query.order_by(ScheduleSuggestion.submitted_date.desc()).all()
    
    return render_template('suggestions.html', suggestions=all_suggestions)

@supervisor_bp.route('/coverage-gaps')
@login_required
def coverage_gaps():
    """View detailed coverage gaps analysis"""
    if not check_supervisor():
        return redirect(url_for('main.employee_dashboard'))
    
    # Get filter parameters
    selected_crew = request.args.get('crew', 'ALL')
    days_ahead = int(request.args.get('days_ahead', 7))
    shift_type = request.args.get('shift_type', '')
    
    # Get coverage gaps
    from utils.helpers import get_coverage_gaps
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

@supervisor_bp.route('/fill-gap')
@login_required
def fill_gap():
    """Fill a specific coverage gap"""
    if not check_supervisor():
        return redirect(url_for('main.employee_dashboard'))
    
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
    from models import CasualWorker
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

@supervisor_bp.route('/overtime-distribution')
@login_required
def overtime_distribution():
    """Smart overtime distribution interface"""
    if not check_supervisor():
        return redirect(url_for('main.employee_dashboard'))
    
    # Get upcoming overtime opportunities
    from utils.helpers import get_overtime_opportunities, get_overtime_eligible_employees
    overtime_opportunities = get_overtime_opportunities()
    
    # Get eligible employees for overtime
    eligible_employees = get_overtime_eligible_employees()
    
    return render_template('overtime_distribution.html',
                         opportunities=overtime_opportunities,
                         eligible_employees=eligible_employees)

@supervisor_bp.route('/messages')
@login_required
def supervisor_messages():
    """View and send messages to other supervisors"""
    if not check_supervisor():
        return redirect(url_for('main.employee_dashboard'))
    
    from models import SupervisorMessage
    
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

@supervisor_bp.route('/todays-schedule')
@login_required
def todays_schedule():
    """Redirect to schedule view for today"""
    if not check_supervisor():
        return redirect(url_for('main.employee_dashboard'))
    
    # Redirect to schedule view with today's date
    return redirect(url_for('schedule.view_schedules', 
                          start_date=date.today().strftime('%Y-%m-%d'),
                          end_date=date.today().strftime('%Y-%m-%d'),
                          crew=current_user.crew or 'ALL'))

@supervisor_bp.route('/create-schedule')
@login_required
def supervisor_create_schedule():
    """Redirect to schedule creation"""
    if not check_supervisor():
        return redirect(url_for('main.employee_dashboard'))
    
    return redirect(url_for('schedule.create_schedule'))
