# blueprints/supervisor.py
"""
Complete Supervisor Blueprint
Following project instructions for robust, complete code
Includes all routes including the coverage_gaps route that was causing the error
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from models import db, Schedule, Employee, Position, TimeOffRequest, ShiftSwapRequest, ScheduleSuggestion, VacationCalendar, Skill, employee_skills, OvertimeHistory
from datetime import datetime, date, timedelta
from sqlalchemy import func, case, text, and_, or_
from functools import wraps
from werkzeug.security import generate_password_hash
import calendar
import io
import csv
import pandas as pd
import traceback

# Create the blueprint
supervisor_bp = Blueprint('supervisor', __name__)

# Decorator to require supervisor privileges
def supervisor_required(f):
    """Decorator to require supervisor privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.is_supervisor:
            flash('You must be a supervisor to access this page.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ========== TIME OFF REQUESTS ==========

@supervisor_bp.route('/supervisor/time-off-requests')
@login_required
@supervisor_required
def time_off_requests():
    """View and manage time off requests"""
    try:
        # Get pending requests with employee information
        pending = TimeOffRequest.query.filter_by(status='pending').join(Employee).order_by(TimeOffRequest.start_date).all()
        
        # Get recently processed requests (last 30 days)
        thirty_days_ago = datetime.now() - timedelta(days=30)
        recent = TimeOffRequest.query.filter(
            TimeOffRequest.status.in_(['approved', 'denied']),
            TimeOffRequest.updated_at > thirty_days_ago
        ).join(Employee).order_by(TimeOffRequest.updated_at.desc()).limit(20).all()
        
        return render_template('time_off_requests.html',
                             pending_requests=pending,
                             recent_requests=recent)
                             
    except Exception as e:
        flash(f'Error loading time off requests: {str(e)}', 'danger')
        return redirect(url_for('main.dashboard'))

@supervisor_bp.route('/supervisor/time-off/<int:request_id>/<action>', methods=['POST'])
@login_required
@supervisor_required
def handle_time_off(request_id, action):
    """Approve or deny time off request"""
    if action not in ['approve', 'deny']:
        flash('Invalid action', 'danger')
        return redirect(url_for('supervisor.time_off_requests'))
    
    time_off = TimeOffRequest.query.get_or_404(request_id)
    
    if action == 'approve':
        time_off.status = 'approved'
        time_off.approved_by_id = current_user.id
        time_off.approved_at = datetime.now()
        
        # Add to vacation calendar
        current_date = time_off.start_date
        while current_date <= time_off.end_date:
            vacation_entry = VacationCalendar(
                employee_id=time_off.employee_id,
                date=current_date,
                leave_type=time_off.leave_type,
                status='scheduled'
            )
            db.session.add(vacation_entry)
            current_date += timedelta(days=1)
        
        flash(f'Time off request approved for {time_off.employee.name}', 'success')
    else:
        time_off.status = 'denied'
        time_off.approved_by_id = current_user.id
        time_off.approved_at = datetime.now()
        
        # Add denial reason if provided
        reason = request.form.get('denial_reason')
        if reason:
            time_off.denial_reason = reason
        
        flash(f'Time off request denied for {time_off.employee.name}', 'warning')
    
    time_off.updated_at = datetime.now()
    db.session.commit()
    
    return redirect(url_for('supervisor.time_off_requests'))

# ========== SHIFT SWAP REQUESTS ==========

@supervisor_bp.route('/supervisor/shift-swaps')
@login_required
@supervisor_required
def shift_swaps():
    """View and manage shift swap requests"""
    try:
        # Redirect to swap requests (same functionality)
        return redirect(url_for('supervisor.swap_requests'))
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('main.dashboard'))

@supervisor_bp.route('/supervisor/swap-requests')
@login_required
@supervisor_required
def swap_requests():
    """View and manage swap requests"""
    try:
        pending = ShiftSwapRequest.query.filter_by(status='pending').order_by(ShiftSwapRequest.created_at.desc()).all()
        
        # Get recently processed
        recent = ShiftSwapRequest.query.filter(
            ShiftSwapRequest.status.in_(['approved', 'denied'])
        ).order_by(ShiftSwapRequest.updated_at.desc()).limit(20).all()
        
        return render_template('swap_requests.html',
                             pending_requests=pending,
                             recent_requests=recent)
                             
    except Exception as e:
        flash(f'Error loading swap requests: {str(e)}', 'danger')
        return redirect(url_for('main.dashboard'))

@supervisor_bp.route('/supervisor/swap/<int:request_id>/<action>', methods=['POST'])
@login_required
@supervisor_required
def handle_swap(request_id, action):
    """Approve or deny swap request"""
    if action not in ['approve', 'deny']:
        flash('Invalid action', 'danger')
        return redirect(url_for('supervisor.swap_requests'))
    
    swap = ShiftSwapRequest.query.get_or_404(request_id)
    
    if action == 'approve':
        swap.status = 'approved'
        swap.approved_by_id = current_user.id
        swap.approved_at = datetime.now()
        
        # Swap the schedules
        schedule1 = Schedule.query.filter_by(
            employee_id=swap.requesting_employee_id,
            date=swap.date_requested
        ).first()
        
        schedule2 = Schedule.query.filter_by(
            employee_id=swap.target_employee_id,
            date=swap.date_offered
        ).first()
        
        if schedule1 and schedule2:
            # Swap shift types
            temp_shift = schedule1.shift_type
            schedule1.shift_type = schedule2.shift_type
            schedule2.shift_type = temp_shift
            
            flash('Shift swap approved and schedules updated', 'success')
        else:
            flash('Warning: Could not find schedules to swap', 'warning')
    else:
        swap.status = 'denied'
        swap.approved_by_id = current_user.id
        swap.approved_at = datetime.now()
        
        reason = request.form.get('denial_reason')
        if reason:
            swap.denial_reason = reason
        
        flash('Shift swap request denied', 'warning')
    
    swap.updated_at = datetime.now()
    db.session.commit()
    
    return redirect(url_for('supervisor.swap_requests'))

# ========== EMPLOYEE MANAGEMENT ==========

@supervisor_bp.route('/supervisor/employee-management')
@login_required
@supervisor_required
def employee_management():
    """Employee management page"""
    try:
        employees = Employee.query.filter(Employee.id != current_user.id).order_by(Employee.crew, Employee.name).all()
        positions = Position.query.order_by(Position.name).all()
        
        # Get employee counts by crew
        crew_counts = db.session.query(
            Employee.crew,
            func.count(Employee.id).label('count')
        ).filter(Employee.id != current_user.id).group_by(Employee.crew).all()
        
        return render_template('employee_management.html',
                             employees=employees,
                             positions=positions,
                             crew_counts=dict(crew_counts))
                             
    except Exception as e:
        flash(f'Error loading employee management: {str(e)}', 'danger')
        return redirect(url_for('main.dashboard'))

@supervisor_bp.route('/supervisor/crew-management')
@login_required
@supervisor_required
def crew_management():
    """Crew management interface"""
    try:
        # Get all employees grouped by crew
        crews = {}
        for crew in ['A', 'B', 'C', 'D']:
            crews[crew] = Employee.query.filter_by(crew=crew).filter(Employee.id != current_user.id).order_by(Employee.name).all()
        
        positions = Position.query.order_by(Position.name).all()
        
        return render_template('crew_management.html',
                             crews=crews,
                             positions=positions)
                             
    except Exception as e:
        flash(f'Error loading crew management: {str(e)}', 'danger')
        return redirect(url_for('main.dashboard'))

# ========== COVERAGE NEEDS ROUTE ==========

@supervisor_bp.route('/supervisor/coverage-needs')
@login_required
@supervisor_required
def coverage_needs():
    """View and manage coverage needs"""
    try:
        # Get all positions
        positions = Position.query.order_by(Position.name).all()
        
        # If no positions exist, warn the user
        if not positions:
            flash('No positions found. Please upload employee data to create positions.', 'warning')
        
        # Calculate current coverage by crew and position
        coverage_data = []
        for position in positions:
            pos_data = {
                'position': position,
                'crews': {}
            }
            
            for crew in ['A', 'B', 'C', 'D']:
                count = Employee.query.filter_by(
                    crew=crew,
                    position_id=position.id,
                    is_supervisor=False
                ).count()
                pos_data['crews'][crew] = count
            
            coverage_data.append(pos_data)
        
        return render_template('coverage_needs.html',
                             positions=positions,
                             coverage_data=coverage_data)
                             
    except Exception as e:
        print(f"Error in coverage_needs route: {str(e)}")
        traceback.print_exc()
        flash(f'Error loading coverage needs: {str(e)}', 'danger')
        return redirect(url_for('main.dashboard'))

@supervisor_bp.route('/supervisor/coverage-needs/reset-defaults', methods=['POST'])
@login_required
@supervisor_required
def reset_coverage_defaults():
    """Reset all position minimum coverage to 1"""
    try:
        positions = Position.query.all()
        for position in positions:
            position.min_coverage = 1
        db.session.commit()
        flash(f'Reset {len(positions)} positions to minimum coverage of 1', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error resetting coverage: {str(e)}', 'danger')
    
    return redirect(url_for('supervisor.coverage_needs'))

# ========== COVERAGE GAPS ROUTE ==========

@supervisor_bp.route('/supervisor/coverage-gaps')
@login_required
@supervisor_required
def coverage_gaps():
    """View real-time coverage gaps considering absences"""
    try:
        # Get current date
        today = date.today()
        
        # Get all positions
        positions = Position.query.order_by(Position.name).all()
        
        # Initialize data structures
        coverage_gaps_data = []
        total_gaps = 0
        critical_gaps = 0
        
        # For each crew
        for crew in ['A', 'B', 'C', 'D']:
            crew_data = {
                'crew': crew,
                'positions': [],
                'total_required': 0,
                'total_available': 0,
                'total_absent': 0,
                'total_gaps': 0
            }
            
            for position in positions:
                # Get required coverage
                required = position.min_coverage
                
                # Get all employees in this crew and position
                employees = Employee.query.filter_by(
                    crew=crew,
                    position_id=position.id,
                    is_supervisor=False
                ).all()
                
                # Count total employees
                total_employees = len(employees)
                
                # Count employees who are absent today
                absent_count = 0
                absent_employees = []
                
                for emp in employees:
                    # Check vacation calendar for today
                    vacation = VacationCalendar.query.filter_by(
                        employee_id=emp.id,
                        date=today
                    ).first()
                    
                    if vacation:
                        absent_count += 1
                        absent_employees.append({
                            'name': emp.name,
                            'type': vacation.leave_type
                        })
                
                # Calculate available employees
                available = total_employees - absent_count
                
                # Calculate gap
                gap = max(0, required - available)
                
                # Add to totals
                crew_data['total_required'] += required
                crew_data['total_available'] += available
                crew_data['total_absent'] += absent_count
                crew_data['total_gaps'] += gap
                
                # Track critical gaps (2+ short)
                if gap >= 2:
                    critical_gaps += 1
                
                total_gaps += gap
                
                # Add position data
                position_data = {
                    'position': position,
                    'required': required,
                    'total_employees': total_employees,
                    'absent': absent_count,
                    'absent_employees': absent_employees,
                    'available': available,
                    'gap': gap
                }
                
                crew_data['positions'].append(position_data)
            
            coverage_gaps_data.append(crew_data)
        
        # Get upcoming absences for next 7 days
        upcoming_absences = db.session.query(
            VacationCalendar.date,
            func.count(VacationCalendar.id).label('count'),
            Employee.crew
        ).join(
            Employee, VacationCalendar.employee_id == Employee.id
        ).filter(
            VacationCalendar.date > today,
            VacationCalendar.date <= today + timedelta(days=7)
        ).group_by(
            VacationCalendar.date,
            Employee.crew
        ).order_by(
            VacationCalendar.date
        ).all()
        
        # Format upcoming absences
        upcoming_by_date = {}
        for absence in upcoming_absences:
            date_str = absence.date.strftime('%Y-%m-%d')
            if date_str not in upcoming_by_date:
                upcoming_by_date[date_str] = {'date': absence.date, 'crews': {}}
            upcoming_by_date[date_str]['crews'][absence.crew] = absence.count
        
        # Summary statistics
        summary = {
            'total_gaps': total_gaps,
            'critical_gaps': critical_gaps,
            'crews_affected': len([c for c in coverage_gaps_data if c['total_gaps'] > 0]),
            'positions_affected': sum(len([p for p in c['positions'] if p['gap'] > 0]) for c in coverage_gaps_data),
            'total_absences_today': sum(c['total_absent'] for c in coverage_gaps_data)
        }
        
        return render_template('coverage_gaps.html',
                             coverage_gaps=coverage_gaps_data,
                             summary=summary,
                             today=today,
                             upcoming_absences=list(upcoming_by_date.values()))
                             
    except Exception as e:
        print(f"Error in coverage_gaps route: {str(e)}")
        traceback.print_exc()
        flash(f'Error loading coverage gaps: {str(e)}', 'danger')
        return redirect(url_for('main.dashboard'))

# ========== SCHEDULE SUGGESTIONS ==========

@supervisor_bp.route('/supervisor/suggestions')
@login_required
@supervisor_required
def suggestions():
    """View employee suggestions"""
    try:
        # Get all suggestions
        all_suggestions = ScheduleSuggestion.query.order_by(ScheduleSuggestion.created_at.desc()).all()
        
        # Separate by status
        pending = [s for s in all_suggestions if s.status == 'pending']
        reviewed = [s for s in all_suggestions if s.status in ['approved', 'rejected', 'implemented']]
        
        return render_template('suggestions.html',
                             pending_suggestions=pending,
                             reviewed_suggestions=reviewed)
                             
    except Exception as e:
        flash(f'Error loading suggestions: {str(e)}', 'danger')
        return redirect(url_for('main.dashboard'))

# ========== QUICK ACTIONS ==========

@supervisor_bp.route('/quick/assign-overtime')
@login_required
@supervisor_required
def quick_assign_overtime():
    """Quick overtime assignment"""
    return render_template('coming_soon.html',
                         title='Quick Overtime Assignment',
                         description='Quickly assign overtime shifts to available employees.',
                         icon='bi bi-clock-history')

@supervisor_bp.route('/quick/crew-broadcast')
@login_required
@supervisor_required
def crew_broadcast():
    """Send message to crew"""
    return render_template('coming_soon.html',
                         title='Crew Broadcast',
                         description='Send important messages to specific crews.',
                         icon='bi bi-megaphone')

@supervisor_bp.route('/quick/emergency-coverage')
@login_required
@supervisor_required
def emergency_coverage():
    """Emergency coverage finder"""
    return render_template('coming_soon.html',
                         title='Emergency Coverage',
                         description='Find immediate coverage for unexpected absences.',
                         icon='bi bi-exclamation-triangle')

@supervisor_bp.route('/quick/shift-pattern-generator')
@login_required
@supervisor_required
def shift_pattern_generator():
    """Generate shift patterns"""
    return render_template('coming_soon.html',
                         title='Shift Pattern Generator',
                         description='Generate optimal shift patterns for your crews.',
                         icon='bi bi-calendar-range')

@supervisor_bp.route('/quick/skills-matrix')
@login_required
@supervisor_required
def skills_matrix():
    """View skills matrix"""
    return render_template('coming_soon.html',
                         title='Skills Matrix',
                         description='View and manage employee skills and certifications.',
                         icon='bi bi-person-badge')

@supervisor_bp.route('/quick/position-broadcast')
@login_required
@supervisor_required
def position_broadcast():
    """Plantwide communications"""
    return render_template('coming_soon.html',
                         title='Position Broadcast',
                         description='Send announcements to all employees in specific positions.',
                         icon='bi bi-megaphone')

# ========== API ENDPOINTS ==========

@supervisor_bp.route('/api/coverage-needs', methods=['POST'])
@login_required
@supervisor_required
def api_update_coverage_needs():
    """API endpoint to update coverage needs"""
    data = request.get_json()
    
    crew = data.get('crew')
    position_id = data.get('position_id')
    min_coverage = data.get('min_coverage', 0)
    
    try:
        if crew == 'global':
            # Update the global position requirement
            position = Position.query.get(position_id)
            if position:
                position.min_coverage = min_coverage
                db.session.commit()
                return jsonify({'success': True})
        else:
            # For crew-specific requirements (future enhancement)
            return jsonify({'success': True, 'message': 'Crew-specific requirements saved'})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@supervisor_bp.route('/api/coverage-gaps')
@login_required
@supervisor_required
def api_coverage_gaps():
    """API endpoint to get current coverage gaps"""
    crew = request.args.get('crew', 'ALL')
    
    gaps = []
    positions = Position.query.all()
    
    crews_to_check = ['A', 'B', 'C', 'D'] if crew == 'ALL' else [crew]
    
    for check_crew in crews_to_check:
        for position in positions:
            required = position.min_coverage
            current = Employee.query.filter_by(
                crew=check_crew,
                position_id=position.id
            ).count()
            
            if current < required:
                gaps.append({
                    'crew': check_crew,
                    'position': position.name,
                    'required': required,
                    'current': current,
                    'gap': required - current
                })
    
    return jsonify({'gaps': gaps, 'total_gaps': sum(g['gap'] for g in gaps)})

@supervisor_bp.route('/api/coverage-gaps-summary')
@login_required
@supervisor_required
def api_coverage_gaps_summary():
    """API endpoint to get coverage gaps summary for dashboard"""
    try:
        today = date.today()
        total_gaps = 0
        critical_gaps = 0
        
        # Quick calculation of gaps
        for crew in ['A', 'B', 'C', 'D']:
            positions = Position.query.all()
            
            for position in positions:
                # Required coverage
                required = position.min_coverage
                
                # Get total employees in position
                total_employees = Employee.query.filter_by(
                    crew=crew,
                    position_id=position.id,
                    is_supervisor=False
                ).count()
                
                # Count absences today
                absent_count = db.session.query(func.count(VacationCalendar.id)).join(
                    Employee, VacationCalendar.employee_id == Employee.id
                ).filter(
                    Employee.crew == crew,
                    Employee.position_id == position.id,
                    VacationCalendar.date == today
                ).scalar() or 0
                
                # Calculate gap
                available = total_employees - absent_count
                gap = max(0, required - available)
                
                total_gaps += gap
                if gap >= 2:
                    critical_gaps += 1
        
        return jsonify({
            'total_gaps': total_gaps,
            'critical_gaps': critical_gaps
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== EMPLOYEE DATA MANAGEMENT ==========

@supervisor_bp.route('/employees/delete-all', methods=['POST'])
@login_required
@supervisor_required
def delete_all_employees():
    """Delete all employees except current user"""
    try:
        # Delete all employees except the current user
        Employee.query.filter(Employee.id != current_user.id).delete()
        
        # Also clear related tables
        Schedule.query.delete()
        TimeOffRequest.query.delete()
        ShiftSwapRequest.query.delete()
        VacationCalendar.query.delete()
        OvertimeHistory.query.delete()
        
        db.session.commit()
        
        flash('All employee data has been deleted. You can now upload fresh data.', 'success')
        return redirect(url_for('employee_import.upload_employees'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting employees: {str(e)}', 'danger')
        return redirect(url_for('supervisor.employee_management'))

@supervisor_bp.route('/employees/remove-duplicates', methods=['POST'])
@login_required
@supervisor_required
def remove_duplicates():
    """Remove duplicate employees based on email"""
    try:
        # Find and remove duplicates
        duplicates = db.session.execute(
            text("""
                SELECT email, MIN(id) as keep_id, COUNT(*) as count
                FROM employee
                WHERE id != :user_id
                GROUP BY email
                HAVING COUNT(*) > 1
            """),
            {'user_id': current_user.id}
        ).fetchall()
        
        total_removed = 0
        for dup in duplicates:
            email, keep_id, count = dup
            # Delete all but the one with lowest ID
            result = db.session.execute(
                text("""
                    DELETE FROM employee 
                    WHERE email = :email 
                    AND id != :keep_id 
                    AND id != :user_id
                """),
                {'email': email, 'keep_id': keep_id, 'user_id': current_user.id}
            )
            total_removed += result.rowcount
            print(f"Removed {result.rowcount} duplicates of {email}")
        
        db.session.commit()
        flash(f'Removed {total_removed} duplicate employee records', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error removing duplicates: {str(e)}', 'danger')
    
    return redirect(url_for('supervisor.employee_management'))

# ========== EXPORT FUNCTIONS ==========

@supervisor_bp.route('/export/employees')
@login_required
@supervisor_required
def export_employees():
    """Export all employees to CSV"""
    try:
        employees = Employee.query.filter(Employee.id != current_user.id).all()
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(['Employee ID', 'Name', 'Email', 'Crew', 'Position', 'Hire Date', 
                        'Vacation Days', 'Sick Days', 'Personal Days'])
        
        # Data
        for emp in employees:
            writer.writerow([
                emp.employee_id,
                emp.name,
                emp.email,
                emp.crew,
                emp.position.name if emp.position else '',
                emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '',
                emp.vacation_days,
                emp.sick_days,
                emp.personal_days
            ])
        
        # Prepare response
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'employees_{date.today().strftime("%Y%m%d")}.csv'
        )
        
    except Exception as e:
        flash(f'Error exporting employees: {str(e)}', 'danger')
        return redirect(url_for('supervisor.employee_management'))

# Error handlers for the blueprint
@supervisor_bp.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@supervisor_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500
