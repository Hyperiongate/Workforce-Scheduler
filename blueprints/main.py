# blueprints/main.py - COMPLETE FILE WITH ALL ROUTES
"""
Main blueprint with all required routes for the dashboard
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, Employee, Schedule, TimeOffRequest, ShiftSwapRequest, Position, OvertimeHistory
from datetime import date, datetime, timedelta
from sqlalchemy import func, or_, and_
import traceback

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Landing page - redirect based on authentication status"""
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    return redirect(url_for('auth.login'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Generic dashboard route - redirects to appropriate dashboard"""
    if current_user.is_supervisor:
        return redirect(url_for('supervisor.dashboard'))
    else:
        return redirect(url_for('main.employee_dashboard'))

@main_bp.route('/employee-dashboard')
@login_required
def employee_dashboard():
    """Employee dashboard with error handling"""
    try:
        # Initialize context with defaults
        context = {
            'current_user': current_user,
            'today': date.today(),
            'my_schedule': [],
            'my_time_off': [],
            'my_swaps': [],
            'overtime_opportunities': [],
            'current_week_overtime': 0,
            'vacation_balance': 0,
            'sick_balance': 0,
            'personal_balance': 0,
            'week_start': None,
            'week_end': None
        }
        
        # Get current week dates
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        context['week_start'] = week_start
        context['week_end'] = week_end
        context['today'] = today
        
        # Get employee's schedule
        try:
            context['my_schedule'] = Schedule.query.filter(
                Schedule.employee_id == current_user.id,
                Schedule.date >= week_start,
                Schedule.date <= week_end
            ).order_by(Schedule.date).all()
        except Exception as e:
            current_app.logger.error(f"Error loading schedule: {e}")
            db.session.rollback()
        
        # Get time-off requests
        try:
            context['my_time_off'] = TimeOffRequest.query.filter_by(
                employee_id=current_user.id
            ).order_by(TimeOffRequest.created_at.desc()).limit(5).all()
        except Exception as e:
            current_app.logger.error(f"Error loading time off requests: {e}")
            db.session.rollback()
        
        # Get shift swaps
        try:
            context['my_swaps'] = ShiftSwapRequest.query.filter(
                or_(
                    ShiftSwapRequest.requester_employee_id == current_user.id,
                    ShiftSwapRequest.target_employee_id == current_user.id
                )
            ).order_by(ShiftSwapRequest.created_at.desc()).limit(5).all()
        except Exception as e:
            current_app.logger.error(f"Error loading shift swaps: {e}")
            db.session.rollback()
        
        # Get overtime hours for current week
        try:
            context['current_week_overtime'] = db.session.query(
                func.sum(OvertimeHistory.overtime_hours)
            ).filter(
                OvertimeHistory.employee_id == current_user.id,
                OvertimeHistory.week_start_date == week_start
            ).scalar() or 0
        except Exception as e:
            current_app.logger.error(f"Error loading overtime: {e}")
            db.session.rollback()
        
        # Get leave balances
        try:
            context['vacation_balance'] = getattr(current_user, 'vacation_days', 0)
            context['sick_balance'] = getattr(current_user, 'sick_days', 0)
            context['personal_balance'] = getattr(current_user, 'personal_days', 0)
        except Exception as e:
            current_app.logger.error(f"Error loading leave balances: {e}")
        
        return render_template('employee_dashboard.html', **context)
        
    except Exception as e:
        current_app.logger.error(f"Critical error in employee dashboard: {e}")
        current_app.logger.error(traceback.format_exc())
        flash('Error loading dashboard. Please try again.', 'danger')
        
        # Return minimal dashboard
        return render_template('employee_dashboard.html',
            current_user=current_user,
            today=date.today(),
            my_schedule=[],
            my_time_off=[],
            my_swaps=[],
            overtime_opportunities=[],
            current_week_overtime=0,
            vacation_balance=0,
            sick_balance=0,
            personal_balance=0
        )

@main_bp.route('/overtime-management')
@login_required
def overtime_management():
    """Overtime management page"""
    if not current_user.is_supervisor:
        flash('Supervisor access required.', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    try:
        db.session.rollback()  # Clear any bad transactions
        
        employees = Employee.query.filter_by(is_supervisor=False).all()
        
        # Get overtime data with error handling
        overtime_data = []
        for emp in employees:
            try:
                recent_ot = OvertimeHistory.query.filter_by(
                    employee_id=emp.id
                ).order_by(OvertimeHistory.week_start_date.desc()).first()
                
                total_ot = db.session.query(
                    func.sum(OvertimeHistory.overtime_hours)
                ).filter_by(employee_id=emp.id).scalar() or 0
                
                overtime_data.append({
                    'employee': emp,
                    'recent_overtime': recent_ot,
                    'total_overtime': total_ot
                })
            except:
                db.session.rollback()
                overtime_data.append({
                    'employee': emp,
                    'recent_overtime': None,
                    'total_overtime': 0
                })
        
        return render_template('overtime_management.html', 
                             overtime_data=overtime_data,
                             is_supervisor=True)
    except Exception as e:
        current_app.logger.error(f"Error in overtime management: {e}")
        flash('Error loading overtime data.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@main_bp.route('/vacation-calendar')
@login_required
def vacation_calendar():
    """Redirect to supervisor vacation calendar"""
    if not current_user.is_supervisor:
        flash('Supervisor access required.', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    return redirect(url_for('supervisor.vacation_calendar'))

@main_bp.route('/employees/management')
@login_required
def employee_management():
    """Redirect to supervisor employee management"""
    if not current_user.is_supervisor:
        flash('Supervisor access required.', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    return redirect(url_for('supervisor.employee_management'))

@main_bp.route('/employees/crew-management')
@login_required
def crew_management():
    """Redirect to supervisor crew management"""
    if not current_user.is_supervisor:
        flash('Supervisor access required.', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    return redirect(url_for('supervisor.crew_management'))

@main_bp.route('/profile')
@login_required
def profile():
    """User profile page"""
    return render_template('profile.html', user=current_user)

@main_bp.route('/api/employee-stats')
@login_required
def api_employee_stats():
    """API endpoint for employee statistics"""
    try:
        db.session.rollback()  # Clear any bad state
        
        stats = {
            'upcoming_shifts': 0,
            'pending_requests': 0,
            'overtime_hours': 0,
            'vacation_days': 0
        }
        
        # Count upcoming shifts
        try:
            stats['upcoming_shifts'] = Schedule.query.filter(
                Schedule.employee_id == current_user.id,
                Schedule.date >= date.today(),
                Schedule.date <= date.today() + timedelta(days=7)
            ).count()
        except:
            db.session.rollback()
        
        # Count pending requests
        try:
            stats['pending_requests'] = TimeOffRequest.query.filter_by(
                employee_id=current_user.id,
                status='pending'
            ).count()
        except:
            db.session.rollback()
        
        # Get overtime hours
        try:
            week_start = date.today() - timedelta(days=date.today().weekday())
            stats['overtime_hours'] = db.session.query(
                func.sum(OvertimeHistory.overtime_hours)
            ).filter(
                OvertimeHistory.employee_id == current_user.id,
                OvertimeHistory.week_start_date == week_start
            ).scalar() or 0
        except:
            db.session.rollback()
        
        # Get vacation balance
        try:
            stats['vacation_days'] = getattr(current_user, 'vacation_days', 0)
        except:
            pass
        
        return jsonify(stats)
        
    except Exception as e:
        current_app.logger.error(f"Error in api_employee_stats: {e}")
        return jsonify({'error': 'Failed to load statistics'}), 500

# Error handlers
@main_bp.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@main_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    current_app.logger.error(f"Internal error: {error}")
    return render_template('500.html'), 500
