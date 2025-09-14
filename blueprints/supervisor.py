# Add this to your blueprints/supervisor.py file
# COMPLETE EMPLOYEE MANAGEMENT ROUTE
# Last Updated: 2025-01-14

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, Employee, Position, Skill, EmployeeSkill, OvertimeHistory
from functools import wraps
from sqlalchemy import func
import logging

logger = logging.getLogger(__name__)

# If blueprint doesn't exist, create it
# supervisor_bp = Blueprint('supervisor', __name__, url_prefix='/supervisor')

def supervisor_required(f):
    """Decorator to require supervisor access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.is_supervisor:
            flash('Access denied. Supervisors only.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@supervisor_bp.route('/employee-management')
@login_required
@supervisor_required
def employee_management():
    """Complete employee management page with all data"""
    try:
        # Get all employees with their relationships eagerly loaded
        employees = db.session.query(Employee).options(
            db.joinedload(Employee.position),
            db.joinedload(Employee.employee_skills).joinedload(EmployeeSkill.skill)
        ).order_by(Employee.crew, Employee.name).all()
        
        # Get all positions for filter dropdown
        positions = Position.query.order_by(Position.name).all()
        
        # Get total skills count
        total_skills = Skill.query.count()
        
        # Calculate statistics
        stats = {
            'total': len(employees),
            'active': sum(1 for e in employees if e.is_active),
            'inactive': sum(1 for e in employees if not e.is_active),
            'supervisors': sum(1 for e in employees if e.is_supervisor),
            'crews': {
                'A': sum(1 for e in employees if e.crew == 'A'),
                'B': sum(1 for e in employees if e.crew == 'B'),
                'C': sum(1 for e in employees if e.crew == 'C'),
                'D': sum(1 for e in employees if e.crew == 'D'),
                'unassigned': sum(1 for e in employees if not e.crew or e.crew not in ['A','B','C','D'])
            }
        }
        
        return render_template(
            'employee_management.html',
            employees=employees,
            positions=positions,
            total_skills=total_skills,
            stats=stats
        )
        
    except Exception as e:
        logger.error(f"Error loading employee management: {e}")
        flash('Error loading employee data. Please try again.', 'error')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/api/employee/<int:employee_id>')
@login_required
@supervisor_required
def get_employee_details(employee_id):
    """API endpoint to get employee details for AJAX"""
    try:
        employee = Employee.query.get_or_404(employee_id)
        
        # Build response data
        data = {
            'id': employee.id,
            'employee_id': employee.employee_id,
            'name': employee.name,
            'email': employee.email,
            'phone': employee.phone,
            'crew': employee.crew,
            'position': employee.position.name if employee.position else None,
            'position_id': employee.position_id,
            'department': employee.department,
            'is_active': employee.is_active,
            'is_supervisor': employee.is_supervisor,
            'hire_date': employee.hire_date.isoformat() if employee.hire_date else None,
            'skills': [
                {
                    'id': es.skill.id,
                    'name': es.skill.name,
                    'category': es.skill.category,
                    'certified_date': es.certified_date.isoformat() if es.certified_date else None,
                    'expiry_date': es.expiry_date.isoformat() if es.expiry_date else None
                }
                for es in employee.employee_skills
            ],
            'overtime_avg': 0  # Calculate if needed
        }
        
        # Calculate average overtime if data exists
        if employee.overtime_histories:
            recent_ot = employee.overtime_histories.limit(13).all()
            if recent_ot:
                data['overtime_avg'] = sum(h.overtime_hours for h in recent_ot) / len(recent_ot)
        
        return jsonify(data)
        
    except Exception as e:
        logger.error(f"Error getting employee details: {e}")
        return jsonify({'error': str(e)}), 500

@supervisor_bp.route('/api/employee/<int:employee_id>/toggle-status', methods=['POST'])
@login_required
@supervisor_required
def toggle_employee_status(employee_id):
    """Toggle employee active/inactive status"""
    try:
        employee = Employee.query.get_or_404(employee_id)
        
        # Don't allow deactivating yourself
        if employee.id == current_user.id and employee.is_active:
            return jsonify({'error': 'You cannot deactivate your own account'}), 400
        
        employee.is_active = not employee.is_active
        db.session.commit()
        
        action = 'activated' if employee.is_active else 'deactivated'
        logger.info(f"Employee {employee.employee_id} {action} by {current_user.name}")
        
        return jsonify({
            'success': True,
            'is_active': employee.is_active,
            'message': f'Employee {action} successfully'
        })
        
    except Exception as e:
        logger.error(f"Error toggling employee status: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@supervisor_bp.route('/api/employee/<int:employee_id>', methods=['PUT'])
@login_required
@supervisor_required
def update_employee(employee_id):
    """Update employee details"""
    try:
        employee = Employee.query.get_or_404(employee_id)
        data = request.get_json()
        
        # Update fields if provided
        if 'name' in data:
            employee.name = data['name']
        if 'email' in data:
            employee.email = data['email']
        if 'phone' in data:
            employee.phone = data['phone']
        if 'crew' in data:
            employee.crew = data['crew']
        if 'position_id' in data:
            employee.position_id = data['position_id']
        if 'department' in data:
            employee.department = data['department']
        if 'is_supervisor' in data:
            # Don't allow removing your own supervisor status
            if employee.id == current_user.id and not data['is_supervisor']:
                return jsonify({'error': 'You cannot remove your own supervisor status'}), 400
            employee.is_supervisor = data['is_supervisor']
        
        db.session.commit()
        logger.info(f"Employee {employee.employee_id} updated by {current_user.name}")
        
        return jsonify({
            'success': True,
            'message': 'Employee updated successfully'
        })
        
    except Exception as e:
        logger.error(f"Error updating employee: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@supervisor_bp.route('/api/employees/export')
@login_required
@supervisor_required
def export_employees_json():
    """Export employee data as JSON for other systems"""
    try:
        employees = Employee.query.filter_by(is_active=True).all()
        
        data = []
        for emp in employees:
            data.append({
                'employee_id': emp.employee_id,
                'name': emp.name,
                'email': emp.email,
                'crew': emp.crew,
                'position': emp.position.name if emp.position else None,
                'is_supervisor': emp.is_supervisor,
                'skills': [es.skill.name for es in emp.employee_skills]
            })
        
        return jsonify({
            'employees': data,
            'count': len(data),
            'exported_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error exporting employees: {e}")
        return jsonify({'error': str(e)}), 500
