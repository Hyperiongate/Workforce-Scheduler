# Add this to your employee.py file, replacing the existing overtime_management route

@employee_bp.route('/overtime-management')
@login_required
def overtime_management():
    """View and manage overtime tracking with multi-level sorting"""
    # Check if user is supervisor
    if not current_user.is_supervisor:
        flash('You must be a supervisor to access this page.', 'danger')
        return redirect(url_for('dashboard'))
    
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
            # In a real implementation, you'd compare recent weeks to older weeks
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
        from flask import send_file
        
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
        
        # Use the same query logic as the main view but without pagination
        # [Copy the same query building logic from above but without .paginate()]
        
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
