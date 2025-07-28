# blueprints/main.py
"""
Fixed main blueprint with proper dashboard routing
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file, current_app
from flask_login import login_required, current_user
from models import db, Employee, Position, OvertimeHistory, TimeOffRequest, ShiftSwapRequest, ScheduleSuggestion
from datetime import date, timedelta, datetime
from sqlalchemy import or_, func
import traceback

# Create the blueprint - MUST be named 'main_bp' to match the import
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Landing page"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    else:
        return redirect(url_for('auth.login'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - route to appropriate dashboard based on user role"""
    try:
        if current_user.is_supervisor:
            # Render supervisor dashboard directly - don't redirect
            # Get statistics for supervisor dashboard
            stats = {
                'pending_time_off': TimeOffRequest.query.filter_by(status='pending').count(),
                'pending_swaps': ShiftSwapRequest.query.filter_by(status='pending').count(),
                'total_employees': Employee.query.filter_by(crew=current_user.crew).count() if current_user.crew else Employee.query.count(),
                'employees_off_today': 0,  # This would need proper calculation
                'coverage_gaps': 0,  # This would need proper calculation
                'pending_suggestions': ScheduleSuggestion.query.filter_by(status='pending').count() if hasattr(ScheduleSuggestion, 'status') else 0,
                'critical_maintenance': 0  # This would need proper calculation
            }
            
            # Check if template exists, otherwise use a simple version
            try:
                return render_template('dashboard.html', **stats)
            except:
                # Fallback if template is missing
                return render_template('supervisor_dashboard_simple.html', **stats)
        else:
            # For regular employees, redirect to employee dashboard
            return redirect(url_for('main.employee_dashboard'))
            
    except Exception as e:
        current_app.logger.error(f"Error in dashboard: {str(e)}\n{traceback.format_exc()}")
        flash(f'Error loading dashboard: {str(e)}', 'danger')
        # Fallback to a simple page
        return redirect(url_for('main.test_dashboard'))

@main_bp.route('/employee-dashboard')
@login_required
def employee_dashboard():
    """Employee dashboard"""
    try:
        # Check if template exists
        try:
            return render_template('employee_dashboard.html')
        except:
            # Simple fallback
            return f"""
            <html>
            <head><title>Employee Dashboard</title></head>
            <body>
                <h1>Employee Dashboard</h1>
                <p>Welcome, {current_user.name}!</p>
                <ul>
                    <li><a href="/vacation/request">Request Time Off</a></li>
                    <li><a href="/shift-marketplace">Shift Marketplace</a></li>
                    <li><a href="/schedule/view">View Schedule</a></li>
                    <li><a href="/auth/logout">Logout</a></li>
                </ul>
            </body>
            </html>
            """
    except Exception as e:
        flash(f'Error loading employee dashboard: {str(e)}', 'danger')
        return redirect(url_for('main.index'))

@main_bp.route('/test-dashboard')
@login_required
def test_dashboard():
    """Test dashboard without redirects"""
    stats = {
        'pending_time_off': TimeOffRequest.query.filter_by(status='pending').count(),
        'pending_swaps': ShiftSwapRequest.query.filter_by(status='pending').count(),
        'total_employees': Employee.query.count(),
        'total_supervisors': Employee.query.filter_by(is_supervisor=True).count()
    }
    
    return f"""
    <html>
    <head>
        <title>Test Dashboard</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .card {{ border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }}
            .card h3 {{ margin-top: 0; color: #11998e; }}
            a {{ color: #11998e; text-decoration: none; padding: 5px 10px; border: 1px solid #11998e; border-radius: 3px; display: inline-block; margin: 5px; }}
            a:hover {{ background-color: #11998e; color: white; }}
        </style>
    </head>
    <body>
        <h1>Workforce Scheduler - Test Dashboard</h1>
        <p>Welcome, {current_user.name}! ({"Supervisor" if current_user.is_supervisor else "Employee"})</p>
        
        <div class="card">
            <h3>Statistics</h3>
            <ul>
                <li>Pending Time Off Requests: {stats['pending_time_off']}</li>
                <li>Pending Shift Swaps: {stats['pending_swaps']}</li>
                <li>Total Employees: {stats['total_employees']}</li>
                <li>Total Supervisors: {stats['total_supervisors']}</li>
            </ul>
        </div>
        
        <div class="card">
            <h3>Quick Actions</h3>
            {"<h4>Supervisor Actions:</h4>" if current_user.is_supervisor else ""}
            {'''
            <a href="/upload-employees">Upload Employees</a>
            <a href="/overtime-management">Overtime Management</a>
            <a href="/supervisor/time-off-requests">Time Off Requests</a>
            <a href="/vacation-calendar">Vacation Calendar</a>
            <a href="/supervisor/coverage-gaps">Coverage Gaps</a>
            ''' if current_user.is_supervisor else ''}
            
            <h4>Employee Actions:</h4>
            <a href="/vacation/request">Request Time Off</a>
            <a href="/shift-marketplace">Shift Marketplace</a>
            <a href="/schedule/view">View Schedule</a>
            
            <h4>Other:</h4>
            <a href="/view-crews">View All Crews</a>
            <a href="/diagnostic">System Diagnostic</a>
            <a href="/auth/logout">Logout</a>
        </div>
    </body>
    </html>
    """

@main_bp.route('/overtime-management')
@login_required
def overtime_management():
    """Overtime management page"""
    # Check if user is supervisor
    if not current_user.is_supervisor:
        flash('You must be a supervisor to access this page.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    try:
        # This should be handled by employee blueprint, but provide fallback
        return redirect(url_for('employee.overtime_management'))
    except:
        # If employee blueprint not available, show simple version
        employees = Employee.query.filter_by(crew=current_user.crew).all()
        return render_template('overtime_management.html', employees=employees)

@main_bp.route('/diagnostic')
@login_required
def diagnostic():
    """System diagnostic page"""
    blueprints = list(current_app.blueprints.keys())
    routes = []
    for rule in current_app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'path': str(rule)
        })
    
    return f"""
    <html>
    <head><title>System Diagnostic</title></head>
    <body>
        <h1>System Diagnostic</h1>
        <h2>Registered Blueprints ({len(blueprints)})</h2>
        <ul>
            {''.join(f'<li>{bp}</li>' for bp in blueprints)}
        </ul>
        <h2>Available Routes ({len(routes)})</h2>
        <ul>
            {''.join(f'<li>{r["path"]} - {r["endpoint"]} ({", ".join(r["methods"])})</li>' for r in sorted(routes, key=lambda x: x["path"]))}
        </ul>
        <p><a href="/">Back to Home</a></p>
    </body>
    </html>
    """

@main_bp.route('/view-crews')
@login_required
def view_crews():
    """View all crews and employees"""
    crews = {}
    employees = Employee.query.order_by(Employee.crew, Employee.name).all()
    
    for employee in employees:
        crew_name = employee.crew or 'Unassigned'
        if crew_name not in crews:
            crews[crew_name] = []
        crews[crew_name].append(employee)
    
    html = """
    <html>
    <head>
        <title>View Crews</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .crew { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
            .crew h3 { margin-top: 0; color: #11998e; }
            .employee { margin: 5px 0; padding: 5px; background: #f5f5f5; }
            .supervisor { font-weight: bold; color: #11998e; }
        </style>
    </head>
    <body>
        <h1>All Crews and Employees</h1>
    """
    
    for crew_name, crew_employees in sorted(crews.items()):
        html += f"""
        <div class="crew">
            <h3>Crew {crew_name} ({len(crew_employees)} employees)</h3>
        """
        for emp in crew_employees:
            supervisor_tag = ' <span class="supervisor">(Supervisor)</span>' if emp.is_supervisor else ''
            html += f'<div class="employee">{emp.name} - {emp.position.name if emp.position else "No Position"}{supervisor_tag}</div>'
        html += '</div>'
    
    html += """
        <p><a href="/dashboard">Back to Dashboard</a></p>
    </body>
    </html>
    """
    
    return html

# API endpoints for any AJAX calls
@main_bp.route('/api/dashboard-stats')
@login_required
def api_dashboard_stats():
    """Get real-time dashboard statistics"""
    try:
        stats = {
            'pending_time_off': TimeOffRequest.query.filter_by(status='pending').count(),
            'pending_swaps': ShiftSwapRequest.query.filter_by(status='pending').count(),
            'coverage_gaps': 0,
            'pending_suggestions': ScheduleSuggestion.query.filter_by(status='pending').count() if hasattr(ScheduleSuggestion, 'status') else 0,
            'new_critical_items': 0
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify({
            'pending_time_off': 0,
            'pending_swaps': 0,
            'coverage_gaps': 0,
            'pending_suggestions': 0,
            'new_critical_items': 0,
            'error': str(e)
        })

# Error handlers
@main_bp.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@main_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500
