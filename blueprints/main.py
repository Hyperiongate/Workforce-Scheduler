# blueprints/main.py - COMPLETE FILE
"""
Main blueprint for general routes and employee functionality
Fixed with complete overtime management implementation
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from models import db, Employee, TimeOffRequest, ShiftSwapRequest, Schedule, Position, OvertimeHistory
from functools import wraps
from datetime import date, timedelta
from sqlalchemy import or_
import logging
import traceback

# Set up logging
logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)

def supervisor_required(f):
    """Decorator to require supervisor access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.is_supervisor:
            flash('Access denied. Supervisors only.', 'warning')
            return redirect(url_for('main.employee_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Root route - handles the home page
@main_bp.route('/')
def index():
    """Landing page - redirect based on authentication"""
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    else:
        return redirect(url_for('auth.login'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - redirect based on role with error handling"""
    try:
        if current_user.is_supervisor:
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    except Exception as e:
        logger.error(f"Error in dashboard redirect: {e}")
        # Fallback to a simple dashboard
        return render_template('basic_dashboard.html', 
                             user_name=current_user.name,
                             pending_time_off=0,
                             pending_swaps=0,
                             total_employees=0)

@main_bp.route('/employee-dashboard')
@login_required
def employee_dashboard():
    """Employee dashboard view with error handling"""
    try:
        # Get pending requests with error handling
        pending_time_off = 0
        pending_swaps = 0
        
        try:
            pending_time_off = TimeOffRequest.query.filter_by(
                employee_id=current_user.id,
                status='pending'
            ).count()
        except Exception as e:
            logger.error(f"Error getting time off requests: {e}")
            db.session.rollback()
        
        try:
            pending_swaps = ShiftSwapRequest.query.filter_by(
                requester_id=current_user.id,
                status='pending'
            ).count()
        except Exception as e:
            logger.error(f"Error getting swap requests: {e}")
            db.session.rollback()
        
        return render_template('employee_dashboard.html',
                             pending_time_off=pending_time_off,
                             pending_swaps=pending_swaps)
    except Exception as e:
        logger.error(f"Error in employee dashboard: {e}")
        flash('Error loading dashboard. Please try again.', 'danger')
        return redirect(url_for('auth.login'))

@main_bp.route('/overtime-management')
@login_required
@supervisor_required
def overtime_management():
    """Enhanced overtime management page with all required data"""
    try:
        # Get filter parameters from request
        page = request.args.get('page', 1, type=int)
        per_page = 25
        search_term = request.args.get('search', '')
        crew_filter = request.args.get('crew', '')
        position_filter = request.args.get('position', '')
        ot_range_filter = request.args.get('ot_range', '')
        
        # Multi-level sorting parameters
        sort_params = []
        for i in range(1, 5):
            sort_field = request.args.get(f'sort{i}')
            sort_dir = request.args.get(f'dir{i}', 'asc')
            if sort_field:
                sort_params.append((sort_field, sort_dir))
        
        # Calculate date range for 13-week period
        end_date = date.today()
        start_date = end_date - timedelta(weeks=13)
        
        # Base query for employees
        query = Employee.query.filter_by(is_supervisor=False)
        
        # Apply search filter
        if search_term:
            query = query.filter(
                or_(
                    Employee.name.ilike(f'%{search_term}%'),
                    Employee.employee_id.ilike(f'%{search_term}%')
                )
            )
        
        # Apply crew filter
        if crew_filter:
            query = query.filter_by(crew=crew_filter)
        
        # Apply position filter
        if position_filter:
            query = query.filter_by(position_id=position_filter)
        
        # Get all employees for calculations
        all_employees = query.all()
        
        # Calculate overtime data for each employee
        employees_with_ot = []
        total_overtime_hours = 0
        employees_with_overtime = 0
        high_overtime_employees = []
        
        for employee in all_employees:
            # Get overtime history for this employee
            overtime_records = OvertimeHistory.query.filter_by(
                employee_id=employee.id
            ).filter(
                OvertimeHistory.week_ending >= start_date,
                OvertimeHistory.week_ending <= end_date
            ).all()
            
            # Calculate totals
            total_ot = sum(record.overtime_hours for record in overtime_records) if overtime_records else 0
            current_week_ot = 0
            
            # Get current week's overtime
            current_week_start = end_date - timedelta(days=end_date.weekday())
            current_week_record = next((r for r in overtime_records if r.week_ending >= current_week_start), None)
            if current_week_record:
                current_week_ot = current_week_record.overtime_hours
            
            # Apply OT range filter
            if ot_range_filter:
                if ot_range_filter == '0-50' and total_ot > 50:
                    continue
                elif ot_range_filter == '50-100' and (total_ot <= 50 or total_ot > 100):
                    continue
                elif ot_range_filter == '100-150' and (total_ot <= 100 or total_ot > 150):
                    continue
                elif ot_range_filter == '150+' and total_ot <= 150:
                    continue
            
            # Calculate trend (simplified)
            if len(overtime_records) >= 2:
                recent_avg = sum(r.overtime_hours for r in overtime_records[-4:]) / min(4, len(overtime_records[-4:]))
                older_avg = sum(r.overtime_hours for r in overtime_records[:-4]) / max(1, len(overtime_records[:-4]))
                
                if recent_avg > older_avg * 1.2:
                    trend = 'increasing'
                elif recent_avg < older_avg * 0.8:
                    trend = 'decreasing'
                else:
                    trend = 'stable'
            else:
                trend = 'stable'
            
            # Calculate years employed
            years_employed = 0
            if employee.hire_date:
                years_employed = (date.today() - employee.hire_date).days // 365
            
            # Add employee data
            employee_data = {
                'id': employee.id,
                'employee_id': employee.employee_id,
                'name': employee.name,
                'crew': employee.crew,
                'position': employee.position,
                'position_id': employee.position_id,
                'hire_date': employee.hire_date,
                'years_employed': years_employed,
                'last_13_weeks_overtime': total_ot,
                'current_week_overtime': current_week_ot,
                'average_weekly_overtime': round(total_ot / 13, 1) if total_ot > 0 else 0,
                'overtime_trend': trend
            }
            
            employees_with_ot.append(employee_data)
            
            # Update statistics
            if total_ot > 0:
                employees_with_overtime += 1
                total_overtime_hours += total_ot
                
                # Check for high overtime (15+ hours average per week)
                if total_ot / 13 >= 15:
                    high_overtime_employees.append(employee_data)
        
        # Apply multi-level sorting
        if sort_params:
            def sort_key(emp):
                key_values = []
                for field, direction in sort_params:
                    if field == 'crew':
                        value = emp['crew'] or 'Z'
                    elif field == 'jobtitle':
                        value = emp['position'].name if emp['position'] else 'Z'
                    elif field == 'seniority':
                        value = emp['years_employed']
                    elif field == 'overtime':
                        value = emp['last_13_weeks_overtime']
                    else:
                        value = ''
                    
                    # Reverse for descending
                    if direction == 'desc':
                        if isinstance(value, (int, float)):
                            value = -value
                        elif isinstance(value, str):
                            # For strings, we'll handle desc differently
                            pass
                    
                    key_values.append(value)
                
                return tuple(key_values)
            
            # Sort with proper handling of desc for strings
            for field, direction in reversed(sort_params):
                reverse = (direction == 'desc')
                if field == 'crew':
                    employees_with_ot.sort(key=lambda x: x['crew'] or 'Z', reverse=reverse)
                elif field == 'jobtitle':
                    employees_with_ot.sort(key=lambda x: x['position'].name if x['position'] else 'Z', reverse=reverse)
                elif field == 'seniority':
                    employees_with_ot.sort(key=lambda x: x['years_employed'], reverse=reverse)
                elif field == 'overtime':
                    employees_with_ot.sort(key=lambda x: x['last_13_weeks_overtime'], reverse=reverse)
        
        # Paginate results
        total_count = len(employees_with_ot)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_employees = employees_with_ot[start_idx:end_idx]
        
        # Calculate pagination info
        total_pages = (total_count + per_page - 1) // per_page
        
        # Get positions for filter dropdown
        positions = Position.query.order_by(Position.name).all()
        
        # Calculate average overtime
        avg_overtime = round(total_overtime_hours / max(1, employees_with_overtime), 1) if employees_with_overtime > 0 else 0
        
        return render_template('overtime_management.html',
                             employees=paginated_employees,
                             page=page,
                             total_pages=total_pages,
                             total_overtime_hours=round(total_overtime_hours),
                             employees_with_overtime=employees_with_overtime,
                             avg_overtime=avg_overtime,
                             high_overtime_count=len(high_overtime_employees),
                             high_overtime_employees=high_overtime_employees,
                             positions=positions,
                             search_term=search_term,
                             crew_filter=crew_filter,
                             position_filter=position_filter,
                             ot_range_filter=ot_range_filter,
                             start_date=start_date,
                             end_date=end_date)
                             
    except Exception as e:
        logger.error(f"Error in overtime management: {e}")
        logger.error(f"Error type: {type(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Return template with minimal data to avoid error
        return render_template('overtime_management.html',
                             employees=[],
                             page=1,
                             total_pages=1,
                             total_overtime_hours=0,
                             employees_with_overtime=0,
                             avg_overtime=0,
                             high_overtime_count=0,
                             high_overtime_employees=[],
                             positions=[],
                             search_term='',
                             crew_filter='',
                             position_filter='',
                             ot_range_filter='',
                             start_date=date.today() - timedelta(weeks=13),
                             end_date=date.today())

@main_bp.route('/view-crews')
@login_required
def view_crews():
    """View all crews and their members"""
    try:
        crews = {}
        for crew in ['A', 'B', 'C', 'D']:
            try:
                crews[crew] = Employee.query.filter_by(crew=crew, is_active=True).all()
            except:
                crews[crew] = []
                db.session.rollback()
        
        return render_template('view_crews.html', crews=crews)
    except Exception as e:
        logger.error(f"Error in view crews: {e}")
        flash('Error loading crew information.', 'danger')
        return redirect(url_for('main.dashboard'))

# ==========================================
# DIAGNOSTIC ROUTES
# ==========================================

@main_bp.route('/diagnostic')
@login_required
@supervisor_required
def diagnostic():
    """System diagnostic page"""
    diagnostics = {
        'database': 'Unknown',
        'employees': 0,
        'supervisors': 0,
        'pending_time_off': 0,
        'pending_swaps': 0,
        'coverage_gaps': 0,
        'open_maintenance': 0
    }
    
    # Test database connection
    try:
        db.session.execute('SELECT 1')
        diagnostics['database'] = 'Connected'
    except:
        diagnostics['database'] = 'Error'
        db.session.rollback()
    
    # Get counts with error handling
    try:
        diagnostics['employees'] = Employee.query.filter_by(is_active=True).count()
    except:
        db.session.rollback()
        
    try:
        diagnostics['supervisors'] = Employee.query.filter_by(is_supervisor=True).count()
    except:
        db.session.rollback()
        
    try:
        diagnostics['pending_time_off'] = TimeOffRequest.query.filter_by(status='pending').count()
    except:
        db.session.rollback()
        
    try:
        diagnostics['pending_swaps'] = ShiftSwapRequest.query.filter_by(status='pending').count()
    except:
        db.session.rollback()
    
    return render_template('diagnostic.html', **diagnostics)

@main_bp.route('/debug-routes')
@login_required
@supervisor_required
def debug_routes():
    """Show all registered routes for debugging"""
    import urllib
    output = []
    
    for rule in current_app.url_map.iter_rules():
        options = {}
        for arg in rule.arguments:
            options[arg] = f"[{arg}]"
            
        methods = ','.join(rule.methods)
        url = url_for(rule.endpoint, **options)
        line = urllib.parse.unquote(f"{rule.endpoint:30s} {methods:10s} {url}")
        output.append(line)
    
    return "<h1>Available Routes:</h1><pre>" + "\n".join(sorted(output)) + "</pre>"

# ==========================================
# ERROR HANDLERS
# ==========================================

@main_bp.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@main_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# ==========================================
# TEMPLATE FILTERS
# ==========================================

@main_bp.app_template_filter('datetimeformat')
def datetimeformat(value, format='%Y-%m-%d %H:%M'):
    """Format a datetime object"""
    if value is None:
        return ""
    return value.strftime(format)

@main_bp.app_template_filter('dateformat')
def dateformat(value, format='%Y-%m-%d'):
    """Format a date object"""
    if value is None:
        return ""
    return value.strftime(format)
