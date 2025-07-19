from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from models import db, Schedule, Employee, Position, TimeOffRequest, ShiftSwapRequest, ScheduleSuggestion, VacationCalendar
from datetime import datetime, date, timedelta
from sqlalchemy import func, case
from functools import wraps
import calendar
import io
import csv

supervisor_bp = Blueprint('supervisor', __name__)

# Decorator to require supervisor privileges
def supervisor_required(f):
    """Decorator to require supervisor privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_supervisor:
            flash('You must be a supervisor to access this page.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@supervisor_bp.route('/vacation-calendar')
@login_required
@supervisor_required
def vacation_calendar():
    """Display the vacation calendar view"""
    return render_template('vacation_calendar.html')

@supervisor_bp.route('/api/vacation-calendar')
@login_required
@supervisor_required
def api_vacation_calendar():
    """API endpoint to get vacation calendar data"""
    year = int(request.args.get('year', date.today().year))
    month = int(request.args.get('month', date.today().month))
    crew = request.args.get('crew', 'ALL')
    
    # Calculate date range for the month
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)
    
    # Query time off requests and vacation calendar entries
    query = db.session.query(
        VacationCalendar.employee_id,
        VacationCalendar.date,
        VacationCalendar.type,
        Employee.name.label('employee_name'),
        Employee.crew,
        TimeOffRequest.reason
    ).join(
        Employee, VacationCalendar.employee_id == Employee.id
    ).outerjoin(
        TimeOffRequest, VacationCalendar.request_id == TimeOffRequest.id
    ).filter(
        VacationCalendar.date >= start_date,
        VacationCalendar.date <= end_date
    )
    
    if crew != 'ALL':
        query = query.filter(Employee.crew == crew)
    
    # Group consecutive dates for the same employee and type
    calendar_entries = query.order_by(
        VacationCalendar.employee_id,
        VacationCalendar.date
    ).all()
    
    # Process results to group consecutive dates
    grouped_data = []
    current_group = None
    
    for entry in calendar_entries:
        if (current_group is None or 
            current_group['employee_id'] != entry.employee_id or
            current_group['type'] != entry.type or
            (entry.date - datetime.strptime(current_group['end_date'], '%Y-%m-%d').date()).days > 1):
            
            # Start new group
            if current_group:
                grouped_data.append(current_group)
            
            current_group = {
                'employee_id': entry.employee_id,
                'employee_name': entry.employee_name,
                'crew': entry.crew,
                'type': entry.type,
                'start_date': entry.date.strftime('%Y-%m-%d'),
                'end_date': entry.date.strftime('%Y-%m-%d'),
                'reason': entry.reason
            }
        else:
            # Extend current group
            current_group['end_date'] = entry.date.strftime('%Y-%m-%d')
    
    if current_group:
        grouped_data.append(current_group)
    
    return jsonify(grouped_data)

@supervisor_bp.route('/api/vacation-calendar/export')
@login_required
@supervisor_required
def export_vacation_calendar():
    """Export vacation calendar as CSV"""
    year = int(request.args.get('year', date.today().year))
    month = int(request.args.get('month', date.today().month))
    crew = request.args.get('crew', 'ALL')
    
    # Get calendar data
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)
    
    query = db.session.query(
        Employee.name,
        Employee.crew,
        VacationCalendar.date,
        VacationCalendar.type,
        TimeOffRequest.reason
    ).join(
        Employee, VacationCalendar.employee_id == Employee.id
    ).outerjoin(
        TimeOffRequest, VacationCalendar.request_id == TimeOffRequest.id
    ).filter(
        VacationCalendar.date >= start_date,
        VacationCalendar.date <= end_date
    ).order_by(
        Employee.name,
        VacationCalendar.date
    )
    
    if crew != 'ALL':
        query = query.filter(Employee.crew == crew)
    
    entries = query.all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Employee Name', 'Crew', 'Date', 'Type', 'Reason'])
    
    # Write data
    for entry in entries:
        writer.writerow([
            entry.name,
            entry.crew,
            entry.date.strftime('%Y-%m-%d'),
            entry.type.title(),
            entry.reason or 'N/A'
        ])
    
    # Create response
    output.seek(0)
    month_name = calendar.month_name[month]
    filename = f'vacation_calendar_{month_name}_{year}'
    if crew != 'ALL':
        filename += f'_crew_{crew}'
    filename += '.csv'
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )

@supervisor_bp.route('/supervisor/time-off-requests')
@login_required
@supervisor_required
def time_off_requests():
    """View and manage time off requests"""
    # Get filter parameters
    status_filter = request.args.get('status', 'pending')
    crew_filter = request.args.get('crew', 'all')
    date_filter = request.args.get('date_range', 'upcoming')
    
    # Base query
    query = TimeOffRequest.query
    
    # Apply status filter
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    # Apply crew filter - FIXED: Specify the join explicitly
    if crew_filter != 'all':
        query = query.join(Employee, Employee.id == TimeOffRequest.employee_id).filter(Employee.crew == crew_filter)
    else:
        query = query.join(Employee, Employee.id == TimeOffRequest.employee_id)
    
    # Apply date filter
    today = datetime.now().date()
    if date_filter == 'upcoming':
        query = query.filter(TimeOffRequest.start_date >= today)
    elif date_filter == 'past':
        query = query.filter(TimeOffRequest.end_date < today)
    elif date_filter == 'current':
        query = query.filter(
            TimeOffRequest.start_date <= today,
            TimeOffRequest.end_date >= today
        )
    
    # Order by start date (pending first, then by date)
    requests = query.order_by(
        case(
            (TimeOffRequest.status == 'pending', 0),
            (TimeOffRequest.status == 'approved', 1),
            (TimeOffRequest.status == 'denied', 2)
        ),
        TimeOffRequest.start_date
    ).all()
    
    # Get statistics
    stats = {
        'pending_count': TimeOffRequest.query.filter_by(status='pending').count(),
        'approved_this_week': TimeOffRequest.query.filter(
            TimeOffRequest.status == 'approved',
            TimeOffRequest.approved_date >= datetime.now() - timedelta(days=7)
        ).count(),
        'coverage_warnings': 0  # Will be calculated based on coverage needs
    }
    
    # Check for coverage warnings (requests that might cause coverage issues)
    for req in requests:
        if req.status == 'pending':
            # Check if approving this would cause coverage issues - FIXED: Use explicit join
            conflicting = TimeOffRequest.query.join(
                Employee, Employee.id == TimeOffRequest.employee_id
            ).filter(
                TimeOffRequest.status == 'approved',
                Employee.crew == req.employee.crew,
                TimeOffRequest.start_date <= req.end_date,
                TimeOffRequest.end_date >= req.start_date
            ).count()
            
            if conflicting >= 2:  # If 2 or more people are already off
                stats['coverage_warnings'] += 1
                req.has_coverage_warning = True
            else:
                req.has_coverage_warning = False
    
    return render_template('time_off_requests.html',
                         requests=requests,
                         stats=stats,
                         status_filter=status_filter,
                         crew_filter=crew_filter,
                         date_filter=date_filter)

@supervisor_bp.route('/supervisor/time-off-requests/<int:request_id>/<action>', methods=['POST'])
@login_required
@supervisor_required
def handle_time_off_request(request_id, action):
    """Approve or deny a time off request"""
    time_off_request = TimeOffRequest.query.get_or_404(request_id)
    
    if time_off_request.status != 'pending':
        flash('This request has already been processed.', 'warning')
        return redirect(url_for('supervisor.time_off_requests'))
    
    if action == 'approve':
        time_off_request.status = 'approved'
        time_off_request.approved_by = current_user.id
        time_off_request.approved_date = datetime.now()
        
        # Send notification to employee (you can implement this later)
        flash(f'Approved {time_off_request.employee.name}\'s time off request for {time_off_request.start_date.strftime("%b %d")} - {time_off_request.end_date.strftime("%b %d")}', 'success')
        
    elif action == 'deny':
        time_off_request.status = 'denied'
        time_off_request.approved_by = current_user.id
        time_off_request.approved_date = datetime.now()
        
        # Get denial reason if provided
        denial_reason = request.form.get('denial_reason', '')
        if denial_reason:
            time_off_request.notes = f"Denial reason: {denial_reason}"
        
        flash(f'Denied {time_off_request.employee.name}\'s time off request', 'info')
    
    db.session.commit()
    return redirect(url_for('supervisor.time_off_requests'))

# ========== OTHER SUPERVISOR ROUTES ==========

@supervisor_bp.route('/supervisor/coverage-needs')
@login_required
@supervisor_required
def coverage_needs():
    """View and manage coverage needs"""
    # Implementation here
    pass

@supervisor_bp.route('/supervisor/swap-requests')
@login_required
@supervisor_required
def swap_requests():
    """Review and approve shift swap requests"""
    # Get filter parameters
    status_filter = request.args.get('status', 'pending')
    crew_filter = request.args.get('crew', 'all')
    
    # Base query
    query = ShiftSwapRequest.query
    
    # Apply status filter
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    # Apply crew filter
    if crew_filter != 'all':
        # Join with requester employee to filter by crew
        query = query.join(Employee, Employee.id == ShiftSwapRequest.requester_id).filter(
            Employee.crew == crew_filter
        )
    
    # Order by creation date (newest first for pending)
    if status_filter == 'pending':
        swap_requests = query.order_by(ShiftSwapRequest.created_at.desc()).all()
    else:
        swap_requests = query.order_by(ShiftSwapRequest.created_at.desc()).all()
    
    # Get statistics
    stats = {
        'pending_count': ShiftSwapRequest.query.filter_by(status='pending').count(),
        'approved_this_week': ShiftSwapRequest.query.filter(
            ShiftSwapRequest.status == 'approved',
            ShiftSwapRequest.created_at >= datetime.now() - timedelta(days=7)
        ).count(),
        'needs_dual_approval': 0
    }
    
    # Check for swaps needing dual approval
    for swap in swap_requests:
        if swap.status == 'pending':
            # Check if this needs approval from both supervisors
            if swap.requester and swap.target_employee:
                if swap.requester.crew != swap.target_employee.crew:
                    stats['needs_dual_approval'] += 1
                    swap.needs_dual_approval = True
                else:
                    swap.needs_dual_approval = False
    
    return render_template('swap_requests.html',
                         requests=swap_requests,
                         stats=stats,
                         status_filter=status_filter,
                         crew_filter=crew_filter)

@supervisor_bp.route('/supervisor/swap-requests/<int:request_id>/<action>', methods=['POST'])
@login_required
@supervisor_required
def handle_swap_request(request_id, action):
    """Approve or deny a swap request"""
    swap_request = ShiftSwapRequest.query.get_or_404(request_id)
    
    if swap_request.status != 'pending':
        flash('This swap request has already been processed.', 'warning')
        return redirect(url_for('supervisor.swap_requests'))
    
    # Determine which supervisor is approving
    is_requester_supervisor = current_user.crew == swap_request.requester.crew
    is_target_supervisor = swap_request.target_employee and current_user.crew == swap_request.target_employee.crew
    
    if action == 'approve':
        # Handle approval based on supervisor's crew
        if is_requester_supervisor:
            swap_request.requester_supervisor_approved = True
            swap_request.requester_supervisor_id = current_user.id
            swap_request.requester_supervisor_date = datetime.now()
        
        if is_target_supervisor:
            swap_request.target_supervisor_approved = True
            swap_request.target_supervisor_id = current_user.id
            swap_request.target_supervisor_date = datetime.now()
        
        # Check if both approvals are complete (or if only one is needed)
        needs_both = swap_request.requester.crew != swap_request.target_employee.crew if swap_request.target_employee else False
        
        if not needs_both or (swap_request.requester_supervisor_approved and swap_request.target_supervisor_approved):
            swap_request.status = 'approved'
            
            # TODO: Actually swap the schedules in the database
            # This would involve swapping the employee_id fields in the Schedule records
            
            flash(f'Approved shift swap between {swap_request.requester.name} and {swap_request.target_employee.name if swap_request.target_employee else "TBD"}', 'success')
        else:
            flash('Swap request partially approved. Waiting for other supervisor approval.', 'info')
            
    elif action == 'deny':
        swap_request.status = 'denied'
        
        # Set the appropriate supervisor fields
        if is_requester_supervisor:
            swap_request.requester_supervisor_approved = False
            swap_request.requester_supervisor_id = current_user.id
            swap_request.requester_supervisor_date = datetime.now()
        
        if is_target_supervisor:
            swap_request.target_supervisor_approved = False
            swap_request.target_supervisor_id = current_user.id
            swap_request.target_supervisor_date = datetime.now()
        
        flash(f'Denied shift swap request from {swap_request.requester.name}', 'info')
    
    db.session.commit()
    return redirect(url_for('supervisor.swap_requests'))

@supervisor_bp.route('/supervisor/suggestions')
@login_required
@supervisor_required
def suggestions():
    """View employee suggestions"""
    # Implementation here
    pass

@supervisor_bp.route('/supervisor/overtime-distribution')
@login_required
@supervisor_required
def overtime_distribution():
    """Manage overtime distribution"""
    # Implementation here
    pass

@supervisor_bp.route('/supervisor/messages')
@login_required
@supervisor_required
def supervisor_messages():
    """Supervisor to supervisor messaging"""
    # Implementation here
    pass
