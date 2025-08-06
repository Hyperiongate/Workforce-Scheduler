# blueprints/supervisor.py - COMPLETE Employee Management Section
# This is the complete code for the employee management functionality
# Replace the entire employee management section in your supervisor.py with this

# ========== EMPLOYEE MANAGEMENT ROUTES ==========

@supervisor_bp.route('/employees/management')
@login_required
@supervisor_required
def employee_management():
    """Employee management page with complete functionality"""
    try:
        # Import required for or_ operator
        from sqlalchemy import or_
        
        # Get all employees except current user
        employees = Employee.query.filter(Employee.id != current_user.id).order_by(Employee.crew, Employee.name).all()
        employee_count = len(employees)
        
        # REQUIRED: Calculate crew_stats - template expects this
        crew_stats = {}
        for crew in ['A', 'B', 'C', 'D', 'Unassigned']:
            if crew == 'Unassigned':
                # Count employees with no crew or empty crew
                count = Employee.query.filter(
                    Employee.id != current_user.id
                ).filter(
                    or_(Employee.crew == None, Employee.crew == '')
                ).count()
            else:
                # Count employees in specific crew
                count = Employee.query.filter(
                    Employee.id != current_user.id
                ).filter_by(crew=crew).count()
            crew_stats[crew] = count
        
        # Get positions for dropdown
        positions = Position.query.order_by(Position.name).all()
        
        # FIXED: Changed from employee_management_new.html to employee_management.html
        return render_template('employee_management.html',
                             employees=employees,
                             employee_count=employee_count,
                             crew_stats=crew_stats,  # REQUIRED by template
                             positions=positions)
                             
    except Exception as e:
        flash(f'Error loading employee management: {str(e)}', 'danger')
        return redirect(url_for('main.dashboard'))  # Fixed: main.dashboard not supervisor.dashboard

@supervisor_bp.route('/employees/upload', methods=['POST'])
@login_required
@supervisor_required
def upload_employees():
    """Handle employee Excel file upload with validation"""
    if 'file' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for('supervisor.employee_management'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('supervisor.employee_management'))
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        flash('Please upload an Excel file (.xlsx or .xls)', 'danger')
        return redirect(url_for('supervisor.employee_management'))
    
    try:
        # Read Excel file
        df = pd.read_excel(file, sheet_name='Employee Data')
        
        # Validate required columns
        required_columns = ['Employee ID', 'First Name', 'Last Name', 'Email', 'Crew', 'Position']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            flash(f'Missing required columns: {", ".join(missing_columns)}', 'danger')
            return redirect(url_for('supervisor.employee_management'))
        
        # Process employees
        created = 0
        updated = 0
        errors = []
        
        for index, row in df.iterrows():
            try:
                employee_id = str(row['Employee ID']).strip()
                
                # Check if employee exists
                employee = Employee.query.filter_by(employee_id=employee_id).first()
                
                if employee:
                    # Update existing employee
                    employee.name = f"{row['First Name']} {row['Last Name']}"
                    employee.email = row['Email']
                    employee.crew = row['Crew'] if row['Crew'] in ['A', 'B', 'C', 'D'] else None
                    
                    # Update position if it exists
                    if pd.notna(row['Position']):
                        position = Position.query.filter_by(name=row['Position']).first()
                        if position:
                            employee.position_id = position.id
                    
                    updated += 1
                else:
                    # Create new employee
                    employee = Employee(
                        employee_id=employee_id,
                        name=f"{row['First Name']} {row['Last Name']}",
                        email=row['Email'],
                        crew=row['Crew'] if row['Crew'] in ['A', 'B', 'C', 'D'] else None,
                        is_supervisor=False,
                        vacation_days=0,
                        sick_days=0,
                        personal_days=0
                    )
                    
                    # Set position if it exists
                    if pd.notna(row['Position']):
                        position = Position.query.filter_by(name=row['Position']).first()
                        if position:
                            employee.position_id = position.id
                    
                    # Generate password
                    employee.set_password('TempPass123!')
                    
                    db.session.add(employee)
                    created += 1
                    
            except Exception as e:
                errors.append(f'Row {index + 2}: {str(e)}')
                continue
        
        # Commit changes
        db.session.commit()
        
        # Build success message
        message = f'Upload complete: {created} created, {updated} updated.'
        if errors:
            message += f' {len(errors)} errors occurred.'
            for error in errors[:5]:  # Show first 5 errors
                flash(error, 'warning')
        
        flash(message, 'success' if created > 0 or updated > 0 else 'warning')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing file: {str(e)}', 'danger')
    
    return redirect(url_for('supervisor.employee_management'))

@supervisor_bp.route('/employees/edit/<int:employee_id>', methods=['GET', 'POST'])
@login_required
@supervisor_required
def edit_employee(employee_id):
    """Edit employee information"""
    employee = Employee.query.get_or_404(employee_id)
    
    if request.method == 'POST':
        try:
            # Update employee fields
            employee.name = request.form.get('name')
            employee.email = request.form.get('email')
            employee.crew = request.form.get('crew')
            employee.employee_id = request.form.get('employee_id')
            
            # Update position
            position_id = request.form.get('position_id')
            if position_id:
                employee.position_id = int(position_id)
            
            # Update time-off balances
            employee.vacation_days = float(request.form.get('vacation_days', 0))
            employee.sick_days = float(request.form.get('sick_days', 0))
            employee.personal_days = float(request.form.get('personal_days', 0))
            
            # Update supervisor status
            employee.is_supervisor = 'is_supervisor' in request.form
            
            db.session.commit()
            flash(f'Successfully updated {employee.name}', 'success')
            return redirect(url_for('supervisor.employee_management'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating employee: {str(e)}', 'danger')
    
    positions = Position.query.order_by(Position.name).all()
    return render_template('edit_employee.html', 
                         employee=employee, 
                         positions=positions)

@supervisor_bp.route('/employees/delete/<int:employee_id>', methods=['POST'])
@login_required
@supervisor_required
def delete_employee(employee_id):
    """Delete/deactivate an employee"""
    try:
        employee = Employee.query.get_or_404(employee_id)
        
        # Don't allow deleting yourself
        if employee.id == current_user.id:
            flash('You cannot delete your own account', 'danger')
            return redirect(url_for('supervisor.employee_management'))
        
        # Instead of hard delete, mark as inactive (if column exists)
        # Otherwise, delete the employee
        try:
            employee.is_active = False
            db.session.commit()
            flash(f'Successfully deactivated {employee.name}', 'success')
        except AttributeError:
            # is_active doesn't exist, do hard delete
            db.session.delete(employee)
            db.session.commit()
            flash(f'Successfully deleted {employee.name}', 'success')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting employee: {str(e)}', 'danger')
    
    return redirect(url_for('supervisor.employee_management'))

@supervisor_bp.route('/employees/download-template')
@login_required
@supervisor_required
def download_employee_template():
    """Download the employee import template"""
    try:
        # Create template structure
        template_data = {
            'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
            'First Name': ['John', 'Jane', 'Bob'],
            'Last Name': ['Smith', 'Doe', 'Johnson'],
            'Email': ['john.smith@company.com', 'jane.doe@company.com', 'bob.johnson@company.com'],
            'Crew': ['A', 'B', 'C'],
            'Position': ['Operator', 'Supervisor', 'Technician'],
            'Department': ['Production', 'Production', 'Maintenance'],
            'Hire Date': ['2020-01-15', '2019-06-20', '2021-03-10'],
            'Phone': ['555-0101', '555-0102', '555-0103']
        }
        
        df = pd.DataFrame(template_data)
        
        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Employee Data', index=False)
            
            # Get workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets['Employee Data']
            
            # Add formatting
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#4472C4',
                'font_color': 'white',
                'border': 1
            })
            
            # Apply header formatting
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            # Set column widths
            worksheet.set_column('A:A', 12)  # Employee ID
            worksheet.set_column('B:C', 15)  # Names
            worksheet.set_column('D:D', 30)  # Email
            worksheet.set_column('E:E', 8)   # Crew
            worksheet.set_column('F:I', 15)  # Other columns
            
            # Add instructions sheet
            instructions = writer.book.add_worksheet('Instructions')
            instructions.write(0, 0, 'EMPLOYEE IMPORT TEMPLATE INSTRUCTIONS', workbook.add_format({'bold': True, 'size': 14}))
            instructions.write(2, 0, '1. Fill out the Employee Data sheet with your employee information')
            instructions.write(3, 0, '2. Employee ID must be unique for each employee')
            instructions.write(4, 0, '3. Crew must be A, B, C, or D')
            instructions.write(5, 0, '4. Email addresses must be unique')
            instructions.write(6, 0, '5. Delete the example rows before importing')
            instructions.write(7, 0, '6. Save the file and upload it to the system')
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'employee_import_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
        )
        
    except Exception as e:
        flash(f'Error creating template: {str(e)}', 'danger')
        return redirect(url_for('supervisor.employee_management'))

@supervisor_bp.route('/employees/export-current')
@login_required
@supervisor_required
def export_current_employees():
    """Export current employee data to Excel"""
    try:
        # Get all employees
        employees = Employee.query.order_by(Employee.crew, Employee.name).all()
        
        # Create DataFrame
        data = []
        for emp in employees:
            data.append({
                'Employee ID': emp.employee_id,
                'First Name': emp.name.split()[0] if emp.name else '',
                'Last Name': ' '.join(emp.name.split()[1:]) if emp.name and len(emp.name.split()) > 1 else '',
                'Email': emp.email,
                'Crew': emp.crew or '',
                'Position': emp.position.name if emp.position else '',
                'Department': emp.position.department if emp.position else '',
                'Hire Date': emp.hire_date.strftime('%Y-%m-%d') if hasattr(emp, 'hire_date') and emp.hire_date else '',
                'Is Supervisor': 'Yes' if emp.is_supervisor else 'No',
                'Vacation Days': emp.vacation_days,
                'Sick Days': emp.sick_days,
                'Personal Days': emp.personal_days
            })
        
        df = pd.DataFrame(data)
        
        # Create Excel file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Employee Data', index=False)
            
            # Formatting
            workbook = writer.book
            worksheet = writer.sheets['Employee Data']
            
            # Header format
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#4472C4',
                'font_color': 'white',
                'border': 1
            })
            
            # Apply formatting
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            # Auto-fit columns
            for column in df:
                column_width = max(df[column].astype(str).map(len).max(), len(column)) + 2
                col_idx = df.columns.get_loc(column)
                worksheet.set_column(col_idx, col_idx, column_width)
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'employee_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
        
    except Exception as e:
        flash(f'Error exporting employees: {str(e)}', 'danger')
        return redirect(url_for('supervisor.employee_management'))

# VERIFICATION: Check all routes reference the correct template
# All redirects go to supervisor.employee_management
# Template name is employee_management.html (not employee_management_new.html)
