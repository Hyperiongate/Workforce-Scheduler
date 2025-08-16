# blueprints/employee_import.py
"""
Employee Import Blueprint - Complete file with all routes and template variables
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db, Employee, Position, Skill, OvertimeHistory, FileUpload, TimeOffRequest, ShiftSwapRequest
from datetime import datetime, date, timedelta
from sqlalchemy import func, or_, and_
import pandas as pd
import os
import io
import re
import random
import string
import logging

# Import the decorator from utils
from utils.decorators import supervisor_required

# Set up logging
logger = logging.getLogger(__name__)

# Create blueprint
employee_import_bp = Blueprint('employee_import', __name__)

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def get_employee_stats():
    """Get statistics for employee data"""
    try:
        total_employees = Employee.query.filter_by(is_supervisor=False).count()
        
        # Get employees without overtime data
        employees_without_ot = Employee.query.filter(
            Employee.is_supervisor == False,
            ~Employee.overtime_history.any()
        ).count()
        
        # Get crew distribution
        crew_counts = db.session.query(
            Employee.crew, 
            func.count(Employee.id)
        ).filter(
            Employee.is_supervisor == False
        ).group_by(Employee.crew).all()
        
        crews = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'Unassigned': 0}
        for crew, count in crew_counts:
            if crew in ['A', 'B', 'C', 'D']:
                crews[crew] = count
            else:
                crews['Unassigned'] += count
        
        return {
            'total_employees': total_employees,
            'employees_without_ot': employees_without_ot,
            'crews': crews
        }
    except Exception as e:
        logger.error(f"Error getting employee stats: {e}")
        return {
            'total_employees': 0,
            'employees_without_ot': 0,
            'crews': {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'Unassigned': 0}
        }

def get_recent_uploads(limit=5):
    """Get recent file uploads"""
    try:
        return FileUpload.query.order_by(
            FileUpload.uploaded_at.desc()
        ).limit(limit).all()
    except Exception as e:
        logger.error(f"Error getting recent uploads: {e}")
        return []

def get_employees_without_accounts():
    """Count employees without login accounts"""
    try:
        return Employee.query.filter(
            Employee.is_supervisor == False,
            or_(Employee.password_hash == None, Employee.password_hash == '')
        ).count()
    except Exception:
        return 0

# ==========================================
# MAIN UPLOAD ROUTES
# ==========================================

@employee_import_bp.route('/upload-employees')
@login_required
@supervisor_required
def upload_employees():
    """Upload employees page with all required template variables"""
    stats = get_employee_stats()
    recent_uploads = get_recent_uploads()
    
    # Get crew distribution for chart
    crew_distribution = stats['crews']
    
    # Get total employees
    total_employees = stats['total_employees']
    
    # Get employees without accounts
    employees_without_accounts = get_employees_without_accounts()
    
    # Check if account creation is available
    account_creation_available = True  # Set based on your business logic
    
    return render_template('upload_employees_enhanced.html',
                         recent_uploads=recent_uploads,
                         stats=stats,
                         crew_distribution=crew_distribution,
                         total_employees=total_employees,
                         employees_without_accounts=employees_without_accounts,
                         account_creation_available=account_creation_available)

@employee_import_bp.route('/upload-overtime')
@login_required
@supervisor_required
def upload_overtime():
    """Upload overtime history page"""
    # Get overtime statistics
    try:
        total_ot_hours = db.session.query(
            func.sum(OvertimeHistory.hours_worked)
        ).scalar() or 0
        
        employees_with_ot = db.session.query(
            func.count(func.distinct(OvertimeHistory.employee_id))
        ).scalar() or 0
        
        recent_uploads = FileUpload.query.filter_by(
            upload_type='overtime'
        ).order_by(FileUpload.uploaded_at.desc()).limit(5).all()
        
    except Exception as e:
        logger.error(f"Error getting overtime stats: {e}")
        total_ot_hours = 0
        employees_with_ot = 0
        recent_uploads = []
    
    return render_template('upload_overtime.html',
                         total_ot_hours=total_ot_hours,
                         employees_with_ot=employees_with_ot,
                         recent_uploads=recent_uploads)

@employee_import_bp.route('/upload-history')
@login_required
@supervisor_required
def upload_history():
    """View upload history"""
    try:
        # Get all uploads, not paginated
        uploads = FileUpload.query.order_by(
            FileUpload.uploaded_at.desc()
        ).limit(100).all()
    except Exception as e:
        logger.error(f"Error getting upload history: {e}")
        uploads = []
    
    return render_template('upload_history.html', uploads=uploads)

# ==========================================
# VALIDATION AND PROCESSING ROUTES
# ==========================================

@employee_import_bp.route('/validate-upload', methods=['POST'])
@login_required
@supervisor_required
def validate_upload():
    """Validate uploaded Excel file"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'success': False, 'error': 'Invalid file type. Please upload Excel files only.'})
    
    upload_type = request.form.get('uploadType', 'employee')
    
    try:
        # Read the Excel file
        df = pd.read_excel(file)
        
        # Validate based on upload type
        if upload_type == 'employee':
            result = validate_employee_data(df)
        elif upload_type == 'overtime':
            result = validate_overtime_data(df)
        elif upload_type == 'bulk':
            result = validate_bulk_update(df)
        else:
            result = {'success': False, 'error': 'Invalid upload type'}
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Validation error: {str(e)}")
        return jsonify({'success': False, 'error': f'Error reading file: {str(e)}'})

@employee_import_bp.route('/process-upload', methods=['POST'])
@login_required
@supervisor_required
def process_upload():
    """Process the uploaded file"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'})
    
    file = request.files['file']
    upload_type = request.form.get('uploadType', 'employee')
    mode = request.form.get('mode', 'append')
    
    try:
        # Save file info to database
        file_upload = FileUpload(
            filename=secure_filename(file.filename),
            upload_type=upload_type,
            uploaded_by_id=current_user.id,
            uploaded_at=datetime.utcnow(),
            status='processing'
        )
        db.session.add(file_upload)
        db.session.commit()
        
        # Read and process file
        df = pd.read_excel(file)
        
        # Process based on type
        if upload_type == 'employee':
            result = process_employee_data(df, mode)
        elif upload_type == 'overtime':
            result = process_overtime_data(df, mode)
        elif upload_type == 'bulk':
            result = process_bulk_update(df)
        else:
            result = {'success': False, 'error': 'Invalid upload type'}
        
        # Update file upload record
        file_upload.status = 'completed' if result.get('success') else 'failed'
        file_upload.total_records = result.get('total', 0)
        file_upload.successful_records = result.get('successful', 0)
        file_upload.failed_records = result.get('failed', 0)
        file_upload.error_details = result.get('error', '') if not result.get('success') else None
        
        db.session.commit()
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Process error: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

# ==========================================
# VALIDATION FUNCTIONS
# ==========================================

def validate_employee_data(df):
    """Validate employee data"""
    errors = []
    warnings = []
    
    # Check required columns
    required_columns = ['Employee ID', 'First Name', 'Last Name', 'Email', 'Crew']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        return {
            'success': False,
            'error': f'Missing required columns: {", ".join(missing_columns)}'
        }
    
    # Validate each row
    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel row number (header is row 1)
        
        # Check required fields
        if pd.isna(row['Employee ID']) or str(row['Employee ID']).strip() == '':
            errors.append(f"Row {row_num}: Missing Employee ID")
        
        if pd.isna(row['Email']) or str(row['Email']).strip() == '':
            errors.append(f"Row {row_num}: Missing Email")
        elif not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', str(row['Email'])):
            errors.append(f"Row {row_num}: Invalid email format")
        
        # Check crew values
        if pd.notna(row['Crew']) and str(row['Crew']).upper() not in ['A', 'B', 'C', 'D']:
            warnings.append(f"Row {row_num}: Invalid crew '{row['Crew']}' (should be A, B, C, or D)")
    
    # Check for duplicates
    duplicates = df[df.duplicated(subset=['Employee ID'], keep=False)]
    if not duplicates.empty:
        for emp_id in duplicates['Employee ID'].unique():
            errors.append(f"Duplicate Employee ID: {emp_id}")
    
    if errors:
        return {
            'success': False,
            'errors': errors[:10],  # First 10 errors
            'error_count': len(errors),
            'warnings': warnings[:5]
        }
    
    return {
        'success': True,
        'total_rows': len(df),
        'valid_rows': len(df.dropna(subset=['Employee ID', 'Email'])),
        'warnings': warnings
    }

def validate_overtime_data(df):
    """Validate overtime data"""
    errors = []
    
    # Check for employee ID column
    if 'Employee ID' not in df.columns:
        return {
            'success': False,
            'error': 'Missing Employee ID column'
        }
    
    # Check for week columns (should have 13 weeks)
    week_columns = [col for col in df.columns if col.startswith('Week')]
    if len(week_columns) < 13:
        errors.append(f"Expected 13 week columns, found {len(week_columns)}")
    
    # Validate data
    for idx, row in df.iterrows():
        row_num = idx + 2
        
        if pd.isna(row['Employee ID']):
            errors.append(f"Row {row_num}: Missing Employee ID")
        
        # Check that overtime hours are numeric
        for week in week_columns:
            if pd.notna(row[week]) and not isinstance(row[week], (int, float)):
                errors.append(f"Row {row_num}, {week}: Invalid hours value")
    
    if errors:
        return {
            'success': False,
            'errors': errors[:10],
            'error_count': len(errors)
        }
    
    return {
        'success': True,
        'total_rows': len(df),
        'employee_count': df['Employee ID'].nunique()
    }

def validate_bulk_update(df):
    """Validate bulk update data"""
    errors = []
    
    if 'Employee ID' not in df.columns:
        return {
            'success': False,
            'error': 'Missing Employee ID column'
        }
    
    # Check what fields are being updated
    update_fields = [col for col in df.columns if col != 'Employee ID']
    
    if not update_fields:
        return {
            'success': False,
            'error': 'No fields to update found'
        }
    
    # Validate each row
    for idx, row in df.iterrows():
        row_num = idx + 2
        
        if pd.isna(row['Employee ID']):
            errors.append(f"Row {row_num}: Missing Employee ID")
    
    if errors:
        return {
            'success': False,
            'errors': errors[:10],
            'error_count': len(errors)
        }
    
    return {
        'success': True,
        'total_rows': len(df),
        'update_fields': update_fields
    }

# ==========================================
# PROCESSING FUNCTIONS
# ==========================================

def process_employee_data(df, mode='append'):
    """Process employee data"""
    try:
        successful = 0
        failed = 0
        errors = []
        
        # If replace mode, delete existing employees first
        if mode == 'replace':
            # Delete all non-supervisor employees
            Employee.query.filter_by(is_supervisor=False).delete()
            db.session.commit()
        
        # Process each row
        for idx, row in df.iterrows():
            try:
                # Check if employee exists
                employee = Employee.query.filter_by(
                    employee_id=str(row['Employee ID'])
                ).first()
                
                if employee and mode == 'append':
                    # Update existing employee
                    employee.name = f"{row['First Name']} {row['Last Name']}"
                    employee.email = str(row['Email'])
                    employee.crew = str(row['Crew']).upper() if pd.notna(row['Crew']) else None
                else:
                    # Create new employee
                    employee = Employee(
                        employee_id=str(row['Employee ID']),
                        name=f"{row['First Name']} {row['Last Name']}",
                        email=str(row['Email']),
                        crew=str(row['Crew']).upper() if pd.notna(row['Crew']) else None,
                        is_supervisor=False,
                        vacation_days=10,
                        sick_days=5,
                        personal_days=3
                    )
                    db.session.add(employee)
                
                successful += 1
                
            except Exception as e:
                failed += 1
                errors.append(f"Row {idx + 2}: {str(e)}")
        
        db.session.commit()
        
        return {
            'success': True,
            'total': len(df),
            'successful': successful,
            'failed': failed,
            'errors': errors[:5] if errors else None,
            'message': f'Successfully processed {successful} employees'
        }
        
    except Exception as e:
        db.session.rollback()
        return {
            'success': False,
            'error': str(e)
        }

def process_overtime_data(df, mode='replace'):
    """Process overtime data"""
    try:
        successful = 0
        failed = 0
        errors = []
        
        # Get week columns
        week_columns = [col for col in df.columns if col.startswith('Week')]
        
        for idx, row in df.iterrows():
            try:
                # Find employee
                employee = Employee.query.filter_by(
                    employee_id=str(row['Employee ID'])
                ).first()
                
                if not employee:
                    errors.append(f"Employee ID {row['Employee ID']} not found")
                    failed += 1
                    continue
                
                # Delete existing overtime if replace mode
                if mode == 'replace':
                    OvertimeHistory.query.filter_by(
                        employee_id=employee.id
                    ).delete()
                
                # Add overtime records
                for i, week_col in enumerate(week_columns):
                    if pd.notna(row[week_col]) and float(row[week_col]) > 0:
                        # Calculate week start date (13 weeks ago from today)
                        weeks_ago = 13 - i
                        week_start = datetime.now().date() - timedelta(weeks=weeks_ago)
                        week_start = week_start - timedelta(days=week_start.weekday())
                        
                        ot_record = OvertimeHistory(
                            employee_id=employee.id,
                            week_start_date=week_start,
                            hours_worked=float(row[week_col])
                        )
                        db.session.add(ot_record)
                
                successful += 1
                
            except Exception as e:
                failed += 1
                errors.append(f"Row {idx + 2}: {str(e)}")
        
        db.session.commit()
        
        return {
            'success': True,
            'total': len(df),
            'successful': successful,
            'failed': failed,
            'errors': errors[:5] if errors else None,
            'message': f'Successfully processed overtime for {successful} employees'
        }
        
    except Exception as e:
        db.session.rollback()
        return {
            'success': False,
            'error': str(e)
        }

def process_bulk_update(df):
    """Process bulk update"""
    try:
        successful = 0
        failed = 0
        errors = []
        
        for idx, row in df.iterrows():
            try:
                # Find employee
                employee = Employee.query.filter_by(
                    employee_id=str(row['Employee ID'])
                ).first()
                
                if not employee:
                    errors.append(f"Employee ID {row['Employee ID']} not found")
                    failed += 1
                    continue
                
                # Update fields
                for col in df.columns:
                    if col != 'Employee ID' and pd.notna(row[col]):
                        if col == 'Crew':
                            employee.crew = str(row[col]).upper()
                        elif col == 'Email':
                            employee.email = str(row[col])
                        elif col == 'Department' and employee.position:
                            employee.position.department = str(row[col])
                        # Add more field mappings as needed
                
                successful += 1
                
            except Exception as e:
                failed += 1
                errors.append(f"Row {idx + 2}: {str(e)}")
        
        db.session.commit()
        
        return {
            'success': True,
            'total': len(df),
            'successful': successful,
            'failed': failed,
            'errors': errors[:5] if errors else None,
            'message': f'Successfully updated {successful} employees'
        }
        
    except Exception as e:
        db.session.rollback()
        return {
            'success': False,
            'error': str(e)
        }

# ==========================================
# TEMPLATE DOWNLOAD ROUTES
# ==========================================

@employee_import_bp.route('/download-employee-template')
@login_required
@supervisor_required
def download_employee_template():
    """Download employee upload template"""
    template_data = {
        'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
        'First Name': ['John', 'Jane', 'Bob'],
        'Last Name': ['Doe', 'Smith', 'Johnson'],
        'Email': ['john.doe@company.com', 'jane.smith@company.com', 'bob.johnson@company.com'],
        'Crew': ['A', 'B', 'C'],
        'Department': ['Production', 'Production', 'Maintenance'],
        'Position': ['Operator', 'Supervisor', 'Technician']
    }
    
    df = pd.DataFrame(template_data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Employee Data', index=False)
        
        # Add formatting
        workbook = writer.book
        worksheet = writer.sheets['Employee Data']
        
        # Header format
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': 'white',
            'border': 1
        })
        
        # Write headers with formatting
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
        
        # Adjust column widths
        worksheet.set_column('A:A', 15)  # Employee ID
        worksheet.set_column('B:C', 12)  # Names
        worksheet.set_column('D:D', 25)  # Email
        worksheet.set_column('E:G', 15)  # Other fields
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'employee_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

@employee_import_bp.route('/download-overtime-template')
@login_required
@supervisor_required
def download_overtime_template():
    """Download overtime upload template"""
    # Create template with employee IDs and 13 weeks
    template_data = {'Employee ID': ['EMP001', 'EMP002', 'EMP003']}
    
    # Add 13 week columns
    for i in range(1, 14):
        template_data[f'Week {i}'] = [0, 0, 0]
    
    df = pd.DataFrame(template_data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Overtime Data', index=False)
        
        # Add formatting
        workbook = writer.book
        worksheet = writer.sheets['Overtime Data']
        
        # Header format
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': 'white',
            'border': 1
        })
        
        # Write headers
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
        
        # Set column widths
        worksheet.set_column('A:A', 15)  # Employee ID
        worksheet.set_column('B:N', 10)  # Week columns
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'overtime_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

@employee_import_bp.route('/download-bulk-update-template/<template_type>')
@login_required
@supervisor_required
def download_bulk_update_template(template_type):
    """Download bulk update template"""
    if template_type == 'employee':
        template_data = {
            'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
            'Email': ['new.email@company.com', '', ''],
            'Crew': ['B', 'C', ''],
            'Department': ['', 'Maintenance', '']
        }
    else:
        template_data = {'Employee ID': ['EMP001', 'EMP002', 'EMP003']}
    
    df = pd.DataFrame(template_data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Bulk Update', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'bulk_update_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

# ==========================================
# EXPORT ROUTES
# ==========================================

@employee_import_bp.route('/export-current-employees')
@login_required
@supervisor_required
def export_current_employees():
    """Export current employee list"""
    try:
        employees = Employee.query.filter_by(is_supervisor=False).all()
        
        data = []
        for emp in employees:
            data.append({
                'Employee ID': emp.employee_id,
                'First Name': emp.name.split()[0] if emp.name else '',
                'Last Name': ' '.join(emp.name.split()[1:]) if emp.name and len(emp.name.split()) > 1 else '',
                'Email': emp.email,
                'Crew': emp.crew or '',
                'Position': emp.position.name if emp.position else '',
                'Department': emp.position.department if emp.position else ''
            })
        
        df = pd.DataFrame(data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Employees', index=False)
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'employees_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
        
    except Exception as e:
        logger.error(f"Error exporting employees: {e}")
        flash('Error exporting employee data.', 'danger')
        return redirect(url_for('employee_import.upload_employees'))

@employee_import_bp.route('/export-current-overtime')
@login_required
@supervisor_required
def export_current_overtime():
    """Export current overtime data"""
    try:
        # Get all employees with overtime
        employees = Employee.query.filter(
            Employee.is_supervisor == False,
            Employee.overtime_history.any()
        ).all()
        
        data = []
        for emp in employees:
            row = {'Employee ID': emp.employee_id}
            
            # Get overtime for last 13 weeks
            for i in range(13):
                week_start = datetime.now().date() - timedelta(weeks=(13-i))
                week_start = week_start - timedelta(days=week_start.weekday())
                
                ot = OvertimeHistory.query.filter_by(
                    employee_id=emp.id,
                    week_start_date=week_start
                ).first()
                
                row[f'Week {i+1}'] = ot.hours_worked if ot else 0
            
            data.append(row)
        
        df = pd.DataFrame(data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Overtime', index=False)
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'overtime_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
        
    except Exception as e:
        logger.error(f"Error exporting overtime: {e}")
        flash('Error exporting overtime data.', 'danger')
        return redirect(url_for('employee_import.upload_overtime'))

# ==========================================
# FILE DOWNLOAD ROUTE
# ==========================================

@employee_import_bp.route('/download-upload-file/<int:upload_id>')
@login_required
@supervisor_required
def download_upload_file(upload_id):
    """Download original uploaded file"""
    try:
        upload = FileUpload.query.get_or_404(upload_id)
        
        # For now, return a message since we don't store the actual files
        flash('Original file download not available. Files are not stored after processing.', 'info')
        return redirect(url_for('employee_import.upload_history'))
        
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        flash('Error downloading file.', 'danger')
        return redirect(url_for('employee_import.upload_history'))

# ==========================================
# ERROR HANDLERS
# ==========================================

@employee_import_bp.errorhandler(Exception)
def handle_error(error):
    """Handle blueprint errors"""
    logger.error(f"Employee import error: {error}")
    db.session.rollback()
    return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500
