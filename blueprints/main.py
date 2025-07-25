from flask import Blueprint, render_template, redirect, url_for, request, jsonify, send_file
from flask_login import login_required, current_user
from models import db, Employee, TimeOffRequest, ShiftSwapRequest, ScheduleSuggestion, MaintenanceIssue, Schedule, VacationCalendar, PositionMessage, PositionMessageRead, OvertimeHistory, Position
from datetime import date, timedelta, datetime
from sqlalchemy import func
from utils.helpers import get_coverage_gaps
import pandas as pd
import io

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

# ========== OVERTIME MANAGEMENT ROUTES ==========

@main_bp.route('/overtime-management')
@login_required
def overtime_management():
    """Display overtime management page with 13-week history"""
    if not current_user.is_supervisor:
        return redirect(url_for('main.employee_dashboard'))
    
    # Calculate date range for last 13 weeks
    today = date.today()
    current_week_start = today - timedelta(days=today.weekday())
    start_date = current_week_start - timedelta(weeks=12)
    end_date = current_week_start + timedelta(days=6)
    
    # Generate list of week start dates
    weeks = []
    for i in range(13):
        week_start = start_date + timedelta(weeks=i)
        weeks.append(week_start)
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 25
    
    # Get all employees with pagination
    employees_query = Employee.query.order_by(Employee.name)
    employees_paginated = employees_query.paginate(page=page, per_page=per_page, error_out=False)
    employees = employees_paginated.items
    
    # Get all positions for filter dropdown
    positions = Position.query.order_by(Position.name).all()
    
    # Find employees with high overtime (approaching 60 hours in current week)
    high_overtime_employees = []
    for employee in Employee.query.all():
        current_week_ot = employee.get_overtime_for_week(current_week_start)
        if current_week_ot >= 50:  # Alert when approaching 60 hours
            high_overtime_employees.append(employee)
    
    return render_template('overtime_management.html',
                         employees=employees,
                         weeks=weeks,
                         start_date=start_date,
                         end_date=end_date,
                         current_date=today,
                         positions=positions,
                         high_overtime_employees=high_overtime_employees,
                         page=page,
                         total_pages=employees_paginated.pages)

@main_bp.route('/overtime-management/export/excel')
@login_required
def export_overtime_excel():
    """Export overtime data to Excel"""
    if not current_user.is_supervisor:
        return redirect(url_for('main.employee_dashboard'))
    
    # Calculate date range
    today = date.today()
    current_week_start = today - timedelta(days=today.weekday())
    start_date = current_week_start - timedelta(weeks=12)
    
    # Generate weeks
    weeks = []
    for i in range(13):
        week_start = start_date + timedelta(weeks=i)
        weeks.append(week_start)
    
    # Get all employees
    employees = Employee.query.order_by(Employee.name).all()
    
    # Build data for Excel
    data = []
    for employee in employees:
        row = {
            'Employee Name': employee.name,
            'Employee ID': employee.employee_id or f'EMP{employee.id}',
            'Crew': employee.crew or '-',
            'Position': employee.position.name if employee.position else '-',
            'Hire Date': employee.hire_date.strftime('%Y-%m-%d') if employee.hire_date else '-',
        }
        
        # Add weekly overtime data
        total_ot = 0
        for i, week in enumerate(weeks):
            ot_hours = employee.get_overtime_for_week(week)
            row[f'Week {i+1} ({week.strftime("%m/%d")})'] = ot_hours
            total_ot += ot_hours
        
        row['Total OT Hours'] = total_ot
        row['Average Weekly OT'] = round(total_ot / 13, 2)
        data.append(row)
    
    # Create DataFrame and Excel file
    df = pd.DataFrame(data)
    
    # Create Excel writer object
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Overtime Report', index=False)
        
        # Get the workbook and worksheet
        workbook = writer.book
        worksheet = writer.sheets['Overtime Report']
        
        # Auto-adjust column widths
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'overtime_report_{today.strftime("%Y%m%d")}.xlsx'
    )

@main_bp.route('/overtime-management/export/pdf')
@login_required
def export_overtime_pdf():
    """Export overtime data to PDF"""
    if not current_user.is_supervisor:
        return redirect(url_for('main.employee_dashboard'))
    
    # For PDF export, you'll need to implement using a library like ReportLab or WeasyPrint
    # This is a placeholder
    return jsonify({"message": "PDF export functionality to be implemented"}), 501

@main_bp.route('/api/overtime/update', methods=['POST'])
@login_required
def update_overtime():
    """Update overtime hours for an employee"""
    if not current_user.is_supervisor:
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.get_json()
    employee_id = data.get('employee_id')
    week_start = data.get('week_start')
    regular_hours = data.get('regular_hours', 40)
    overtime_hours = data.get('overtime_hours', 0)
    
    try:
        employee = Employee.query.get(employee_id)
        if not employee:
            return jsonify({"error": "Employee not found"}), 404
        
        week_start_date = datetime.strptime(week_start, '%Y-%m-%d').date()
        employee.update_overtime_hours(week_start_date, regular_hours, overtime_hours)
        
        return jsonify({"success": True, "message": "Overtime hours updated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

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
