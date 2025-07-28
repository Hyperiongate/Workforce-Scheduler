# blueprints/main.py
"""
Diagnostic version of main blueprint to identify and bypass redirect issues
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file, current_app
from flask_login import login_required, current_user
from models import db, Employee, Position, OvertimeHistory
from datetime import date, timedelta, datetime
from sqlalchemy import or_, func
import traceback

# Create the blueprint - MUST be named 'main_bp' to match the import
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Landing page - NO REDIRECT"""
    try:
        # Don't redirect, just show a simple page
        if current_user.is_authenticated:
            return f"""
            <html>
            <head><title>Workforce Scheduler</title></head>
            <body>
                <h1>Workforce Scheduler - Home</h1>
                <p>Welcome, {current_user.name}!</p>
                <p>User ID: {current_user.id}</p>
                <p>Is Supervisor: {current_user.is_supervisor}</p>
                <p>Crew: {current_user.crew or 'None'}</p>
                <hr>
                <h2>Available Routes:</h2>
                <ul>
                    <li><a href="/test-dashboard">Test Dashboard (No redirect)</a></li>
                    <li><a href="/overtime-management">Overtime Management</a></li>
                    <li><a href="/employees/crew-management">Crew Management</a></li>
                    <li><a href="/upload-employees">Upload Employees</a></li>
                    <li><a href="/view-crews">View Crews</a></li>
                    <li><a href="/diagnostic">System Diagnostic</a></li>
                </ul>
            </body>
            </html>
            """
        else:
            return """
            <html>
            <head><title>Workforce Scheduler</title></head>
            <body>
                <h1>Workforce Scheduler</h1>
                <p>Please <a href="/auth/login">login</a> to continue.</p>
            </body>
            </html>
            """
    except Exception as e:
        return f"Error in index: {str(e)}<br><pre>{traceback.format_exc()}</pre>", 500

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - DIAGNOSTIC VERSION"""
    try:
        # Log the attempt
        current_app.logger.info(f"Dashboard accessed by user: {current_user.id}")
        
        # Don't redirect, show diagnostic info
        return f"""
        <html>
        <head><title>Dashboard Diagnostic</title></head>
        <body>
            <h1>Dashboard Diagnostic</h1>
            <p>This is the dashboard route that's causing issues.</p>
            <h2>Current User Info:</h2>
            <ul>
                <li>ID: {current_user.id}</li>
                <li>Name: {current_user.name}</li>
                <li>Email: {current_user.email}</li>
                <li>Is Supervisor: {current_user.is_supervisor}</li>
                <li>Crew: {current_user.crew or 'None'}</li>
            </ul>
            <h2>Available Blueprints:</h2>
            <ul>
                <li>supervisor.dashboard exists: {'supervisor.dashboard' in current_app.view_functions}</li>
                <li>main.employee_dashboard exists: {'main.employee_dashboard' in current_app.view_functions}</li>
            </ul>
            <h2>Options:</h2>
            <ul>
                <li><a href="/test-dashboard">Go to Test Dashboard</a></li>
                <li><a href="/employee-dashboard">Try Employee Dashboard</a></li>
                <li><a href="/">Back to Home</a></li>
            </ul>
        </body>
        </html>
        """
    except Exception as e:
        current_app.logger.error(f"Error in dashboard: {str(e)}\n{traceback.format_exc()}")
        return f"Dashboard Error: {str(e)}<br><pre>{traceback.format_exc()}</pre>", 500

@main_bp.route('/test-dashboard')
@login_required
def test_dashboard():
    """Test dashboard without redirects"""
    return f"""
    <html>
    <head>
        <title>Test Dashboard</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .card {{ border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }}
            .card h3 {{ margin-top: 0; color: #11998e; }}
            a {{ color: #11998e; text-decoration: none; padding: 5px 10px; border: 1px solid #11998e; border-radius: 3px; display: inline-block; margin: 5px; }}
            a:hover {{ background: #11998e; color: white; }}
        </style>
    </head>
    <body>
        <h1>Workforce Scheduler - Test Dashboard</h1>
        <p>Welcome, {current_user.name}!</p>
        
        <div class="card">
            <h3>User Information</h3>
            <ul>
                <li>Employee ID: {current_user.employee_id or 'Not set'}</li>
                <li>Email: {current_user.email}</li>
                <li>Crew: {current_user.crew or 'Not assigned'}</li>
                <li>Role: {'Supervisor' if current_user.is_supervisor else 'Employee'}</li>
            </ul>
        </div>
        
        <div class="card">
            <h3>Quick Links</h3>
            <a href="/overtime-management">Overtime Management</a>
            <a href="/employees/crew-management">Crew Management</a>
            <a href="/upload-employees">Upload Employees</a>
            <a href="/view-crews">View Crews</a>
            <a href="/auth/logout">Logout</a>
        </div>
        
        <div class="card">
            <h3>Debug Information</h3>
            <p>Current Time: {datetime.now()}</p>
            <p>Database Connected: {'Yes' if db else 'No'}</p>
        </div>
    </body>
    </html>
    """

@main_bp.route('/employee-dashboard')
@login_required
def employee_dashboard():
    """Employee dashboard - SIMPLIFIED VERSION"""
    try:
        return f"""
        <html>
        <head>
            <title>Employee Dashboard</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                h2 {{ color: #11998e; }}
            </style>
        </head>
        <body>
            <h1>Employee Dashboard</h1>
            <p>Welcome, {current_user.name}!</p>
            
            <div class="section">
                <h2>Your Information</h2>
                <ul>
                    <li>Employee ID: {current_user.employee_id or 'Not set'}</li>
                    <li>Crew: {current_user.crew or 'Not assigned'}</li>
                    <li>Email: {current_user.email}</li>
                </ul>
            </div>
            
            <div class="section">
                <h2>Quick Actions</h2>
                <ul>
                    <li><a href="/view-schedule">View My Schedule</a></li>
                    <li><a href="/time-off-requests">Time Off Requests</a></li>
                    <li><a href="/swap-requests">Shift Swap Requests</a></li>
                </ul>
            </div>
            
            <p><a href="/">Back to Home</a></p>
        </body>
        </html>
        """
    except Exception as e:
        return f"Employee Dashboard Error: {str(e)}", 500

@main_bp.route('/diagnostic')
@login_required
def diagnostic():
    """System diagnostic page"""
    try:
        # Check database connection
        try:
            employee_count = Employee.query.count()
            db_status = f"Connected - {employee_count} employees"
        except Exception as e:
            db_status = f"Error: {str(e)}"
        
        # Check blueprints
        blueprints = list(current_app.blueprints.keys())
        
        # Check routes
        routes = []
        for rule in current_app.url_map.iter_rules():
            routes.append(f"{rule.endpoint}: {rule.rule}")
        
        return f"""
        <html>
        <head><title>System Diagnostic</title></head>
        <body>
            <h1>System Diagnostic</h1>
            
            <h2>Database Status:</h2>
            <p>{db_status}</p>
            
            <h2>Registered Blueprints:</h2>
            <ul>
                {''.join(f'<li>{bp}</li>' for bp in blueprints)}
            </ul>
            
            <h2>Available Routes (first 20):</h2>
            <ul>
                {''.join(f'<li>{route}</li>' for route in routes[:20])}
            </ul>
            
            <h2>Current User:</h2>
            <ul>
                <li>ID: {current_user.id}</li>
                <li>Name: {current_user.name}</li>
                <li>Authenticated: {current_user.is_authenticated}</li>
            </ul>
            
            <p><a href="/">Back to Home</a></p>
        </body>
        </html>
        """
    except Exception as e:
        return f"Diagnostic Error: {str(e)}<br><pre>{traceback.format_exc()}</pre>", 500

@main_bp.route('/overtime-management')
@login_required
def overtime_management():
    """Overtime management - WORKING VERSION"""
    try:
        # For now, allow all authenticated users to view
        # if not current_user.is_supervisor:
        #     return "<h1>Access Denied</h1><p>Supervisor access required.</p><p><a href='/'>Back to Home</a></p>"
        
        # Get basic employee list
        employees = Employee.query.filter(Employee.id != current_user.id).all()
        
        # Simple HTML table
        rows = []
        for emp in employees:
            try:
                ot_hours = emp.last_13_weeks_overtime or 0
                rows.append(f"""
                <tr>
                    <td>{emp.employee_id or f'EMP{emp.id}'}</td>
                    <td>{emp.name}</td>
                    <td>{emp.crew or '-'}</td>
                    <td>{round(ot_hours)}</td>
                </tr>
                """)
            except:
                pass
        
        return f"""
        <html>
        <head>
            <title>Overtime Management</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #11998e; color: white; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <h1>Overtime Management</h1>
            <p><a href="/">Back to Home</a></p>
            
            <h2>Employee Overtime Summary</h2>
            <p>Total Employees: {len(employees)}</p>
            
            <table>
                <tr>
                    <th>Employee ID</th>
                    <th>Name</th>
                    <th>Crew</th>
                    <th>13-Week Total OT</th>
                </tr>
                {''.join(rows)}
            </table>
            
            <p><a href="/upload-employees">Upload Employee Data</a></p>
        </body>
        </html>
        """
    except Exception as e:
        current_app.logger.error(f"Error in overtime_management: {str(e)}\n{traceback.format_exc()}")
        return f"Overtime Management Error: {str(e)}<br><pre>{traceback.format_exc()}</pre>", 500

@main_bp.route('/view-crews')
@login_required
def view_crews():
    """Simple crew view"""
    try:
        crews = {}
        employees = Employee.query.all()
        
        for emp in employees:
            crew = emp.crew or 'Unassigned'
            if crew not in crews:
                crews[crew] = []
            crews[crew].append(emp)
        
        crew_html = []
        for crew, emps in sorted(crews.items()):
            crew_html.append(f"<h3>Crew {crew} ({len(emps)} employees)</h3><ul>")
            for emp in emps:
                crew_html.append(f"<li>{emp.name} - {emp.employee_id or 'No ID'}</li>")
            crew_html.append("</ul>")
        
        return f"""
        <html>
        <head><title>View Crews</title></head>
        <body>
            <h1>Crew Overview</h1>
            <p><a href="/">Back to Home</a></p>
            {''.join(crew_html)}
        </body>
        </html>
        """
    except Exception as e:
        return f"View Crews Error: {str(e)}", 500

# Simplified coming soon page
@main_bp.route('/coming-soon')
@login_required
def coming_soon():
    """Coming soon page"""
    feature = request.args.get('feature', 'This feature')
    return f"""
    <html>
    <head><title>Coming Soon</title></head>
    <body>
        <h1>Coming Soon</h1>
        <p>{feature} is under development.</p>
        <p><a href="/">Back to Home</a></p>
    </body>
    </html>
    """

# Error handlers
@main_bp.app_errorhandler(404)
def not_found_error(error):
    return """
    <html>
    <head><title>404 Not Found</title></head>
    <body>
        <h1>404 - Page Not Found</h1>
        <p>The page you're looking for doesn't exist.</p>
        <p><a href="/">Go to Home</a></p>
    </body>
    </html>
    """, 404

@main_bp.app_errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return f"""
    <html>
    <head><title>500 Internal Error</title></head>
    <body>
        <h1>500 - Internal Server Error</h1>
        <p>Something went wrong.</p>
        <p>Error: {str(error)}</p>
        <p><a href="/">Go to Home</a></p>
    </body>
    </html>
    """, 500
