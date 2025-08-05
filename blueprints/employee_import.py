# blueprints/employee_import.py - COMPLETE FILE WITH ALL ROUTES
"""
Employee Import Blueprint - Complete implementation
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
import random
import string

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
            filename = secure_filename(file.filename)
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
            
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            
            # Process the file
            upload_type = request.form.get('upload_type', 'employees')
            replace_all = request.form.get('replace_all') == 'true'
            
            try:
                if upload_type == 'employees':
                    result = process_employee_file(filepath, replace_all)
                elif upload_type == 'overtime':
                    result = process_overtime_file(filepath)
                else:
                    result = {'success': False, 'error': 'Invalid upload type'}
                
                # Record upload
                file_upload = FileUpload(
                    filename=filename,
                    file_type=upload_type,
                    uploaded_by_id=current_user.id,
                    upload_date=datetime.now(),
                    records_processed=result.get('processed', 0),
                    records_failed=len(result.get('errors', [])),
                    status='completed' if result['success'] else 'failed',
                    error_details='\n'.join(result.get('errors', [])) if not result['success'] else None
                )
                db.session.add(file_upload)
                db.session.commit()
                
                if result['success']:
                    flash(f'Successfully processed {result.get("processed", 0)} records', 'success')
                else:
                    flash(f'Upload failed: {result.get("error", "Unknown error")}', 'danger')
                
            except Exception as e:
                flash(f'Error processing file: {str(e)}', 'danger')
            
            finally:
                # Clean up file
                if os.path.exists(filepath):
                    os.remove(filepath)
        else:
            flash('Invalid file type. Please upload an Excel file (.xlsx or .xls)', 'danger')
    
    # Get all required data for template
    recent_uploads = FileUpload.query.order_by(FileUpload.upload_date.desc()).limit(10).all()
    
    # Get employee statistics
    total_employees = Employee.query.count()
    active_employees = Employee.query.filter_by(is_active=True).count()
    
    # Count employees without accounts (no username)
    employees_without_accounts = Employee.query.filter(
        or_(Employee.username == None, Employee.username == '')
    ).count()
    
    # Get crew distribution
    crew_counts = db.session.query(
        Employee.crew, func.count(Employee.id)
    ).filter(Employee.is_active == True).group_by(Employee.crew).all()
    
    crew_distribution = {}
    for crew, count in crew_counts:
        crew_distribution[crew if crew else 'Unassigned'] = count
    
    # Ensure all crews are represented
    for crew in ['A', 'B', 'C', 'D']:
        if crew not in crew_distribution:
            crew_distribution[crew] = 0
    
    # Calculate additional stats
    stats = {
        'total_employees': total_employees,
        'active_employees': active_employees,
        'crews': {
            'A': crew_distribution.get('A', 0),
            'B': crew_distribution.get('B', 0),
            'C': crew_distribution.get('C', 0),
            'D': crew_distribution.get('D', 0),
        },
        'missing_overtime': Employee.query.filter(
            ~Employee.id.in_(
                db.session.query(OvertimeHistory.employee_id).distinct()
            )
        ).count()
    }
    
    # Check if we can create accounts
    ACCOUNT_CREATION_AVAILABLE = True  # Set based on your logic
    
    return render_template('upload_employees_enhanced.html', 
                         recent_uploads=recent_uploads,
                         stats=stats,
                         total_employees=total_employees,
                         employees_without_accounts=employees_without_accounts,
                         crew_distribution=crew_distribution,
                         account_creation_available=ACCOUNT_CREATION_AVAILABLE)

@employee_import_bp.route('/upload-overtime', methods=['GET', 'POST'])
@login_required
def upload_overtime():
    """Upload overtime history"""
    if not current_user.is_supervisor:
        flash('Only supervisors can upload overtime data', 'danger')
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
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
            
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            
            try:
                result = process_overtime_file(filepath)
                
                if result['success']:
                    flash(f'Successfully imported overtime for {result.get("processed", 0)} employees', 'success')
                else:
                    flash(f'Error: {result.get("error", "Unknown error")}', 'danger')
                    
            except Exception as e:
                flash(f'Error processing file: {str(e)}', 'danger')
            finally:
                if os.path.exists(filepath):
                    os.remove(filepath)
    
    # Get statistics - matching what template expects
    total_ot_hours = db.session.query(func.sum(OvertimeHistory.hours_worked)).scalar() or 0
    employees_with_ot = db.session.query(OvertimeHistory.employee_id).distinct().count()
    
    # Get recent uploads for overtime type
    recent_uploads = FileUpload.query.filter_by(file_type='overtime').order_by(
        FileUpload.upload_date.desc()
    ).limit(5).all()
    
    return render_template('upload_overtime.html', 
                         total_ot_hours=total_ot_hours,
                         employees_with_ot=employees_with_ot,
                         recent_uploads=recent_uploads)

@employee_import_bp.route('/upload-history')
@login_required
def upload_history():
    """View upload history"""
    if not current_user.is_supervisor:
        flash('Only supervisors can view upload history', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    # Get filter parameters
    file_type = request.args.get('type')
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

@employee_import_bp.route('/validate-upload', methods=['POST'])
@login_required
def validate_upload():
    """Validate uploaded file before processing"""
    if not current_user.is_supervisor:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    upload_type = request.form.get('upload_type', 'employees')
    
    if file and allowed_file(file.filename):
        try:
            # Read file
            df = pd.read_excel(file)
            
            # Validate based on type
            if upload_type == 'employees':
                errors = validate_employee_data(df)
            elif upload_type == 'overtime':
                errors = validate_overtime_data(df)
            else:
                errors = ['Invalid upload type']
            
            return jsonify({
                'success': len(errors) == 0,
                'errors': errors,
                'row_count': len(df),
                'preview': df.head(5).to_dict('records') if len(errors) == 0 else []
            })
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    return jsonify({'success': False, 'error': 'Invalid file type'}), 400

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
        'Email': ['john.doe@company.com', 'jane.smith@company.com', 'bob.j@company.com'],
        'Crew': ['A', 'B', 'C'],
        'Position': ['Operator', 'Lead Operator', 'Supervisor'],
        'Department': ['Production', 'Production', 'Management'],
        'Hire Date': ['2020-01-15', '2019-05-20', '2018-03-10'],
        'Phone': ['555-0101', '555-0102', '555-0103'],
        'Skills': ['Forklift,Safety', 'Forklift,Electrical', 'Leadership,Safety']
    }
    
    # Create DataFrame
    df = pd.DataFrame(template_data)
    
    # Create Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Employee Data', index=False)
        
        # Get workbook and worksheet
        workbook = writer.book
        worksheet = writer.sheets['Employee Data']
        
        # Format
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#366092',
            'font_color': 'white'
        })
        
        # Apply header format
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
        
        # Auto-fit columns
        for column in df:
            column_width = max(df[column].astype(str).map(len).max(), len(column)) + 2
            col_idx = df.columns.get_loc(column)
            worksheet.set_column(col_idx, col_idx, column_width)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='employee_upload_template.xlsx'
    )

@employee_import_bp.route('/download-overtime-template')
@login_required
def download_overtime_template():
    """Download overtime upload template"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    # Create template with employee data and 13 weeks
    employees = Employee.query.filter_by(is_active=True).all()
    
    data = []
    for emp in employees[:5]:  # Show first 5 as example
        row = {
            'Employee ID': emp.employee_id,
            'Employee Name': emp.name
        }
        
        # Add 13 weeks of columns
        for i in range(1, 14):
            week_date = date.today() - timedelta(weeks=i)
            week_str = week_date.strftime('%Y-%m-%d')
            row[f'Week {week_str}'] = random.choice([0, 4, 8, 12, 16])
        
        data.append(row)
    
    df = pd.DataFrame(data)
    
    # Create Excel file
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Overtime Data', index=False)
        
        # Format
        workbook = writer.book
        worksheet = writer.sheets['Overtime Data']
        
        # Header format
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#E67E22',
            'font_color': 'white'
        })
        
        # Apply formatting
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='overtime_upload_template.xlsx'
    )

@employee_import_bp.route('/download-bulk-update-template/<template_type>')
@login_required
def download_bulk_update_template(template_type):
    """Download bulk update template"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    if template_type == 'employee':
        # Get current employees
        employees = Employee.query.filter_by(is_active=True).all()
        
        data = []
        for emp in employees:
            data.append({
                'Employee ID': emp.employee_id,
                'First Name': emp.name.split()[0] if emp.name else '',
                'Last Name': ' '.join(emp.name.split()[1:]) if emp.name and len(emp.name.split()) > 1 else '',
                'Email': emp.email,
                'Crew': emp.crew,
                'Position': emp.position.name if emp.position else '',
                'Department': emp.department,
                'Action': 'UPDATE'  # UPDATE, DELETE, or SKIP
            })
        
        df = pd.DataFrame(data)
        filename = 'bulk_update_employees.xlsx'
        
    else:
        return "Invalid template type", 400
    
    # Create Excel file
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

# Export routes
@employee_import_bp.route('/export-current-employees')
@login_required
def export_current_employees():
    """Export current employee data"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    # Get all employees
    employees = Employee.query.all()
    
    data = []
    for emp in employees:
        data.append({
            'Employee ID': emp.employee_id,
            'First Name': emp.name.split()[0] if emp.name else '',
            'Last Name': ' '.join(emp.name.split()[1:]) if emp.name and len(emp.name.split()) > 1 else '',
            'Email': emp.email,
            'Username': emp.username,
            'Crew': emp.crew or '',
            'Position': emp.position.name if emp.position else '',
            'Department': emp.department or '',
            'Hire Date': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '',
            'Seniority Date': emp.seniority_date.strftime('%Y-%m-%d') if emp.seniority_date else '',
            'Phone': emp.phone or '',
            'Is Supervisor': 'Yes' if emp.is_supervisor else 'No',
            'Is Active': 'Yes' if emp.is_active else 'No',
            'Skills': ','.join([s.name for s in emp.skills])
        })
    
    df = pd.DataFrame(data)
    
    # Create Excel file
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Employees', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'employees_export_{date.today().strftime("%Y%m%d")}.xlsx'
    )

@employee_import_bp.route('/export-current-overtime')
@login_required
def export_current_overtime():
    """Export current overtime data"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    # Get overtime data
    overtime = OvertimeHistory.query.join(Employee).order_by(
        Employee.name, OvertimeHistory.week_ending.desc()
    ).all()
    
    data = []
    for ot in overtime:
        data.append({
            'Employee ID': ot.employee.employee_id,
            'Employee Name': ot.employee.name,
            'Crew': ot.employee.crew,
            'Week Ending': ot.week_ending.strftime('%Y-%m-%d'),
            'Regular Hours': ot.regular_hours or 40,
            'Overtime Hours': ot.hours_worked,
            'Total Hours': (ot.regular_hours or 40) + ot.hours_worked,
            'Type': ot.overtime_type or 'Regular',
            'Reason': ot.reason or ''
        })
    
    df = pd.DataFrame(data)
    
    # Create Excel file
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Overtime History', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'overtime_export_{date.today().strftime("%Y%m%d")}.xlsx'
    )

# Processing functions
def process_employee_file(filepath, replace_all=False):
    """Process uploaded employee file"""
    try:
        # Read Excel file
        df = pd.read_excel(filepath)
        
        # Validate columns
        required_columns = ['Employee ID', 'First Name', 'Last Name', 'Crew']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return {
                'success': False,
                'error': f'Missing required columns: {", ".join(missing_columns)}'
            }
        
        processed = 0
        errors = []
        credentials = []
        
        # Delete all if replace_all
        if replace_all:
            Employee.query.filter_by(is_supervisor=False).delete()
            db.session.commit()
        
        # Process each row
        for idx, row in df.iterrows():
            try:
                employee_id = str(row['Employee ID']).strip()
                
                # Check if employee exists
                employee = Employee.query.filter_by(employee_id=employee_id).first()
                
                if not employee:
                    # Create new employee
                    employee = Employee()
                    employee.employee_id = employee_id
                    
                    # Generate username and password
                    first_name = str(row['First Name']).strip()
                    last_name = str(row['Last Name']).strip()
                    employee.username = generate_username(first_name, last_name)
                    
                    temp_password = generate_temp_password()
                    employee.set_password(temp_password)
                    employee.must_change_password = True
                    employee.first_login = True
                    
                    credentials.append({
                        'employee_id': employee_id,
                        'name': f"{first_name} {last_name}",
                        'username': employee.username,
                        'password': temp_password
                    })
                
                # Update employee data
                employee.name = f"{row['First Name']} {row['Last Name']}".strip()
                employee.email = row.get('Email', f"{employee.username}@company.com")
                employee.crew = row['Crew'] if row['Crew'] in ['A', 'B', 'C', 'D'] else None
                
                # Handle position
                if 'Position' in row and pd.notna(row['Position']):
                    position = Position.query.filter_by(name=row['Position']).first()
                    if position:
                        employee.position_id = position.id
                
                employee.department = row.get('Department', '')
                
                # Handle dates
                if 'Hire Date' in row and pd.notna(row['Hire Date']):
                    employee.hire_date = pd.to_datetime(row['Hire Date']).date()
                    employee.seniority_date = employee.hire_date
                
                employee.phone = str(row.get('Phone', ''))
                employee.is_active = True
                employee.account_created_date = datetime.now()
                
                # Handle skills
                if 'Skills' in row and pd.notna(row['Skills']):
                    skill_names = [s.strip() for s in str(row['Skills']).split(',')]
                    employee.skills = []
                    for skill_name in skill_names:
                        skill = Skill.query.filter_by(name=skill_name).first()
                        if skill:
                            employee.skills.append(skill)
                
                db.session.add(employee)
                processed += 1
                
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
        
        # Commit all changes
        db.session.commit()
        
        # Save credentials if any
        if credentials:
            save_credentials_file(credentials)
        
        return {
            'success': True,
            'processed': processed,
            'errors': errors,
            'credentials_generated': len(credentials)
        }
        
    except Exception as e:
        db.session.rollback()
        return {
            'success': False,
            'error': str(e)
        }

def process_overtime_file(filepath):
    """Process uploaded overtime file"""
    try:
        # Read Excel file
        df = pd.read_excel(filepath)
        
        processed = 0
        errors = []
        
        # Process each row
        for idx, row in df.iterrows():
            try:
                employee_id = str(row['Employee ID']).strip()
                employee = Employee.query.filter_by(employee_id=employee_id).first()
                
                if not employee:
                    errors.append(f"Row {idx + 2}: Employee {employee_id} not found")
                    continue
                
                # Process each week column
                for col in df.columns:
                    if col.startswith('Week '):
                        week_date_str = col.replace('Week ', '')
                        try:
                            week_date = pd.to_datetime(week_date_str).date()
                            hours = float(row[col]) if pd.notna(row[col]) else 0
                            
                            if hours > 0:
                                # Check if record exists
                                ot_record = OvertimeHistory.query.filter_by(
                                    employee_id=employee.id,
                                    week_ending=week_date
                                ).first()
                                
                                if not ot_record:
                                    ot_record = OvertimeHistory(
                                        employee_id=employee.id,
                                        week_ending=week_date,
                                        hours_worked=hours,
                                        regular_hours=40,
                                        overtime_type='regular',
                                        created_at=datetime.now()
                                    )
                                else:
                                    ot_record.hours_worked = hours
                                
                                db.session.add(ot_record)
                                
                        except:
                            continue
                
                processed += 1
                
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
        
        # Commit all changes
        db.session.commit()
        
        return {
            'success': True,
            'processed': processed,
            'errors': errors
        }
        
    except Exception as e:
        db.session.rollback()
        return {
            'success': False,
            'error': str(e)
        }

def validate_employee_data(df):
    """Validate employee data"""
    errors = []
    
    # Check required columns
    required_columns = ['Employee ID', 'First Name', 'Last Name', 'Crew']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        errors.append(f'Missing required columns: {", ".join(missing_columns)}')
        return errors
    
    # Check for duplicates
    if df['Employee ID'].duplicated().any():
        dup_ids = df[df['Employee ID'].duplicated()]['Employee ID'].tolist()
        errors.append(f'Duplicate Employee IDs found: {", ".join(map(str, dup_ids))}')
    
    # Validate each row
    for idx, row in df.iterrows():
        row_num = idx + 2
        
        # Check required fields
        if pd.isna(row['Employee ID']) or str(row['Employee ID']).strip() == '':
            errors.append(f'Row {row_num}: Missing Employee ID')
        
        if pd.isna(row['First Name']) or str(row['First Name']).strip() == '':
            errors.append(f'Row {row_num}: Missing First Name')
        
        if pd.isna(row['Last Name']) or str(row['Last Name']).strip() == '':
            errors.append(f'Row {row_num}: Missing Last Name')
        
        # Validate crew
        if pd.notna(row['Crew']) and row['Crew'] not in ['A', 'B', 'C', 'D']:
            errors.append(f'Row {row_num}: Invalid crew "{row["Crew"]}" (must be A, B, C, or D)')
        
        # Validate email format
        if 'Email' in row and pd.notna(row['Email']):
            email = str(row['Email']).strip()
            if '@' not in email:
                errors.append(f'Row {row_num}: Invalid email format')
    
    return errors

def validate_overtime_data(df):
    """Validate overtime data"""
    errors = []
    
    # Check required columns
    if 'Employee ID' not in df.columns:
        errors.append('Missing required column: Employee ID')
        return errors
    
    # Check for week columns
    week_columns = [col for col in df.columns if col.startswith('Week ')]
    if not week_columns:
        errors.append('No week columns found. Columns should be named "Week YYYY-MM-DD"')
    
    # Validate employee IDs exist
    for idx, row in df.iterrows():
        employee_id = str(row['Employee ID']).strip()
        if not Employee.query.filter_by(employee_id=employee_id).first():
            errors.append(f'Row {idx + 2}: Employee {employee_id} not found')
    
    return errors

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

# Error handler
@employee_import_bp.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404
