# blueprints/employee_import.py - Enhanced version with new upload system

# At the top of blueprints/employee_import.py
import sys
sys.path.append('..')  # If the files are in parent directory
from excel_templates_generator import (
    create_employee_import_template,
    create_overtime_history_template,
    create_bulk_update_template
)
from excel_upload_handler import ExcelUploadValidator, ExcelUploadProcessor

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify, current_app
from flask_login import login_required, current_user
from functools import wraps
import pandas as pd
import io
from datetime import datetime, date, timedelta
import traceback
import os
from werkzeug.utils import secure_filename
from models import db, Employee, Position, OvertimeHistory, Skill, EmployeeSkill, FileUpload
from sqlalchemy import func
import random

# Import our new validation and processing classes
from excel_templates_generator import (
    create_employee_import_template,
    create_overtime_history_template,
    create_bulk_update_template
)
from excel_upload_handler import ExcelUploadValidator, ExcelUploadProcessor

employee_import_bp = Blueprint('employee_import', __name__)

def supervisor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))
        if not current_user.is_supervisor:
            flash('Access denied. Supervisor privileges required.', 'error')
            return redirect(url_for('main.employee_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Template download routes
@employee_import_bp.route('/download-employee-template')
@login_required
@supervisor_required
def download_employee_template():
    """Download the enhanced employee import template"""
    try:
        output = create_employee_import_template()
        filename = f'employee_import_template_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        current_app.logger.error(f"Error generating employee template: {str(e)}")
        flash(f'Error generating template: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

@employee_import_bp.route('/download-overtime-template')
@login_required
@supervisor_required
def download_overtime_template():
    """Download the overtime history import template"""
    try:
        output = create_overtime_history_template()
        filename = f'overtime_history_template_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        current_app.logger.error(f"Error generating overtime template: {str(e)}")
        flash(f'Error generating template: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

@employee_import_bp.route('/download-bulk-update-template/<template_type>')
@login_required
@supervisor_required
def download_bulk_update_template(template_type):
    """Download bulk update templates"""
    try:
        if template_type not in ['employee', 'overtime']:
            flash('Invalid template type', 'error')
            return redirect(url_for('main.dashboard'))
            
        output = create_bulk_update_template(template_type)
        filename = f'{template_type}_bulk_update_template_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        current_app.logger.error(f"Error generating bulk update template: {str(e)}")
        flash(f'Error generating template: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

# Enhanced upload page
@employee_import_bp.route('/upload-employees', methods=['GET', 'POST'])
@login_required
@supervisor_required
def upload_employees():
    """Enhanced employee data upload with validation"""
    if request.method == 'GET':
        try:
            # Get statistics
            employee_count = Employee.query.filter(Employee.id != current_user.id).count()
            
            # Get recent uploads
            recent_uploads = FileUpload.query.filter_by(
                file_type='employee_import'
            ).order_by(FileUpload.upload_date.desc()).limit(10).all()
            
            # Get crew distribution
            crew_stats = db.session.query(
                Employee.crew,
                func.count(Employee.id)
            ).filter(
                Employee.id != current_user.id
            ).group_by(Employee.crew).all()
            
            crew_distribution = {crew: count for crew, count in crew_stats}
            
            return render_template('upload_employees_enhanced.html',
                                 employee_count=employee_count,
                                 recent_uploads=recent_uploads,
                                 crew_distribution=crew_distribution)
                                 
        except Exception as e:
            current_app.logger.error(f"Error in upload_employees GET: {str(e)}")
            flash(f'Error loading upload page: {str(e)}', 'error')
            return redirect(url_for('main.dashboard'))
    
    # POST - Process upload
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
        # Save file temporarily
        filename = secure_filename(file.filename)
        temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        file.save(temp_path)
        file_size = os.path.getsize(temp_path)
        
        # Read and validate the file
        df = pd.read_excel(temp_path, sheet_name='Employee Data')
        
        # Initialize validator
        validator = ExcelUploadValidator()
        is_valid, validated_data = validator.validate_employee_data(df)
        
        # Remove temp file
        os.remove(temp_path)
        
        if not is_valid:
            # Show validation errors
            flash('Validation failed. Please fix the following errors:', 'error')
            for error in validator.errors[:10]:  # Show first 10 errors
                flash(f'• {error}', 'error')
            if len(validator.errors) > 10:
                flash(f'... and {len(validator.errors) - 10} more errors', 'error')
            return redirect(request.url)
        
        # Show warnings if any
        if validator.warnings:
            for warning in validator.warnings[:5]:
                flash(f'⚠️ {warning}', 'warning')
        
        # Process the upload
        processor = ExcelUploadProcessor(db, {
            'Employee': Employee,
            'OvertimeHistory': OvertimeHistory,
            'FileUpload': FileUpload,
            'Position': Position,
            'Skill': Skill,
            'EmployeeSkill': EmployeeSkill
        })
        
        replace_all = request.form.get('replace_all') == 'true'
        
        result = processor.process_employee_upload(
            validated_data,
            {
                'filename': filename,
                'size': file_size,
                'uploaded_by_id': current_user.id
            },
            replace_all=replace_all
        )
        
        if result['success']:
            flash(f'✅ Successfully processed {result["created"]} new employees and updated {result["updated"]} existing employees', 'success')
            if result['errors']:
                flash(f'⚠️ {len(result["errors"])} records had errors', 'warning')
        else:
            flash(f'❌ Upload failed: {result["error"]}', 'error')
            
        return redirect(url_for('employee_import.upload_employees'))
        
    except Exception as e:
        current_app.logger.error(f"Error processing employee upload: {str(e)}\n{traceback.format_exc()}")
        flash(f'Error processing file: {str(e)}', 'error')
        return redirect(request.url)

# Overtime upload route
@employee_import_bp.route('/upload-overtime', methods=['GET', 'POST'])
@login_required
@supervisor_required
def upload_overtime():
    """Upload 13-week overtime history"""
    if request.method == 'GET':
        try:
            # Get current overtime statistics
            total_ot = db.session.query(func.sum(OvertimeHistory.overtime_hours)).scalar() or 0
            
            # Get recent overtime uploads
            recent_uploads = FileUpload.query.filter_by(
                file_type='overtime_import'
            ).order_by(FileUpload.upload_date.desc()).limit(10).all()
            
            # Get employees without overtime data
            employees_without_ot = db.session.query(Employee).outerjoin(
                OvertimeHistory
            ).filter(
                OvertimeHistory.id == None,
                Employee.id != current_user.id
            ).count()
            
            return render_template('upload_overtime.html',
                                 total_overtime_hours=total_ot,
                                 recent_uploads=recent_uploads,
                                 employees_without_ot=employees_without_ot)
                                 
        except Exception as e:
            current_app.logger.error(f"Error in upload_overtime GET: {str(e)}")
            flash(f'Error loading upload page: {str(e)}', 'error')
            return redirect(url_for('main.dashboard'))
    
    # POST - Process overtime upload
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'})
    
    file = request.files['file']
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'success': False, 'error': 'Invalid file type'})
    
    try:
        # Save file temporarily
        filename = secure_filename(file.filename)
        temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        file.save(temp_path)
        file_size = os.path.getsize(temp_path)
        
        # Read and validate
        df = pd.read_excel(temp_path, sheet_name='Overtime History')
        
        validator = ExcelUploadValidator()
        is_valid, validated_data = validator.validate_overtime_data(df)
        
        os.remove(temp_path)
        
        if not is_valid:
            return jsonify({
                'success': False,
                'errors': validator.errors[:10],
                'total_errors': len(validator.errors)
            })
        
        # Process the upload
        processor = ExcelUploadProcessor(db, {
            'Employee': Employee,
            'OvertimeHistory': OvertimeHistory,
            'FileUpload': FileUpload,
            'Position': Position,
            'Skill': Skill,
            'EmployeeSkill': EmployeeSkill
        })
        
        replace_all = request.form.get('replace_all') == 'true'
        
        result = processor.process_overtime_upload(
            validated_data,
            {
                'filename': filename,
                'size': file_size,
                'uploaded_by_id': current_user.id
            },
            replace_all=replace_all
        )
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Error processing overtime upload: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

# Export current data routes
@employee_import_bp.route('/export-current-employees')
@login_required
@supervisor_required
def export_current_employees():
    """Export current employee data in import template format"""
    try:
        # Get all employees with their data
        employees = Employee.query.filter(
            Employee.email != 'admin@workforce.com'
        ).order_by(Employee.crew, Employee.name).all()
        
        # Build export data
        data = []
        for emp in employees:
            # Get employee skills
            skills = [es.skill.name for es in emp.employee_skills]
            
            data.append({
                'Employee ID': emp.employee_id or f'EMP{emp.id}',
                'First Name': emp.name.split(' ')[0] if emp.name else '',
                'Last Name': ' '.join(emp.name.split(' ')[1:]) if emp.name and ' ' in emp.name else emp.name,
                'Email': emp.email,
                'Crew': emp.crew or '',
                'Position': emp.position.name if emp.position else '',
                'Department': '',  # Add department if you have it
                'Hire Date': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '',
                'Phone': emp.phone or '',
                'Emergency Contact': emp.emergency_contact or '',
                'Emergency Phone': emp.emergency_phone or '',
                'Skills': ','.join(skills)
            })
        
        # Create Excel file
        output = io.BytesIO()
        df = pd.DataFrame(data)
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Employee Data', index=False)
            
            # Format the sheet
            workbook = writer.book
            worksheet = writer.sheets['Employee Data']
            
            # Set column widths
            for i, col in enumerate(df.columns):
                column_len = max(df[col].astype(str).str.len().max(), len(col)) + 2
                worksheet.set_column(i, i, min(column_len, 50))
        
        output.seek(0)
        
        filename = f'employee_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        current_app.logger.error(f"Error exporting employees: {str(e)}")
        flash(f'Error exporting data: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

@employee_import_bp.route('/export-current-overtime')
@login_required
@supervisor_required
def export_current_overtime():
    """Export current overtime data in import template format"""
    try:
        # Get overtime data for last 13 weeks
        thirteen_weeks_ago = datetime.now().date() - timedelta(weeks=13)
        
        overtime_data = db.session.query(
            OvertimeHistory,
            Employee
        ).join(
            Employee
        ).filter(
            OvertimeHistory.week_start_date >= thirteen_weeks_ago
        ).order_by(
            Employee.employee_id,
            OvertimeHistory.week_start_date.desc()
        ).all()
        
        # Build export data
        data = []
        for ot, emp in overtime_data:
            week_end = ot.week_start_date + timedelta(days=6)
            
            data.append({
                'Employee ID': emp.employee_id or f'EMP{emp.id}',
                'Employee Name': emp.name,
                'Week Start Date': ot.week_start_date.strftime('%Y-%m-%d'),
                'Week End Date': week_end.strftime('%Y-%m-%d'),
                'Regular Hours': ot.regular_hours,
                'Overtime Hours': ot.overtime_hours,
                'Total Hours': ot.total_hours,
                'Notes': ''
            })
        
        # Create Excel file
        output = io.BytesIO()
        df = pd.DataFrame(data)
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Overtime History', index=False)
            
            # Add summary sheet
            summary_data = {
                'Metric': [
                    'Total Employees',
                    'Total Records',
                    'Total Overtime Hours',
                    'Average Weekly OT'
                ],
                'Value': [
                    len(set(d['Employee ID'] for d in data)),
                    len(data),
                    sum(d['Overtime Hours'] for d in data),
                    round(sum(d['Overtime Hours'] for d in data) / len(data), 1) if data else 0
                ]
            }
            
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name='Summary', index=False)
        
        output.seek(0)
        
        filename = f'overtime_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        current_app.logger.error(f"Error exporting overtime: {str(e)}")
        flash(f'Error exporting data: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

# Upload history and management
@employee_import_bp.route('/upload-history')
@login_required
@supervisor_required
def upload_history():
    """View upload history and manage uploads"""
    try:
        # Get upload history with pagination
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        uploads = FileUpload.query.order_by(
            FileUpload.upload_date.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        return render_template('upload_history.html',
                             uploads=uploads)
                             
    except Exception as e:
        current_app.logger.error(f"Error loading upload history: {str(e)}")
        flash(f'Error loading history: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

@employee_import_bp.route('/validate-upload', methods=['POST'])
@login_required
@supervisor_required
def validate_upload():
    """AJAX endpoint to validate upload before processing"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'})
    
    file = request.files['file']
    upload_type = request.form.get('type', 'employee')
    
    try:
        # Read file
        df = pd.read_excel(file)
        
        # Validate based on type
        validator = ExcelUploadValidator()
        
        if upload_type == 'employee':
            is_valid, validated_data = validator.validate_employee_data(df)
        elif upload_type == 'overtime':
            is_valid, validated_data = validator.validate_overtime_data(df)
        else:
            return jsonify({'success': False, 'error': 'Invalid upload type'})
        
        return jsonify({
            'success': is_valid,
            'errors': validator.errors[:10],
            'warnings': validator.warnings[:5],
            'total_errors': len(validator.errors),
            'total_warnings': len(validator.warnings),
            'records_valid': validator.processed_count,
            'records_failed': validator.failed_count
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
