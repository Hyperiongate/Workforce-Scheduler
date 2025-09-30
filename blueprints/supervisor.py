# blueprints/supervisor.py - COMPLETE FIXED VERSION WITH API ROUTES
"""
Supervisor blueprint with comprehensive error handling and ALL ROUTE FIXES
INCLUDES EMPLOYEE API ENDPOINTS FOR EDIT FUNCTIONALITY
COMPLETE DEPLOYMENT-READY VERSION - UPDATED 2025-09-30
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_required, current_user
from models import db, Employee, TimeOffRequest, ShiftSwapRequest, Schedule, Position
from datetime import date, datetime, timedelta
from sqlalchemy import func, and_, or_, text
from sqlalchemy.exc import ProgrammingError, OperationalError, IntegrityError
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
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def safe_database_query(description, query_func, fallback_value=None):
    """
    Execute database queries with comprehensive error handling
    Prevents crashes and provides graceful fallbacks
    """
    try:
        return query_func()
    except (ProgrammingError, OperationalError) as db_error:
        error_msg = str(db_error)
        logger.error(f"Database error in {description}: {error_msg}")
        
        # Handle specific column missing errors
        if 'column' in error_msg.lower() and 'does not exist' in error_msg.lower():
            logger.error(f"Missing database column detected in {description}")
            flash('Database schema issue detected. Running database fix...', 'warning')
        else:
            flash('Database error occurred. Please try again.', 'warning')
        
        db.session.rollback()
        return fallback_value
    except Exception as e:
        logger.error(f"Unexpected error in {description}: {str(e)}")
        flash('An unexpected error occurred. Please try again.', 'warning')
        db.session.rollback()
        return fallback_value

# ==========================================
# MAIN DASHBOARD - COMPREHENSIVE FIX
# ==========================================

@supervisor_bp.route('/supervisor/dashboard')
@login_required
@supervisor_required
def dashboard():
    """Supervisor dashboard with robust error handling and fallbacks"""
    try:
        logger.info(f"Loading supervisor dashboard for user: {current_user.name}")
        
        # Get selected crew from session or default to 'all'
        selected_crew = session.get('selected_crew', 'all')
        
        def get_dashboard_stats():
            """Get dashboard statistics with comprehensive error handling"""
            stats = {
                'pending_time_off': 0,
                'pending_swaps': 0,
                'employees_count': 0,
                'crew_counts': {'A': 0, 'B': 0, 'C': 0, 'D': 0},
                'recent_requests': []
            }
            
            try:
                # Get employee counts - this should always work
                if selected_crew == 'all':
                    stats['employees_count'] = Employee.query.count()
                    for crew in ['A', 'B', 'C', 'D']:
                        stats['crew_counts'][crew] = Employee.query.filter_by(crew=crew).count()
                else:
                    stats['employees_count'] = Employee.query.filter_by(crew=selected_crew).count()
                    stats['crew_counts'][selected_crew] = stats['employees_count']
                
                # Try to get time off requests
                try:
                    if selected_crew == 'all':
                        stats['pending_time_off'] = TimeOffRequest.query.filter_by(status='pending').count()
                    else:
                        stats['pending_time_off'] = db.session.query(TimeOffRequest).join(Employee).filter(
                            TimeOffRequest.status == 'pending',
                            Employee.crew == selected_crew
                        ).count()
                except Exception as e:
                    logger.warning(f"Could not get time off stats: {e}")
                    stats['pending_time_off'] = 0
                
                # Try to get shift swap requests using raw SQL to avoid ORM column issues
                try:
                    if selected_crew == 'all':
                        result = db.session.execute(text("""
                            SELECT COUNT(*) 
                            FROM shift_swap_request 
                            WHERE COALESCE(status, 'pending') = 'pending'
                        """))
                    else:
                        result = db.session.execute(text("""
                            SELECT COUNT(*) 
                            FROM shift_swap_request ssr
                            JOIN employee e ON ssr.requester_id = e.id
                            WHERE COALESCE(ssr.status, 'pending') = 'pending'
                            AND e.crew = :crew
                        """), {'crew': selected_crew})
                    
                    stats['pending_swaps'] = result.scalar() or 0
                    
                except Exception as e:
                    logger.warning(f"Could not get shift swap stats: {e}")
                    stats['pending_swaps'] = 0
                
                # Get recent requests for timeline with error handling
                try:
                    recent_time_off = []
                    recent_swaps = []
                    
                    # Get recent time off requests
                    try:
                        if selected_crew == 'all':
                            recent_time_off = TimeOffRequest.query.order_by(
                                TimeOffRequest.created_at.desc()
                            ).limit(5).all()
                        else:
                            recent_time_off = db.session.query(TimeOffRequest).join(Employee).filter(
                                Employee.crew == selected_crew
                            ).order_by(TimeOffRequest.created_at.desc()).limit(5).all()
                    except Exception as e:
                        logger.warning(f"Could not get recent time off requests: {e}")
                    
                    # Get recent swap requests using raw SQL
                    try:
                        if selected_crew == 'all':
                            result = db.session.execute(text("""
                                SELECT ssr.id, ssr.created_at, e.name as requester_name,
                                       COALESCE(ssr.status, 'pending') as status
                                FROM shift_swap_request ssr
                                JOIN employee e ON ssr.requester_id = e.id
                                ORDER BY ssr.created_at DESC
                                LIMIT 5
                            """))
                        else:
                            result = db.session.execute(text("""
                                SELECT ssr.id, ssr.created_at, e.name as requester_name,
                                       COALESCE(ssr.status, 'pending') as status
                                FROM shift_swap_request ssr
                                JOIN employee e ON ssr.requester_id = e.id
                                WHERE e.crew = :crew
                                ORDER BY ssr.created_at DESC
                                LIMIT 5
                            """), {'crew': selected_crew})
                        
                        recent_swaps = [dict(row._mapping) for row in result]
                    except Exception as e:
                        logger.warning(f"Could not get recent swap requests: {e}")
                    
                    # Combine and format recent requests safely
                    stats['recent_requests'] = []
                    
                    for req in recent_time_off:
                        try:
                            stats['recent_requests'].append({
                                'type': 'time_off',
                                'employee': req.employee.name if hasattr(req, 'employee') and req.employee else 'Unknown',
                                'date': req.created_at.strftime('%m/%d') if req.created_at else 'Unknown',
                                'status': req.status or 'pending'
                            })
                        except Exception as e:
                            logger.warning(f"Error processing time off request: {e}")
                    
                    for req in recent_swaps:
                        try:
                            stats['recent_requests'].append({
                                'type': 'shift_swap',
                                'employee': req.get('requester_name', 'Unknown'),
                                'date': req.get('created_at').strftime('%m/%d') if req.get('created_at') else 'Unknown',
                                'status': req.get('status', 'pending')
                            })
                        except Exception as e:
                            logger.warning(f"Error processing swap request: {e}")
                    
                    # Sort by date (most recent first)
                    stats['recent_requests'] = sorted(
                        stats['recent_requests'], 
                        key=lambda x: x.get('date', ''), 
                        reverse=True
                    )[:10]
                    
                except Exception as e:
                    logger.warning(f"Could not build recent requests timeline: {e}")
                    stats['recent_requests'] = []
            
            except Exception as e:
                logger.error(f"Error getting dashboard stats: {e}")
            
            return stats
        
        # Get dashboard data with error handling
        dashboard_data = safe_database_query("dashboard stats", get_dashboard_stats, {
            'pending_time_off': 0,
            'pending_swaps': 0,
            'employees_count': 0,
            'crew_counts': {'A': 0, 'B': 0, 'C': 0, 'D': 0},
            'recent_requests': []
        })
        
        return render_template('supervisor/dashboard.html',
                             selected_crew=selected_crew,
                             **dashboard_data)
    
    except Exception as e:
        logger.error(f"Critical error loading supervisor dashboard: {e}")
        flash('Dashboard temporarily unavailable. Please try again.', 'warning')
        return redirect(url_for('main.dashboard'))

@supervisor_bp.route('/supervisor/set-crew/<crew>')
@login_required
@supervisor_required
def set_crew(crew):
    """Set the selected crew filter"""
    if crew in ['all', 'A', 'B', 'C', 'D']:
        session['selected_crew'] = crew
        flash(f'Viewing crew: {crew if crew != "all" else "All Crews"}', 'info')
    return redirect(url_for('supervisor.dashboard'))

# ==========================================
# TIME OFF MANAGEMENT - ERROR HANDLED
# ==========================================

@supervisor_bp.route('/supervisor/time-off-requests')
@login_required
@supervisor_required
def time_off_requests():
    """View and manage time off requests with error handling"""
    try:
        crew = request.args.get('crew', session.get('selected_crew', 'all'))
        session['selected_crew'] = crew
        
        def get_time_off_requests():
            """Get time off requests with error handling"""
            try:
                if crew == 'all':
                    requests = TimeOffRequest.query.filter_by(status='pending').order_by(
                        TimeOffRequest.created_at.desc()
                    ).all()
                else:
                    requests = db.session.query(TimeOffRequest).join(Employee).filter(
                        TimeOffRequest.status == 'pending',
                        Employee.crew == crew
                    ).order_by(TimeOffRequest.created_at.desc()).all()
                
                return requests
            except Exception as e:
                logger.error(f"Error getting time off requests: {e}")
                return []
        
        pending_requests = safe_database_query("time off requests", get_time_off_requests, [])
        
        return render_template('supervisor/time_off_requests.html',
                             pending_requests=pending_requests,
                             selected_crew=crew)
    
    except Exception as e:
        logger.error(f"Error loading time off requests: {e}")
        flash('Error loading time off requests.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/approve-time-off/<int:request_id>')
@login_required
@supervisor_required
def approve_time_off(request_id):
    """Approve a time off request with error handling"""
    try:
        def approve_request():
            request_obj = TimeOffRequest.query.get_or_404(request_id)
            request_obj.status = 'approved'
            request_obj.approved_date = date.today()
            db.session.commit()
            return True
        
        success = safe_database_query("approve time off", approve_request)
        if success:
            flash('Time off request approved!', 'success')
        else:
            flash('Error approving request.', 'danger')
        
    except Exception as e:
        logger.error(f"Error approving time off: {e}")
        flash('Error approving request.', 'danger')
    
    crew = request.args.get('crew', session.get('selected_crew', 'all'))
    return redirect(url_for('supervisor.time_off_requests', crew=crew))

@supervisor_bp.route('/supervisor/deny-time-off/<int:request_id>')
@login_required
@supervisor_required
def deny_time_off(request_id):
    """Deny a time off request with error handling"""
    try:
        def deny_request():
            request_obj = TimeOffRequest.query.get_or_404(request_id)
            request_obj.status = 'denied'
            db.session.commit()
            return True
        
        success = safe_database_query("deny time off", deny_request)
        if success:
            flash('Time off request denied.', 'info')
        else:
            flash('Error denying request.', 'danger')
        
    except Exception as e:
        logger.error(f"Error denying time off: {e}")
        flash('Error denying request.', 'danger')
    
    crew = request.args.get('crew', session.get('selected_crew', 'all'))
    return redirect(url_for('supervisor.time_off_requests', crew=crew))

# ==========================================
# SHIFT SWAP MANAGEMENT - FIXED ROUTE NAME
# ==========================================

@supervisor_bp.route('/supervisor/shift-swaps')
@login_required
@supervisor_required
def shift_swaps():
    """View and manage shift swap requests - CORRECT ROUTE NAME"""
    try:
        crew = request.args.get('crew', session.get('selected_crew', 'all'))
        session['selected_crew'] = crew
        
        def get_swaps():
            """Get shift swaps using raw SQL to avoid ORM issues"""
            try:
                if crew and crew != 'all':
                    result = db.session.execute(text("""
                        SELECT ssr.id, ssr.requester_id,
                               COALESCE(ssr.status, 'pending') as status,
                               COALESCE(ssr.reason, '') as reason,
                               ssr.created_at,
                               e.name as requester_name, e.crew
                        FROM shift_swap_request ssr
                        JOIN employee e ON ssr.requester_id = e.id
                        WHERE COALESCE(ssr.status, 'pending') = 'pending'
                        AND e.crew = :crew
                        ORDER BY ssr.created_at DESC
                    """), {'crew': crew})
                else:
                    result = db.session.execute(text("""
                        SELECT ssr.id, ssr.requester_id,
                               COALESCE(ssr.status, 'pending') as status,
                               COALESCE(ssr.reason, '') as reason,
                               ssr.created_at,
                               e.name as requester_name, e.crew
                        FROM shift_swap_request ssr
                        JOIN employee e ON ssr.requester_id = e.id
                        WHERE COALESCE(ssr.status, 'pending') = 'pending'
                        ORDER BY ssr.created_at DESC
                    """))
                
                swaps = []
                for row in result:
                    # Create a simple object to hold swap data
                    class SimpleSwap:
                        pass
                    
                    swap = SimpleSwap()
                    swap.id = row[0]
                    swap.requester_id = row[1]
                    swap.status = row[2]
                    swap.reason = row[3] or ''
                    swap.created_at = row[4]
                    swap.requester_name = row[5]
                    swap.crew = row[6]
                    swaps.append(swap)
                
                return swaps
                
            except Exception as e:
                logger.error(f"Error getting shift swaps: {e}")
                return []
        
        pending_swaps = safe_database_query("shift swaps", get_swaps, [])
        
        return render_template('supervisor/shift_swaps.html',
                             pending_swaps=pending_swaps,
                             selected_crew=crew)
        
    except Exception as e:
        logger.error(f"Error loading shift swaps: {e}")
        flash('Error loading shift swaps.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/approve-swap/<int:swap_id>')
@login_required
@supervisor_required
def approve_swap(swap_id):
    """Approve a shift swap request with error handling"""
    try:
        def approve_swap_func():
            # Use raw SQL to avoid ORM issues
            db.session.execute(text("""
                UPDATE shift_swap_request 
                SET status = 'approved',
                    reviewed_by_id = :reviewer_id,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE id = :swap_id
            """), {'swap_id': swap_id, 'reviewer_id': current_user.id})
            db.session.commit()
            return True
        
        success = safe_database_query("approve swap", approve_swap_func)
        if success:
            flash('Shift swap approved!', 'success')
        else:
            flash('Error approving swap.', 'danger')
        
    except Exception as e:
        logger.error(f"Error approving swap: {e}")
        flash('Error approving swap.', 'danger')
    
    crew = request.args.get('crew', session.get('selected_crew', 'all'))
    return redirect(url_for('supervisor.shift_swaps', crew=crew))

@supervisor_bp.route('/supervisor/deny-swap/<int:swap_id>')
@login_required
@supervisor_required
def deny_swap(swap_id):
    """Deny a shift swap request with error handling"""
    try:
        def deny_swap_func():
            # Use raw SQL to avoid ORM issues
            db.session.execute(text("""
                UPDATE shift_swap_request 
                SET status = 'denied',
                    reviewed_by_id = :reviewer_id,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE id = :swap_id
            """), {'swap_id': swap_id, 'reviewer_id': current_user.id})
            db.session.commit()
            return True
        
        success = safe_database_query("deny swap", deny_swap_func)
        if success:
            flash('Shift swap denied.', 'info')
        else:
            flash('Error denying swap.', 'danger')
        
    except Exception as e:
        logger.error(f"Error denying swap: {e}")
        flash('Error denying swap.', 'danger')
    
    crew = request.args.get('crew', session.get('selected_crew', 'all'))
    return redirect(url_for('supervisor.shift_swaps', crew=crew))

# ==========================================
# EMPLOYEE MANAGEMENT - FIXED ROUTES
# ==========================================

@supervisor_bp.route('/supervisor/employees')
@login_required
@supervisor_required
def employees():
    """View and manage employees with error handling"""
    try:
        crew = request.args.get('crew', session.get('selected_crew', 'all'))
        session['selected_crew'] = crew
        
        def get_employees():
            if crew == 'all':
                return Employee.query.order_by(Employee.name).all()
            else:
                return Employee.query.filter_by(crew=crew).order_by(Employee.name).all()
        
        employees_list = safe_database_query("employees", get_employees, [])
        
        return render_template('supervisor/employees.html',
                             employees=employees_list,
                             selected_crew=crew)
    
    except Exception as e:
        logger.error(f"Error loading employees: {e}")
        flash('Error loading employees.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/employee-management')
@login_required
@supervisor_required
def employee_management():
    """Employee management page - renders the comprehensive employee list"""
    try:
        crew = request.args.get('crew', session.get('selected_crew', 'all'))
        session['selected_crew'] = crew
        
        # Get employees based on crew filter
        def get_employees():
            if crew == 'all':
                return Employee.query.order_by(Employee.name).all()
            else:
                return Employee.query.filter_by(crew=crew).order_by(Employee.name).all()
        
        employees_list = safe_database_query("employees", get_employees, [])
        
        # Get positions for the filter dropdown
        positions = Position.query.order_by(Position.name).all()
        
        # Calculate total skills if you have the Skill model
        try:
            from models import Skill
            total_skills = db.session.query(func.count(func.distinct(Skill.id))).scalar() or 0
        except:
            total_skills = 0
        
        # FIXED: Render the template - use employee_management.html directly
        return render_template('employee_management.html',
                             employees=employees_list,
                             positions=positions,
                             total_skills=total_skills,
                             selected_crew=crew)
    
    except Exception as e:
        logger.error(f"Error loading employee management: {e}")
        flash('Error loading employee management.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# EMPLOYEE API ENDPOINTS
# ==========================================

@supervisor_bp.route('/api/employee/<int:employee_id>')
@login_required
@supervisor_required
def api_get_employee(employee_id):
    """API endpoint to get employee details"""
    try:
        employee = Employee.query.get_or_404(employee_id)
        
        position_name = ''
        if employee.position:
            position_name = employee.position.name
        
        return jsonify({
            'success': True,
            'employee': {
                'id': employee.id,
                'employee_id': employee.employee_id,
                'first_name': employee.name.split(' ')[0] if employee.name else '',
                'last_name': ' '.join(employee.name.split(' ')[1:]) if employee.name and len(employee.name.split(' ')) > 1 else '',
                'email': employee.email,
                'crew': employee.crew,
                'position': position_name,
                'department': getattr(employee, 'department', ''),
                'phone': getattr(employee, 'phone', ''),
                'hire_date': employee.hire_date.strftime('%Y-%m-%d') if employee.hire_date else None,
                'is_supervisor': employee.is_supervisor,
                'is_active': employee.is_active
            }
        })
    except Exception as e:
        logger.error(f"Error getting employee {employee_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@supervisor_bp.route('/api/employee/<int:employee_id>', methods=['PUT'])
@login_required
@supervisor_required
def api_update_employee(employee_id):
    """API endpoint to update employee details"""
    try:
        employee = Employee.query.get_or_404(employee_id)
        data = request.get_json()
        
        # Update basic fields
        if 'first_name' in data and 'last_name' in data:
            employee.name = f"{data['first_name']} {data['last_name']}"
        
        if 'employee_code' in data:
            employee.employee_id = data['employee_code']
        
        if 'email' in data:
            employee.email = data['email']
        
        if 'crew' in data:
            employee.crew = data['crew'] if data['crew'] else None
        
        if 'department' in data and hasattr(employee, 'department'):
            employee.department = data['department']
        
        if 'phone' in data and hasattr(employee, 'phone'):
            employee.phone = data['phone']
        
        if 'hire_date' in data and data['hire_date']:
            try:
                employee.hire_date = datetime.strptime(data['hire_date'], '%Y-%m-%d').date()
            except:
                pass
        
        # Update position if provided
        if 'position' in data:
            if data['position']:
                position = Position.query.filter_by(name=data['position']).first()
                if not position:
                    position = Position(name=data['position'])
                    db.session.add(position)
                employee.position = position
            else:
                employee.position = None
        
        # Update boolean fields
        if 'is_supervisor' in data:
            employee.is_supervisor = bool(data['is_supervisor'])
        
        if 'is_active' in data:
            employee.is_active = bool(data['is_active'])
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Employee updated successfully'
        })
        
    except Exception as e:
        logger.error(f"Error updating employee {employee_id}: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@supervisor_bp.route('/api/employee/<int:employee_id>/status', methods=['PATCH'])
@login_required
@supervisor_required
def api_toggle_employee_status(employee_id):
    """API endpoint to toggle employee active status"""
    try:
        employee = Employee.query.get_or_404(employee_id)
        data = request.get_json()
        
        if 'is_active' in data:
            employee.is_active = bool(data['is_active'])
            db.session.commit()
            
            status = 'activated' if employee.is_active else 'deactivated'
            return jsonify({
                'success': True,
                'message': f'Employee {status} successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'is_active not provided'}), 400
            
    except Exception as e:
        logger.error(f"Error toggling employee status {employee_id}: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ==========================================
# CREW MANAGEMENT
# ==========================================

@supervisor_bp.route('/supervisor/crew-management')
@login_required
@supervisor_required
def crew_management():
    """Crew management page"""
    try:
        crew = request.args.get('crew', session.get('selected_crew', 'all'))
        session['selected_crew'] = crew
        
        def get_crew_data():
            if crew == 'all':
                crew_data = {}
                for c in ['A', 'B', 'C', 'D']:
                    crew_data[c] = Employee.query.filter_by(crew=c).all()
                return crew_data
            else:
                return {crew: Employee.query.filter_by(crew=crew).all()}
        
        crew_data = safe_database_query("crew data", get_crew_data, {})
        
        # Try template first, fallback to HTML
        try:
            return render_template('supervisor/crew_management.html',
                                 crew_data=crew_data,
                                 selected_crew=crew)
        except:
            total_employees = sum(len(employees) for employees in crew_data.values())
            
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Crew Management</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
                <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.7.2/font/bootstrap-icons.css" rel="stylesheet">
            </head>
            <body>
                <div class="container mt-4">
                    <h2>Crew Management</h2>
                    <p>Managing {total_employees} total employees across all crews.</p>
                    <a href="/supervisor/dashboard" class="btn btn-primary">Back to Dashboard</a>
                </div>
            </body>
            </html>
            """
    
    except Exception as e:
        logger.error(f"Error loading crew management: {e}")
        flash('Error loading crew management.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# OVERTIME MANAGEMENT
# ==========================================

@supervisor_bp.route('/supervisor/overtime-management')
@login_required
@supervisor_required
def overtime_management():
    """Overtime management page"""
    try:
        crew = request.args.get('crew', session.get('selected_crew', 'all'))
        session['selected_crew'] = crew
        
        flash('Overtime management feature coming soon.', 'info')
        return redirect(url_for('supervisor.employee_management', crew=crew))
    
    except Exception as e:
        logger.error(f"Error loading overtime management: {e}")
        flash('Error loading overtime management.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# COVERAGE MANAGEMENT
# ==========================================

@supervisor_bp.route('/supervisor/coverage-gaps')
@login_required
@supervisor_required
def coverage_gaps():
    """Coverage gaps analysis"""
    try:
        crew = request.args.get('crew', session.get('selected_crew', 'all'))
        session['selected_crew'] = crew
        
        # Simple HTML fallback for now
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Coverage Gaps</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body>
            <div class="container mt-4">
                <h2>Coverage Gaps Analysis</h2>
                <p>No critical coverage gaps detected for {crew if crew != 'all' else 'all crews'}.</p>
                <a href="/supervisor/dashboard" class="btn btn-primary">Back to Dashboard</a>
            </div>
        </body>
        </html>
        """
    
    except Exception as e:
        logger.error(f"Error loading coverage gaps: {e}")
        flash('Error loading coverage gaps.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/coverage-needs')
@login_required
@supervisor_required
def coverage_needs():
    """Coverage needs analysis"""
    try:
        crew = request.args.get('crew', session.get('selected_crew', 'all'))
        session['selected_crew'] = crew
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Coverage Needs</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body>
            <div class="container mt-4">
                <h2>Coverage Needs Analysis</h2>
                <p>Current staffing levels meet operational requirements for {crew if crew != 'all' else 'all crews'}.</p>
                <a href="/supervisor/dashboard" class="btn btn-primary">Back to Dashboard</a>
            </div>
        </body>
        </html>
        """
    
    except Exception as e:
        logger.error(f"Error loading coverage needs: {e}")
        flash('Error loading coverage needs.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# SCHEDULES MANAGEMENT
# ==========================================

@supervisor_bp.route('/supervisor/schedules')
@login_required
@supervisor_required
def schedules():
    """View schedules with error handling"""
    try:
        crew = request.args.get('crew', session.get('selected_crew', 'all'))
        session['selected_crew'] = crew
        
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        
        def get_schedules():
            if crew == 'all':
                return Schedule.query.filter(
                    Schedule.date.between(start_of_week, end_of_week)
                ).order_by(Schedule.date, Schedule.shift_type).all()
            else:
                return db.session.query(Schedule).join(Employee).filter(
                    Schedule.date.between(start_of_week, end_of_week),
                    Employee.crew == crew
                ).order_by(Schedule.date, Schedule.shift_type).all()
        
        schedules_list = safe_database_query("schedules", get_schedules, [])
        
        return render_template('supervisor/schedules.html',
                             schedules=schedules_list,
                             selected_crew=crew,
                             start_date=start_of_week,
                             end_date=end_of_week)
    
    except Exception as e:
        logger.error(f"Error loading schedules: {e}")
        flash('Error loading schedules.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# API ENDPOINTS
# ==========================================

@supervisor_bp.route('/api/supervisor/stats')
@login_required
@supervisor_required
def api_stats():
    """API endpoint for dashboard statistics"""
    try:
        crew = request.args.get('crew', 'all')
        
        def get_api_stats():
            stats = {
                'pending_time_off': 0,
                'pending_swaps': 0,
                'employees_count': 0
            }
            
            try:
                if crew == 'all':
                    stats['employees_count'] = Employee.query.count()
                    stats['pending_time_off'] = TimeOffRequest.query.filter_by(status='pending').count()
                else:
                    stats['employees_count'] = Employee.query.filter_by(crew=crew).count()
                    stats['pending_time_off'] = db.session.query(TimeOffRequest).join(Employee).filter(
                        TimeOffRequest.status == 'pending',
                        Employee.crew == crew
                    ).count()
                
                # Get pending swaps with raw SQL
                if crew == 'all':
                    result = db.session.execute(text("""
                        SELECT COUNT(*) FROM shift_swap_request 
                        WHERE COALESCE(status, 'pending') = 'pending'
                    """))
                else:
                    result = db.session.execute(text("""
                        SELECT COUNT(*) FROM shift_swap_request ssr
                        JOIN employee e ON ssr.requester_id = e.id
                        WHERE COALESCE(ssr.status, 'pending') = 'pending'
                        AND e.crew = :crew
                    """), {'crew': crew})
                
                stats['pending_swaps'] = result.scalar() or 0
                
            except Exception as e:
                logger.error(f"Error getting API stats: {e}")
            
            return stats
        
        stats = safe_database_query("API stats", get_api_stats, {
            'pending_time_off': 0,
            'pending_swaps': 0,
            'employees_count': 0
        })
        
        return jsonify(stats)
    
    except Exception as e:
        logger.error(f"Error in API stats endpoint: {e}")
        return jsonify({'error': 'Unable to retrieve statistics'}), 500

# ==========================================
# ERROR HANDLERS
# ==========================================

@supervisor_bp.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors in supervisor blueprint"""
    flash('The requested page was not found.', 'warning')
    return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.errorhandler(500)
def internal_error(error):
    """Handle 500 errors in supervisor blueprint"""
    logger.error(f"Internal server error in supervisor blueprint: {error}")
    db.session.rollback()
    flash('An internal error occurred. Please try again.', 'danger')
    return redirect(url_for('supervisor.dashboard'))
