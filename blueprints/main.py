# main.py (or wherever your overtime route is defined)
# Complete route implementation for /overtime-management

from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import or_, and_, func
from models import db, Employee, Position, OvertimeHistory

# If using blueprints
main = Blueprint('main', __name__)

@main.route('/overtime-management')
@login_required
def overtime_management():
    """Display overtime management page with employee overtime data"""
    
    # Get filter parameters from URL
    search_term = request.args.get('search', '')
    crew_filter = request.args.get('crew', '')
    position_filter = request.args.get('position', '')
    ot_range_filter = request.args.get('ot_range', '')
    page = request.args.get('page', 1, type=int)
    
    # Get sorting parameters (up to 4 levels)
    sort_params = []
    for i in range(1, 5):
        sort_field = request.args.get(f'sort{i}')
        sort_dir = request.args.get(f'dir{i}', 'asc')
        if sort_field:
            sort_params.append((sort_field, sort_dir))
    
    # Base query - get all employees except current user
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
    
    # Apply overtime range filter
    if ot_range_filter:
        if ot_range_filter == '0-50':
            query = query.filter(
                and_(
                    Employee.last_13_weeks_overtime >= 0,
                    Employee.last_13_weeks_overtime <= 50
                )
            )
        elif ot_range_filter == '50-100':
            query = query.filter(
                and_(
                    Employee.last_13_weeks_overtime > 50,
                    Employee.last_13_weeks_overtime <= 100
                )
            )
        elif ot_range_filter == '100-150':
            query = query.filter(
                and_(
                    Employee.last_13_weeks_overtime > 100,
                    Employee.last_13_weeks_overtime <= 150
                )
            )
        elif ot_range_filter == '150+':
            query = query.filter(Employee.last_13_weeks_overtime > 150)
    
    # Apply multi-level sorting
    for sort_field, sort_dir in sort_params:
        if sort_field == 'crew':
            order_column = Employee.crew
        elif sort_field == 'jobtitle':
            # Join with Position table for sorting by position name
            if 'position' not in str(query):
                query = query.outerjoin(Position, Employee.position_id == Position.id)
            order_column = Position.name
        elif sort_field == 'seniority':
            order_column = Employee.hire_date
        elif sort_field == 'overtime':
            order_column = Employee.last_13_weeks_overtime
        else:
            continue
        
        # Apply sort direction
        if sort_dir == 'desc':
            order_column = order_column.desc()
        else:
            order_column = order_column.asc()
        
        # Handle NULL values
        if sort_field in ['crew', 'seniority', 'overtime']:
            order_column = order_column.nullslast() if sort_dir == 'asc' else order_column.nullsfirst()
        
        query = query.order_by(order_column)
    
    # If no sorting specified, default sort by name
    if not sort_params:
        query = query.order_by(Employee.name)
    
    # Ensure we join Position table if needed for display
    if 'position' not in str(query):
        query = query.options(db.joinedload(Employee.position))
    
    # Paginate results
    per_page = 20
    try:
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        employees = pagination.items
        total_pages = pagination.pages
    except Exception as e:
        print(f"Pagination error: {e}")
        employees = query.all()
        total_pages = 1
        page = 1
    
    # Calculate statistics for ALL employees (not just current page)
    all_employees_query = Employee.query.filter(Employee.id != current_user.id)
    
    # Apply the same filters to statistics query (but no pagination)
    if search_term:
        search_pattern = f'%{search_term}%'
        all_employees_query = all_employees_query.filter(
            or_(
                Employee.name.ilike(search_pattern),
                Employee.employee_id.ilike(search_pattern)
            )
        )
    
    if crew_filter:
        all_employees_query = all_employees_query.filter(Employee.crew == crew_filter)
    
    if position_filter:
        try:
            position_id = int(position_filter)
            all_employees_query = all_employees_query.filter(Employee.position_id == position_id)
        except ValueError:
            pass
    
    if ot_range_filter:
        if ot_range_filter == '0-50':
            all_employees_query = all_employees_query.filter(
                and_(
                    Employee.last_13_weeks_overtime >= 0,
                    Employee.last_13_weeks_overtime <= 50
                )
            )
        elif ot_range_filter == '50-100':
            all_employees_query = all_employees_query.filter(
                and_(
                    Employee.last_13_weeks_overtime > 50,
                    Employee.last_13_weeks_overtime <= 100
                )
            )
        elif ot_range_filter == '100-150':
            all_employees_query = all_employees_query.filter(
                and_(
                    Employee.last_13_weeks_overtime > 100,
                    Employee.last_13_weeks_overtime <= 150
                )
            )
        elif ot_range_filter == '150+':
            all_employees_query = all_employees_query.filter(Employee.last_13_weeks_overtime > 150)
    
    all_employees = all_employees_query.all()
    
    # Calculate statistics
    total_overtime_hours = 0
    employees_with_overtime = 0
    high_overtime_employees = []
    
    for emp in all_employees:
        # Get overtime value safely
        ot_hours = getattr(emp, 'last_13_weeks_overtime', 0) or 0
        total_overtime_hours += ot_hours
        
        if ot_hours > 0:
            employees_with_overtime += 1
        
        # High overtime is over 200 hours in 13 weeks (about 15+ hours per week)
        if ot_hours > 200:
            high_overtime_employees.append(emp)
    
    # Calculate average overtime
    if all_employees:
        avg_overtime = round(total_overtime_hours / len(all_employees))
    else:
        avg_overtime = 0
    
    high_overtime_count = len(high_overtime_employees)
    
    # Get all positions for filter dropdown
    positions = Position.query.order_by(Position.name).all()
    
    # Calculate date range (13 weeks)
    end_date = datetime.now()
    start_date = end_date - timedelta(weeks=13)
    
    # Ensure employees have all required properties
    for employee in employees:
        # Set defaults if properties don't exist
        if not hasattr(employee, 'last_13_weeks_overtime'):
            employee.last_13_weeks_overtime = 0
        if not hasattr(employee, 'current_week_overtime'):
            employee.current_week_overtime = 0
        if not hasattr(employee, 'average_weekly_overtime'):
            employee.average_weekly_overtime = 0
        if not hasattr(employee, 'overtime_trend'):
            employee.overtime_trend = 'stable'
        if not hasattr(employee, 'years_employed'):
            employee.years_employed = 0
    
    return render_template('overtime_management.html',
        employees=employees,
        positions=positions,
        total_overtime_hours=int(total_overtime_hours),
        employees_with_overtime=employees_with_overtime,
        avg_overtime=avg_overtime,
        high_overtime_count=high_overtime_count,
        high_overtime_employees=high_overtime_employees,
        start_date=start_date,
        end_date=end_date,
        total_pages=total_pages,
        page=page,
        # Pass filter values back to template
        search_term=search_term,
        crew_filter=crew_filter,
        position_filter=position_filter,
        ot_range_filter=ot_range_filter
    )


# Export route for Excel
@main.route('/export-overtime-excel')
@login_required
def export_overtime_excel():
    """Export overtime data to Excel with current filters applied"""
    try:
        import pandas as pd
        from io import BytesIO
        from flask import send_file
        
        # Get filter parameters
        search_term = request.args.get('search', '')
        crew_filter = request.args.get('crew', '')
        position_filter = request.args.get('position', '')
        ot_range_filter = request.args.get('ot_range', '')
        
        # Build query with filters (same as main route)
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
        
        if ot_range_filter:
            if ot_range_filter == '0-50':
                query = query.filter(Employee.last_13_weeks_overtime.between(0, 50))
            elif ot_range_filter == '50-100':
                query = query.filter(Employee.last_13_weeks_overtime.between(50, 100))
            elif ot_range_filter == '100-150':
                query = query.filter(Employee.last_13_weeks_overtime.between(100, 150))
            elif ot_range_filter == '150+':
                query = query.filter(Employee.last_13_weeks_overtime >= 150)
        
        # Get all matching employees
        employees = query.all()
        
        # Create DataFrame
        data = []
        for emp in employees:
            data.append({
                'Employee ID': emp.employee_id,
                'Name': emp.name,
                'Crew': emp.crew or '',
                'Position': emp.position.name if emp.position else '',
                'Hire Date': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '',
                'Years Employed': getattr(emp, 'years_employed', 0),
                'Current Week OT': getattr(emp, 'current_week_overtime', 0),
                '13-Week Total OT': getattr(emp, 'last_13_weeks_overtime', 0),
                'Weekly Average OT': getattr(emp, 'average_weekly_overtime', 0),
                'Trend': getattr(emp, 'overtime_trend', 'stable')
            })
        
        df = pd.DataFrame(data)
        
        # Create Excel file in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Overtime Report', index=False)
            
            # Get workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets['Overtime Report']
            
            # Add formats
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'fg_color': '#11998e',
                'font_color': '#FFFFFF',
                'border': 1
            })
            
            # Format header row
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            # Set column widths
            worksheet.set_column('A:A', 12)  # Employee ID
            worksheet.set_column('B:B', 25)  # Name
            worksheet.set_column('C:C', 8)   # Crew
            worksheet.set_column('D:D', 20)  # Position
            worksheet.set_column('E:E', 12)  # Hire Date
            worksheet.set_column('F:J', 15)  # Numeric columns
        
        output.seek(0)
        
        # Generate filename with timestamp
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
