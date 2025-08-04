# blueprints/employee_import.py - Enhanced version with account creation

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, current_app, session
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import Employee, UploadHistory, db, OvertimeHistory
from datetime import datetime, date, timedelta
import pandas as pd
import os
import json

employee_import_bp = Blueprint('employee_import', __name__)

# Import account generator if it exists
try:
    from utils.account_generator import AccountGenerator, create_accounts_after_import
    ACCOUNT_CREATION_AVAILABLE = True
except ImportError:
    ACCOUNT_CREATION_AVAILABLE = False
    print("Warning: Account generator not available")

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
        
    # Clear from session after download
    session.pop('credentials_file', None)
    
    return send_file(filepath, as_attachment=True,
                    download_name=f'employee_credentials_{datetime.now().strftime("%Y%m%d")}.xlsx',
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


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
        
    uploads = query.order_by(UploadHistory.uploaded_at.desc()).all()
    
    return render_template('upload_history.html', uploads=uploads)


@employee_import_bp.route('/api/upload-history')
@login_required
def api_upload_history():
    """API endpoint for upload history"""
    if not current_user.is_supervisor:
        return jsonify([])
        
    uploads = UploadHistory.query.filter_by(
        uploaded_by_id=current_user.id
    ).order_by(UploadHistory.uploaded_at.desc()).limit(50).all()
    
    return jsonify([{
        'id': u.id,
        'filename': u.filename,
        'upload_type': u.upload_type,
        'status': u.status,
        'uploaded_at': u.uploaded_at.isoformat(),
        'records_processed': u.records_processed,
        'records_created': u.records_created,
        'records_updated': u.records_updated,
        'uploaded_by': u.uploaded_by.name if u.uploaded_by else 'Unknown'
    } for u in uploads])


@employee_import_bp.route('/upload/<int:upload_id>/download')
@login_required
def download_upload_file(upload_id):
    """Download original uploaded file"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('employee.dashboard'))
        
    upload = UploadHistory.query.get_or_404(upload_id)
    
    # Check permissions
    if upload.uploaded_by_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('employee_import.upload_history'))
    
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
    filepath = os.path.join(upload_folder, upload.file_path)
    
    if not os.path.exists(filepath):
        flash('File not found', 'error')
        return redirect(url_for('employee_import.upload_history'))
        
    return send_file(filepath, as_attachment=True,
                    download_name=upload.filename,
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@employee_import_bp.route('/upload-overtime', methods=['GET', 'POST'])
@login_required
def upload_overtime():
    """Dedicated overtime upload page"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisor role required.', 'danger')
        return redirect(url_for('employee.dashboard'))
        
    if request.method == 'POST':
        # Redirect to main upload handler with overtime type
        return redirect(url_for('employee_import.upload_employees'))
        
    # Get statistics for overtime
    total_ot_hours = db.session.query(db.func.sum(OvertimeHistory.overtime_hours)).scalar() or 0
    employees_with_ot = db.session.query(db.func.count(db.func.distinct(OvertimeHistory.employee_id))).scalar() or 0
    
    recent_uploads = UploadHistory.query.filter_by(
        uploaded_by_id=current_user.id,
        upload_type='overtime'
    ).order_by(UploadHistory.uploaded_at.desc()).limit(5).all()
    
    return render_template('upload_overtime.html',
                         total_ot_hours=total_ot_hours,
                         employees_with_ot=employees_with_ot,
                         recent_uploads=recent_uploads).upload_employees'))
                
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
                upload_type=upload_type,
                uploaded_by_id=current_user.id,
                file_path=saved_filename,
                status='processing',
                started_at=datetime.utcnow()
            )
            db.session.add(upload_record)
            db.session.commit()
            
            # Process the file
            if upload_type == 'employee':
                result = process_employee_file(filepath, replace_all=replace_all)
                
                if result['success']:
                    # Create accounts if requested and available
                    if create_accounts and ACCOUNT_CREATION_AVAILABLE and result.get('new_employees'):
                        account_result = create_accounts_after_import(result['new_employees'], db)
                        
                        if account_result['success']:
                            flash(f"Created {account_result['created_count']} new accounts", 'success')
                            
                            # Store credentials file info in session for download
                            session['credentials_file'] = account_result['excel_report']
                            
                            # Update upload record with account info
                            upload_record.notes = json.dumps({
                                'accounts_created': account_result['created_count'],
                                'credentials_file': account_result['excel_report']
                            })
                    
                    # Update upload record
                    upload_record.status = 'completed'
                    upload_record.records_processed = result.get('total_processed', 0)
                    upload_record.records_created = result.get('created', 0)
                    upload_record.records_updated = result.get('updated', 0)
                    upload_record.completed_at = datetime.utcnow()
                    
                    flash(f"Successfully processed {result['total_processed']} employees. "
                          f"Created: {result['created']}, Updated: {result['updated']}", 'success')
                          
                    # Offer credentials download if accounts were created
                    if create_accounts and ACCOUNT_CREATION_AVAILABLE and result.get('new_employees'):
                        return redirect(url_for('employee_import.download_credentials'))
                        
                else:
                    upload_record.status = 'failed'
                    upload_record.error_details = json.dumps(result.get('errors', []))
                    flash(f"Upload failed: {result.get('error', 'Unknown error')}", 'error')
                    
            elif upload_type == 'overtime':
                result = process_overtime_file(filepath, replace_all=replace_all)
                
                if result['success']:
                    upload_record.status = 'completed'
                    upload_record.records_processed = result.get('total_processed', 0)
                    upload_record.completed_at = datetime.utcnow()
                    flash(f"Successfully uploaded overtime data for {result['total_processed']} employees", 'success')
                else:
                    upload_record.status = 'failed'
                    upload_record.error_details = json.dumps(result.get('errors', []))
                    flash(f"Upload failed: {result.get('error', 'Unknown error')}", 'error')
                    
            db.session.commit()
            
        except Exception as e:
            current_app.logger.error(f"Upload error: {str(e)}")
            if 'upload_record' in locals():
                upload_record.status = 'failed'
                upload_record.error_details = str(e)
                db.session.commit()
            flash(f"Error processing file: {str(e)}", 'error')
            
        return redirect(url_for('employee_import.upload_employees'))
        
    # GET request - show upload page
    recent_uploads = UploadHistory.query.filter_by(
        uploaded_by_id=current_user.id
    ).order_by(UploadHistory.uploaded_at.desc()).limit(5).all()
    
    # Get statistics
    total_employees = Employee.query.count()
    employees_without_accounts = Employee.query.filter(
        (Employee.username == None) | (Employee.username == '')
    ).count()
    
    crew_distribution = db.session.query(
        Employee.crew, 
        db.func.count(Employee.id)
    ).group_by(Employee.crew).all()
    
    return render_template('upload_employees_enhanced.html',
                         recent_uploads=recent_uploads,
                         total_employees=total_employees,
                         employees_without_accounts=employees_without_accounts,
                         crew_distribution=crew_distribution,
                         account_creation_available=ACCOUNT_CREATION_AVAILABLE)


@employee_import_bp.route('/validate-upload', methods=['POST'])
@login_required
def validate_upload():
    """Validate an uploaded file without importing"""
    if not current_user.is_supervisor:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
    try:
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
            
        file = request.files['file']
        upload_type = request.form.get('type', 'employee')
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
            
        # Check file extension
        if not file.filename.endswith(('.xlsx', '.xls')):
            return jsonify({'success': False, 'error': 'Invalid file format. Please upload an Excel file.'})
            
        # Read the Excel file
        try:
            if upload_type == 'employee':
                df = pd.read_excel(file, sheet_name='Employee Data')
            elif upload_type == 'overtime':
                df = pd.read_excel(file, sheet_name='Overtime Data')
            else:
                df = pd.read_excel(file)
        except ValueError as e:
            if 'Worksheet named' in str(e):
                return jsonify({
                    'success': False, 
                    'error': f'Invalid sheet name. Expected "{"Employee Data" if upload_type == "employee" else "Overtime Data"}"'
                })
            else:
                return jsonify({'success': False, 'error': f'Error reading Excel file: {str(e)}'})
        except Exception as e:
            return jsonify({'success': False, 'error': f'Error reading file: {str(e)}'})
            
        # Check if dataframe is empty
        if df.empty:
            return jsonify({'success': False, 'error': 'The uploaded file contains no data'})
            
        errors = []
        warnings = []
        
        if upload_type == 'employee':
            # Validate employee data
            required_fields = ['Employee ID', 'First Name', 'Last Name', 'Crew', 'Position', 'Department', 'Hire Date']
            
            # Check for required columns
            missing_columns = [col for col in required_fields if col not in df.columns]
            if missing_columns:
                return jsonify({
                    'success': False, 
                    'error': f'Missing required columns: {", ".join(missing_columns)}'
                })
            
            # Validate each row
            employee_ids = set()
            
            for idx, row in df.iterrows():
                row_num = idx + 2  # Excel row number (header is row 1)
                
                # Check Employee ID
                if pd.isna(row['Employee ID']) or str(row['Employee ID']).strip() == '':
                    errors.append(f'Row {row_num}: Missing Employee ID')
                else:
                    emp_id = str(row['Employee ID']).strip()
                    if emp_id in employee_ids:
                        errors.append(f'Row {row_num}: Duplicate Employee ID "{emp_id}"')
                    employee_ids.add(emp_id)
                
                # Check First Name
                if pd.isna(row['First Name']) or str(row['First Name']).strip() == '':
                    errors.append(f'Row {row_num}: Missing First Name')
                    
                # Check Last Name
                if pd.isna(row['Last Name']) or str(row['Last Name']).strip() == '':
                    errors.append(f'Row {row_num}: Missing Last Name')
                    
                # Check Crew
                if pd.isna(row['Crew']) or str(row['Crew']).strip() == '':
                    errors.append(f'Row {row_num}: Missing Crew')
                elif str(row['Crew']).strip().upper() not in ['A', 'B', 'C', 'D']:
                    errors.append(f'Row {row_num}: Invalid Crew "{row["Crew"]}" (must be A, B, C, or D)')
                    
                # Check Position
                if pd.isna(row['Position']) or str(row['Position']).strip() == '':
                    errors.append(f'Row {row_num}: Missing Position')
                    
                # Check Department
                if pd.isna(row['Department']) or str(row['Department']).strip() == '':
                    errors.append(f'Row {row_num}: Missing Department')
                    
                # Check Hire Date
                if pd.isna(row['Hire Date']):
                    errors.append(f'Row {row_num}: Missing Hire Date')
                else:
                    try:
                        pd.to_datetime(row['Hire Date'])
                    except:
                        errors.append(f'Row {row_num}: Invalid Hire Date format')
                        
                # Check Email (optional but validate format if provided)
                if 'Email' in row and not pd.isna(row['Email']) and str(row['Email']).strip() != '':
                    email = str(row['Email']).strip()
                    if '@' not in email or '.' not in email.split('@')[-1]:
                        warnings.append(f'Row {row_num}: Invalid email format "{email}"')
                        
            # Check for existing employees (for merge operations)
            if not request.form.get('replace_all') == 'true':
                existing_employees = Employee.query.all()
                existing_ids = {emp.employee_id for emp in existing_employees}
                new_ids = employee_ids - existing_ids
                update_ids = employee_ids & existing_ids
                
                if new_ids:
                    warnings.append(f'{len(new_ids)} new employees will be added')
                if update_ids:
                    warnings.append(f'{len(update_ids)} existing employees will be updated')
                    
        elif upload_type == 'overtime':
            # Validate overtime data
            required_fields = ['Employee ID', 'Employee Name']
            
            # Check for required columns
            missing_columns = [col for col in required_fields if col not in df.columns]
            if missing_columns:
                return jsonify({
                    'success': False, 
                    'error': f'Missing required columns: {", ".join(missing_columns)}'
                })
                
            # Check for week columns
            week_columns = [col for col in df.columns if col.startswith('Week ')]
            if len(week_columns) < 13:
                warnings.append(f'Expected 13 weeks of data, found {len(week_columns)}')
                
            # Validate each row
            for idx, row in df.iterrows():
                row_num = idx + 2
                
                # Check Employee ID
                if pd.isna(row['Employee ID']) or str(row['Employee ID']).strip() == '':
                    errors.append(f'Row {row_num}: Missing Employee ID')
                    
                # Validate overtime hours
                for week_col in week_columns:
                    if week_col in row:
                        try:
                            hours = float(row[week_col]) if not pd.isna(row[week_col]) else 0
                            if hours < 0:
                                errors.append(f'Row {row_num}, {week_col}: Negative hours not allowed')
                            elif hours > 40:
                                warnings.append(f'Row {row_num}, {week_col}: Unusually high overtime ({hours} hours)')
                        except:
                            errors.append(f'Row {row_num}, {week_col}: Invalid number format')
                            
        # Return validation results
        if errors:
            return jsonify({
                'success': False,
                'errors': errors[:20],  # Limit to first 20 errors
                'error_count': len(errors),
                'warnings': warnings[:10],
                'row_count': len(df)
            })
        else:
            return jsonify({
                'success': True,
                'message': 'Validation passed!',
                'warnings': warnings,
                'row_count': len(df),
                'data_preview': {
                    'columns': list(df.columns),
                    'sample_row': df.iloc[0].to_dict() if len(df) > 0 else {}
                }
            })
            
    except Exception as e:
        current_app.logger.error(f"Validation error: {str(e)}")
        return jsonify({'success': False, 'error': f'Validation error: {str(e)}'})


def process_employee_file(filepath, replace_all=False):
    """Process uploaded employee file"""
    try:
        # Read Excel file
        df = pd.read_excel(filepath, sheet_name='Employee Data')
        
        # Clean data
        df = df.fillna('')
        
        created = 0
        updated = 0
        errors = []
        new_employees = []
        
        if replace_all:
            # Delete all existing employees (be careful!)
            Employee.query.delete()
            db.session.commit()
        
        for idx, row in df.iterrows():
            try:
                emp_id = str(row['Employee ID']).strip()
                
                # Check if employee exists
                employee = Employee.query.filter_by(employee_id=emp_id).first()
                
                if employee:
                    # Update existing employee
                    updated += 1
                else:
                    # Create new employee
                    employee = Employee(employee_id=emp_id)
                    new_employees.append(employee)
                    created += 1
                
                # Update fields
                # Combine first and last name into name field
                first_name = str(row['First Name']).strip()
                last_name = str(row['Last Name']).strip()
                employee.name = f"{first_name} {last_name}"
                
                employee.crew = str(row['Crew']).strip().upper()
                employee.position_id = None  # You might want to look up position by name
                employee.department = str(row['Department']).strip()
                
                # Parse hire date
                if row['Hire Date']:
                    employee.hire_date = pd.to_datetime(row['Hire Date']).date()
                
                # Optional fields
                if 'Email' in row and row['Email']:
                    employee.email = str(row['Email']).strip()
                else:
                    # Generate default email
                    employee.email = f"{emp_id.lower()}@company.com"
                    
                if 'Phone' in row and row['Phone']:
                    employee.phone = str(row['Phone']).strip()
                
                # Add to session
                if not employee.id:
                    db.session.add(employee)
                    
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                
        # Commit all changes
        db.session.commit()
        
        return {
            'success': True,
            'total_processed': len(df),
            'created': created,
            'updated': updated,
            'errors': errors,
            'new_employees': new_employees
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'errors': [str(e)]
        }


def process_overtime_file(filepath, replace_all=False):
    """Process uploaded overtime file"""
    try:
        # Read Excel file
        df = pd.read_excel(filepath, sheet_name='Overtime Data')
        
        # Clean data
        df = df.fillna(0)
        
        processed = 0
        errors = []
        
        # Get week columns
        week_columns = [col for col in df.columns if col.startswith('Week ')]
        
        # Calculate base date (13 weeks ago from last Monday)
        today = date.today()
        days_since_monday = today.weekday()
        last_monday = today - timedelta(days=days_since_monday)
        base_date = last_monday - timedelta(weeks=13)
        
        for idx, row in df.iterrows():
            try:
                emp_id = str(row['Employee ID']).strip()
                
                # Find employee
                employee = Employee.query.filter_by(employee_id=emp_id).first()
                if not employee:
                    errors.append(f"Row {idx + 2}: Employee {emp_id} not found")
                    continue
                
                # Process each week
                for week_num, week_col in enumerate(week_columns):
                    if week_col in row:
                        week_start = base_date + timedelta(weeks=week_num)
                        overtime_hours = float(row[week_col]) if row[week_col] else 0
                        
                        # Check if record exists
                        ot_record = OvertimeHistory.query.filter_by(
                            employee_id=employee.id,
                            week_start_date=week_start
                        ).first()
                        
                        if ot_record:
                            # Update existing record
                            ot_record.overtime_hours = overtime_hours
                            ot_record.total_hours = 40 + overtime_hours  # Assuming 40 regular hours
                        else:
                            # Create new record
                            ot_record = OvertimeHistory(
                                employee_id=employee.id,
                                week_start_date=week_start,
                                regular_hours=40,
                                overtime_hours=overtime_hours,
                                total_hours=40 + overtime_hours
                            )
                            db.session.add(ot_record)
                
                processed += 1
                
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
        
        # Commit all changes
        db.session.commit()
        
        return {
            'success': True,
            'total_processed': processed,
            'errors': errors
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'errors': [str(e)]
        }


@employee_import_bp.route('/download-employee-template')
@login_required
def download_employee_template():
    """Download employee upload template"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('employee.dashboard'))
    
    # Create template
    template_data = {
        'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
        'First Name': ['John', 'Jane', 'Bob'],
        'Last Name': ['Doe', 'Smith', 'Johnson'],
        'Crew': ['A', 'B', 'C'],
        'Position': ['Operator', 'Lead Operator', 'Supervisor'],
        'Department': ['Production', 'Production', 'Management'],
        'Hire Date': ['2020-01-15', '2019-05-20', '2018-03-10'],
        'Email': ['john.doe@company.com', 'jane.smith@company.com', 'bob.j@company.com'],
        'Phone': ['555-0101', '555-0102', '555-0103']
    }
    
    df = pd.DataFrame(template_data)
    
    # Save to file
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
        
    filename = os.path.join(upload_folder, 'employee_template.xlsx')
    df.to_excel(filename, sheet_name='Employee Data', index=False)
    
    return send_file(filename, as_attachment=True, 
                    download_name='employee_upload_template.xlsx',
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@employee_import_bp.route('/download-overtime-template')
@login_required
def download_overtime_template():
    """Download overtime upload template"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('employee.dashboard'))
    
    # Create template
    template_data = {
        'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
        'Employee Name': ['John Doe', 'Jane Smith', 'Bob Johnson']
    }
    
    # Add 13 weeks of columns
    for i in range(1, 14):
        template_data[f'Week {i}'] = [8, 4, 0]  # Sample overtime hours
    
    df = pd.DataFrame(template_data)
    
    # Save to file
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
        
    filename = os.path.join(upload_folder, 'overtime_template.xlsx')
    df.to_excel(filename, sheet_name='Overtime Data', index=False)
    
    return send_file(filename, as_attachment=True,
                    download_name='overtime_upload_template.xlsx',
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@employee_import_bp.route('/download-credentials')
@login_required
def download_credentials():
    """Download credentials file after account creation"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('employee.dashboard'))
        
    credentials_file = session.get('credentials_file')
    if not credentials_file:
        flash('No credentials file available', 'warning')
        return redirect(url_for('employee_import.upload_employees'))
    
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
    filepath = os.path.join(upload_folder, credentials_file)
    
    if not os.path.exists(filepath):
        flash('Credentials file not found', 'error')
        return redirect(url_for('employee_import
