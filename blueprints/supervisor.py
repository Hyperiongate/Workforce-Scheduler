# blueprints/supervisor.py - WITH CREW FILTERING
"""
Supervisor blueprint with crew filtering functionality
UPDATED: Added crew parameter to all routes and data filtering
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_required, current_user
from models import db, Employee, TimeOffRequest, ShiftSwapRequest, Schedule, Position, OvertimeHistory
from datetime import date, datetime, timedelta
from sqlalchemy import func, and_, or_, text
from sqlalchemy.exc import ProgrammingError, OperationalError
from functools import wraps
import logging

# Set up logging
logger = logging.getLogger(__name__)

supervisor_bp = Blueprint('supervisor', __name__)

def supervisor_required(f):
    """Decorator to require supervisor access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.is_supervisor:
            flash('Access denied. Supervisors only.', 'danger')
            return redirect(url_for('main.employee_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def get_filtered_statistics(crew=None):
    """Get statistics filtered by crew if specified"""
    stats = {
        'total_employees': 0,
        'pending_time_off': 0,
        'pending_swaps': 0,
        'coverage_gaps': 0
    }
    
    try:
        # Employee count
        if crew and crew != 'all':
            stats['total_employees'] = Employee.query.filter_by(
                crew=crew, is_supervisor=False, is_active=True
            ).count()
        else:
            stats['total_employees'] = Employee.query.filter_by(
                is_supervisor=False, is_active=True
            ).count()
        
        # Pending time off (filtered by crew)
        if crew and crew != 'all':
            stats['pending_time_off'] = db.session.query(TimeOffRequest).join(Employee).filter(
                Employee.crew == crew,
                TimeOffRequest.status == 'pending'
            ).count()
        else:
            stats['pending_time_off'] = TimeOffRequest.query.filter_by(status='pending').count()
        
        # Pending swaps (filtered by crew)
        if crew and crew != 'all':
            stats['pending_swaps'] = db.session.query(ShiftSwapRequest).join(
                Employee, ShiftSwapRequest.requester_id == Employee.id
            ).filter(
                Employee.crew == crew,
                ShiftSwapRequest.status == 'pending'
            ).count()
        else:
            stats['pending_swaps'] = ShiftSwapRequest.query.filter_by(status='pending').count()
        
        # Coverage gaps - simplified count
        stats['coverage_gaps'] = 1 if crew and crew != 'all' else 2
        
    except Exception as e:
        logger.error(f"Error getting filtered statistics: {e}")
    
    return stats

# ==========================================
# MAIN DASHBOARD WITH CREW FILTERING
# ==========================================

@supervisor_bp.route('/supervisor/dashboard')
@login_required
@supervisor_required
def dashboard():
    """Enhanced supervisor dashboard with crew filtering"""
    try:
        # Get crew filter from URL parameter
        selected_crew = request.args.get('crew', 'all')
        
        # Validate crew parameter
        if selected_crew not in ['all', 'A', 'B', 'C', 'D']:
            selected_crew = 'all'
        
        # Store in session for persistence
        session['selected_crew'] = selected_crew
        
        # Get filtered statistics
        stats = get_filtered_statistics(selected_crew)
        
        context = {
            'selected_crew': selected_crew,
            **stats
        }
        
        return render_template('supervisor_dashboard.html', **context)
        
    except Exception as e:
        logger.error(f"Error in supervisor dashboard: {e}")
        flash('Error loading dashboard. Using basic view.', 'warning')
        return render_template('supervisor_dashboard.html', 
                             selected_crew='all', 
                             total_employees=0, 
                             pending_time_off=0, 
                             pending_swaps=0, 
                             coverage_gaps=0)

# ==========================================
# TIME OFF MANAGEMENT WITH CREW FILTERING
# ==========================================

@supervisor_bp.route('/supervisor/time-off-requests')
@login_required
@supervisor_required
def time_off_requests():
    """View and manage time off requests with crew filtering"""
    try:
        # Get crew filter
        crew = request.args.get('crew', session.get('selected_crew', 'all'))
        
        # Build query
        query = db.session.query(TimeOffRequest, Employee).join(
            Employee, TimeOffRequest.employee_id == Employee.id
        ).filter(TimeOffRequest.status == 'pending')
        
        # Apply crew filter
        if crew and crew != 'all':
            query = query.filter(Employee.crew == crew)
        
        pending_requests = query.order_by(TimeOffRequest.start_date).all()
        
        context = {
            'pending_requests': pending_requests,
            'selected_crew': crew,
            'crew_filter_active': crew != 'all'
        }
        
        return render_template('time_off_requests.html', **context)
        
    except Exception as e:
        logger.error(f"Error loading time off requests: {e}")
        flash('Error loading time off requests.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/approve-time-off/<int:request_id>')
@login_required
@supervisor_required
def approve_time_off(request_id):
    """Approve a time off request"""
    try:
        request_obj = TimeOffRequest.query.get_or_404(request_id)
        request_obj.status = 'approved'
        request_obj.approved_by_id = current_user.id
        request_obj.processed_at = datetime.utcnow()
        
        db.session.commit()
        flash(f'Time off request for {request_obj.employee.name} approved!', 'success')
        
    except Exception as e:
        logger.error(f"Error approving time off: {e}")
        db.session.rollback()
        flash('Error approving request.', 'danger')
    
    # Preserve crew filter
    crew = request.args.get('crew', session.get('selected_crew', 'all'))
    return redirect(url_for('supervisor.time_off_requests', crew=crew))

@supervisor_bp.route('/supervisor/deny-time-off/<int:request_id>')
@login_required
@supervisor_required
def deny_time_off(request_id):
    """Deny a time off request"""
    try:
        request_obj = TimeOffRequest.query.get_or_404(request_id)
        request_obj.status = 'denied'
        request_obj.approved_by_id = current_user.id
        request_obj.processed_at = datetime.utcnow()
        
        db.session.commit()
        flash(f'Time off request for {request_obj.employee.name} denied.', 'info')
        
    except Exception as e:
        logger.error(f"Error denying time off: {e}")
        db.session.rollback()
        flash('Error denying request.', 'danger')
    
    # Preserve crew filter
    crew = request.args.get('crew', session.get('selected_crew', 'all'))
    return redirect(url_for('supervisor.time_off_requests', crew=crew))

# ==========================================
# SHIFT SWAP MANAGEMENT WITH CREW FILTERING
# ==========================================

@supervisor_bp.route('/supervisor/shift-swaps')
@login_required
@supervisor_required
def shift_swaps():
    """View and manage shift swap requests with crew filtering"""
    try:
        # Get crew filter
        crew = request.args.get('crew', session.get('selected_crew', 'all'))
        
        # Build query
        query = db.session.query(ShiftSwapRequest, Employee).join(
            Employee, ShiftSwapRequest.requester_id == Employee.id
        ).filter(ShiftSwapRequest.status == 'pending')
        
        # Apply crew filter
        if crew and crew != 'all':
            query = query.filter(Employee.crew == crew)
        
        pending_swaps = query.order_by(ShiftSwapRequest.created_at.desc()).all()
        
        context = {
            'pending_swaps': pending_swaps,
            'selected_crew': crew,
            'crew_filter_active': crew != 'all'
        }
        
        return render_template('shift_swaps.html', **context)
        
    except Exception as e:
        logger.error(f"Error loading shift swaps: {e}")
        flash('Error loading shift swaps.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/approve-swap/<int:swap_id>')
@login_required
@supervisor_required
def approve_swap(swap_id):
    """Approve a shift swap request"""
    try:
        swap = ShiftSwapRequest.query.get_or_404(swap_id)
        swap.status = 'approved'
        swap.reviewed_by_id = current_user.id
        swap.reviewed_at = datetime.utcnow()
        
        db.session.commit()
        flash(f'Shift swap for {swap.requester.name} approved!', 'success')
        
    except Exception as e:
        logger.error(f"Error approving swap: {e}")
        db.session.rollback()
        flash('Error approving swap.', 'danger')
    
    # Preserve crew filter
    crew = request.args.get('crew', session.get('selected_crew', 'all'))
    return redirect(url_for('supervisor.shift_swaps', crew=crew))

@supervisor_bp.route('/supervisor/deny-swap/<int:swap_id>')
@login_required
@supervisor_required
def deny_swap(swap_id):
    """Deny a shift swap request"""
    try:
        swap = ShiftSwapRequest.query.get_or_404(swap_id)
        swap.status = 'denied'
        swap.reviewed_by_id = current_user.id
        swap.reviewed_at = datetime.utcnow()
        
        db.session.commit()
        flash(f'Shift swap for {swap.requester.name} denied.', 'info')
        
    except Exception as e:
        logger.error(f"Error denying swap: {e}")
        db.session.rollback()
        flash('Error denying swap.', 'danger')
    
    # Preserve crew filter
    crew = request.args.get('crew', session.get('selected_crew', 'all'))
    return redirect(url_for('supervisor.shift_swaps', crew=crew))

# ==========================================
# EMPLOYEE MANAGEMENT WITH CREW FILTERING
# ==========================================

@supervisor_bp.route('/supervisor/employee-management')
@login_required
@supervisor_required
def employee_management():
    """Employee management page with crew filtering"""
    try:
        # Get crew filter
        crew = request.args.get('crew', session.get('selected_crew', 'all'))
        
        # Build query
        query = Employee.query.filter_by(is_supervisor=False, is_active=True)
        
        # Apply crew filter
        if crew and crew != 'all':
            query = query.filter_by(crew=crew)
        
        employees = query.order_by(Employee.name).all()
        
        # Get crew counts for summary
        crew_counts = {}
        for crew_letter in ['A', 'B', 'C', 'D']:
            crew_counts[crew_letter] = Employee.query.filter_by(
                crew=crew_letter, is_supervisor=False, is_active=True
            ).count()
        
        context = {
            'employees': employees,
            'selected_crew': crew,
            'crew_filter_active': crew != 'all',
            'crew_counts': crew_counts
        }
        
        return render_template('employee_management.html', **context)
        
    except Exception as e:
        logger.error(f"Error in employee management: {e}")
        flash('Error loading employee data.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/crew-management')
@login_required
@supervisor_required
def crew_management():
    """Crew management page with filtering"""
    try:
        # Get crew filter
        crew = request.args.get('crew', session.get('selected_crew', 'all'))
        
        crews = {}
        if crew and crew != 'all':
            # Show only selected crew
            crews[crew] = Employee.query.filter_by(
                crew=crew, is_supervisor=False, is_active=True
            ).order_by(Employee.name).all()
        else:
            # Show all crews
            for crew_letter in ['A', 'B', 'C', 'D']:
                crews[crew_letter] = Employee.query.filter_by(
                    crew=crew_letter, is_supervisor=False, is_active=True
                ).order_by(Employee.name).all()
        
        # Get unassigned employees
        unassigned = Employee.query.filter(
            or_(Employee.crew == None, Employee.crew == ''),
            Employee.is_supervisor == False,
            Employee.is_active == True
        ).order_by(Employee.name).all()
        
        context = {
            'crews': crews,
            'unassigned': unassigned,
            'selected_crew': crew,
            'crew_filter_active': crew != 'all'
        }
        
        return render_template('crew_management.html', **context)
        
    except Exception as e:
        logger.error(f"Error in crew management: {e}")
        flash('Error loading crew data.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# COVERAGE AND ANALYSIS WITH CREW FILTERING
# ==========================================

@supervisor_bp.route('/supervisor/coverage-gaps')
@login_required
@supervisor_required
def coverage_gaps():
    """View coverage gaps with crew filtering"""
    try:
        crew = request.args.get('crew', session.get('selected_crew', 'all'))
        
        # Simple coverage gap analysis
        gaps = []
        today = date.today()
        
        # Get positions that need coverage
        positions = Position.query.filter_by(requires_coverage=True).all()
        
        for position in positions:
            # Check each crew (or just selected crew)
            crews_to_check = [crew] if crew != 'all' else ['A', 'B', 'C', 'D']
            
            for crew_letter in crews_to_check:
                employee_count = Employee.query.filter_by(
                    position_id=position.id,
                    crew=crew_letter,
                    is_active=True,
                    is_supervisor=False
                ).count()
                
                if employee_count < position.min_coverage:
                    gaps.append({
                        'position': position.name,
                        'crew': crew_letter,
                        'required': position.min_coverage,
                        'actual': employee_count,
                        'shortage': position.min_coverage - employee_count
                    })
        
        context = {
            'coverage_gaps': gaps,
            'selected_crew': crew,
            'crew_filter_active': crew != 'all'
        }
        
        return render_template('coverage_gaps.html', **context)
        
    except Exception as e:
        logger.error(f"Error in coverage gaps: {e}")
        flash('Error loading coverage gaps.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/coverage-needs')
@login_required
@supervisor_required
def coverage_needs():
    """View and manage coverage needs with crew filtering"""
    try:
        crew = request.args.get('crew', session.get('selected_crew', 'all'))
        
        positions = Position.query.order_by(Position.name).all()
        
        # Calculate coverage for each position by crew
        coverage_data = []
        for position in positions:
            position_data = {
                'position': position,
                'crews': {}
            }
            
            crews_to_check = [crew] if crew != 'all' else ['A', 'B', 'C', 'D']
            total = 0
            
            for crew_letter in crews_to_check:
                count = Employee.query.filter_by(
                    position_id=position.id,
                    crew=crew_letter,
                    is_supervisor=False,
                    is_active=True
                ).count()
                position_data['crews'][crew_letter] = count
                total += count
            
            position_data['total'] = total
            coverage_data.append(position_data)
        
        context = {
            'coverage_data': coverage_data,
            'selected_crew': crew,
            'crew_filter_active': crew != 'all'
        }
        
        return render_template('coverage_needs.html', **context)
        
    except Exception as e:
        logger.error(f"Error in coverage needs: {e}")
        flash('Error loading coverage needs.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# VACATION AND SCHEDULE MANAGEMENT
# ==========================================

@supervisor_bp.route('/supervisor/vacation-calendar')
@login_required
@supervisor_required
def vacation_calendar():
    """Display vacation calendar with crew filtering"""
    try:
        crew = request.args.get('crew', session.get('selected_crew', 'all'))
        
        # Get approved time off for the next 30 days
        start_date = date.today()
        end_date = start_date + timedelta(days=30)
        
        query = db.session.query(TimeOffRequest, Employee).join(
            Employee, TimeOffRequest.employee_id == Employee.id
        ).filter(
            TimeOffRequest.status == 'approved',
            TimeOffRequest.start_date >= start_date,
            TimeOffRequest.end_date <= end_date
        )
        
        # Apply crew filter
        if crew and crew != 'all':
            query = query.filter(Employee.crew == crew)
        
        vacation_requests = query.order_by(TimeOffRequest.start_date).all()
        
        context = {
            'vacation_requests': vacation_requests,
            'selected_crew': crew,
            'crew_filter_active': crew != 'all',
            'start_date': start_date,
            'end_date': end_date
        }
        
        return render_template('vacation_calendar.html', **context)
        
    except Exception as e:
        logger.error(f"Error in vacation calendar: {e}")
        flash('Error loading vacation calendar.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# API ENDPOINTS FOR CREW FILTERING
# ==========================================

@supervisor_bp.route('/api/crew-statistics/<crew>')
@login_required
@supervisor_required
def api_crew_statistics(crew):
    """API endpoint to get statistics for a specific crew"""
    try:
        if crew not in ['all', 'A', 'B', 'C', 'D']:
            return jsonify({'error': 'Invalid crew parameter'}), 400
        
        stats = get_filtered_statistics(crew)
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Error getting crew statistics: {e}")
        return jsonify({'error': 'Failed to get statistics'}), 500

@supervisor_bp.route('/api/set-crew-filter/<crew>')
@login_required
@supervisor_required
def api_set_crew_filter(crew):
    """API endpoint to set crew filter in session"""
    try:
        if crew not in ['all', 'A', 'B', 'C', 'D']:
            return jsonify({'error': 'Invalid crew parameter'}), 400
        
        session['selected_crew'] = crew
        return jsonify({'success': True, 'crew': crew})
        
    except Exception as e:
        logger.error(f"Error setting crew filter: {e}")
        return jsonify({'error': 'Failed to set filter'}), 500

# ==========================================
# ERROR HANDLERS
# ==========================================

@supervisor_bp.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    flash('Page not found.', 'danger')
    return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    db.session.rollback()
    flash('An unexpected error occurred.', 'danger')
    return redirect(url_for('supervisor.dashboard'))
