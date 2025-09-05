# blueprints/employee_import.py
"""
Complete Excel upload system for employee data management
FULL UNTRUNCATED VERSION - Deploy this entire file
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, send_file, make_response
from flask_login import login_required, current_user
from models import db, Employee, Position, OvertimeHistory, FileUpload
from datetime import datetime, timedelta, date
from werkzeug.utils import secure_filename
from sqlalchemy import func, and_, or_, text
from functools import wraps
import pandas as pd
import os
import io
import re
import logging
import json
import traceback
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# Set up logging
logger = logging.getLogger(__name__)

# Create blueprint - NO url_prefix so routes are at root level
employee_import_bp = Blueprint('employee_import', __name__)

# ==========================================
# DECORATORS AND HELPERS
# ==========================================

def supervisor_required(f):
    """Decorator to require supervisor access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.is_supervisor:
            flash('Access denied. Supervisors only.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    """Check if uploaded file has allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ['xlsx', 'xls']

def secure_file_path(filename):
    """Generate secure file path for uploads"""
    filename = secure_filename(filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    name, ext = os.path.splitext(filename)
    unique_filename = f"{name}_{timestamp}{ext}"
    return os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)

# ==========================================
# STATISTICS AND DATA FUNCTIONS
# ==========================================

def get_employee_stats():
    """Get employee statistics for dashboard"""
    try:
        total = Employee.query.filter_by(is_active=True).count()
        
        crews = {}
        for crew in ['A', 'B', 'C', 'D']:
            crews[crew] = Employee.query.filter_by(crew=crew, is_active=True).count()
        
        # Count employees with overtime
        with_overtime = 0
        try:
            with_overtime = OvertimeHistory.query.filter(
                OvertimeHistory.total_hours > 40
            ).distinct(OvertimeHistory.employee_id).count()
        except:
            pass
        
        return {
            'total_employees': total,
            'crews': crews,
            'with_overtime': with_overtime,
            'low_ot': 0,
            'medium_ot': 0,
            'high_ot': 0,
            'last_updated': datetime.now()
        }
    except Exception as e:
        logger.error(f"Error getting employee stats: {e}")
        return {
            'total_employees': 0,
            'crews': {'A': 0, 'B': 0, 'C': 0, 'D': 0},
            'with_overtime': 0,
            'low_ot': 0,
            'medium_ot': 0,
            'high_ot': 0,
            'last_updated': datetime.now()
        }

def get_recent_uploads(limit=5):
    """Get recent upload history"""
    try:
        uploads = FileUpload.query.order_by(
            FileUpload.uploaded_at.desc()
        ).limit(limit).all()
        
        return [{
            'id': upload.id,
            'filename': upload.filename,
            'upload_type': upload.upload_type or 'employee',
            'status': upload.status or 'completed',
            'records_processed': upload.records_processed or 0,
            'created_at': upload.uploaded_at,
            'uploaded_by': upload.uploaded_by
        } for upload in uploads]
    except Exception as e:
        logger.error(f"Error getting recent uploads: {e}")
        return []

def get_employees_without_accounts():
    """Get count of employees without login accounts"""
    try:
        return Employee.query.filter(
            and_(
                Employee.is_active == True,
                or_(Employee.email.is_(None), Employee.email == '')
            )
        ).count()
    except Exception as e:
        logger.error(f"Error getting employees without accounts: {e}")
        return 0

# ==========================================
# VALIDATION FUNCTIONS
# ==========================================

def validate_employee_data_comprehensive(df):
    """Comprehensive validation of employee data"""
    errors = []
    warnings = []
    
    # Check required columns
    required_columns = ['Employee ID', 'First Name', 'Last Name', 'Crew']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        return {
            'success': False,
            'error': f'Missing required columns: {", ".join(missing_columns)}'
        }
    
    # Track Employee IDs for duplicate check
    seen_ids = set()
    
    # Validate each row
    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel row number (1-indexed + header)
        
        # Check Employee ID
        emp_id = str(row.get('Employee ID', '')).strip() if pd.notna(row.get('Employee ID')) else ''
        if not emp_id:
            errors.append(f'Row {row_num}: Missing Employee ID')
        elif emp_id in seen_ids:
            errors.append(f'Row {row_num}: Duplicate Employee ID "{emp_id}"')
        else:
            seen_ids.add(emp_id)
        
        # Check Names
        first_name = str(row.get('First Name', '')).strip() if pd.notna(row.get('First Name')) else ''
        last_name = str(row.get('Last Name', '')).strip() if pd.notna(row.get('Last Name')) else ''
        
        if not first_name:
            errors.append(f'Row {row_num}: Missing First Name')
        if not last_name:
            errors.append(f'Row {row_num}: Missing Last Name')
        
        # Check Crew
        crew = str(row.get('Crew', '')).strip().upper() if pd.notna(row.get('Crew')) else ''
        if crew not in ['A', 'B', 'C', 'D']:
            errors.append(f'Row {row_num}: Invalid crew "{crew}". Must be A, B, C, or D')
        
        # Check email format if provided
        email = row.get('Email')
        if email and pd.notna(email):
            email_str = str(email).strip()
            if email_str and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email_str):
                warnings.append(f'Row {row_num}: Invalid email format "{email_str}"')
        
        # Check date format if hire date provided
        hire_date = row.get('Hire Date')
        if hire_date and pd.notna(hire_date):
            try:
                if isinstance(hire_date, str):
                    datetime.strptime(hire_date, '%Y-%m-%d')
            except:
                warnings.append(f'Row {row_num}: Invalid date format for Hire Date')
        
        # Stop if too many errors
        if len(errors) > 50:
            errors.append('... and more errors. Please fix the above issues first.')
            break
    
    if errors:
        return {
            'success': False,
            'error': f'Validation failed with {len(errors)} errors',
            'errors': errors[:20],  # Return first 20 errors
            'total_errors': len(errors),
            'warnings': warnings
        }
    
    return {
        'success': True,
        'message': f'Validation passed for {len(df)} employees',
        'employee_count': len(df),
        'warnings': warnings
    }

def validate_overtime_data_comprehensive(df):
    """Comprehensive validation of overtime data"""
    errors = []
    warnings = []
    
    # Check for Employee ID column
    if 'Employee ID' not in df.columns:
        return {
            'success': False,
            'error': 'Missing required column: Employee ID'
        }
    
    # Check for week columns
    week_columns = [col for col in df.columns if 'Week' in str(col)]
    if len(week_columns) < 1:
        return {
            'success': False,
            'error': 'No week columns found. Expected columns like "Week 1", "Week 2", etc.'
        }
    
    # Validate each row
    for idx, row in df.iterrows():
        row_num = idx + 2
        
        emp_id = str(row.get('Employee ID', '')).strip() if pd.notna(row.get('Employee ID')) else ''
        if not emp_id:
            errors.append(f'Row {row_num}: Missing Employee ID')
        
        # Check if employee exists
        employee = Employee.query.filter_by(employee_id=emp_id).first()
        if emp_id and not employee:
            warnings.append(f'Row {row_num}: Employee ID "{emp_id}" not found in system')
        
        # Validate week values
        for week_col in week_columns:
            value = row.get(week_col)
            if pd.notna(value):
                try:
                    hours = float(value)
                    if hours < 0:
                        errors.append(f'Row {row_num}, {week_col}: Negative hours not allowed')
                    elif hours > 168:  # Max hours in a week
                        errors.append(f'Row {row_num}, {week_col}: Hours exceed maximum (168)')
                except:
                    errors.append(f'Row {row_num}, {week_col}: Invalid hours value "{value}"')
    
    if errors:
        return {
            'success': False,
            'error': f'Validation failed with {len(errors)} errors',
            'errors': errors[:20],
            'total_errors': len(errors),
            'warnings': warnings
        }
    
    return {
        'success': True,
        'message': f'Validation passed for {len(df)} employees with {len(week_columns)} weeks of data',
        'employee_count': len(df),
        'weeks_count': len(week_columns),
        'warnings': warnings
    }

# ==========================================
# MAIN ROUTES
# ==========================================

@employee_import_bp.route('/upload-employees')
@login_required
@supervisor_required
def upload_employees():
    """Main upload page for employees"""
    try:
        stats = get_employee_stats()
        recent_uploads = get_recent_uploads()
        employees_without_accounts = get_employees_without_accounts()
        
        # Check which template exists
        template_options = [
            'upload_employees_enhanced.html',
            'upload_employees_simple.html',
            'upload_employees.html',
            'employee_upload.html'
        ]
        
        for template_name in template_options:
            try:
                return render_template(
                    template_name,
                    stats=stats,
                    recent_uploads=recent_uploads,
                    crew_distribution=stats.get('crews', {}),
                    total_employees=stats.get('total_employees', 0),
                    employees_without_accounts=employees_without_accounts,
                    account_creation_available=True
                )
            except Exception as e:
                continue
        
        # If no template works, render inline HTML
        return render_simple_upload_page(stats, recent_uploads)
        
    except Exception as e:
        logger.error(f"Error in upload_employees: {e}")
        flash('Error loading upload page. Please try again.', 'error')
        return redirect(url_for('supervisor.dashboard'))

def render_simple_upload_page(stats, recent_uploads):
    """Render a simple upload page inline if templates are missing"""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Upload Employees</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css">
    </head>
    <body>
        <nav class="navbar navbar-dark bg-primary">
            <div class="container-fluid">
                <span class="navbar-brand mb-0 h1">Workforce Scheduler</span>
                <a href="/dashboard" class="btn btn-light btn-sm">Back to Dashboard</a>
            </div>
        </nav>
        
        <div class="container mt-5">
            <h2><i class="bi bi-upload"></i> Employee Data Upload</h2>
            
            <div class="row mt-4">
                <div class="col-md-8">
                    <div class="card">
                        <div class="card-header bg-primary text-white">
                            <h5 class="mb-0">Upload Excel File</h5>
                        </div>
                        <div class="card-body">
                            <form method="POST" action="/upload-employees" enctype="multipart/form-data">
                                <div class="mb-3">
                                    <label for="uploadType" class="form-label">Upload Type</label>
                                    <select class="form-select" id="uploadType" name="uploadType">
                                        <option value="employee">Employee Data</option>
                                        <option value="overtime">Overtime History</option>
                                    </select>
                                </div>
                                
                                <div class="mb-3">
                                    <label for="file" class="form-label">Select Excel File</label>
                                    <input type="file" class="form-control" id="file" name="file" accept=".xlsx,.xls" required>
                                    <div class="form-text">Supported formats: .xlsx, .xls</div>
                                </div>
                                
                                <div class="mb-3">
                                    <div class="form-check">
                                        <input class="form-check-input" type="checkbox" id="replaceAll" name="replaceAll">
                                        <label class="form-check-label" for="replaceAll">
                                            Replace all existing data (use with caution)
                                        </label>
                                    </div>
                                </div>
                                
                                <button type="submit" class="btn btn-primary">
                                    <i class="bi bi-upload"></i> Upload File
                                </button>
                                <a href="/download-employee-template" class="btn btn-secondary">
                                    <i class="bi bi-download"></i> Download Template
                                </a>
                            </form>
                        </div>
                    </div>
                </div>
                
                <div class="col-md-4">
                    <div class="card bg-info text-white">
                        <div class="card-body">
                            <h5>Statistics</h5>
                            <p>Total Employees: <strong>{stats.get('total_employees', 0)}</strong></p>
                            <hr>
                            <h6>Crew Distribution:</h6>
                            <ul class="list-unstyled">
                                <li>Crew A: {stats.get('crews', {}).get('A', 0)}</li>
                                <li>Crew B: {stats.get('crews', {}).get('B', 0)}</li>
                                <li>Crew C: {stats.get('crews', {}).get('C', 0)}</li>
                                <li>Crew D: {stats.get('crews', {}).get('D', 0)}</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return make_response(html)

@employee_import_bp.route('/upload-employees', methods=['POST'])
@login_required
@supervisor_required
def upload_employees_post():
    """Handle file upload and processing"""
    try:
        logger.info(f"Upload POST received from user: {current_user.employee_id}")
        
        if 'file' not in request.files:
            flash('No file selected', 'error')
            return redirect(url_for('employee_import.upload_employees'))
        
        file = request.files['file']
        upload_type = request.form.get('uploadType', 'employee')
        replace_all = request.form.get('replaceAll') == 'on'
        
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('employee_import.upload_employees'))
        
        if not allowed_file(file.filename):
            flash('Invalid file type. Please upload an Excel file (.xlsx or .xls)', 'error')
            return redirect(url_for('employee_import.upload_employees'))
        
        # Save file
        filepath = secure_file_path(file.filename)
        file.save(filepath)
        
        # Create upload record
        upload_record = FileUpload(
            filename=file.filename,
            upload_type=upload_type,
            uploaded_by_id=current_user.id,
            status='processing',
            file_size=os.path.getsize(filepath)
        )
        db.session.add(upload_record)
        db.session.flush()
        
        try:
            # Read Excel file
            df = pd.read_excel(filepath, sheet_name=None)
            
            # Get the appropriate sheet
            if isinstance(df, dict):
                if 'Employee Data' in df:
                    df = df['Employee Data']
                elif 'Overtime Data' in df:
                    df = df['Overtime Data']
                else:
                    df = df[list(df.keys())[0]]
            
            # Validate data
            if upload_type == 'employee':
                validation = validate_employee_data_comprehensive(df)
                if validation['success']:
                    result = process_employee_upload(df, upload_record, replace_all)
                else:
                    result = validation
            elif upload_type == 'overtime':
                validation = validate_overtime_data_comprehensive(df)
                if validation['success']:
                    result = process_overtime_upload(df, upload_record)
                else:
                    result = validation
            else:
                result = {'success': False, 'error': 'Invalid upload type'}
            
            # Update upload record
            if result.get('success'):
                upload_record.status = 'completed'
                upload_record.records_processed = result.get('records_processed', 0)
                upload_record.successful_records = result.get('created', 0) + result.get('updated', 0)
                flash(f"Successfully processed {result.get('records_processed', 0)} records!", 'success')
            else:
                upload_record.status = 'failed'
                upload_record.error_details = {'error': result.get('error'), 'errors': result.get('errors', [])}
                flash(f"Upload failed: {result.get('error')}", 'error')
            
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Error processing upload: {e}\n{traceback.format_exc()}")
            upload_record.status = 'failed'
            upload_record.error_details = {'error': str(e)}
            db.session.commit()
            flash('Error processing file. Please check the format and try again.', 'error')
        
        return redirect(url_for('employee_import.upload_employees'))
        
    except Exception as e:
        logger.error(f"Error in upload POST: {e}")
        flash('Server error during upload. Please try again.', 'error')
        return redirect(url_for('employee_import.upload_employees'))

# ==========================================
# AJAX VALIDATION ROUTE
# ==========================================

@employee_import_bp.route('/validate-upload', methods=['POST'])
@login_required
@supervisor_required
def validate_upload():
    """AJAX endpoint to validate uploaded file before processing"""
    try:
        logger.info(f"Validation request from user: {current_user.employee_id}")
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        file = request.files['file']
        upload_type = request.form.get('uploadType', 'employee')
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Invalid file type. Please upload .xlsx or .xls files only'})
        
        # Save file temporarily
        filepath = secure_file_path(file.filename)
        file.save(filepath)
        
        try:
            # Read Excel file
            df = pd.read_excel(filepath, sheet_name=None)
            
            # Get the appropriate sheet
            if isinstance(df, dict):
                if 'Employee Data' in df:
                    df = df['Employee Data']
                elif 'Overtime Data' in df:
                    df = df['Overtime Data']
                else:
                    df = df[list(df.keys())[0]]
            
            # Check if empty
            if df.empty:
                os.remove(filepath)
                return jsonify({'success': False, 'error': 'File is empty or contains no data'})
            
            # Validate based on upload type
            if upload_type == 'employee':
                result = validate_employee_data_comprehensive(df)
            elif upload_type == 'overtime':
                result = validate_overtime_data_comprehensive(df)
            else:
                result = {'success': False, 'error': 'Invalid upload type'}
            
            # Clean up temp file if validation failed
            if not result.get('success'):
                os.remove(filepath)
            else:
                # Store filepath for later use
                result['filepath'] = filepath
            
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"Error validating file: {e}")
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({'success': False, 'error': f'Error reading file: {str(e)}'})
            
    except Exception as e:
        logger.error(f"Error in validate_upload: {e}")
        return jsonify({'success': False, 'error': 'Server error during validation'}), 500

# ==========================================
# PROCESSING FUNCTIONS
# ==========================================

def process_employee_upload(df, upload_record, replace_all=False):
    """Process employee data upload"""
    try:
        created_count = 0
        updated_count = 0
        skipped_count = 0
        errors = []
        
        # If replace all, delete existing non-admin employees
        if replace_all:
            deleted = Employee.query.filter(
                and_(
                    Employee.email != 'admin@workforce.com',
                    Employee.is_admin == False
                )
            ).delete()
            logger.info(f"Deleted {deleted} existing employees")
        
        # Process each row
        for idx, row in df.iterrows():
            try:
                employee_id = str(row.get('Employee ID', '')).strip()
                if not employee_id:
                    skipped_count += 1
                    continue
                
                # Check if employee exists
                employee = Employee.query.filter_by(employee_id=employee_id).first()
                
                if not employee:
                    # Create new employee
                    first_name = str(row.get('First Name', '')).strip()
                    last_name = str(row.get('Last Name', '')).strip()
                    
                    employee = Employee(
                        employee_id=employee_id,
                        name=f"{first_name} {last_name}".strip(),
                        email=str(row.get('Email', '')).strip() if pd.notna(row.get('Email')) else f"{employee_id}@company.com",
                        crew=str(row.get('Crew', '')).strip().upper(),
                        department=str(row.get('Department', '')).strip() if pd.notna(row.get('Department')) else None,
                        phone=str(row.get('Phone', '')).strip() if pd.notna(row.get('Phone')) else None,
                        is_active=True,
                        is_supervisor=str(row.get('Is Supervisor', 'No')).lower() == 'yes'
                    )
                    
                    # Set position if provided
                    if pd.notna(row.get('Position')):
                        position_name = str(row.get('Position')).strip()
                        position = Position.query.filter_by(name=position_name).first()
                        if not position:
                            position = Position(name=position_name)
                            db.session.add(position)
                            db.session.flush()
                        employee.position_id = position.id
                    
                    # Set hire date if provided
                    if pd.notna(row.get('Hire Date')):
                        try:
                            if isinstance(row.get('Hire Date'), str):
                                employee.hire_date = datetime.strptime(row.get('Hire Date'), '%Y-%m-%d').date()
                            else:
                                employee.hire_date = row.get('Hire Date')
                        except:
                            pass
                    
                    # Set default password
                    employee.set_password('changeme123')
                    
                    db.session.add(employee)
                    created_count += 1
                else:
                    # Update existing employee
                    first_name = str(row.get('First Name', '')).strip()
                    last_name = str(row.get('Last Name', '')).strip()
                    employee.name = f"{first_name} {last_name}".strip()
                    employee.crew = str(row.get('Crew', '')).strip().upper()
                    
                    if pd.notna(row.get('Email')):
                        employee.email = str(row.get('Email')).strip()
                    if pd.notna(row.get('Department')):
                        employee.department = str(row.get('Department')).strip()
                    if pd.notna(row.get('Phone')):
                        employee.phone = str(row.get('Phone')).strip()
                    if pd.notna(row.get('Is Supervisor')):
                        employee.is_supervisor = str(row.get('Is Supervisor')).lower() == 'yes'
                    
                    updated_count += 1
                
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                logger.error(f"Error processing row {idx + 2}: {e}")
        
        db.session.commit()
        
        return {
            'success': True,
            'records_processed': created_count + updated_count,
            'created': created_count,
            'updated': updated_count,
            'skipped': skipped_count,
            'errors': errors
        }
        
    except Exception as e:
        logger.error(f"Error processing employee upload: {e}")
        db.session.rollback()
        return {'success': False, 'error': str(e)}

def process_overtime_upload(df, upload_record):
    """Process overtime data upload"""
    try:
        processed_count = 0
        skipped_count = 0
        errors = []
        
        # Get week columns
        week_columns = [col for col in df.columns if 'Week' in str(col)]
        
        for idx, row in df.iterrows():
            try:
                employee_id = str(row.get('Employee ID', '')).strip()
                if not employee_id:
                    skipped_count += 1
                    continue
                
                employee = Employee.query.filter_by(employee_id=employee_id).first()
                if not employee:
                    errors.append(f"Row {idx + 2}: Employee ID '{employee_id}' not found")
                    continue
                
                # Process each week
                for week_num, week_col in enumerate(week_columns, 1):
                    hours = row.get(week_col)
                    if pd.notna(hours):
                        try:
                            hours_float = float(hours)
                            
                            # Calculate week ending date (example logic)
                            week_ending = date.today() - timedelta(weeks=13-week_num)
                            
                            # Check if record exists
                            ot_record = OvertimeHistory.query.filter_by(
                                employee_id=employee.id,
                                week_ending=week_ending
                            ).first()
                            
                            if not ot_record:
                                ot_record = OvertimeHistory(
                                    employee_id=employee.id,
                                    week_ending=week_ending,
                                    total_hours=hours_float,
                                    overtime_hours=max(0, hours_float - 40),
                                    regular_hours=min(40, hours_float)
                                )
                                db.session.add(ot_record)
                            else:
                                ot_record.total_hours = hours_float
                                ot_record.overtime_hours = max(0, hours_float - 40)
                                ot_record.regular_hours = min(40, hours_float)
                            
                            processed_count += 1
                        except ValueError:
                            errors.append(f"Row {idx + 2}, {week_col}: Invalid hours value")
                
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                logger.error(f"Error processing overtime row {idx + 2}: {e}")
        
        db.session.commit()
        
        return {
            'success': True,
            'records_processed': processed_count,
            'skipped': skipped_count,
            'errors': errors
        }
        
    except Exception as e:
        logger.error(f"Error processing overtime upload: {e}")
        db.session.rollback()
        return {'success': False, 'error': str(e)}

# ==========================================
# TEMPLATE DOWNLOAD ROUTES
# ==========================================

@employee_import_bp.route('/download-employee-template')
@login_required
@supervisor_required
def download_employee_template():
    """Download Excel template for employee upload"""
    try:
        # Create workbook
        wb = Workbook()
        ws = wb.active
        ws.title = 'Employee Data'
        
        # Define headers
        headers = [
            'Employee ID', 'First Name', 'Last Name', 'Email', 'Crew',
            'Position', 'Department', 'Hire Date', 'Phone',
            'Emergency Contact', 'Skills', 'Is Supervisor'
        ]
        
        # Style headers
        header_font = Font(bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='366092', end_color='366092', fill_type='solid')
        header_alignment = Alignment(horizontal='center')
        
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            ws.column_dimensions[get_column_letter(col)].width = 15
        
        # Add sample data
        sample_data = [
            ['EMP001', 'John', 'Doe', 'john.doe@company.com', 'A', 
             'Operator', 'Production', '2020-01-15', '555-0001',
             'Jane Doe (555-0002)', 'Forklift, Safety', 'No'],
            ['EMP002', 'Jane', 'Smith', 'jane.smith@company.com', 'B',
             'Technician', 'Maintenance', '2019-06-01', '555-0003',
             'John Smith (555-0004)', 'Electrical, HVAC', 'No']
        ]
        
        for row_num, data in enumerate(sample_data, 2):
            for col_num, value in enumerate(data, 1):
                ws.cell(row=row_num, column=col_num, value=value)
        
        # Add instructions sheet
        ws2 = wb.create_sheet('Instructions')
        instructions = [
            ['Instructions for Employee Upload'],
            [''],
            ['1. Fill in employee information in the Employee Data sheet'],
            ['2. Required fields: Employee ID, First Name, Last Name, Crew'],
            ['3. Employee ID must be unique for each employee'],
            ['4. Crew must be one of: A, B, C, or D'],
            ['5. Email is optional but recommended for login access'],
            ['6. Hire Date format: YYYY-MM-DD'],
            ['7. Skills should be comma-separated (e.g., "Forklift, Safety")'],
            ['8. Is Supervisor should be "Yes" or "No"'],
            [''],
            ['Default password for new employees: changeme123'],
            [''],
            ['Save the file and upload it to the system']
        ]
        
        for row_num, instruction in enumerate(instructions, 1):
            if instruction:
                ws2.cell(row=row_num, column=1, value=instruction[0])
                if row_num == 1:
                    ws2.cell(row=row_num, column=1).font = Font(bold=True, size=14)
        
        ws2.column_dimensions['A'].width = 80
        
        # Save to BytesIO
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'employee_upload_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
        )
        
    except Exception as e:
        logger.error(f"Error creating employee template: {e}")
        flash('Error creating template. Please try again.', 'error')
        return redirect(url_for('employee_import.upload_employees'))

@employee_import_bp.route('/download-overtime-template')
@login_required
@supervisor_required
def download_overtime_template():
    """Download Excel template for overtime upload"""
    try:
        wb = Workbook()
        ws = wb.active
        ws.title = 'Overtime Data'
        
        # Create headers
        headers = ['Employee ID'] + [f'Week {i}' for i in range(1, 14)]
        
        # Style headers
        header_font = Font(bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='366092', end_color='366092', fill_type='solid')
        
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            ws.column_dimensions[get_column_letter(col)].width = 12
        
        # Add sample data
        sample_employees = ['EMP001', 'EMP002', 'EMP003']
        for row_num, emp_id in enumerate(sample_employees, 2):
            ws.cell(row=row_num, column=1, value=emp_id)
            for week_col in range(2, 15):
                ws.cell(row=row_num, column=week_col, value=40)
        
        # Add instructions sheet
        ws2 = wb.create_sheet('Instructions')
        instructions = [
            ['Overtime History Upload Instructions'],
            [''],
            ['1. Enter Employee IDs in the first column'],
            ['2. Enter total hours worked for each of the past 13 weeks'],
            ['3. Week 1 is the most recent week, Week 13 is the oldest'],
            ['4. Enter total hours (regular + overtime)'],
            ['5. System will calculate overtime as hours over 40'],
            [''],
            ['Example: If an employee worked 45 hours, enter 45'],
            ['The system will record 40 regular hours and 5 overtime hours']
        ]
        
        for row_num, instruction in enumerate(instructions, 1):
            if instruction:
                ws2.cell(row=row_num, column=1, value=instruction[0])
                if row_num == 1:
                    ws2.cell(row=row_num, column=1).font = Font(bold=True, size=14)
        
        ws2.column_dimensions['A'].width = 70
        
        # Save to BytesIO
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'overtime_upload_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
        )
        
    except Exception as e:
        logger.error(f"Error creating overtime template: {e}")
        flash('Error creating template. Please try again.', 'error')
        return redirect(url_for('employee_import.upload_employees'))

# ==========================================
# ADDITIONAL ROUTES
# ==========================================

@employee_import_bp.route('/upload-history')
@login_required
@supervisor_required
def upload_history():
    """View upload history"""
    try:
        page = request.args.get('page', 1, type=int)
        uploads = FileUpload.query.order_by(
            FileUpload.uploaded_at.desc()
        ).paginate(page=page, per_page=20, error_out=False)
        
        # Try to render template, fall back to simple list
        try:
            return render_template('upload_history.html', uploads=uploads)
        except:
            # Simple fallback
            html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Upload History</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            </head>
            <body>
                <div class="container mt-5">
                    <h2>Upload History</h2>
                    <a href="/upload-employees" class="btn btn-primary mb-3">Back to Upload</a>
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Filename</th>
                                <th>Type</th>
                                <th>Status</th>
                                <th>Processed</th>
                                <th>Date</th>
                            </tr>
                        </thead>
                        <tbody>
            """
            
            for upload in uploads.items:
                status_class = 'success' if upload.status == 'completed' else 'danger'
                date_str = upload.uploaded_at.strftime('%Y-%m-%d %H:%M') if upload.uploaded_at else 'Unknown'
                html += f"""
                    <tr>
                        <td>{upload.filename}</td>
                        <td>{upload.upload_type or 'Unknown'}</td>
                        <td><span class="badge bg-{status_class}">{upload.status or 'Unknown'}</span></td>
                        <td>{upload.records_processed or 0}</td>
                        <td>{date_str}</td>
                    </tr>
                """
            
            html += """
                        </tbody>
                    </table>
                </div>
            </body>
            </html>
            """
            return make_response(html)
            
    except Exception as e:
        logger.error(f"Error in upload_history: {e}")
        flash('Error loading upload history.', 'error')
        return redirect(url_for('employee_import.upload_employees'))

@employee_import_bp.route('/upload-overtime')
@login_required
@supervisor_required
def upload_overtime():
    """Dedicated overtime upload page"""
    return redirect(url_for('employee_import.upload_employees'))

@employee_import_bp.route('/export-employees')
@login_required
@supervisor_required
def export_employees():
    """Export current employee data to Excel"""
    try:
        employees = Employee.query.filter_by(is_active=True).all()
        
        if not employees:
            flash('No employees found to export.', 'warning')
            return redirect(url_for('employee_import.upload_employees'))
        
        # Create workbook
        wb = Workbook()
        ws = wb.active
        ws.title = 'Employee Data'
        
        # Headers
        headers = [
            'Employee ID', 'First Name', 'Last Name', 'Email', 'Crew',
            'Position', 'Department', 'Hire Date', 'Phone', 'Is Supervisor'
        ]
        
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = Font(bold=True)
        
        # Employee data
        for row_num, emp in enumerate(employees, 2):
            # Split name into first and last
            name_parts = emp.name.split(' ', 1) if emp.name else ['', '']
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ''
            
            ws.cell(row=row_num, column=1, value=emp.employee_id)
            ws.cell(row=row_num, column=2, value=first_name)
            ws.cell(row=row_num, column=3, value=last_name)
            ws.cell(row=row_num, column=4, value=emp.email)
            ws.cell(row=row_num, column=5, value=emp.crew)
            ws.cell(row=row_num, column=6, value=emp.position.name if emp.position else '')
            ws.cell(row=row_num, column=7, value=emp.department)
            ws.cell(row=row_num, column=8, value=emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '')
            ws.cell(row=row_num, column=9, value=emp.phone)
            ws.cell(row=row_num, column=10, value='Yes' if emp.is_supervisor else 'No')
        
        # Save to BytesIO
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'employee_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
        
    except Exception as e:
        logger.error(f"Error exporting employees: {e}")
        flash('Error exporting employee data.', 'error')
        return redirect(url_for('employee_import.upload_employees'))

@employee_import_bp.route('/test-upload-route')
def test_upload_route():
    """Test route to verify blueprint is loaded"""
    return jsonify({
        'status': 'Employee import blueprint is working!',
        'routes_available': [
            '/upload-employees',
            '/validate-upload',
            '/download-employee-template',
            '/download-overtime-template',
            '/upload-history',
            '/export-employees'
        ],
        'authenticated': current_user.is_authenticated,
        'is_supervisor': current_user.is_supervisor if current_user.is_authenticated else False,
        'upload_folder': current_app.config.get('UPLOAD_FOLDER'),
        'timestamp': datetime.now().isoformat()
    })

# Log successful blueprint loading
logger.info("Employee import blueprint loaded successfully with all routes")
