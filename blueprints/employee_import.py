# blueprints/employee_import.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, current_app
from flask_login import login_required, current_user
from models import db, Employee, Position, Skill, OvertimeHistory, FileUpload, Schedule
from functools import wraps
import pandas as pd
import os
from werkzeug.utils import secure_filename
from datetime import datetime, date, timedelta
import tempfile
from sqlalchemy import text
import re

# Create blueprint
employee_import_bp = Blueprint('employee_import', __name__)

# Decorator for supervisor-only access
def supervisor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_supervisor:
            flash('You must be a supervisor to access this page.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Helper function for email validation
def validate_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

# Main upload page
@employee_import_bp.route('/upload-employees')
@login_required
@supervisor_required
def upload_employees():
    """Display the enhanced employee upload page"""
    # Get recent uploads
    recent_uploads = FileUpload.query.filter_by(
        file_type='employee_import'
    ).order_by(FileUpload.upload_date.desc()).limit(5).all()
    
    # Get statistics
    total_employees = Employee.query.count()
    crew_stats = db.session.query(
        Employee.crew, 
        db.func.count(Employee.id)
    ).group_by(Employee.crew).all()
    
    return render_template('upload_employees_enhanced.html',
                         recent_uploads=recent_uploads,
                         total_employees=total_employees,
                         crew_stats=crew_stats)

# Process employee upload
@employee_import_bp.route('/upload-employees', methods=['POST'])
@login_required
@supervisor_required
def process_employee_upload():
    """Process the uploaded employee Excel file"""
    try:
        if 'file' not in request.files:
            flash('No file selected', 'error')
            return redirect(url_for('employee_import.upload_employees'))
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('employee_import.upload_employees'))
        
        # Get upload type and options
        upload_type = request.form.get('upload_type', 'employee_data')
        replace_all = request.form.get('replace_all') == 'on'
        validate_only = request.form.get('validate_only') == 'on'
        
        # Create upload folder
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
        
        # Get the absolute path for the upload folder
        if not os.path.isabs(upload_folder):
            upload_folder = os.path.join(current_app.root_path, upload_folder)
        
        # Check if path exists and handle accordingly
        try:
            if os.path.exists(upload_folder):
                if os.path.isfile(upload_folder):
                    # If it's a file, use a different name
                    current_app.logger.warning(f"{upload_folder} exists as a file, using alternative")
                    upload_folder = os.path.join(current_app.root_path, 'upload_files')
            
            # Create directory if it doesn't exist
            if not os.path.exists(upload_folder) or not os.path.isdir(upload_folder):
                os.makedirs(upload_folder, exist_ok=True)
                current_app.logger.info(f"Created upload folder: {upload_folder}")
                
        except Exception as e:
            current_app.logger.error(f"Error with upload folder: {str(e)}")
            # Use temp directory as fallback
            upload_folder = tempfile.gettempdir()
            current_app.logger.info(f"Using temp directory: {upload_folder}")
        
        # Save file temporarily
        filename = secure_filename(file.filename)
        temp_path = os.path.join(upload_folder, filename)
        
        try:
            file.save(temp_path)
            current_app.logger.info(f"File saved to: {temp_path}")
        except Exception as e:
            current_app.logger.error(f"Error saving file: {str(e)}")
            raise
        
        # Read and process the file
        df = pd.read_excel(temp_path, sheet_name='Employee Data')
        
        # Process based on replace_all option
        if replace_all and not validate_only:
            # Delete existing employees (except admin) and their related records
            try:
                # Get list of employee IDs to delete
                employees_to_delete = Employee.query.filter(
                    Employee.email != 'admin@workforce.com'
                ).all()
                employee_ids = [emp.id for emp in employees_to_delete]
                
                if employee_ids:
                    # Use raw SQL to delete related records to avoid import issues
                    # Delete employee skills
                    db.session.execute(
                        text("DELETE FROM employee_skills WHERE employee_id = ANY(:employee_ids)"),
                        {'employee_ids': employee_ids}
                    )
                    
                    # Delete overtime history
                    db.session.execute(
                        text("DELETE FROM overtime_history WHERE employee_id = ANY(:employee_ids)"),
                        {'employee_ids': employee_ids}
                    )
                    
                    # Delete schedules
                    db.session.execute(
                        text("DELETE FROM schedule WHERE employee_id = ANY(:employee_ids)"),
                        {'employee_ids': employee_ids}
                    )
                    
                    # Delete time off requests if table exists
                    try:
                        db.session.execute(
                            text("DELETE FROM time_off_request WHERE employee_id = ANY(:employee_ids)"),
                            {'employee_ids': employee_ids}
                        )
                    except:
                        pass  # Table might not exist
                    
                    # Delete shift swap requests if table exists
                    try:
                        db.session.execute(
                            text("DELETE FROM shift_swap_request WHERE requester_id = ANY(:employee_ids) OR target_employee_id = ANY(:employee_ids)"),
                            {'employee_ids': employee_ids}
                        )
                    except:
                        pass  # Table might not exist
                    
                    # Delete additional related records
                    # Coverage requests
                    try:
                        db.session.execute(
                            text("DELETE FROM coverage_request WHERE requester_id = ANY(:employee_ids)"),
                            {'employee_ids': employee_ids}
                        )
                    except:
                        pass
                    
                    # Vacation calendar
                    try:
                        db.session.execute(
                            text("DELETE FROM vacation_calendar WHERE employee_id = ANY(:employee_ids)"),
                            {'employee_ids': employee_ids}
                        )
                    except:
                        pass
                    
                    # Availability
                    try:
                        db.session.execute(
                            text("DELETE FROM availability WHERE employee_id = ANY(:employee_ids)"),
                            {'employee_ids': employee_ids}
                        )
                    except:
                        pass
                    
                    # Overtime opportunities and responses
                    try:
                        db.session.execute(
                            text("DELETE FROM overtime_response WHERE employee_id = ANY(:employee_ids)"),
                            {'employee_ids': employee_ids}
                        )
                        db.session.execute(
                            text("DELETE FROM overtime_opportunities WHERE posted_by_id = ANY(:employee_ids) OR filled_by_id = ANY(:employee_ids)"),
                            {'employee_ids': employee_ids}
                        )
                    except:
                        pass
                    
                    # Messages
                    try:
                        db.session.execute(
                            text("DELETE FROM supervisor_message WHERE sender_id = ANY(:employee_ids) OR recipient_id = ANY(:employee_ids)"),
                            {'employee_ids': employee_ids}
                        )
                        db.session.execute(
                            text("DELETE FROM position_message WHERE sender_id = ANY(:employee_ids)"),
                            {'employee_ids': employee_ids}
                        )
                    except:
                        pass
                    
                    # Maintenance issues
                    try:
                        db.session.execute(
                            text("DELETE FROM maintenance_issue WHERE reporter_id = ANY(:employee_ids) OR assigned_to_id = ANY(:employee_ids)"),
                            {'employee_ids': employee_ids}
                        )
                    except:
                        pass
                    
                    # Commit the deletions
                    db.session.commit()
                    
                    # Now delete the employees
                    Employee.query.filter(Employee.email != 'admin@workforce.com').delete()
                    db.session.commit()
                    
                current_app.logger.info(f"Deleted {len(employee_ids)} employees and their related records")
                
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error during deletion: {str(e)}")
                flash('Error clearing existing data. Please try again.', 'error')
                return redirect(url_for('employee_import.upload_employees'))
        
        # Process each row
        success_count = 0
        error_count = 0
        errors = []
        
        for index, row in df.iterrows():
            try:
                # Get or create employee
                employee_id = str(row.get('Employee ID', '')).strip()
                email = str(row.get('Email', '')).strip()
                
                if not email or not validate_email(email):
                    error_count += 1
                    errors.append(f"Row {index + 2}: Invalid email")
                    continue
                
                if replace_all:
                    employee = Employee()
                else:
                    employee = Employee.query.filter(
                        (Employee.employee_id == employee_id) | 
                        (Employee.email == email)
                    ).first()
                    if not employee:
                        employee = Employee()
                
                # Update employee data
                employee.employee_id = employee_id
                employee.name = f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip()
                employee.email = email
                employee.crew = str(row.get('Crew', '')).strip()
                employee.phone = str(row.get('Phone', '')).strip() if pd.notna(row.get('Phone')) else None
                
                # Set position
                position_name = str(row.get('Position', '')).strip()
                if position_name:
                    position = Position.query.filter_by(name=position_name).first()
                    if not position:
                        # Create position if it doesn't exist
                        position = Position(name=position_name)
                        db.session.add(position)
                        db.session.flush()
                    employee.position_id = position.id
                
                # Set hire date
                if pd.notna(row.get('Hire Date')):
                    employee.hire_date = pd.to_datetime(row['Hire Date']).date()
                
                # Set supervisor status
                is_supervisor = str(row.get('Is Supervisor', 'No')).strip().lower() == 'yes'
                employee.is_supervisor = is_supervisor
                
                # Set default password for new employees
                if not employee.id:
                    employee.set_password('Scheduler123!')
                
                # Add skills if provided
                if 'Skills' in row and pd.notna(row['Skills']):
                    skills_str = str(row['Skills']).strip()
                    if skills_str:
                        # Remove existing skills for this employee
                        if employee.id:
                            db.session.execute(
                                text("DELETE FROM employee_skills WHERE employee_id = :emp_id"),
                                {'emp_id': employee.id}
                            )
                        
                        # Parse and add skills
                        skill_names = [s.strip() for s in skills_str.split(',')]
                        for skill_name in skill_names:
                            if skill_name:
                                skill = Skill.query.filter_by(name=skill_name).first()
                                if not skill:
                                    skill = Skill(name=skill_name)
                                    db.session.add(skill)
                                    db.session.flush()
                                
                                # Add skill to employee after they're saved
                                if not employee.id:
                                    db.session.add(employee)
                                    db.session.flush()
                                
                                db.session.execute(
                                    text("INSERT INTO employee_skills (employee_id, skill_id) VALUES (:emp_id, :skill_id)"),
                                    {'emp_id': employee.id, 'skill_id': skill.id}
                                )
                
                # Save employee
                if not employee.id:
                    db.session.add(employee)
                success_count += 1
                
            except Exception as e:
                error_count += 1
                errors.append(f"Row {index + 2}: {str(e)}")
        
        # Commit all changes
        db.session.commit()
        
        # Create upload record
        upload_record = FileUpload(
            filename=filename,
            file_type='employee_import',
            file_size=os.path.getsize(temp_path),
            uploaded_by_id=current_user.id,
            records_processed=success_count + error_count,
            records_failed=error_count,
            status='completed' if error_count == 0 else 'partial',
            error_details='\n'.join(errors) if errors else None
        )
        db.session.add(upload_record)
        db.session.commit()
        
        # Remove temp file
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                current_app.logger.info(f"Removed temp file: {temp_path}")
        except Exception as e:
            current_app.logger.warning(f"Could not remove temp file: {str(e)}")
        
        # Flash results
        if error_count == 0:
            flash(f'Successfully imported {success_count} employees!', 'success')
        else:
            flash(f'Imported {success_count} employees with {error_count} errors. Check upload history for details.', 'warning')
        
        return redirect(url_for('employee_import.upload_employees'))
        
    except Exception as e:
        current_app.logger.error(f"Error processing upload: {str(e)}")
        flash(f'Error processing file: {str(e)}', 'error')
        return redirect(url_for('employee_import.upload_employees'))

# Overtime upload page
@employee_import_bp.route('/upload-overtime')
@login_required
@supervisor_required
def upload_overtime():
    """Display the overtime upload page"""
    # Get statistics
    total_ot_hours = db.session.query(db.func.sum(OvertimeHistory.overtime_hours)).scalar() or 0
    employees_with_ot = db.session.query(db.func.count(db.func.distinct(OvertimeHistory.employee_id))).scalar() or 0
    total_employees = Employee.query.count()
    
    # Get recent uploads
    recent_uploads = FileUpload.query.filter_by(
        file_type='overtime_import'
    ).order_by(FileUpload.upload_date.desc()).limit(5).all()
    
    return render_template('upload_overtime.html',
                         total_ot_hours=total_ot_hours,
                         employees_with_ot=employees_with_ot,
                         total_employees=total_employees,
                         recent_uploads=recent_uploads)

# Process overtime upload
@employee_import_bp.route('/upload-overtime', methods=['POST'])
@login_required
@supervisor_required
def process_overtime_upload():
    """Process the uploaded overtime Excel file"""
    try:
        if 'file' not in request.files:
            flash('No file selected', 'error')
            return redirect(url_for('employee_import.upload_overtime'))
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('employee_import.upload_overtime'))
        
        # Create upload folder
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
        
        # Get the absolute path for the upload folder
        if not os.path.isabs(upload_folder):
            upload_folder = os.path.join(current_app.root_path, upload_folder)
        
        # Check if path exists and handle accordingly
        try:
            if os.path.exists(upload_folder):
                if os.path.isfile(upload_folder):
                    # If it's a file, use a different name
                    upload_folder = os.path.join(current_app.root_path, 'upload_files')
            
            # Create directory if it doesn't exist
            if not os.path.exists(upload_folder) or not os.path.isdir(upload_folder):
                os.makedirs(upload_folder, exist_ok=True)
                
        except Exception as e:
            # Use temp directory as fallback
            upload_folder = tempfile.gettempdir()
        
        # Save file
        filename = secure_filename(file.filename)
        temp_path = os.path.join(upload_folder, filename)
        file.save(temp_path)
        
        # Read Excel file
        df = pd.read_excel(temp_path, sheet_name='Overtime Data')
        
        # Get options
        replace_all = request.form.get('replace_all') == 'true'
        validate_only = request.form.get('validate_only') == 'on'
        
        if replace_all and not validate_only:
            # Delete existing overtime history
            try:
                OvertimeHistory.query.delete()
                db.session.commit()
                current_app.logger.info("Deleted all existing overtime history")
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error deleting overtime history: {str(e)}")
                flash('Error clearing existing overtime data.', 'error')
        
        # Process each row
        success_count = 0
        error_count = 0
        errors = []
        
        for index, row in df.iterrows():
            try:
                # Find employee
                employee_id = str(row.get('Employee ID', '')).strip()
                employee = Employee.query.filter_by(employee_id=employee_id).first()
                
                if not employee:
                    error_count += 1
                    errors.append(f"Row {index + 2}: Employee ID '{employee_id}' not found")
                    continue
                
                # Process each week
                for week_num in range(1, 14):
                    week_col = f'Week {week_num}'
                    if week_col in row:
                        hours = row[week_col]
                        if pd.notna(hours) and hours > 0:
                            # Calculate week ending date (13 weeks ago + week_num)
                            week_ending = date.today() - timedelta(weeks=(13 - week_num))
                            week_start = week_ending - timedelta(days=6)
                            
                            # Check if record exists
                            existing = OvertimeHistory.query.filter_by(
                                employee_id=employee.id,
                                week_start_date=week_start
                            ).first()
                            
                            if existing:
                                existing.overtime_hours = float(hours)
                                existing.total_hours = 40 + float(hours)
                            else:
                                ot_record = OvertimeHistory(
                                    employee_id=employee.id,
                                    week_start_date=week_start,
                                    regular_hours=40,
                                    overtime_hours=float(hours),
                                    total_hours=40 + float(hours)
                                )
                                db.session.add(ot_record)
                
                success_count += 1
                
            except Exception as e:
                error_count += 1
                errors.append(f"Row {index + 2}: {str(e)}")
        
        # Commit all changes
        db.session.commit()
        
        # Create upload record
        upload_record = FileUpload(
            filename=filename,
            file_type='overtime_import',
            file_size=os.path.getsize(temp_path),
            uploaded_by_id=current_user.id,
            records_processed=success_count + error_count,
            records_success=success_count,
            records_failed=error_count,
            status='completed' if error_count == 0 else 'partial',
            error_details='\n'.join(errors) if errors else None
        )
        db.session.add(upload_record)
        db.session.commit()
        
        # Remove temp file
        try:
            os.remove(temp_path)
        except:
            pass
        
        # Flash results
        if error_count == 0:
            flash(f'Successfully imported overtime data for {success_count} employees!', 'success')
        else:
            flash(f'Imported overtime for {success_count} employees with {error_count} errors.', 'warning')
        
        return redirect(url_for('employee_import.upload_overtime'))
        
    except Exception as e:
        current_app.logger.error(f"Error processing overtime upload: {str(e)}")
        flash(f'Error processing file: {str(e)}', 'error')
        return redirect(url_for('employee_import.upload_overtime'))

# Upload history page
@employee_import_bp.route('/upload-history')
@login_required
@supervisor_required
def upload_history():
    """Display upload history"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    uploads = FileUpload.query.order_by(
        FileUpload.upload_date.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('upload_history.html', uploads=uploads)

# Download template
@employee_import_bp.route('/download-template/<template_type>')
@login_required
@supervisor_required
def download_template(template_type):
    """Download Excel template"""
    try:
        from utils.excel_templates_generator import create_employee_template, create_overtime_template
        
        if template_type == 'employees':
            file_path = create_employee_template()
            return send_file(file_path, as_attachment=True, download_name='employee_upload_template.xlsx')
        elif template_type == 'overtime':
            file_path = create_overtime_template()
            return send_file(file_path, as_attachment=True, download_name='overtime_upload_template.xlsx')
        else:
            flash('Invalid template type', 'error')
            return redirect(url_for('employee_import.upload_employees'))
            
    except Exception as e:
        flash(f'Error generating template: {str(e)}', 'error')
        return redirect(url_for('employee_import.upload_employees'))

# Export current data
@employee_import_bp.route('/export-data/<data_type>')
@login_required
@supervisor_required
def export_data(data_type):
    """Export current data in Excel format"""
    try:
        if data_type == 'employees':
            # Create DataFrame from current employees
            employees = Employee.query.all()
            data = []
            for emp in employees:
                data.append({
                    'Employee ID': emp.employee_id,
                    'First Name': emp.name.split()[0] if emp.name else '',
                    'Last Name': ' '.join(emp.name.split()[1:]) if emp.name and len(emp.name.split()) > 1 else '',
                    'Email': emp.email,
                    'Crew': emp.crew,
                    'Position': emp.position.name if emp.position else '',
                    'Phone': emp.phone or '',
                    'Hire Date': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '',
                    'Is Supervisor': 'Yes' if emp.is_supervisor else 'No',
                    'Skills': ', '.join([skill.name for skill in emp.skills]) if hasattr(emp, 'skills') else ''
                })
            
            df = pd.DataFrame(data)
            
            # Save to Excel
            output_path = os.path.join(tempfile.gettempdir(), f'employees_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Employee Data', index=False)
            
            return send_file(output_path, as_attachment=True, download_name=f'employees_export_{datetime.now().strftime("%Y%m%d")}.xlsx')
            
        elif data_type == 'overtime':
            # Create DataFrame from overtime history
            # Get all employees
            employees = Employee.query.order_by(Employee.name).all()
            
            # Calculate date range for last 13 weeks
            end_date = date.today()
            while end_date.weekday() != 6:  # Find last Sunday
                end_date -= timedelta(days=1)
            
            data = []
            for emp in employees:
                row_data = {
                    'Employee ID': emp.employee_id,
                    'Employee Name': emp.name
                }
                
                # Get overtime for each of the last 13 weeks
                for week_num in range(13):
                    week_end = end_date - timedelta(weeks=week_num)
                    week_start = week_end - timedelta(days=6)
                    
                    ot_record = OvertimeHistory.query.filter_by(
                        employee_id=emp.id,
                        week_start_date=week_start
                    ).first()
                    
                    row_data[f'Week {13 - week_num}'] = ot_record.overtime_hours if ot_record else 0
                
                data.append(row_data)
            
            df = pd.DataFrame(data)
            
            # Save to Excel
            output_path = os.path.join(tempfile.gettempdir(), f'overtime_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Overtime Data', index=False)
            
            return send_file(output_path, as_attachment=True, download_name=f'overtime_export_{datetime.now().strftime("%Y%m%d")}.xlsx')
            
        else:
            flash('Invalid export type', 'error')
            return redirect(url_for('employee_import.upload_employees'))
            
    except Exception as e:
        flash(f'Error exporting data: {str(e)}', 'error')
        return redirect(url_for('employee_import.upload_employees'))

# View upload details
@employee_import_bp.route('/upload-details/<int:upload_id>')
@login_required
@supervisor_required
def upload_details(upload_id):
    """View details of a specific upload"""
    upload = FileUpload.query.get_or_404(upload_id)
    return render_template('upload_details.html', upload=upload)

# Delete upload record
@employee_import_bp.route('/delete-upload/<int:upload_id>', methods=['POST'])
@login_required
@supervisor_required
def delete_upload(upload_id):
    """Delete an upload record"""
    try:
        upload = FileUpload.query.get_or_404(upload_id)
        db.session.delete(upload)
        db.session.commit()
        flash('Upload record deleted successfully', 'success')
    except Exception as e:
        flash(f'Error deleting record: {str(e)}', 'error')
    
    return redirect(url_for('employee_import.upload_history'))

# API endpoints for AJAX operations
@employee_import_bp.route('/api/validate-employee-data', methods=['POST'])
@login_required
@supervisor_required
def validate_employee_data():
    """Validate employee data without importing"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        file = request.files['file']
        df = pd.read_excel(file, sheet_name='Employee Data')
        
        errors = []
        warnings = []
        
        # Validate required fields
        required_fields = ['Employee ID', 'First Name', 'Last Name', 'Email', 'Crew']
        for field in required_fields:
            if field not in df.columns:
                errors.append(f"Missing required column: {field}")
        
        if errors:
            return jsonify({
                'success': False,
                'errors': errors,
                'row_count': 0
            })
        
        # Validate each row
        valid_crews = ['A', 'B', 'C', 'D']
        valid_positions = [p.name for p in Position.query.all()]
        
        for index, row in df.iterrows():
            row_num = index + 2
            
            # Check required fields
            if pd.isna(row['Employee ID']) or str(row['Employee ID']).strip() == '':
                errors.append(f"Row {row_num}: Missing Employee ID")
            
            if pd.isna(row['Email']) or not validate_email(str(row['Email']).strip()):
                errors.append(f"Row {row_num}: Invalid email format")
            
            # Check crew
            crew = str(row.get('Crew', '')).strip().upper()
            if crew not in valid_crews:
                errors.append(f"Row {row_num}: Invalid crew '{crew}'. Must be A, B, C, or D")
            
            # Check position (warning only)
            position = str(row.get('Position', '')).strip()
            if position and position not in valid_positions:
                warnings.append(f"Row {row_num}: Position '{position}' will be created")
        
        return jsonify({
            'success': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'row_count': len(df),
            'preview_data': df.head(5).to_dict('records')
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@employee_import_bp.route('/api/validate-overtime-data', methods=['POST'])
@login_required
@supervisor_required
def validate_overtime_data():
    """Validate overtime data without importing"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        file = request.files['file']
        df = pd.read_excel(file, sheet_name='Overtime Data')
        
        errors = []
        warnings = []
        
        # Validate required fields
        if 'Employee ID' not in df.columns:
            errors.append("Missing required column: Employee ID")
        
        # Check for week columns
        week_columns = [f'Week {i}' for i in range(1, 14)]
        missing_weeks = [col for col in week_columns if col not in df.columns]
        if missing_weeks:
            errors.append(f"Missing week columns: {', '.join(missing_weeks)}")
        
        if errors:
            return jsonify({
                'success': False,
                'errors': errors,
                'row_count': 0
            })
        
        # Validate each row
        for index, row in df.iterrows():
            row_num = index + 2
            
            # Check employee exists
            employee_id = str(row.get('Employee ID', '')).strip()
            if not employee_id:
                errors.append(f"Row {row_num}: Missing Employee ID")
                continue
            
            employee = Employee.query.filter_by(employee_id=employee_id).first()
            if not employee:
                errors.append(f"Row {row_num}: Employee ID '{employee_id}' not found")
            
            # Validate overtime hours
            for week_col in week_columns:
                if week_col in row and pd.notna(row[week_col]):
                    try:
                        hours = float(row[week_col])
                        if hours < 0:
                            errors.append(f"Row {row_num}, {week_col}: Negative hours not allowed")
                        elif hours > 40:
                            warnings.append(f"Row {row_num}, {week_col}: High overtime ({hours} hours)")
                    except:
                        errors.append(f"Row {row_num}, {week_col}: Invalid number format")
        
        return jsonify({
            'success': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'row_count': len(df),
            'preview_data': df.head(5).to_dict('records')
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Get upload statistics
@employee_import_bp.route('/api/upload-stats')
@login_required
@supervisor_required
def upload_stats():
    """Get upload statistics for dashboard"""
    try:
        # Get recent uploads
        recent_uploads = FileUpload.query.order_by(
            FileUpload.upload_date.desc()
        ).limit(10).all()
        
        # Calculate statistics
        total_uploads = FileUpload.query.count()
        successful_uploads = FileUpload.query.filter_by(status='completed').count()
        
        stats = {
            'total_uploads': total_uploads,
            'successful_uploads': successful_uploads,
            'recent_uploads': [{
                'id': u.id,
                'filename': u.filename,
                'type': u.file_type,
                'date': u.upload_date.strftime('%Y-%m-%d %H:%M'),
                'status': u.status,
                'records': u.records_processed
            } for u in recent_uploads]
        }
        
        return jsonify(stats)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
