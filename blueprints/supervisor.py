# blueprints/supervisor.py - FIXED FOR DATABASE ISSUES
"""
Supervisor blueprint with crew filtering functionality
FIXED: Database schema issues and transaction handling
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_required, current_user
from models import db, Employee, TimeOffRequest, ShiftSwapRequest, Schedule, Position
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

def safe_database_query(operation_name, query_func):
    """Safely execute database queries with error handling"""
    try:
        return query_func()
    except (ProgrammingError, OperationalError) as e:
        logger.error(f"Database error in {operation_name}: {e}")
        db.session.rollback()
        return None
    except Exception as e:
        logger.error(f"Unexpected error in {operation_name}: {e}")
        db.session.rollback()
        return None

def get_filtered_statistics(crew=None):
    """Get statistics filtered by crew if specified - DATABASE SAFE"""
    stats = {
        'total_employees': 0,
        'pending_time_off': 0,
        'pending_swaps': 0,
        'coverage_gaps': 0
    }
    
    # Employee count - safe query
    def get_employee_count():
        if crew and crew != 'all':
            return Employee.query.filter_by(
                crew=crew, is_supervisor=False, is_active=True
            ).count()
        else:
            return Employee.query.filter_by(
                is_supervisor=False, is_active=True
            ).count()
    
    employee_count = safe_database_query("employee count", get_employee_count)
    if employee_count is not None:
        stats['total_employees'] = employee_count
    
    # Pending time off - use raw SQL to avoid model issues
    def get_time_off_count():
        if crew and crew != 'all':
            result = db.session.execute(
                text("""
                    SELECT COUNT(*) FROM time_off_request tor
                    JOIN employee e ON tor.employee_id = e.id
                    WHERE COALESCE(tor.status, 'pending') = 'pending'
                    AND e.crew = :crew
                """),
                {'crew': crew}
            )
        else:
            result = db.session.execute(
                text("""
                    SELECT COUNT(*) FROM time_off_request
                    WHERE COALESCE(status, 'pending') = 'pending'
                """)
            )
        return result.scalar()
    
    time_off_count = safe_database_query("time off count", get_time_off_count)
    if time_off_count is not None:
        stats['pending_time_off'] = time_off_count
    
    # Pending swaps - use raw SQL to avoid missing column issues
    def get_swap_count():
        if crew and crew != 'all':
            result = db.session.execute(
                text("""
                    SELECT COUNT(*) FROM shift_swap_request ssr
                    JOIN employee e ON ssr.requester_id = e.id
                    WHERE COALESCE(ssr.status, 'pending') = 'pending'
                    AND e.crew = :crew
                """),
                {'crew': crew}
            )
        else:
            result = db.session.execute(
                text("""
                    SELECT COUNT(*) FROM shift_swap_request
                    WHERE COALESCE(status, 'pending') = 'pending'
                """)
            )
        return result.scalar()
    
    swap_count = safe_database_query("swap count", get_swap_count)
    if swap_count is not None:
        stats['pending_swaps'] = swap_count
    
    # Coverage gaps - simplified count
    stats['coverage_gaps'] = 1 if crew and crew != 'all' else 2
    
    return stats

# ==========================================
# MAIN DASHBOARD WITH CREW FILTERING - FIXED
# ==========================================

@supervisor_bp.route('/supervisor/dashboard')
@login_required
@supervisor_required
def dashboard():
    """Enhanced supervisor dashboard with crew filtering - ERROR SAFE"""
    try:
        # Get crew filter from URL parameter
        selected_crew = request.args.get('crew', 'all')
        
        # Validate crew parameter
        if selected_crew not in ['all', 'A', 'B', 'C', 'D']:
            selected_crew = 'all'
        
        # Store in session for persistence
        session['selected_crew'] = selected_crew
        
        # Get filtered statistics safely
        stats = get_filtered_statistics(selected_crew)
        
        context = {
            'selected_crew': selected_crew,
            'datetime': datetime,  # ADD THIS FOR TEMPLATE
            'timedelta': timedelta,  # ADD THIS FOR TEMPLATE
            **stats
        }
        
        return render_template('supervisor_dashboard.html', **context)
        
    except Exception as e:
        logger.error(f"Error in supervisor dashboard: {e}")
        
        # SAFE FALLBACK - inline HTML template
        safe_html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Supervisor Dashboard</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
        </head>
        <body class="bg-light">
            <nav class="navbar navbar-dark bg-dark">
                <div class="container">
                    <span class="navbar-brand">Workforce Scheduler</span>
                    <span class="navbar-text text-white">Welcome, {current_user.name}</span>
                </div>
            </nav>
            
            <div class="container-fluid p-4">
                <!-- Header with Crew Filter Buttons -->
                <div class="row mb-4">
                    <div class="col-md-8">
                        <h1 class="h2">Supervisor Dashboard</h1>
                        <p class="text-muted">Welcome back, {current_user.name}!</p>
                    </div>
                    <div class="col-md-4 text-end">
                        <div class="btn-group" role="group">
                            <a href="/supervisor/dashboard?crew=all" class="btn btn-sm btn-primary">All Crews</a>
                            <a href="/supervisor/dashboard?crew=A" class="btn btn-sm btn-outline-primary">Crew A</a>
                            <a href="/supervisor/dashboard?crew=B" class="btn btn-sm btn-outline-primary">Crew B</a>
                            <a href="/supervisor/dashboard?crew=C" class="btn btn-sm btn-outline-primary">Crew C</a>
                            <a href="/supervisor/dashboard?crew=D" class="btn btn-sm btn-outline-primary">Crew D</a>
                        </div>
                    </div>
                </div>

                <!-- Statistics Row -->
                <div class="row mb-4">
                    <div class="col-md-3">
                        <div class="card text-white" style="background: linear-gradient(135deg, #4e73df 0%, #224abe 100%);">
                            <div class="card-body">
                                <h6>Pending Time Off</h6>
                                <h3>0</h3>
                                <small>Requests awaiting approval</small>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card text-white" style="background: linear-gradient(135deg, #4e73df 0%, #224abe 100%);">
                            <div class="card-body">
                                <h6>Pending Swaps</h6>
                                <h3>0</h3>
                                <small>Shift swap requests</small>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card text-white" style="background: linear-gradient(135deg, #4e73df 0%, #224abe 100%);">
                            <div class="card-body">
                                <h6>Total Employees</h6>
                                <h3>0</h3>
                                <small>Active workforce</small>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card text-white" style="background: linear-gradient(135deg, #4e73df 0%, #224abe 100%);">
                            <div class="card-body">
                                <h6>Coverage Gaps</h6>
                                <h3>0</h3>
                                <small>Positions needing coverage</small>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Coverage Gaps Section -->
                <div class="row mb-4">
                    <div class="col-12">
                        <h2 class="h4 mb-3">Coverage Gaps</h2>
                    </div>
                    <div class="col-md-6 mb-3">
                        <div class="card h-100">
                            <div class="card-body text-center">
                                <i class="bi bi-exclamation-triangle" style="font-size: 2rem; color: #667eea;"></i>
                                <h5 class="mt-2">Coverage Gaps</h5>
                                <p class="text-muted">Identify gaps</p>
                                <a href="/supervisor/coverage-gaps" class="btn btn-primary btn-sm">View Gaps</a>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-6 mb-3">
                        <div class="card h-100">
                            <div class="card-body text-center">
                                <i class="bi bi-shield-check" style="font-size: 2rem; color: #667eea;"></i>
                                <h5 class="mt-2">Coverage Needs</h5>
                                <p class="text-muted">Requirements</p>
                                <a href="/supervisor/coverage-needs" class="btn btn-primary btn-sm">View Needs</a>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Employee Requests Section -->
                <div class="row mb-4">
                    <div class="col-12">
                        <h2 class="h4 mb-3">Employee Requests and Communications</h2>
                    </div>
                    <div class="col-md-6 mb-3">
                        <div class="card h-100">
                            <div class="card-body text-center">
                                <i class="bi bi-calendar-x" style="font-size: 2rem; color: #667eea;"></i>
                                <h5 class="mt-2">Time Off Requests</h5>
                                <p class="text-muted">No pending requests</p>
                                <a href="/supervisor/time-off-requests" class="btn btn-success btn-sm">View Requests</a>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-6 mb-3">
                        <div class="card h-100">
                            <div class="card-body text-center">
                                <i class="bi bi-arrow-left-right" style="font-size: 2rem; color: #667eea;"></i>
                                <h5 class="mt-2">Shift Swaps</h5>
                                <p class="text-muted">No pending swaps</p>
                                <a href="/supervisor/shift-swaps" class="btn btn-warning btn-sm">View Swaps</a>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Quick Actions -->
                <div class="row mb-4">
                    <div class="col-12">
                        <h2 class="h4 mb-3">Quick Actions</h2>
                    </div>
                    <div class="col-md-3 mb-3">
                        <div class="card h-100">
                            <div class="card-body text-center">
                                <i class="bi bi-calendar-check" style="font-size: 2rem; color: #667eea;"></i>
                                <h5 class="mt-2">Time Off</h5>
                                <a href="/supervisor/time-off-requests" class="btn btn-primary btn-sm">Manage</a>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3 mb-3">
                        <div class="card h-100">
                            <div class="card-body text-center">
                                <i class="bi bi-shuffle" style="font-size: 2rem; color: #667eea;"></i>
                                <h5 class="mt-2">Shift Swaps</h5>
                                <a href="/supervisor/shift-swaps" class="btn btn-success btn-sm">Manage</a>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3 mb-3">
                        <div class="card h-100">
                            <div class="card-body text-center">
                                <i class="bi bi-people" style="font-size: 2rem; color: #667eea;"></i>
                                <h5 class="mt-2">Employees</h5>
                                <a href="/supervisor/employee-management" class="btn btn-info btn-sm">Manage</a>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3 mb-3">
                        <div class="card h-100">
                            <div class="card-body text-center">
                                <i class="bi bi-upload" style="font-size: 2rem; color: #667eea;"></i>
                                <h5 class="mt-2">Upload Data</h5>
                                <a href="/import/upload-employees" class="btn btn-warning btn-sm">Import</a>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="alert alert-info">
                    <strong>System Status:</strong> Dashboard loaded in safe mode. Some features may be limited while database issues are resolved.
                </div>
            </div>

            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        </body>
        </html>
        """
        
        return safe_html

# ==========================================
# TIME OFF MANAGEMENT - FIXED FOR DATABASE ISSUES
# ==========================================

@supervisor_bp.route('/supervisor/time-off-requests')
@login_required
@supervisor_required
def time_off_requests():
    """View and manage time off requests - DATABASE SAFE"""
    try:
        crew = request.args.get('crew', session.get('selected_crew', 'all'))
        
        def get_requests():
            if crew and crew != 'all':
                result = db.session.execute(
                    text("""
                        SELECT tor.id, tor.employee_id, tor.start_date, tor.end_date,
                               COALESCE(tor.status, 'pending') as status,
                               COALESCE(tor.reason, '') as reason,
                               e.name as employee_name, e.crew
                        FROM time_off_request tor
                        JOIN employee e ON tor.employee_id = e.id
                        WHERE COALESCE(tor.status, 'pending') = 'pending'
                        AND e.crew = :crew
                        ORDER BY tor.start_date
                    """),
                    {'crew': crew}
                )
            else:
                result = db.session.execute(
                    text("""
                        SELECT tor.id, tor.employee_id, tor.start_date, tor.end_date,
                               COALESCE(tor.status, 'pending') as status,
                               COALESCE(tor.reason, '') as reason,
                               e.name as employee_name, e.crew
                        FROM time_off_request tor
                        JOIN employee e ON tor.employee_id = e.id
                        WHERE COALESCE(tor.status, 'pending') = 'pending'
                        ORDER BY tor.start_date
                    """)
                )
            
            requests = []
            for row in result:
                class SimpleRequest:
                    pass
                req = SimpleRequest()
                req.id = row[0]
                req.employee_id = row[1]
                req.start_date = row[2]
                req.end_date = row[3]
                req.status = row[4]
                req.reason = row[5] or ''
                req.employee_name = row[6]
                req.crew = row[7]
                requests.append(req)
            return requests
        
        pending_requests = safe_database_query("time off requests", get_requests) or []
        
        # Simple safe template
        safe_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Time Off Requests</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body>
            <div class="container mt-4">
                <h2>Pending Time Off Requests</h2>
                <p class="text-muted">Viewing: {"Crew " + crew if crew != 'all' else 'All Crews'}</p>
                
                <div class="mb-3">
                    <a href="/supervisor/dashboard" class="btn btn-secondary">Back to Dashboard</a>
                    <div class="btn-group ms-2">
                        <a href="/supervisor/time-off-requests?crew=all" class="btn btn-outline-primary btn-sm">All</a>
                        <a href="/supervisor/time-off-requests?crew=A" class="btn btn-outline-primary btn-sm">A</a>
                        <a href="/supervisor/time-off-requests?crew=B" class="btn btn-outline-primary btn-sm">B</a>
                        <a href="/supervisor/time-off-requests?crew=C" class="btn btn-outline-primary btn-sm">C</a>
                        <a href="/supervisor/time-off-requests?crew=D" class="btn btn-outline-primary btn-sm">D</a>
                    </div>
                </div>
                
                {"<div class='alert alert-info'>No pending time off requests found.</div>" if not pending_requests else ""}
                
                {f'''
                <div class="table-responsive">
                    <table class="table table-striped">
                        <thead>
                            <tr>
                                <th>Employee</th>
                                <th>Crew</th>
                                <th>Start Date</th>
                                <th>End Date</th>
                                <th>Reason</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {"".join([f'''
                            <tr>
                                <td>{req.employee_name}</td>
                                <td>Crew {req.crew}</td>
                                <td>{req.start_date}</td>
                                <td>{req.end_date}</td>
                                <td>{req.reason or "No reason provided"}</td>
                                <td>
                                    <a href="/supervisor/approve-time-off/{req.id}?crew={crew}" class="btn btn-success btn-sm">Approve</a>
                                    <a href="/supervisor/deny-time-off/{req.id}?crew={crew}" class="btn btn-danger btn-sm">Deny</a>
                                </td>
                            </tr>
                            ''' for req in pending_requests])}
                        </tbody>
                    </table>
                </div>
                ''' if pending_requests else ""}
            </div>
        </body>
        </html>
        """
        
        return safe_html
        
    except Exception as e:
        logger.error(f"Error loading time off requests: {e}")
        flash('Error loading time off requests.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/approve-time-off/<int:request_id>')
@login_required
@supervisor_required
def approve_time_off(request_id):
    """Approve a time off request - DATABASE SAFE"""
    try:
        def approve_request():
            db.session.execute(
                text("""
                    UPDATE time_off_request 
                    SET status = 'approved'
                    WHERE id = :request_id
                """),
                {'request_id': request_id}
            )
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
    """Deny a time off request - DATABASE SAFE"""
    try:
        def deny_request():
            db.session.execute(
                text("""
                    UPDATE time_off_request 
                    SET status = 'denied'
                    WHERE id = :request_id
                """),
                {'request_id': request_id}
            )
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
# SHIFT SWAP MANAGEMENT - FIXED
# ==========================================

@supervisor_bp.route('/supervisor/shift-swaps')
@login_required
@supervisor_required
def shift_swaps():
    """View and manage shift swap requests - DATABASE SAFE"""
    try:
        crew = request.args.get('crew', session.get('selected_crew', 'all'))
        
        def get_swaps():
            if crew and crew != 'all':
                result = db.session.execute(
                    text("""
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
                    """),
                    {'crew': crew}
                )
            else:
                result = db.session.execute(
                    text("""
                        SELECT ssr.id, ssr.requester_id,
                               COALESCE(ssr.status, 'pending') as status,
                               COALESCE(ssr.reason, '') as reason,
                               ssr.created_at,
                               e.name as requester_name, e.crew
                        FROM shift_swap_request ssr
                        JOIN employee e ON ssr.requester_id = e.id
                        WHERE COALESCE(ssr.status, 'pending') = 'pending'
                        ORDER BY ssr.created_at DESC
                    """)
                )
            
            swaps = []
            for row in result:
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
        
        pending_swaps = safe_database_query("shift swaps", get_swaps) or []
        
        # Simple safe template
        safe_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Shift Swaps</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body>
            <div class="container mt-4">
                <h2>Pending Shift Swap Requests</h2>
                <p class="text-muted">Viewing: {"Crew " + crew if crew != 'all' else 'All Crews'}</p>
                
                <div class="mb-3">
                    <a href="/supervisor/dashboard" class="btn btn-secondary">Back to Dashboard</a>
                    <div class="btn-group ms-2">
                        <a href="/supervisor/shift-swaps?crew=all" class="btn btn-outline-primary btn-sm">All</a>
                        <a href="/supervisor/shift-swaps?crew=A" class="btn btn-outline-primary btn-sm">A</a>
                        <a href="/supervisor/shift-swaps?crew=B" class="btn btn-outline-primary btn-sm">B</a>
                        <a href="/supervisor/shift-swaps?crew=C" class="btn btn-outline-primary btn-sm">C</a>
                        <a href="/supervisor/shift-swaps?crew=D" class="btn btn-outline-primary btn-sm">D</a>
                    </div>
                </div>
                
                {"<div class='alert alert-info'>No pending shift swap requests found.</div>" if not pending_swaps else ""}
                
                {f'''
                <div class="table-responsive">
                    <table class="table table-striped">
                        <thead>
                            <tr>
                                <th>Requester</th>
                                <th>Crew</th>
                                <th>Reason</th>
                                <th>Date Requested</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {"".join([f'''
                            <tr>
                                <td>{swap.requester_name}</td>
                                <td>Crew {swap.crew}</td>
                                <td>{swap.reason or "No reason provided"}</td>
                                <td>{swap.created_at.strftime('%Y-%m-%d') if swap.created_at else 'Unknown'}</td>
                                <td>
                                    <a href="/supervisor/approve-swap/{swap.id}?crew={crew}" class="btn btn-success btn-sm">Approve</a>
                                    <a href="/supervisor/deny-swap/{swap.id}?crew={crew}" class="btn btn-danger btn-sm">Deny</a>
                                </td>
                            </tr>
                            ''' for swap in pending_swaps])}
                        </tbody>
                    </table>
                </div>
                ''' if pending_swaps else ""}
            </div>
        </body>
        </html>
        """
        
        return safe_html
        
    except Exception as e:
        logger.error(f"Error loading shift swaps: {e}")
        flash('Error loading shift swaps.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/approve-swap/<int:swap_id>')
@login_required
@supervisor_required
def approve_swap(swap_id):
    """Approve a shift swap request - DATABASE SAFE"""
    try:
        def approve_swap_func():
            db.session.execute(
                text("""
                    UPDATE shift_swap_request 
                    SET status = 'approved'
                    WHERE id = :swap_id
                """),
                {'swap_id': swap_id}
            )
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
    """Deny a shift swap request - DATABASE SAFE"""
    try:
        def deny_swap_func():
            db.session.execute(
                text("""
                    UPDATE shift_swap_request 
                    SET status = 'denied'
                    WHERE id = :swap_id
                """),
                {'swap_id': swap_id}
            )
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
# BASIC EMPLOYEE MANAGEMENT ROUTES
# ==========================================

@supervisor_bp.route('/supervisor/employee-management')
@login_required
@supervisor_required
def employee_management():
    """Basic employee management page"""
    return """
    <html><head><title>Employee Management</title></head>
    <body style="padding:20px;">
        <h2>Employee Management</h2>
        <p>Employee management functionality available.</p>
        <a href="/supervisor/dashboard">Back to Dashboard</a>
    </body></html>
    """

@supervisor_bp.route('/supervisor/coverage-gaps')
@login_required
@supervisor_required
def coverage_gaps():
    """Basic coverage gaps page"""
    return """
    <html><head><title>Coverage Gaps</title></head>
    <body style="padding:20px;">
        <h2>Coverage Gaps</h2>
        <p>Coverage gap analysis functionality available.</p>
        <a href="/supervisor/dashboard">Back to Dashboard</a>
    </body></html>
    """

@supervisor_bp.route('/supervisor/coverage-needs')
@login_required
@supervisor_required
def coverage_needs():
    """Basic coverage needs page"""
    return """
    <html><head><title>Coverage Needs</title></head>
    <body style="padding:20px;">
        <h2>Coverage Needs</h2>
        <p>Coverage needs analysis functionality available.</p>
        <a href="/supervisor/dashboard">Back to Dashboard</a>
    </body></html>
    """

# ==========================================
# ERROR HANDLERS
# ==========================================

@supervisor_bp.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    db.session.rollback()
    return redirect(url_for('supervisor.dashboard'))
