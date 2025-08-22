# blueprints/employee_import.py
"""
Employee Import Blueprint - Complete Fixed Version
All template variables provided, all routes implemented, all edge cases handled
Fixed: Template name and parameter mismatches
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
from functools import wraps
import traceback

# Set up logging
logger = logging.getLogger(__name__)

# Create blueprint
employee_import_bp = Blueprint('employee_import', __name__)

# ==========================================
# DECORATOR
# ==========================================

def supervisor_required(f):
    """Decorator to require supervisor access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.is_supervisor:
            flash('Access denied. Supervisors only.', 'danger')
            return redirect(url_for('main.employee_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def get_employee_stats():
    """Get statistics for employee data with comprehensive error handling"""
    try:
        # Get total employees
        total_employees = Employee.query.filter_by(is_supervisor=False).count()
        
        # Get employees without overtime data
        employees_without_ot = Employee.query.filter(
            Employee.is_supervisor == False,
            ~Employee.overtime_histories.any()
        ).count()
        
        # Get crew distribution
        crew_counts = db.session.query(
            Employee.crew, 
            func.count(Employee.id)
        ).filter(
            Employee.is_supervisor == False
        ).group_by(Employee.crew).all()
        
        # Initialize crew dictionary
        crews = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'Unassigned': 0}
        
        # Populate crew counts
        for crew, count in crew_counts:
            if crew in ['A', 'B', 'C', 'D']:
                crews[crew] = count
            elif crew is None or crew == '':
                crews['Unassigned'] += count
            else:
                # Any other value goes to Unassigned
                crews['Unassigned'] += count
        
        return {
            'total_employees': total_employees,
            'employees_without_ot': employees_without_ot,
            'crews': crews
        }
    except Exception as e:
        logger.error(f"Error getting employee stats: {e}")
        # Always rollback on error
        try:
            db.session.rollback()
        except:
            pass
        return {
            'total_employees': 0,
            'employees_without_ot': 0,
            'crews': {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'Unassigned': 0}
        }

def get_recent_uploads(limit=5, upload_type=None):
    """Get recent file uploads with error handling"""
    try:
        query = FileUpload.query
        if upload_type:
            query = query.filter_by(upload_type=upload_type)
        
        uploads = query.order_by(FileUpload.uploaded_at.desc()).limit(limit).all()
        
        # Augment each upload for template compatibility
        for upload in uploads:
            augment_file_upload(upload)
        
        return uploads
    except Exception as e:
        logger.error(f"Error getting recent uploads: {e}")
        # Always rollback on error
        try:
            db.session.rollback()
        except:
            pass
        return []

def get_employees_without_accounts():
    """Count employees without login accounts"""
    try:
        count = Employee.query.filter(
            Employee.is_supervisor == False,
            or_(Employee.password_hash == None, Employee.password_hash == '')
        ).count()
        return count
    except Exception as e:
        logger.error(f"Error counting employees without accounts: {e}")
        # Always rollback on error
        try:
            db.session.rollback()
        except:
            pass
        return 0

def get_overtime_stats():
    """Get overtime statistics with error handling"""
    try:
        # Get total overtime hours using the correct field
        total_ot_hours = db.session.query(
            func.sum(OvertimeHistory.overtime_hours)
        ).scalar() or 0
        
        # Get count of employees with overtime
        employees_with_ot = db.session.query(
            func.count(func.distinct(OvertimeHistory.employee_id))
        ).scalar() or 0
        
        # Get recent overtime uploads
        recent_uploads = get_recent_uploads(limit=5, upload_type='overtime')
        
        return {
            'total_ot_hours': float(total_ot_hours),
            'employees_with_ot': employees_with_ot,
            'recent_uploads': recent_uploads
        }
    except Exception as e:
        logger.error(f"Error getting overtime stats: {e}")
        # Always rollback on error
        try:
            db.session.rollback()
        except:
            pass
        return {
            'total_ot_hours': 0,
            'employees_with_ot': 0,
            'recent_uploads': []
        }

def augment_file_upload(upload):
    """Add template-expected properties to FileUpload objects"""
    if upload:
        # Add aliases for template compatibility
        upload.upload_date = upload.uploaded_at
        upload.file_type = upload.upload_type
        
        # Calculate computed properties
        if upload.successful_records is not None and upload.failed_records is not None:
            upload.records_processed = upload.successful_records + upload.failed_records
        else:
            upload.records_processed = 0
        
        upload.records_created = upload.successful_records or 0
        upload.records_updated = 0  # We don't track this separately yet
        
        # Ensure status is never None
        if not upload.status:
            upload.status = 'completed'
    
    return upload

# ==========================================
# MAIN UPLOAD ROUTES
# ==========================================

@employee_import_bp.route('/upload-employees')
@login_required
@supervisor_required
def upload_employees():
    """Upload employees page with all required template variables"""
    try:
        # Get all statistics
        stats = get_employee_stats()
        recent_uploads = get_recent_uploads()
        employees_without_accounts = get_employees_without_accounts()
        
        # Prepare crew distribution for the template
        # The template expects it as a dictionary
        crew_distribution = stats['crews']
        
        # Check if account creation is available
        account_creation_available = True  # Set based on your business logic
        
        # FIXED: Use the correct template name
        return render_template('upload_employees_enhanced.html',
                             recent_uploads=recent_uploads,
                             stats=stats,
                             crew_distribution=crew_distribution,
                             total_employees=stats['total_employees'],
                             employees_without_accounts=employees_without_accounts,
                             account_creation_available=account_creation_available)
    
    except Exception as e:
        logger.error(f"Error in upload_employees route: {e}")
        flash('An error occurred while loading the page. Please try again.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@employee_import_bp.route('/upload-employees', methods=['POST'])
@login_required
@supervisor_required
def upload_employees_post():
    """Handle the actual file upload"""
    try:
        # Check if file was uploaded
        if 'file' not in request.files:
            flash('No file selected', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)
        
        # Check file extension
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash('Invalid file type. Please upload an Excel file (.xlsx or .xls)', 'error')
            return redirect(request.url)
        
        # Get form data
        upload_type = request.form.get('upload_type', 'employee')
        mode = request.form.get('mode', 'replace')
        
        # Save file temporarily
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        
        # Ensure upload folder exists
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
        os.makedirs(upload_folder, exist_ok=True)
        
        filepath = os.path.join(upload_folder, filename)
        
        # Save the file
        file.save(filepath)
        
        # Create upload record
        file_upload = FileUpload(
            filename=filename,
            upload_type=upload_type,
            uploaded_by_id=current_user.id,
            uploaded_at=datetime.utcnow(),
            status='processing'
        )
        db.session.add(file_upload)
        db.session.commit()
        
        try:
            # Read the Excel file
            df = pd.read_excel(filepath)
            
            # Process based on upload type
            if upload_type == 'employee':
                # Validate first
                validation_result = validate_employee_data(df)
                
                if not validation_result.get('success'):
                    file_upload.status = 'failed'
                    file_upload.error_details = validation_result
                    db.session.commit()
                    
                    flash('Validation failed. Please check the errors below:', 'error')
                    for error in validation_result.get('errors', [])[:10]:
                        flash(error, 'error')
                    
                    return redirect(url_for('employee_import.upload_employees'))
                
                # Process the data
                result = process_employee_data(df, mode, file_upload)
                
                if result.get('success'):
                    flash(f"Successfully uploaded {result.get('successful', 0)} employees!", 'success')
                    if result.get('failed', 0) > 0:
                        flash(f"{result.get('failed', 0)} records failed to process", 'warning')
                else:
                    flash(f"Upload failed: {result.get('error', 'Unknown error')}", 'error')
                    
            elif upload_type == 'overtime':
                # Process overtime data
                result = process_overtime_data(df, mode, file_upload)
                
                if result.get('success'):
                    flash(f"Successfully uploaded overtime data for {result.get('successful', 0)} employees!", 'success')
                else:
                    flash(f"Upload failed: {result.get('error', 'Unknown error')}", 'error')
                    
            else:
                flash('Invalid upload type', 'error')
                
        except Exception as e:
            logger.error(f"Error processing file: {e}", exc_info=True)
            file_upload.status = 'failed'
            file_upload.error_details = {'error': str(e)}
            db.session.commit()
            flash(f'Error processing file: {str(e)}', 'error')
            
        finally:
            # Clean up the temporary file
            try:
                os.remove(filepath)
            except:
                pass
        
        return redirect(url_for('employee_import.upload_employees'))
        
    except Exception as e:
        logger.error(f"Error in upload_employees_post: {e}", exc_info=True)
        flash('An unexpected error occurred. Please try again.', 'error')
        return redirect(url_for('employee_import.upload_employees'))

@employee_import_bp.route('/upload-overtime')
@login_required
@supervisor_required
def upload_overtime():
    """Upload overtime history page"""
    try:
        # Get overtime statistics as a dict
        stats = get_overtime_stats()
        
        return render_template('upload_overtime.html', stats=stats)
    
    except Exception as e:
        logger.error(f"Error in upload_overtime route: {e}")
        flash('An error occurred while loading the page. Please try again.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@employee_import_bp.route('/upload-history')
@login_required
@supervisor_required
def upload_history():
    """View upload history with filtering"""
    try:
        # Get filter parameters
        file_type = request.args.get('file_type', '')
        status = request.args.get('status', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        
        # Build query
        query = FileUpload.query
        
        # Apply filters
        if file_type:
            query = query.filter_by(upload_type=file_type)
        if status:
            query = query.filter_by(status=status)
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(FileUpload.uploaded_at >= start_dt)
            except ValueError:
                logger.warning(f"Invalid start date format: {start_date}")
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(FileUpload.uploaded_at < end_dt)
            except ValueError:
                logger.warning(f"Invalid end date format: {end_date}")
        
        # Get uploads with limit
        uploads = query.order_by(FileUpload.uploaded_at.desc()).limit(100).all()
        
        # Augment each upload for template compatibility
        for upload in uploads:
            augment_file_upload(upload)
        
        return render_template('upload_history.html', uploads=uploads)
    
    except Exception as e:
        logger.error(f"Error in upload_history route: {e}")
        flash('An error occurred while loading upload history.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# VALIDATION AND PROCESSING ROUTES
# ==========================================

@employee_import_bp.route('/validate-upload', methods=['POST'])
@login_required
@supervisor_required
def validate_upload():
    """Validate uploaded Excel file - FIXED parameter handling"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            return jsonify({'success': False, 'error': 'Invalid file type. Please upload Excel files only.'})
        
        # FIXED: Accept both 'type' and 'uploadType' for compatibility
        upload_type = request.form.get('uploadType') or request.form.get('type', 'employee')
        
        # Save current position for re-reading
        file.seek(0)
        
        try:
            # Read the Excel file
            df = pd.read_excel(file)
        except Exception as e:
            logger.error(f"Error reading Excel file: {e}")
            return jsonify({'success': False, 'error': f'Error reading Excel file: {str(e)}'})
        
        # Reset file position for potential re-use
        file.seek(0)
        
        # Validate based on upload type
        if upload_type == 'employee':
            result = validate_employee_data(df)
        elif upload_type == 'overtime':
            result = validate_overtime_data(df)
        elif upload_type == 'bulk':
            result = validate_bulk_update(df)
        else:
            result = {'success': False, 'error': 'Invalid upload type'}
        
        # Ensure result has all expected fields for the template
        if 'row_count' not in result and 'total_rows' in result:
            result['row_count'] = result['total_rows']
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Validation error: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': f'Validation error: {str(e)}'})

@employee_import_bp.route('/process-upload', methods=['POST'])
@login_required
@supervisor_required
def process_upload():
    """Process the uploaded file"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        file = request.files['file']
        upload_type = request.form.get('uploadType', 'employee')
        mode = request.form.get('mode', 'append')
        
        # Create file upload record
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
        file.seek(0)
        df = pd.read_excel(file)
        
        # Process based on type
        if upload_type == 'employee':
            result = process_employee_data(df, mode, file_upload)
        elif upload_type == 'overtime':
            result = process_overtime_data(df, mode, file_upload)
        elif upload_type == 'bulk':
            result = process_bulk_update(df, file_upload)
        else:
            result = {'success': False, 'error': 'Invalid upload type'}
        
        # Update file upload record
        file_upload.status = 'completed' if result.get('success') else 'failed'
        file_upload.total_records = result.get('total', 0)
        file_upload.successful_records = result.get('successful', 0)
        file_upload.failed_records = result.get('failed', 0)
        
        if not result.get('success'):
            file_upload.error_details = {'error': result.get('error', 'Unknown error')}
        elif result.get('errors'):
            file_upload.error_details = {'errors': result.get('errors', [])}
        
        db.session.commit()
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Process error: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

# ==========================================
# VALIDATION FUNCTIONS
# ==========================================

def validate_employee_data(df):
    """Validate employee data with comprehensive checks"""
    errors = []
    warnings = []
    
    # Check for empty dataframe
    if df.empty:
        return {'success': False, 'error': 'The uploaded file contains no data'}
    
    # Check required columns
    required_columns = ['Employee ID', 'First Name', 'Last Name', 'Email', 'Crew']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        return {
            'success': False,
            'error': f'Missing required columns: {", ".join(missing_columns)}'
        }
    
    # Track unique employee IDs
    seen_employee_ids = set()
    
    # Validate each row
    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel row number (header is row 1)
        
        # Check Employee ID
        emp_id = str(row.get('Employee ID', '')).strip()
        if not emp_id or emp_id == 'nan':
            errors.append(f"Row {row_num}: Missing Employee ID")
        elif emp_id in seen_employee_ids:
            errors.append(f"Row {row_num}: Duplicate Employee ID '{emp_id}'")
        else:
            seen_employee_ids.add(emp_id)
        
        # Check names
        first_name = str(row.get('First Name', '')).strip()
        last_name = str(row.get('Last Name', '')).strip()
        if not first_name or first_name == 'nan':
            errors.append(f"Row {row_num}: Missing First Name")
        if not last_name or last_name == 'nan':
            errors.append(f"Row {row_num}: Missing Last Name")
        
        # Check email
        email = str(row.get('Email', '')).strip()
        if not email or email == 'nan':
            errors.append(f"Row {row_num}: Missing Email")
        elif not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
            errors.append(f"Row {row_num}: Invalid email format '{email}'")
        
        # Check crew values
        crew = str(row.get('Crew', '')).strip().upper()
        if crew and crew != 'NAN' and crew not in ['A', 'B', 'C', 'D']:
            warnings.append(f"Row {row_num}: Invalid crew '{crew}' (should be A, B, C, or D)")
        
        # Stop if we have too many errors
        if len(errors) > 50:
            errors.append("... and more errors. Please fix the issues above first.")
            break
    
    if errors:
        return {
            'success': False,
            'errors': errors[:50],  # Limit to first 50 errors
            'error_count': len(errors),
            'warnings': warnings[:10]
        }
    
    # Count valid rows
    valid_rows = len(df) - len(errors)
    
    return {
        'success': True,
        'total_rows': len(df),
        'valid_rows': valid_rows,
        'warnings': warnings,
        'message': f'Validation successful. {valid_rows} employees ready to import.'
    }

def validate_overtime_data(df):
    """Validate overtime data"""
    errors = []
    
    # Check for empty dataframe
    if df.empty:
        return {'success': False, 'error': 'The uploaded file contains no data'}
    
    # Check for employee ID column
    if 'Employee ID' not in df.columns:
        return {
            'success': False,
            'error': 'Missing required column: Employee ID'
        }
    
    # Check for week columns (should have 13 weeks)
    week_columns = [col for col in df.columns if str(col).startswith('Week')]
    if len(week_columns) < 13:
        errors.append(f"Expected 13 week columns, found {len(week_columns)}")
    
    # Validate each row
    for idx, row in df.iterrows():
        row_num = idx + 2
        
        # Check Employee ID
        emp_id = str(row.get('Employee ID', '')).strip()
        if not emp_id or emp_id == 'nan':
            errors.append(f"Row {row_num}: Missing Employee ID")
        
        # Check that overtime hours are numeric and reasonable
        for week in week_columns:
            value = row.get(week)
            if pd.notna(value):
                try:
                    hours = float(value)
                    if hours < 0:
                        errors.append(f"Row {row_num}, {week}: Negative hours not allowed")
                    elif hours > 84:  # More than 12 hours/day for 7 days
                        errors.append(f"Row {row_num}, {week}: Unrealistic hours ({hours})")
                except (ValueError, TypeError):
                    errors.append(f"Row {row_num}, {week}: Invalid hours value '{value}'")
        
        # Stop if too many errors
        if len(errors) > 50:
            errors.append("... and more errors. Please fix the issues above first.")
            break
    
    if errors:
        return {
            'success': False,
            'errors': errors[:50],
            'error_count': len(errors)
        }
    
    return {
        'success': True,
        'total_rows': len(df),
        'employee_count': df['Employee ID'].nunique(),
        'message': f'Validation successful. Overtime data for {df["Employee ID"].nunique()} employees ready to import.'
    }

def validate_bulk_update(df):
    """Validate bulk update data"""
    errors = []
    
    # Check for empty dataframe
    if df.empty:
        return {'success': False, 'error': 'The uploaded file contains no data'}
    
    if 'Employee ID' not in df.columns:
        return {
            'success': False,
            'error': 'Missing required column: Employee ID'
        }
    
    # Check what fields are being updated
    update_fields = [col for col in df.columns if col != 'Employee ID']
    
    if not update_fields:
        return {
            'success': False,
            'error': 'No fields to update found. Please include at least one field to update.'
        }
    
    # Validate each row
    for idx, row in df.iterrows():
        row_num = idx + 2
        
        emp_id = str(row.get('Employee ID', '')).strip()
        if not emp_id or emp_id == 'nan':
            errors.append(f"Row {row_num}: Missing Employee ID")
        
        # Validate specific fields if present
        if 'Email' in update_fields:
            email = str(row.get('Email', '')).strip()
            if email and email != 'nan' and not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
                errors.append(f"Row {row_num}: Invalid email format '{email}'")
        
        if 'Crew' in update_fields:
            crew = str(row.get('Crew', '')).strip().upper()
            if crew and crew != 'NAN' and crew not in ['A', 'B', 'C', 'D']:
                errors.append(f"Row {row_num}: Invalid crew '{crew}'")
    
    if errors:
        return {
            'success': False,
            'errors': errors[:50],
            'error_count': len(errors)
        }
    
    return {
        'success': True,
        'total_rows': len(df),
        'update_fields': update_fields,
        'message': f'Validation successful. Ready to update {len(df)} employees.'
    }

# ==========================================
# PROCESSING FUNCTIONS
# ==========================================

def process_employee_data(df, mode='append', file_upload=None):
    """Process employee data with comprehensive error handling"""
    successful = 0
    failed = 0
    errors = []
    created = 0
    updated = 0
    
    try:
        # If replace mode, delete existing employees first
        if mode == 'replace':
            # Delete all non-supervisor employees
            deleted_count = Employee.query.filter_by(is_supervisor=False).delete()
            db.session.commit()
            logger.info(f"Deleted {deleted_count} existing employees in replace mode")
        
        # Process each row
        for idx, row in df.iterrows():
            try:
                # Extract and clean data
                emp_id = str(row.get('Employee ID', '')).strip()
                first_name = str(row.get('First Name', '')).strip()
                last_name = str(row.get('Last Name', '')).strip()
                email = str(row.get('Email', '')).strip().lower()
                crew = str(row.get('Crew', '')).strip().upper()
                
                # Skip if essential data is missing
                if not emp_id or emp_id == 'nan':
                    failed += 1
                    errors.append(f"Row {idx + 2}: Missing Employee ID")
                    continue
                
                # Clean crew value
                if crew == 'NAN' or crew not in ['A', 'B', 'C', 'D']:
                    crew = None
                
                # Check if employee exists
                employee = Employee.query.filter_by(employee_id=emp_id).first()
                
                if employee and mode == 'append':
                    # Update existing employee
                    employee.name = f"{first_name} {last_name}".strip()
                    employee.email = email
                    if crew:
                        employee.crew = crew
                    updated += 1
                else:
                    # Create new employee
                    employee = Employee(
                        employee_id=emp_id,
                        name=f"{first_name} {last_name}".strip(),
                        email=email,
                        crew=crew,
                        is_supervisor=False,
                        is_active=True
                    )
                    
                    # Set default password
                    if hasattr(employee, 'set_password'):
                        employee.set_password('changeme123')
                    
                    db.session.add(employee)
                    created += 1
                
                successful += 1
                
            except Exception as e:
                failed += 1
                error_msg = f"Row {idx + 2}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
                
                # Continue processing other rows
                continue
        
        # Commit all changes
        db.session.commit()
        logger.info(f"Employee import completed: {successful} successful, {failed} failed")
        
        result = {
            'success': True,
            'total': len(df),
            'successful': successful,
            'failed': failed,
            'created': created,
            'updated': updated,
            'message': f'Successfully processed {successful} employees ({created} created, {updated} updated)'
        }
        
        if errors:
            result['errors'] = errors[:10]  # Include first 10 errors
            if len(errors) > 10:
                result['errors'].append(f"... and {len(errors) - 10} more errors")
        
        return result
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Employee data processing failed: {str(e)}", exc_info=True)
        return {
            'success': False,
            'error': f'Processing failed: {str(e)}'
        }

def process_overtime_data(df, mode='replace', file_upload=None):
    """Process overtime data - FIXED to use correct OvertimeHistory fields"""
    successful = 0
    failed = 0
    errors = []
    total_hours = 0
    
    try:
        # Get week columns
        week_columns = [col for col in df.columns if str(col).startswith('Week')]
        week_columns.sort(key=lambda x: int(x.split(' ')[1]) if len(x.split(' ')) > 1 else 0)
        
        # Process each employee
        for idx, row in df.iterrows():
            try:
                emp_id = str(row.get('Employee ID', '')).strip()
                
                # Find employee
                employee = Employee.query.filter_by(employee_id=emp_id).first()
                
                if not employee:
                    failed += 1
                    errors.append(f"Row {idx + 2}: Employee ID '{emp_id}' not found")
                    continue
                
                # Delete existing overtime if replace mode
                if mode == 'replace':
                    OvertimeHistory.query.filter_by(employee_id=employee.id).delete()
                
                # Add overtime records for each week
                for i, week_col in enumerate(week_columns[:13]):  # Limit to 13 weeks
                    value = row.get(week_col)
                    if pd.notna(value):
                        try:
                            hours = float(value)
                            if hours > 0:
                                # Calculate week end date (13 weeks ago from today)
                                weeks_ago = 13 - i
                                week_end = datetime.now().date() - timedelta(weeks=weeks_ago)
                                # Adjust to Sunday (end of week)
                                days_until_sunday = 6 - week_end.weekday()
                                if days_until_sunday < 0:
                                    days_until_sunday += 7
                                week_end = week_end + timedelta(days=days_until_sunday)
                                
                                # Week start is Monday
                                week_start = week_end - timedelta(days=6)
                                
                                # Check if record exists (if append mode)
                                if mode == 'append':
                                    existing = OvertimeHistory.query.filter_by(
                                        employee_id=employee.id,
                                        week_ending=week_end
                                    ).first()
                                    
                                    if existing:
                                        # Update existing record with correct fields
                                        existing.overtime_hours = hours
                                        existing.hours = hours  # backward compatibility
                                        existing.total_hours = 40 + hours  # assuming 40 regular hours
                                        existing.regular_hours = 40
                                        existing.week_start_date = week_start
                                    else:
                                        # Create new record with all fields
                                        ot_record = OvertimeHistory(
                                            employee_id=employee.id,
                                            week_ending=week_end,
                                            week_start_date=week_start,
                                            overtime_hours=hours,
                                            hours=hours,  # backward compatibility
                                            regular_hours=40,
                                            total_hours=40 + hours,
                                            is_current=(i == 0)  # Mark most recent week as current
                                        )
                                        db.session.add(ot_record)
                                else:
                                    # Create new record for replace mode
                                    ot_record = OvertimeHistory(
                                        employee_id=employee.id,
                                        week_ending=week_end,
                                        week_start_date=week_start,
                                        overtime_hours=hours,
                                        hours=hours,  # backward compatibility
                                        regular_hours=40,
                                        total_hours=40 + hours,
                                        is_current=(i == 0)
                                    )
                                    db.session.add(ot_record)
                                
                                total_hours += hours
                        except (ValueError, TypeError):
                            errors.append(f"Row {idx + 2}, {week_col}: Invalid hours value")
                
                successful += 1
                
            except Exception as e:
                failed += 1
                error_msg = f"Row {idx + 2}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        # Commit all changes
        db.session.commit()
        logger.info(f"Overtime import completed: {successful} successful, {failed} failed")
        
        result = {
            'success': True,
            'total': len(df),
            'successful': successful,
            'failed': failed,
            'total_hours': total_hours,
            'message': f'Successfully processed overtime for {successful} employees ({total_hours:.1f} total hours)'
        }
        
        if errors:
            result['errors'] = errors[:10]
            if len(errors) > 10:
                result['errors'].append(f"... and {len(errors) - 10} more errors")
        
        return result
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Overtime data processing failed: {str(e)}", exc_info=True)
        return {
            'success': False,
            'error': f'Processing failed: {str(e)}'
        }

def process_bulk_update(df, file_upload=None):
    """Process bulk update"""
    successful = 0
    failed = 0
    errors = []
    fields_updated = set()
    
    try:
        # Get update fields
        update_fields = [col for col in df.columns if col != 'Employee ID']
        
        # Process each row
        for idx, row in df.iterrows():
            try:
                emp_id = str(row.get('Employee ID', '')).strip()
                
                # Find employee
                employee = Employee.query.filter_by(employee_id=emp_id).first()
                
                if not employee:
                    failed += 1
                    errors.append(f"Row {idx + 2}: Employee ID '{emp_id}' not found")
                    continue
                
                # Track what was updated
                row_updated = False
                
                # Update fields
                for col in update_fields:
                    value = row.get(col)
                    if pd.notna(value) and str(value).strip() and str(value).strip() != 'nan':
                        value = str(value).strip()
                        
                        if col == 'Crew':
                            value = value.upper()
                            if value in ['A', 'B', 'C', 'D']:
                                employee.crew = value
                                row_updated = True
                                fields_updated.add('Crew')
                        elif col == 'Email':
                            employee.email = value.lower()
                            row_updated = True
                            fields_updated.add('Email')
                        elif col == 'Department':
                            employee.department = value
                            row_updated = True
                            fields_updated.add('Department')
                        elif col == 'Position' and hasattr(employee, 'position_name'):
                            employee.position_name = value
                            row_updated = True
                            fields_updated.add('Position')
                        # Add more field mappings as needed
                
                if row_updated:
                    successful += 1
                else:
                    failed += 1
                    errors.append(f"Row {idx + 2}: No valid updates found")
                
            except Exception as e:
                failed += 1
                error_msg = f"Row {idx + 2}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        # Commit all changes
        db.session.commit()
        logger.info(f"Bulk update completed: {successful} successful, {failed} failed")
        
        result = {
            'success': True,
            'total': len(df),
            'successful': successful,
            'failed': failed,
            'fields_updated': list(fields_updated),
            'message': f'Successfully updated {successful} employees'
        }
        
        if errors:
            result['errors'] = errors[:10]
            if len(errors) > 10:
                result['errors'].append(f"... and {len(errors) - 10} more errors")
        
        return result
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bulk update processing failed: {str(e)}", exc_info=True)
        return {
            'success': False,
            'error': f'Processing failed: {str(e)}'
        }

# ==========================================
# TEMPLATE DOWNLOAD ROUTES
# ==========================================

@employee_import_bp.route('/download-employee-template')
@login_required
@supervisor_required
def download_employee_template():
    """Download employee upload template"""
    try:
        # Create sample template data
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
        
        # Create Excel file
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
            
            # Write headers with formatting
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            # Adjust column widths
            worksheet.set_column('A:A', 15)  # Employee ID
            worksheet.set_column('B:C', 12)  # Names
            worksheet.set_column('D:D', 25)  # Email
            worksheet.set_column('E:G', 15)  # Other fields
            
            # Add instructions as comments
            worksheet.write_comment('A1', 'Unique identifier for each employee')
            worksheet.write_comment('E1', 'Crew must be A, B, C, or D')
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'employee_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
        )
    
    except Exception as e:
        logger.error(f"Error generating employee template: {e}")
        flash('Error generating template. Please try again.', 'danger')
        return redirect(url_for('employee_import.upload_employees'))

@employee_import_bp.route('/download-overtime-template')
@login_required
@supervisor_required
def download_overtime_template():
    """Download overtime upload template"""
    try:
        # Create template with employee IDs and 13 weeks
        template_data = {'Employee ID': ['EMP001', 'EMP002', 'EMP003']}
        
        # Add 13 week columns with dates
        base_date = datetime.now().date()
        for i in range(1, 14):
            weeks_ago = 13 - i
            week_start = base_date - timedelta(weeks=weeks_ago)
            week_start = week_start - timedelta(days=week_start.weekday())
            week_label = f'Week {i} ({week_start.strftime("%m/%d")})'
            template_data[f'Week {i}'] = [0, 0, 0]
        
        df = pd.DataFrame(template_data)
        
        # Create Excel file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Overtime Data', index=False)
            
            # Get workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets['Overtime Data']
            
            # Add formatting
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#4472C4',
                'font_color': 'white',
                'border': 1,
                'text_wrap': True
            })
            
            # Number format for hours
            hours_format = workbook.add_format({'num_format': '#,##0.0'})
            
            # Write headers
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            # Apply number format to week columns
            for col in range(1, 14):
                worksheet.set_column(col, col, 10, hours_format)
            
            # Set column widths
            worksheet.set_column('A:A', 15)  # Employee ID
            
            # Add instructions
            worksheet.write_comment('A1', 'Employee ID must match existing employees')
            worksheet.write_comment('B1', 'Enter overtime hours for each week (0 if none)')
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'overtime_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
        )
    
    except Exception as e:
        logger.error(f"Error generating overtime template: {e}")
        flash('Error generating template. Please try again.', 'danger')
        return redirect(url_for('employee_import.upload_overtime'))

@employee_import_bp.route('/download-bulk-update-template/<template_type>')
@login_required
@supervisor_required
def download_bulk_update_template(template_type):
    """Download bulk update template"""
    try:
        if template_type == 'employee':
            template_data = {
                'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
                'Email': ['new.email@company.com', '', ''],
                'Crew': ['B', 'C', ''],
                'Department': ['', 'Maintenance', '']
            }
            sheet_name = 'Employee Updates'
        else:
            # Generic template
            template_data = {
                'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
                'Field 1': ['', '', ''],
                'Field 2': ['', '', '']
            }
            sheet_name = 'Bulk Update'
        
        df = pd.DataFrame(template_data)
        
        # Create Excel file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            # Add formatting
            workbook = writer.book
            worksheet = writer.sheets[sheet_name]
            
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#4472C4',
                'font_color': 'white',
                'border': 1
            })
            
            # Write headers
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            # Add instructions
            worksheet.write_comment('A1', 'Employee ID must match existing employees')
            worksheet.write_comment('B1', 'Leave blank to keep current value')
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'bulk_update_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
        )
    
    except Exception as e:
        logger.error(f"Error generating bulk update template: {e}")
        flash('Error generating template. Please try again.', 'danger')
        return redirect(url_for('employee_import.upload_employees'))

# ==========================================
# EXPORT ROUTES
# ==========================================

@employee_import_bp.route('/export-current-employees')
@login_required
@supervisor_required
def export_current_employees():
    """Export current employee list"""
    try:
        # Get all non-supervisor employees
        employees = Employee.query.filter_by(is_supervisor=False).order_by(Employee.employee_id).all()
        
        if not employees:
            flash('No employees found to export.', 'warning')
            return redirect(url_for('employee_import.upload_employees'))
        
        # Build data for export
        data = []
        for emp in employees:
            data.append({
                'Employee ID': emp.employee_id,
                'First Name': emp.name.split()[0] if emp.name else '',
                'Last Name': ' '.join(emp.name.split()[1:]) if emp.name and len(emp.name.split()) > 1 else '',
                'Email': emp.email,
                'Crew': emp.crew or '',
                'Department': getattr(emp, 'department', ''),
                'Position': emp.position.name if emp.position else getattr(emp, 'position_name', ''),
                'Active': 'Yes' if getattr(emp, 'is_active', True) else 'No'
            })
        
        df = pd.DataFrame(data)
        
        # Create Excel file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Employees', index=False)
            
            # Add formatting
            workbook = writer.book
            worksheet = writer.sheets['Employees']
            
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#4472C4',
                'font_color': 'white',
                'border': 1
            })
            
            # Apply header format
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            # Auto-fit columns
            for idx, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.set_column(idx, idx, max_len)
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'employees_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
        
    except Exception as e:
        logger.error(f"Error exporting employees: {e}", exc_info=True)
        flash('Error exporting employee data. Please try again.', 'danger')
        return redirect(url_for('employee_import.upload_employees'))

# Alias for the route
export_employees = export_current_employees

@employee_import_bp.route('/export-current-overtime')
@login_required
@supervisor_required
def export_current_overtime():
    """Export current overtime data to Excel with filters applied - FIXED VERSION"""
    try:
        # Get filter parameters from request (same as overtime_management)
        search_term = request.args.get('search', '')
        crew_filter = request.args.get('crew', '')
        position_filter = request.args.get('position', '')
        ot_range_filter = request.args.get('ot_range', '')
        
        # Calculate date range for 13-week period
        end_date = date.today()
        start_date = end_date - timedelta(weeks=13)
        
        # Base query for employees
        query = Employee.query.filter_by(is_supervisor=False)
        
        # Apply filters
        if search_term:
            query = query.filter(
                or_(
                    Employee.name.ilike(f'%{search_term}%'),
                    Employee.employee_id.ilike(f'%{search_term}%')
                )
            )
        
        if crew_filter:
            query = query.filter_by(crew=crew_filter)
        
        if position_filter:
            query = query.filter_by(position_id=position_filter)
        
        # Get all filtered employees
        employees = query.all()
        
        # Prepare data for export
        export_data = []
        
        for employee in employees:
            # Get overtime history
            overtime_records = OvertimeHistory.query.filter_by(
                employee_id=employee.id
            ).filter(
                OvertimeHistory.week_ending >= start_date,
                OvertimeHistory.week_ending <= end_date
            ).order_by(OvertimeHistory.week_ending).all()
            
            # Calculate totals using the correct field names from OvertimeHistory model
            total_ot = 0
            for record in overtime_records:
                # Check which field exists in the model
                if hasattr(record, 'overtime_hours') and record.overtime_hours is not None:
                    total_ot += record.overtime_hours
                elif hasattr(record, 'hours') and record.hours is not None:
                    total_ot += record.hours
                elif hasattr(record, 'total_hours') and record.total_hours is not None:
                    # If using total_hours, assume anything over 40/week is OT
                    total_ot += max(0, record.total_hours - 40)
            
            # Apply OT range filter
            if ot_range_filter:
                if ot_range_filter == '0-50' and total_ot > 50:
                    continue
                elif ot_range_filter == '50-100' and (total_ot <= 50 or total_ot > 100):
                    continue
                elif ot_range_filter == '100-150' and (total_ot <= 100 or total_ot > 150):
                    continue
                elif ot_range_filter == '150+' and total_ot <= 150:
                    continue
            
            # Build row data with weekly breakdown
            row_data = {
                'Employee ID': employee.employee_id,
                'Name': employee.name,
                'Email': employee.email,
                'Crew': employee.crew or '',
                'Position': employee.position.name if employee.position else '',
                'Department': employee.department or '',
                'Hire Date': employee.hire_date.strftime('%Y-%m-%d') if employee.hire_date else '',
                'Years Employed': (date.today() - employee.hire_date).days // 365 if employee.hire_date else 0
            }
            
            # Add weekly overtime data
            week_data = {}
            for i in range(13):
                week_end = end_date - timedelta(weeks=i)
                week_start = week_end - timedelta(days=6)
                week_label = f'Week {13-i} ({week_start.strftime("%m/%d")} - {week_end.strftime("%m/%d")})'
                
                # Find overtime for this week
                week_ot = 0
                for record in overtime_records:
                    if record.week_ending == week_end:
                        if hasattr(record, 'overtime_hours') and record.overtime_hours is not None:
                            week_ot = record.overtime_hours
                        elif hasattr(record, 'hours') and record.hours is not None:
                            week_ot = record.hours
                        elif hasattr(record, 'total_hours') and record.total_hours is not None:
                            week_ot = max(0, record.total_hours - 40)
                        break
                
                week_data[week_label] = week_ot
            
            # Add week data in chronological order
            for week_label in sorted(week_data.keys()):
                row_data[week_label] = week_data[week_label]
            
            # Add totals
            row_data['Total OT Hours'] = round(total_ot, 1)
            row_data['Average Weekly OT'] = round(total_ot / 13, 1)
            
            export_data.append(row_data)
        
        # Create DataFrame
        df = pd.DataFrame(export_data)
        
        # Generate Excel file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Write main data
            df.to_excel(writer, sheet_name='Overtime Report', index=False)
            
            # Get workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets['Overtime Report']
            
            # Add formats
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#4472C4',
                'font_color': 'white',
                'border': 1
            })
            
            number_format = workbook.add_format({
                'num_format': '#,##0.0'
            })
            
            # Apply header format
            for col_num, col_name in enumerate(df.columns):
                worksheet.write(0, col_num, col_name, header_format)
            
            # Adjust column widths
            worksheet.set_column('A:A', 12)  # Employee ID
            worksheet.set_column('B:B', 25)  # Name
            worksheet.set_column('C:C', 30)  # Email
            worksheet.set_column('D:H', 15)  # Crew, Position, etc.
            
            # Apply number format to numeric columns
            if len(df.columns) > 8:
                for col_idx in range(8, len(df.columns)):
                    worksheet.set_column(col_idx, col_idx, 12, number_format)
            
            # Add summary statistics
            summary_data = {
                'Summary': ['Total Employees', 'Total OT Hours', 'Average OT per Employee', 
                           'Employees with High OT (195+ hrs)', 'Report Generated'],
                'Value': [
                    len(export_data),
                    sum(row['Total OT Hours'] for row in export_data) if export_data else 0,
                    round(sum(row['Total OT Hours'] for row in export_data) / max(1, len(export_data)), 1) if export_data else 0,
                    sum(1 for row in export_data if row['Total OT Hours'] >= 195) if export_data else 0,
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                ]
            }
            
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Format summary sheet
            summary_worksheet = writer.sheets['Summary']
            for col_num, col_name in enumerate(summary_df.columns):
                summary_worksheet.write(0, col_num, col_name, header_format)
            
            # Apply filters if any
            filters_data = {
                'Filter': ['Search Term', 'Crew', 'Position', 'OT Range', 'Date Range'],
                'Value': [
                    search_term or 'None',
                    crew_filter or 'All',
                    Position.query.get(position_filter).name if position_filter else 'All',
                    ot_range_filter or 'All',
                    f'{start_date.strftime("%Y-%m-%d")} to {end_date.strftime("%Y-%m-%d")}'
                ]
            }
            
            filters_df = pd.DataFrame(filters_data)
            filters_df.to_excel(writer, sheet_name='Applied Filters', index=False)
            
            # Format filters sheet
            filters_worksheet = writer.sheets['Applied Filters']
            for col_num, col_name in enumerate(filters_df.columns):
                filters_worksheet.write(0, col_num, col_name, header_format)
        
        # Prepare file for download
        output.seek(0)
        filename = f'overtime_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f"Error exporting overtime data: {e}")
        logger.error(f"Error type: {type(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        flash('Error exporting overtime data. Please try again.', 'danger')
        return redirect(url_for('main.overtime_management'))

# ==========================================
# API ENDPOINTS FOR AJAX CALLS
# ==========================================

@employee_import_bp.route('/api/upload-details/<int:upload_id>')
@login_required
@supervisor_required
def get_upload_details(upload_id):
    """Get detailed information about an upload"""
    try:
        upload = FileUpload.query.get_or_404(upload_id)
        
        # Augment for template compatibility
        augment_file_upload(upload)
        
        # Build response
        response = {
            'id': upload.id,
            'filename': upload.filename,
            'file_type': upload.upload_type,
            'uploaded_by': upload.uploaded_by.name if upload.uploaded_by else 'Unknown',
            'upload_date': upload.uploaded_at.strftime('%Y-%m-%d %H:%M:%S'),
            'status': upload.status or 'completed',
            'total_records': upload.total_records or 0,
            'successful_records': upload.successful_records or 0,
            'failed_records': upload.failed_records or 0,
            'records_processed': upload.records_processed,
            'records_created': upload.records_created,
            'records_updated': upload.records_updated
        }
        
        # Add error details if present
        if upload.error_details:
            if isinstance(upload.error_details, dict):
                response['error_details'] = upload.error_details
            else:
                response['error_details'] = str(upload.error_details)
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error getting upload details: {e}")
        return jsonify({'error': 'Failed to get upload details'}), 500

@employee_import_bp.route('/api/delete-upload/<int:upload_id>', methods=['DELETE'])
@login_required
@supervisor_required
def delete_upload(upload_id):
    """Delete an upload record"""
    try:
        upload = FileUpload.query.get_or_404(upload_id)
        
        # Only allow deletion by uploader or admin
        if upload.uploaded_by_id != current_user.id and not getattr(current_user, 'is_admin', False):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        db.session.delete(upload)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Upload record deleted successfully'
        })
        
    except Exception as e:
        logger.error(f"Error deleting upload: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Failed to delete upload'}), 500

# ==========================================
# TEST ROUTE
# ==========================================

@employee_import_bp.route('/upload-test')
@login_required
@supervisor_required
def upload_test():
    """Simple test page to verify the blueprint is working"""
    return f"""
    <html>
    <head>
        <title>Upload Test</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; }}
            .info {{ background: #e3f2fd; padding: 10px; margin: 10px 0; border-radius: 4px; }}
            .success {{ color: green; }}
            .error {{ color: red; }}
        </style>
    </head>
    <body>
        <h1>Employee Import Blueprint Test</h1>
        
        <div class="info">
            <h3>Blueprint Status: <span class="success">✓ Working</span></h3>
            <p>User: {current_user.name}</p>
            <p>Is Supervisor: {current_user.is_supervisor}</p>
            <p>Upload Folder: {current_app.config.get('UPLOAD_FOLDER', 'Not configured')}</p>
            <p>Upload Folder Exists: {os.path.exists(current_app.config.get('UPLOAD_FOLDER', ''))}</p>
        </div>
        
        <h3>Quick Tests:</h3>
        <ul>
            <li><a href="/upload-employees">Upload Employees Page</a></li>
            <li><a href="/upload-overtime">Upload Overtime Page</a></li>
            <li><a href="/download-employee-template">Download Employee Template</a></li>
            <li><a href="/download-overtime-template">Download Overtime Template</a></li>
        </ul>
        
        <a href="/supervisor/dashboard">Back to Dashboard</a>
    </body>
    </html>
    """

# ==========================================
# ERROR HANDLERS
# ==========================================

@employee_import_bp.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Resource not found'}), 404
    flash('Page not found.', 'warning')
    return redirect(url_for('supervisor.dashboard'))

@employee_import_bp.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal error in employee_import: {error}")
    db.session.rollback()
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500
    flash('An unexpected error occurred. Please try again.', 'danger')
    return redirect(url_for('supervisor.dashboard'))
