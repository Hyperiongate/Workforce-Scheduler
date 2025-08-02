# blueprints/employee_import.py - Fixed version without external dependencies

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify, current_app
from flask_login import login_required, current_user
from functools import wraps
import pandas as pd
import io
from datetime import datetime, date, timedelta
import traceback
import os
import tempfile
from werkzeug.utils import secure_filename
from models import db, Employee, Position, OvertimeHistory, Skill, EmployeeSkill, FileUpload
from sqlalchemy import func
import re

# Create the blueprint
employee_import_bp = Blueprint('employee_import', __name__)

def supervisor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))
        if not current_user.is_supervisor:
            flash('Access denied. Supervisor privileges required.', 'error')
            return redirect(url_for('main.employee_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Simple validation helper
def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

# Template download routes
@employee_import_bp.route('/download-employee-template')
@login_required
@supervisor_required
def download_employee_template():
    """Download the employee import template"""
    try:
        # Create a sample template
        template_data = {
            'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
            'First Name': ['John', 'Jane', 'Bob'],
            'Last Name': ['Doe', 'Smith', 'Johnson'],
            'Email': ['john.doe@company.com', 'jane.smith@company.com', 'bob.johnson@company.com'],
            'Crew': ['A', 'B', 'C'],
            'Position': ['Operator', 'Technician', 'Operator'],
            'Department': ['Production', 'Maintenance', 'Production'],
            'Hire Date': ['2020-01-15', '2019-06-01', '2021-03-20'],
            'Phone': ['555-0101', '555-0102', '555-0103'],
            'Emergency Contact': ['Mary Doe (555-0201)', 'Jim Smith (555-0202)', 'Alice Johnson (555-0203)'],
            'Skills': ['Forklift, Safety', 'Electrical, HVAC', 'Forklift'],
            'Is Supervisor': ['No', 'No', 'Yes']
        }
        
        df = pd.DataFrame(template_data)
        
        # Create Excel file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Employee Data', index=False)
            
            # Add instructions sheet
            instructions = pd.DataFrame({
                'Instructions': [
                    'Employee Import Template Instructions',
                    '',
                    '1. Fill in all required fields (Employee ID, First Name, Last Name, Email, Crew)',
                    '2. Crew must be A, B, C, or D',
                    '3. Position must match existing positions in the system',
                    '4. Hire Date format: YYYY-MM-DD',
                    '5. Skills should be comma-separated',
                    '6. Is Supervisor: Yes or No',
                    '',
                    'Do not modify column headers or sheet names'
                ]
            })
            instructions.to_excel(writer, sheet_name='Instructions', index=False, header=False)
            
            # Format the Excel file
            workbook = writer.book
            worksheet = writer.sheets['Employee Data']
            
            # Set column widths
            worksheet.set_column('A:A', 15)  # Employee ID
            worksheet.set_column('B:C', 15)  # Names
            worksheet.set_column('D:D', 25)  # Email
            worksheet.set_column('E:E', 10)  # Crew
            worksheet.set_column('F:G', 15)  # Position, Department
            worksheet.set_column('H:H', 15)  # Hire Date
            worksheet.set_column('I:J', 20)  # Phone, Emergency
            worksheet.set_column('K:K', 30)  # Skills
            worksheet.set_column('L:L', 15)  # Is Supervisor
        
        output.seek(0)
        
        filename = f'employee_import_template_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        current_app.logger.error(f"Error generating employee template: {str(e)}")
        flash(f'Error generating template: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

@employee_import_bp.route('/download-overtime-template')
@login_required
@supervisor_required
def download_overtime_template():
    """Download the overtime history template"""
    try:
        # Get current employees
        employees = Employee.query.filter(
            Employee.email != 'admin@workforce.com'
        ).order_by(Employee.crew, Employee.name).all()
        
        # Create template data
        data = []
        for emp in employees:
            row = {
                'Employee ID': emp.employee_id or f'EMP{emp.id}',
                'Employee Name': emp.name,
                'Crew': emp.crew
            }
            # Add 13 weeks of columns
            for week in range(1, 14):
                row[f'Week {week}'] = 0
            data.append(row)
        
        df = pd.DataFrame(data)
        
        # Create Excel file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Overtime Data', index=False)
            
            # Add instructions
            instructions = pd.DataFrame({
                'Instructions': [
                    'Overtime History Import Template',
                    '',
                    '1. Do not modify Employee ID, Name, or Crew columns',
                    '2. Enter overtime hours for each week (0-168)',
                    '3. Week 1 is the oldest week, Week 13 is the most recent',
                    '4. Leave blank or enter 0 for no overtime',
                    '5. Decimal hours are allowed (e.g., 8.5)',
                    '',
                    'The system will match records by Employee ID'
                ]
            })
            instructions.to_excel(writer, sheet_name='Instructions', index=False, header=False)
            
            # Format
            workbook = writer.book
            worksheet = writer.sheets['Overtime Data']
            
            # Set column widths
            worksheet.set_column('A:A', 15)  # Employee ID
            worksheet.set_column('B:B', 25)  # Name
            worksheet.set_column('C:C', 10)  # Crew
            worksheet.set_column('D:P', 10)  # Week columns
        
        output.seek(0)
        
        filename = f'overtime_history_template_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        current_app.logger.error(f"Error generating overtime template: {str(e)}")
        flash(f'Error generating template: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

@employee_import_bp.route('/download-bulk-update-template/<template_type>')
@login_required
@supervisor_required
def download_bulk_update_template(template_type):
    """Download bulk update templates"""
    try:
        if template_type not in ['employee', 'overtime']:
            flash('Invalid template type', 'error')
            return redirect(url_for('main.dashboard'))
        
        if template_type == 'employee':
            # Create employee update template
            employees = Employee.query.filter(
                Employee.email != 'admin@workforce.com'
            ).all()
            
            data = []
            for emp in employees:
                data.append({
                    'Employee ID': emp.employee_id or f'EMP{emp.id}',
                    'Current Name': emp.name,
                    'New Name': emp.name,
                    'Current Email': emp.email,
                    'New Email': emp.email,
                    'Current Crew': emp.crew,
                    'New Crew': emp.crew,
                    'Current Position': emp.position.name if emp.position else '',
                    'New Position': emp.position.name if emp.position else '',
                    'Action': 'UPDATE'  # UPDATE or DELETE
                })
            
            df = pd.DataFrame(data)
            sheet_name = 'Employee Updates'
            
        else:  # overtime
            data = []
            employees = Employee.query.all()
            
            for emp in employees:
                data.append({
                    'Employee ID': emp.employee_id or f'EMP{emp.id}',
                    'Employee Name': emp.name,
                    'Current Week OT': 0,
                    'Adjustment': 0,
                    'Reason': ''
                })
            
            df = pd.DataFrame(data)
            sheet_name = 'Overtime Updates'
        
        # Create Excel file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        output.seek(0)
        filename = f'{template_type}_bulk_update_template_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        current_app.logger.error(f"Error generating bulk update template: {str(e)}")
        flash(f'Error generating template: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

# Enhanced upload page - SIMPLIFIED VERSION
@employee_import_bp.route('/upload-employees', methods=['GET', 'POST'])
@login_required
@supervisor_required
def upload_employees():
    """Employee data upload page"""
    if request.method == 'GET':
        try:
            # Get statistics
            employee_count = Employee.query.filter(Employee.id != current_user.id).count()
            
            # Get recent uploads
            recent_uploads = FileUpload.query.filter_by(
                file_type='employee_import'
            ).order_by(FileUpload.upload_date.desc()).limit(10).all()
            
            # Get crew distribution
            crew_stats = db.session.query(
                Employee.crew,
                func.count(Employee.id)
            ).filter(
                Employee.id != current_user.id
            ).group_by(Employee.crew).all()
            
            crew_distribution = {crew: count for crew, count in crew_stats if crew}
            
            # Use the simpler template for now
            return render_template('upload_employees.html',
                                 employee_count=employee_count,
                                 recent_uploads=recent_uploads,
                                 crew_distribution=crew_distribution)
                                 
        except Exception as e:
            current_app.logger.error(f"Error in upload_employees GET: {str(e)}")
            current_app.logger.error(traceback.format_exc())
            flash(f'Error loading upload page: {str(e)}', 'error')
            return redirect(url_for('main.dashboard'))
    
    # POST - Process upload
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(request.url)
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        flash('Please upload an Excel file (.xlsx or .xls)', 'error')
        return redirect(request.url)
    
    try:
        # Use a different folder name to avoid conflicts
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
        
        # Get the absolute path for the upload folder
        if not os.path.isabs(upload_folder):
            upload_folder = os.path.join(current_app.root_path, upload_folder)
        
        # Check if path exists and handle accordingly
        try:
            if os.path.exists(upload_folder):
                if os.path.isfile(upload_folder):
                    # If it's a file, use a different name
                    current_app.logger.warning(f"{upload_folder} exists as a file, using alternative")
                    upload_folder = os.path.join(current_app.root_path, 'upload_files')
            
            # Create directory if it doesn't exist
            if not os.path.exists(upload_folder) or not os.path.isdir(upload_folder):
                os.makedirs(upload_folder, exist_ok=True)
                current_app.logger.info(f"Created upload folder: {upload_folder}")
                
        except Exception as e:
            current_app.logger.error(f"Error with upload folder: {str(e)}")
            # Use temp directory as fallback
            upload_folder = tempfile.gettempdir()
            current_app.logger.info(f"Using temp directory: {upload_folder}")
        
        # Save file temporarily
        filename = secure_filename(file.filename)
        temp_path = os.path.join(upload_folder, filename)
        
        try:
            file.save(temp_path)
            current_app.logger.info(f"File saved to: {temp_path}")
        except Exception as e:
            current_app.logger.error(f"Error saving file: {str(e)}")
            raise
        
        # Read and process the file
        df = pd.read_excel(temp_path, sheet_name='Employee Data')
        
        # Process based on replace_all option (default to True for simplicity)
        replace_all = True
        
        if replace_all:
            # Delete existing employees (except admin) and their related records
            try:
                # First, delete related records
                employees_to_delete = Employee.query.filter(Employee.email != 'admin@workforce.com').all()
                employee_ids = [emp.id for emp in employees_to_delete]
                
                if employee_ids:
                    # Delete employee skills
                    EmployeeSkill.query.filter(EmployeeSkill.employee_id.in_(employee_ids)).delete(synchronize_session=False)
                    
                    # Delete overtime history
                    OvertimeHistory.query.filter(OvertimeHistory.employee_id.in_(employee_ids)).delete(synchronize_session=False)
                    
                    # Delete time off requests
                    if hasattr(db.Model, 'TimeOffRequest'):
                        db.session.execute(f"DELETE FROM time_off_request WHERE employee_id IN ({','.join(map(str, employee_ids))})")
                    
                    # Delete shift swap requests
                    if hasattr(db.Model, 'ShiftSwapRequest'):
                        db.session.execute(f"DELETE FROM shift_swap_request WHERE requester_id IN ({','.join(map(str, employee_ids))}) OR target_employee_id IN ({','.join(map(str, employee_ids))})")
                    
                    # Delete schedules
                    if hasattr(db.Model, 'Schedule'):
                        db.session.execute(f"DELETE FROM schedule WHERE employee_id IN ({','.join(map(str, employee_ids))})")
                    
                    # Commit the deletions
                    db.session.commit()
                    
                    # Now delete the employees
                    Employee.query.filter(Employee.email != 'admin@workforce.com').delete()
                    db.session.commit()
                    
                current_app.logger.info(f"Deleted {len(employee_ids)} employees and their related records")
                
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error during deletion: {str(e)}")
                flash('Error clearing existing data. Please try again.', 'error')
                return redirect(url_for('employee_import.upload_employees'))
        
        # Process each row
        success_count = 0
        error_count = 0
        errors = []
        
        for index, row in df.iterrows():
            try:
                # Get or create employee
                employee_id = str(row.get('Employee ID', '')).strip()
                email = str(row.get('Email', '')).strip()
                
                if not email or not validate_email(email):
                    error_count += 1
                    errors.append(f"Row {index + 2}: Invalid email")
                    continue
                
                if replace_all:
                    employee = Employee()
                else:
                    employee = Employee.query.filter(
                        (Employee.employee_id == employee_id) | 
                        (Employee.email == email)
                    ).first()
                    if not employee:
                        employee = Employee()
                
                # Update employee data
                employee.employee_id = employee_id
                employee.name = f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip()
                employee.email = email
                employee.crew = str(row.get('Crew', '')).strip()
                employee.phone = str(row.get('Phone', '')).strip() if pd.notna(row.get('Phone')) else None
                
                # Set position
                position_name = str(row.get('Position', '')).strip()
                if position_name:
                    position = Position.query.filter_by(name=position_name).first()
                    if position:
                        employee.position_id = position.id
                
                # Set hire date
                if pd.notna(row.get('Hire Date')):
                    employee.hire_date = pd.to_datetime(row['Hire Date']).date()
                
                # Set supervisor status
                is_supervisor = str(row.get('Is Supervisor', 'No')).strip().lower() == 'yes'
                employee.is_supervisor = is_supervisor
                
                # Set default password for new employees
                if not employee.id:
                    employee.set_password('Scheduler123!')
                
                db.session.add(employee)
                success_count += 1
                
            except Exception as e:
                error_count += 1
                errors.append(f"Row {index + 2}: {str(e)}")
        
        # Commit all changes
        db.session.commit()
        
        # Create upload record
        upload_record = FileUpload(
            filename=filename,
            file_type='employee_import',
            file_size=os.path.getsize(temp_path),
            uploaded_by_id=current_user.id,
            records_processed=success_count + error_count,
            records_success=success_count,
            records_failed=error_count,
            status='completed' if error_count == 0 else 'partial',
            error_details='\n'.join(errors) if errors else None
        )
        db.session.add(upload_record)
        db.session.commit()
        
        # Remove temp file
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                current_app.logger.info(f"Removed temp file: {temp_path}")
        except Exception as e:
            current_app.logger.warning(f"Could not remove temp file: {str(e)}")
        
        # Flash results
        if error_count == 0:
            flash(f'Successfully imported {success_count} employees!', 'success')
        else:
            flash(f'Imported {success_count} employees with {error_count} errors.', 'warning')
            if errors:
                for error in errors[:5]:  # Show first 5 errors
                    flash(error, 'error')
        
        return redirect(url_for('employee_import.upload_employees'))
        
    except Exception as e:
        current_app.logger.error(f"Error processing upload: {str(e)}")
        flash(f'Error processing file: {str(e)}', 'error')
        return redirect(url_for('employee_import.upload_employees'))

# Upload overtime route
@employee_import_bp.route('/upload-overtime')
@login_required
@supervisor_required
def upload_overtime():
    """Show overtime upload page"""
    try:
        # Get statistics
        total_employees = Employee.query.count()
        employees_with_ot = db.session.query(
            func.count(func.distinct(OvertimeHistory.employee_id))
        ).scalar() or 0
        
        # Get total OT hours
        total_ot_hours = db.session.query(
            func.sum(OvertimeHistory.hours)
        ).scalar() or 0
        
        # Calculate average weekly OT
        if employees_with_ot > 0:
            avg_weekly_ot = round(total_ot_hours / (employees_with_ot * 13), 1)
        else:
            avg_weekly_ot = 0
        
        # Count high OT employees (>20 hrs/week average)
        high_ot_count = 0
        employees = Employee.query.all()
        for emp in employees:
            if emp.average_weekly_overtime > 20:
                high_ot_count += 1
        
        # Get recent uploads
        recent_uploads = FileUpload.query.filter_by(
            file_type='overtime_import'
        ).order_by(FileUpload.upload_date.desc()).limit(5).all()
        
        return render_template('upload_overtime.html',
                             total_employees=total_employees,
                             employees_with_ot=employees_with_ot,
                             total_ot_hours=int(total_ot_hours),
                             avg_weekly_ot=avg_weekly_ot,
                             high_ot_count=high_ot_count,
                             recent_uploads=recent_uploads)
                             
    except Exception as e:
        current_app.logger.error(f"Error loading overtime upload page: {str(e)}")
        flash('Error loading page', 'error')
        return redirect(url_for('main.dashboard'))

# Process overtime upload
@employee_import_bp.route('/process-overtime-upload', methods=['POST'])
@login_required
@supervisor_required
def process_overtime_upload():
    """Process overtime history upload"""
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('employee_import.upload_overtime'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('employee_import.upload_overtime'))
    
    try:
        # Use a different folder name to avoid conflicts
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
        
        # Get the absolute path for the upload folder
        if not os.path.isabs(upload_folder):
            upload_folder = os.path.join(current_app.root_path, upload_folder)
        
        # Check if path exists and handle accordingly
        try:
            if os.path.exists(upload_folder):
                if os.path.isfile(upload_folder):
                    # If it's a file, use a different name
                    upload_folder = os.path.join(current_app.root_path, 'upload_files')
            
            # Create directory if it doesn't exist
            if not os.path.exists(upload_folder) or not os.path.isdir(upload_folder):
                os.makedirs(upload_folder, exist_ok=True)
                
        except Exception as e:
            # Use temp directory as fallback
            upload_folder = tempfile.gettempdir()
        
        # Save file
        filename = secure_filename(file.filename)
        temp_path = os.path.join(upload_folder, filename)
        file.save(temp_path)
        
        # Read Excel file
        df = pd.read_excel(temp_path, sheet_name='Overtime Data')
        
        # Get options
        replace_all = request.form.get('replace_all') == 'true'
        validate_only = request.form.get('validate_only') == 'on'
        
        if replace_all and not validate_only:
            # Delete existing overtime history
            try:
                OvertimeHistory.query.delete()
                db.session.commit()
                current_app.logger.info("Deleted all existing overtime history")
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error deleting overtime history: {str(e)}")
                flash('Error clearing existing overtime data.', 'error')
        
        # Process each row
        success_count = 0
        error_count = 0
        errors = []
        
        for index, row in df.iterrows():
            try:
                # Find employee
                employee_id = str(row.get('Employee ID', '')).strip()
                employee = Employee.query.filter_by(employee_id=employee_id).first()
                
                if not employee:
                    error_count += 1
                    errors.append(f"Row {index + 2}: Employee ID '{employee_id}' not found")
                    continue
                
                # Process each week
                for week_num in range(1, 14):
                    week_col = f'Week {week_num}'
                    if week_col in row:
                        hours = row[week_col]
                        if pd.notna(hours) and hours > 0:
                            # Calculate week ending date (13 weeks ago + week_num)
                            week_ending = date.today() - timedelta(weeks=(13 - week_num))
                            
                            if not validate_only:
                                # Check if record exists
                                ot_record = OvertimeHistory.query.filter_by(
                                    employee_id=employee.id,
                                    week_ending=week_ending
                                ).first()
                                
                                if not ot_record:
                                    ot_record = OvertimeHistory(
                                        employee_id=employee.id,
                                        week_ending=week_ending
                                    )
                                
                                ot_record.hours = float(hours)
                                db.session.add(ot_record)
                
                success_count += 1
                
            except Exception as e:
                error_count += 1
                errors.append(f"Row {index + 2}: {str(e)}")
        
        if not validate_only:
            # Commit changes
            db.session.commit()
            
            # Create upload record
            upload_record = FileUpload(
                filename=filename,
                file_type='overtime_import',
                file_size=os.path.getsize(temp_path),
                uploaded_by_id=current_user.id,
                records_processed=success_count + error_count,
                records_success=success_count,
                records_failed=error_count,
                status='completed' if error_count == 0 else 'partial',
                error_details='\n'.join(errors) if errors else None
            )
            db.session.add(upload_record)
            db.session.commit()
        
        # Remove temp file
        os.remove(temp_path)
        
        # Flash results
        if validate_only:
            if error_count == 0:
                flash(f'Validation successful! {success_count} records ready to import.', 'success')
            else:
                flash(f'Validation found {error_count} errors in {success_count + error_count} records.', 'warning')
        else:
            if error_count == 0:
                flash(f'Successfully imported overtime data for {success_count} employees!', 'success')
            else:
                flash(f'Imported {success_count} employees with {error_count} errors.', 'warning')
        
        # Show errors
        if errors:
            for error in errors[:5]:
                flash(error, 'error')
        
        return redirect(url_for('employee_import.upload_overtime'))
        
    except Exception as e:
        current_app.logger.error(f"Error processing overtime upload: {str(e)}")
        flash(f'Error processing file: {str(e)}', 'error')
        return redirect(url_for('employee_import.upload_overtime'))

# Upload history
@employee_import_bp.route('/upload-history')
@login_required
@supervisor_required
def upload_history():
    """View upload history"""
    try:
        # Get filter parameters
        upload_type = request.args.get('upload_type', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        
        # Build query
        query = FileUpload.query
        
        if upload_type:
            query = query.filter_by(file_type=upload_type)
        
        if start_date:
            query = query.filter(FileUpload.upload_date >= datetime.strptime(start_date, '%Y-%m-%d'))
        
        if end_date:
            query = query.filter(FileUpload.upload_date <= datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1))
        
        # Get uploads
        uploads = query.order_by(FileUpload.upload_date.desc()).all()
        
        # Calculate statistics
        total_uploads = len(uploads)
        successful_uploads = len([u for u in uploads if u.status == 'completed'])
        partial_uploads = len([u for u in uploads if u.status == 'partial'])
        failed_uploads = len([u for u in uploads if u.status == 'failed'])
        
        return render_template('upload_history.html',
                             uploads=uploads,
                             total_uploads=total_uploads,
                             successful_uploads=successful_uploads,
                             partial_uploads=partial_uploads,
                             failed_uploads=failed_uploads)
                             
    except Exception as e:
        current_app.logger.error(f"Error loading upload history: {str(e)}")
        flash('Error loading upload history', 'error')
        return redirect(url_for('main.dashboard'))

# Export current employees
@employee_import_bp.route('/export-current-employees')
@login_required
@supervisor_required
def export_current_employees():
    """Export current employee data"""
    try:
        employees = Employee.query.filter(
            Employee.email != 'admin@workforce.com'
        ).order_by(Employee.crew, Employee.name).all()
        
        data = []
        for emp in employees:
            data.append({
                'Employee ID': emp.employee_id or f'EMP{emp.id}',
                'First Name': emp.name.split(' ')[0] if emp.name else '',
                'Last Name': ' '.join(emp.name.split(' ')[1:]) if emp.name and ' ' in emp.name else '',
                'Email': emp.email,
                'Crew': emp.crew or '',
                'Position': emp.position.name if emp.position else '',
                'Department': '',
                'Hire Date': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '',
                'Phone': emp.phone or '',
                'Emergency Contact': '',
                'Skills': '',
                'Is Supervisor': 'Yes' if emp.is_supervisor else 'No'
            })
        
        df = pd.DataFrame(data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Employee Data', index=False)
        
        output.seek(0)
        
        filename = f'employee_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        flash(f'Error exporting data: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

# Export current overtime
@employee_import_bp.route('/export-current-overtime')
@login_required
@supervisor_required
def export_current_overtime():
    """Export current overtime data"""
    try:
        employees = Employee.query.filter(
            Employee.email != 'admin@workforce.com'
        ).order_by(Employee.crew, Employee.name).all()
        
        data = []
        for emp in employees:
            row = {
                'Employee ID': emp.employee_id or f'EMP{emp.id}',
                'Employee Name': emp.name,
                'Crew': emp.crew
            }
            
            # Get overtime for last 13 weeks
            for week_num in range(1, 14):
                week_ending = date.today() - timedelta(weeks=(13 - week_num))
                ot_record = OvertimeHistory.query.filter_by(
                    employee_id=emp.id,
                    week_ending=week_ending
                ).first()
                row[f'Week {week_num}'] = ot_record.hours if ot_record else 0
            
            data.append(row)
        
        df = pd.DataFrame(data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Overtime Data', index=False)
        
        output.seek(0)
        
        filename = f'overtime_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        flash(f'Error exporting data: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

# Delete upload record
@employee_import_bp.route('/delete-upload/<int:upload_id>', methods=['POST'])
@login_required
@supervisor_required
def delete_upload(upload_id):
    """Delete an upload record"""
    try:
        upload = FileUpload.query.get_or_404(upload_id)
        db.session.delete(upload)
        db.session.commit()
        flash('Upload record deleted successfully', 'success')
    except Exception as e:
        flash(f'Error deleting record: {str(e)}', 'error')
    
    return redirect(url_for('employee_import.upload_history'))

# API endpoints for AJAX operations
@employee_import_bp.route('/api/validate-employee-data', methods=['POST'])
@login_required
@supervisor_required
def validate_employee_data():
    """Validate employee data without importing"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        file = request.files['file']
        df = pd.read_excel(file, sheet_name='Employee Data')
        
        errors = []
        warnings = []
        
        # Validate required fields
        required_fields = ['Employee ID', 'First Name', 'Last Name', 'Email', 'Crew']
        for field in required_fields:
            if field not in df.columns:
                errors.append(f"Missing required column: {field}")
        
        if errors:
            return jsonify({
                'success': False,
                'errors': errors,
                'row_count': 0
            })
        
        # Validate each row
        valid_crews = ['A', 'B', 'C', 'D']
        valid_positions = [p.name for p in Position.query.all()]
        
        for index, row in df.iterrows():
            row_num = index + 2
            
            # Check required fields
            if pd.isna(row['Employee ID']) or str(row['Employee ID']).strip() == '':
                errors.append(f"Row {row_num}: Missing Employee ID")
            
            if pd.isna(row['Email']) or not validate_email(str(row['Email'])):
                errors.append(f"Row {row_num}: Invalid email address")
            
            # Check crew
            crew = str(row.get('Crew', '')).strip().upper()
            if crew not in valid_crews:
                errors.append(f"Row {row_num}: Invalid crew '{crew}' (must be A, B, C, or D)")
            
            # Check position
            position = str(row.get('Position', '')).strip()
            if position and position not in valid_positions:
                warnings.append(f"Row {row_num}: Unknown position '{position}'")
        
        return jsonify({
            'success': len(errors) == 0,
            'errors': errors[:10],  # Limit to first 10 errors
            'warnings': warnings[:10],
            'row_count': len(df),
            'total_errors': len(errors),
            'total_warnings': len(warnings)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@employee_import_bp.route('/api/upload-stats')
@login_required
@supervisor_required
def upload_stats():
    """Get upload statistics"""
    try:
        stats = {
            'total_uploads': FileUpload.query.count(),
            'successful_uploads': FileUpload.query.filter_by(status='completed').count(),
            'employees_imported': Employee.query.filter(Employee.email != 'admin@workforce.com').count(),
            'last_upload': None
        }
        
        last_upload = FileUpload.query.order_by(FileUpload.upload_date.desc()).first()
        if last_upload:
            stats['last_upload'] = {
                'date': last_upload.upload_date.strftime('%Y-%m-%d %H:%M'),
                'type': last_upload.file_type,
                'records': last_upload.records_processed
            }
        
        return jsonify(stats)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
