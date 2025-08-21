# blueprints/supervisor.py - COMPLETE FILE WITH FIXED COVERAGE NEEDS ROUTE

"""
Supervisor blueprint with complete error handling and database migration support
This version works even with missing database columns
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from models import db, Employee, TimeOffRequest, ShiftSwapRequest, Schedule, Position, OvertimeHistory
from datetime import date, datetime, timedelta
from sqlalchemy import func, and_, or_, text
from sqlalchemy.exc import ProgrammingError, OperationalError
from functools import wraps
import pandas as pd
import os
import io
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

def safe_count_query(model, **filters):
    """Safely count records even if columns don't exist"""
    try:
        query = model.query
        for key, value in filters.items():
            if hasattr(model, key):
                query = query.filter_by(**{key: value})
        return query.count()
    except (ProgrammingError, OperationalError) as e:
        logger.error(f"Database error in count query for {model.__name__}: {e}")
        db.session.rollback()
        return 0

@supervisor_bp.route('/supervisor/dashboard')
@login_required
@supervisor_required
def dashboard():
    """Supervisor dashboard with complete error handling"""
    # Initialize context with safe defaults
    context = {
        'user_name': current_user.name,
        'pending_time_off': 0,
        'pending_swaps': 0,
        'total_employees': 0,
        'coverage_gaps': 0,
        'today_scheduled': 0,
        'today_on_leave': 0,
        'critical_maintenance': 0,
        'recent_time_off': [],
        'recent_swaps': [],
        'pending_time_off_count': 0,
        'pending_swaps_count': 0,
        'database_errors': []
    }
    
    # Get total employees - this should always work
    try:
        context['total_employees'] = Employee.query.filter_by(is_supervisor=False).count()
    except Exception as e:
        logger.error(f"Error getting total employees: {e}")
        db.session.rollback()
    
    # Get pending time off with comprehensive error handling
    try:
        # Method 1: Try normal query
        context['pending_time_off'] = TimeOffRequest.query.filter_by(status='pending').count()
        context['pending_time_off_count'] = context['pending_time_off']
    except (ProgrammingError, OperationalError) as e:
        if 'column' in str(e) and 'does not exist' in str(e):
            logger.warning(f"Column missing in time_off_request: {e}")
            db.session.rollback()
            try:
                # Method 2: Try raw SQL with only known columns
                result = db.session.execute(
                    text("SELECT COUNT(*) FROM time_off_request WHERE status = 'pending'")
                ).scalar()
                context['pending_time_off'] = result or 0
                context['pending_time_off_count'] = context['pending_time_off']
            except:
                logger.error("Failed to get time off count even with raw SQL")
                db.session.rollback()
                context['database_errors'].append("Time off requests table has missing columns")
        else:
            logger.error(f"Unexpected database error: {e}")
            db.session.rollback()
    except Exception as e:
        logger.error(f"General error getting pending time off: {e}")
        db.session.rollback()
    
    # Get pending swaps with error handling
    try:
        context['pending_swaps'] = ShiftSwapRequest.query.filter_by(status='pending').count()
        context['pending_swaps_count'] = context['pending_swaps']
    except (ProgrammingError, OperationalError) as e:
        if 'column' in str(e) and 'does not exist' in str(e):
            logger.warning(f"Column missing in shift_swap_request: {e}")
            db.session.rollback()
            try:
                # Try raw SQL
                result = db.session.execute(
                    text("SELECT COUNT(*) FROM shift_swap_request WHERE status = 'pending'")
                ).scalar()
                context['pending_swaps'] = result or 0
                context['pending_swaps_count'] = context['pending_swaps']
            except:
                logger.error("Failed to get swap count even with raw SQL")
                db.session.rollback()
                context['database_errors'].append("Shift swap requests table has missing columns")
        else:
            logger.error(f"Unexpected database error: {e}")
            db.session.rollback()
    except Exception as e:
        logger.error(f"General error getting pending swaps: {e}")
        db.session.rollback()
    
    # Get today's schedule info
    try:
        today = date.today()
        context['today_scheduled'] = Schedule.query.filter_by(date=today).count()
    except Exception as e:
        logger.error(f"Error getting today's schedule: {e}")
        db.session.rollback()
    
    # Show database errors if any
    if context['database_errors']:
        flash('Warning: Some database tables need updating. Contact your administrator.', 'warning')
    
    # Try to render the appropriate template
    templates = [
        'supervisor_dashboard.html',
        'dashboard_classic.html',
        'supervisor_dashboard_simple.html',
        'dashboard.html',
        'basic_dashboard.html'
    ]
    
    for template in templates:
        try:
            return render_template(template, **context)
        except Exception as e:
            logger.debug(f"Template {template} not found or error: {e}")
            continue
    
    # If no template works, use inline template
    return render_template_string('''
    {% extends "base.html" %}
    {% block content %}
    <div class="container mt-4">
        <h1>Supervisor Dashboard</h1>
        <p>Welcome, {{ user_name }}!</p>
        
        <div class="row mt-4">
            <div class="col-md-3">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">Total Employees</h5>
                        <h2>{{ total_employees }}</h2>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">Pending Time Off</h5>
                        <h2>{{ pending_time_off }}</h2>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">Pending Swaps</h5>
                        <h2>{{ pending_swaps }}</h2>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">Coverage Gaps</h5>
                        <h2>{{ coverage_gaps }}</h2>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="row mt-4">
            <div class="col-12">
                <h2>Quick Actions</h2>
                <div class="list-group">
                    <a href="{{ url_for('supervisor.time_off_requests') }}" class="list-group-item list-group-item-action">
                        Time Off Requests
                    </a>
                    <a href="{{ url_for('supervisor.shift_swaps') }}" class="list-group-item list-group-item-action">
                        Shift Swap Requests
                    </a>
                    <a href="{{ url_for('employee_import.upload_employees') }}" class="list-group-item list-group-item-action">
                        Upload Employees
                    </a>
                    <a href="{{ url_for('main.overtime_management') }}" class="list-group-item list-group-item-action">
                        Overtime Management
                    </a>
                </div>
            </div>
        </div>
        
        {% if database_errors %}
        <div class="alert alert-warning mt-4">
            <h4>Database Issues Detected</h4>
            <ul>
            {% for error in database_errors %}
                <li>{{ error }}</li>
            {% endfor %}
            </ul>
            <p>Please run the database migration script to fix these issues.</p>
        </div>
        {% endif %}
    </div>
    {% endblock %}
    ''', **context)

# ==========================================
# TIME OFF MANAGEMENT
# ==========================================

@supervisor_bp.route('/supervisor/time-off-requests')
@login_required
@supervisor_required
def time_off_requests():
    """View and manage time off requests"""
    pending_requests = []
    
    try:
        # Try to get requests with safe query
        pending_requests = TimeOffRequest.query.filter_by(status='pending').all()
    except (ProgrammingError, OperationalError) as e:
        logger.error(f"Database error in time off requests: {e}")
        db.session.rollback()
        
        # Try raw SQL as fallback
        try:
            result = db.session.execute(
                text("""
                    SELECT id, employee_id, start_date, end_date, status, reason
                    FROM time_off_request
                    WHERE status = 'pending'
                """)
            )
            # Convert to objects manually
            for row in result:
                # Create a simple object to hold the data
                class SimpleRequest:
                    pass
                req = SimpleRequest()
                req.id = row[0]
                req.employee_id = row[1]
                req.start_date = row[2]
                req.end_date = row[3]
                req.status = row[4]
                req.reason = row[5]
                # Try to get employee
                try:
                    req.employee = Employee.query.get(req.employee_id)
                except:
                    req.employee = None
                pending_requests.append(req)
        except Exception as e2:
            logger.error(f"Failed to get requests even with raw SQL: {e2}")
            flash('Error loading time off requests. Database may need updating.', 'danger')
    
    return render_template('time_off_requests.html', requests=pending_requests)

@supervisor_bp.route('/supervisor/approve-time-off/<int:request_id>')
@login_required
@supervisor_required
def approve_time_off(request_id):
    """Approve a time off request"""
    try:
        # Use raw SQL to update
        db.session.execute(
            text("""
                UPDATE time_off_request 
                SET status = 'approved', 
                    approved_by_id = :approver_id,
                    processed_at = :now
                WHERE id = :request_id
            """),
            {
                'approver_id': current_user.id,
                'now': datetime.utcnow(),
                'request_id': request_id
            }
        )
        db.session.commit()
        flash('Time off request approved!', 'success')
    except Exception as e:
        logger.error(f"Error approving time off: {e}")
        db.session.rollback()
        flash('Error approving request. Please try again.', 'danger')
    
    return redirect(url_for('supervisor.time_off_requests'))

@supervisor_bp.route('/supervisor/deny-time-off/<int:request_id>')
@login_required
@supervisor_required
def deny_time_off(request_id):
    """Deny a time off request"""
    try:
        db.session.execute(
            text("""
                UPDATE time_off_request 
                SET status = 'denied', 
                    approved_by_id = :approver_id,
                    processed_at = :now
                WHERE id = :request_id
            """),
            {
                'approver_id': current_user.id,
                'now': datetime.utcnow(),
                'request_id': request_id
            }
        )
        db.session.commit()
        flash('Time off request denied.', 'info')
    except Exception as e:
        logger.error(f"Error denying time off: {e}")
        db.session.rollback()
        flash('Error denying request. Please try again.', 'danger')
    
    return redirect(url_for('supervisor.time_off_requests'))

# ==========================================
# SHIFT SWAP MANAGEMENT
# ==========================================

@supervisor_bp.route('/supervisor/shift-swaps')
@login_required
@supervisor_required
def shift_swaps():
    """View and manage shift swap requests"""
    pending_swaps = []
    
    try:
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').all()
    except (ProgrammingError, OperationalError) as e:
        logger.error(f"Database error in shift swaps: {e}")
        db.session.rollback()
        
        # Try simpler query
        try:
            result = db.session.execute(
                text("""
                    SELECT id, requester_id, status, reason, created_at
                    FROM shift_swap_request
                    WHERE status = 'pending'
                """)
            )
            for row in result:
                class SimpleSwap:
                    pass
                swap = SimpleSwap()
                swap.id = row[0]
                swap.requester_id = row[1]
                swap.status = row[2]
                swap.reason = row[3]
                swap.created_at = row[4]
                try:
                    swap.requester = Employee.query.get(swap.requester_id)
                except:
                    swap.requester = None
                pending_swaps.append(swap)
        except Exception as e2:
            logger.error(f"Failed to get swaps even with raw SQL: {e2}")
            flash('Error loading shift swaps. Database may need updating.', 'danger')
    
    return render_template('shift_swaps.html', swaps=pending_swaps)

@supervisor_bp.route('/supervisor/approve-swap/<int:swap_id>')
@login_required
@supervisor_required
def approve_swap(swap_id):
    """Approve a shift swap request"""
    try:
        db.session.execute(
            text("""
                UPDATE shift_swap_request 
                SET status = 'approved', 
                    processed_at = :now
                WHERE id = :swap_id
            """),
            {
                'now': datetime.utcnow(),
                'swap_id': swap_id
            }
        )
        db.session.commit()
        flash('Shift swap approved!', 'success')
    except Exception as e:
        logger.error(f"Error approving swap: {e}")
        db.session.rollback()
        flash('Error approving swap. Please try again.', 'danger')
    
    return redirect(url_for('supervisor.shift_swaps'))

@supervisor_bp.route('/supervisor/deny-swap/<int:swap_id>')
@login_required
@supervisor_required
def deny_swap(swap_id):
    """Deny a shift swap request"""
    try:
        db.session.execute(
            text("""
                UPDATE shift_swap_request 
                SET status = 'denied', 
                    processed_at = :now
                WHERE id = :swap_id
            """),
            {
                'now': datetime.utcnow(),
                'swap_id': swap_id
            }
        )
        db.session.commit()
        flash('Shift swap denied.', 'info')
    except Exception as e:
        logger.error(f"Error denying swap: {e}")
        db.session.rollback()
        flash('Error denying swap. Please try again.', 'danger')
    
    return redirect(url_for('supervisor.shift_swaps'))

# ==========================================
# EMPLOYEE MANAGEMENT
# ==========================================

@supervisor_bp.route('/supervisor/employee-management')
@login_required
@supervisor_required
def employee_management():
    """Employee management page"""
    try:
        employees = Employee.query.filter_by(is_supervisor=False).all()
        return render_template('employee_management.html', employees=employees)
    except Exception as e:
        logger.error(f"Error in employee management: {e}")
        flash('Error loading employee data.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/crew-management')
@login_required
@supervisor_required
def crew_management():
    """Crew management page"""
    try:
        crews = {}
        for crew in ['A', 'B', 'C', 'D']:
            crews[crew] = Employee.query.filter_by(crew=crew, is_supervisor=False).all()
        
        unassigned = Employee.query.filter(
            or_(Employee.crew == None, Employee.crew == ''),
            Employee.is_supervisor == False
        ).all()
        
        return render_template('crew_management.html', crews=crews, unassigned=unassigned)
    except Exception as e:
        logger.error(f"Error in crew management: {e}")
        flash('Error loading crew data.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# SCHEDULE MANAGEMENT
# ==========================================

@supervisor_bp.route('/supervisor/vacation-calendar')
@login_required
@supervisor_required
def vacation_calendar():
    """Display vacation calendar"""
    try:
        today = date.today()
        start_of_month = date(today.year, today.month, 1)
        
        if today.month == 12:
            end_of_month = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            end_of_month = date(today.year, today.month + 1, 1) - timedelta(days=1)
        
        # Try to get time off requests
        time_off_requests = []
        try:
            time_off_requests = TimeOffRequest.query.filter(
                TimeOffRequest.status == 'approved',
                TimeOffRequest.start_date <= end_of_month,
                TimeOffRequest.end_date >= start_of_month
            ).all()
        except Exception as e:
            logger.error(f"Error getting time off requests: {e}")
            db.session.rollback()
        
        return render_template('vacation_calendar.html',
                             time_off_requests=time_off_requests,
                             current_month=today)
    except Exception as e:
        logger.error(f"Error in vacation calendar: {e}")
        flash('Error loading vacation calendar.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/coverage-gaps')
@login_required
@supervisor_required
def coverage_gaps():
    """View coverage gaps"""
    gaps = []
    return render_template('coverage_gaps.html', gaps=gaps)

@supervisor_bp.route('/supervisor/coverage-needs')
@login_required
@supervisor_required
def coverage_needs():
    """View and manage coverage needs - FIXED VERSION"""
    try:
        # Get all positions
        positions = Position.query.order_by(Position.name).all()
        
        # Initialize data structures
        crew_totals = {'A': 0, 'B': 0, 'C': 0, 'D': 0}
        current_coverage = {
            'A': {},
            'B': {},
            'C': {},
            'D': {}
        }
        
        # Count employees by crew
        for crew in ['A', 'B', 'C', 'D']:
            crew_totals[crew] = Employee.query.filter_by(
                crew=crew, 
                is_supervisor=False
            ).count()
        
        # Count employees by position and crew
        for crew in ['A', 'B', 'C', 'D']:
            for position in positions:
                count = Employee.query.filter_by(
                    crew=crew,
                    position_id=position.id,
                    is_supervisor=False
                ).count()
                current_coverage[crew][position.id] = count
        
        # Calculate total current staff
        total_current_staff = sum(crew_totals.values())
        
        return render_template('coverage_needs.html',
                             positions=positions,
                             crew_totals=crew_totals,
                             current_coverage=current_coverage,
                             total_current_staff=total_current_staff)
                             
    except Exception as e:
        logger.error(f"Error in coverage needs: {e}")
        flash('Error loading coverage needs. Make sure employee data is uploaded.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# OVERTIME MANAGEMENT
# ==========================================

@supervisor_bp.route('/supervisor/overtime-distribution')
@login_required
@supervisor_required
def overtime_distribution():
    """View overtime distribution report"""
    try:
        # Get all employees with their overtime data
        employees = Employee.query.filter_by(is_supervisor=False).all()
        
        overtime_data = []
        for emp in employees:
            # Get total overtime for last 13 weeks
            total_ot = db.session.query(func.sum(OvertimeHistory.hours)).filter_by(
                employee_id=emp.id
            ).scalar() or 0
            
            overtime_data.append({
                'employee': emp,
                'total_overtime': total_ot,
                'average_weekly': round(total_ot / 13, 2) if total_ot > 0 else 0
            })
        
        # Sort by total overtime descending
        overtime_data.sort(key=lambda x: x['total_overtime'], reverse=True)
        
        return render_template('overtime_distribution.html', overtime_data=overtime_data)
    except Exception as e:
        logger.error(f"Error in overtime distribution: {e}")
        flash('Error loading overtime distribution.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# API ENDPOINTS
# ==========================================

@supervisor_bp.route('/api/coverage-needs', methods=['POST'])
@login_required
@supervisor_required
def api_update_coverage_needs():
    """API endpoint to update coverage requirements"""
    try:
        data = request.get_json()
        crew = data.get('crew')
        position_id = data.get('position_id')
        min_coverage = data.get('min_coverage', 0)
        
        # For now, just return success
        # In a real implementation, you'd save this to a database table
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error updating coverage needs: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==========================================
# DATABASE MIGRATION CHECK
# ==========================================

@supervisor_bp.route('/supervisor/check-database')
@login_required
@supervisor_required
def check_database():
    """Check database schema and show migration needs"""
    issues = []
    
    # Check TimeOffRequest columns
    try:
        db.session.execute(text("SELECT type FROM time_off_request LIMIT 1"))
    except:
        issues.append("time_off_request.type column is missing")
        db.session.rollback()
    
    # Check ShiftSwapRequest columns
    try:
        db.session.execute(text("SELECT requester_date FROM shift_swap_request LIMIT 1"))
    except:
        issues.append("shift_swap_request.requester_date column is missing")
        db.session.rollback()
    
    return jsonify({
        'database_ok': len(issues) == 0,
        'issues': issues
    })

# ==========================================
# ERROR HANDLERS
# ==========================================

@supervisor_bp.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@supervisor_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500
