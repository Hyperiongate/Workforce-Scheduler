# blueprints/main.py
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

@main_bp.route('/view-crews')
@login_required
def view_crews():
    """View all crews and their members"""
    try:
        # Get all employees grouped by crew
        crews = {
            'A': [],
            'B': [],
            'C': [],
            'D': [],
            'Unassigned': []
        }
        
        all_employees = Employee.query.order_by(Employee.crew, Employee.name).all()
        
        for employee in all_employees:
            crew_key = employee.crew if employee.crew in ['A', 'B', 'C', 'D'] else 'Unassigned'
            crews[crew_key].append(employee)
        
        # Get crew statistics
        crew_stats = {}
        crew_supervisors = {}
        
        for crew_name in ['A', 'B', 'C', 'D']:
            crew_employees = crews[crew_name]
            
            # Find supervisor for this crew
            supervisor = next((e for e in crew_employees if e.is_supervisor), None)
            crew_supervisors[crew_name] = supervisor
            
            # Calculate stats
            operators = len([e for e in crew_employees if e.position and 'Operator' in e.position.name])
            supervisors = len([e for e in crew_employees if e.is_supervisor])
            maintenance = len([e for e in crew_employees if e.position and e.position.department == 'Maintenance'])
            
            crew_stats[crew_name] = {
                'total': len(crew_employees),
                'operators': operators,
                'supervisors': supervisors,
                'maintenance': maintenance,
                'positions': len(set(e.position_id for e in crew_employees if e.position_id))
            }
        
        # Handle unassigned
        crew_stats['Unassigned'] = {
            'total': len(crews['Unassigned']),
            'operators': 0,
            'supervisors': 0,
            'maintenance': 0,
            'positions': 0
        }
        crew_supervisors['Unassigned'] = None
        
        return render_template('view_crews.html',
                             crews=crews,
                             crew_stats=crew_stats,
                             crew_supervisors=crew_supervisors)
                             
    except Exception as e:
        current_app.logger.error(f"Error in view_crews: {e}")
        flash('Error loading crew information.', 'danger')
        return redirect(url_for('main.dashboard'))

@main_bp.route('/diagnostic')
@login_required
def diagnostic():
    """System diagnostic page"""
    if not current_user.is_supervisor:
        flash('Supervisor access required.', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    try:
        # Get database statistics
        stats = {
            'employees': Employee.query.count(),
            'supervisors': Employee.query.filter_by(is_supervisor=True).count(),
            'schedules': Schedule.query.count(),
            'time_off_requests': TimeOffRequest.query.count(),
            'positions': Position.query.count(),
            'overtime_records': OvertimeHistory.query.count()
        }
        
        # Get crew distribution
        crew_dist = {}
        for crew in ['A', 'B', 'C', 'D', None]:
            count = Employee.query.filter_by(crew=crew).count()
            crew_dist[crew or 'Unassigned'] = count
        
        # Check for common issues
        issues = []
        
        # Check for employees without crews
        no_crew = Employee.query.filter(or_(Employee.crew == None, Employee.crew == '')).count()
        if no_crew > 0:
            issues.append(f"{no_crew} employees without crew assignment")
        
        # Check for employees without positions
        no_position = Employee.query.filter_by(position_id=None).count()
        if no_position > 0:
            issues.append(f"{no_position} employees without position assignment")
        
        # Check for missing OT data
        employees_with_ot = db.session.query(OvertimeHistory.employee_id).distinct().count()
        employees_without_ot = stats['employees'] - employees_with_ot
        if employees_without_ot > 0:
            issues.append(f"{employees_without_ot} employees without overtime history")
        
        return render_template('diagnostic.html',
                             stats=stats,
                             crew_dist=crew_dist,
                             issues=issues)
                             
    except Exception as e:
        current_app.logger.error(f"Error in diagnostic: {e}")
        flash('Error loading diagnostic information.', 'danger')
        return redirect(url_for('main.dashboard'))

@main_bp.route('/debug-routes')
@login_required
def debug_routes():
    """Show all registered routes"""
    if not current_user.is_supervisor:
        flash('Supervisor access required.', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    try:
        routes = []
        for rule in current_app.url_map.iter_rules():
            if rule.endpoint != 'static':
                routes.append({
                    'endpoint': rule.endpoint,
                    'url': str(rule),
                    'methods': ', '.join(rule.methods - {'HEAD', 'OPTIONS'})
                })
        
        routes.sort(key=lambda x: x['url'])
        
        return render_template('debug_routes.html', routes=routes)
        
    except Exception as e:
        current_app.logger.error(f"Error in debug_routes: {e}")
        return jsonify({'error': str(e)}), 500

# Redirect routes for backward compatibility
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
