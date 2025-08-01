# blueprints/employee_import.py - Enhanced version with complete upload system

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
import json

# Import validation and template generation utilities
import sys
sys.path.append('..')
try:
    from utils.excel_templates_generator import (
        create_employee_import_template,
        create_overtime_history_template,
        create_bulk_update_template
    )
    from utils.excel_upload_handler import ExcelUploadValidator, ExcelUploadProcessor
except ImportError:
    # Fallback if utils are in different location
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
            return redirect(url_for('employee.employee_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Enhanced upload page with new UI
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
        return jsonify({'success': False, 'error': 'No file provided'})
    
    file = request.files['file']
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'success': False, 'error': 'Invalid file type. Please upload an Excel file.'})
    
    try:
        # Save file temporarily
        filename = secure_filename(file.filename)
        temp_dir = current_app.config.get('UPLOAD_FOLDER', 'temp')
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
        
        temp_path = os.path.join(temp_dir, filename)
        file.save(temp_path)
        file_size = os.path.getsize(temp_path)
        
        # Read and validate the file
        df = pd.read_excel(temp_path, sheet_name='Employee Data' if 'Employee Data' in pd.ExcelFile(temp_path).sheet_names else 0)
        
        # Initialize validator
        validator = ExcelUploadValidator()
        is_valid, validated_data = validator.validate_employee_data(df)
        
        # Remove temp file
        os.remove(temp_path)
        
        if not is_valid:
            return jsonify({
                'success': False,
                'errors': validator.errors[:10],
                'total_errors': len(validator.errors),
                'warnings': validator.warnings[:5],
                'total_warnings': len(validator.warnings)
            })
        
        # Process the upload
        processor = ExcelUploadProcessor(db, {
            'Employee': Employee,
            'Position': Position,
            'Skill': Skill,
            'EmployeeSkill': EmployeeSkill,
            'FileUpload': FileUpload
        })
        
        replace_all = request.form.get('replace_all') == 'on'
        
        result = processor.process_employee_upload(
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
        current_app.logger.error(f"Error processing employee upload: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

# Overtime upload page
@employee_import_bp.route('/upload-overtime', methods=['GET', 'POST'])
@login_required
@supervisor_required
def upload_overtime():
    """Upload overtime history data"""
    if request.method == 'GET':
        try:
            # Get overtime statistics
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
        temp_dir = current_app.config.get('UPLOAD_FOLDER', 'temp')
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            
        temp_path = os.path.join(temp_dir, filename)
        file.save(temp_path)
        file_size = os.path.getsize(temp_path)
        
        # Read and validate
        sheet_name = 'Overtime History' if 'Overtime History' in pd.ExcelFile(temp_path).sheet_names else 0
        df = pd.read_excel(temp_path, sheet_name=sheet_name)
        
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
            'FileUpload': FileUpload
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
        
        # Add summary information
        if result['success']:
            result['summary'] = {
                'processed': result.get('records_imported', 0),
                'added': result.get('records_added', 0),
                'updated': result.get('records_updated', 0),
                'employees': len(set([r.get('employee_id') for r in validated_data if 'employee_id' in r])),
                'weeks': len(set([r.get('week_start') for r in validated_data if 'week_start' in r])),
                'total_hours': sum([r.get('overtime_hours', 0) for r in validated_data])
            }
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Error processing overtime upload: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

# Validation endpoint
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

# Overtime validation endpoint
@employee_import_bp.route('/upload-overtime/validate', methods=['POST'])
@login_required
@supervisor_required
def validate_overtime():
    """Validate overtime file before upload"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'})
    
    file = request.files['file']
    
    try:
        # Read file
        df = pd.read_excel(file)
        
        # Validate
        validator = ExcelUploadValidator()
        is_valid, validated_data = validator.validate_overtime_data(df)
        
        # Calculate summary
        summary = {}
        if is_valid and validated_data:
            summary = {
                'employees': len(set([r.get('employee_id') for r in validated_data if 'employee_id' in r])),
                'weeks': len(set([r.get('week_start') for r in validated_data if 'week_start' in r])),
                'total_hours': sum([r.get('overtime_hours', 0) for r in validated_data])
            }
        
        return jsonify({
            'success': is_valid,
            'records': len(validated_data),
            'errors': validator.errors[:10],
            'warnings': validator.warnings[:5],
            'summary': summary
        })
        
    except Exception as e:
        return jsonify({'success': False, 'errors': [str(e)]})

# Template download routes
@employee_import_bp.route('/download-employee-template')
@login_required
@supervisor_required
def download_employee_template():
    """Download employee import template"""
    try:
        output = create_employee_import_template()
        filename = f'employee_import_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        current_app.logger.error(f"Error generating employee template: {str(e)}")
        flash(f'Error generating template: {str(e)}', 'error')
        return redirect(url_for('employee_import.upload_employees'))

@employee_import_bp.route('/download-overtime-template')
@login_required
@supervisor_required
def download_overtime_template():
    """Download overtime history template"""
    try:
        output = create_overtime_history_template()
        filename = f'overtime_history_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        current_app.logger.error(f"Error generating overtime template: {str(e)}")
        flash(f'Error generating template: {str(e)}', 'error')
        return redirect(url_for('employee_import.upload_overtime'))

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
        
        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Create Excel file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Employee Data', index=False)
            
            # Get worksheet
            worksheet = writer.sheets['Employee Data']
            
            # Auto-adjust column widths
            for i, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.set_column(i, i, max_len)
        
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
        return redirect(url_for('employee_import.upload_employees'))

@employee_import_bp.route('/export-current-overtime')
@login_required
@supervisor_required
def export_current_overtime():
    """Export current overtime data"""
    try:
        # Get all overtime history
        overtime_data = db.session.query(
            OvertimeHistory,
            Employee
        ).join(
            Employee, OvertimeHistory.employee_id == Employee.id
        ).order_by(
            Employee.employee_id,
            OvertimeHistory.week_start.desc()
        ).all()
        
        # Build export data
        data = []
        for ot, emp in overtime_data:
            data.append({
                'Employee ID': emp.employee_id or f'EMP{emp.id}',
                'Employee Name': emp.name,
                'Week Starting': ot.week_start.strftime('%Y-%m-%d'),
                'Week Ending': ot.week_end.strftime('%Y-%m-%d'),
                'Regular Hours': ot.regular_hours,
                'Overtime Hours': ot.overtime_hours,
                'Total Hours': ot.total_hours,
                'Notes': ot.notes or ''
            })
        
        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Create Excel file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Overtime History', index=False)
            
            # Format worksheet
            worksheet = writer.sheets['Overtime History']
            for i, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.set_column(i, i, max_len)
        
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
        return redirect(url_for('employee_import.upload_overtime'))

# Upload history management
@employee_import_bp.route('/upload-history')
@login_required
@supervisor_required
def upload_history():
    """View upload history and manage uploads"""
    try:
        # Get filter parameters
        upload_type = request.args.get('type', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        # Build query
        query = FileUpload.query
        
        if upload_type:
            query = query.filter_by(file_type=upload_type)
        
        if start_date:
            query = query.filter(FileUpload.upload_date >= datetime.strptime(start_date, '%Y-%m-%d'))
        
        if end_date:
            query = query.filter(FileUpload.upload_date <= datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1))
        
        # Get paginated results
        uploads = query.order_by(
            FileUpload.upload_date.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        # Get statistics
        successful_uploads = FileUpload.query.filter_by(status='completed').count()
        partial_uploads = FileUpload.query.filter_by(status='partial').count()
        failed_uploads = FileUpload.query.filter_by(status='failed').count()
        
        return render_template('upload_history.html',
                             uploads=uploads,
                             successful_uploads=successful_uploads,
                             partial_uploads=partial_uploads,
                             failed_uploads=failed_uploads)
                             
    except Exception as e:
        current_app.logger.error(f"Error loading upload history: {str(e)}")
        flash(f'Error loading history: {str(e)}', 'error')
        return redirect(url_for('main.dashboard'))

@employee_import_bp.route('/upload-history/<int:upload_id>/details')
@login_required
@supervisor_required
def upload_details(upload_id):
    """Get upload details for modal"""
    try:
        upload = FileUpload.query.get_or_404(upload_id)
        
        return jsonify({
            'filename': upload.filename,
            'file_type': upload.file_type,
            'upload_date': upload.upload_date.strftime('%Y-%m-%d %H:%M:%S'),
            'uploaded_by': upload.uploaded_by.name,
            'file_size': upload.file_size,
            'records_processed': upload.records_processed,
            'records_failed': upload.records_failed,
            'status': upload.status,
            'upload_log': upload.upload_log
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@employee_import_bp.route('/upload-history/<int:upload_id>/download')
@login_required
@supervisor_required
def download_upload(upload_id):
    """Download original upload file if available"""
    try:
        upload = FileUpload.query.get_or_404(upload_id)
        
        # In a real implementation, you would store and retrieve the actual file
        # For now, we'll just show an error
        flash('File download not available for this upload', 'warning')
        return redirect(url_for('employee_import.upload_history'))
        
    except Exception as e:
        flash(f'Error downloading file: {str(e)}', 'error')
        return redirect(url_for('employee_import.upload_history'))

@employee_import_bp.route('/upload-history/<int:upload_id>/delete', methods=['POST'])
@login_required
@supervisor_required
def delete_upload(upload_id):
    """Delete upload record"""
    try:
        upload = FileUpload.query.get_or_404(upload_id)
        
        db.session.delete(upload)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400
