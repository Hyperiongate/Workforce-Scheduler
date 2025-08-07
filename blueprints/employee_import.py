# blueprints/employee_import.py - COMPLETE FILE WITH ALL ROUTES AND FIXES
"""
Employee Import Blueprint - Complete implementation with all fixes
Handles all Excel upload/download functionality
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, current_app, session
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db, Employee, Position, Skill, OvertimeHistory, FileUpload
from datetime import datetime, date, timedelta
from sqlalchemy import func, or_
import pandas as pd
import os
import io
import re
import random
import string
import logging

# Set up logging
logger = logging.getLogger(__name__)

# Create blueprint
employee_import_bp = Blueprint('employee_import', __name__)

# Helper functions
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

# Main upload route
@employee_import_bp.route('/upload-employees', methods=['GET', 'POST'])
@login_required
def upload_employees():
    """Main employee upload page with enhanced UI"""
    if not current_user.is_supervisor:
        flash('Only supervisors can upload employee data', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    if request.method == 'POST':
        # Handle file upload
        if 'file' not in request.files:
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            try:
                # Save file
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_{filename}"
                
                upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)
                    
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                
                # Get upload options
                upload_type = request.form.get('upload_type', 'employee')
                replace_all = request.form.get('replace_all', 'false') == 'true'
                validate_only = request.form.get('validate_only', 'false') == 'true'
                
                # Process based on upload type
                if upload_type == 'employee':
                    result = process_employee_upload(filepath, replace_all, validate_only)
                elif upload_type == 'overtime':
                    result = process_overtime_upload(filepath, replace_all)
                elif upload_type == 'bulk_update':
                    result = process_bulk_update(filepath)
                else:
                    flash('Invalid upload type', 'danger')
                    return redirect(request.url)
                
                # Handle results
                if result['success']:
                    flash(result['message'], 'success')
                    if result.get('credentials_file'):
                        session['credentials_file'] = result['credentials_file']
                        flash('Employee credentials have been generated. Download them below.', 'info')
                else:
                    flash(result['message'], 'danger')
                    if result.get('errors'):
                        for error in result['errors'][:10]:  # Show first 10 errors
                            flash(error, 'warning')
                
                return redirect(url_for('employee_import.upload_employees'))
                
            except Exception as e:
                logger.error(f"Upload error: {str(e)}")
                flash(f'Error processing file: {str(e)}', 'danger')
                return redirect(request.url)
        else:
            flash('Invalid file type. Please upload an Excel file.', 'danger')
            return redirect(request.url)
    
    # GET request - render the upload page
    recent_uploads = FileUpload.query.filter_by(
        uploaded_by_id=current_user.id
    ).order_by(FileUpload.upload_date.desc()).limit(5).all()
    
    # Get statistics for the page
    employee_count = Employee.query.filter_by(is_active=True).count()
    crew_counts = db.session.query(
        Employee.crew, func.count(Employee.id)
    ).filter(Employee.is_active == True).group_by(Employee.crew).all()
    
    crew_data = {crew: count for crew, count in crew_counts}
    
    stats = {
        'employee_count': employee_count,
        'crew_a_count': crew_data.get('A', 0),
        'crew_b_count': crew_data.get('B', 0),
        'crew_c_count': crew_data.get('C', 0),
        'crew_d_count': crew_data.get('D', 0),
        'last_upload_date': recent_uploads[0].upload_date.strftime('%Y-%m-%d %H:%M') if recent_uploads else 'Never'
    }
    
    return render_template('upload_employees_enhanced.html', 
                         recent_uploads=recent_uploads,
                         **stats)

# Upload processing functions
def process_employee_upload(filepath, replace_all=False, validate_only=False):
    """Process employee data upload"""
    try:
        # Read the Excel file
        df = pd.read_excel(filepath, sheet_name=0)
        
        # Validate the data
        errors = validate_employee_data(df)
        if errors:
            return {'success': False, 'message': 'Validation failed', 'errors': errors}
        
        if validate_only:
            return {'success': True, 'message': f'Validation passed! {len(df)} employees ready to import.'}
        
        # Record the upload
        file_upload = FileUpload(
            filename=os.path.basename(filepath),
            file_type='employee_import',
            file_size=os.path.getsize(filepath),
            uploaded_by_id=current_user.id,
            status='processing'
        )
        db.session.add(file_upload)
        db.session.flush()
        
        # Process employees
        if replace_all:
            # Delete existing employees (except current user)
            Employee.query.filter(Employee.id != current_user.id).delete()
            db.session.commit()
        
        created_count = 0
        updated_count = 0
        credentials = []
        
        for idx, row in df.iterrows():
            try:
                employee_id = str(row['Employee ID']).strip()
                
                # Check if employee exists
                existing = Employee.query.filter_by(employee_id=employee_id).first()
                
                if existing:
                    # Update existing employee
                    existing.first_name = row['First Name']
                    existing.last_name = row['Last Name']
                    existing.email = row['Email'].lower()
                    existing.crew = row['Crew']
                    existing.position = row['Position']
                    existing.department = row.get('Department', 'Production')
                    updated_count += 1
                else:
                    # Create new employee
                    username = generate_username(row['First Name'], row['Last Name'])
                    temp_password = generate_temp_password()
                    
                    employee = Employee(
                        employee_id=employee_id,
                        username=username,
                        email=row['Email'].lower(),
                        first_name=row['First Name'],
                        last_name=row['Last Name'],
                        crew=row['Crew'],
                        position=row['Position'],
                        department=row.get('Department', 'Production'),
                        hire_date=pd.to_datetime(row.get('Hire Date', datetime.now())).date(),
                        is_active=True,
                        is_supervisor=row.get('Position', '').lower() == 'supervisor'
                    )
                    employee.set_password(temp_password)
                    
                    db.session.add(employee)
                    created_count += 1
                    
                    credentials.append({
                        'Employee ID': employee_id,
                        'Name': f"{row['First Name']} {row['Last Name']}",
                        'Username': username,
                        'Temporary Password': temp_password,
                        'Email': row['Email']
                    })
                    
            except Exception as e:
                logger.error(f"Error processing row {idx}: {str(e)}")
                continue
        
        db.session.commit()
        
        # Update file upload record
        file_upload.status = 'completed'
        file_upload.records_processed = len(df)
        file_upload.records_created = created_count
        file_upload.records_updated = updated_count
        db.session.commit()
        
        # Generate credentials file if new employees created
        credentials_file = None
        if credentials:
            credentials_file = save_credentials_file(credentials)
        
        message = f"Successfully processed {len(df)} employees. "
        message += f"Created: {created_count}, Updated: {updated_count}"
        
        return {
            'success': True,
            'message': message,
            'created': created_count,
            'updated': updated_count,
            'credentials_file': credentials_file
        }
        
    except Exception as e:
        logger.error(f"Employee upload failed: {str(e)}")
        return {'success': False, 'message': str(e)}

def process_overtime_upload(filepath, replace_all=True):
    """Process overtime history upload"""
    try:
        df = pd.read_excel(filepath)
        
        # Validate
        errors = validate_overtime_data(df)
        if errors:
            return {'success': False, 'message': 'Validation failed', 'errors': errors}
        
        # Record upload
        file_upload = FileUpload(
            filename=os.path.basename(filepath),
            file_type='overtime_import',
            file_size=os.path.getsize(filepath),
            uploaded_by_id=current_user.id,
            status='processing'
        )
        db.session.add(file_upload)
        db.session.flush()
        
        if replace_all:
            OvertimeHistory.query.delete()
            db.session.commit()
        
        # Get week columns
        week_columns = [col for col in df.columns if col.startswith('Week')]
        created_count = 0
        
        for idx, row in df.iterrows():
            employee_id = str(row['Employee ID']).strip()
            employee = Employee.query.filter_by(employee_id=employee_id).first()
            
            if not employee:
                continue
                
            for week_col in week_columns:
                try:
                    week_date = pd.to_datetime(week_col.replace('Week ', '')).date()
                    hours = float(row[week_col]) if pd.notna(row[week_col]) else 0
                    
                    if hours > 0:
                        ot_record = OvertimeHistory(
                            employee_id=employee.id,
                            week_start_date=week_date,
                            hours_worked=hours
                        )
                        db.session.add(ot_record)
                        created_count += 1
                except:
                    continue
        
        db.session.commit()
        
        # Update file upload
        file_upload.status = 'completed'
        file_upload.records_processed = len(df) * len(week_columns)
        file_upload.records_created = created_count
        db.session.commit()
        
        return {
            'success': True,
            'message': f'Successfully imported {created_count} overtime records for {len(df)} employees'
        }
        
    except Exception as e:
        logger.error(f"Overtime upload failed: {str(e)}")
        return {'success': False, 'message': str(e)}

def process_bulk_update(filepath):
    """Process bulk employee updates"""
    try:
        df = pd.read_excel(filepath)
        
        # Record upload
        file_upload = FileUpload(
            filename=os.path.basename(filepath),
            file_type='bulk_update',
            file_size=os.path.getsize(filepath),
            uploaded_by_id=current_user.id,
            status='processing'
        )
        db.session.add(file_upload)
        db.session.flush()
        
        updated_count = 0
        errors = []
        
        for idx, row in df.iterrows():
            try:
                employee_id = str(row['Employee ID']).strip()
                employee = Employee.query.filter_by(employee_id=employee_id).first()
                
                if not employee:
                    errors.append(f"Employee {employee_id} not found")
                    continue
                
                # Update fields if provided
                if pd.notna(row.get('Crew')) and row['Crew']:
                    employee.crew = row['Crew']
                if pd.notna(row.get('Position')) and row['Position']:
                    employee.position = row['Position']
                if pd.notna(row.get('Department')) and row['Department']:
                    employee.department = row['Department']
                if pd.notna(row.get('Email')) and row['Email']:
                    employee.email = row['Email'].lower()
                    
                updated_count += 1
                
            except Exception as e:
                errors.append(f"Error updating row {idx + 2}: {str(e)}")
                
        db.session.commit()
        
        # Update file upload
        file_upload.status = 'completed' if not errors else 'completed_with_errors'
        file_upload.records_processed = len(df)
        file_upload.records_updated = updated_count
        db.session.commit()
        
        message = f"Updated {updated_count} employees"
        if errors:
            message += f" with {len(errors)} errors"
            
        return {
            'success': updated_count > 0,
            'message': message,
            'errors': errors[:10]  # First 10 errors
        }
        
    except Exception as e:
        logger.error(f"Bulk update failed: {str(e)}")
        return {'success': False, 'message': str(e)}

# Validation functions
def validate_employee_data(df):
    """Validate employee data from DataFrame"""
    errors = []
    
    # Required columns
    required_columns = ['Employee ID', 'First Name', 'Last Name', 'Email', 'Crew', 'Position']
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")
        return errors
    
    # Check for duplicates
    duplicates = df[df.duplicated('Employee ID', keep=False)]['Employee ID'].unique()
    if len(duplicates) > 0:
        errors.append(f"Duplicate Employee IDs: {', '.join(map(str, duplicates[:5]))}")
    
    # Validate each row
    for idx, row in df.iterrows():
        row_num = idx + 2
        
        # Check required fields
        for col in required_columns:
            if pd.isna(row[col]) or str(row[col]).strip() == '':
                errors.append(f"Row {row_num}: {col} is required")
                
        # Validate email
        if pd.notna(row['Email']):
            email = str(row['Email']).strip()
            if not is_valid_email(email):
                errors.append(f"Row {row_num}: Invalid email format")
                
        # Validate crew
        if pd.notna(row['Crew']):
            crew = str(row['Crew']).strip().upper()
            if crew not in ['A', 'B', 'C', 'D']:
                errors.append(f"Row {row_num}: Invalid crew '{crew}'")
    
    return errors[:20]  # Return first 20 errors

def validate_overtime_data(df):
    """Validate overtime data"""
    errors = []
    
    if 'Employee ID' not in df.columns:
        errors.append("Missing Employee ID column")
        return errors
    
    # Check for week columns
    week_columns = [col for col in df.columns if col.startswith('Week')]
    if len(week_columns) != 13:
        errors.append(f"Expected 13 week columns, found {len(week_columns)}")
    
    # Validate employee IDs exist
    for idx, row in df.iterrows():
        employee_id = str(row['Employee ID']).strip()
        if not Employee.query.filter_by(employee_id=employee_id).first():
            errors.append(f'Row {idx + 2}: Employee {employee_id} not found')
    
    return errors

def validate_employee_data_detailed(df):
    """Detailed validation for employee data with specific error messages"""
    errors = []
    warnings = []
    
    # Check sheet name if possible
    if hasattr(df, 'sheet_name') and df.sheet_name != 'Employee Data':
        warnings.append("Sheet name should be 'Employee Data' for best compatibility")
    
    # Required columns
    required_columns = ['Employee ID', 'First Name', 'Last Name', 'Email', 'Crew', 'Position']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        errors.append(f"Missing required columns: {', '.join(missing_columns)}")
        return errors, warnings
    
    # Check for duplicate Employee IDs
    duplicate_ids = df[df.duplicated('Employee ID', keep=False)]['Employee ID'].unique()
    if len(duplicate_ids) > 0:
        errors.append(f"Duplicate Employee IDs found: {', '.join(map(str, duplicate_ids[:5]))}")
    
    # Row-by-row validation
    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel row number (1-indexed + header)
        
        # Check required fields
        if pd.isna(row.get('Employee ID')) or str(row.get('Employee ID')).strip() == '':
            errors.append(f"Row {row_num}: Employee ID is required")
            
        if pd.isna(row.get('First Name')) or str(row.get('First Name')).strip() == '':
            errors.append(f"Row {row_num}: First Name is required")
            
        if pd.isna(row.get('Last Name')) or str(row.get('Last Name')).strip() == '':
            errors.append(f"Row {row_num}: Last Name is required")
            
        # Validate email format
        email = str(row.get('Email', '')).strip()
        if email and not is_valid_email(email):
            errors.append(f"Row {row_num}: Invalid email format: {email}")
            
        # Validate crew
        crew = str(row.get('Crew', '')).strip().upper()
        if crew and crew not in ['A', 'B', 'C', 'D']:
            errors.append(f"Row {row_num}: Invalid crew '{crew}'. Must be A, B, C, or D")
            
        # Stop after 20 errors to avoid overwhelming
        if len(errors) >= 20:
            errors.append(f"... and more errors. Fix these first.")
            break
    
    # Check for existing employees (warning only)
    if not errors:
        existing_ids = []
        for emp_id in df['Employee ID'].unique():
            if Employee.query.filter_by(employee_id=str(emp_id)).first():
                existing_ids.append(str(emp_id))
        
        if existing_ids:
            warnings.append(f"The following Employee IDs already exist and will be updated: {', '.join(existing_ids[:5])}")
            if len(existing_ids) > 5:
                warnings.append(f"... and {len(existing_ids) - 5} more")
    
    return errors, warnings

def validate_overtime_data_detailed(df):
    """Detailed validation for overtime data"""
    errors = []
    warnings = []
    
    # Check for Employee ID column
    if 'Employee ID' not in df.columns:
        errors.append("Missing required column: Employee ID")
        return errors, warnings
    
    # Check for week columns (should have exactly 13)
    week_columns = [col for col in df.columns if col.startswith('Week') or 'week' in col.lower()]
    if len(week_columns) != 13:
        errors.append(f"Expected 13 week columns, found {len(week_columns)}")
        if len(week_columns) > 0:
            errors.append(f"Week columns found: {', '.join(week_columns[:5])}")
    
    # Validate employee IDs exist
    missing_employees = []
    for idx, row in df.iterrows():
        emp_id = str(row.get('Employee ID', '')).strip()
        if emp_id:
            employee = Employee.query.filter_by(employee_id=emp_id).first()
            if not employee:
                missing_employees.append(emp_id)
    
    if missing_employees:
        errors.append(f"Employee IDs not found in system: {', '.join(missing_employees[:5])}")
        if len(missing_employees) > 5:
            errors.append(f"... and {len(missing_employees) - 5} more")
    
    # Validate overtime hours are numeric
    for col in week_columns:
        non_numeric = df[~pd.to_numeric(df[col], errors='coerce').notna() & df[col].notna()]
        if len(non_numeric) > 0:
            errors.append(f"Non-numeric values found in {col}")
    
    return errors, warnings

def validate_bulk_update_data(df):
    """Validate bulk update data"""
    errors = []
    warnings = []
    
    if 'Employee ID' not in df.columns:
        errors.append("Missing required column: Employee ID")
        return errors, warnings
    
    # Check that at least one updateable field exists
    updateable_fields = ['Crew', 'Position', 'Department', 'Shift', 'Email']
    found_fields = [field for field in updateable_fields if field in df.columns]
    
    if not found_fields:
        errors.append(f"No updateable fields found. Expected at least one of: {', '.join(updateable_fields)}")
    
    # Validate that employees exist
    for idx, row in df.iterrows():
        emp_id = str(row.get('Employee ID', '')).strip()
        if emp_id and not Employee.query.filter_by(employee_id=emp_id).first():
            errors.append(f"Row {idx + 2}: Employee ID '{emp_id}' not found")
            
        # Stop after 20 errors
        if len(errors) >= 20:
            errors.append("... and more errors. Fix these first.")
            break
    
    return errors, warnings

def save_credentials_file(credentials):
    """Save credentials to file for download"""
    df = pd.DataFrame(credentials)
    
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
    
    filename = f'credentials_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    filepath = os.path.join(upload_folder, filename)
    
    df.to_excel(filepath, index=False)
    
    # Store filename in session for download
    session['credentials_file'] = filename
    
    return filename

# VALIDATION ENDPOINT - THE MISSING ROUTE
@employee_import_bp.route('/validate-upload', methods=['POST'])
@login_required
def validate_upload():
    """Validate uploaded file before processing - COMPLETE IMPLEMENTATION"""
    
    # STEP 1: Permission Check
    if not current_user.is_supervisor:
        return jsonify({
            'success': False, 
            'error': 'Unauthorized - Supervisor access required',
            'total_errors': 1
        }), 403
    
    # STEP 2: File Presence Check
    if 'file' not in request.files:
        return jsonify({
            'success': False, 
            'error': 'No file provided',
            'total_errors': 1
        }), 400
    
    file = request.files['file']
    
    # STEP 3: File Validation
    if not file or file.filename == '':
        return jsonify({
            'success': False, 
            'error': 'No file selected',
            'total_errors': 1
        }), 400
    
    # STEP 4: File Extension Check
    if not allowed_file(file.filename):
        return jsonify({
            'success': False, 
            'error': 'Invalid file type. Please upload an Excel file (.xlsx or .xls)',
            'total_errors': 1
        }), 400
    
    # STEP 5: Get Upload Type (with default)
    upload_type = request.form.get('type', request.form.get('upload_type', 'employee'))
    
    try:
        # STEP 6: Read Excel File
        df = pd.read_excel(file)
        
        # STEP 7: Check if DataFrame is empty
        if df.empty:
            return jsonify({
                'success': False,
                'error': 'The uploaded file contains no data',
                'total_errors': 1,
                'row_count': 0
            })
        
        # STEP 8: Type-Specific Validation
        errors = []
        warnings = []
        preview_data = []
        
        if upload_type in ['employee', 'employees']:
            # Validate employee data
            errors, warnings = validate_employee_data_detailed(df)
            if not errors:
                # Prepare preview (first 5 rows)
                preview_data = df.head(5).fillna('').to_dict('records')
                
        elif upload_type == 'overtime':
            # Validate overtime data
            errors, warnings = validate_overtime_data_detailed(df)
            if not errors:
                preview_data = df.head(5).fillna('').to_dict('records')
                
        elif upload_type == 'bulk_update':
            # Validate bulk update data
            errors, warnings = validate_bulk_update_data(df)
            if not errors:
                preview_data = df.head(5).fillna('').to_dict('records')
                
        else:
            errors.append(f'Invalid upload type: {upload_type}')
        
        # STEP 9: Prepare Response
        response_data = {
            'success': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'row_count': len(df),
            'total_errors': len(errors),
            'total_warnings': len(warnings),
            'preview': preview_data,
            'columns': list(df.columns) if not errors else []
        }
        
        return jsonify(response_data)
        
    except pd.errors.EmptyDataError:
        return jsonify({
            'success': False,
            'error': 'The file appears to be empty or corrupted',
            'total_errors': 1
        })
    except Exception as e:
        # Log the error for debugging
        current_app.logger.error(f"Validation error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error reading file: {str(e)}',
            'total_errors': 1
        })

# Upload overtime route
@employee_import_bp.route('/upload-overtime', methods=['GET', 'POST'])
@login_required
def upload_overtime():
    """Overtime history upload page"""
    if not current_user.is_supervisor:
        flash('Only supervisors can upload overtime data', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    if request.method == 'POST':
        # Process the upload
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
            
        file = request.files['file']
        if file and allowed_file(file.filename):
            try:
                # Save file
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"overtime_{timestamp}_{filename}"
                
                upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)
                    
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                
                # Process
                replace_all = request.form.get('replace_all', 'true') == 'true'
                result = process_overtime_upload(filepath, replace_all)
                
                if result['success']:
                    return jsonify({
                        'success': True,
                        'message': result['message']
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': result['message'],
                        'errors': result.get('errors', [])
                    }), 400
                    
            except Exception as e:
                logger.error(f"Overtime upload error: {str(e)}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
    
    # GET request - calculate statistics
    total_ot = db.session.query(func.sum(OvertimeHistory.hours_worked)).scalar() or 0
    employee_count = Employee.query.filter_by(is_active=True).count()
    avg_ot = total_ot / employee_count if employee_count > 0 else 0
    
    # Count employees missing OT data
    employees_with_ot = db.session.query(OvertimeHistory.employee_id).distinct().count()
    missing_ot_count = employee_count - employees_with_ot
    
    # OT distribution
    ot_ranges = db.session.query(
        func.case(
            (func.sum(OvertimeHistory.hours_worked) <= 130, '0-10'),
            (func.sum(OvertimeHistory.hours_worked) <= 260, '10-20'),
            (func.sum(OvertimeHistory.hours_worked) <= 520, '20-40'),
            else_='40+'
        ).label('range'),
        func.count(OvertimeHistory.employee_id.distinct())
    ).group_by('range').all()
    
    ot_distribution = {r[0]: r[1] for r in ot_ranges}
    
    return render_template('upload_overtime.html',
                         total_ot_hours=int(total_ot),
                         avg_ot_hours=int(avg_ot),
                         missing_ot_count=missing_ot_count,
                         ot_0_10=ot_distribution.get('0-10', 0),
                         ot_10_20=ot_distribution.get('10-20', 0),
                         ot_20_40=ot_distribution.get('20-40', 0),
                         ot_40_plus=ot_distribution.get('40+', 0))

# Upload history route
@employee_import_bp.route('/upload-history')
@login_required
def upload_history():
    """View upload history"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    # Handle JSON request for AJAX
    if request.args.get('format') == 'json':
        file_type = request.args.get('file_type')
        query = FileUpload.query
        
        if file_type:
            query = query.filter_by(file_type=file_type)
            
        uploads = query.order_by(FileUpload.upload_date.desc()).limit(10).all()
        
        data = []
        for upload in uploads:
            data.append({
                'id': upload.id,
                'upload_date': upload.upload_date.isoformat(),
                'uploaded_by_name': f"{upload.uploaded_by.first_name} {upload.uploaded_by.last_name}",
                'records_processed': upload.records_processed,
                'status': upload.status,
                'total_hours': 0  # Calculate if needed
            })
            
        return jsonify(data)
    
    # Regular HTML request
    # Get filter parameters
    file_type = request.args.get('file_type')
    status = request.args.get('status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Build query
    query = FileUpload.query
    
    if file_type:
        query = query.filter_by(file_type=file_type)
    if status:
        query = query.filter_by(status=status)
    if start_date:
        query = query.filter(FileUpload.upload_date >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(FileUpload.upload_date <= datetime.strptime(end_date, '%Y-%m-%d'))
    
    # Order by date and get all uploads
    uploads = query.order_by(FileUpload.upload_date.desc()).all()
    
    return render_template('upload_history.html', uploads=uploads)

# Download template routes
@employee_import_bp.route('/download-employee-template')
@login_required
def download_employee_template():
    """Download employee upload template"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    # Create template data
    template_data = {
        'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
        'First Name': ['John', 'Jane', 'Bob'],
        'Last Name': ['Doe', 'Smith', 'Johnson'],
        'Email': ['john.doe@company.com', 'jane.smith@company.com', 'bob.johnson@company.com'],
        'Crew': ['A', 'B', 'C'],
        'Position': ['Operator', 'Lead Operator', 'Supervisor'],
        'Department': ['Production', 'Production', 'Management'],
        'Hire Date': ['2020-01-15', '2019-06-20', '2018-03-10']
    }
    
    df = pd.DataFrame(template_data)
    
    # Create Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Employee Data', index=False)
        
        # Add instructions sheet
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
                '- Department: Department name (defaults to Production)',
                '- Hire Date: Format YYYY-MM-DD',
                '',
                'Notes:',
                '- Do not modify column headers',
                '- Remove sample data before uploading',
                '- Usernames and passwords will be auto-generated'
            ]
        })
        instructions.to_excel(writer, sheet_name='Instructions', index=False, header=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'employee_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

@employee_import_bp.route('/download-overtime-template')
@login_required
def download_overtime_template():
    """Download overtime upload template"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    # Create template with 13 weeks
    template_data = {'Employee ID': ['EMP001', 'EMP002', 'EMP003']}
    
    # Add 13 week columns
    base_date = datetime.now() - timedelta(weeks=13)
    for i in range(13):
        week_date = base_date + timedelta(weeks=i)
        week_col = f"Week {week_date.strftime('%Y-%m-%d')}"
        template_data[week_col] = [8, 12, 0]  # Sample data
    
    df = pd.DataFrame(template_data)
    
    # Create Excel file
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Overtime History', index=False)
        
        # Add instructions
        instructions = pd.DataFrame({
            'Instructions': [
                'OVERTIME HISTORY UPLOAD TEMPLATE',
                '',
                'Instructions:',
                '1. Employee ID must match existing employees',
                '2. Enter overtime hours for each week',
                '3. Use 0 for weeks with no overtime',
                '4. Week columns must be named "Week YYYY-MM-DD"',
                '5. Upload covers exactly 13 weeks of history',
                '',
                'This data is used for:',
                '- Fair overtime distribution',
                '- Fatigue management',
                '- Historical reporting'
            ]
        })
        instructions.to_excel(writer, sheet_name='Instructions', index=False, header=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'overtime_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

@employee_import_bp.route('/download-bulk-update-template')
@login_required
def download_bulk_update_template():
    """Download bulk update template"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    # Create template
    template_data = {
        'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
        'Crew': ['B', '', 'D'],  # Some blanks to show optional
        'Position': ['', 'Lead Operator', ''],
        'Department': ['Maintenance', '', ''],
        'Email': ['', '', 'new.email@company.com']
    }
    
    df = pd.DataFrame(template_data)
    
    # Create Excel file
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Bulk Update', index=False)
        
        # Instructions
        instructions = pd.DataFrame({
            'Instructions': [
                'BULK UPDATE TEMPLATE',
                '',
                'Instructions:',
                '1. Employee ID is required and must match existing employees',
                '2. Only fill in fields you want to update',
                '3. Leave fields blank to keep current values',
                '4. Crew must be A, B, C, or D if specified',
                '',
                'Updateable Fields:',
                '- Crew: Employee crew assignment',
                '- Position: Job title',
                '- Department: Department name',
                '- Email: Employee email address'
            ]
        })
        instructions.to_excel(writer, sheet_name='Instructions', index=False, header=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'bulk_update_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

# Export current data
@employee_import_bp.route('/export-current-employees')
@login_required
def export_current_employees():
    """Export current employee data"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    # Get all employees
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.last_name).all()
    
    # Create DataFrame
    data = []
    for emp in employees:
        data.append({
            'Employee ID': emp.employee_id,
            'First Name': emp.first_name,
            'Last Name': emp.last_name,
            'Email': emp.email,
            'Crew': emp.crew or '',
            'Position': emp.position or '',
            'Department': emp.department or 'Production',
            'Hire Date': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else ''
        })
    
    df = pd.DataFrame(data)
    
    # Create Excel file
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Employee Data', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'employee_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    )

# Download credentials
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
    
    # Clear from session after download
    session.pop('credentials_file', None)
    
    return send_file(
        filepath,
        as_attachment=True,
        download_name=f'employee_credentials_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

# API endpoints
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
    
    # Build response data
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
    
    # Add type-specific details
    if upload.file_type == 'overtime_import' and upload.records_processed:
        # Calculate total OT hours if it's an overtime upload
        try:
            total_hours = OvertimeHistory.query.filter(
                OvertimeHistory.created_at >= upload.upload_date,
                OvertimeHistory.created_at <= upload.upload_date + timedelta(minutes=5)
            ).with_entities(func.sum(OvertimeHistory.hours_worked)).scalar()
            data['total_overtime_hours'] = float(total_hours) if total_hours else 0
        except:
            pass
    
    return jsonify(data)

@employee_import_bp.route('/download-upload-file/<int:upload_id>')
@login_required
def download_upload_file(upload_id):
    """Download original uploaded file"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    upload = FileUpload.query.get_or_404(upload_id)
    
    # Check if file still exists
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
    filepath = os.path.join(upload_folder, upload.filename)
    
    if not os.path.exists(filepath):
        flash('Original file no longer exists', 'warning')
        return redirect(url_for('employee_import.upload_history'))
    
    return send_file(filepath, as_attachment=True, download_name=upload.filename)

# Error handlers
@employee_import_bp.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@employee_import_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500
