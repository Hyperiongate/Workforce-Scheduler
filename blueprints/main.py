# blueprints/main.py
"""
Main blueprint for general routes
COMPLETE FIXED VERSION - Deploy this entire file
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, Employee, Schedule, Position, TimeOffRequest, ShiftSwapRequest, OvertimeHistory
from datetime import datetime, date, timedelta
from sqlalchemy import func, and_, or_
import logging

# Set up logging
logger = logging.getLogger(__name__)

# Create the blueprint FIRST before using it
main_bp = Blueprint('main', __name__)

# ==========================================
# DASHBOARD ROUTES
# ==========================================

@main_bp.route('/')
def index():
    """Landing page - redirects based on login status"""
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    return redirect(url_for('auth.login'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - redirects based on user role"""
    if current_user.is_supervisor:
        return redirect(url_for('supervisor.dashboard'))
    else:
        return redirect(url_for('main.employee_dashboard'))

@main_bp.route('/employee-dashboard')
@login_required
def employee_dashboard():
    """Employee dashboard with schedule and requests"""
    try:
        # Get current week schedules
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        
        schedules = Schedule.query.filter(
            Schedule.employee_id == current_user.id,
            Schedule.date >= week_start,
            Schedule.date <= week_end
        ).order_by(Schedule.date).all()
        
        # Get pending requests
        time_off_requests = TimeOffRequest.query.filter_by(
            employee_id=current_user.id
        ).order_by(TimeOffRequest.created_at.desc()).limit(5).all()
        
        swap_requests = ShiftSwapRequest.query.filter(
            or_(
                ShiftSwapRequest.requester_id == current_user.id,
                ShiftSwapRequest.target_employee_id == current_user.id
            )
        ).order_by(ShiftSwapRequest.created_at.desc()).limit(5).all()
        
        # Calculate stats
        total_hours_week = sum(
            (s.end_time.hour - s.start_time.hour) + 
            (s.end_time.minute - s.start_time.minute) / 60
            for s in schedules if s.start_time and s.end_time
        )
        
        # Get overtime hours
        overtime = OvertimeHistory.query.filter_by(
            employee_id=current_user.id
        ).order_by(OvertimeHistory.week_ending.desc()).first()
        
        overtime_hours = overtime.total_ot_hours if overtime else 0
        
        return render_template('employee_dashboard.html',
                             schedules=schedules,
                             time_off_requests=time_off_requests,
                             swap_requests=swap_requests,
                             total_hours_week=total_hours_week,
                             overtime_hours=overtime_hours,
                             week_start=week_start,
                             week_end=week_end)
                             
    except Exception as e:
        logger.error(f"Error loading employee dashboard: {e}")
        flash('Error loading dashboard. Please try again.', 'error')
        return render_template('employee_dashboard.html',
                             schedules=[],
                             time_off_requests=[],
                             swap_requests=[],
                             total_hours_week=0,
                             overtime_hours=0,
                             week_start=date.today(),
                             week_end=date.today())

# ==========================================
# CREW MANAGEMENT ROUTES
# ==========================================

@main_bp.route('/crew-management')
@login_required
def crew_management():
    """Crew management page"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    try:
        # Get all active employees grouped by crew
        crews = {}
        for crew in ['A', 'B', 'C', 'D']:
            crews[crew] = Employee.query.filter_by(
                crew=crew,
                is_active=True
            ).order_by(Employee.name).all()
        
        # Get unassigned employees
        unassigned = Employee.query.filter(
            or_(Employee.crew.is_(None), ~Employee.crew.in_(['A', 'B', 'C', 'D'])),
            Employee.is_active == True
        ).order_by(Employee.name).all()
        
        # Calculate crew statistics
        stats = {
            'total_employees': Employee.query.filter_by(is_active=True).count(),
            'crew_counts': {crew: len(employees) for crew, employees in crews.items()},
            'unassigned_count': len(unassigned),
            'positions': db.session.query(Position.name, func.count(Employee.id))\
                          .join(Employee)\
                          .filter(Employee.is_active == True)\
                          .group_by(Position.name)\
                          .all()
        }
        
        return render_template('crew_management.html',
                             crews=crews,
                             unassigned=unassigned,
                             stats=stats)
                             
    except Exception as e:
        logger.error(f"Error in crew management: {e}")
        flash('Error loading crew management page.', 'error')
        return redirect(url_for('supervisor.dashboard'))

@main_bp.route('/api/update-crew', methods=['POST'])
@login_required
def update_crew():
    """API endpoint to update employee crew assignment"""
    if not current_user.is_supervisor:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        employee_id = data.get('employee_id')
        new_crew = data.get('crew')
        
        # Validate crew
        if new_crew not in ['A', 'B', 'C', 'D', None]:
            return jsonify({'success': False, 'error': 'Invalid crew assignment'})
        
        # Update employee
        employee = Employee.query.get(employee_id)
        if not employee:
            return jsonify({'success': False, 'error': 'Employee not found'})
        
        old_crew = employee.crew
        employee.crew = new_crew
        db.session.commit()
        
        logger.info(f"Updated {employee.name} from crew {old_crew} to {new_crew}")
        
        return jsonify({
            'success': True,
            'message': f'Updated {employee.name} to crew {new_crew}',
            'employee': {
                'id': employee.id,
                'name': employee.name,
                'old_crew': old_crew,
                'new_crew': new_crew
            }
        })
        
    except Exception as e:
        logger.error(f"Error updating crew: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ==========================================
# PROFILE ROUTES
# ==========================================

@main_bp.route('/profile')
@login_required
def profile():
    """User profile page"""
    try:
        # Get employee details
        employee = Employee.query.get(current_user.id)
        
        # Get position info
        position = Position.query.get(employee.position_id) if employee.position_id else None
        
        # Get recent schedules
        recent_schedules = Schedule.query.filter_by(
            employee_id=current_user.id
        ).order_by(Schedule.date.desc()).limit(10).all()
        
        # Calculate statistics
        stats = {
            'total_scheduled_days': Schedule.query.filter_by(employee_id=current_user.id).count(),
            'total_time_off_requests': TimeOffRequest.query.filter_by(employee_id=current_user.id).count(),
            'approved_time_off': TimeOffRequest.query.filter_by(
                employee_id=current_user.id,
                status='approved'
            ).count(),
            'total_swap_requests': ShiftSwapRequest.query.filter(
                or_(
                    ShiftSwapRequest.requester_id == current_user.id,
                    ShiftSwapRequest.target_employee_id == current_user.id
                )
            ).count()
        }
        
        return render_template('profile.html',
                             employee=employee,
                             position=position,
                             recent_schedules=recent_schedules,
                             stats=stats)
                             
    except Exception as e:
        logger.error(f"Error loading profile: {e}")
        flash('Error loading profile page.', 'error')
        return redirect(url_for('main.dashboard'))

@main_bp.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    """Update user profile information"""
    try:
        employee = Employee.query.get(current_user.id)
        
        # Update allowed fields
        phone = request.form.get('phone')
        emergency_contact = request.form.get('emergency_contact')
        emergency_phone = request.form.get('emergency_phone')
        
        if phone:
            employee.phone = phone
        if emergency_contact:
            employee.emergency_contact = emergency_contact
        if emergency_phone:
            employee.emergency_phone = emergency_phone
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        
        logger.info(f"Profile updated for {employee.name}")
        
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        db.session.rollback()
        flash('Error updating profile. Please try again.', 'error')
    
    return redirect(url_for('main.profile'))

# ==========================================
# HELP & SUPPORT ROUTES
# ==========================================

@main_bp.route('/help')
@login_required
def help_page():
    """Help and documentation page"""
    return render_template('help.html')

@main_bp.route('/contact')
@login_required
def contact():
    """Contact support page"""
    return render_template('contact.html')

# ==========================================
# API ENDPOINTS
# ==========================================

@main_bp.route('/api/employee-stats')
@login_required
def employee_stats():
    """Get employee statistics"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        stats = {
            'total_employees': Employee.query.filter_by(is_active=True).count(),
            'crews': {
                'A': Employee.query.filter_by(crew='A', is_active=True).count(),
                'B': Employee.query.filter_by(crew='B', is_active=True).count(),
                'C': Employee.query.filter_by(crew='C', is_active=True).count(),
                'D': Employee.query.filter_by(crew='D', is_active=True).count()
            },
            'supervisors': Employee.query.filter_by(is_supervisor=True, is_active=True).count(),
            'positions': {}
        }
        
        # Get position counts
        positions = db.session.query(
            Position.name,
            func.count(Employee.id)
        ).join(Employee).filter(
            Employee.is_active == True
        ).group_by(Position.name).all()
        
        for pos_name, count in positions:
            stats['positions'][pos_name] = count
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Error getting employee stats: {e}")
        return jsonify({'error': str(e)}), 500

@main_bp.route('/api/schedule-summary')
@login_required
def schedule_summary():
    """Get schedule summary for current week"""
    try:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        
        if current_user.is_supervisor:
            # Get all schedules for the week
            schedules = Schedule.query.filter(
                Schedule.date >= week_start,
                Schedule.date <= week_end
            ).all()
        else:
            # Get only user's schedules
            schedules = Schedule.query.filter(
                Schedule.employee_id == current_user.id,
                Schedule.date >= week_start,
                Schedule.date <= week_end
            ).all()
        
        # Group by date
        schedule_data = {}
        for schedule in schedules:
            date_str = schedule.date.strftime('%Y-%m-%d')
            if date_str not in schedule_data:
                schedule_data[date_str] = []
            
            schedule_data[date_str].append({
                'id': schedule.id,
                'employee': schedule.employee.name if schedule.employee else 'Unknown',
                'shift_type': schedule.shift_type,
                'start_time': schedule.start_time.strftime('%H:%M') if schedule.start_time else None,
                'end_time': schedule.end_time.strftime('%H:%M') if schedule.end_time else None,
                'position': schedule.position
            })
        
        return jsonify({
            'week_start': week_start.strftime('%Y-%m-%d'),
            'week_end': week_end.strftime('%Y-%m-%d'),
            'schedules': schedule_data
        })
        
    except Exception as e:
        logger.error(f"Error getting schedule summary: {e}")
        return jsonify({'error': str(e)}), 500

# ==========================================
# ERROR HANDLERS (Blueprint specific)
# ==========================================

@main_bp.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors within this blueprint"""
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not found'}), 404
    return render_template('404.html'), 404

@main_bp.errorhandler(500)
def internal_error(error):
    """Handle 500 errors within this blueprint"""
    db.session.rollback()
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500
    return render_template('500.html'), 500
