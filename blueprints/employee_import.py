# blueprints/employee_import.py
"""
Employee Import Blueprint - Complete and Validated
This file handles all employee and overtime data imports/exports
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify, current_app
from flask_login import login_required, current_user
from functools import wraps
from models import db, Employee, Position, Skill, OvertimeHistory, FileUpload, EmployeeSkill
from datetime import datetime, date, timedelta
from werkzeug.utils import secure_filename
from sqlalchemy import func
import pandas as pd
import io
import os
import tempfile
import traceback

# Create blueprint
employee_import_bp = Blueprint('employee_import', __name__)

# Decorator for supervisor access
def supervisor_required(f):
    """Decorator to ensure user is a supervisor"""
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

# Helper function to validate email
def validate_email(email):
    """Basic email validation"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, str(email)))

# Helper function to ensure upload directory exists
def ensure_upload_directory():
    """Ensure upload directory exists and return path"""
    try:
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
        
        if not os.path.isabs(upload_folder):
            upload_folder = os.path.join(current_app.root_path, upload_folder)
        
        if os.path.exists(upload_folder) and os.path.isfile(upload_folder):
            upload_folder = os.path.join(current_app.root_path, 'temp_uploads')
        
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder, exist_ok=True)
            
        return upload_folder
    except Exception as e:
        current_app.logger.warning(f"Could not create upload folder: {e}")
        return tempfile.gettempdir()

# ===== TEMPLATE DOWNLOAD ROUTES =====

@employee_import_bp.route('/download-employee-template')
@login_required
@supervisor_required
def download_employee_template():
    """Download employee import template"""
    try:
        # Create sample data
        template_data = {
            'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
            'First Name': ['John', 'Jane', 'Bob'],
            'Last Name': ['Smith', 'Doe', 'Johnson'],
            'Email': ['john.smith@company.com', 'jane.doe@company.com', 'bob.johnson@company.com'],
            'Crew': ['A', 'B', 'C'],
            'Position': ['Operator', 'Supervisor', 'Technician'],
            'Department': ['Production', 'Production', 'Maintenance'],
            'Hire Date': ['2023-01-15', '2022-06-20', '2023-03-10'],
            'Phone': ['555-0101', '555-0102', '555-0103'],
            'Emergency Contact': ['Mary Smith', 'John Doe', 'Alice Johnson'],
            'Emergency Phone': ['555-9101', '555-9102', '555-9103'],
            'Skills': ['Forklift,Safety', 'Leadership,Training', 'Electrical,Welding'],
            'Is Supervisor': ['No', 'Yes', 'No']
        }
        
        df = pd.DataFrame(template_data)
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Employee Data', index=False)
            
            # Add instructions
            instructions = pd.DataFrame({
                'Instructions': [
                    'Employee Import Template Instructions',
                    '',
                    '1. Fill in all required fields',
                    '2. Crew must be A, B, C, or D',
                    '3. Email must be unique',
                    '4. Date format: YYYY-MM-DD',
                    '5. Skills: comma-separated',
                    '6. Delete example rows before importing'
                ]
            })
            instructions.to_excel(writer, sheet_name='Instructions', index=False, header=False)
        
        output.seek(0)
        filename = f'employee_template_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        current_app.logger.error(f"Error generating template: {str(e)}")
        flash('Error generating template', 'error')
        return redirect(url_for('main.dashboard'))

@employee_import_bp.route('/download-overtime-template')
@login_required
@supervisor_required
def download_overtime_template():
    """Download overtime history template"""
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
            for week in range(1, 14):
                row[f'Week {week}'] = 0
            data.append(row)
        
        df = pd.DataFrame(data)
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Overtime Data', index=False)
            
            instructions = pd.DataFrame({
                'Instructions': [
                    'Overtime History Import Template',
                    '',
                    '1. Do not modify Employee ID, Name, or Crew',
                    '2. Enter hours for each week (0-168)',
                    '3. Week 1 = oldest, Week 13 = most recent',
                    '4. Decimal hours allowed (e.g., 8.5)'
                ]
            })
            instructions.to_excel(writer, sheet_name='Instructions', index=False, header=False)
        
        output.seek(0)
        filename = f'overtime_template_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        current_app.logger.error(f"Error generating template: {str(e)}")
        flash('Error generating template', 'error')
        return redirect(url_for('main.dashboard'))

# ===== UPLOAD PAGES =====

@employee_import_bp.route('/upload-employees', methods=['GET', 'POST'])
@login_required
@supervisor_required
def upload_employees():
    """Employee upload page and processing"""
    if request.method == 'GET':
        try:
            # Get statistics for display
            employee_count = Employee.query.filter(Employee.id != current_user.id).count()
            
            recent_uploads = FileUpload.query.filter_by(
                file_type='employee_import'
            ).order_by(FileUpload.upload_date.desc()).limit(5).all()
            
            crew_stats = db.session.query(
                Employee.crew,
                func.count(Employee.id)
            ).filter(
                Employee.id != current_user.id
            ).group_by(Employee.crew).all()
            
            crew_distribution = {crew: count for crew, count in crew_stats if crew}
            
            return render_template('upload_employees_enhanced.html',
                                 employee_count=employee_count,
                                 recent_uploads=recent_uploads,
                                 crew_distribution=crew_distribution)
        except Exception as e:
            current_app.logger.error(f"Error loading upload page: {str(e)}")
            flash('Error loading page', 'error')
            return redirect(url_for('main.dashboard'))
    
    # POST - Process file upload
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(request.url)
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        flash('Please upload an Excel file', 'error')
        return redirect(request.url)
    
    try:
        # Save uploaded file
        upload_folder = ensure_upload_directory()
        filename = secure_filename(file.filename)
        temp_path = os.path.join(upload_folder, filename)
        file.save(temp_path)
        
        # Read Excel file
        df = pd.read_excel(temp_path, sheet_name='Employee Data')
        
        # Get options
        replace_all = request.form.get('replace_all') == 'on'
        
        if replace_all:
            # Delete existing non-admin employees
            try:
                employees_to_delete = Employee.query.filter(
                    Employee.email != 'admin@workforce.com'
                ).all()
                
                for emp in employees_to_delete:
                    db.session.delete(emp)
                
                db.session.commit()
                current_app.logger.info(f"Deleted {len(employees_to_delete)} employees")
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error deleting employees: {str(e)}")
                flash('Error clearing existing data', 'error')
                return redirect(request.url)
        
        # Process each row
        success_count = 0
        error_count = 0
        errors = []
        
        for index, row in df.iterrows():
            try:
                # Validate required fields
                employee_id = str(row.get('Employee ID', '')).strip()
                email = str(row.get('Email', '')).strip()
                
                if not email or not validate_email(email):
                    error_count += 1
                    errors.append(f"Row {index + 2}: Invalid email")
                    continue
                
                # Check if employee exists
                employee = None
                if not replace_all:
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
                employee.crew = str(row.get('Crew', '')).strip().upper()
                employee.phone = str(row.get('Phone', '')).strip() if pd.notna(row.get('Phone')) else None
                
                # Set position
                position_name = str(row.get('Position', '')).strip()
                if position_name:
                    position = Position.query.filter_by(name=position_name).first()
                    if not position:
                        position = Position(name=position_name)
                        db.session.add(position)
                    employee.position = position
                
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
            records_failed=error_count,
            status='completed' if error_count == 0 else 'partial',
            error_details='\n'.join(errors) if errors else None
        )
        db.session.add(upload_record)
        db.session.commit()
        
        # Clean up
        try:
            os.remove(temp_path)
        except:
            pass
        
        # Flash results
        if error_count == 0:
            flash(f'Successfully imported {success_count} employees!', 'success')
        else:
            flash(f'Imported {success_count} employees with {error_count} errors.', 'warning')
            for error in errors[:5]:
                flash(error, 'error')
        
        return redirect(url_for('employee_import.upload_employees'))
        
    except Exception as e:
        current_app.logger.error(f"Error processing upload: {str(e)}")
        flash(f'Error processing file: {str(e)}', 'error')
        return redirect(url_for('employee_import.upload_employees'))

@employee_import_bp.route('/upload-overtime')
@login_required
@supervisor_required
def upload_overtime():
    """Overtime upload page"""
    try:
        # Get statistics
        total_employees = Employee.query.count()
        employees_with_ot = db.session.query(
            func.count(func.distinct(OvertimeHistory.employee_id))
        ).scalar() or 0
        
        # Fixed: OvertimeHistory doesn't have 'hours' column, it has 'overtime_hours'
        total_ot_hours = db.session.query(
            func.sum(OvertimeHistory.overtime_hours)
        ).scalar() or 0
        
        avg_weekly_ot = round(total_ot_hours / (employees_with_ot * 13), 1) if employees_with_ot > 0 else 0
        
        high_ot_count = 0
        employees = Employee.query.all()
        for emp in employees:
            if hasattr(emp, 'average_weekly_overtime') and emp.average_weekly_overtime > 20:
                high_ot_count += 1
        
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
        current_app.logger.error(f"Error loading overtime page: {str(e)}")
        flash('Error loading page', 'error')
        return redirect(url_for('main.dashboard'))

@employee_import_bp.route('/process-overtime-upload', methods=['POST'])
@login_required
@supervisor_required
def process_overtime_upload():
    """Process overtime file upload"""
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('employee_import.upload_overtime'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('employee_import.upload_overtime'))
    
    try:
        # Save file
        upload_folder = ensure_upload_directory()
        filename = secure_filename(file.filename)
        temp_path = os.path.join(upload_folder, filename)
        file.save(temp_path)
        
        # Read Excel file
        df = pd.read_excel(temp_path, sheet_name='Overtime Data')
        
        # Get options
        replace_all = request.form.get('replace_all') == 'true'
        validate_only = request.form.get('validate_only') == 'on'
        
        if replace_all and not validate_only:
            OvertimeHistory.query.delete()
            db.session.commit()
        
        # Process each row
        success_count = 0
        error_count = 0
        errors = []
        
        for index, row in df.iterrows():
            try:
                employee_id = str(row.get('Employee ID', '')).strip()
                employee = Employee.query.filter_by(employee_id=employee_id).first()
                
                if not employee:
                    error_count += 1
                    errors.append(f"Row {index + 2}: Employee ID '{employee_id}' not found")
                    continue
                
                # Process weeks
                for week_num in range(1, 14):
                    week_col = f'Week {week_num}'
                    if week_col in row and pd.notna(row[week_col]):
                        hours = float(row[week_col])
                        if hours > 0:
                            # Calculate week start date (13 weeks ago + week_num)
                            week_start = date.today() - timedelta(weeks=(14 - week_num))
                            # Adjust to start of week (Monday)
                            week_start = week_start - timedelta(days=week_start.weekday())
                            
                            if not validate_only:
                                ot_record = OvertimeHistory.query.filter_by(
                                    employee_id=employee.id,
                                    week_start_date=week_start
                                ).first()
                                
                                if not ot_record:
                                    ot_record = OvertimeHistory(
                                        employee_id=employee.id,
                                        week_start_date=week_start,
                                        regular_hours=40,  # Default
                                        overtime_hours=hours,
                                        total_hours=40 + hours
                                    )
                                else:
                                    ot_record.overtime_hours = hours
                                    ot_record.total_hours = ot_record.regular_hours + hours
                                
                                db.session.add(ot_record)
                
                success_count += 1
                
            except Exception as e:
                error_count += 1
                errors.append(f"Row {index + 2}: {str(e)}")
        
        if not validate_only:
            db.session.commit()
            
            # Create upload record
            upload_record = FileUpload(
                filename=filename,
                file_type='overtime_import',
                file_size=os.path.getsize(temp_path),
                uploaded_by_id=current_user.id,
                records_processed=success_count + error_count,
                records_failed=error_count,
                status='completed' if error_count == 0 else 'partial',
                error_details='\n'.join(errors) if errors else None
            )
            db.session.add(upload_record)
            db.session.commit()
        
        # Clean up
        try:
            os.remove(temp_path)
        except:
            pass
        
        # Flash results
        if validate_only:
            if error_count == 0:
                flash(f'Validation successful! {success_count} records ready to import.', 'success')
            else:
                flash(f'Validation found {error_count} errors.', 'warning')
        else:
            if error_count == 0:
                flash(f'Successfully imported overtime for {success_count} employees!', 'success')
            else:
                flash(f'Imported {success_count} employees with {error_count} errors.', 'warning')
        
        if errors:
            for error in errors[:5]:
                flash(error, 'error')
        
        return redirect(url_for('employee_import.upload_overtime'))
        
    except Exception as e:
        current_app.logger.error(f"Error processing overtime: {str(e)}")
        flash(f'Error processing file: {str(e)}', 'error')
        return redirect(url_for('employee_import.upload_overtime'))

# ===== HISTORY AND EXPORT ROUTES =====

@employee_import_bp.route('/upload-history')
@login_required
@supervisor_required
def upload_history():
    """View upload history"""
    try:
        uploads = FileUpload.query.order_by(FileUpload.upload_date.desc()).all()
        
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
        current_app.logger.error(f"Error loading history: {str(e)}")
        flash('Error loading history', 'error')
        return redirect(url_for('main.dashboard'))

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
            
            for week_num in range(1, 14):
                week_start = date.today() - timedelta(weeks=(14 - week_num))
                week_start = week_start - timedelta(days=week_start.weekday())
                ot_record = OvertimeHistory.query.filter_by(
                    employee_id=emp.id,
                    week_start_date=week_start
                ).first()
                row[f'Week {week_num}'] = ot_record.overtime_hours if ot_record else 0
            
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

# ===== BULK UPDATE TEMPLATE =====

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
                    'Action': 'UPDATE'
                })
            
            df = pd.DataFrame(data)
            sheet_name = 'Employee Updates'
        else:
            employees = Employee.query.all()
            
            data = []
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
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        output.seek(0)
        filename = f'{template_type}_bulk_update_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        current_app.logger.error(f"Error generating bulk template: {str(e)}")
        flash('Error generating template', 'error')
        return redirect(url_for('main.dashboard'))

# ===== VALIDATION ROUTES =====

# This is the main validation route that the frontend is looking for
@employee_import_bp.route('/validate-upload', methods=['POST'])
@login_required
@supervisor_required
def validate_upload():
    """Generic validation endpoint that routes to specific validators based on upload type"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        file = request.files['file']
        upload_type = request.form.get('type', 'employee')  # Note: 'type' not 'upload_type'
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        # Route to appropriate validator based on type
        if upload_type == 'employee':
            return validate_employee_data()
        elif upload_type == 'overtime':
            return validate_overtime_data()
        elif upload_type == 'bulk_update':
            return validate_bulk_update()
        else:
            return jsonify({'success': False, 'error': f'Unknown upload type: {upload_type}'})
            
    except Exception as e:
        current_app.logger.error(f"Validation error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Validation failed: {str(e)}'
        })

# Employee data validation
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
            
            if pd.isna(row['First Name']) or str(row['First Name']).strip() == '':
                errors.append(f"Row {row_num}: Missing First Name")
                
            if pd.isna(row['Last Name']) or str(row['Last Name']).strip() == '':
                errors.append(f"Row {row_num}: Missing Last Name")
            
            if pd.isna(row['Email']) or not validate_email(str(row['Email'])):
                errors.append(f"Row {row_num}: Invalid email format")
            
            crew = str(row.get('Crew', '')).strip().upper()
            if crew not in valid_crews:
                errors.append(f"Row {row_num}: Invalid crew '{crew}' (must be A, B, C, or D)")
                
            # Check for duplicate emails
            email = str(row['Email']).strip().lower()
            existing = Employee.query.filter_by(email=email).first()
            if existing:
                warnings.append(f"Row {row_num}: Email '{email}' already exists (will update)")
        
        return jsonify({
            'success': len(errors) == 0,
            'errors': errors[:10],  # Limit to first 10 errors
            'warnings': warnings[:10],
            'row_count': len(df),
            'error_count': len(errors),
            'warning_count': len(warnings),
            'preview_data': df.head(5).to_dict('records') if len(errors) == 0 else None
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error reading file: {str(e)}'
        })

# Overtime data validation
@employee_import_bp.route('/api/validate-overtime-data', methods=['POST'])
@login_required
@supervisor_required
def validate_overtime_data():
    """Validate overtime data without importing"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        file = request.files['file']
        df = pd.read_excel(file, sheet_name='Overtime Data')
        
        errors = []
        warnings = []
        
        # Check required columns
        required_columns = ['Employee ID']
        week_columns = [f'Week {i}' for i in range(1, 14)]
        
        for col in required_columns + week_columns:
            if col not in df.columns:
                errors.append(f"Missing required column: {col}")
        
        if errors:
            return jsonify({
                'success': False,
                'errors': errors,
                'row_count': 0
            })
        
        # Validate each row
        valid_rows = 0
        for index, row in df.iterrows():
            row_num = index + 2
            
            # Check Employee ID exists
            emp_id = str(row['Employee ID']).strip()
            employee = Employee.query.filter_by(employee_id=emp_id).first()
            
            if not employee:
                errors.append(f"Row {row_num}: Employee ID '{emp_id}' not found")
                continue
            
            # Validate week data
            for week_num in range(1, 14):
                week_col = f'Week {week_num}'
                hours = row.get(week_col, 0)
                
                try:
                    hours_float = float(hours) if pd.notna(hours) else 0
                    if hours_float < 0:
                        warnings.append(f"Row {row_num}, {week_col}: Negative hours ({hours_float})")
                    elif hours_float > 168:  # More than hours in a week
                        errors.append(f"Row {row_num}, {week_col}: Invalid hours ({hours_float} > 168)")
                except:
                    errors.append(f"Row {row_num}, {week_col}: Invalid number format")
            
            if len([e for e in errors if f"Row {row_num}" in e]) == 0:
                valid_rows += 1
        
        return jsonify({
            'success': len(errors) == 0,
            'errors': errors[:10],  # Limit to first 10 errors
            'warnings': warnings[:10],
            'row_count': len(df),
            'valid_rows': valid_rows,
            'error_count': len(errors),
            'warning_count': len(warnings),
            'preview_data': df.head(5).to_dict('records') if len(errors) == 0 else None
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error reading file: {str(e)}'
        })

# Bulk update validation
@employee_import_bp.route('/api/validate-bulk-update', methods=['POST'])
@login_required  
@supervisor_required
def validate_bulk_update():
    """Validate bulk update data"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        file = request.files['file']
        df = pd.read_excel(file, sheet_name=0)  # First sheet
        
        errors = []
        warnings = []
        updates_preview = []
        
        # Must have Employee ID
        if 'Employee ID' not in df.columns:
            return jsonify({
                'success': False,
                'error': 'Missing required column: Employee ID'
            })
        
        # Determine which fields are being updated
        update_fields = [col for col in df.columns if col != 'Employee ID']
        
        if not update_fields:
            return jsonify({
                'success': False,
                'error': 'No fields to update. File must contain at least one field besides Employee ID'
            })
        
        # Validate each row
        for index, row in df.iterrows():
            row_num = index + 2
            emp_id = str(row['Employee ID']).strip()
            
            employee = Employee.query.filter_by(employee_id=emp_id).first()
            if not employee:
                errors.append(f"Row {row_num}: Employee ID '{emp_id}' not found")
                continue
            
            update_preview = {'employee_id': emp_id, 'updates': {}}
            
            # Validate each field
            for field in update_fields:
                value = row.get(field)
                if pd.isna(value):
                    continue
                    
                if field == 'Crew' and value not in ['A', 'B', 'C', 'D']:
                    errors.append(f"Row {row_num}: Invalid crew '{value}'")
                elif field == 'Email':
                    if not validate_email(str(value)):
                        errors.append(f"Row {row_num}: Invalid email format '{value}'")
                elif field == 'Position':
                    if not Position.query.filter_by(name=str(value)).first():
                        warnings.append(f"Row {row_num}: Position '{value}' will be created")
                
                update_preview['updates'][field] = value
            
            if update_preview['updates']:
                updates_preview.append(update_preview)
        
        return jsonify({
            'success': len(errors) == 0,
            'errors': errors[:10],
            'warnings': warnings[:10],
            'row_count': len(df),
            'update_count': len(updates_preview),
            'fields_to_update': update_fields,
            'preview': updates_preview[:5]
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error processing file: {str(e)}'
        })

# ===== API ENDPOINTS =====

@employee_import_bp.route('/api/validate-upload', methods=['POST'])
@login_required
@supervisor_required
def api_validate_upload():
    """API endpoint for validation - redirects to main validation"""
    return validate_upload()

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

# ===== DELETE UPLOAD RECORD =====

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
