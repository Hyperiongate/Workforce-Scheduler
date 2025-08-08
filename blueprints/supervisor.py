# blueprints/supervisor.py - COMPLETE FIXED FILE
"""
Supervisor blueprint with robust error handling
Provides all required template variables and handles errors gracefully
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, Employee, TimeOffRequest, ShiftSwapRequest, Schedule, Position, OvertimeHistory
from datetime import date, datetime, timedelta
from sqlalchemy import func, and_, or_
from functools import wraps
import traceback

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

@supervisor_bp.route('/supervisor/dashboard')
@login_required
@supervisor_required
def dashboard():
    """Supervisor dashboard with complete error handling and all required variables"""
    try:
        # Initialize ALL variables that the template expects
        context = {
            # Basic counts
            'pending_time_off': 0,
            'pending_time_off_count': 0,  # Duplicate for template compatibility
            'pending_swaps': 0,
            'total_employees': 0,
            'coverage_gaps': 0,
            
            # Additional stats that may be used
            'pending_suggestions': 0,
            'recent_activities': [],
            'coverage_warnings': 0,
            'overtime_alerts': 0,
            'employees_on_leave_today': 0,
            'shifts_needing_coverage': 0,
            
            # User info
            'current_user': current_user,
            'today': date.today(),
            'now': datetime.now()
        }
        
        # Get pending time off requests
        try:
            pending_count = TimeOffRequest.query.filter_by(status='pending').count()
            context['pending_time_off'] = pending_count
            context['pending_time_off_count'] = pending_count  # Both variables for compatibility
        except Exception as e:
            current_app.logger.error(f"Error getting pending time off: {e}")
        
        # Get pending swap requests
        try:
            context['pending_swaps'] = ShiftSwapRequest.query.filter_by(status='pending').count()
        except Exception as e:
            current_app.logger.error(f"Error getting pending swaps: {e}")
        
        # Get total employees
        try:
            context['total_employees'] = Employee.query.filter_by(is_supervisor=False).count()
        except Exception as e:
            current_app.logger.error(f"Error getting total employees: {e}")
        
        # Calculate coverage gaps
        try:
            # Import helper safely
            try:
                from utils.helpers import get_coverage_gaps
                all_gaps = get_coverage_gaps()
                context['coverage_gaps'] = len([g for g in all_gaps if g['date'] == date.today()])
            except ImportError:
                # If helper doesn't exist, calculate inline
                today = date.today()
                scheduled_today = Schedule.query.filter_by(date=today).count()
                required_today = db.session.query(func.sum(Position.min_coverage)).scalar() or 0
                context['coverage_gaps'] = max(0, required_today - scheduled_today)
        except Exception as e:
            current_app.logger.error(f"Error calculating coverage gaps: {e}")
            context['coverage_gaps'] = 0
        
        # Get employees on leave today
        try:
            today = date.today()
            context['employees_on_leave_today'] = TimeOffRequest.query.filter(
                TimeOffRequest.status == 'approved',
                TimeOffRequest.start_date <= today,
                TimeOffRequest.end_date >= today
            ).count()
        except Exception as e:
            current_app.logger.error(f"Error getting employees on leave: {e}")
        
        # Get recent activities for dashboard
        try:
            recent_time_off = TimeOffRequest.query.order_by(
                TimeOffRequest.created_at.desc()
            ).limit(5).all()
            
            recent_swaps = ShiftSwapRequest.query.order_by(
                ShiftSwapRequest.created_at.desc()
            ).limit(5).all()
            
            # Combine and sort by date
            activities = []
            for req in recent_time_off:
                activities.append({
                    'type': 'time_off',
                    'description': f"{req.employee.name} requested time off",
                    'date': req.created_at,
                    'status': req.status
                })
            
            for swap in recent_swaps:
                activities.append({
                    'type': 'swap',
                    'description': f"Shift swap request",
                    'date': swap.created_at,
                    'status': swap.status
                })
            
            # Sort by date and take top 10
            context['recent_activities'] = sorted(
                activities, 
                key=lambda x: x['date'], 
                reverse=True
            )[:10]
        except Exception as e:
            current_app.logger.error(f"Error getting recent activities: {e}")
            context['recent_activities'] = []
        
        return render_template('dashboard.html', **context)
        
    except Exception as e:
        current_app.logger.error(f"Critical dashboard error: {e}")
        current_app.logger.error(traceback.format_exc())
        flash('Error loading dashboard. Showing limited view.', 'warning')
        
        # Return with absolute minimum required variables
        return render_template('dashboard.html',
            pending_time_off=0,
            pending_time_off_count=0,
            pending_swaps=0,
            total_employees=0,
            coverage_gaps=0,
            current_user=current_user
        )

@supervisor_bp.route('/supervisor/time-off-requests')
@login_required
@supervisor_required
def time_off_requests():
    """View and manage time off requests"""
    try:
        # Get filter parameters
        status_filter = request.args.get('status', 'all')
        crew_filter = request.args.get('crew', 'all')
        date_filter = request.args.get('date', 'all')
        
        # Build query
        query = TimeOffRequest.query
        
        if status_filter != 'all':
            query = query.filter_by(status=status_filter)
        
        if crew_filter != 'all':
            query = query.join(Employee).filter(Employee.crew == crew_filter)
        
        if date_filter == 'today':
            today = date.today()
            query = query.filter(
                TimeOffRequest.start_date <= today,
                TimeOffRequest.end_date >= today
            )
        elif date_filter == 'week':
            week_start = date.today() - timedelta(days=date.today().weekday())
            week_end = week_start + timedelta(days=6)
            query = query.filter(
                TimeOffRequest.start_date <= week_end,
                TimeOffRequest.end_date >= week_start
            )
        
        # Get requests
        requests = query.order_by(TimeOffRequest.created_at.desc()).all()
        
        # Get statistics
        stats = {
            'pending_count': TimeOffRequest.query.filter_by(status='pending').count(),
            'approved_this_week': TimeOffRequest.query.filter(
                TimeOffRequest.status == 'approved',
                TimeOffRequest.created_at >= datetime.now() - timedelta(days=7)
            ).count(),
            'coverage_warnings': 0
        }
        
        return render_template('time_off_requests.html',
                             requests=requests,
                             stats=stats,
                             status_filter=status_filter,
                             crew_filter=crew_filter,
                             date_filter=date_filter)
    
    except Exception as e:
        current_app.logger.error(f"Error in time_off_requests: {e}")
        flash('Error loading time off requests.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/shift-swaps')
@login_required
@supervisor_required
def shift_swaps():
    """View and manage shift swap requests"""
    try:
        swaps = ShiftSwapRequest.query.order_by(
            ShiftSwapRequest.created_at.desc()
        ).all()
        
        stats = {
            'pending_count': ShiftSwapRequest.query.filter_by(status='pending').count(),
            'approved_this_week': ShiftSwapRequest.query.filter(
                ShiftSwapRequest.status == 'approved',
                ShiftSwapRequest.created_at >= datetime.now() - timedelta(days=7)
            ).count()
        }
        
        return render_template('shift_swaps.html', swaps=swaps, stats=stats)
    
    except Exception as e:
        current_app.logger.error(f"Error in shift_swaps: {e}")
        flash('Error loading shift swap requests.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/api/dashboard-stats')
@login_required
@supervisor_required
def api_dashboard_stats():
    """API endpoint for real-time dashboard statistics"""
    try:
        stats = {
            'pending_time_off': TimeOffRequest.query.filter_by(status='pending').count(),
            'pending_swaps': ShiftSwapRequest.query.filter_by(status='pending').count(),
            'coverage_gaps': 0,
            'total_employees': Employee.query.filter_by(is_supervisor=False).count(),
            'employees_on_leave': 0,
            'last_updated': datetime.now().strftime('%H:%M:%S')
        }
        
        # Calculate coverage gaps
        try:
            today = date.today()
            scheduled = Schedule.query.filter_by(date=today).count()
            required = db.session.query(func.sum(Position.min_coverage)).scalar() or 0
            stats['coverage_gaps'] = max(0, required - scheduled)
        except:
            pass
        
        # Count employees on leave today
        try:
            today = date.today()
            stats['employees_on_leave'] = TimeOffRequest.query.filter(
                TimeOffRequest.status == 'approved',
                TimeOffRequest.start_date <= today,
                TimeOffRequest.end_date >= today
            ).count()
        except:
            pass
        
        return jsonify(stats)
    
    except Exception as e:
        current_app.logger.error(f"Error in api_dashboard_stats: {e}")
        return jsonify({'error': 'Failed to load statistics'}), 500
