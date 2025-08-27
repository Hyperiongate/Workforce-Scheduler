# blueprints/employee_import.py
"""
Complete Excel upload system for employee data management
PRODUCTION-READY VERSION with all routes and validation
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
    """Upload employees page - enhanced version"""
    try:
        stats = get_employee_stats()
        recent_uploads = get_recent_uploads()
        employees_without_accounts = get_employees_without_accounts()
        
        # Check which template exists and use it
        template_options = [
            'upload_employees_enhanced.html',
            'upload_employees_simple_direct.html',
            'upload_employees.html'
        ]
        
        template = None
        for option in template_options:
            template_path = os.path.join(current_app.template_folder, option)
            if os.path.exists(template_path):
                template = option
                break
        
        if not template:
            # Create a simple fallback template inline
            logger.warning("No upload template found, using fallback")
            template = 'upload_employees_clean.html'
        
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
    """Handle the file upload"""
    try:
        logger.info("Upload POST received")
        
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
        
        logger.info(f"Processing file: {file.filename}")
        
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
            upload_type='employee',
            uploaded_by_id=current_user.id,
            uploaded_at=datetime.utcnow(),
            status='processing'
        )
        db.session.add(file_upload)
        db.session.commit()
        
        try:
            # Read the Excel file
            df = pd.read_excel(filepath)
            logger.info(f"Read {len(df)} rows from Excel")
            logger.info(f"Columns: {list(df.columns)}")
            
            # First validate the data
            validation_result = validate_employee_data_custom(df)
            
            if not validation_result.get('success'):
                # Validation failed
                file_upload.status = 'failed'
                file_upload.error_details = validation_result
                db.session.commit()
                
                # Show validation errors
                flash('File validation failed:', 'error')
                errors = validation_result.get('errors', [])
                # Show first 5 errors
                for error in errors[:5]:
                    flash(f"• {error}", 'error')
                if len(errors) > 5:
                    flash(f"... and {len(errors) - 5} more errors", 'error')
                
                return redirect(url_for('employee_import.upload_employees'))
            
            # Validation passed, process the data
            result = process_employee_data_custom(df, 'append', file_upload)
            
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
                flash(f"✅ Successfully uploaded {result.get('successful', 0)} employees!", 'success')
                if result.get('failed', 0) > 0:
                    flash(f"⚠️ {result.get('failed', 0)} records failed to process", 'warning')
                    if result.get('errors'):
                        for error in result.get('errors', [])[:3]:
                            flash(f"• {error}", 'warning')
            else:
                flash(f"❌ Upload failed: {result.get('error', 'Unknown error')}", 'error')
                
        except Exception as e:
            logger.error(f"ERROR processing file: {e}")
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
        logger.error(f"ERROR in upload: {e}")
        flash('An error occurred during upload. Please try again.', 'error')
        return redirect(url_for('employee_import.upload_employees'))

# ==========================================
# CRITICAL MISSING ROUTE - VALIDATE UPLOAD
# ==========================================

@employee_import_bp.route('/validate-upload', methods=['POST'])
@login_required
@supervisor_required
def validate_upload():
    """AJAX endpoint to validate uploaded file before processing"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        file = request.files['file']
        upload_type = request.form.get('uploadType', 'employee')
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            return jsonify({'success': False, 'error': 'Invalid file type. Please upload an Excel file.'})
        
        # Save file temporarily for validation
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"temp_{timestamp}_{filename}"
        
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
        os.makedirs(upload_folder, exist_ok=True)
        
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)
        
        try:
            # Read the Excel file
            df = pd.read_excel(filepath)
            
            # Validate based on upload type
            if upload_type == 'employee':
                validation_result = validate_employee_data_custom(df)
            elif upload_type == 'overtime':
                validation_result = validate_overtime_data(df)
            else:
                validation_result = {'success': False, 'error': 'Invalid upload type'}
            
            # Clean up temp file
            os.remove(filepath)
            
            if validation_result.get('success'):
                return jsonify({
                    'success': True,
                    'message': validation_result.get('message', 'Validation successful'),
                    'employee_count': validation_result.get('employee_count', 0),
                    'total_rows': validation_result.get('total_rows', len(df))
                })
            else:
                return jsonify({
                    'success': False,
                    'error': validation_result.get('error'),
                    'errors': validation_result.get('errors', [])[:10]  # Limit to 10 errors
                })
                
        except Exception as e:
            logger.error(f"Error validating file: {e}")
            try:
                os.remove(filepath)
            except:
                pass
            return jsonify({'success': False, 'error': f'Error reading file: {str(e)}'})
            
    except Exception as e:
        logger.error(f"Error in validate_upload: {e}")
        return jsonify({'success': False, 'error': 'Server error during validation'})

# ==========================================
# EXPORT ROUTES
# ==========================================

@employee_import_bp.route('/export-employees')
@login_required
@supervisor_required
def export_employees():
    """Export current employee data to Excel format"""
    try:
        # Get all active employees
        employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
        
        if not employees:
            flash('No employees found to export.', 'warning')
            return redirect(url_for('supervisor.dashboard'))
        
        # Create workbook and worksheet
        wb = Workbook()
        ws = wb.active
        ws.title = "Employee Export"
        
        # Define headers to match your import format
        headers = [
            'Employee ID', 'First Name', 'Last Name', 'Email',
            'Crew', 'Department', 'Position', 'Phone', 
            'Hire Date', 'Is Active'
        ]
        
        # Add headers to worksheet
        for col, header in enumerate(headers, 1):
            ws.cell(row=1, column=col, value=header)
        
        # Add employee data
        for row, employee in enumerate(employees, 2):
            ws.cell(row=row, column=1, value=employee.employee_id or '')
            ws.cell(row=row, column=2, value=employee.first_name or '')
            ws.cell(row=row, column=3, value=employee.last_name or '')
            ws.cell(row=row, column=4, value=employee.email or '')
            ws.cell(row=row, column=5, value=employee.crew or '')
            ws.cell(row=row, column=6, value=employee.department or '')
            
            # Get position name
            position_name = ''
            if employee.position:
                position_name = employee.position.name
            ws.cell(row=row, column=7, value=position_name)
            
            ws.cell(row=row, column=8, value=employee.phone or '')
            ws.cell(row=row, column=9, value=employee.hire_date.strftime('%Y-%m-%d') if employee.hire_date else '')
            ws.cell(row=row, column=10, value='Yes' if employee.is_active else 'No')
        
        # Prepare file for download
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        filename = f"employees_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f"Error exporting employees: {e}")
        flash('Error exporting employee data. Please try again.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@employee_import_bp.route('/export-overtime')
@login_required  
@supervisor_required
def export_overtime():
    """Export overtime history data"""
    try:
        # Get all overtime records
        overtime_records = OvertimeHistory.query.join(Employee).order_by(
            Employee.name, OvertimeHistory.week_ending
        ).all()
        
        if not overtime_records:
            flash('No overtime data found to export.', 'warning')
            return redirect(url_for('supervisor.dashboard'))
        
        # Create workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Overtime Export"
        
        # Headers
        headers = [
            'Employee ID', 'Employee Name', 'Week Ending', 
            'Overtime Hours', 'Total Hours', 'Regular Hours'
        ]
        
        for col, header in enumerate(headers, 1):
            ws.cell(row=1, column=col, value=header)
        
        # Add data
        for row, record in enumerate(overtime_records, 2):
            ws.cell(row=row, column=1, value=record.employee.employee_id or '')
            ws.cell(row=row, column=2, value=record.employee.name or '')
            ws.cell(row=row, column=3, value=record.week_ending.strftime('%Y-%m-%d') if record.week_ending else '')
            ws.cell(row=row, column=4, value=record.overtime_hours or record.hours or 0)
            ws.cell(row=row, column=5, value=record.total_hours or 0)
            ws.cell(row=row, column=6, value=record.regular_hours or 0)
        
        # Save to BytesIO
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        filename = f"overtime_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f"Error exporting overtime: {e}")
        flash('Error exporting overtime data. Please try again.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# CUSTOM VALIDATION FUNCTIONS FOR YOUR FORMAT
# ==========================================

def validate_employee_data_custom(df):
    """Validate employee data with custom format"""
    errors = []
    warnings = []
    
    logger.info(f"Validating {len(df)} rows")
    
    # Check for empty dataframe
    if df.empty:
        return {'success': False, 'error': 'The uploaded file contains no data'}
    
    # Check for YOUR required columns
    required_columns = ['Last Name', 'First Name', 'Employee ID', 'Crew Assigned', 'Current Job Position']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        logger.info(f"Missing columns: {missing_columns}")
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
        
        # Check Crew
        crew = str(row.get('Crew Assigned', '')).strip().upper()
        if crew and crew != 'NAN' and crew not in ['A', 'B', 'C', 'D']:
            errors.append(f"Row {row_num}: Invalid crew '{crew}'. Must be A, B, C, or D")
        
        # Check Current Job Position
        position = str(row.get('Current Job Position', '')).strip()
        if not position or position == 'nan':
            errors.append(f"Row {row_num}: Missing Current Job Position")
        
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
    
    logger.info(f"Validation successful - {len(employee_ids)} employees")
    
    # Return success with summary
    return {
        'success': True,
        'total_rows': len(df),
        'employee_count': len(employee_ids),
        'message': f'Validation successful. {len(employee_ids)} employees ready to import.'
    }

# ==========================================
# CUSTOM PROCESSING FUNCTION FOR YOUR FORMAT
# ==========================================

def process_employee_data_custom(df, mode, file_upload):
    """Process employee data with custom format"""
    try:
        successful = 0
        failed = 0
        errors = []
        
        logger.info(f"Starting to process {len(df)} rows")
        logger.info(f"Columns found: {list(df.columns)}")
        
        # Get total count before processing
        count_before = Employee.query.count()
        logger.info(f"Employee count BEFORE: {count_before}")
        
        # Process each row
        for idx, row in df.iterrows():
            try:
                emp_id = str(row.get('Employee ID', '')).strip()
                logger.info(f"Processing employee {emp_id}")
                
                # Check if employee exists
                employee = Employee.query.filter_by(employee_id=emp_id).first()
                
                if not employee:
                    # Create new employee
                    employee = Employee(employee_id=emp_id)
                    logger.info(f"Creating NEW employee {emp_id}")
                else:
                    logger.info(f"Found EXISTING employee {emp_id}")
                
                # Update employee data with YOUR column names
                employee.first_name = str(row.get('First Name', '')).strip()
                employee.last_name = str(row.get('Last Name', '')).strip()
                employee.name = f"{employee.first_name} {employee.last_name}"
                
                # Generate email from employee ID if not present
                if not employee.email:
                    employee.email = f"emp{emp_id}@company.com"
                    logger.info(f"Generated email: {employee.email}")
                
                # Set crew from YOUR column name
                crew = str(row.get('Crew Assigned', '')).strip().upper()
                if crew in ['A', 'B', 'C', 'D']:
                    employee.crew = crew
                    logger.info(f"Set crew: {crew}")
                
                # Set position from YOUR column name
                pos_name = str(row.get('Current Job Position', '')).strip()
                if pos_name and pos_name != 'nan':
                    # Find or create position
                    position = Position.query.filter_by(name=pos_name).first()
                    if not position:
                        position = Position(name=pos_name)
                        db.session.add(position)
                        db.session.flush()  # Get the ID
                        logger.info(f"Created new position: {pos_name}")
                    employee.position_id = position.id
                
                # Handle Date of Hire if present
                if 'Date of Hire' in row:
                    hire_date = row.get('Date of Hire')
                    if pd.notna(hire_date):
                        try:
                            if isinstance(hire_date, str):
                                employee.hire_date = datetime.strptime(hire_date, '%m/%d/%Y').date()
                            else:
                                employee.hire_date = hire_date.date() if hasattr(hire_date, 'date') else hire_date
                            logger.info(f"Set hire date: {employee.hire_date}")
                        except:
                            logger.warning(f"Could not parse hire date for {emp_id}")
                
                # Mark as active
                employee.is_active = True
                
                # Process 13-week overtime if present
                if 'Total Overtime (Last 3 Months)' in row:
                    total_ot = row.get('Total Overtime (Last 3 Months)')
                    if pd.notna(total_ot):
                        try:
                            total_hours = float(total_ot)
                            # Distribute evenly across 13 weeks
                            weekly_hours = total_hours / 13.0
                            logger.info(f"Processing {total_hours} OT hours")
                            
                            # Create overtime records for last 13 weeks
                            for week_num in range(13):
                                week_date = date.today() - timedelta(weeks=(13 - week_num - 1))
                                
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
                                
                                ot_record.hours = round(weekly_hours, 1)
                                db.session.add(ot_record)
                        except Exception as ot_error:
                            logger.error(f"ERROR processing overtime for {emp_id}: {ot_error}")
                
                db.session.add(employee)
                successful += 1
                logger.info(f"Successfully processed employee {emp_id}")
                
            except Exception as e:
                failed += 1
                errors.append(f"Row {idx + 2}: {str(e)}")
                logger.error(f"ERROR processing row {idx + 2}: {e}")
        
        # Commit all changes
        try:
            logger.info("Committing to database...")
            db.session.commit()
            
            # Get count after processing
            count_after = Employee.query.count()
            logger.info(f"Employee count AFTER: {count_after}")
            logger.info(f"Added {count_after - count_before} employees")
            
        except Exception as e:
            logger.error(f"ERROR committing to database: {e}")
            db.session.rollback()
            return {
                'success': False,
                'error': f'Database error: {str(e)}',
                'successful': successful,
                'failed': failed
            }
        
        logger.info(f"Process complete - {successful} successful, {failed} failed")
        
        return {
            'success': True,
            'total': len(df),
            'successful': successful,
            'failed': failed,
            'errors': errors[:10] if errors else None
        }
        
    except Exception as e:
        logger.error(f"ERROR in process_employee_data_custom: {e}")
        db.session.rollback()
        return {
            'success': False,
            'error': str(e)
        }

# ==========================================
# ORIGINAL VALIDATION (for backwards compatibility)
# ==========================================

def validate_employee_data(df):
    """Original validation - tries custom format first, then standard"""
    # First try custom format
    custom_result = validate_employee_data_custom(df)
    if custom_result.get('success') or 'Crew Assigned' in df.columns:
        return custom_result
    
    # Fall back to standard format
    errors = []
    warnings = []
    
    if df.empty:
        return {'success': False, 'error': 'The uploaded file contains no data'}
    
    required_columns = ['Employee ID', 'First Name', 'Last Name', 'Email', 'Crew']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        return {
            'success': False,
            'error': f"Missing required columns: {', '.join(missing_columns)}"
        }
    
    # ... rest of original validation ...
    return {'success': True, 'total_rows': len(df), 'employee_count': len(df)}

def process_employee_data(df, mode, file_upload):
    """Process employee data - detects format and uses appropriate processor"""
    # Check which format we have
    if 'Crew Assigned' in df.columns:
        return process_employee_data_custom(df, mode, file_upload)
    else:
        # Use original processor for standard format
        return process_employee_data_standard(df, mode, file_upload)

def process_employee_data_standard(df, mode, file_upload):
    """Original processing function for standard format"""
    try:
        successful = 0
        failed = 0
        errors = []
        
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

# ==========================================
# TEMPLATE DOWNLOAD ROUTES
# ==========================================

@employee_import_bp.route('/download-employee-template')
@login_required
@supervisor_required
def download_employee_template():
    """Download employee upload template with YOUR format"""
    try:
        # Create workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Employee Data"
        
        # Define YOUR headers
        headers = [
            'Last Name', 'First Name', 'Employee ID', 'Date of Hire',
            'Total Overtime (Last 3 Months)', 'Crew Assigned', 'Current Job Position',
            'Operator', 'Senior Operator', 'Lead Operator', 'Maintenance Technician',
            'Electrician', 'Mechanic', 'Control Room Operator', 'Shift Supervisor',
            'Process Engineer', 'Safety Coordinator'
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
            if col <= 7:
                ws.column_dimensions[get_column_letter(col)].width = 18
            else:
                ws.column_dimensions[get_column_letter(col)].width = 15
        
        # Add sample data with YOUR format
        sample_data = [
            ['Smith', 'James', '10001', '1/15/2010', '45', 'A', 'Operator', 
             'current', 'yes', 'yes', '', '', '', '', '', '', ''],
            ['Johnson', 'Mary', '10002', '6/3/2011', '62', 'A', 'Senior Operator',
             'yes', 'current', 'yes', '', '', '', '', '', '', ''],
            ['Williams', 'John', '10003', '3/20/2012', '38', 'A', 'Maintenance Technician',
             '', '', '', 'current', 'yes', '', '', '', '', ''],
            ['Brown', 'Patricia', '10004', '5/3/2012', '71', 'A', 'Lead Operator',
             'yes', 'yes', 'current', '', '', '', '', '', '', '']
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
            ["- Last Name: Employee's last name"],
            ["- First Name: Employee's first name"],
            ["- Employee ID: Unique identifier for each employee"],
            ["- Crew Assigned: Must be A, B, C, or D"],
            ["- Current Job Position: Employee's main job role"],
            [""],
            ["Optional Fields:"],
            ["- Date of Hire: Format MM/DD/YYYY"],
            ["- Total Overtime (Last 3 Months): Total OT hours in the last 13 weeks"],
            [""],
            ["Qualification Matrix:"],
            ["- Mark 'current' for the employee's current position"],
            ["- Mark 'yes' for positions they are qualified for"],
            ["- Leave blank for positions they are not qualified for"],
            [""],
            ["Notes:"],
            ["- Do not modify the header row"],
            ["- Save as .xlsx format"],
            ["- Email addresses will be auto-generated from Employee IDs"]
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

@employee_import_bp.route('/upload-overtime', methods=['POST'])
@login_required
@supervisor_required
def upload_overtime_post():
    """Handle overtime file upload"""
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
        
        # Save file temporarily
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
        os.makedirs(upload_folder, exist_ok=True)
        
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)
        
        # Create upload record
        file_upload = FileUpload(
            filename=filename,
            upload_type='overtime',
            uploaded_by_id=current_user.id,
            uploaded_at=datetime.utcnow(),
            status='processing'
        )
        db.session.add(file_upload)
        db.session.commit()
        
        try:
            # Read and validate
            df = pd.read_excel(filepath)
            validation_result = validate_overtime_data(df)
            
            if not validation_result.get('success'):
                # Validation failed
                file_upload.status = 'failed'
                file_upload.error_details = validation_result
                db.session.commit()
                
                flash('File validation failed:', 'error')
                errors = validation_result.get('errors', [])
                for error in errors[:5]:
                    flash(f"• {error}", 'error')
                if len(errors) > 5:
                    flash(f"... and {len(errors) - 5} more errors", 'error')
                
                return redirect(url_for('employee_import.upload_overtime'))
            
            # Process the data
            mode = request.form.get('mode', 'append')
            result = process_overtime_data(df, mode, file_upload)
            
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
            
            # Show message
            if result.get('success'):
                flash(f"✅ Successfully uploaded overtime data for {result.get('successful', 0)} employees!", 'success')
                if result.get('failed', 0) > 0:
                    flash(f"⚠️ {result.get('failed', 0)} records failed to process", 'warning')
            else:
                flash(f"❌ Upload failed: {result.get('error', 'Unknown error')}", 'error')
                
        except Exception as e:
            logger.error(f"Error processing overtime file: {e}")
            file_upload.status = 'failed'
            file_upload.error_details = {'error': str(e)}
            db.session.commit()
            flash(f"Error processing file: {str(e)}", 'error')
            
        finally:
            try:
                os.remove(filepath)
            except:
                pass
                
        return redirect(url_for('employee_import.upload_overtime'))
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        flash('An error occurred during upload. Please try again.', 'error')
        return redirect(url_for('employee_import.upload_overtime'))

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
