# blueprints/employee_import.py
"""
Employee import/export functionality for workforce scheduler
Handles Excel template download and data upload
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import pandas as pd
from datetime import datetime, timedelta
import os
import io
import numpy as np
from models import db, Employee, Position, Skill, OvertimeHistory, employee_skills
from sqlalchemy import func, text
import traceback

employee_import_bp = Blueprint('employee_import', __name__)

def supervisor_required(f):
    """Decorator to require supervisor access"""
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_supervisor:
            flash('Access denied. Supervisor privileges required.', 'error')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@employee_import_bp.route('/download-employee-template')
@login_required
@supervisor_required
def download_employee_template():
    """Generate and download the employee import template"""
    try:
        # Get all positions from database
        positions = Position.query.order_by(Position.name).all()
        position_names = [pos.name for pos in positions]
        
        # If no positions exist, use defaults
        if not position_names:
            position_names = [
                'Operator', 'Senior Operator', 'Lead Operator', 
                'Maintenance Technician', 'Senior Maintenance', 
                'Shift Supervisor', 'Area Coordinator', 
                'Quality Inspector', 'Material Handler', 'Trainer'
            ]
        
        # Ensure we have at least 10 position columns
        while len(position_names) < 10:
            position_names.append(f'Position {len(position_names) + 1}')
        
        # Create the template structure
        template_data = {
            'Last Name': ['Example', 'Sample'],
            'First Name': ['John', 'Jane'],
            'Employee ID': ['EMP001', 'EMP002'],
            'Date of Hire': ['2020-01-15', '2021-03-22'],
            'Total Overtime (Last 3 Months)': [120.5, 85.0],
            'Crew Assigned': ['A', 'B'],
            'Current Job Position': [position_names[0], position_names[1]]
        }
        
        # Add position columns
        for i, pos_name in enumerate(position_names[:10]):
            if i == 0:
                template_data[pos_name] = ['current', 'yes']
            elif i == 1:
                template_data[pos_name] = ['yes', 'current']
            elif i == 2:
                template_data[pos_name] = ['yes', '']
            else:
                template_data[pos_name] = ['', '']
        
        # Create DataFrame
        df = pd.DataFrame(template_data)
        
        # Create Excel writer with xlsxwriter engine for better formatting
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Write instructions on first sheet
            instructions_df = pd.DataFrame({
                'A': ['EMPLOYEE IMPORT TEMPLATE - INSTRUCTIONS', '', 
                     'IMPORTANT: Before filling out this template, you MUST replace the position column headers with your actual job position titles.',
                     '', 'INSTRUCTIONS:',
                     '1. The position columns have been pre-filled with your system positions.',
                     '2. For each employee, enter their basic information in the first 7 columns',
                     '3. In the position columns, mark their qualifications as follows:',
                     '   - Write "current" under the position that matches their Current Job Position',
                     '   - Write "yes" under any other positions they are qualified for',
                     '   - Leave blank if they are not qualified for that position',
                     '', 'EXAMPLE:',
                     'If an employee\'s current position is "Operator" and they\'re also qualified as "Senior Operator":',
                     '- Under the "Operator" column: write "current"',
                     '- Under the "Senior Operator" column: write "yes"',
                     '', 'NOTES:',
                     '- Date of Hire should be in YYYY-MM-DD format',
                     '- Total Overtime is in hours for the last 3 months',
                     '- Crew Assigned should be A, B, C, or D',
                     '- Delete the example rows before uploading']
            })
            
            instructions_df.to_excel(writer, sheet_name='Instructions', index=False, header=False)
            
            # Write the actual template
            df.to_excel(writer, sheet_name='Employee Data', index=False)
            
            # Get the workbook and worksheets
            workbook = writer.book
            instructions_sheet = writer.sheets['Instructions']
            data_sheet = writer.sheets['Employee Data']
            
            # Format instructions sheet
            title_format = workbook.add_format({'bold': True, 'font_size': 14, 'bg_color': '#4472C4', 'font_color': 'white'})
            header_format = workbook.add_format({'bold': True, 'bg_color': '#D9E1F2'})
            
            instructions_sheet.set_column('A:A', 100)
            instructions_sheet.write('A1', instructions_df.iloc[0, 0], title_format)
            
            # Format data sheet
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#4472C4',
                'font_color': 'white',
                'border': 1,
                'text_wrap': True,
                'valign': 'vcenter'
            })
            
            date_format = workbook.add_format({'num_format': 'yyyy-mm-dd'})
            
            # Set column widths
            data_sheet.set_column('A:B', 15)  # Names
            data_sheet.set_column('C:C', 12)  # Employee ID
            data_sheet.set_column('D:D', 12)  # Date of Hire
            data_sheet.set_column('E:E', 20)  # Overtime
            data_sheet.set_column('F:F', 12)  # Crew
            data_sheet.set_column('G:G', 20)  # Current Position
            data_sheet.set_column('H:Q', 15)  # Qualification columns
            
            # Write headers with formatting
            for col_num, value in enumerate(df.columns.values):
                data_sheet.write(0, col_num, value, header_format)
            
            # Add data validation for Crew column
            data_sheet.data_validation('F2:F1000', {
                'validate': 'list',
                'source': ['A', 'B', 'C', 'D'],
                'error_title': 'Invalid Crew',
                'error_message': 'Please select A, B, C, or D'
            })
            
            # Add conditional formatting for position columns
            current_format = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
            yes_format = workbook.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C5700'})
            
            for col in range(7, 17):  # Position columns (H-Q)
                data_sheet.conditional_format(1, col, 1000, col, {
                    'type': 'text',
                    'criteria': 'containing',
                    'value': 'current',
                    'format': current_format
                })
                data_sheet.conditional_format(1, col, 1000, col, {
                    'type': 'text',
                    'criteria': 'containing',
                    'value': 'yes',
                    'format': yes_format
                })
        
        output.seek(0)
        
        # Generate filename with timestamp
        filename = f'employee_import_template_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        current_app.logger.error(f"Error generating template: {str(e)}")
        flash(f'Error generating template: {str(e)}', 'error')
        return redirect(url_for('supervisor.dashboard'))

@employee_import_bp.route('/upload-employees', methods=['GET', 'POST'])
@login_required
@supervisor_required
def upload_employees():
    """Handle employee data upload from Excel file"""
    if request.method == 'GET':
        try:
            # Count employees (excluding current user)
            employee_count = Employee.query.filter(Employee.id != current_user.id).count()
            # Get upload history - simplified without FileUpload model
            return render_template('upload_employees.html', employee_count=employee_count, recent_uploads=[])
        except Exception as e:
            current_app.logger.error(f"Error in upload_employees GET: {str(e)}\n{traceback.format_exc()}")
            flash(f'Error loading upload page: {str(e)}', 'error')
            return redirect(url_for('main.dashboard'))
    
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(request.url)
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        flash('Please upload an Excel file (.xlsx or .xls)', 'error')
        return redirect(request.url)
    
    try:
        # NUCLEAR OPTION - Delete all employees except current user
        current_app.logger.info(f"Starting nuclear employee upload - deleting all employees except user {current_user.id}")
        
        # First, try to delete all employees except current user
        try:
            # Delete related records first to avoid foreign key constraints
            # List of tables that reference employee
            related_tables = [
                'employee_skills',
                'overtime_history',
                'time_off_request',
                'circadian_profile',
                'sleep_log',
                'schedule',
                'shift_swap_request',
                'shift_trade_post',
                'shift_trade_proposal',
                'shift_trade',
                'maintenance_issue',
                'maintenance_update',
                'position_message',
                'coverage_request',
                'schedule_suggestion',
                'vacation_calendar'
            ]
            
            # Delete from each related table
            for table in related_tables:
                try:
                    delete_query = text(f"""
                        DELETE FROM {table} 
                        WHERE employee_id IN (
                            SELECT id FROM employee WHERE id != :current_user_id
                        )
                    """)
                    db.session.execute(delete_query, {'current_user_id': current_user.id})
                except Exception as e:
                    # Table might not exist or might not have employee_id column
                    current_app.logger.warning(f"Could not delete from {table}: {str(e)}")
            
            # Also handle tables with different column names
            # For shift swap requests (has requester_id and requested_with_id)
            try:
                db.session.execute(text("""
                    DELETE FROM shift_swap_request 
                    WHERE requester_id IN (SELECT id FROM employee WHERE id != :current_user_id)
                    OR requested_with_id IN (SELECT id FROM employee WHERE id != :current_user_id)
                """), {'current_user_id': current_user.id})
            except:
                pass
            
            # For shift trades (might have multiple employee references)
            try:
                db.session.execute(text("""
                    DELETE FROM shift_trade 
                    WHERE employee1_id IN (SELECT id FROM employee WHERE id != :current_user_id)
                    OR employee2_id IN (SELECT id FROM employee WHERE id != :current_user_id)
                """), {'current_user_id': current_user.id})
            except:
                pass
            
            # For messages (might have sender_id)
            try:
                db.session.execute(text("""
                    DELETE FROM position_message 
                    WHERE sender_id IN (SELECT id FROM employee WHERE id != :current_user_id)
                """), {'current_user_id': current_user.id})
            except:
                pass
            
            # Now delete employees
            delete_query = text("""
                DELETE FROM employee 
                WHERE id != :current_user_id
            """)
            
            result = db.session.execute(delete_query, {'current_user_id': current_user.id})
            deleted_count = result.rowcount
            db.session.commit()
            
            current_app.logger.info(f"Successfully deleted {deleted_count} employees and their related records")
            
        except Exception as delete_error:
            db.session.rollback()
            current_app.logger.error(f"Error during deletion: {str(delete_error)}")
            flash(f'Error clearing existing employees: {str(delete_error)}', 'error')
            return redirect(request.url)
        
        # Now proceed with uploading new data
        # Read Excel file
        df = pd.read_excel(file, sheet_name='Employee Data' if 'Employee Data' in pd.ExcelFile(file).sheet_names else 0)
        
        # Check if we have the required columns
        required_columns = ['Last Name', 'First Name', 'Employee ID', 'Date of Hire', 
                           'Total Overtime (Last 3 Months)', 'Crew Assigned', 'Current Job Position']
        
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            flash(f'Missing required columns: {", ".join(missing_columns)}. Please use the correct template.', 'error')
            return redirect(request.url)
        
        # Process each row
        success_count = 0
        error_count = 0
        errors = []
        
        # Get position columns (everything after the first 7 columns)
        base_columns = ['Last Name', 'First Name', 'Employee ID', 'Date of Hire', 
                       'Total Overtime (Last 3 Months)', 'Crew Assigned', 'Current Job Position']
        position_columns = [col for col in df.columns if col not in base_columns]
        
        for index, row in df.iterrows():
            try:
                # Skip empty rows - check if Last Name or First Name is empty/NaN
                if pd.isna(row.get('Last Name', '')) or pd.isna(row.get('First Name', '')) or \
                   str(row.get('Last Name', '')).strip() == '' or str(row.get('First Name', '')).strip() == '':
                    continue
                
                # Also skip if Employee ID is missing
                if pd.isna(row.get('Employee ID', '')) or str(row.get('Employee ID', '')).strip() == '':
                    errors.append(f"Row {index + 2}: Missing Employee ID")
                    error_count += 1
                    continue
                
                # Create new employee (no need to check for existing since we deleted all)
                employee = Employee(
                    employee_id=str(row['Employee ID']),
                    name=f"{row['First Name']} {row['Last Name']}",
                    email=f"{str(row['First Name']).lower()}.{str(row['Last Name']).lower()}@company.com",
                    password_hash='$2b$12$default_hash',  # Will need to be reset
                    crew=str(row.get('Crew Assigned', '')),
                    is_supervisor=False,
                    hire_date=pd.to_datetime(row['Date of Hire']).date() if pd.notna(row.get('Date of Hire')) else datetime.now().date()
                )
                db.session.add(employee)
                db.session.flush()  # Get the ID
                
                # Handle current position
                current_pos_name = row.get('Current Job Position', '')
                if pd.notna(current_pos_name) and str(current_pos_name).strip():
                    position = Position.query.filter_by(name=str(current_pos_name)).first()
                    if not position:
                        position = Position(name=str(current_pos_name), department=f"{current_pos_name} department")
                        db.session.add(position)
                        db.session.flush()
                    employee.position_id = position.id
                
                # Handle overtime if provided
                overtime_value = row.get('Total Overtime (Last 3 Months)')
                if pd.notna(overtime_value) and str(overtime_value).strip():
                    try:
                        # Calculate average weekly overtime from 3-month total
                        total_ot = float(overtime_value)
                        weekly_avg = total_ot / 13  # Approximately 13 weeks in 3 months
                        
                        # Create overtime history record for current week
                        current_week = datetime.now().isocalendar()[1]
                        current_year = datetime.now().year
                        week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())
                        
                        ot_record = OvertimeHistory(
                            employee_id=employee.id,
                            week_start_date=week_start,
                            overtime_hours=weekly_avg,
                            regular_hours=40,
                            total_hours=40 + weekly_avg
                        )
                        db.session.add(ot_record)
                    except ValueError:
                        # Skip if overtime value is not a valid number
                        pass
                
                # Handle position qualifications
                for pos_col in position_columns:
                    cell_value = row.get(pos_col, '')
                    if pd.notna(cell_value) and str(cell_value).strip().lower() in ['current', 'yes']:
                        # Find or create position
                        position = Position.query.filter_by(name=str(pos_col)).first()
                        if not position:
                            position = Position(name=str(pos_col), department=f"{pos_col} department")
                            db.session.add(position)
                            db.session.flush()
                        
                        # Find or create skill for this position
                        skill = Skill.query.filter_by(name=f"{pos_col} Certified").first()
                        if not skill:
                            skill = Skill(
                                name=f"{pos_col} Certified",
                                description=f"Qualified to work as {pos_col}",
                                category='position'
                            )
                            db.session.add(skill)
                            db.session.flush()
                        
                        # Add employee skill using the association table
                        db.session.execute(
                            employee_skills.insert().values(
                                employee_id=employee.id,
                                skill_id=skill.id,
                                is_primary=(str(cell_value).strip().lower() == 'current'),
                                certification_date=datetime.now().date()
                            )
                        )
                
                success_count += 1
                
            except Exception as e:
                error_count += 1
                errors.append(f"Row {index + 2}: {str(e)}")
                current_app.logger.error(f"Error processing row {index}: {str(e)}")
        
        # Commit all changes
        db.session.commit()
        
        if success_count > 0:
            flash(f'Successfully imported {success_count} employees. (Deleted {deleted_count} existing employees first)', 'success')
        if error_count > 0:
            flash(f'{error_count} records failed to import. Details: {"; ".join(errors[:5])}', 'warning')
        
        return redirect(url_for('employee_import.upload_employees'))
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error uploading file: {str(e)}\n{traceback.format_exc()}")
        flash(f'Error processing file: {str(e)}', 'error')
        return redirect(url_for('employee_import.upload_employees'))

@employee_import_bp.route('/download-sample-data')
@login_required
@supervisor_required
def download_sample_data():
    """Download a sample filled template with 100 employees"""
    try:
        # Get positions from database or use defaults
        positions = Position.query.order_by(Position.name).limit(10).all()
        position_names = [pos.name for pos in positions]
        
        if len(position_names) < 10:
            default_positions = [
                'Operator', 'Senior Operator', 'Lead Operator', 
                'Maintenance Technician', 'Senior Maintenance', 
                'Shift Supervisor', 'Area Coordinator', 
                'Quality Inspector', 'Material Handler', 'Trainer'
            ]
            position_names.extend(default_positions[len(position_names):10])
        
        # Generate sample data
        data = []
        first_names = ['John', 'Jane', 'Michael', 'Sarah', 'David', 'Emily', 'Robert', 'Lisa', 'James', 'Mary']
        last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Martinez', 'Wilson']
        crews = ['A', 'B', 'C', 'D']
        
        for i in range(100):
            employee = {
                'Last Name': last_names[i % len(last_names)] + str(i // len(last_names) + 1),
                'First Name': first_names[i % len(first_names)],
                'Employee ID': f'EMP{str(i + 1).zfill(3)}',
                'Date of Hire': (datetime.now() - pd.Timedelta(days=np.random.randint(30, 3650))).strftime('%Y-%m-%d'),
                'Total Overtime (Last 3 Months)': round(np.random.uniform(0, 200), 1),
                'Crew Assigned': crews[i % 4],
                'Current Job Position': position_names[np.random.randint(0, 5)]
            }
            
            # Add position qualifications
            current_pos_index = position_names.index(employee['Current Job Position'])
            for j, pos in enumerate(position_names):
                if j == current_pos_index:
                    employee[pos] = 'current'
                elif j < current_pos_index:  # Qualified for lower positions
                    employee[pos] = 'yes' if np.random.random() > 0.3 else ''
                else:  # Might be qualified for some higher positions
                    employee[pos] = 'yes' if np.random.random() > 0.7 else ''
            
            data.append(employee)
        
        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Create Excel file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Employee Data', index=False)
            
            # Format the sheet
            workbook = writer.book
            worksheet = writer.sheets['Employee Data']
            
            # Header format
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#4472C4',
                'font_color': 'white',
                'border': 1
            })
            
            # Write headers
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            # Set column widths
            worksheet.set_column('A:B', 15)
            worksheet.set_column('C:C', 12)
            worksheet.set_column('D:D', 12)
            worksheet.set_column('E:E', 20)
            worksheet.set_column('F:F', 12)
            worksheet.set_column('G:Q', 15)
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'sample_employee_data_100.xlsx'
        )
        
    except Exception as e:
        current_app.logger.error(f"Error generating sample data: {str(e)}")
        flash(f'Error generating sample data: {str(e)}', 'error')
        return redirect(url_for('supervisor.dashboard'))

@employee_import_bp.route('/export-current-employees')
@login_required
@supervisor_required
def export_current_employees():
    """Export current employee data to Excel"""
    try:
        # Get all employees with their positions and skills
        employees = Employee.query.order_by(Employee.crew, Employee.name).all()
        
        # Get all positions for columns
        positions = Position.query.order_by(Position.name).all()
        position_names = [pos.name for pos in positions[:10]]  # Limit to 10 positions
        
        # Build data for export
        data = []
        for emp in employees:
            if emp.email == 'admin@workforce.com':  # Skip admin
                continue
                
            # Calculate total overtime for last 13 weeks
            total_overtime = emp.last_13_weeks_overtime
            
            # Parse name (assuming "First Last" format)
            name_parts = emp.name.split(' ', 1)
            first_name = name_parts[0] if name_parts else emp.name
            last_name = name_parts[1] if len(name_parts) > 1 else ''
            
            row = {
                'Last Name': last_name,
                'First Name': first_name,
                'Employee ID': emp.employee_id,
                'Date of Hire': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '',
                'Total Overtime (Last 3 Months)': round(total_overtime, 1),
                'Crew Assigned': emp.crew or '',
                'Current Job Position': emp.position.name if emp.position else ''
            }
            
            # Add position qualifications
            emp_skills = set()
            for skill in emp.skills:
                if skill.name.endswith(' Certified'):
                    pos_name = skill.name.replace(' Certified', '')
                    emp_skills.add(pos_name)
            
            for pos_name in position_names:
                if emp.position and emp.position.name == pos_name:
                    row[pos_name] = 'current'
                elif pos_name in emp_skills:
                    row[pos_name] = 'yes'
                else:
                    row[pos_name] = ''
            
            data.append(row)
        
        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Create Excel file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Employee Data', index=False)
            
            # Format the sheet
            workbook = writer.book
            worksheet = writer.sheets['Employee Data']
            
            # Header format
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#4472C4',
                'font_color': 'white',
                'border': 1
            })
            
            # Write headers
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            # Set column widths
            worksheet.set_column('A:B', 15)
            worksheet.set_column('C:C', 12)
            worksheet.set_column('D:D', 12)
            worksheet.set_column('E:E', 20)
            worksheet.set_column('F:F', 12)
            worksheet.set_column('G:Q', 15)
            
            # Conditional formatting
            current_format = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
            yes_format = workbook.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C5700'})
            
            for col in range(7, 17):
                worksheet.conditional_format(1, col, len(data), col, {
                    'type': 'text',
                    'criteria': 'containing',
                    'value': 'current',
                    'format': current_format
                })
                worksheet.conditional_format(1, col, len(data), col, {
                    'type': 'text',
                    'criteria': 'containing',
                    'value': 'yes',
                    'format': yes_format
                })
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'employee_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
        
    except Exception as e:
        current_app.logger.error(f"Error exporting employees: {str(e)}")
        flash(f'Error exporting employees: {str(e)}', 'error')
        return redirect(url_for('supervisor.dashboard'))
