# blueprints/employee_import.py
"""
Employee Import Blueprint - Complete file with all routes
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

# Import the decorator from utils
from utils.decorators import supervisor_required

# Set up logging
logger = logging.getLogger(__name__)

# Create blueprint
employee_import_bp = Blueprint('employee_import', __name__)

# ==========================================
# MAIN UPLOAD ROUTES
# ==========================================

@employee_import_bp.route('/upload-employees')
@login_required
@supervisor_required
def upload_employees():
    """Upload employees page"""
    # Get pending counts for the navbar
    pending_time_off = 0
    pending_swaps = 0
    
    try:
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
    except:
        pass
        
    try:
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
    except:
        pass
    
    return render_template('upload_employees_enhanced.html',
                         pending_time_off=pending_time_off,
                         pending_swaps=pending_swaps)

@employee_import_bp.route('/upload-overtime')
@login_required
@supervisor_required
def upload_overtime():
    """Upload overtime history page"""
    # Get pending counts for the navbar
    pending_time_off = 0
    pending_swaps = 0
    
    try:
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
    except:
        pass
        
    try:
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
    except:
        pass
    
    return render_template('upload_overtime.html',
                         pending_time_off=pending_time_off,
                         pending_swaps=pending_swaps)

@employee_import_bp.route('/upload-history')
@login_required
@supervisor_required
def upload_history():
    """View upload history"""
    uploads = FileUpload.query.order_by(FileUpload.uploaded_at.desc()).limit(50).all()
    
    # Get pending counts for the navbar
    pending_time_off = 0
    pending_swaps = 0
    
    try:
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
    except:
        pass
        
    try:
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
    except:
        pass
    
    return render_template('upload_history.html', 
                         uploads=uploads,
                         pending_time_off=pending_time_off,
                         pending_swaps=pending_swaps)

# ==========================================
# VALIDATION & PROCESSING ROUTES
# ==========================================

@employee_import_bp.route('/validate-upload', methods=['POST'])
@login_required
@supervisor_required
def validate_upload():
    """Validate uploaded Excel file"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'success': False, 'error': 'Invalid file type. Please upload Excel files only.'})
    
    try:
        # Read the Excel file
        df = pd.read_excel(file)
        
        # Basic validation
        required_columns = ['Employee ID', 'Email', 'Crew']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return jsonify({
                'success': False,
                'error': f'Missing required columns: {", ".join(missing_columns)}'
            })
        
        # Count valid rows
        valid_rows = len(df.dropna(subset=['Employee ID', 'Email']))
        
        return jsonify({
            'success': True,
            'message': f'File validated successfully. Found {valid_rows} employees.',
            'total_rows': len(df),
            'valid_rows': valid_rows
        })
        
    except Exception as e:
        logger.error(f"Validation error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@employee_import_bp.route('/process-upload', methods=['POST'])
@login_required
@supervisor_required
def process_upload():
    """Process the uploaded file"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'})
    
    file = request.files['file']
    upload_type = request.form.get('upload_type', 'employee')
    
    try:
        # Save file info
        file_upload = FileUpload(
            filename=file.filename,
            upload_type=upload_type,
            uploaded_by_id=current_user.id,
            uploaded_at=datetime.utcnow()
        )
        db.session.add(file_upload)
        db.session.commit()
        
        # Read and process file
        df = pd.read_excel(file)
        
        # Process based on type
        if upload_type == 'employee':
            result = process_employee_data(df)
        elif upload_type == 'overtime':
            result = process_overtime_data(df)
        else:
            result = {'success': False, 'error': 'Invalid upload type'}
        
        # Update file upload record
        if result.get('success'):
            file_upload.total_records = result.get('total', 0)
            file_upload.successful_records = result.get('successful', 0)
            file_upload.failed_records = result.get('failed', 0)
        else:
            file_upload.error_details = result.get('error', 'Unknown error')
        
        db.session.commit()
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Process error: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

# ==========================================
# TEMPLATE DOWNLOAD ROUTES
# ==========================================

@employee_import_bp.route('/download-employee-template')
@login_required
@supervisor_required
def download_employee_template():
    """Download employee upload template"""
    try:
        # Create template DataFrame
        template_data = {
            'Employee ID': ['EMP001', 'EMP002'],
            'First Name': ['John', 'Jane'],
            'Last Name': ['Doe', 'Smith'],
            'Email': ['john.doe@example.com', 'jane.smith@example.com'],
            'Crew': ['A', 'B'],
            'Position': ['Operator', 'Lead Operator'],
            'Department': ['Production', 'Production'],
            'Phone': ['555-0001', '555-0002'],
            'Hire Date': ['2023-01-15', '2023-02-01'],
            'Skills': ['Welding, Forklift', 'Leadership, Safety']
        }
        
        df = pd.DataFrame(template_data)
        
        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Employee Data')
            
            # Add instructions sheet
            instructions = pd.DataFrame({
                'Instructions': [
                    'Employee Upload Template Instructions',
                    '',
                    '1. Fill in all required fields: Employee ID, First Name, Last Name, Email, Crew, Position',
                    '2. Crew must be one of: A, B, C, or D',
                    '3. Email addresses must be unique',
                    '4. Employee IDs must be unique',
                    '5. Date format: YYYY-MM-DD',
                    '6. Skills should be comma-separated',
                    '',
                    'Optional fields: Department, Phone, Hire Date, Skills',
                    '',
                    'Delete the sample data rows before uploading your actual data.'
                ]
            })
            instructions.to_excel(writer, index=False, sheet_name='Instructions')
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='employee_upload_template.xlsx'
        )
        
    except Exception as e:
        logger.error(f"Template download error: {str(e)}")
        flash('Error generating template', 'danger')
        return redirect(url_for('employee_import.upload_employees'))

@employee_import_bp.route('/download-overtime-template')
@login_required
@supervisor_required
def download_overtime_template():
    """Download overtime upload template"""
    try:
        # Create template with 13 weeks of data
        template_data = []
        start_date = date.today() - timedelta(weeks=13)
        
        for week in range(13):
            week_start = start_date + timedelta(weeks=week)
            template_data.append({
                'Employee ID': 'EMP001',
                'Week Start Date': week_start.strftime('%Y-%m-%d'),
                'Regular Hours': 40,
                'Overtime Hours': 5,
                'Total Hours': 45,
                'Notes': 'Sample data - replace with actual'
            })
        
        df = pd.DataFrame(template_data)
        
        # Create Excel file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Overtime Data')
            
            # Add instructions
            instructions = pd.DataFrame({
                'Instructions': [
                    'Overtime History Upload Template',
                    '',
                    'Requirements:',
                    '1. Must include exactly 13 weeks of data per employee',
                    '2. Week Start Date must be a Monday',
                    '3. All hour values must be non-negative',
                    '4. Total Hours should equal Regular Hours + Overtime Hours',
                    '',
                    'Format:',
                    '- Employee ID: Must match existing employee',
                    '- Week Start Date: YYYY-MM-DD format (Mondays only)',
                    '- Regular Hours: Standard work hours',
                    '- Overtime Hours: Hours worked beyond regular',
                    '- Total Hours: Sum of regular and overtime',
                    '- Notes: Optional field for comments'
                ]
            })
            instructions.to_excel(writer, index=False, sheet_name='Instructions')
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='overtime_upload_template.xlsx'
        )
        
    except Exception as e:
        logger.error(f"Overtime template error: {str(e)}")
        flash('Error generating overtime template', 'danger')
        return redirect(url_for('employee_import.upload_overtime'))

# ==========================================
# EXPORT ROUTES
# ==========================================

@employee_import_bp.route('/export-current-employees')
@login_required
@supervisor_required
def export_current_employees():
    """Export current employee data"""
    try:
        employees = Employee.query.filter_by(is_supervisor=False).all()
        
        data = []
        for emp in employees:
            data.append({
                'Employee ID': emp.employee_id,
                'First Name': emp.name.split()[0] if emp.name else '',
                'Last Name': ' '.join(emp.name.split()[1:]) if emp.name and len(emp.name.split()) > 1 else '',
                'Email': emp.email,
                'Crew': emp.crew or '',
                'Position': emp.position.name if emp.position else '',
                'Department': emp.department or '',
                'Phone': emp.phone or '',
                'Hire Date': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '',
                'Is Active': 'Yes' if emp.is_active else 'No'
            })
        
        df = pd.DataFrame(data)
        
        # Create Excel file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Current Employees')
        
        output.seek(0)
        
        filename = f'employees_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f"Export error: {str(e)}")
        flash('Error exporting employee data', 'danger')
        return redirect(url_for('employee_import.upload_employees'))

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def process_employee_data(df):
    """Process employee data from DataFrame"""
    try:
        successful = 0
        failed = 0
        errors = []
        
        # Get or create positions
        positions = {}
        for _, row in df.iterrows():
            if 'Position' in row and pd.notna(row['Position']):
                pos_name = str(row['Position']).strip()
                if pos_name and pos_name not in positions:
                    position = Position.query.filter_by(name=pos_name).first()
                    if not position:
                        position = Position(name=pos_name)
                        db.session.add(position)
                        db.session.flush()
                    positions[pos_name] = position
        
        # Process employees
        for idx, row in df.iterrows():
            try:
                # Required fields
                emp_id = str(row.get('Employee ID', '')).strip()
                email = str(row.get('Email', '')).strip().lower()
                crew = str(row.get('Crew', '')).strip().upper()
                
                if not emp_id or not email or not crew:
                    errors.append(f"Row {idx+2}: Missing required fields")
                    failed += 1
                    continue
                
                # Check if employee exists
                employee = Employee.query.filter_by(employee_id=emp_id).first()
                if not employee:
                    employee = Employee(employee_id=emp_id)
                
                # Update fields
                employee.email = email
                employee.crew = crew if crew in ['A', 'B', 'C', 'D'] else None
                
                # Name handling
                first_name = str(row.get('First Name', '')).strip()
                last_name = str(row.get('Last Name', '')).strip()
                employee.name = f"{first_name} {last_name}".strip()
                
                # Optional fields
                if 'Position' in row and pd.notna(row['Position']):
                    pos_name = str(row['Position']).strip()
                    if pos_name in positions:
                        employee.position = positions[pos_name]
                
                if 'Department' in row and pd.notna(row['Department']):
                    employee.department = str(row['Department']).strip()
                
                if 'Phone' in row and pd.notna(row['Phone']):
                    employee.phone = str(row['Phone']).strip()
                
                if 'Hire Date' in row and pd.notna(row['Hire Date']):
                    try:
                        employee.hire_date = pd.to_datetime(row['Hire Date']).date()
                    except:
                        pass
                
                # Set default password for new employees
                if not employee.password_hash:
                    employee.set_password('password123')
                
                employee.is_active = True
                employee.is_supervisor = False
                
                db.session.add(employee)
                successful += 1
                
            except Exception as e:
                errors.append(f"Row {idx+2}: {str(e)}")
                failed += 1
        
        db.session.commit()
        
        return {
            'success': True,
            'total': len(df),
            'successful': successful,
            'failed': failed,
            'errors': errors
        }
        
    except Exception as e:
        db.session.rollback()
        return {
            'success': False,
            'error': str(e)
        }

def process_overtime_data(df):
    """Process overtime data from DataFrame"""
    try:
        successful = 0
        failed = 0
        errors = []
        
        # Group by employee
        for emp_id in df['Employee ID'].unique():
            emp_data = df[df['Employee ID'] == emp_id]
            
            # Find employee
            employee = Employee.query.filter_by(employee_id=str(emp_id).strip()).first()
            if not employee:
                errors.append(f"Employee {emp_id} not found")
                failed += len(emp_data)
                continue
            
            # Process each week
            for idx, row in emp_data.iterrows():
                try:
                    week_start = pd.to_datetime(row['Week Start Date']).date()
                    
                    # Check if record exists
                    ot_record = OvertimeHistory.query.filter_by(
                        employee_id=employee.id,
                        week_start_date=week_start
                    ).first()
                    
                    if not ot_record:
                        ot_record = OvertimeHistory(
                            employee_id=employee.id,
                            week_start_date=week_start
                        )
                    
                    # Update values
                    ot_record.regular_hours = float(row.get('Regular Hours', 0))
                    ot_record.overtime_hours = float(row.get('Overtime Hours', 0))
                    ot_record.total_hours = float(row.get('Total Hours', 
                        ot_record.regular_hours + ot_record.overtime_hours))
                    ot_record.week_ending = week_start + timedelta(days=6)
                    
                    db.session.add(ot_record)
                    successful += 1
                    
                except Exception as e:
                    errors.append(f"Row {idx+2}: {str(e)}")
                    failed += 1
        
        db.session.commit()
        
        return {
            'success': True,
            'total': len(df),
            'successful': successful,
            'failed': failed,
            'errors': errors
        }
        
    except Exception as e:
        db.session.rollback()
        return {
            'success': False,
            'error': str(e)
        }
