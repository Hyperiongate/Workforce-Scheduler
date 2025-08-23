# blueprints/employee_import.py
"""
Complete Excel upload system for employee data management
Handles employee data, overtime history, and bulk updates
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, send_file
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
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# Set up logging
logger = logging.getLogger(__name__)

employee_import_bp = Blueprint('employee_import', __name__)

# ==========================================
# DECORATORS
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
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def get_employee_stats():
    """Get comprehensive employee statistics"""
    try:
        total_employees = Employee.query.count()
        
        # Get crew distribution
        crew_stats = db.session.query(
            Employee.crew,
            func.count(Employee.id).label('count')
        ).group_by(Employee.crew).all()
        
        crews = {
            'A': 0, 'B': 0, 'C': 0, 'D': 0, 'Unassigned': 0
        }
        
        for crew, count in crew_stats:
            if crew in ['A', 'B', 'C', 'D']:
                crews[crew] = count
            else:
                crews['Unassigned'] += count
        
        # Get employees without overtime data
        employees_with_ot = db.session.query(OvertimeHistory.employee_id).distinct().subquery()
        employees_without_ot = Employee.query.filter(
            ~Employee.id.in_(db.session.query(employees_with_ot))
        ).count()
        
        # Get position distribution
        position_stats = db.session.query(
            Position.name,
            func.count(Employee.id).label('count')
        ).join(Employee).group_by(Position.name).all()
        
        positions = {pos: count for pos, count in position_stats}
        
        return {
            'total_employees': total_employees,
            'crews': crews,
            'employees_without_ot': employees_without_ot,
            'positions': positions
        }
        
    except Exception as e:
        logger.error(f"Error getting employee stats: {e}")
        return {
            'total_employees': 0,
            'crews': {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'Unassigned': 0},
            'employees_without_ot': 0,
            'positions': {}
        }

def get_recent_uploads(limit=5):
    """Get recent file uploads"""
    try:
        uploads = FileUpload.query.order_by(
            FileUpload.uploaded_at.desc()
        ).limit(limit).all()
        
        # Add computed properties for backward compatibility
        for upload in uploads:
            augment_file_upload(upload)
            
        return uploads
    except Exception as e:
        logger.error(f"Error getting recent uploads: {e}")
        return []

def get_employees_without_accounts():
    """Get count of employees without user accounts"""
    try:
        return Employee.query.filter(
            or_(Employee.email == None, Employee.email == '')
        ).count()
    except Exception as e:
        logger.error(f"Error counting employees without accounts: {e}")
        return 0

def augment_file_upload(upload):
    """Add computed properties to FileUpload object for template compatibility"""
    if upload:
        # Calculate processed records from successful + failed
        upload.records_processed = (upload.successful_records or 0) + (upload.failed_records or 0)
        
        # For backward compatibility
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
    """Upload employees page"""
    try:
        stats = get_employee_stats()
        recent_uploads = get_recent_uploads()
        employees_without_accounts = get_employees_without_accounts()
        
        # Check which template to use (you can switch between templates here)
        template = 'upload_employees_enhanced.html'  # or 'upload_employees.html' for simple version
        
        return render_template(template,
                             recent_uploads=recent_uploads,
                             stats=stats,
                             crew_distribution=stats['crews'],
                             total_employees=stats['total_employees'],
                             employees_without_accounts=employees_without_accounts,
                             account_creation_available=True)
    
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
        if 'file' not in request.files:
            flash('No file selected', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)
        
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
        
        # Create upload folder if it doesn't exist
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
        os.makedirs(upload_folder, exist_ok=True)
        
        filepath = os.path.join(upload_folder, filename)
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
            # Read and process the Excel file
            df = pd.read_excel(filepath)
            
            # Process based on upload type
            if upload_type == 'employee':
                result = process_employee_data(df, mode, file_upload)
            elif upload_type == 'overtime':
                result = process_overtime_data(df, mode, file_upload)
            elif upload_type == 'bulk_update':
                result = process_bulk_update(df, file_upload)
            else:
                result = {'success': False, 'error': 'Invalid upload type'}
            
            # Update upload record
            file_upload.status = 'completed' if result.get('success') else 'failed'
            file_upload.total_records = result.get('total', 0)
            file_upload.successful_records = result.get('successful', 0)
            file_upload.failed_records = result.get('failed', 0)
            
            if result.get('error'):
                file_upload.error_details = {'error': result.get('error')}
            elif result.get('errors'):
                file_upload.error_details = {'errors': result.get('errors')}
                
            db.session.commit()
            
            # Show appropriate message
            if result.get('success'):
                flash(f"Successfully processed {result.get('successful', 0)} records!", 'success')
                if result.get('failed', 0) > 0:
                    flash(f"{result.get('failed', 0)} records failed to process", 'warning')
            else:
                flash(f"Upload failed: {result.get('error', 'Unknown error')}", 'error')
                
        except Exception as e:
            logger.error(f"Error processing file: {e}")
            file_upload.status = 'failed'
            file_upload.error_details = {'error': str(e)}
            db.session.commit()
            flash(f"Error processing file: {str(e)}", 'error')
            
        finally:
            # Clean up temp file
            try:
                os.remove(filepath)
            except:
                pass
                
        return redirect(url_for('employee_import.upload_employees'))
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        flash('An error occurred during upload. Please try again.', 'error')
        return redirect(url_for('employee_import.upload_employees'))

# ==========================================
# VALIDATION AND PROCESSING ROUTES
# ==========================================

@employee_import_bp.route('/validate-upload', methods=['POST'])
@login_required
@supervisor_required
def validate_upload():
    """Validate uploaded Excel file via AJAX"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            return jsonify({'success': False, 'error': 'Invalid file type. Please upload Excel files only.'})
        
        # Get upload type from form data (handle both 'uploadType' and 'upload_type')
        upload_type = request.form.get('uploadType') or request.form.get('upload_type', 'employee')
        
        # Map bulk to bulk_update for consistency
        if upload_type == 'bulk':
            upload_type = 'bulk_update'
        
        # Read the Excel file
        try:
            df = pd.read_excel(file)
        except Exception as read_error:
            return jsonify({'success': False, 'error': f'Error reading Excel file: {str(read_error)}'})
        
        # Validate based on upload type
        if upload_type == 'employee':
            result = validate_employee_data(df)
        elif upload_type == 'overtime':
            result = validate_overtime_data(df)
        elif upload_type == 'bulk_update':
            result = validate_bulk_update(df)
        else:
            result = {'success': False, 'error': f'Invalid upload type: {upload_type}'}
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Validation error: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': f'Validation error: {str(e)}'})

@employee_import_bp.route('/process-upload', methods=['POST'])
@login_required
@supervisor_required
def process_upload():
    """Process the uploaded file via AJAX"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        file = request.files['file']
        
        # Get upload type and mode (handle both naming conventions)
        upload_type = request.form.get('uploadType') or request.form.get('upload_type', 'employee')
        mode = request.form.get('mode', 'append')
        
        # Map bulk to bulk_update
        if upload_type == 'bulk':
            upload_type = 'bulk_update'
        
        # Save file temporarily
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
        os.makedirs(upload_folder, exist_ok=True)
        
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)
        
        # Create file upload record
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
            # Read and process file
            df = pd.read_excel(filepath)
            
            # Process based on type
            if upload_type == 'employee':
                result = process_employee_data(df, mode, file_upload)
            elif upload_type == 'overtime':
                result = process_overtime_data(df, mode, file_upload)
            elif upload_type == 'bulk_update':
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
            file_upload.status = 'failed'
            file_upload.error_details = {'error': str(e)}
            db.session.commit()
            return jsonify({'success': False, 'error': str(e)})
            
        finally:
            # Clean up temp file
            try:
                os.remove(filepath)
            except:
                pass
        
    except Exception as e:
        logger.error(f"Process error: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

# ==========================================
# VALIDATION FUNCTIONS
# ==========================================

def validate_employee_data(df):
    """Validate employee data"""
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
            'error': f"Missing required columns: {', '.join(missing_columns)}"
        }
    
    # Validate each row
    employee_ids = set()
    
    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel row number (1-indexed + header)
        
        # Check Employee ID
        emp_id = str(row.get('Employee ID', '')).strip()
        if not emp_id or emp_id == 'nan':
            errors.append(f"Row {row_num}: Missing Employee ID")
        elif emp_id in employee_ids:
            errors.append(f"Row {row_num}: Duplicate Employee ID '{emp_id}'")
        else:
            employee_ids.add(emp_id)
        
        # Check First Name
        first_name = str(row.get('First Name', '')).strip()
        if not first_name or first_name == 'nan':
            errors.append(f"Row {row_num}: Missing First Name")
        
        # Check Last Name
        last_name = str(row.get('Last Name', '')).strip()
        if not last_name or last_name == 'nan':
            errors.append(f"Row {row_num}: Missing Last Name")
        
        # Check Email
        email = str(row.get('Email', '')).strip()
        if not email or email == 'nan':
            errors.append(f"Row {row_num}: Missing Email")
        elif not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
            errors.append(f"Row {row_num}: Invalid email format '{email}'")
        
        # Check Crew
        crew = str(row.get('Crew', '')).strip().upper()
        if crew and crew != 'NAN' and crew not in ['A', 'B', 'C', 'D']:
            errors.append(f"Row {row_num}: Invalid crew '{crew}'. Must be A, B, C, or D")
        
        # Stop if too many errors
        if len(errors) > 50:
            errors.append("Too many errors. Please fix the issues above first.")
            break
    
    if errors:
        return {
            'success': False,
            'errors': errors[:50],  # Limit errors shown
            'error_count': len(errors)
        }
    
    # Return success with summary
    return {
        'success': True,
        'total_rows': len(df),
        'employee_count': len(employee_ids),
        'message': f'Validation successful. {len(employee_ids)} employees ready to import.'
    }

def validate_overtime_data(df):
    """Validate overtime history data"""
    errors = []
    
    if df.empty:
        return {'success': False, 'error': 'The uploaded file contains no data'}
    
    # Check for Employee ID column
    if 'Employee ID' not in df.columns:
        return {
            'success': False,
            'error': 'Missing required column: Employee ID'
        }
    
    # Check for week columns (Week 1 through Week 13)
    missing_weeks = []
    for week in range(1, 14):
        if f'Week {week}' not in df.columns:
            missing_weeks.append(f'Week {week}')
    
    if missing_weeks:
        return {
            'success': False,
            'error': f"Missing week columns: {', '.join(missing_weeks)}"
        }
    
    # Validate data
    for idx, row in df.iterrows():
        row_num = idx + 2
        
        emp_id = str(row.get('Employee ID', '')).strip()
        if not emp_id or emp_id == 'nan':
            errors.append(f"Row {row_num}: Missing Employee ID")
            continue
        
        # Check overtime hours
        for week in range(1, 14):
            hours = row.get(f'Week {week}')
            if pd.notna(hours):
                try:
                    hours_float = float(hours)
                    if hours_float < 0:
                        errors.append(f"Row {row_num}, Week {week}: Negative hours not allowed")
                    elif hours_float > 100:
                        errors.append(f"Row {row_num}, Week {week}: Unusually high hours ({hours_float})")
                except (ValueError, TypeError):
                    errors.append(f"Row {row_num}, Week {week}: Invalid number format")
        
        if len(errors) > 50:
            errors.append("Too many errors. Please fix the issues above first.")
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

def process_employee_data(df, mode, file_upload):
    """Process employee data upload"""
    try:
        successful = 0
        failed = 0
        errors = []
        
        # If mode is replace, deactivate existing employees first
        if mode == 'replace':
            try:
                # Instead of deleting, mark as inactive or remove from system
                # This preserves historical data
                Employee.query.update({'is_active': False})
                db.session.commit()
            except Exception as e:
                logger.error(f"Error deactivating employees: {e}")
                db.session.rollback()
        
        # Process each row
        for idx, row in df.iterrows():
            try:
                emp_id = str(row.get('Employee ID', '')).strip()
                
                # Check if employee exists
                employee = Employee.query.filter_by(employee_id=emp_id).first()
                
                if not employee:
                    # Create new employee
                    employee = Employee(employee_id=emp_id)
                
                # Update employee data
                employee.first_name = str(row.get('First Name', '')).strip()
                employee.last_name = str(row.get('Last Name', '')).strip()
                employee.name = f"{employee.first_name} {employee.last_name}"
                employee.email = str(row.get('Email', '')).strip()
                
                # Set crew
                crew = str(row.get('Crew', '')).strip().upper()
                if crew in ['A', 'B', 'C', 'D']:
                    employee.crew = crew
                
                # Set department if present
                if 'Department' in row:
                    dept = str(row.get('Department', '')).strip()
                    if dept and dept != 'nan':
                        employee.department = dept
                
                # Set position if present
                if 'Position' in row:
                    pos_name = str(row.get('Position', '')).strip()
                    if pos_name and pos_name != 'nan':
                        position = Position.query.filter_by(name=pos_name).first()
                        if position:
                            employee.position_id = position.id
                
                # Mark as active
                employee.is_active = True
                
                db.session.add(employee)
                successful += 1
                
            except Exception as e:
                failed += 1
                errors.append(f"Row {idx + 2}: {str(e)}")
                logger.error(f"Error processing row {idx + 2}: {e}")
        
        # Commit all changes
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'error': f'Database error: {str(e)}',
                'successful': successful,
                'failed': failed
            }
        
        return {
            'success': True,
            'total': len(df),
            'successful': successful,
            'failed': failed,
            'errors': errors[:10] if errors else None
        }
        
    except Exception as e:
        logger.error(f"Error processing employee data: {e}")
        db.session.rollback()
        return {
            'success': False,
            'error': str(e)
        }

def process_overtime_data(df, mode, file_upload):
    """Process overtime history data"""
    try:
        successful = 0
        failed = 0
        errors = []
        
        # If replace mode, clear existing overtime data
        if mode == 'replace':
            try:
                OvertimeHistory.query.delete()
                db.session.commit()
            except Exception as e:
                logger.error(f"Error clearing overtime data: {e}")
                db.session.rollback()
        
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
                
                # Process each week
                for week_num in range(1, 14):
                    hours = row.get(f'Week {week_num}')
                    if pd.notna(hours):
                        try:
                            hours_float = float(hours)
                            
                            # Calculate the week date (13 weeks ago from now)
                            week_date = date.today() - timedelta(weeks=(13 - week_num))
                            
                            # Check if record exists
                            ot_record = OvertimeHistory.query.filter_by(
                                employee_id=employee.id,
                                week_starting=week_date
                            ).first()
                            
                            if not ot_record:
                                ot_record = OvertimeHistory(
                                    employee_id=employee.id,
                                    week_starting=week_date
                                )
                            
                            ot_record.hours = hours_float
                            db.session.add(ot_record)
                            
                        except (ValueError, TypeError) as e:
                            errors.append(f"Row {idx + 2}, Week {week_num}: Invalid hours value")
                
                successful += 1
                
            except Exception as e:
                failed += 1
                errors.append(f"Row {idx + 2}: {str(e)}")
                logger.error(f"Error processing overtime row {idx + 2}: {e}")
        
        # Commit changes
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'error': f'Database error: {str(e)}',
                'successful': successful,
                'failed': failed
            }
        
        return {
            'success': True,
            'total': len(df),
            'successful': successful,
            'failed': failed,
            'errors': errors[:10] if errors else None
        }
        
    except Exception as e:
        logger.error(f"Error processing overtime data: {e}")
        db.session.rollback()
        return {
            'success': False,
            'error': str(e)
        }

def process_bulk_update(df, file_upload):
    """Process bulk employee updates"""
    try:
        successful = 0
        failed = 0
        errors = []
        update_fields = [col for col in df.columns if col != 'Employee ID']
        
        for idx, row in df.iterrows():
            try:
                emp_id = str(row.get('Employee ID', '')).strip()
                
                # Find employee
                employee = Employee.query.filter_by(employee_id=emp_id).first()
                if not employee:
                    failed += 1
                    errors.append(f"Row {idx + 2}: Employee ID '{emp_id}' not found")
                    continue
                
                # Update fields
                for field in update_fields:
                    value = row.get(field)
                    if pd.notna(value):
                        value_str = str(value).strip()
                        
                        if field == 'First Name':
                            employee.first_name = value_str
                            employee.name = f"{employee.first_name} {employee.last_name}"
                        elif field == 'Last Name':
                            employee.last_name = value_str
                            employee.name = f"{employee.first_name} {employee.last_name}"
                        elif field == 'Email':
                            employee.email = value_str
                        elif field == 'Crew':
                            if value_str.upper() in ['A', 'B', 'C', 'D']:
                                employee.crew = value_str.upper()
                        elif field == 'Department':
                            employee.department = value_str
                        elif field == 'Position':
                            position = Position.query.filter_by(name=value_str).first()
                            if position:
                                employee.position_id = position.id
                
                db.session.add(employee)
                successful += 1
                
            except Exception as e:
                failed += 1
                errors.append(f"Row {idx + 2}: {str(e)}")
                logger.error(f"Error updating row {idx + 2}: {e}")
        
        # Commit changes
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'error': f'Database error: {str(e)}',
                'successful': successful,
                'failed': failed
            }
        
        return {
            'success': True,
            'total': len(df),
            'successful': successful,
            'failed': failed,
            'errors': errors[:10] if errors else None,
            'update_fields': update_fields
        }
        
    except Exception as e:
        logger.error(f"Error processing bulk update: {e}")
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
    try:
        # Create workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Employee Data"
        
        # Define headers
        headers = [
            'Employee ID', 'First Name', 'Last Name', 'Email',
            'Crew', 'Department', 'Position', 'Phone',
            'Hire Date', 'Birth Date'
        ]
        
        # Style headers
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center")
        
        # Add headers
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            
            # Set column width
            ws.column_dimensions[get_column_letter(col)].width = 15
        
        # Add sample data
        sample_data = [
            ['EMP001', 'John', 'Doe', 'john.doe@company.com', 'A', 'Operations', 'Machine Operator', '555-0001', '2020-01-15', '1985-05-20'],
            ['EMP002', 'Jane', 'Smith', 'jane.smith@company.com', 'B', 'Operations', 'Lead Operator', '555-0002', '2019-03-22', '1990-08-15'],
            ['EMP003', 'Mike', 'Johnson', 'mike.johnson@company.com', 'C', 'Maintenance', 'Technician', '555-0003', '2021-06-10', '1988-12-03']
        ]
        
        for row_idx, row_data in enumerate(sample_data, 2):
            for col_idx, value in enumerate(row_data, 1):
                ws.cell(row=row_idx, column=col_idx, value=value)
        
        # Add instructions sheet
        ws2 = wb.create_sheet("Instructions")
        instructions = [
            ["Employee Upload Template Instructions"],
            [""],
            ["Required Fields:"],
            ["- Employee ID: Unique identifier for each employee"],
            ["- First Name: Employee's first name"],
            ["- Last Name: Employee's last name"],
            ["- Email: Valid email address (will be used for login)"],
            ["- Crew: Must be A, B, C, or D"],
            [""],
            ["Optional Fields:"],
            ["- Department: Employee's department"],
            ["- Position: Job title/position"],
            ["- Phone: Contact number"],
            ["- Hire Date: Format YYYY-MM-DD"],
            ["- Birth Date: Format YYYY-MM-DD"],
            [""],
            ["Notes:"],
            ["- Do not modify the header row"],
            ["- Do not change the sheet name 'Employee Data'"],
            ["- Save as .xlsx format"],
            ["- Maximum 5000 employees per upload"]
        ]
        
        for row_idx, instruction in enumerate(instructions, 1):
            if instruction:
                ws2.cell(row=row_idx, column=1, value=instruction[0])
                if row_idx == 1:
                    ws2.cell(row=row_idx, column=1).font = Font(bold=True, size=14)
        
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
    """Download overtime upload template"""
    try:
        wb = Workbook()
        ws = wb.active
        ws.title = "Overtime History"
        
        # Headers
        headers = ['Employee ID', 'Employee Name']
        for week in range(1, 14):
            headers.append(f'Week {week}')
        
        # Style headers
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            ws.column_dimensions[get_column_letter(col)].width = 12
        
        # Add date row
        ws.cell(row=2, column=1, value="Week Starting:")
        for week in range(1, 14):
            week_date = date.today() - timedelta(weeks=(13 - week))
            ws.cell(row=2, column=week + 2, value=week_date.strftime('%Y-%m-%d'))
        
        # Sample data
        sample_employees = [
            ['EMP001', 'John Doe', 45, 42, 48, 40, 44, 46, 43, 45, 41, 40, 42, 44, 43],
            ['EMP002', 'Jane Smith', 40, 40, 45, 42, 40, 48, 44, 42, 40, 45, 43, 41, 40],
            ['EMP003', 'Mike Johnson', 42, 44, 40, 43, 45, 40, 42, 44, 46, 48, 40, 42, 44]
        ]
        
        for row_idx, emp_data in enumerate(sample_employees, 3):
            for col_idx, value in enumerate(emp_data, 1):
                ws.cell(row=row_idx, column=col_idx, value=value)
        
        # Instructions sheet
        ws2 = wb.create_sheet("Instructions")
        instructions = [
            ["Overtime History Upload Instructions"],
            [""],
            ["This template captures 13 weeks of overtime history"],
            [""],
            ["Format:"],
            ["- Employee ID: Must match existing employee IDs in the system"],
            ["- Employee Name: For reference only (not imported)"],
            ["- Week 1-13: Overtime hours for each week (numbers only)"],
            [""],
            ["Notes:"],
            ["- Week 1 is the oldest week, Week 13 is the most recent"],
            ["- Enter 0 for weeks with no overtime"],
            ["- Leave blank if no data available"],
            ["- Decimal hours are allowed (e.g., 42.5)"]
        ]
        
        for row_idx, instruction in enumerate(instructions, 1):
            if instruction:
                ws2.cell(row=row_idx, column=1, value=instruction[0])
                if row_idx == 1:
                    ws2.cell(row=row_idx, column=1).font = Font(bold=True, size=14)
        
        # Save
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
# UPLOAD HISTORY ROUTES
# ==========================================

@employee_import_bp.route('/upload-history')
@login_required
@supervisor_required
def upload_history():
    """View upload history"""
    try:
        # Get filter parameters
        upload_type = request.args.get('type')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        # Build query
        query = FileUpload.query
        
        if upload_type:
            query = query.filter_by(upload_type=upload_type)
        
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                query = query.filter(FileUpload.uploaded_at >= date_from_obj)
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
                date_to_obj = date_to_obj.replace(hour=23, minute=59, second=59)
                query = query.filter(FileUpload.uploaded_at <= date_to_obj)
            except ValueError:
                pass
        
        # Get uploads with pagination
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        uploads = query.order_by(FileUpload.uploaded_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # Augment uploads for display
        for upload in uploads.items:
            augment_file_upload(upload)
        
        return render_template('upload_history.html',
                             uploads=uploads,
                             upload_type=upload_type,
                             date_from=date_from,
                             date_to=date_to)
        
    except Exception as e:
        logger.error(f"Error loading upload history: {e}")
        flash('Error loading upload history', 'error')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# ADDITIONAL ROUTES
# ==========================================

@employee_import_bp.route('/upload-overtime')
@login_required
@supervisor_required
def upload_overtime():
    """Dedicated overtime upload page"""
    try:
        # Get overtime statistics
        total_employees = Employee.query.count()
        employees_with_ot = db.session.query(OvertimeHistory.employee_id).distinct().count()
        employees_without_ot = total_employees - employees_with_ot
        
        # Get recent overtime uploads
        recent_uploads = FileUpload.query.filter_by(
            upload_type='overtime'
        ).order_by(FileUpload.uploaded_at.desc()).limit(5).all()
        
        for upload in recent_uploads:
            augment_file_upload(upload)
        
        # Calculate average OT
        avg_ot = db.session.query(func.avg(OvertimeHistory.hours)).scalar() or 0
        
        return render_template('upload_overtime.html',
                             total_employees=total_employees,
                             employees_with_ot=employees_with_ot,
                             employees_without_ot=employees_without_ot,
                             recent_uploads=recent_uploads,
                             average_ot=round(avg_ot, 1))
        
    except Exception as e:
        logger.error(f"Error loading overtime upload page: {e}")
        flash('Error loading page', 'error')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# API ENDPOINTS
# ==========================================

@employee_import_bp.route('/api/upload-details/<int:upload_id>')
@login_required
@supervisor_required
def get_upload_details(upload_id):
    """Get detailed information about an upload"""
    try:
        upload = FileUpload.query.get_or_404(upload_id)
        augment_file_upload(upload)
        
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
# ERROR HANDLERS
# ==========================================

@employee_import_bp.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not found'}), 404
    flash('Page not found', 'error')
    return redirect(url_for('supervisor.dashboard'))

@employee_import_bp.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    db.session.rollback()
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500
    flash('An unexpected error occurred', 'error')
    return redirect(url_for('supervisor.dashboard'))
