# blueprints/employee_import.py

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from utils.decorators import supervisor_required
from models import db, Employee, Position, OvertimeHistory, UploadHistory
from utils.excel_upload_handler import ExcelUploadHandler
from utils.excel_templates_generator import ExcelTemplateGenerator
import os
import pandas as pd
from datetime import datetime, timedelta
import json
from sqlalchemy import func

bp = Blueprint('employee_import', __name__, url_prefix='/employees')

ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Main upload page with enhanced interface
@bp.route('/upload-employees')
@login_required
@supervisor_required
def upload_employees():
    """Enhanced employee upload interface"""
    # Get statistics for dashboard
    total_employees = Employee.query.filter_by(is_active=True).count()
    crew_distribution = db.session.query(
        Employee.crew, func.count(Employee.id)
    ).filter_by(is_active=True).group_by(Employee.crew).all()
    
    recent_uploads = UploadHistory.query.filter_by(
        upload_type='employee'
    ).order_by(UploadHistory.upload_date.desc()).limit(3).all()
    
    employees_without_ot = Employee.query.filter(
        ~Employee.id.in_(
            db.session.query(OvertimeHistory.employee_id).distinct()
        )
    ).count()
    
    return render_template('upload_employees_enhanced.html',
                         total_employees=total_employees,
                         crew_distribution=crew_distribution,
                         recent_uploads=recent_uploads,
                         employees_without_ot=employees_without_ot)

# Overtime upload page
@bp.route('/upload-overtime')
@login_required
@supervisor_required
def upload_overtime():
    """Overtime history upload interface"""
    # Get overtime statistics
    total_ot_hours = db.session.query(func.sum(OvertimeHistory.hours)).scalar() or 0
    employees_with_ot = db.session.query(func.count(func.distinct(OvertimeHistory.employee_id))).scalar()
    
    # Get high OT employees (>50 hours average)
    high_ot_employees = db.session.query(
        Employee.name,
        func.avg(OvertimeHistory.hours).label('avg_hours')
    ).join(OvertimeHistory).group_by(Employee.id, Employee.name).having(
        func.avg(OvertimeHistory.hours) > 50
    ).all()
    
    recent_uploads = UploadHistory.query.filter_by(
        upload_type='overtime'
    ).order_by(UploadHistory.upload_date.desc()).limit(3).all()
    
    return render_template('upload_overtime.html',
                         total_ot_hours=total_ot_hours,
                         employees_with_ot=employees_with_ot,
                         high_ot_employees=high_ot_employees,
                         recent_uploads=recent_uploads)

# Upload history page
@bp.route('/upload-history')
@login_required
@supervisor_required
def upload_history():
    """View upload history with filtering"""
    page = request.args.get('page', 1, type=int)
    upload_type = request.args.get('type', 'all')
    
    query = UploadHistory.query
    
    if upload_type != 'all':
        query = query.filter_by(upload_type=upload_type)
    
    uploads = query.order_by(UploadHistory.upload_date.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    
    return render_template('upload_history.html',
                         uploads=uploads,
                         upload_type=upload_type)

# Validate upload endpoint - THIS WAS MISSING
@bp.route('/validate-upload', methods=['POST'])
@login_required
@supervisor_required
def validate_upload():
    """Validate Excel file before processing"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'errors': ['No file provided']}), 400
    
    file = request.files['file']
    upload_type = request.form.get('upload_type', 'employee')
    
    if file.filename == '':
        return jsonify({'success': False, 'errors': ['No file selected']}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'errors': ['Invalid file type. Please upload .xlsx or .xls files']}), 400
    
    # Save file temporarily
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_{filename}"
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    
    # Ensure upload folder exists
    os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    file.save(filepath)
    
    try:
        handler = ExcelUploadHandler(filepath)
        
        if upload_type == 'employee':
            is_valid, errors, warnings, preview_data = handler.validate_employee_data()
        elif upload_type == 'overtime':
            is_valid, errors, warnings, preview_data = handler.validate_overtime_data()
        elif upload_type == 'bulk_update':
            is_valid, errors, warnings, preview_data = handler.validate_bulk_update()
        else:
            return jsonify({'success': False, 'errors': ['Invalid upload type']}), 400
        
        # Store file path in session for actual import
        from flask import session
        session['pending_upload'] = {
            'filepath': filepath,
            'upload_type': upload_type,
            'filename': file.filename
        }
        
        return jsonify({
            'success': is_valid,
            'errors': errors,
            'warnings': warnings,
            'preview': preview_data,
            'record_count': len(preview_data) if preview_data else 0
        })
        
    except Exception as e:
        # Clean up file on error
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'success': False, 'errors': [f'Error processing file: {str(e)}']}), 500

# Process upload endpoint
@bp.route('/process-upload', methods=['POST'])
@login_required
@supervisor_required
def process_upload():
    """Process validated Excel file"""
    from flask import session
    
    if 'pending_upload' not in session:
        return jsonify({'success': False, 'error': 'No pending upload found'}), 400
    
    pending = session['pending_upload']
    filepath = pending['filepath']
    upload_type = pending['upload_type']
    filename = pending['filename']
    
    if not os.path.exists(filepath):
        return jsonify({'success': False, 'error': 'Upload file not found'}), 400
    
    replace_all = request.json.get('replace_all', False)
    
    try:
        handler = ExcelUploadHandler(filepath)
        
        if upload_type == 'employee':
            success, message, stats = handler.import_employees(replace_all=replace_all)
        elif upload_type == 'overtime':
            success, message, stats = handler.import_overtime(replace_all=replace_all)
        elif upload_type == 'bulk_update':
            success, message, stats = handler.process_bulk_update()
        else:
            return jsonify({'success': False, 'error': 'Invalid upload type'}), 400
        
        if success:
            # Record in upload history
            upload_record = UploadHistory(
                upload_type=upload_type,
                filename=filename,
                uploaded_by=current_user.id,
                upload_date=datetime.utcnow(),
                status='completed',
                records_processed=stats.get('processed', 0),
                records_failed=stats.get('failed', 0),
                details=json.dumps(stats)
            )
            db.session.add(upload_record)
            db.session.commit()
            
            # Clean up session
            session.pop('pending_upload', None)
            
            # Keep file for history
            new_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'history', filename)
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            os.rename(filepath, new_path)
            
            return jsonify({
                'success': True,
                'message': message,
                'stats': stats
            })
        else:
            # Clean up file on failure
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({'success': False, 'error': message}), 400
            
    except Exception as e:
        # Clean up on error
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'success': False, 'error': f'Processing error: {str(e)}'})

# Template download endpoints
@bp.route('/download-template/<template_type>')
@login_required
@supervisor_required
def download_template(template_type):
    """Download Excel templates"""
    generator = ExcelTemplateGenerator()
    
    if template_type == 'employee':
        filepath = generator.create_employee_template()
        filename = 'employee_upload_template.xlsx'
    elif template_type == 'overtime':
        filepath = generator.create_overtime_template()
        filename = 'overtime_upload_template.xlsx'
    elif template_type == 'bulk_update':
        filepath = generator.create_bulk_update_template()
        filename = 'bulk_update_template.xlsx'
    else:
        flash('Invalid template type', 'error')
        return redirect(url_for('employee_import.upload_employees'))
    
    return send_file(filepath, as_attachment=True, download_name=filename)

# Export endpoints
@bp.route('/export/<export_type>')
@login_required
@supervisor_required
def export_data(export_type):
    """Export current data"""
    try:
        if export_type == 'employees':
            employees = Employee.query.filter_by(is_active=True).all()
            data = []
            for emp in employees:
                data.append({
                    'Employee ID': emp.employee_id,
                    'First Name': emp.name.split()[0] if emp.name else '',
                    'Last Name': ' '.join(emp.name.split()[1:]) if emp.name and len(emp.name.split()) > 1 else '',
                    'Email': emp.email,
                    'Phone': emp.phone or '',
                    'Position': emp.position.name if emp.position else '',
                    'Department': emp.department or '',
                    'Crew': emp.crew or '',
                    'Hire Date': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '',
                    'Is Supervisor': 'Yes' if emp.is_supervisor else 'No',
                    'Max Hours/Week': emp.max_hours_per_week or 40
                })
            
            df = pd.DataFrame(data)
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'exports', f'employees_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            df.to_excel(filepath, index=False, sheet_name='Employee Data')
            
            return send_file(filepath, as_attachment=True, download_name='employees_export.xlsx')
            
        elif export_type == 'overtime':
            # Get all overtime data
            overtime_data = db.session.query(
                Employee.employee_id,
                Employee.name,
                OvertimeHistory.week_ending,
                OvertimeHistory.hours
            ).join(OvertimeHistory).order_by(Employee.employee_id, OvertimeHistory.week_ending).all()
            
            # Pivot data for export
            data_dict = {}
            for emp_id, name, week_ending, hours in overtime_data:
                if emp_id not in data_dict:
                    data_dict[emp_id] = {'Employee ID': emp_id, 'Name': name}
                week_str = f"Week {week_ending.strftime('%m/%d/%Y')}"
                data_dict[emp_id][week_str] = hours
            
            df = pd.DataFrame(list(data_dict.values()))
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'exports', f'overtime_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            df.to_excel(filepath, index=False, sheet_name='Overtime Data')
            
            return send_file(filepath, as_attachment=True, download_name='overtime_export.xlsx')
            
    except Exception as e:
        flash(f'Export failed: {str(e)}', 'error')
        return redirect(url_for('employee_import.upload_employees'))

# Delete upload history record
@bp.route('/delete-upload/<int:upload_id>', methods=['POST'])
@login_required
@supervisor_required
def delete_upload(upload_id):
    """Delete upload history record"""
    upload = UploadHistory.query.get_or_404(upload_id)
    
    # Delete associated file if exists
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'history', upload.filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    
    db.session.delete(upload)
    db.session.commit()
    
    return jsonify({'success': True})

# Get upload statistics
@bp.route('/upload-stats')
@login_required
@supervisor_required
def upload_stats():
    """Get upload statistics for dashboard"""
    stats = {
        'total_employees': Employee.query.filter_by(is_active=True).count(),
        'employees_with_ot': db.session.query(func.count(func.distinct(OvertimeHistory.employee_id))).scalar(),
        'recent_uploads': UploadHistory.query.count(),
        'crew_distribution': dict(db.session.query(
            Employee.crew, func.count(Employee.id)
        ).filter_by(is_active=True).group_by(Employee.crew).all())
    }
    
    return jsonify(stats)
