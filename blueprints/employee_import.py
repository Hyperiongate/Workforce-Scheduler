# blueprints/employee_import.py - COMPLETE FILE WITH ALL ROUTES
"""
Employee Import Blueprint - Complete implementation with all features
Handles all Excel upload/download/export functionality
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, current_app, session
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db, Employee, Position, Skill, OvertimeHistory, FileUpload
from datetime import datetime, date, timedelta
from sqlalchemy import func, or_, and_
import pandas as pd
import os
import io
import re
import random
import string
import logging
import traceback

# Set up logging
logger = logging.getLogger(__name__)

# Create blueprint
employee_import_bp = Blueprint('employee_import', __name__)

# ============================================
# HELPER FUNCTIONS
# ============================================

def allowed_file(filename):
    """Check if file extension is allowed"""
    ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_username(first_name, last_name):
    """Generate unique username from name"""
    base_username = f"{first_name[0].lower()}{last_name.lower()}"
    username = base_username
    counter = 1
    
    while Employee.query.filter_by(username=username).first():
        username = f"{base_username}{counter}"
        counter += 1
    
    return username

def generate_temp_password():
    """Generate temporary password"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=12))

def is_valid_email(email):
    """Simple email validation"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def get_upload_statistics():
    """Get statistics for the upload dashboard"""
    try:
        total_employees = Employee.query.count()
        
        crew_stats = db.session.query(
            Employee.crew, func.count(Employee.id)
        ).group_by(Employee.crew).all()
        
        crews = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'Unassigned': 0}
        for crew, count in crew_stats:
            if crew in ['A', 'B', 'C', 'D']:
                crews[crew] = count
            elif not crew:
                crews['Unassigned'] = count
        
        recent_uploads = FileUpload.query.order_by(
            FileUpload.upload_date.desc()
        ).limit(5).all()
        
        employees_without_ot = Employee.query.filter(
            ~Employee.id.in_(
                db.session.query(OvertimeHistory.employee_id).distinct()
            )
        ).count()
        
        return {
            'total_employees': total_employees,
            'crews': crews,
            'recent_uploads': recent_uploads,
            'employees_without_ot': employees_without_ot
        }
    except Exception as e:
        logger.error(f"Error getting upload statistics: {str(e)}")
        return {
            'total_employees': 0,
            'crews': {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'Unassigned': 0},
            'recent_uploads': [],
            'employees_without_ot': 0
        }

# ============================================
# MAIN UPLOAD ROUTES
# ============================================

@employee_import_bp.route('/upload-employees', methods=['GET', 'POST'])
@login_required
def upload_employees():
    """Main employee upload page"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisor privileges required.', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{filename}"
            
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, filename)
            
            try:
                file.save(filepath)
                
                # Process the file
                upload_type = request.form.get('upload_type', 'employee')
                replace_all = request.form.get('replace_all') == 'true'
                validate_only = request.form.get('validate_only') == 'true'
                
                if upload_type == 'employee':
                    result = process_employee_upload(filepath, replace_all, validate_only)
                elif upload_type == 'overtime':
                    result = process_overtime_upload(filepath, replace_all, validate_only)
                elif upload_type == 'bulk_update':
                    result = process_bulk_update(filepath, validate_only)
                else:
                    result = {'success': False, 'message': 'Invalid upload type'}
                
                if result['success']:
                    flash(result['message'], 'success')
                    if 'credentials_file' in result:
                        session['credentials_file'] = result['credentials_file']
                        return redirect(url_for('employee_import.download_credentials'))
                else:
                    flash(result['message'], 'danger')
                    if 'errors' in result:
                        for error in result['errors'][:10]:  # Show first 10 errors
                            flash(error, 'warning')
            
            except Exception as e:
                logger.error(f"Upload processing error: {str(e)}")
                flash(f'Error processing file: {str(e)}', 'danger')
            
            return redirect(url_for('employee_import.upload_employees'))
    
    # GET request - show upload page
    stats = get_upload_statistics()
    return render_template('upload_employees_enhanced.html', stats=stats)

@employee_import_bp.route('/upload-overtime', methods=['GET', 'POST'])
@login_required
def upload_overtime():
    """Upload overtime history"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"overtime_{timestamp}_{filename}"
            
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, filename)
            
            try:
                file.save(filepath)
                
                replace_all = request.form.get('replace_all') == 'true'
                validate_only = request.form.get('validate_only') == 'true'
                
                result = process_overtime_upload(filepath, replace_all, validate_only)
                
                if result['success']:
                    flash(result['message'], 'success')
                else:
                    flash(result['message'], 'danger')
                    if 'errors' in result:
                        for error in result['errors'][:10]:
                            flash(error, 'warning')
                
            except Exception as e:
                logger.error(f"Overtime upload error: {str(e)}")
                flash(f'Error processing file: {str(e)}', 'danger')
            
            return redirect(url_for('employee_import.upload_overtime'))
    
    # GET request - show overtime statistics
    stats = {
        'total_ot_hours': db.session.query(func.sum(OvertimeHistory.hours_worked)).scalar() or 0,
        'employees_with_ot': db.session.query(func.count(func.distinct(OvertimeHistory.employee_id))).scalar() or 0,
        'recent_uploads': FileUpload.query.filter_by(file_type='overtime_import')
                                         .order_by(FileUpload.upload_date.desc())
                                         .limit(5).all()
    }
    
    return render_template('upload_overtime.html', stats=stats)

@employee_import_bp.route('/upload-history')
@login_required
def upload_history():
    """View upload history"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    # Handle AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        uploads = FileUpload.query.order_by(FileUpload.upload_date.desc()).all()
        data = []
        for upload in uploads:
            data.append({
                'id': upload.id,
                'filename': upload.filename,
                'file_type': upload.file_type,
                'upload_date': upload.upload_date.strftime('%Y-%m-%d %H:%M:%S'),
                'uploaded_by': f"{upload.uploaded_by.first_name} {upload.uploaded_by.last_name}",
                'status': upload.status,
                'records_processed': upload.records_processed,
                'records_created': upload.records_created,
                'records_updated': upload.records_updated
            })
        return jsonify(data)
    
    # Regular HTML request
    file_type = request.args.get('file_type')
    status = request.args.get('status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = FileUpload.query
    
    if file_type:
        query = query.filter_by(file_type=file_type)
    if status:
        query = query.filter_by(status=status)
    if start_date:
        query = query.filter(FileUpload.upload_date >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(FileUpload.upload_date <= datetime.strptime(end_date, '%Y-%m-%d'))
    
    uploads = query.order_by(FileUpload.upload_date.desc()).all()
    
    return render_template('upload_history.html', uploads=uploads)

# ============================================
# VALIDATION ROUTES
# ============================================

@employee_import_bp.route('/validate-upload', methods=['POST'])
@login_required
def validate_upload():
    """Validate uploaded file before processing"""
    if not current_user.is_supervisor:
        return jsonify({
            'success': False, 
            'error': 'Unauthorized - Supervisor access required',
            'total_errors': 1
        }), 403
    
    if 'file' not in request.files:
        return jsonify({
            'success': False, 
            'error': 'No file provided',
            'total_errors': 1
        }), 400
    
    file = request.files['file']
    
    if not file or file.filename == '':
        return jsonify({
            'success': False, 
            'error': 'No file selected',
            'total_errors': 1
        }), 400
    
    if not allowed_file(file.filename):
        return jsonify({
            'success': False, 
            'error': 'Invalid file type. Please upload an Excel file (.xlsx or .xls)',
            'total_errors': 1
        }), 400
    
    # Save file temporarily
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"validate_{timestamp}_{filename}"
    
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
    os.makedirs(upload_folder, exist_ok=True)
    filepath = os.path.join(upload_folder, filename)
    
    try:
        file.save(filepath)
        
        # Read and validate the file
        upload_type = request.form.get('type', 'employee')
        
        if upload_type == 'employee':
            df = pd.read_excel(filepath, sheet_name='Employee Data')
            errors = validate_employee_data(df)
            warnings = []
            
            # Check for employees without crew assignment
            if 'Crew' in df.columns:
                no_crew = df[df['Crew'].isna() | (df['Crew'] == '')].shape[0]
                if no_crew > 0:
                    warnings.append(f"{no_crew} employees have no crew assignment")
            
            result = {
                'success': len(errors) == 0,
                'row_count': len(df),
                'errors': errors,
                'warnings': warnings,
                'total_errors': len(errors)
            }
            
        elif upload_type == 'overtime':
            df = pd.read_excel(filepath, sheet_name=0)
            errors = validate_overtime_data(df)
            
            result = {
                'success': len(errors) == 0,
                'row_count': len(df),
                'errors': errors,
                'total_errors': len(errors),
                'employee_count': df['Employee ID'].nunique() if 'Employee ID' in df.columns else 0
            }
            
        elif upload_type == 'bulk_update':
            df = pd.read_excel(filepath, sheet_name=0)
            errors = validate_bulk_update_data(df)
            
            result = {
                'success': len(errors) == 0,
                'row_count': len(df),
                'errors': errors,
                'total_errors': len(errors)
            }
            
        else:
            result = {
                'success': False,
                'error': 'Invalid upload type',
                'total_errors': 1
            }
        
        # Clean up temporary file
        try:
            os.remove(filepath)
        except:
            pass
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Validation error: {str(e)}")
        # Clean up on error
        try:
            os.remove(filepath)
        except:
            pass
            
        return jsonify({
            'success': False,
            'error': f'Error reading file: {str(e)}',
            'total_errors': 1
        })

# ============================================
# DOWNLOAD TEMPLATE ROUTES
# ============================================

@employee_import_bp.route('/download-employee-template')
@login_required
def download_employee_template():
    """Download employee upload template"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    template_data = {
        'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
        'First Name': ['John', 'Jane', 'Bob'],
        'Last Name': ['Doe', 'Smith', 'Johnson'],
        'Email': ['john.doe@company.com', 'jane.smith@company.com', 'bob.johnson@company.com'],
        'Crew': ['A', 'B', 'C'],
        'Position': ['Operator', 'Lead Operator', 'Supervisor'],
        'Department': ['Production', 'Production', 'Management'],
        'Hire Date': ['2020-01-15', '2019-06-20', '2018-03-10'],
        'Phone': ['555-0101', '555-0102', '555-0103'],
        'Emergency Contact': ['Mary Doe (555-0201)', 'Jim Smith (555-0202)', 'Alice Johnson (555-0203)'],
        'Skills': ['Forklift, Safety', 'Electrical, HVAC', 'Leadership, Safety']
    }
    
    df = pd.DataFrame(template_data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Employee Data', index=False)
        
        instructions = pd.DataFrame({
            'Instructions': [
                'EMPLOYEE UPLOAD TEMPLATE',
                '',
                'Required Fields:',
                '- Employee ID: Unique identifier for each employee',
                '- First Name: Employee first name',
                '- Last Name: Employee last name', 
                '- Email: Valid email address (will be used for login)',
                '- Crew: Must be A, B, C, or D',
                '- Position: Job title/position',
                '',
                'Optional Fields:',
                '- Department: Department name',
                '- Hire Date: Format YYYY-MM-DD',
                '- Phone: Contact number',
                '- Emergency Contact: Name and phone',
                '- Skills: Comma-separated list',
                '',
                'Notes:',
                '- Do not modify column headers',
                '- Do not add extra sheets',
                '- Save as .xlsx format'
            ]
        })
        instructions.to_excel(writer, sheet_name='Instructions', index=False)
        
        # Add data validation
        workbook = writer.book
        worksheet = workbook['Employee Data']
        
        # Adjust column widths
        worksheet.column_dimensions['A'].width = 15  # Employee ID
        worksheet.column_dimensions['B'].width = 15  # First Name
        worksheet.column_dimensions['C'].width = 15  # Last Name
        worksheet.column_dimensions['D'].width = 30  # Email
        worksheet.column_dimensions['E'].width = 10  # Crew
        worksheet.column_dimensions['F'].width = 20  # Position
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'employee_upload_template_{date.today().strftime("%Y%m%d")}.xlsx'
    )

@employee_import_bp.route('/download-overtime-template')
@login_required
def download_overtime_template():
    """Download overtime upload template"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    # Create sample data for 3 employees with 13 weeks
    weeks = []
    for i in range(13, 0, -1):
        week_start = date.today() - timedelta(weeks=i)
        week_start = week_start - timedelta(days=week_start.weekday())  # Monday
        week_end = week_start + timedelta(days=6)  # Sunday
        weeks.append({
            'week_num': 14 - i,
            'start': week_start,
            'end': week_end
        })
    
    data = []
    for emp_id in ['EMP001', 'EMP002', 'EMP003']:
        for week in weeks:
            data.append({
                'Employee ID': emp_id,
                'Week Number': week['week_num'],
                'Week Start Date': week['start'].strftime('%Y-%m-%d'),
                'Week End Date': week['end'].strftime('%Y-%m-%d'),
                'Hours Worked': 40.0 if week['week_num'] % 2 == 0 else 48.0,
                'Notes': 'Regular week' if week['week_num'] % 2 == 0 else 'Overtime week'
            })
    
    df = pd.DataFrame(data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Overtime Data', index=False)
        
        instructions = pd.DataFrame({
            'Instructions': [
                'OVERTIME HISTORY UPLOAD TEMPLATE',
                '',
                'This template is for uploading 13 weeks of overtime history.',
                '',
                'Required Fields:',
                '- Employee ID: Must match existing employee',
                '- Week Number: 1-13 (1 being the oldest week)',
                '- Week Start Date: Monday of the week (YYYY-MM-DD)',
                '- Week End Date: Sunday of the week (YYYY-MM-DD)',
                '- Hours Worked: Total hours for the week (decimal)',
                '',
                'Optional Fields:',
                '- Notes: Any relevant notes about the week',
                '',
                'Important:',
                '- Include all 13 weeks for each employee',
                '- Week dates must be consecutive',
                '- Hours should be realistic (0-84 typical range)'
            ]
        })
        instructions.to_excel(writer, sheet_name='Instructions', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'overtime_upload_template_{date.today().strftime("%Y%m%d")}.xlsx'
    )

@employee_import_bp.route('/download-bulk-update-template')
@login_required
def download_bulk_update_template():
    """Download bulk update template"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    # Get current employees for the template
    employees = Employee.query.order_by(Employee.last_name).limit(10).all()
    
    data = []
    for emp in employees:
        data.append({
            'Employee ID': emp.employee_id,
            'Current Name': emp.name,
            'Current Email': emp.email,
            'Current Crew': emp.crew or '',
            'Current Position': emp.position.name if emp.position else '',
            'New Crew': '',
            'New Position': '',
            'New Department': '',
            'New Email': '',
            'Action Notes': ''
        })
    
    df = pd.DataFrame(data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Bulk Updates', index=False)
        
        instructions = pd.DataFrame({
            'Instructions': [
                'BULK UPDATE TEMPLATE',
                '',
                'Use this template to update multiple employees at once.',
                '',
                'How to use:',
                '1. Employee ID must match existing employees',
                '2. Current fields show existing data (DO NOT MODIFY)',
                '3. Fill in only the "New" fields you want to change',
                '4. Leave "New" fields blank to keep current values',
                '',
                'Updateable Fields:',
                '- New Crew: A, B, C, or D',
                '- New Position: Must match existing position names',
                '- New Department: Department name',
                '- New Email: Valid email address',
                '',
                'Notes:',
                '- Updates are applied only to filled fields',
                '- Use Action Notes to document reason for changes'
            ]
        })
        instructions.to_excel(writer, sheet_name='Instructions', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'bulk_update_template_{date.today().strftime("%Y%m%d")}.xlsx'
    )

# ============================================
# EXPORT ROUTES
# ============================================

@employee_import_bp.route('/export-employees')
@login_required
def export_employees():
    """Export all employees to Excel"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    employees = Employee.query.order_by(Employee.last_name).all()
    
    data = []
    for emp in employees:
        skills = [es.skill.name for es in emp.employee_skills] if hasattr(emp, 'employee_skills') else []
        
        data.append({
            'Employee ID': emp.employee_id,
            'First Name': emp.first_name,
            'Last Name': emp.last_name,
            'Email': emp.email,
            'Username': emp.username,
            'Crew': emp.crew or '',
            'Position': emp.position.name if emp.position else '',
            'Department': emp.department or '',
            'Hire Date': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '',
            'Phone': emp.phone or '',
            'Emergency Contact': emp.emergency_contact or '',
            'Skills': ', '.join(skills),
            'Is Supervisor': 'Yes' if emp.is_supervisor else 'No',
            'Is Active': 'Yes' if emp.is_active else 'No',
            'Vacation Days': emp.vacation_days,
            'Sick Days': emp.sick_days,
            'Personal Days': emp.personal_days
        })
    
    df = pd.DataFrame(data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Employees', index=False)
        
        # Add summary sheet
        summary_data = {
            'Metric': ['Total Employees', 'Active Employees', 'Supervisors', 'Crew A', 'Crew B', 'Crew C', 'Crew D', 'Unassigned'],
            'Count': [
                len(employees),
                sum(1 for e in employees if e.is_active),
                sum(1 for e in employees if e.is_supervisor),
                sum(1 for e in employees if e.crew == 'A'),
                sum(1 for e in employees if e.crew == 'B'),
                sum(1 for e in employees if e.crew == 'C'),
                sum(1 for e in employees if e.crew == 'D'),
                sum(1 for e in employees if not e.crew or e.crew == '')
            ]
        }
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'employee_export_{date.today().strftime("%Y%m%d")}.xlsx'
    )

@employee_import_bp.route('/export-overtime-history')
@login_required
def export_overtime_history():
    """Export overtime history to Excel"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    # Get all overtime history
    overtime_records = OvertimeHistory.query.join(Employee).order_by(
        Employee.last_name, OvertimeHistory.week_start_date.desc()
    ).all()
    
    data = []
    for record in overtime_records:
        data.append({
            'Employee ID': record.employee.employee_id,
            'Employee Name': record.employee.name,
            'Crew': record.employee.crew or 'Unassigned',
            'Week Start': record.week_start_date.strftime('%Y-%m-%d'),
            'Week End': record.week_end_date.strftime('%Y-%m-%d'),
            'Hours Worked': record.hours_worked,
            'Notes': record.notes or ''
        })
    
    df = pd.DataFrame(data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Main data sheet
        df.to_excel(writer, sheet_name='Overtime History', index=False)
        
        # Summary by employee
        if len(df) > 0:
            summary = df.groupby(['Employee ID', 'Employee Name', 'Crew']).agg({
                'Hours Worked': ['sum', 'mean', 'count']
            }).round(2)
            summary.columns = ['Total Hours', 'Average Hours', 'Weeks Count']
            summary.reset_index().to_excel(writer, sheet_name='Employee Summary', index=False)
            
            # Summary by crew
            crew_summary = df.groupby('Crew').agg({
                'Hours Worked': ['sum', 'mean'],
                'Employee ID': 'nunique'
            }).round(2)
            crew_summary.columns = ['Total Hours', 'Average Hours', 'Employee Count']
            crew_summary.reset_index().to_excel(writer, sheet_name='Crew Summary', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'overtime_export_{date.today().strftime("%Y%m%d")}.xlsx'
    )

# ============================================
# ADDITIONAL ROUTES
# ============================================

@employee_import_bp.route('/download-credentials')
@login_required
def download_credentials():
    """Download generated credentials file"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    credentials_file = session.get('credentials_file')
    if not credentials_file:
        flash('No credentials file available', 'warning')
        return redirect(url_for('employee_import.upload_employees'))
    
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
    filepath = os.path.join(upload_folder, credentials_file)
    
    if not os.path.exists(filepath):
        flash('Credentials file not found', 'danger')
        return redirect(url_for('employee_import.upload_employees'))
    
    session.pop('credentials_file', None)
    
    return send_file(
        filepath,
        as_attachment=True,
        download_name=f'employee_credentials_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

@employee_import_bp.route('/download-upload-file/<int:upload_id>')
@login_required
def download_upload_file(upload_id):
    """Download original uploaded file"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    upload = FileUpload.query.get_or_404(upload_id)
    
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
    filepath = os.path.join(upload_folder, upload.filename)
    
    if not os.path.exists(filepath):
        flash('Original file no longer exists', 'warning')
        return redirect(url_for('employee_import.upload_history'))
    
    return send_file(filepath, as_attachment=True, download_name=upload.filename)

# ============================================
# API ENDPOINTS
# ============================================

@employee_import_bp.route('/api/upload/delete/<int:upload_id>', methods=['DELETE'])
@login_required
def delete_upload(upload_id):
    """Delete an upload record"""
    if not current_user.is_supervisor:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        upload = FileUpload.query.get_or_404(upload_id)
        db.session.delete(upload)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@employee_import_bp.route('/api/upload/details/<int:upload_id>')
@login_required
def get_upload_details(upload_id):
    """Get detailed information about an upload"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    upload = FileUpload.query.get_or_404(upload_id)
    
    data = {
        'id': upload.id,
        'filename': upload.filename,
        'file_type': upload.file_type,
        'file_size': upload.file_size,
        'upload_date': upload.upload_date.isoformat(),
        'uploaded_by_name': f"{upload.uploaded_by.first_name} {upload.uploaded_by.last_name}",
        'uploaded_by_email': upload.uploaded_by.email,
        'status': upload.status,
        'records_processed': upload.records_processed,
        'records_created': upload.records_created,
        'records_updated': upload.records_updated,
        'error_details': upload.error_details,
        'notes': upload.notes
    }
    
    if upload.file_type == 'overtime_import' and upload.records_processed:
        try:
            total_hours = OvertimeHistory.query.filter(
                OvertimeHistory.created_at >= upload.upload_date,
                OvertimeHistory.created_at <= upload.upload_date + timedelta(minutes=5)
            ).with_entities(func.sum(OvertimeHistory.hours_worked)).scalar()
            data['total_overtime_hours'] = float(total_hours) if total_hours else 0
        except:
            pass
    
    return jsonify(data)

# ============================================
# PROCESSING FUNCTIONS
# ============================================

def process_employee_upload(filepath, replace_all=False, validate_only=False):
    """Process employee data upload"""
    try:
        # Read the Excel file
        df = pd.read_excel(filepath, sheet_name='Employee Data')
        
        # Validate data
        errors = validate_employee_data(df)
        if errors:
            return {'success': False, 'message': 'Validation failed', 'errors': errors}
        
        if validate_only:
            return {'success': True, 'message': f'Validation passed! {len(df)} employees ready to import.'}
        
        # Create file upload record
        file_upload = FileUpload(
            filename=os.path.basename(filepath),
            file_type='employee_import',
            file_size=os.path.getsize(filepath),
            uploaded_by_id=current_user.id,
            status='processing',
            records_processed=len(df)
        )
        db.session.add(file_upload)
        db.session.commit()
        
        # Process employees
        credentials = []
        created_count = 0
        updated_count = 0
        errors = []
        
        if replace_all:
            # Delete all existing employees except current user
            Employee.query.filter(Employee.id != current_user.id).delete()
            db.session.commit()
        
        for idx, row in df.iterrows():
            try:
                emp_id = str(row['Employee ID']).strip()
                existing = Employee.query.filter_by(employee_id=emp_id).first()
                
                if existing:
                    # Update existing employee
                    existing.first_name = str(row['First Name']).strip()
                    existing.last_name = str(row['Last Name']).strip()
                    existing.name = f"{row['First Name'].strip()} {row['Last Name'].strip()}"
                    existing.email = str(row['Email']).strip().lower()
                    existing.crew = str(row['Crew']).strip().upper() if pd.notna(row['Crew']) else None
                    
                    if 'Department' in row and pd.notna(row['Department']):
                        existing.department = str(row['Department']).strip()
                    
                    if 'Phone' in row and pd.notna(row['Phone']):
                        existing.phone = str(row['Phone']).strip()
                    
                    if 'Emergency Contact' in row and pd.notna(row['Emergency Contact']):
                        existing.emergency_contact = str(row['Emergency Contact']).strip()
                    
                    updated_count += 1
                else:
                    # Create new employee
                    username = generate_username(row['First Name'].strip(), row['Last Name'].strip())
                    temp_password = generate_temp_password()
                    
                    new_emp = Employee(
                        employee_id=emp_id,
                        first_name=str(row['First Name']).strip(),
                        last_name=str(row['Last Name']).strip(),
                        name=f"{row['First Name'].strip()} {row['Last Name'].strip()}",
                        email=str(row['Email']).strip().lower(),
                        username=username,
                        crew=str(row['Crew']).strip().upper() if pd.notna(row['Crew']) else None,
                        department=str(row.get('Department', '')).strip() if 'Department' in row and pd.notna(row['Department']) else None,
                        phone=str(row.get('Phone', '')).strip() if 'Phone' in row and pd.notna(row['Phone']) else None,
                        emergency_contact=str(row.get('Emergency Contact', '')).strip() if 'Emergency Contact' in row and pd.notna(row['Emergency Contact']) else None,
                        is_active=True,
                        must_change_password=True,
                        first_login=True
                    )
                    
                    new_emp.set_password(temp_password)
                    
                    # Set position if provided
                    if 'Position' in row and pd.notna(row['Position']):
                        position = Position.query.filter_by(name=str(row['Position']).strip()).first()
                        if position:
                            new_emp.position_id = position.id
                    
                    # Set other fields if provided
                    if 'Hire Date' in row and pd.notna(row['Hire Date']):
                        try:
                            new_emp.hire_date = pd.to_datetime(row['Hire Date']).date()
                        except:
                            pass
                    
                    # Set supervisor flag based on position
                    if 'Position' in row and pd.notna(row['Position']):
                        position_name = str(row['Position']).lower()
                        if 'supervisor' in position_name:
                            new_emp.is_supervisor = True
                    
                    db.session.add(new_emp)
                    created_count += 1
                    
                    credentials.append({
                        'Employee ID': emp_id,
                        'Name': new_emp.name,
                        'Email': new_emp.email,
                        'Username': username,
                        'Temporary Password': temp_password
                    })
                    
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                logger.error(f"Error processing row {idx + 2}: {str(e)}")
        
        db.session.commit()
        
        # Update file upload record
        file_upload.status = 'completed' if not errors else 'completed_with_errors'
        file_upload.records_created = created_count
        file_upload.records_updated = updated_count
        if errors:
            file_upload.error_details = '\n'.join(errors[:50])
        db.session.commit()
        
        # Save credentials if any were created
        if credentials:
            cred_df = pd.DataFrame(credentials)
            cred_filename = f"credentials_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            cred_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], cred_filename)
            cred_df.to_excel(cred_filepath, index=False)
            
            return {
                'success': True,
                'message': f'Successfully processed {created_count + updated_count} employees. Created: {created_count}, Updated: {updated_count}',
                'credentials_file': cred_filename
            }
        
        return {
            'success': True,
            'message': f'Successfully processed {created_count + updated_count} employees. Created: {created_count}, Updated: {updated_count}'
        }
        
    except Exception as e:
        logger.error(f"Employee upload failed: {str(e)}\n{traceback.format_exc()}")
        return {'success': False, 'message': str(e)}

def process_overtime_upload(filepath, replace_all=False, validate_only=False):
    """Process overtime history upload"""
    try:
        df = pd.read_excel(filepath, sheet_name=0)
        
        errors = validate_overtime_data(df)
        if errors:
            return {'success': False, 'message': 'Validation failed', 'errors': errors}
        
        if validate_only:
            employee_count = df['Employee ID'].nunique()
            return {'success': True, 'message': f'Validation passed! {len(df)} overtime records for {employee_count} employees ready to import.'}
        
        # Create file upload record
        file_upload = FileUpload(
            filename=os.path.basename(filepath),
            file_type='overtime_import',
            file_size=os.path.getsize(filepath),
            uploaded_by_id=current_user.id,
            status='processing',
            records_processed=len(df)
        )
        db.session.add(file_upload)
        db.session.commit()
        
        created_count = 0
        updated_count = 0
        errors = []
        
        if replace_all:
            # Delete all existing overtime history
            OvertimeHistory.query.delete()
            db.session.commit()
        
        for idx, row in df.iterrows():
            try:
                emp_id = str(row['Employee ID']).strip()
                employee = Employee.query.filter_by(employee_id=emp_id).first()
                
                if not employee:
                    errors.append(f"Row {idx + 2}: Employee {emp_id} not found")
                    continue
                
                # Check if record already exists
                week_start = pd.to_datetime(row['Week Start Date']).date()
                existing = OvertimeHistory.query.filter_by(
                    employee_id=employee.id,
                    week_start_date=week_start
                ).first()
                
                if existing:
                    # Update existing record
                    existing.hours_worked = float(row['Hours Worked'])
                    existing.week_end_date = pd.to_datetime(row['Week End Date']).date()
                    if 'Notes' in row and pd.notna(row['Notes']):
                        existing.notes = str(row['Notes']).strip()
                    updated_count += 1
                else:
                    # Create new record
                    ot_record = OvertimeHistory(
                        employee_id=employee.id,
                        week_start_date=week_start,
                        week_end_date=pd.to_datetime(row['Week End Date']).date(),
                        hours_worked=float(row['Hours Worked']),
                        notes=str(row['Notes']).strip() if 'Notes' in row and pd.notna(row['Notes']) else None,
                        created_at=datetime.now()
                    )
                    db.session.add(ot_record)
                    created_count += 1
                    
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                logger.error(f"Error processing overtime row {idx + 2}: {str(e)}")
        
        db.session.commit()
        
        # Update file upload record
        file_upload.status = 'completed' if not errors else 'completed_with_errors'
        file_upload.records_created = created_count
        file_upload.records_updated = updated_count
        if errors:
            file_upload.error_details = '\n'.join(errors[:50])
        db.session.commit()
        
        message = f"Successfully imported {created_count} and updated {updated_count} overtime records"
        if errors:
            message += f" with {len(errors)} errors"
        
        return {
            'success': created_count > 0 or updated_count > 0,
            'message': message,
            'errors': errors[:10] if errors else []
        }
        
    except Exception as e:
        logger.error(f"Overtime upload failed: {str(e)}\n{traceback.format_exc()}")
        return {'success': False, 'message': str(e)}

def process_bulk_update(filepath, validate_only=False):
    """Process bulk employee updates"""
    try:
        df = pd.read_excel(filepath, sheet_name=0)
        
        errors = validate_bulk_update_data(df)
        if errors:
            return {'success': False, 'message': 'Validation failed', 'errors': errors}
        
        if validate_only:
            return {'success': True, 'message': f'Validation passed! {len(df)} updates ready to process.'}
        
        # Create file upload record
        file_upload = FileUpload(
            filename=os.path.basename(filepath),
            file_type='bulk_update',
            file_size=os.path.getsize(filepath),
            uploaded_by_id=current_user.id,
            status='processing',
            records_processed=len(df)
        )
        db.session.add(file_upload)
        db.session.commit()
        
        updated_count = 0
        errors = []
        
        for idx, row in df.iterrows():
            try:
                emp_id = str(row['Employee ID']).strip()
                employee = Employee.query.filter_by(employee_id=emp_id).first()
                
                if not employee:
                    errors.append(f"Row {idx + 2}: Employee {emp_id} not found")
                    continue
                
                updated = False
                
                # Update crew if provided
                if 'New Crew' in row and pd.notna(row['New Crew']) and str(row['New Crew']).strip():
                    new_crew = str(row['New Crew']).strip().upper()
                    if new_crew in ['A', 'B', 'C', 'D']:
                        employee.crew = new_crew
                        updated = True
                
                # Update position if provided
                if 'New Position' in row and pd.notna(row['New Position']) and str(row['New Position']).strip():
                    position = Position.query.filter_by(name=str(row['New Position']).strip()).first()
                    if position:
                        employee.position_id = position.id
                        updated = True
                    else:
                        errors.append(f"Row {idx + 2}: Position '{row['New Position']}' not found")
                
                # Update department if provided
                if 'New Department' in row and pd.notna(row['New Department']) and str(row['New Department']).strip():
                    employee.department = str(row['New Department']).strip()
                    updated = True
                
                # Update email if provided
                if 'New Email' in row and pd.notna(row['New Email']) and str(row['New Email']).strip():
                    new_email = str(row['New Email']).strip().lower()
                    if is_valid_email(new_email):
                        employee.email = new_email
                        updated = True
                    else:
                        errors.append(f"Row {idx + 2}: Invalid email format '{new_email}'")
                
                if updated:
                    updated_count += 1
                    
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                logger.error(f"Error processing bulk update row {idx + 2}: {str(e)}")
                
        db.session.commit()
        
        file_upload.status = 'completed' if not errors else 'completed_with_errors'
        file_upload.records_updated = updated_count
        if errors:
            file_upload.error_details = '\n'.join(errors[:50])
        db.session.commit()
        
        message = f"Updated {updated_count} employees"
        if errors:
            message += f" with {len(errors)} errors"
            
        return {
            'success': updated_count > 0,
            'message': message,
            'errors': errors[:10]
        }
        
    except Exception as e:
        logger.error(f"Bulk update failed: {str(e)}\n{traceback.format_exc()}")
        return {'success': False, 'message': str(e)}

# ============================================
# VALIDATION FUNCTIONS
# ============================================

def validate_employee_data(df):
    """Validate employee data"""
    errors = []
    
    # Check required columns
    required_columns = ['Employee ID', 'First Name', 'Last Name', 'Email', 'Crew', 'Position']
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")
        return errors
    
    # Check for duplicate employee IDs
    duplicates = df[df.duplicated('Employee ID', keep=False)]['Employee ID'].unique()
    if len(duplicates) > 0:
        errors.append(f"Duplicate Employee IDs found: {', '.join(map(str, duplicates[:5]))}")
    
    # Validate each row
    for idx, row in df.iterrows():
        row_num = idx + 2
        
        # Check required fields
        for col in required_columns:
            if pd.isna(row[col]) or str(row[col]).strip() == '':
                errors.append(f"Row {row_num}: {col} is required")
                
        # Validate email format
        if pd.notna(row['Email']):
            email = str(row['Email']).strip()
            if not is_valid_email(email):
                errors.append(f"Row {row_num}: Invalid email format - {email}")
                
        # Validate crew
        if pd.notna(row['Crew']):
            crew = str(row['Crew']).strip().upper()
            if crew not in ['A', 'B', 'C', 'D']:
                errors.append(f"Row {row_num}: Invalid crew '{crew}' - must be A, B, C, or D")
    
    return errors[:20]  # Return first 20 errors

def validate_overtime_data(df):
    """Validate overtime data"""
    errors = []
    
    # Check required columns
    required_columns = ['Employee ID', 'Week Start Date', 'Week End Date', 'Hours Worked']
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")
        return errors
    
    # Validate each row
    for idx, row in df.iterrows():
        row_num = idx + 2
        
        # Check required fields
        if pd.isna(row['Employee ID']) or str(row['Employee ID']).strip() == '':
            errors.append(f"Row {row_num}: Employee ID is required")
            
        # Validate dates
        try:
            week_start = pd.to_datetime(row['Week Start Date']).date()
            week_end = pd.to_datetime(row['Week End Date']).date()
            
            if week_end < week_start:
                errors.append(f"Row {row_num}: Week end date cannot be before start date")
            elif (week_end - week_start).days != 6:
                errors.append(f"Row {row_num}: Week should be exactly 7 days")
                
        except:
            errors.append(f"Row {row_num}: Invalid date format")
            
        # Validate hours
        try:
            hours = float(row['Hours Worked'])
            if hours < 0 or hours > 168:  # Max hours in a week
                errors.append(f"Row {row_num}: Hours worked must be between 0 and 168")
        except:
            errors.append(f"Row {row_num}: Invalid hours format")
    
    return errors[:20]

def validate_bulk_update_data(df):
    """Validate bulk update data"""
    errors = []
    
    # Check required columns
    if 'Employee ID' not in df.columns:
        errors.append("Missing required column: Employee ID")
        return errors
    
    # Check for at least one update column
    update_columns = ['New Crew', 'New Position', 'New Department', 'New Email']
    if not any(col in df.columns for col in update_columns):
        errors.append("No update columns found. Need at least one of: " + ', '.join(update_columns))
        return errors
    
    # Validate each row
    for idx, row in df.iterrows():
        row_num = idx + 2
        
        if pd.isna(row['Employee ID']) or str(row['Employee ID']).strip() == '':
            errors.append(f"Row {row_num}: Employee ID is required")
            
        # Validate new crew if provided
        if 'New Crew' in row and pd.notna(row['New Crew']) and str(row['New Crew']).strip():
            crew = str(row['New Crew']).strip().upper()
            if crew not in ['A', 'B', 'C', 'D']:
                errors.append(f"Row {row_num}: Invalid crew '{crew}' - must be A, B, C, or D")
                
        # Validate new email if provided
        if 'New Email' in row and pd.notna(row['New Email']) and str(row['New Email']).strip():
            email = str(row['New Email']).strip()
            if not is_valid_email(email):
                errors.append(f"Row {row_num}: Invalid email format - {email}")
    
    return errors[:20]
