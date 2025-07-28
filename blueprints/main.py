# blueprints/main.py
"""
Main blueprint for general routes and dashboard
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from models import db, Employee, Schedule, TimeOffRequest, ShiftSwapRequest, CoverageRequest, MaintenanceIssue, Position, OvertimeHistory, VacationCalendar, CircadianProfile, SleepLog, PositionMessage, CasualWorker
from datetime import date, timedelta, datetime
from sqlalchemy import or_, and_, func
import pandas as pd
from io import BytesIO

# Create the blueprint - MUST be named 'main_bp' to match the import
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Landing page"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('index.html')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - redirect based on user role"""
    if current_user.is_supervisor:
        return redirect(url_for('supervisor.dashboard'))
    else:
        return redirect(url_for('main.employee_dashboard'))

@main_bp.route('/employee-dashboard')
@login_required
def employee_dashboard():
    """Employee dashboard"""
    # Get upcoming schedules
    upcoming_schedules = Schedule.query.filter(
        Schedule.employee_id == current_user.id,
        Schedule.date >= date.today(),
        Schedule.date <= date.today() + timedelta(days=14)
    ).order_by(Schedule.date).all()
    
    # Get pending requests
    pending_time_off = TimeOffRequest.query.filter_by(
        employee_id=current_user.id,
        status='pending'
    ).all()
    
    pending_swaps = ShiftSwapRequest.query.filter_by(
        requester_id=current_user.id,
        status='pending'
    ).all()
    
    # Get open coverage requests
    open_coverage = CoverageRequest.query.filter_by(
        status='open'
    ).order_by(CoverageRequest.created_at.desc()).limit(5).all()
    
    # Get recent maintenance issues
    recent_issues = MaintenanceIssue.query.filter_by(
        reporter_id=current_user.id
    ).order_by(MaintenanceIssue.reported_at.desc()).limit(5).all()
    
    return render_template('employee_dashboard.html',
                         upcoming_schedules=upcoming_schedules,
                         pending_time_off=pending_time_off,
                         pending_swaps=pending_swaps,
                         open_coverage=open_coverage,
                         recent_issues=recent_issues)

@main_bp.route('/overtime-management')
@login_required
def overtime_management():
    """Overtime management page"""
    # Check if user is supervisor
    if not current_user.is_supervisor:
        flash('You must be a supervisor to access this page.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Get filter parameters
    search_term = request.args.get('search', '')
    crew_filter = request.args.get('crew', '')
    position_filter = request.args.get('position', '')
    ot_range_filter = request.args.get('ot_range', '')
    page = request.args.get('page', 1, type=int)
    
    # Get sorting parameters
    sort_params = []
    for i in range(1, 5):
        sort_field = request.args.get(f'sort{i}')
        sort_dir = request.args.get(f'dir{i}', 'asc')
        if sort_field:
            sort_params.append((sort_field, sort_dir))
    
    # Base query
    query = Employee.query.filter(Employee.id != current_user.id)
    
    # Apply search filter
    if search_term:
        search_pattern = f'%{search_term}%'
        query = query.filter(
            or_(
                Employee.name.ilike(search_pattern),
                Employee.employee_id.ilike(search_pattern)
            )
        )
    
    # Apply crew filter
    if crew_filter:
        query = query.filter(Employee.crew == crew_filter)
    
    # Apply position filter
    if position_filter:
        try:
            position_id = int(position_filter)
            query = query.filter(Employee.position_id == position_id)
        except ValueError:
            pass
    
    # Apply overtime range filter using OvertimeHistory
    if ot_range_filter:
        # Subquery to get 13-week overtime totals
        thirteen_weeks_ago = datetime.now().date() - timedelta(weeks=13)
        overtime_subquery = db.session.query(
            OvertimeHistory.employee_id,
            func.sum(OvertimeHistory.overtime_hours).label('total_ot')
        ).filter(
            OvertimeHistory.week_start_date >= thirteen_weeks_ago
        ).group_by(OvertimeHistory.employee_id).subquery()
        
        # Join with subquery
        query = query.outerjoin(
            overtime_subquery,
            Employee.id == overtime_subquery.c.employee_id
        )
        
        if ot_range_filter == '0-50':
            query = query.filter(
                or_(
                    overtime_subquery.c.total_ot.between(0, 50),
                    overtime_subquery.c.total_ot.is_(None)
                )
            )
        elif ot_range_filter == '50-100':
            query = query.filter(overtime_subquery.c.total_ot.between(50, 100))
        elif ot_range_filter == '100-150':
            query = query.filter(overtime_subquery.c.total_ot.between(100, 150))
        elif ot_range_filter == '150+':
            query = query.filter(overtime_subquery.c.total_ot > 150)
    
    # Apply sorting
    for sort_field, sort_dir in sort_params:
        if sort_field == 'crew':
            order_column = Employee.crew
        elif sort_field == 'jobtitle':
            if 'position' not in str(query):
                query = query.outerjoin(Position, Employee.position_id == Position.id)
            order_column = Position.name
        elif sort_field == 'seniority':
            order_column = Employee.hire_date
        elif sort_field == 'overtime':
            # Sort by 13-week total from property
            continue  # Handle after query execution
        else:
            continue
        
        if sort_dir == 'desc':
            order_column = order_column.desc()
        else:
            order_column = order_column.asc()
        
        query = query.order_by(order_column)
    
    # Default sort by name if no sorting specified
    if not sort_params:
        query = query.order_by(Employee.name)
    
    # Ensure position is loaded
    query = query.options(db.joinedload(Employee.position))
    
    # Execute query to get all employees
    all_employees = query.all()
    
    # If sorting by overtime, sort in memory after calculating totals
    if any(sort[0] == 'overtime' for sort in sort_params):
        sort_dir = next((sort[1] for sort in sort_params if sort[0] == 'overtime'), 'asc')
        reverse = (sort_dir == 'desc')
        all_employees.sort(key=lambda e: e.last_13_weeks_overtime, reverse=reverse)
    
    # Manual pagination
    per_page = 20
    total_count = len(all_employees)
    total_pages = (total_count + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    employees = all_employees[start_idx:end_idx]
    
    # Prepare employee data for template
    employees_data = []
    for emp in employees:
        # Calculate years employed
        years_employed = 0
        if emp.hire_date:
            delta = datetime.now().date() - emp.hire_date
            years_employed = delta.days // 365
        
        employee_data = {
            'id': emp.id,
            'name': emp.name,
            'employee_id': emp.employee_id,
            'crew': emp.crew,
            'position': emp.position,
            'position_id': emp.position_id if emp.position else None,
            'hire_date': emp.hire_date,
            'years_employed': years_employed,
            'current_week_overtime': emp.current_week_overtime,
            'last_13_weeks_overtime': emp.last_13_weeks_overtime,
            'average_weekly_overtime': emp.average_weekly_overtime,
            'overtime_trend': emp.overtime_trend
        }
        employees_data.append(employee_data)
    
    # Calculate statistics
    total_overtime_hours = 0
    employees_with_overtime = 0
    high_overtime_employees = []
    
    for emp in all_employees:
        ot_hours = emp.last_13_weeks_overtime
        total_overtime_hours += ot_hours
        
        if ot_hours > 0:
            employees_with_overtime += 1
        
        if ot_hours > 200:
            high_overtime_employees.append(emp)
    
    if all_employees:
        avg_overtime = round(total_overtime_hours / len(all_employees))
    else:
        avg_overtime = 0
    
    high_overtime_count = len(high_overtime_employees)
    
    # Calculate crew overtime data for charts
    crew_overtime_data = [0, 0, 0, 0]  # For crews A, B, C, D
    crew_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
    
    for emp in all_employees:
        if emp.crew in crew_map:
            crew_overtime_data[crew_map[emp.crew]] += round(emp.last_13_weeks_overtime or 0)
    
    # Get all positions
    positions = Position.query.order_by(Position.name).all()
    
    # Date range
    end_date = datetime.now().date()
    start_date = end_date - timedelta(weeks=13)
    
    return render_template('overtime_management.html',
        employees=employees_data,
        positions=positions,
        total_overtime_hours=int(total_overtime_hours),
        employees_with_overtime=employees_with_overtime,
        avg_overtime=avg_overtime,
        high_overtime_count=high_overtime_count,
        high_overtime_employees=high_overtime_employees,
        crew_overtime_data=crew_overtime_data,
        start_date=start_date,
        end_date=end_date,
        total_pages=total_pages,
        page=page,
        search_term=search_term,
        crew_filter=crew_filter,
        position_filter=position_filter,
        ot_range_filter=ot_range_filter,
        sort_params=sort_params,
        current_date=datetime.now().date()
    )

@main_bp.route('/export-overtime-excel')
@login_required
def export_overtime_excel():
    """Export overtime data to Excel"""
    if not current_user.is_supervisor:
        flash('You must be a supervisor to export data.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    try:
        # Get filter parameters
        search_term = request.args.get('search', '')
        crew_filter = request.args.get('crew', '')
        position_filter = request.args.get('position', '')
        ot_range_filter = request.args.get('ot_range', '')
        
        # Build query with filters
        query = Employee.query.filter(Employee.id != current_user.id)
        
        if search_term:
            search_pattern = f'%{search_term}%'
            query = query.filter(
                or_(
                    Employee.name.ilike(search_pattern),
                    Employee.employee_id.ilike(search_pattern)
                )
            )
        
        if crew_filter:
            query = query.filter(Employee.crew == crew_filter)
        
        if position_filter:
            try:
                position_id = int(position_filter)
                query = query.filter(Employee.position_id == position_id)
            except ValueError:
                pass
        
        # Get all matching employees
        employees = query.options(db.joinedload(Employee.position)).all()
        
        # Filter by overtime range in memory
        if ot_range_filter:
            filtered_employees = []
            for emp in employees:
                ot_total = emp.last_13_weeks_overtime
                if ot_range_filter == '0-50' and 0 <= ot_total <= 50:
                    filtered_employees.append(emp)
                elif ot_range_filter == '50-100' and 50 < ot_total <= 100:
                    filtered_employees.append(emp)
                elif ot_range_filter == '100-150' and 100 < ot_total <= 150:
                    filtered_employees.append(emp)
                elif ot_range_filter == '150+' and ot_total > 150:
                    filtered_employees.append(emp)
            employees = filtered_employees
        
        # Create DataFrame
        data = []
        for emp in employees:
            # Get years employed
            years_employed = 0
            if emp.hire_date:
                delta = datetime.now().date() - emp.hire_date
                years_employed = delta.days // 365
            
            data.append({
                'Employee ID': emp.employee_id,
                'Name': emp.name,
                'Crew': emp.crew or '',
                'Position': emp.position.name if emp.position else '',
                'Hire Date': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '',
                'Years Employed': years_employed,
                'Current Week OT': emp.current_week_overtime,
                '13-Week Total OT': emp.last_13_weeks_overtime,
                'Weekly Average OT': emp.average_weekly_overtime,
                'Trend': emp.overtime_trend
            })
        
        df = pd.DataFrame(data)
        
        # Create Excel file
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Overtime Report', index=False)
            
            workbook = writer.book
            worksheet = writer.sheets['Overtime Report']
            
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'fg_color': '#11998e',
                'font_color': '#FFFFFF',
                'border': 1
            })
            
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            worksheet.set_column('A:A', 12)
            worksheet.set_column('B:B', 25)
            worksheet.set_column('C:C', 8)
            worksheet.set_column('D:D', 20)
            worksheet.set_column('E:E', 12)
            worksheet.set_column('F:J', 15)
        
        output.seek(0)
        
        filename = f'overtime_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        flash(f'Error exporting data: {str(e)}', 'error')
        return redirect(url_for('main.overtime_management'))

@main_bp.route('/view-crews')
@login_required
def view_crews():
    """View all crews and their members"""
    crews = {}
    employees = Employee.query.order_by(Employee.crew, Employee.name).all()
    
    for employee in employees:
        crew_name = employee.crew or 'Unassigned'
        if crew_name not in crews:
            crews[crew_name] = []
        crews[crew_name].append(employee)
    
    # Get positions for each crew
    positions = Position.query.all()
    
    # Calculate statistics
    stats = {
        'total_employees': len(employees),
        'total_crews': len([c for c in crews if c != 'Unassigned']),
        'total_supervisors': len([e for e in employees if e.is_supervisor]),
        'unassigned': len(crews.get('Unassigned', []))
    }
    
    return render_template('view_crews.html',
                         crews=crews,
                         positions=positions,
                         stats=stats)

@main_bp.route('/schedule-selection')
@login_required
def schedule_selection():
    """Schedule viewing selection page"""
    return render_template('schedule_selection.html')

@main_bp.route('/crew-schedule/<crew>')
@login_required
def crew_schedule(crew):
    """View schedule for a specific crew"""
    # Get date range from query params or default to current week
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date:
        start_date = date.today() - timedelta(days=date.today().weekday())
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    if not end_date:
        end_date = start_date + timedelta(days=6)
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Get all employees in the crew
    crew_employees = Employee.query.filter_by(crew=crew).order_by(Employee.name).all()
    
    # Get schedules for the crew in the date range
    schedules = Schedule.query.join(Employee).filter(
        Employee.crew == crew,
        Schedule.date >= start_date,
        Schedule.date <= end_date
    ).all()
    
    # Organize schedules by date and employee
    schedule_grid = {}
    current_date = start_date
    while current_date <= end_date:
        schedule_grid[current_date] = {}
        current_date += timedelta(days=1)
    
    for schedule in schedules:
        schedule_grid[schedule.date][schedule.employee_id] = schedule
    
    return render_template('crew_schedule.html',
                         crew=crew,
                         crew_employees=crew_employees,
                         schedule_grid=schedule_grid,
                         start_date=start_date,
                         end_date=end_date)

@main_bp.route('/view-schedule')
@login_required
def view_schedule():
    """View personal schedule"""
    # Get date range from query params or default to current month
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date:
        start_date = date.today().replace(day=1)
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    if not end_date:
        # Last day of the month
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1, day=1) - timedelta(days=1)
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Get schedules for the employee
    schedules = Schedule.query.filter(
        Schedule.employee_id == current_user.id,
        Schedule.date >= start_date,
        Schedule.date <= end_date
    ).order_by(Schedule.date).all()
    
    # Get time off requests
    time_off_requests = TimeOffRequest.query.filter(
        TimeOffRequest.employee_id == current_user.id,
        TimeOffRequest.start_date <= end_date,
        TimeOffRequest.end_date >= start_date
    ).all()
    
    # Calculate statistics
    total_hours = sum(s.hours for s in schedules if s.hours)
    overtime_hours = sum(s.hours - 8 for s in schedules if s.hours and s.hours > 8)
    days_off = sum(1 for d in pd.date_range(start_date, end_date) 
                   if not any(s.date == d.date() for s in schedules))
    
    stats = {
        'total_hours': total_hours,
        'overtime_hours': overtime_hours,
        'days_worked': len(schedules),
        'days_off': days_off
    }
    
    return render_template('view_schedule.html',
                         schedules=schedules,
                         time_off_requests=time_off_requests,
                         start_date=start_date,
                         end_date=end_date,
                         stats=stats)

@main_bp.route('/vacation-calendar')
@login_required
def vacation_calendar():
    """View vacation calendar"""
    # Get month from query params or default to current month
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)
    
    if not month or not year:
        today = date.today()
        month = today.month
        year = today.year
    
    # Get first and last day of the month
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    
    # Get all vacation calendar entries for the month
    calendar_entries = VacationCalendar.query.filter(
        VacationCalendar.date >= first_day,
        VacationCalendar.date <= last_day
    ).all()
    
    # Organize by date
    calendar_data = {}
    current_date = first_day
    while current_date <= last_day:
        calendar_data[current_date] = []
        current_date += timedelta(days=1)
    
    for entry in calendar_entries:
        calendar_data[entry.date].append(entry)
    
    # Get crew statistics
    crew_stats = {}
    if current_user.is_supervisor:
        crews = ['A', 'B', 'C', 'D']
        for crew in crews:
            crew_employees = Employee.query.filter_by(crew=crew).all()
            crew_stats[crew] = {
                'total': len(crew_employees),
                'on_vacation': 0
            }
    
    return render_template('vacation_calendar.html',
                         calendar_data=calendar_data,
                         month=month,
                         year=year,
                         first_day=first_day,
                         last_day=last_day,
                         crew_stats=crew_stats)

@main_bp.route('/time-off-requests')
@login_required
def time_off_requests():
    """View time off requests"""
    if current_user.is_supervisor:
        # Supervisors see all pending requests
        requests = TimeOffRequest.query.filter_by(status='pending').order_by(TimeOffRequest.created_at.desc()).all()
    else:
        # Employees see only their own requests
        requests = TimeOffRequest.query.filter_by(employee_id=current_user.id).order_by(TimeOffRequest.created_at.desc()).all()
    
    # Group by status
    pending_requests = [r for r in requests if r.status == 'pending']
    approved_requests = [r for r in requests if r.status == 'approved']
    denied_requests = [r for r in requests if r.status == 'denied']
    
    return render_template('time_off_requests.html',
                         pending_requests=pending_requests,
                         approved_requests=approved_requests,
                         denied_requests=denied_requests)

@main_bp.route('/swap-requests')
@login_required
def swap_requests():
    """View shift swap requests"""
    if current_user.is_supervisor:
        # Get requests for employees in supervisor's crews
        employee_ids = [e.id for e in Employee.query.filter_by(crew=current_user.crew).all()]
        requests = ShiftSwapRequest.query.filter(
            or_(
                ShiftSwapRequest.requester_id.in_(employee_ids),
                ShiftSwapRequest.target_employee_id.in_(employee_ids)
            )
        ).order_by(ShiftSwapRequest.created_at.desc()).all()
    else:
        # Employees see requests they're involved in
        requests = ShiftSwapRequest.query.filter(
            or_(
                ShiftSwapRequest.requester_id == current_user.id,
                ShiftSwapRequest.target_employee_id == current_user.id
            )
        ).order_by(ShiftSwapRequest.created_at.desc()).all()
    
    # Group by status
    pending_requests = [r for r in requests if r.status == 'pending']
    approved_requests = [r for r in requests if r.status == 'approved']
    denied_requests = [r for r in requests if r.status == 'denied']
    
    return render_template('swap_requests.html',
                         pending_requests=pending_requests,
                         approved_requests=approved_requests,
                         denied_requests=denied_requests)

@main_bp.route('/suggestions')
@login_required
def suggestions():
    """View and submit schedule suggestions"""
    from models import ScheduleSuggestion
    
    # Get user's suggestions
    my_suggestions = ScheduleSuggestion.query.filter_by(
        employee_id=current_user.id
    ).order_by(ScheduleSuggestion.submitted_date.desc()).all()
    
    # If supervisor, also get suggestions from their crew
    crew_suggestions = []
    if current_user.is_supervisor:
        crew_suggestions = ScheduleSuggestion.query.join(Employee).filter(
            Employee.crew == current_user.crew,
            Employee.id != current_user.id
        ).order_by(ScheduleSuggestion.submitted_date.desc()).all()
    
    return render_template('suggestions.html',
                         my_suggestions=my_suggestions,
                         crew_suggestions=crew_suggestions)

@main_bp.route('/casual-workers')
@login_required
def casual_workers():
    """View and manage casual workers"""
    if not current_user.is_supervisor:
        flash('Only supervisors can manage casual workers.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Get all active casual workers
    workers = CasualWorker.query.filter_by(is_active=True).order_by(CasualWorker.name).all()
    
    # Get statistics
    stats = {
        'total_workers': len(workers),
        'available_today': len([w for w in workers if w.is_active]),
        'high_rated': len([w for w in workers if w.rating >= 4.5]),
        'total_hours': sum(w.total_hours_worked for w in workers)
    }
    
    return render_template('casual_workers.html',
                         workers=workers,
                         stats=stats)

@main_bp.route('/coverage-gaps')
@login_required
def coverage_gaps():
    """View coverage gaps"""
    if not current_user.is_supervisor:
        flash('Only supervisors can view coverage gaps.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Get date range
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date:
        start_date = date.today()
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    if not end_date:
        end_date = start_date + timedelta(days=6)
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Get coverage requirements and actual coverage
    coverage_data = []
    current_date = start_date
    
    while current_date <= end_date:
        # Get scheduled employees for each position
        for position in Position.query.all():
            scheduled = Schedule.query.filter(
                Schedule.date == current_date,
                Schedule.position_id == position.id
            ).count()
            
            gap = position.min_coverage - scheduled
            
            if gap > 0:
                coverage_data.append({
                    'date': current_date,
                    'position': position,
                    'required': position.min_coverage,
                    'scheduled': scheduled,
                    'gap': gap
                })
        
        current_date += timedelta(days=1)
    
    return render_template('coverage_gaps.html',
                         coverage_data=coverage_data,
                         start_date=start_date,
                         end_date=end_date)

@main_bp.route('/coming-soon')
@login_required
def coming_soon():
    """Coming soon page for features under development"""
    feature = request.args.get('feature', 'This feature')
    return render_template('coming_soon.html', feature=feature)

# Error handlers
@main_bp.app_errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@main_bp.app_errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500
