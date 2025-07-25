from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from models import db, Schedule, VacationCalendar, Employee, Position, Skill, TimeOffRequest, ShiftSwapRequest, CircadianProfile, CoverageNotification, OvertimeHistory
from datetime import date, timedelta, datetime
from sqlalchemy import or_, func, case, and_

# Create the blueprint
employee_bp = Blueprint('employee', __name__)

@employee_bp.route('/view-employees-crews')
@login_required
def view_employees_crews():
    """View all employees and their crew assignments"""
    # Get all employees grouped by crew
    crews = {}
    employees = Employee.query.order_by(Employee.crew, Employee.name).all()
    
    for employee in employees:
        crew_name = employee.crew or 'Unassigned'
        if crew_name not in crews:
            crews[crew_name] = []
        crews[crew_name].append(employee)
    
    # Get positions
    positions = Position.query.all()
    
    # Get skills
    skills = Skill.query.all()
    
    # Calculate statistics
    stats = {
        'total_employees': len(employees),
        'total_crews': len([c for c in crews if c != 'Unassigned']),
        'total_supervisors': len([e for e in employees if e.is_supervisor]),
        'unassigned': len(crews.get('Unassigned', []))
    }
    
    return render_template('view_employees_crews.html',
                         crews=crews,
                         positions=positions,
                         skills=skills,
                         stats=stats)

@employee_bp.route('/overtime-management')
@login_required
def overtime_management():
    """View and manage overtime tracking with multi-level sorting"""
    # Check if user is supervisor
    if not current_user.is_supervisor:
        flash('You must be a supervisor to access this page.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    try:
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = 25  # Show 25 employees per page
        
        # Get filter parameters
        search_term = request.args.get('search', '')
        crew_filter = request.args.get('crew', '')
        position_filter = request.args.get('position', '')
        ot_range_filter = request.args.get('ot_range', '')
        
        # Get sorting parameters
        sort_params = []
        for i in range(1, 5):
            sort_field = request.args.get(f'sort{i}', '')
            sort_dir = request.args.get(f'dir{i}', 'asc')
            if sort_field:
                sort_params.append({'field': sort_field, 'direction': sort_dir})
        
        # Calculate date range for 13-week period
        end_date = date.today()
        start_date = end_date - timedelta(weeks=13)
        current_week_start = end_date - timedelta(days=end_date.weekday())
        
        # Build base query with overtime calculations
        # Using subqueries for current week and 13-week totals
        current_week_subquery = db.session.query(
            OvertimeHistory.employee_id,
            func.sum(OvertimeHistory.overtime_hours).label('current_week_hours')
        ).filter(
            OvertimeHistory.week_start_date >= current_week_start,
            OvertimeHistory.week_start_date <= end_date
        ).group_by(OvertimeHistory.employee_id).subquery()
        
        total_13week_subquery = db.session.query(
            OvertimeHistory.employee_id,
            func.sum(OvertimeHistory.overtime_hours).label('total_hours')
        ).filter(
            OvertimeHistory.week_start_date >= start_date,
            OvertimeHistory.week_start_date <= end_date
        ).group_by(OvertimeHistory.employee_id).subquery()
        
        # Main query
        query = db.session.query(
            Employee,
            func.coalesce(current_week_subquery.c.current_week_hours, 0).label('current_week_overtime'),
            func.coalesce(total_13week_subquery.c.total_hours, 0).label('last_13_weeks_overtime'),
            Position.name.label('position_name')
        ).outerjoin(
            current_week_subquery, Employee.id == current_week_subquery.c.employee_id
        ).outerjoin(
            total_13week_subquery, Employee.id == total_13week_subquery.c.employee_id
        ).outerjoin(
            Position, Employee.position_id == Position.id
        ).filter(
            Employee.is_active == True
        )
        
        # Apply search filter
        if search_term:
            query = query.filter(
                or_(
                    Employee.name.ilike(f'%{search_term}%'),
                    Employee.employee_id.ilike(f'%{search_term}%')
                )
            )
        
        # Apply crew filter
        if crew_filter:
            query = query.filter(Employee.crew == crew_filter)
        
        # Apply position filter
        if position_filter:
            query = query.filter(Employee.position_id == int(position_filter))
        
        # Apply OT range filter using having clause
        if ot_range_filter:
            if ot_range_filter == '0-50':
                query = query.having(
                    func.coalesce(total_13week_subquery.c.total_hours, 0).between(0, 50)
                )
            elif ot_range_filter == '50-100':
                query = query.having(
                    func.coalesce(total_13week_subquery.c.total_hours, 0).between(50, 100)
                )
            elif ot_range_filter == '100-150':
                query = query.having(
                    func.coalesce(total_13week_subquery.c.total_hours, 0).between(100, 150)
                )
            elif ot_range_filter == '150+':
                query = query.having(
                    func.coalesce(total_13week_subquery.c.total_hours, 0) > 150
                )
        
        # Apply multi-level sorting
        if sort_params:
            for sort in sort_params:
                if sort['field'] == 'crew':
                    if sort['direction'] == 'asc':
                        query = query.order_by(Employee.crew.asc())
                    else:
                        query = query.order_by(Employee.crew.desc())
                
                elif sort['field'] == 'jobtitle':
                    if sort['direction'] == 'asc':
                        query = query.order_by(Position.name.asc())
                    else:
                        query = query.order_by(Position.name.desc())
                
                elif sort['field'] == 'seniority':
                    if sort['direction'] == 'asc':
                        query = query.order_by(Employee.hire_date.desc())  # Newest first
                    else:
                        query = query.order_by(Employee.hire_date.asc())   # Oldest first
                
                elif sort['field'] == 'overtime':
                    if sort['direction'] == 'asc':
                        query = query.order_by('last_13_weeks_overtime')
                    else:
                        query = query.order_by(db.desc('last_13_weeks_overtime'))
        else:
            # Default sort by overtime descending
            query = query.order_by(db.desc('last_13_weeks_overtime'))
        
        # Execute pagination
        paginated_results = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Process results for display
        employees_data = []
        high_overtime_employees = []
        
        for result in paginated_results.items:
            employee = result.Employee if hasattr(result, 'Employee') else result[0]
            
            # Round overtime values to nearest whole number
            current_week_ot = round(float(result.current_week_overtime))
            total_13_week_ot = round(float(result.last_13_weeks_overtime))
            avg_weekly_ot = round(total_13_week_ot / 13) if total_13_week_ot > 0 else 0
            
            # Calculate seniority in years
            if employee.hire_date:
                years_employed = (datetime.now().date() - employee.hire_date).days / 365.25
            else:
                years_employed = 0
            
            # Determine overtime trend (simplified)
            if total_13_week_ot > 200:
                trend = 'increasing'
            elif total_13_week_ot < 100:
                trend = 'decreasing'
            else:
                trend = 'stable'
            
            employee_data = {
                'id': employee.id,
                'name': employee.name,
                'employee_id': employee.employee_id or f'EMP{employee.id}',
                'crew': employee.crew,
                'position': employee.position,
                'position_id': employee.position_id if employee.position else None,
                'hire_date': employee.hire_date,
                'years_employed': int(years_employed),
                'current_week_overtime': current_week_ot,
                'last_13_weeks_overtime': total_13_week_ot,
                'average_weekly_overtime': avg_weekly_ot,
                'overtime_trend': trend
            }
            
            employees_data.append(employee_data)
            
            # Track high overtime employees
            if current_week_ot > 60:
                high_overtime_employees.append(employee_data)
        
        # Get all positions for filter dropdown
        positions = Position.query.order_by(Position.name).all()
        
        # Calculate statistics for the dashboard
        # Get all employees for statistics (not just current page)
        all_employees_stats = db.session.query(
            func.count(Employee.id).label('total_count'),
            func.sum(func.coalesce(total_13week_subquery.c.total_hours, 0)).label('total_ot_hours')
        ).outerjoin(
            total_13week_subquery, Employee.id == total_13week_subquery.c.employee_id
        ).filter(
            Employee.is_active == True
        ).first()
        
        total_overtime_hours = round(float(all_employees_stats.total_ot_hours or 0))
        total_employees = all_employees_stats.total_count or 0
        avg_overtime = round(total_overtime_hours / total_employees) if total_employees > 0 else 0
        
        # Calculate crew overtime data for charts
        crew_stats = db.session.query(
            Employee.crew,
            func.sum(func.coalesce(total_13week_subquery.c.total_hours, 0)).label('crew_total')
        ).outerjoin(
            total_13week_subquery, Employee.id == total_13week_subquery.c.employee_id
        ).filter(
            Employee.is_active == True,
            Employee.crew.in_(['A', 'B', 'C', 'D'])
        ).group_by(Employee.crew).all()
        
        crew_overtime_data = [0, 0, 0, 0]  # For crews A, B, C, D
        crew_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
        for crew_stat in crew_stats:
            if crew_stat.crew in crew_map:
                crew_overtime_data[crew_map[crew_stat.crew]] = round(float(crew_stat.crew_total))
        
        return render_template('overtime_management.html',
                             employees=employees_data,
                             positions=positions,
                             page=page,
                             total_pages=paginated_results.pages,
                             start_date=start_date,
                             end_date=end_date,
                             current_date=datetime.now().date(),
                             high_overtime_employees=high_overtime_employees,
                             # Pass current filter/sort values back to template
                             search_term=search_term,
                             crew_filter=crew_filter,
                             position_filter=position_filter,
                             ot_range_filter=ot_range_filter,
                             sort_params=sort_params,
                             # Statistics
                             total_overtime_hours=total_overtime_hours,
                             employees_with_overtime=len([e for e in employees_data if e['last_13_weeks_overtime'] > 0]),
                             avg_overtime=avg_overtime,
                             high_overtime_count=len(high_overtime_employees),
                             crew_overtime_data=crew_overtime_data)
                             
    except Exception as e:
        # Log error and show user-friendly message
        print(f"Error in overtime_management: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Fallback to basic view if advanced features fail
        try:
            employees = Employee.query.filter_by(is_active=True).order_by(Employee.crew, Employee.name).all()
            
            # Add basic overtime data
            for emp in employees:
                emp.current_week_overtime = 0
                emp.last_13_weeks_overtime = 0
                emp.average_weekly_overtime = 0
                emp.overtime_trend = 'stable'
            
            return render_template('overtime_management.html',
                                 employees=employees,
                                 positions=Position.query.all(),
                                 page=1,
                                 total_pages=1,
                                 start_date=date.today() - timedelta(weeks=13),
                                 end_date=date.today(),
                                 current_date=date.today(),
                                 high_overtime_employees=[],
                                 search_term='',
                                 crew_filter='',
                                 position_filter='',
                                 ot_range_filter='',
                                 sort_params=[],
                                 total_overtime_hours=0,
                                 employees_with_overtime=0,
                                 avg_overtime=0,
                                 high_overtime_count=0,
                                 crew_overtime_data=[0, 0, 0, 0])
        except:
            flash('Error loading overtime data. Please try again later.', 'danger')
            return redirect(url_for('main.dashboard'))

@employee_bp.route('/overtime-management/export/excel')
@login_required
def export_overtime_excel():
    """Export overtime data to Excel with current filters and sorting"""
    if not current_user.is_supervisor:
        flash('You must be a supervisor to export data.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    try:
        import io
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        
        # Get the same parameters as the main view
        search_term = request.args.get('search', '')
        crew_filter = request.args.get('crew', '')
        position_filter = request.args.get('position', '')
        ot_range_filter = request.args.get('ot_range', '')
        
        # Get sorting parameters
        sort_params = []
        for i in range(1, 5):
            sort_field = request.args.get(f'sort{i}', '')
            sort_dir = request.args.get(f'dir{i}', 'asc')
            if sort_field:
                sort_params.append({'field': sort_field, 'direction': sort_dir})
        
        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(weeks=13)
        current_week_start = end_date - timedelta(days=end_date.weekday())
        
        # Build the same query (without pagination)
        current_week_subquery = db.session.query(
            OvertimeHistory.employee_id,
            func.sum(OvertimeHistory.overtime_hours).label('current_week_hours')
        ).filter(
            OvertimeHistory.week_start_date >= current_week_start,
            OvertimeHistory.week_start_date <= end_date
        ).group_by(OvertimeHistory.employee_id).subquery()
        
        total_13week_subquery = db.session.query(
            OvertimeHistory.employee_id,
            func.sum(OvertimeHistory.overtime_hours).label('total_hours')
        ).filter(
            OvertimeHistory.week_start_date >= start_date,
            OvertimeHistory.week_start_date <= end_date
        ).group_by(OvertimeHistory.employee_id).subquery()
        
        query = db.session.query(
            Employee,
            func.coalesce(current_week_subquery.c.current_week_hours, 0).label('current_week_overtime'),
            func.coalesce(total_13week_subquery.c.total_hours, 0).label('last_13_weeks_overtime'),
            Position.name.label('position_name')
        ).outerjoin(
            current_week_subquery, Employee.id == current_week_subquery.c.employee_id
        ).outerjoin(
            total_13week_subquery, Employee.id == total_13week_subquery.c.employee_id
        ).outerjoin(
            Position, Employee.position_id == Position.id
        ).filter(
            Employee.is_active == True
        )
        
        # Apply filters (same as main view)
        if search_term:
            query = query.filter(
                or_(
                    Employee.name.ilike(f'%{search_term}%'),
                    Employee.employee_id.ilike(f'%{search_term}%')
                )
            )
        
        if crew_filter:
            query = query.filter(Employee.crew == crew_filter)
        
        if position_filter:
            query = query.filter(Employee.position_id == int(position_filter))
        
        # Apply sorting (same as main view)
        if sort_params:
            for sort in sort_params:
                if sort['field'] == 'crew':
                    if sort['direction'] == 'asc':
                        query = query.order_by(Employee.crew.asc())
                    else:
                        query = query.order_by(Employee.crew.desc())
                elif sort['field'] == 'jobtitle':
                    if sort['direction'] == 'asc':
                        query = query.order_by(Position.name.asc())
                    else:
                        query = query.order_by(Position.name.desc())
                elif sort['field'] == 'seniority':
                    if sort['direction'] == 'asc':
                        query = query.order_by(Employee.hire_date.desc())
                    else:
                        query = query.order_by(Employee.hire_date.asc())
                elif sort['field'] == 'overtime':
                    if sort['direction'] == 'asc':
                        query = query.order_by('last_13_weeks_overtime')
                    else:
                        query = query.order_by(db.desc('last_13_weeks_overtime'))
        else:
            query = query.order_by(db.desc('last_13_weeks_overtime'))
        
        # Get all results
        results = query.all()
        
        # Create Excel workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Overtime Report"
        
        # Add title row
        ws.merge_cells('A1:I1')
        title_cell = ws['A1']
        title_cell.value = f"Overtime Report ({start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')})"
        title_cell.font = Font(size=16, bold=True)
        title_cell.alignment = Alignment(horizontal="center")
        
        # Headers
        headers = ['Employee Name', 'Employee ID', 'Crew', 'Position', 'Seniority (Years)', 
                   'Current Week OT', '13-Week Total OT', 'Weekly Average', 'Trend']
        
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=3, column=col, value=header)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="11998e", end_color="11998e", fill_type="solid")
            cell.alignment = Alignment(horizontal="center")
        
        # Data rows
        row_num = 4
        for result in results:
            employee = result.Employee if hasattr(result, 'Employee') else result[0]
            
            # Round overtime values
            current_week_ot = round(float(result.current_week_overtime))
            total_13_week_ot = round(float(result.last_13_weeks_overtime))
            avg_weekly_ot = round(total_13_week_ot / 13) if total_13_week_ot > 0 else 0
            
            # Calculate seniority
            if employee.hire_date:
                years_employed = int((datetime.now().date() - employee.hire_date).days / 365.25)
            else:
                years_employed = 0
            
            # Determine trend
            if total_13_week_ot > 200:
                trend = 'Increasing'
            elif total_13_week_ot < 100:
                trend = 'Decreasing'
            else:
                trend = 'Stable'
            
            ws.cell(row=row_num, column=1, value=employee.name)
            ws.cell(row=row_num, column=2, value=employee.employee_id or f'EMP{employee.id}')
            ws.cell(row=row_num, column=3, value=employee.crew or '-')
            ws.cell(row=row_num, column=4, value=employee.position.name if employee.position else '-')
            ws.cell(row=row_num, column=5, value=years_employed)
            ws.cell(row=row_num, column=6, value=current_week_ot)
            ws.cell(row=row_num, column=7, value=total_13_week_ot)
            ws.cell(row=row_num, column=8, value=avg_weekly_ot)
            ws.cell(row=row_num, column=9, value=trend)
            
            # Highlight high overtime
            if current_week_ot > 60:
                for col in range(1, 10):
                    ws.cell(row=row_num, column=col).fill = PatternFill(
                        start_color="FFCCCC", end_color="FFCCCC", fill_type="solid"
                    )
            
            row_num += 1
        
        # Add summary row
        ws.cell(row=row_num + 1, column=1, value="TOTAL")
        ws.cell(row=row_num + 1, column=1).font = Font(bold=True)
        
        # Auto-fit columns
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(cell.value)
                except:
                    pass
            adjusted_width = (max_length + 2)
            ws.column_dimensions[column_letter].width = adjusted_width
        
        # Save to BytesIO object
        excel_file = io.BytesIO()
        wb.save(excel_file)
        excel_file.seek(0)
        
        # Return as download
        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'overtime_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
        
    except Exception as e:
        print(f"Error exporting to Excel: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Error exporting data. Please try again.', 'danger')
        return redirect(url_for('employee.overtime_management'))

@employee_bp.route('/vacation/request', methods=['GET', 'POST'])
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
            return redirect(url_for('employee.vacation_request'))
        elif request_type == 'sick' and days_requested > current_user.sick_days:
            flash('Insufficient sick days available.', 'danger')
            return redirect(url_for('employee.vacation_request'))
        elif request_type == 'personal' and days_requested > current_user.personal_days:
            flash('Insufficient personal days available.', 'danger')
            return redirect(url_for('employee.vacation_request'))
        
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
        return redirect(url_for('main.employee_dashboard'))
    
    return render_template('vacation_request.html',
                         vacation_days=current_user.vacation_days,
                         sick_days=current_user.sick_days,
                         personal_days=current_user.personal_days)

@employee_bp.route('/swap-request', methods=['POST'])
@login_required
def create_swap_request():
    """Create a shift swap request"""
    schedule_id = request.form.get('schedule_id')
    reason = request.form.get('reason', '')
    
    schedule = Schedule.query.get_or_404(schedule_id)
    
    if schedule.employee_id != current_user.id:
        flash('You can only request swaps for your own shifts.', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
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
    return redirect(url_for('main.employee_dashboard'))

@employee_bp.route('/sleep-dashboard')
@login_required
def sleep_dashboard():
    """Main sleep health dashboard"""
    # Get or create circadian profile
    profile = CircadianProfile.query.filter_by(employee_id=current_user.id).first()
    if not profile:
        return redirect(url_for('employee.sleep_profile'))
    
    # Get recent sleep logs
    from models import SleepLog, SleepRecommendation
    recent_logs = SleepLog.query.filter_by(
        employee_id=current_user.id
    ).order_by(SleepLog.date.desc()).limit(7).all()
    
    # Get active recommendations
    recommendations = SleepRecommendation.query.filter_by(
        employee_id=current_user.id,
        is_active=True
    ).order_by(SleepRecommendation.priority).all()
    
    # Get upcoming shift changes
    upcoming_schedules = Schedule.query.filter(
        Schedule.employee_id == current_user.id,
        Schedule.date >= date.today(),
        Schedule.date <= date.today() + timedelta(days=14)
    ).order_by(Schedule.date).all()
    
    return render_template('sleep_dashboard.html',
                         profile=profile,
                         recent_logs=recent_logs,
                         recommendations=recommendations,
                         upcoming_schedules=upcoming_schedules)

@employee_bp.route('/sleep-profile', methods=['GET', 'POST'])
@login_required
def sleep_profile():
    """Complete chronotype assessment"""
    if request.method == 'POST':
        # Create or update circadian profile
        profile = CircadianProfile.query.filter_by(employee_id=current_user.id).first()
        if not profile:
            profile = CircadianProfile(employee_id=current_user.id)
        
        profile.chronotype = request.form.get('chronotype')
        profile.preferred_sleep_time = datetime.strptime(request.form.get('preferred_sleep_time'), '%H:%M').time()
        profile.preferred_wake_time = datetime.strptime(request.form.get('preferred_wake_time'), '%H:%M').time()
        
        db.session.add(profile)
        db.session.commit()
        
        flash('Sleep profile updated successfully!', 'success')
        return redirect(url_for('employee.sleep_dashboard'))
    
    profile = CircadianProfile.query.filter_by(employee_id=current_user.id).first()
    return render_template('sleep_profile_form.html', profile=profile)

@employee_bp.route('/position/messages')
@login_required
def position_messages():
    """View messages for employee's position"""
    if not current_user.position_id:
        flash('You must be assigned to a position to view position messages.', 'warning')
        return redirect(url_for('main.employee_dashboard'))
    
    from models import PositionMessage
    
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

@employee_bp.route('/shift-marketplace')
@login_required
def shift_marketplace():
    """Main shift trade marketplace view"""
    from models import ShiftTradePost, ShiftTrade, ShiftTradeProposal
    
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
    from utils.helpers import calculate_trade_compatibility
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
    from utils.helpers import get_trade_history
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

@employee_bp.route('/maintenance/report', methods=['GET', 'POST'])
@login_required
def report_maintenance():
    """Report a maintenance issue"""
    if request.method == 'POST':
        try:
            from models import MaintenanceIssue, MaintenanceUpdate, MaintenanceManager
            
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
                status='open',
                reported_at=datetime.now()
            )
            
            # Try to auto-assign to primary maintenance manager if exists
            try:
                primary_manager = MaintenanceManager.query.filter_by(is_primary=True).first()
                if primary_manager:
                    issue.assigned_to_id = primary_manager.employee_id
            except:
                pass
            
            db.session.add(issue)
            db.session.flush()
            
            # Create initial update
            try:
                update = MaintenanceUpdate(
                    issue_id=issue.id,
                    author_id=current_user.id,
                    update_type='comment',
                    message=f"Issue reported: {description}",
                    created_at=datetime.now()
                )
                db.session.add(update)
            except:
                pass
            
            db.session.commit()
            
            flash('Maintenance issue reported successfully!', 'success')
            return redirect(url_for('employee.maintenance_issues'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error reporting issue: {str(e)}', 'danger')
            return redirect(url_for('employee.report_maintenance'))
    
    return render_template('report_maintenance.html')

@employee_bp.route('/maintenance/issues')
@login_required
def maintenance_issues():
    """View maintenance issues"""
    from models import MaintenanceIssue, MaintenanceManager
    
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
    from sqlalchemy import case
    issues = issues_query.order_by(
        case(
            (MaintenanceIssue.priority == 'critical', 1),
            (MaintenanceIssue.priority == 'high', 2),
            (MaintenanceIssue.priority == 'normal', 3),
            (MaintenanceIssue.priority == 'low', 4)
        ),
        MaintenanceIssue.reported_at.desc()
    ).all()
    
    # Get statistics for managers
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
            pass
    
    return render_template('maintenance_issues.html',
                         issues=issues,
                         is_manager=is_manager,
                         stats=stats,
                         status_filter=status_filter)
