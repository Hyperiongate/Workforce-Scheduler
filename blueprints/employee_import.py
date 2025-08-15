# blueprints/employee_import.py - FIXED VERSION
"""
Employee Import Blueprint - Fixed to remove non-existent import
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db, Employee, Position, Skill, OvertimeHistory, FileUpload
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

# Basic routes to prevent 404 errors
@employee_import_bp.route('/upload-employees')
@login_required
@supervisor_required
def upload_employees():
    """Upload employees page"""
    return render_template('upload_employees_enhanced.html')

@employee_import_bp.route('/upload-overtime')
@login_required
@supervisor_required
def upload_overtime():
    """Upload overtime history page"""
    return render_template('upload_overtime.html')

@employee_import_bp.route('/upload-history')
@login_required
@supervisor_required
def upload_history():
    """View upload history"""
    uploads = FileUpload.query.order_by(FileUpload.uploaded_at.desc()).limit(50).all()
    return render_template('upload_history.html', uploads=uploads)

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

def process_employee_data(df):
    """Process employee data from DataFrame"""
    try:
        successful = 0
        failed = 0
        
        for _, row in df.iterrows():
            try:
                # Check if employee exists
                emp_id = str(row.get('Employee ID', '')).strip()
                if not emp_id:
                    failed += 1
                    continue
                
                employee = Employee.query.filter_by(employee_id=emp_id).first()
                
                if not employee:
                    # Create new employee
                    employee = Employee(
                        employee_id=emp_id,
                        name=f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip() or row.get('Name', 'Unknown'),
                        email=str(row.get('Email', '')).lower().strip(),
                        crew=str(row.get('Crew', '')).upper().strip(),
                        department=str(row.get('Department', 'Production')).strip(),
                        is_active=True
                    )
                    
                    # Set default password
                    employee.set_password('changeme123')
                    db.session.add(employee)
                else:
                    # Update existing
                    if row.get('Email'):
                        employee.email = str(row.get('Email', '')).lower().strip()
                    if row.get('Crew'):
                        employee.crew = str(row.get('Crew', '')).upper().strip()
                    if row.get('Department'):
                        employee.department = str(row.get('Department', '')).strip()
                
                successful += 1
                
            except Exception as e:
                logger.error(f"Error processing row: {str(e)}")
                failed += 1
                continue
        
        db.session.commit()
        
        return {
            'success': True,
            'total': len(df),
            'successful': successful,
            'failed': failed,
            'message': f'Processed {successful} employees successfully'
        }
        
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'error': str(e)}

def process_overtime_data(df):
    """Process overtime data from DataFrame"""
    try:
        successful = 0
        failed = 0
        
        # Implementation for overtime processing
        # This is a placeholder - implement based on your needs
        
        return {
            'success': True,
            'total': len(df),
            'successful': successful,
            'failed': failed,
            'message': f'Processed {successful} overtime records'
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

# Template download routes
@employee_import_bp.route('/download-employee-template')
@login_required
@supervisor_required
def download_employee_template():
    """Download employee upload template"""
    # Create sample template
    template_data = {
        'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
        'Name': ['John Doe', 'Jane Smith', 'Bob Johnson'],
        'Email': ['john.doe@company.com', 'jane.smith@company.com', 'bob.johnson@company.com'],
        'Crew': ['A', 'B', 'C'],
        'Department': ['Production', 'Production', 'Maintenance'],
        'Position': ['Operator', 'Supervisor', 'Technician']
    }
    
    df = pd.DataFrame(template_data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Employee Data', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'employee_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )
