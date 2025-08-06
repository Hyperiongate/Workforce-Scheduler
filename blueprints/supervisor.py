# blueprints/supervisor.py - COMPLETE FILE WITH BLUEPRINT DEFINITION
"""
Supervisor blueprint - Complete implementation
Handles all supervisor-specific functionality
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from datetime import date, timedelta, datetime
from sqlalchemy import or_, func, case, and_
import pandas as pd
import io
from werkzeug.utils import secure_filename
import os

# Import all required models
from models import (
    db, Employee, Schedule, VacationCalendar, Position, Skill, 
    TimeOffRequest, ShiftSwapRequest, CircadianProfile, CoverageNotification, 
    OvertimeHistory, SleepLog, PositionMessage, MessageReadReceipt, 
    MaintenanceIssue, ShiftTradePost, ShiftTradeProposal, ShiftTrade,
    FileUpload, Availability, CoverageRequest, OvertimeOpportunity,
    CoverageGap, ScheduleSuggestion, CrewCoverageRequirement
)

# CREATE THE BLUEPRINT - THIS WAS MISSING!
supervisor_bp = Blueprint('supervisor', __name__)

# Helper decorator for supervisor-only routes
def supervisor_required(f):
    """Decorator to require supervisor access"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.is_supervisor:
            flash('You must be a supervisor to access this page.', 'danger')
            return redirect(url_for('main.employee_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

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
                        vacation_days=10,
                        sick_days=5,
                        personal_days=3
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

@supervisor_bp.route('/employees/crew-management')
@login_required
@supervisor_required
def crew_management():
    """Interactive crew management interface"""
    employees = Employee.query.filter(Employee.id != current_user.id).order_by(Employee.crew, Employee.name).all()
    positions = Position.query.order_by(Position.name).all()
    
    return render_template('crew_management.html',
                         employees=employees,
                         positions=positions)

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

# ========== COVERAGE NEEDS ROUTES ==========

@supervisor_bp.route('/supervisor/coverage-needs')
@login_required
@supervisor_required
def coverage_needs():
    """View and manage coverage needs"""
    try:
        # Get all positions
        positions = Position.query.order_by(Position.name).all()
        
        # Get current coverage requirements
        requirements = {}
        for position in positions:
            reqs = CrewCoverageRequirement.query.filter_by(position_id=position.id).all()
            requirements[position.id] = {req.crew: req.minimum_required for req in reqs}
        
        # Calculate current staffing
        current_staffing = {}
        for crew in ['A', 'B', 'C', 'D']:
            current_staffing[crew] = {}
            for position in positions:
                count = Employee.query.filter_by(
                    crew=crew,
                    position_id=position.id
                ).count()
                current_staffing[crew][position.id] = count
        
        return render_template('coverage_needs.html',
                             positions=positions,
                             requirements=requirements,
                             current_staffing=current_staffing)
                             
    except Exception as e:
        flash(f'Error loading coverage needs: {str(e)}', 'danger')
        return redirect(url_for('main.dashboard'))

@supervisor_bp.route('/api/coverage-needs', methods=['POST'])
@login_required
@supervisor_required
def update_coverage_needs():
    """Update coverage requirements via API"""
    try:
        data = request.get_json()
        
        for position_id, crews in data.items():
            for crew, minimum in crews.items():
                # Find or create requirement
                req = CrewCoverageRequirement.query.filter_by(
                    position_id=int(position_id),
                    crew=crew
                ).first()
                
                if req:
                    req.minimum_required = int(minimum)
                else:
                    req = CrewCoverageRequirement(
                        position_id=int(position_id),
                        crew=crew,
                        minimum_required=int(minimum)
                    )
                    db.session.add(req)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Coverage requirements updated'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

# ========== TIME OFF MANAGEMENT ROUTES ==========

@supervisor_bp.route('/supervisor/time-off-requests')
@login_required
@supervisor_required
def time_off_requests():
    """View and manage time off requests"""
    # Get pending requests
    pending_requests = TimeOffRequest.query.filter_by(status='pending').order_by(TimeOffRequest.created_at.desc()).all()
    
    # Get recent approved/denied requests
    recent_requests = TimeOffRequest.query.filter(
        TimeOffRequest.status.in_(['approved', 'denied'])
    ).order_by(TimeOffRequest.created_at.desc()).limit(20).all()
    
    return render_template('time_off_requests.html',
                         pending_requests=pending_requests,
                         recent_requests=recent_requests)

@supervisor_bp.route('/supervisor/approve-time-off/<int:request_id>', methods=['POST'])
@login_required
@supervisor_required
def approve_time_off(request_id):
    """Approve a time off request"""
    time_off = TimeOffRequest.query.get_or_404(request_id)
    
    try:
        # Update request status
        time_off.status = 'approved'
        time_off.approved_by = current_user.id
        time_off.approved_date = datetime.now()
        
        # Deduct from employee balance
        employee = time_off.employee
        days_requested = time_off.days_requested or 1
        
        if time_off.request_type == 'vacation':
            employee.vacation_days -= days_requested
        elif time_off.request_type == 'sick':
            employee.sick_days -= days_requested
        elif time_off.request_type == 'personal':
            employee.personal_days -= days_requested
        
        # Add to vacation calendar
        current_date = time_off.start_date
        while current_date <= time_off.end_date:
            calendar_entry = VacationCalendar(
                employee_id=employee.id,
                date=current_date,
                reason=time_off.request_type,
                status='approved'
            )
            db.session.add(calendar_entry)
            current_date += timedelta(days=1)
        
        db.session.commit()
        flash(f'Time off request approved for {employee.name}', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error approving request: {str(e)}', 'danger')
    
    return redirect(url_for('supervisor.time_off_requests'))

# ========== DOWNLOAD TEMPLATE ROUTES ==========

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

# ========== API ROUTES ==========

@supervisor_bp.route('/api/employee/<int:employee_id>/crew', methods=['PUT'])
@login_required
@supervisor_required
def update_employee_crew(employee_id):
    """API endpoint to update employee crew assignment"""
    employee = Employee.query.get_or_404(employee_id)
    data = request.get_json()
    
    new_crew = data.get('crew')
    if new_crew in ['A', 'B', 'C', 'D', 'UNASSIGNED']:
        employee.crew = new_crew if new_crew != 'UNASSIGNED' else None
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Invalid crew'}), 400
