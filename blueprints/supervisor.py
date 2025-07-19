# Add these routes to your supervisor blueprint (blueprints/supervisor.py)

from flask import render_template, jsonify, request, send_file
from datetime import datetime, date, timedelta
import calendar
import io
import csv

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

# Also add this helper decorator if not already present
def supervisor_required(f):
    """Decorator to require supervisor privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_supervisor:
            flash('You must be a supervisor to access this page.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function
