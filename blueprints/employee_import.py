# blueprints/employee_import.py - Complete working version with all fixes

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, current_app, session
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import Employee, UploadHistory, db, OvertimeHistory
from datetime import datetime, date, timedelta
import pandas as pd
import os
import json
import traceback

employee_import_bp = Blueprint('employee_import', __name__)

# Import account generator if it exists
try:
    from utils.account_generator import AccountGenerator, create_accounts_after_import
    ACCOUNT_CREATION_AVAILABLE = True
except ImportError:
    ACCOUNT_CREATION_AVAILABLE = False
    print("Warning: Account generator not available")

# Import Excel handler if it exists
try:
    from utils.excel_upload_handler import ExcelUploadHandler
    EXCEL_HANDLER_AVAILABLE = True
except ImportError:
    EXCEL_HANDLER_AVAILABLE = False
    print("Warning: Excel upload handler not available")

@employee_import_bp.route('/upload-employees', methods=['GET', 'POST'])
@login_required
def upload_employees():
    """Enhanced employee upload with account creation"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisor role required.', 'danger')
        return redirect(url_for('employee.dashboard'))
        
    if request.method == 'POST':
        try:
            # Get file and options
            file = request.files.get('file')
            upload_type = request.form.get('upload_type', 'employee')
            replace_all = request.form.get('replace_all', 'false') == 'true'
            create_accounts = request.form.get('create_accounts', 'true') == 'true'
            
            if not file or file.filename == '':
                flash('No file selected', 'error')
                return redirect(url_for('employee_import.upload_employees'))
                
            # Save uploaded file
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            saved_filename = f"{timestamp}_{filename}"
            
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
                
            filepath = os.path.join(upload_folder, saved_filename)
            file.save(filepath)
            
            # Create upload history record
            upload_record = UploadHistory(
                filename=filename,
                file_path=saved_filename,
                upload_type=upload_type,
                uploaded_by_id=current_user.id,
                status='processing'
            )
            db.session.add(upload_record)
            db.session.commit()
            
            # Process based on upload type
            if upload_type == 'employee':
                result = process_employee_upload(filepath, replace_all, create_accounts)
            elif upload_type == 'overtime':
                result = process_overtime_upload(filepath, replace_all)
            elif upload_type == 'bulk_update':
                result = process_bulk_update(filepath)
            else:
                result = {'success': False, 'error': 'Unknown upload type'}
                
            # Update upload record
            upload_record.status = 'completed' if result['success'] else 'failed'
            upload_record.rows_processed = result.get('processed', 0)
            upload_record.rows_failed = result.get('failed', 0)
            upload_record.error_details = json.dumps(result.get('errors', []))
            db.session.commit()
            
            if result['success']:
                flash(f"Successfully uploaded {result.get('processed', 0)} records", 'success')
            else:
                flash(f"Upload failed: {result.get('error', 'Unknown error')}", 'danger')
                
        except Exception as e:
            flash(f'Error processing upload: {str(e)}', 'danger')
            if 'upload_record' in locals():
                upload_record.status = 'failed'
                upload_record.error_details = str(e)
                db.session.commit()
                
        return redirect(url_for('employee_import.upload_employees'))
        
    # GET request - show upload page
    try:
        # Get statistics
        total_employees = Employee.query.count()
        recent_uploads = UploadHistory.query.filter_by(
            uploaded_by_id=current_user.id
        ).order_by(UploadHistory.uploaded_at.desc()).limit(5).all()
        
        # Check for employees without accounts
        employees_without_accounts = Employee.query.filter(
            (Employee.username == None) | (Employee.username == '')
        ).count()
        
        # Get crew distribution
        crew_distribution = db.session.query(
            Employee.crew, 
            db.func.count(Employee.id)
        ).group_by(Employee.crew).all()
        
        crew_distribution = [
            {'crew': crew or 'Unassigned', 'count': count} 
            for crew, count in crew_distribution
        ]
        
    except Exception as e:
        print(f"Error getting statistics: {e}")
        total_employees = 0
        recent_uploads = []
        employees_without_accounts = 0
        crew_distribution = []
        
    return render_template('upload_employees_enhanced.html',
                         recent_uploads=recent_uploads,
                         total_employees=total_employees,
                         employees_without_accounts=employees_without_accounts,
                         crew_distribution=crew_distribution,
                         account_creation_available=ACCOUNT_CREATION_AVAILABLE)


@employee_import_bp.route('/validate-upload', methods=['POST'])
@login_required
def validate_upload():
    """Validate an uploaded file without importing - COMPLETE VERSION"""
    
    # Check permissions
    if not current_user.is_supervisor:
        return jsonify({
            'success': False, 
            'error': 'Unauthorized - Supervisor access required'
        }), 403
    
    try:
        # Check file presence
        if 'file' not in request.files:
            return jsonify({
                'success': False, 
                'error': 'No file provided. Please select a file to upload.'
            })
        
        file = request.files['file']
        upload_type = request.form.get('type', 'employee')
        
        # Check file selection
        if file.filename == '':
            return jsonify({
                'success': False, 
                'error': 'No file selected. Please choose a file to upload.'
            })
        
        # Validate file extension
        if not file.filename.endswith(('.xlsx', '.xls')):
            return jsonify({
                'success': False, 
                'error': 'Invalid file format. Please upload an Excel file (.xlsx or .xls).'
            })
        
        # Attempt to read Excel file with proper error handling
        try:
            # Determine expected sheet name based on upload type
            sheet_name_map = {
                'employee': 'Employee Data',
                'overtime': 'Overtime Data',
                'bulk_update': 'Bulk Update'
            }
            expected_sheet = sheet_name_map.get(upload_type, 'Employee Data')
            
            # Try to read the specific sheet
            df = pd.read_excel(file, sheet_name=expected_sheet)
            
        except ValueError as e:
            # Handle missing sheet names
            if 'Worksheet named' in str(e) or 'Worksheet' in str(e):
                # Get available sheets for helpful error message
                try:
                    file.seek(0)  # Reset file pointer
                    excel_file = pd.ExcelFile(file)
                    available_sheets = excel_file.sheet_names
                    return jsonify({
                        'success': False, 
                        'error': f'Invalid sheet name. Expected "{expected_sheet}" but file contains: {", ".join(available_sheets)}'
                    })
                except:
                    return jsonify({
                        'success': False, 
                        'error': f'Invalid sheet name. Expected "{expected_sheet}"'
                    })
            else:
                return jsonify({
                    'success': False, 
                    'error': f'Error reading Excel file: {str(e)}'
                })
                
        except Exception as e:
            # Handle general Excel reading errors
            return jsonify({
                'success': False, 
                'error': f'Error reading file: {str(e)}. Please ensure this is a valid Excel file.'
            })
        
        # Check for empty dataframe
        if df.empty:
            return jsonify({
                'success': False, 
                'error': 'The uploaded file contains no data. Please check your file.'
            })
        
        # Initialize validation results
        errors = []
        warnings = []
        row_count = len(df)
        
        # Type-specific validation
        if upload_type == 'employee':
            errors, warnings = validate_employee_data(df)
        elif upload_type == 'overtime':
            errors, warnings = validate_overtime_data(df)
        elif upload_type == 'bulk_update':
            errors, warnings = validate_bulk_update_data(df)
        
        # Return appropriate response
        if errors:
            return jsonify({
                'success': False,
                'errors': errors[:20],  # Limit to first 20 errors
                'total_errors': len(errors),
                'warnings': warnings,
                'row_count': row_count,
                'upload_type': upload_type
            })
        else:
            return jsonify({
                'success': True,
                'message': 'Validation passed!',
                'warnings': warnings,
                'row_count': row_count,
                'upload_type': upload_type,
                'details': {
                    'total_rows': row_count,
                    'columns_found': list(df.columns)
                }
            })
            
    except Exception as e:
        # Catch-all error handler
        return jsonify({
            'success': False,
            'error': f'Unexpected error during validation: {str(e)}',
            'details': traceback.format_exc() if current_app.debug else None
        }), 500


def validate_employee_data(df):
    """Validate employee data and return errors and warnings"""
    errors = []
    warnings = []
    
    # Required columns
    required_fields = ['Employee ID', 'First Name', 'Last Name', 'Email', 'Crew', 'Position']
    
    # Check for required columns
    missing_columns = [col for col in required_fields if col not in df.columns]
    if missing_columns:
        errors.append(f'Missing required columns: {", ".join(missing_columns)}')
        return errors, warnings
    
    # Validate each row
    employee_ids = set()
    email_set = set()
    
    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel row number (header is row 1)
        
        # Check Employee ID
        emp_id = str(row.get('Employee ID', '')).strip()
        if pd.isna(row['Employee ID']) or emp_id == '':
            errors.append(f'Row {row_num}: Missing Employee ID')
        elif emp_id in employee_ids:
            errors.append(f'Row {row_num}: Duplicate Employee ID "{emp_id}"')
        else:
            employee_ids.add(emp_id)
        
        # Check required fields
        if pd.isna(row['First Name']) or str(row['First Name']).strip() == '':
            errors.append(f'Row {row_num}: Missing First Name')
            
        if pd.isna(row['Last Name']) or str(row['Last Name']).strip() == '':
            errors.append(f'Row {row_num}: Missing Last Name')
        
        # Validate Email
        email = str(row.get('Email', '')).strip().lower()
        if pd.isna(row['Email']) or email == '':
            errors.append(f'Row {row_num}: Missing Email')
        elif '@' not in email or '.' not in email.split('@')[-1]:
            errors.append(f'Row {row_num}: Invalid email format "{email}"')
        elif email in email_set:
            errors.append(f'Row {row_num}: Duplicate email "{email}"')
        else:
            email_set.add(email)
        
        # Validate Crew
        crew = str(row.get('Crew', '')).strip().upper()
        if pd.isna(row['Crew']) or crew == '':
            errors.append(f'Row {row_num}: Missing Crew assignment')
        elif crew not in ['A', 'B', 'C', 'D']:
            errors.append(f'Row {row_num}: Invalid crew "{crew}" (must be A, B, C, or D)')
        
        # Check Position
        if pd.isna(row['Position']) or str(row['Position']).strip() == '':
            errors.append(f'Row {row_num}: Missing Position')
    
    # Check for existing employees (warnings only)
    try:
        existing_employees = Employee.query.all()
        existing_ids = {emp.employee_id for emp in existing_employees}
        new_ids = employee_ids - existing_ids
        update_ids = employee_ids & existing_ids
        
        if new_ids:
            warnings.append(f'{len(new_ids)} new employee(s) will be added')
        if update_ids:
            warnings.append(f'{len(update_ids)} existing employee(s) will be updated')
    except:
        pass
        
    return errors, warnings


def validate_overtime_data(df):
    """Validate overtime data and return errors and warnings"""
    errors = []
    warnings = []
    
    # Required columns
    required_fields = ['Employee ID', 'Employee Name']
    
    # Check for required columns
    missing_columns = [col for col in required_fields if col not in df.columns]
    if missing_columns:
        errors.append(f'Missing required columns: {", ".join(missing_columns)}')
        return errors, warnings
    
    # Check for week columns
    week_columns = [col for col in df.columns if str(col).startswith('Week ')]
    if len(week_columns) < 13:
        warnings.append(f'Expected 13 weeks of data, found {len(week_columns)} week columns')
    
    # Validate each row
    for idx, row in df.iterrows():
        row_num = idx + 2
        
        # Check Employee ID
        if pd.isna(row['Employee ID']) or str(row['Employee ID']).strip() == '':
            errors.append(f'Row {row_num}: Missing Employee ID')
        
        # Validate overtime hours
        for week_col in week_columns:
            if week_col in row and not pd.isna(row[week_col]):
                try:
                    hours = float(row[week_col])
                    if hours < 0:
                        errors.append(f'Row {row_num}, {week_col}: Negative hours not allowed')
                    elif hours > 168:  # More than hours in a week
                        errors.append(f'Row {row_num}, {week_col}: Invalid hours ({hours} > 168)')
                except (ValueError, TypeError):
                    errors.append(f'Row {row_num}, {week_col}: Invalid number format')
    
    return errors, warnings


def validate_bulk_update_data(df):
    """Validate bulk update data and return errors and warnings"""
    errors = []
    warnings = []
    
    # Required column for bulk update
    if 'Employee ID' not in df.columns:
        errors.append('Missing required column: Employee ID')
        return errors, warnings
    
    # Check each row
    for idx, row in df.iterrows():
        row_num = idx + 2
        
        # Check Employee ID
        if pd.isna(row['Employee ID']) or str(row['Employee ID']).strip() == '':
            errors.append(f'Row {row_num}: Missing Employee ID')
        
        # Validate crew if present
        if 'Crew' in df.columns and not pd.isna(row.get('Crew')):
            crew = str(row['Crew']).strip().upper()
            if crew and crew not in ['A', 'B', 'C', 'D']:
                errors.append(f'Row {row_num}: Invalid crew "{crew}"')
        
        # Validate email if present
        if 'Email' in df.columns and not pd.isna(row.get('Email')):
            email = str(row['Email']).strip().lower()
            if email and ('@' not in email or '.' not in email.split('@')[-1]):
                errors.append(f'Row {row_num}: Invalid email format')
    
    # Count updates
    update_count = len(df[df['Employee ID'].notna()])
    warnings.append(f'{update_count} employee(s) will be updated')
    
    return errors, warnings


def process_employee_upload(filepath, replace_all=False, create_accounts=True):
    """Process employee data upload"""
    try:
        # Read Excel file
        df = pd.read_excel(filepath, sheet_name='Employee Data')
        
        if replace_all:
            # Delete all existing employees if replace_all is True
            Employee.query.delete()
            db.session.commit()
        
        processed = 0
        failed = 0
        errors = []
        new_employees = []
        
        for idx, row in df.iterrows():
            try:
                emp_id = str(row['Employee ID']).strip()
                
                # Check if employee exists
                employee = Employee.query.filter_by(employee_id=emp_id).first()
                
                if not employee:
                    # Create new employee
                    employee = Employee(employee_id=emp_id)
                    new_employees.append(employee)
                
                # Update employee data
                employee.first_name = str(row['First Name']).strip()
                employee.last_name = str(row['Last Name']).strip()
                employee.name = f"{employee.first_name} {employee.last_name}"
                employee.email = str(row['Email']).strip().lower()
                employee.crew = str(row['Crew']).strip().upper()
                employee.position = str(row['Position']).strip()
                
                # Optional fields
                if 'Department' in row:
                    employee.department = str(row.get('Department', '')).strip()
                
                if 'Hire Date' in row and not pd.isna(row['Hire Date']):
                    try:
                        employee.hire_date = pd.to_datetime(row['Hire Date']).date()
                    except:
                        pass
                
                if 'Phone' in row:
                    employee.phone = str(row.get('Phone', '')).strip()
                
                if 'Is Supervisor' in row:
                    is_sup = str(row.get('Is Supervisor', 'No')).strip().lower()
                    employee.is_supervisor = is_sup in ['yes', 'true', '1']
                
                if employee not in db.session:
                    db.session.add(employee)
                
                processed += 1
                
            except Exception as e:
                failed += 1
                errors.append(f"Row {idx + 2}: {str(e)}")
        
        # Commit all changes
        db.session.commit()
        
        # Create accounts if requested and available
        if create_accounts and ACCOUNT_CREATION_AVAILABLE and new_employees:
            try:
                account_results = create_accounts_after_import(new_employees)
                return {
                    'success': True,
                    'processed': processed,
                    'failed': failed,
                    'errors': errors,
                    'accounts_created': account_results.get('created', 0)
                }
            except Exception as e:
                print(f"Account creation error: {e}")
        
        return {
            'success': True,
            'processed': processed,
            'failed': failed,
            'errors': errors
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'processed': 0,
            'failed': 0
        }


def process_overtime_upload(filepath, replace_all=False):
    """Process overtime data upload"""
    try:
        # Read Excel file
        df = pd.read_excel(filepath, sheet_name='Overtime Data')
        
        processed = 0
        failed = 0
        errors = []
        
        # Get week columns
        week_columns = [col for col in df.columns if str(col).startswith('Week ')]
        
        for idx, row in df.iterrows():
            try:
                emp_id = str(row['Employee ID']).strip()
                employee = Employee.query.filter_by(employee_id=emp_id).first()
                
                if not employee:
                    errors.append(f"Row {idx + 2}: Employee ID '{emp_id}' not found")
                    failed += 1
                    continue
                
                # Clear existing overtime if replace_all
                if replace_all:
                    OvertimeHistory.query.filter_by(employee_id=employee.id).delete()
                
                # Process each week
                for i, week_col in enumerate(week_columns):
                    if week_col in row and not pd.isna(row[week_col]):
                        hours = float(row[week_col])
                        if hours > 0:
                            # Calculate week date (assuming weeks go backwards from current)
                            week_date = date.today() - timedelta(weeks=(13 - i - 1))
                            
                            # Check if record exists
                            ot_record = OvertimeHistory.query.filter_by(
                                employee_id=employee.id,
                                week_start=week_date
                            ).first()
                            
                            if not ot_record:
                                ot_record = OvertimeHistory(
                                    employee_id=employee.id,
                                    week_start=week_date
                                )
                            
                            ot_record.hours_worked = hours
                            db.session.add(ot_record)
                
                processed += 1
                
            except Exception as e:
                failed += 1
                errors.append(f"Row {idx + 2}: {str(e)}")
        
        db.session.commit()
        
        return {
            'success': True,
            'processed': processed,
            'failed': failed,
            'errors': errors
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'processed': 0,
            'failed': 0
        }


def process_bulk_update(filepath):
    """Process bulk update file"""
    try:
        # Read Excel file
        df = pd.read_excel(filepath, sheet_name='Bulk Update')
        
        processed = 0
        failed = 0
        errors = []
        
        for idx, row in df.iterrows():
            try:
                emp_id = str(row['Employee ID']).strip()
                employee = Employee.query.filter_by(employee_id=emp_id).first()
                
                if not employee:
                    errors.append(f"Row {idx + 2}: Employee ID '{emp_id}' not found")
                    failed += 1
                    continue
                
                # Update only provided fields
                if 'First Name' in row and not pd.isna(row['First Name']):
                    employee.first_name = str(row['First Name']).strip()
                
                if 'Last Name' in row and not pd.isna(row['Last Name']):
                    employee.last_name = str(row['Last Name']).strip()
                
                if 'First Name' in row or 'Last Name' in row:
                    employee.name = f"{employee.first_name} {employee.last_name}"
                
                if 'Email' in row and not pd.isna(row['Email']):
                    employee.email = str(row['Email']).strip().lower()
                
                if 'Crew' in row and not pd.isna(row['Crew']):
                    employee.crew = str(row['Crew']).strip().upper()
                
                if 'Position' in row and not pd.isna(row['Position']):
                    employee.position = str(row['Position']).strip()
                
                if 'Department' in row and not pd.isna(row['Department']):
                    employee.department = str(row['Department']).strip()
                
                if 'Phone' in row and not pd.isna(row['Phone']):
                    employee.phone = str(row['Phone']).strip()
                
                processed += 1
                
            except Exception as e:
                failed += 1
                errors.append(f"Row {idx + 2}: {str(e)}")
        
        db.session.commit()
        
        return {
            'success': True,
            'processed': processed,
            'failed': failed,
            'errors': errors
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'processed': 0,
            'failed': 0
        }


@employee_import_bp.route('/download-template/<template_type>')
@login_required
def download_template(template_type):
    """Download Excel template for uploads"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('employee.dashboard'))
    
    try:
        if template_type == 'employee':
            # Create employee template
            template_data = {
                'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
                'First Name': ['John', 'Jane', 'Bob'],
                'Last Name': ['Doe', 'Smith', 'Johnson'],
                'Email': ['john.doe@company.com', 'jane.smith@company.com', 'bob.johnson@company.com'],
                'Crew': ['A', 'B', 'C'],
                'Position': ['Operator', 'Technician', 'Supervisor'],
                'Department': ['Production', 'Maintenance', 'Production'],
                'Hire Date': ['2020-01-15', '2019-06-01', '2021-03-20'],
                'Phone': ['555-0101', '555-0102', '555-0103'],
                'Emergency Contact': ['Mary Doe', 'Jim Smith', 'Alice Johnson'],
                'Emergency Phone': ['555-0201', '555-0202', '555-0203'],
                'Skills': ['Forklift, Safety', 'Electrical, HVAC', 'Leadership, Forklift'],
                'Is Supervisor': ['No', 'No', 'Yes']
            }
            df = pd.DataFrame(template_data)
            sheet_name = 'Employee Data'
            filename = 'employee_upload_template.xlsx'
            
        elif template_type == 'overtime':
            # Create overtime template with 13 weeks
            template_data = {
                'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
                'Employee Name': ['John Doe', 'Jane Smith', 'Bob Johnson']
            }
            # Add 13 week columns
            for i in range(13):
                template_data[f'Week {i+1}'] = [8, 4, 0]  # Sample hours
            
            df = pd.DataFrame(template_data)
            sheet_name = 'Overtime Data'
            filename = 'overtime_upload_template.xlsx'
            
        elif template_type == 'bulk_update':
            # Create bulk update template
            template_data = {
                'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
                'First Name': ['', '', ''],
                'Last Name': ['', '', ''],
                'Email': ['', '', ''],
                'Crew': ['', '', ''],
                'Position': ['', '', ''],
                'Department': ['', '', ''],
                'Phone': ['', '', '']
            }
            df = pd.DataFrame(template_data)
            sheet_name = 'Bulk Update'
            filename = 'bulk_update_template.xlsx'
            
        else:
            flash('Invalid template type', 'danger')
            return redirect(url_for('employee_import.upload_employees'))
        
        # Create Excel file in memory
        from io import BytesIO
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            # Add instructions sheet
            instructions = pd.DataFrame({
                'Instructions': [
                    f'This is the template for {template_type} upload',
                    'Do not modify column headers',
                    'Required fields must be filled for all rows',
                    'Employee ID must be unique',
                    'Crew must be A, B, C, or D',
                    'Dates should be in YYYY-MM-DD format',
                    'For bulk updates, leave fields blank to keep existing values'
                ]
            })
            instructions.to_excel(writer, sheet_name='Instructions', index=False)
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        flash(f'Error generating template: {str(e)}', 'danger')
        return redirect(url_for('employee_import.upload_employees'))


@employee_import_bp.route('/export-employees')
@login_required
def export_employees():
    """Export current employee data"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('employee.dashboard'))
    
    try:
        # Get all employees
        employees = Employee.query.order_by(Employee.last_name).all()
        
        # Create DataFrame
        data = []
        for emp in employees:
            data.append({
                'Employee ID': emp.employee_id,
                'First Name': emp.first_name,
                'Last Name': emp.last_name,
                'Email': emp.email,
                'Crew': emp.crew,
                'Position': emp.position,
                'Department': emp.department or '',
                'Hire Date': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '',
                'Phone': emp.phone or '',
                'Emergency Contact': emp.emergency_contact or '',
                'Emergency Phone': emp.emergency_phone or '',
                'Skills': ', '.join(emp.skills) if hasattr(emp, 'skills') and emp.skills else '',
                'Is Supervisor': 'Yes' if emp.is_supervisor else 'No',
                'Username': emp.username or '',
                'Account Active': 'Yes' if emp.username else 'No'
            })
        
        df = pd.DataFrame(data)
        
        # Create Excel file
        from io import BytesIO
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Employee Data', index=False)
            
            # Auto-fit columns
            worksheet = writer.sheets['Employee Data']
            for i, col in enumerate(df.columns):
                column_width = max(df[col].astype(str).apply(len).max(), len(col)) + 2
                worksheet.set_column(i, i, min(column_width, 50))
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'employee_export_{datetime.now().strftime("%Y%m%d")}.xlsx'
        )
        
    except Exception as e:
        flash(f'Error exporting employees: {str(e)}', 'danger')
        return redirect(url_for('employee_import.upload_employees'))


@employee_import_bp.route('/upload-history')
@login_required
def upload_history():
    """View upload history"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('employee.dashboard'))
    
    # Get filter parameters
    upload_type = request.args.get('type', 'all')
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    
    # Build query
    query = UploadHistory.query
    
    # Only show uploads by current user unless admin
    query = query.filter_by(uploaded_by_id=current_user.id)
    
    if upload_type != 'all':
        query = query.filter_by(upload_type=upload_type)
    
    if date_from:
        query = query.filter(UploadHistory.uploaded_at >= date_from)
    
    if date_to:
        query = query.filter(UploadHistory.uploaded_at <= date_to)
    
    # Get results
    uploads = query.order_by(UploadHistory.uploaded_at.desc()).all()
    
    return render_template('upload_history.html', uploads=uploads)


@employee_import_bp.route('/delete-upload/<int:upload_id>', methods=['POST'])
@login_required
def delete_upload(upload_id):
    """Delete upload record"""
    if not current_user.is_supervisor:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        upload = UploadHistory.query.get_or_404(upload_id)
        
        # Only allow deletion of own uploads
        if upload.uploaded_by_id != current_user.id:
            return jsonify({'success': False, 'error': 'Cannot delete uploads by other users'}), 403
        
        # Delete associated file if exists
        if upload.file_path:
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
            filepath = os.path.join(upload_folder, upload.file_path)
            if os.path.exists(filepath):
                os.remove(filepath)
        
        db.session.delete(upload)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@employee_import_bp.route('/download-upload/<int:upload_id>')
@login_required
def download_upload(upload_id):
    """Download original uploaded file"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('employee.dashboard'))
    
    try:
        upload = UploadHistory.query.get_or_404(upload_id)
        
        # Check permission
        if upload.uploaded_by_id != current_user.id:
            flash('Cannot download uploads by other users', 'danger')
            return redirect(url_for('employee_import.upload_history'))
        
        # Check if file exists
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
        filepath = os.path.join(upload_folder, upload.file_path)
        
        if not os.path.exists(filepath):
            flash('File not found', 'danger')
            return redirect(url_for('employee_import.upload_history'))
        
        return send_file(
            filepath,
            as_attachment=True,
            download_name=upload.filename
        )
        
    except Exception as e:
        flash(f'Error downloading file: {str(e)}', 'danger')
        return redirect(url_for('employee_import.upload_history'))
