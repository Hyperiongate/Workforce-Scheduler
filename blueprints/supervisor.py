# blueprints/supervisor.py
"""
Supervisor blueprint with robust error handling and proper session management
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from models import db, Employee, TimeOffRequest, ShiftSwapRequest, Schedule, Position, OvertimeHistory, PositionCoverage, VacationCalendar
from datetime import date, datetime, timedelta
from sqlalchemy import func, and_, or_, inspect
from sqlalchemy.orm import joinedload, selectinload
from functools import wraps
import traceback
import pandas as pd
import os

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

def safe_query(query_func, default=None, error_msg="Query failed"):
    """
    Safely execute a query function with error handling
    Returns default value if query fails
    """
    try:
        return query_func()
    except Exception as e:
        current_app.logger.error(f"{error_msg}: {e}")
        db.session.rollback()
        return default

@supervisor_bp.route('/supervisor/dashboard')
@login_required
@supervisor_required
def dashboard():
    """Supervisor dashboard with robust error handling and proper session management"""
    try:
        # Ensure we have a fresh session
        db.session.commit()  # Commit any pending changes
        db.session.close()   # Close the session
        
        # Re-query current user within this request context to avoid detached instance
        current_user_id = current_user.id
        user = db.session.query(Employee).filter_by(id=current_user_id).first()
        
        if not user:
            flash('User session error. Please log in again.', 'danger')
            return redirect(url_for('auth.logout'))
        
        # Initialize context with all required variables
        context = {
            # Basic stats
            'pending_time_off': 0,
            'pending_swaps': 0,
            'total_employees': 0,
            'coverage_gaps': 0,
            
            # Additional stats for template
            'employees_missing_ot': 0,
            'high_ot_employees': [],
            'recent_time_off': [],
            'employees_on_leave_today': 0,
            'recent_activities': [],
            
            # User info - use the fresh user object
            'current_user': user,
            'user_name': user.name,
            'today': date.today(),
            'now': datetime.now()
        }
        
        # Get pending time off requests
        context['pending_time_off'] = safe_query(
            lambda: TimeOffRequest.query.filter_by(status='pending').count(),
            default=0,
            error_msg="Error counting pending time off"
        )
        
        # Get pending swaps - with proper error handling
        context['pending_swaps'] = safe_query(
            lambda: ShiftSwapRequest.query.filter_by(status='pending').count(),
            default=0,
            error_msg="Error counting pending swaps"
        )
        
        # Get employee statistics
        all_employees = safe_query(
            lambda: Employee.query.filter_by(is_supervisor=False).all(),
            default=[],
            error_msg="Error loading employees"
        )
        
        context['total_employees'] = len(all_employees)
        
        # Count employees missing OT data
        if all_employees:
            employees_with_ot = safe_query(
                lambda: set(
                    db.session.query(OvertimeHistory.employee_id)
                    .distinct()
                    .scalar_subquery()
                ),
                default=set(),
                error_msg="Error checking OT data"
            )
            
            context['employees_missing_ot'] = len([
                emp for emp in all_employees 
                if emp.id not in employees_with_ot
            ])
        
        # Get high OT employees with proper joins
        week_start = date.today() - timedelta(days=date.today().weekday())
        high_ot_result = safe_query(
            lambda: db.session.query(Employee)
            .join(OvertimeHistory)
            .filter(
                OvertimeHistory.week_start_date == week_start,
                OvertimeHistory.overtime_hours > 10
            )
            .options(selectinload(Employee.position))
            .all(),
            default=[],
            error_msg="Error loading high OT employees"
        )
        
        context['high_ot_employees'] = high_ot_result
        
        # Get recent time off requests with eager loading
        context['recent_time_off'] = safe_query(
            lambda: TimeOffRequest.query
            .options(joinedload(TimeOffRequest.employee))
            .order_by(TimeOffRequest.created_at.desc())
            .limit(5)
            .all(),
            default=[],
            error_msg="Error loading recent time off"
        )
        
        # Calculate coverage gaps
        today = date.today()
        scheduled_today = safe_query(
            lambda: Schedule.query.filter_by(date=today).count(),
            default=0,
            error_msg="Error counting today's schedule"
        )
        
        # Get required coverage
        required_coverage = safe_query(
            lambda: db.session.query(func.sum(Position.min_coverage)).scalar() or 0,
            default=20,  # Default minimum if query fails
            error_msg="Error calculating required coverage"
        )
        
        context['coverage_gaps'] = max(0, required_coverage - scheduled_today)
        
        # Try to render appropriate template
        template_names = [
            'supervisor_dashboard.html',
            'dashboard_classic.html',
            'supervisor_dashboard_simple.html',
            'basic_dashboard.html'
        ]
        
        for template_name in template_names:
            try:
                return render_template(template_name, **context)
            except Exception as e:
                current_app.logger.debug(f"Template {template_name} not found: {e}")
                continue
        
        # If no template works, provide a functional fallback
        return render_dashboard_fallback(context)
        
    except Exception as e:
        current_app.logger.error(f"Critical error in supervisor dashboard: {e}")
        current_app.logger.error(traceback.format_exc())
        
        # Clean up the session
        db.session.rollback()
        db.session.close()
        
        flash('An error occurred loading the dashboard. Please try again.', 'danger')
        return redirect(url_for('main.home') if 'main' in current_app.blueprints else '/')

def render_dashboard_fallback(context):
    """Render a functional dashboard when templates are missing"""
    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Supervisor Dashboard - Workforce Scheduler</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.7.2/font/bootstrap-icons.css">
    <style>
        body { background-color: #f5f7fa; }
        .stat-card {
            background: white;
            border-radius: 10px;
            padding: 1.5rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }
        .stat-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        }
        .stat-value {
            font-size: 2.5rem;
            font-weight: bold;
            color: #11998e;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="/">
                <i class="bi bi-calendar3"></i> Workforce Scheduler
            </a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/auth/logout">
                    <i class="bi bi-box-arrow-right"></i> Logout
                </a>
            </div>
        </div>
    </nav>
    
    <div class="container mt-4">
        <h1 class="mb-4">Supervisor Dashboard</h1>
        <p class="lead">Welcome, {{ user_name }}!</p>
        
        <!-- Statistics -->
        <div class="row mb-4">
            <div class="col-md-3 mb-3">
                <div class="stat-card text-center">
                    <i class="bi bi-calendar-x fs-1 text-primary mb-2"></i>
                    <div class="stat-value">{{ pending_time_off }}</div>
                    <div class="text-muted">Pending Time Off</div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="stat-card text-center">
                    <i class="bi bi-arrow-left-right fs-1 text-info mb-2"></i>
                    <div class="stat-value">{{ pending_swaps }}</div>
                    <div class="text-muted">Pending Swaps</div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="stat-card text-center">
                    <i class="bi bi-people fs-1 text-success mb-2"></i>
                    <div class="stat-value">{{ total_employees }}</div>
                    <div class="text-muted">Total Employees</div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="stat-card text-center">
                    <i class="bi bi-exclamation-circle fs-1 text-warning mb-2"></i>
                    <div class="stat-value">{{ coverage_gaps }}</div>
                    <div class="text-muted">Coverage Gaps</div>
                </div>
            </div>
        </div>
        
        <!-- Quick Actions -->
        <div class="row">
            <div class="col-md-6">
                <div class="card mb-4">
                    <div class="card-header bg-primary text-white">
                        <h5 class="mb-0"><i class="bi bi-lightning"></i> Quick Actions</h5>
                    </div>
                    <div class="list-group list-group-flush">
                        <a href="/supervisor/time-off-requests" class="list-group-item list-group-item-action">
                            <i class="bi bi-calendar-check text-primary"></i> Review Time Off Requests
                            {% if pending_time_off > 0 %}
                                <span class="badge bg-danger float-end">{{ pending_time_off }}</span>
                            {% endif %}
                        </a>
                        <a href="/supervisor/swap-requests" class="list-group-item list-group-item-action">
                            <i class="bi bi-shuffle text-info"></i> Review Shift Swaps
                            {% if pending_swaps > 0 %}
                                <span class="badge bg-danger float-end">{{ pending_swaps }}</span>
                            {% endif %}
                        </a>
                        <a href="/schedule/view" class="list-group-item list-group-item-action">
                            <i class="bi bi-calendar3 text-success"></i> View Schedule
                        </a>
                        <a href="/supervisor/coverage-gaps" class="list-group-item list-group-item-action">
                            <i class="bi bi-exclamation-triangle text-warning"></i> Coverage Analysis
                        </a>
                    </div>
                </div>
            </div>
            
            <div class="col-md-6">
                <div class="card mb-4">
                    <div class="card-header bg-success text-white">
                        <h5 class="mb-0"><i class="bi bi-database"></i> Data Management</h5>
                    </div>
                    <div class="list-group list-group-flush">
                        <a href="/upload-employees" class="list-group-item list-group-item-action">
                            <i class="bi bi-upload text-primary"></i> Upload Employee Data
                            {% if employees_missing_ot > 0 %}
                                <span class="badge bg-warning float-end">{{ employees_missing_ot }} missing OT</span>
                            {% endif %}
                        </a>
                        <a href="/upload-overtime" class="list-group-item list-group-item-action">
                            <i class="bi bi-clock-history text-info"></i> Upload Overtime History
                        </a>
                        <a href="/upload-history" class="list-group-item list-group-item-action">
                            <i class="bi bi-journal-text text-secondary"></i> View Upload History
                        </a>
                        <a href="/supervisor/employee-management" class="list-group-item list-group-item-action">
                            <i class="bi bi-people-fill text-success"></i> Employee Management
                        </a>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Recent Activity -->
        {% if recent_time_off %}
        <div class="card">
            <div class="card-header">
                <h5 class="mb-0"><i class="bi bi-activity"></i> Recent Time Off Requests</h5>
            </div>
            <div class="table-responsive">
                <table class="table table-hover mb-0">
                    <thead>
                        <tr>
                            <th>Employee</th>
                            <th>Type</th>
                            <th>Dates</th>
                            <th>Status</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for request in recent_time_off[:5] %}
                        <tr>
                            <td>{{ request.employee.name }}</td>
                            <td>{{ request.request_type|title }}</td>
                            <td>{{ request.start_date.strftime('%b %d') }} - {{ request.end_date.strftime('%b %d') }}</td>
                            <td>
                                <span class="badge bg-{{ 'warning' if request.status == 'pending' else 'success' }}">
                                    {{ request.status|title }}
                                </span>
                            </td>
                            <td>
                                <a href="/supervisor/time-off-requests" class="btn btn-sm btn-primary">View</a>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        {% endif %}
        
        <!-- High OT Alert -->
        {% if high_ot_employees %}
        <div class="alert alert-warning mt-4" role="alert">
            <h5 class="alert-heading"><i class="bi bi-exclamation-triangle"></i> High Overtime Alert</h5>
            <p>The following employees have worked more than 10 hours of overtime this week:</p>
            <ul class="mb-0">
                {% for emp in high_ot_employees %}
                <li>{{ emp.name }} - {{ emp.crew }} Crew</li>
                {% endfor %}
            </ul>
        </div>
        {% endif %}
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
    ''', **context)

# Continue with the rest of the routes, all using the safe_query pattern...

@supervisor_bp.route('/supervisor/time-off-requests')
@login_required
@supervisor_required
def time_off_requests():
    """View and manage time off requests with proper error handling"""
    try:
        # Ensure clean session
        db.session.commit()
        
        # Get filter parameters
        status_filter = request.args.get('status', 'all')
        crew_filter = request.args.get('crew', 'all')
        
        # Build query with eager loading
        query = TimeOffRequest.query.options(
            joinedload(TimeOffRequest.employee),
            joinedload(TimeOffRequest.approver)
        )
        
        # Apply filters
        if status_filter != 'all':
            query = query.filter_by(status=status_filter)
        
        if crew_filter != 'all':
            query = query.join(Employee).filter(Employee.crew == crew_filter)
        
        # Get requests
        requests = safe_query(
            lambda: query.order_by(TimeOffRequest.created_at.desc()).all(),
            default=[],
            error_msg="Error loading time off requests"
        )
        
        # Get statistics
        stats = {
            'pending_count': safe_query(
                lambda: TimeOffRequest.query.filter_by(status='pending').count(),
                default=0
            ),
            'approved_this_week': safe_query(
                lambda: TimeOffRequest.query.filter(
                    TimeOffRequest.status == 'approved',
                    TimeOffRequest.created_at >= datetime.now() - timedelta(days=7)
                ).count(),
                default=0
            ),
            'total_days_requested': safe_query(
                lambda: db.session.query(
                    func.sum(
                        func.julianday(TimeOffRequest.end_date) - 
                        func.julianday(TimeOffRequest.start_date) + 1
                    )
                ).filter_by(status='pending').scalar() or 0,
                default=0
            )
        }
        
        return render_template('time_off_requests.html', 
                             requests=requests,
                             stats=stats,
                             status_filter=status_filter,
                             crew_filter=crew_filter)
    
    except Exception as e:
        current_app.logger.error(f"Error in time_off_requests: {e}")
        db.session.rollback()
        flash('Error loading time off requests.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/approve-time-off/<int:request_id>')
@login_required
@supervisor_required
def approve_time_off(request_id):
    """Approve a time off request"""
    try:
        time_off = TimeOffRequest.query.get_or_404(request_id)
        
        if time_off.status != 'pending':
            flash('This request has already been processed.', 'warning')
            return redirect(url_for('supervisor.time_off_requests'))
        
        # Update the request
        time_off.status = 'approved'
        time_off.approved_by_id = current_user.id
        time_off.approved_date = datetime.now()
        
        # Create vacation calendar entries for each day
        current_date = time_off.start_date
        while current_date <= time_off.end_date:
            # Check if entry already exists
            existing = VacationCalendar.query.filter_by(
                employee_id=time_off.employee_id,
                date=current_date
            ).first()
            
            if not existing:
                vacation_entry = VacationCalendar(
                    employee_id=time_off.employee_id,
                    date=current_date,
                    request_id=time_off.id,
                    type=time_off.request_type,
                    status='approved'
                )
                db.session.add(vacation_entry)
            
            current_date += timedelta(days=1)
        
        db.session.commit()
        flash(f'Time off request for {time_off.employee.name} has been approved.', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error approving time off: {e}")
        flash('Error approving request.', 'danger')
    
    return redirect(url_for('supervisor.time_off_requests'))

# Add the rest of the routes with similar safe_query pattern and proper session management...
# (I can continue with the rest if needed, but this shows the robust pattern)

# Import render_template_string for fallback rendering
from flask import render_template_string
