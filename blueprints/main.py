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
def overtime_management_main():  # Changed function name to be unique
    """Enhanced overtime management page with multi-level sorting"""
    # Check if user is supervisor
    if not current_user.is_supervisor:
        flash('You must be a supervisor to access this page.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    try:
        # Get all employees (no is_active filter since field doesn't exist)
        employees = Employee.query.order_by(Employee.crew, Employee.name).all()
        
        # Check employee count
        total_employees = len(employees)
        expected_count = 100  # You mentioned uploading 100 employees
        
        # Get overtime history for the last 13 weeks
        thirteen_weeks_ago = datetime.now().date() - timedelta(weeks=13)
        
        employees_data = []
        for emp in employees:
            # Skip the current user (supervisor) from the count
            if emp.id == current_user.id:
                continue
                
            # Get overtime hours from OvertimeHistory table
            overtime_total = db.session.query(func.sum(OvertimeHistory.overtime_hours)).filter(
                OvertimeHistory.employee_id == emp.id,
                OvertimeHistory.week_start_date >= thirteen_weeks_ago
            ).scalar() or 0.0
            
            # Get current week overtime
            current_week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())
            current_week_ot = db.session.query(func.sum(OvertimeHistory.overtime_hours)).filter(
                OvertimeHistory.employee_id == emp.id,
                OvertimeHistory.week_start_date == current_week_start
            ).scalar() or 0.0
            
            employees_data.append({
                'id': emp.id,
                'name': emp.name,
                'employee_id': emp.employee_id or f'EMP{emp.id}',
                'crew': emp.crew or 'Unassigned',
                'position': emp.position.name if emp.position else 'No Position',
                'hire_date': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else None,
                'current_week_ot': round(current_week_ot, 1),
                'overtime_13week': round(overtime_total, 1),
                'weekly_average': round(overtime_total / 13, 1) if overtime_total else 0
            })
        
        # Count excluding supervisor
        actual_employee_count = len(employees_data)
        
        # Calculate statistics
        total_ot = sum(e['overtime_13week'] for e in employees_data)
        high_ot_count = len([e for e in employees_data if e['overtime_13week'] > 200])
        avg_ot = round(total_ot / len(employees_data), 1) if employees_data else 0
        
        # Return the improved HTML template
        return render_template_string(open('improved_overtime_template.html').read(),
                                    employees=employees_data,
                                    total_employees=actual_employee_count,
                                    expected_count=expected_count,
                                    total_ot=total_ot,
                                    high_ot_count=high_ot_count,
                                    avg_ot=avg_ot)
        
    except Exception as e:
        # If template not found or other error, use inline version
        employees = Employee.query.order_by(Employee.crew, Employee.name).all()
        actual_employee_count = len([e for e in employees if e.id != current_user.id])
        
@main_bp.route('/overtime-management')
@login_required
def overtime_management():
    """Enhanced overtime management page with multi-level sorting"""
    # Check if user is supervisor
    if not current_user.is_supervisor:
        flash('You must be a supervisor to access this page.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    try:
        # Get all employees (no is_active filter since field doesn't exist)
        employees = Employee.query.order_by(Employee.crew, Employee.name).all()
        
        # Get overtime history for the last 13 weeks
        thirteen_weeks_ago = datetime.now().date() - timedelta(weeks=13)
        
        employees_data = []
        for emp in employees:
            # Skip the current user (supervisor) from the list
            if emp.id == current_user.id:
                continue
                
            # Get overtime hours from OvertimeHistory table
            overtime_total = db.session.query(func.sum(OvertimeHistory.overtime_hours)).filter(
                OvertimeHistory.employee_id == emp.id,
                OvertimeHistory.week_start_date >= thirteen_weeks_ago
            ).scalar() or 0.0
            
            # Get current week overtime
            current_week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())
            current_week_ot = db.session.query(func.sum(OvertimeHistory.overtime_hours)).filter(
                OvertimeHistory.employee_id == emp.id,
                OvertimeHistory.week_start_date == current_week_start
            ).scalar() or 0.0
            
            employees_data.append({
                'id': emp.id,
                'name': emp.name,
                'employee_id': emp.employee_id or f'EMP{emp.id}',
                'crew': emp.crew or 'Unassigned',
                'position': emp.position.name if emp.position else 'No Position',
                'hire_date': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else 'N/A',
                'hire_date_sort': emp.hire_date if emp.hire_date else datetime(2099, 12, 31).date(),
                'current_week_ot': round(current_week_ot, 1),
                'overtime_13week': round(overtime_total, 1),
                'weekly_average': round(overtime_total / 13, 1) if overtime_total else 0
            })
        
        # Calculate statistics
        total_ot = sum(e['overtime_13week'] for e in employees_data)
        high_ot_count = len([e for e in employees_data if e['overtime_13week'] > 200])
        avg_ot = round(total_ot / len(employees_data), 1) if employees_data else 0
        
        # Full HTML with multi-level sorting
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Overtime Management</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.7.2/font/bootstrap-icons.css">
            <style>
                body {{ background-color: #f5f7fa; }}
                .container {{ max-width: 1400px; margin: 2rem auto; }}
                .header {{ margin-bottom: 2rem; }}
                table {{ background: white; font-size: 0.9rem; }}
                .high-ot {{ background-color: #ffebee !important; }}
                .medium-ot {{ background-color: #fff8e1 !important; }}
                .low-ot {{ background-color: #e8f5e9 !important; }}
                .crew-badge {{
                    display: inline-block;
                    padding: 0.25rem 0.5rem;
                    border-radius: 0.25rem;
                    font-size: 0.875rem;
                    font-weight: 500;
                }}
                .crew-a {{ background-color: #e3f2fd; color: #1976d2; }}
                .crew-b {{ background-color: #f3e5f5; color: #7b1fa2; }}
                .crew-c {{ background-color: #e8f5e9; color: #388e3c; }}
                .crew-d {{ background-color: #fff3e0; color: #f57c00; }}
                .sort-controls {{
                    background: white;
                    padding: 20px;
                    border-radius: 8px;
                    margin-bottom: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .sort-level {{
                    margin-bottom: 10px;
                    padding: 10px;
                    background: #f8f9fa;
                    border-radius: 5px;
                }}
                .stats-card {{
                    background: white;
                    border-radius: 8px;
                    padding: 20px;
                    text-align: center;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    height: 100%;
                }}
                .stat-value {{
                    font-size: 2rem;
                    font-weight: bold;
                    color: #11998e;
                }}
                .clickable {{ cursor: pointer; }}
                .clickable:hover {{ background-color: #e9ecef; }}
                .filters {{
                    background: white;
                    padding: 15px;
                    border-radius: 8px;
                    margin-bottom: 20px;
                }}
                .table-container {{
                    background: white;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    overflow-x: auto;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1><i class="bi bi-clock-history"></i> Overtime Management</h1>
                    <p class="text-muted">13-Week Rolling Overtime Summary with Multi-Level Sorting</p>
                </div>

                <!-- Action Buttons -->
                <div class="mb-3">
                    <a href="/dashboard" class="btn btn-secondary">
                        <i class="bi bi-arrow-left"></i> Back to Dashboard
                    </a>
                    <a href="/upload-employees" class="btn btn-primary">
                        <i class="bi bi-upload"></i> Re-upload Employee Data
                    </a>
                    <button class="btn btn-success" onclick="exportData()">
                        <i class="bi bi-download"></i> Export to Excel
                    </button>
                </div>

                <!-- Statistics Cards -->
                <div class="row mb-4">
                    <div class="col-md-3">
                        <div class="stats-card">
                            <div class="stat-value">{len(employees_data)}</div>
                            <div class="text-muted">Total Employees</div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="stats-card">
                            <div class="stat-value">{total_ot:.0f}h</div>
                            <div class="text-muted">Total OT (13 weeks)</div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="stats-card">
                            <div class="stat-value">{avg_ot}h</div>
                            <div class="text-muted">Average OT/Employee</div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="stats-card">
                            <div class="stat-value">{high_ot_count}</div>
                            <div class="text-muted">High OT (>200h)</div>
                        </div>
                    </div>
                </div>

                <!-- Filters -->
                <div class="filters">
                    <h5>Filters</h5>
                    <div class="row">
                        <div class="col-md-3">
                            <select class="form-select" id="crewFilter" onchange="applyFilters()">
                                <option value="">All Crews</option>
                                <option value="A">Crew A</option>
                                <option value="B">Crew B</option>
                                <option value="C">Crew C</option>
                                <option value="D">Crew D</option>
                            </select>
                        </div>
                        <div class="col-md-3">
                            <select class="form-select" id="positionFilter" onchange="applyFilters()">
                                <option value="">All Positions</option>
                                {"".join(f'<option value="{p}">{p}</option>' for p in sorted(set(e['position'] for e in employees_data if e['position'] != 'No Position')))}
                            </select>
                        </div>
                        <div class="col-md-3">
                            <select class="form-select" id="otFilter" onchange="applyFilters()">
                                <option value="">All OT Ranges</option>
                                <option value="0-50">0-50 hours</option>
                                <option value="50-100">50-100 hours</option>
                                <option value="100-150">100-150 hours</option>
                                <option value="150-200">150-200 hours</option>
                                <option value="200+">200+ hours</option>
                            </select>
                        </div>
                        <div class="col-md-3">
                            <button class="btn btn-secondary" onclick="resetFilters()">
                                <i class="bi bi-arrow-counterclockwise"></i> Reset Filters
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Sort Controls -->
                <div class="sort-controls">
                    <h5>Multi-Level Sorting</h5>
                    <div class="row">
                        <div class="col-md-3">
                            <div class="sort-level">
                                <label>Sort Level 1:</label>
                                <select class="form-select" id="sort1" onchange="applySort()">
                                    <option value="">None</option>
                                    <option value="crew">Crew</option>
                                    <option value="position">Position</option>
                                    <option value="overtime">13-Week Total</option>
                                    <option value="hire_date">Date of Hire</option>
                                    <option value="name">Name</option>
                                </select>
                                <select class="form-select mt-1" id="dir1" onchange="applySort()">
                                    <option value="asc">Ascending</option>
                                    <option value="desc">Descending</option>
                                </select>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <div class="sort-level">
                                <label>Sort Level 2:</label>
                                <select class="form-select" id="sort2" onchange="applySort()">
                                    <option value="">None</option>
                                    <option value="crew">Crew</option>
                                    <option value="position">Position</option>
                                    <option value="overtime">13-Week Total</option>
                                    <option value="hire_date">Date of Hire</option>
                                    <option value="name">Name</option>
                                </select>
                                <select class="form-select mt-1" id="dir2" onchange="applySort()">
                                    <option value="asc">Ascending</option>
                                    <option value="desc">Descending</option>
                                </select>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <div class="sort-level">
                                <label>Sort Level 3:</label>
                                <select class="form-select" id="sort3" onchange="applySort()">
                                    <option value="">None</option>
                                    <option value="crew">Crew</option>
                                    <option value="position">Position</option>
                                    <option value="overtime">13-Week Total</option>
                                    <option value="hire_date">Date of Hire</option>
                                    <option value="name">Name</option>
                                </select>
                                <select class="form-select mt-1" id="dir3" onchange="applySort()">
                                    <option value="asc">Ascending</option>
                                    <option value="desc">Descending</option>
                                </select>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <div class="sort-level">
                                <label>Sort Level 4:</label>
                                <select class="form-select" id="sort4" onchange="applySort()">
                                    <option value="">None</option>
                                    <option value="crew">Crew</option>
                                    <option value="position">Position</option>
                                    <option value="overtime">13-Week Total</option>
                                    <option value="hire_date">Date of Hire</option>
                                    <option value="name">Name</option>
                                </select>
                                <select class="form-select mt-1" id="dir4" onchange="applySort()">
                                    <option value="asc">Ascending</option>
                                    <option value="desc">Descending</option>
                                </select>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Employee Table -->
                <div class="table-container">
                    <table class="table table-hover" id="employeeTable">
                        <thead>
                            <tr>
                                <th class="clickable" onclick="quickSort('name')">Employee <i class="bi bi-arrow-down-up"></i></th>
                                <th>Employee ID</th>
                                <th class="clickable" onclick="quickSort('crew')">Crew <i class="bi bi-arrow-down-up"></i></th>
                                <th class="clickable" onclick="quickSort('position')">Position <i class="bi bi-arrow-down-up"></i></th>
                                <th class="clickable" onclick="quickSort('hire_date')">Date of Hire <i class="bi bi-arrow-down-up"></i></th>
                                <th>Current Week</th>
                                <th class="clickable" onclick="quickSort('overtime')">13-Week Total <i class="bi bi-arrow-down-up"></i></th>
                                <th>Weekly Avg</th>
                                <th>Trend</th>
                            </tr>
                        </thead>
                        <tbody id="tableBody">
        """
        
        # Add employee rows
        for emp in sorted(employees_data, key=lambda x: (-x['overtime_13week'])):
            row_class = ''
            if emp['overtime_13week'] > 200:
                row_class = 'high-ot'
            elif emp['overtime_13week'] > 150:
                row_class = 'medium-ot'
            elif emp['overtime_13week'] < 50:
                row_class = 'low-ot'
            
            crew_badge = f'<span class="crew-badge crew-{emp["crew"].lower()}">{emp["crew"]}</span>' if emp['crew'] != 'Unassigned' else emp['crew']
            
            # Simple trend indicator
            trend = '→'
            trend_color = 'text-muted'
            if emp['current_week_ot'] > emp['weekly_average'] * 1.2:
                trend = '↑'
                trend_color = 'text-danger'
            elif emp['current_week_ot'] < emp['weekly_average'] * 0.8:
                trend = '↓'
                trend_color = 'text-success'
            
            html += f"""
                <tr class="{row_class}" data-crew="{emp['crew']}" data-position="{emp['position']}" 
                    data-overtime="{emp['overtime_13week']}" data-hire-date="{emp['hire_date_sort']}"
                    data-name="{emp['name']}">
                    <td>{emp['name']}</td>
                    <td>{emp['employee_id']}</td>
                    <td>{crew_badge}</td>
                    <td>{emp['position']}</td>
                    <td>{emp['hire_date']}</td>
                    <td>{emp['current_week_ot']}h</td>
                    <td><strong>{emp['overtime_13week']}h</strong></td>
                    <td>{emp['weekly_average']}h</td>
                    <td class="{trend_color}">{trend}</td>
                </tr>
            """
        
        html += """
                        </tbody>
                    </table>
                </div>
            </div>

            <script>
                let allRows = [];
                let filteredRows = [];
                
                // Store all rows on load
                document.addEventListener('DOMContentLoaded', function() {
                    allRows = Array.from(document.querySelectorAll('#tableBody tr'));
                    filteredRows = [...allRows];
                });
                
                function applyFilters() {
                    const crewFilter = document.getElementById('crewFilter').value;
                    const positionFilter = document.getElementById('positionFilter').value;
                    const otFilter = document.getElementById('otFilter').value;
                    
                    filteredRows = allRows.filter(row => {
                        const crew = row.getAttribute('data-crew');
                        const position = row.getAttribute('data-position');
                        const overtime = parseFloat(row.getAttribute('data-overtime'));
                        
                        let show = true;
                        
                        if (crewFilter && crew !== crewFilter) show = false;
                        if (positionFilter && position !== positionFilter) show = false;
                        
                        if (otFilter) {
                            switch(otFilter) {
                                case '0-50': if (overtime > 50) show = false; break;
                                case '50-100': if (overtime <= 50 || overtime > 100) show = false; break;
                                case '100-150': if (overtime <= 100 || overtime > 150) show = false; break;
                                case '150-200': if (overtime <= 150 || overtime > 200) show = false; break;
                                case '200+': if (overtime <= 200) show = false; break;
                            }
                        }
                        
                        return show;
                    });
                    
                    applySort();
                }
                
                function resetFilters() {
                    document.getElementById('crewFilter').value = '';
                    document.getElementById('positionFilter').value = '';
                    document.getElementById('otFilter').value = '';
                    filteredRows = [...allRows];
                    applySort();
                }
                
                function applySort() {
                    const sortLevels = [];
                    for (let i = 1; i <= 4; i++) {
                        const field = document.getElementById(`sort${i}`).value;
                        const dir = document.getElementById(`dir${i}`).value;
                        if (field) {
                            sortLevels.push({ field, dir });
                        }
                    }
                    
                    if (sortLevels.length === 0) {
                        // Default sort by overtime descending
                        sortLevels.push({ field: 'overtime', dir: 'desc' });
                    }
                    
                    const sortedRows = [...filteredRows].sort((a, b) => {
                        for (const level of sortLevels) {
                            let aVal, bVal;
                            
                            switch(level.field) {
                                case 'crew':
                                    aVal = a.getAttribute('data-crew');
                                    bVal = b.getAttribute('data-crew');
                                    break;
                                case 'position':
                                    aVal = a.getAttribute('data-position');
                                    bVal = b.getAttribute('data-position');
                                    break;
                                case 'overtime':
                                    aVal = parseFloat(a.getAttribute('data-overtime'));
                                    bVal = parseFloat(b.getAttribute('data-overtime'));
                                    break;
                                case 'hire_date':
                                    aVal = a.getAttribute('data-hire-date');
                                    bVal = b.getAttribute('data-hire-date');
                                    break;
                                case 'name':
                                    aVal = a.getAttribute('data-name');
                                    bVal = b.getAttribute('data-name');
                                    break;
                            }
                            
                            if (aVal < bVal) return level.dir === 'asc' ? -1 : 1;
                            if (aVal > bVal) return level.dir === 'asc' ? 1 : -1;
                        }
                        return 0;
                    });
                    
                    // Update table
                    const tbody = document.getElementById('tableBody');
                    tbody.innerHTML = '';
                    
                    // Show filtered and sorted rows
                    sortedRows.forEach(row => {
                        tbody.appendChild(row.cloneNode(true));
                    });
                    
                    // Hide non-filtered rows
                    allRows.forEach(row => {
                        if (!filteredRows.includes(row)) {
                            row.style.display = 'none';
                        }
                    });
                }
                
                function quickSort(field) {
                    // Set first sort level to this field
                    document.getElementById('sort1').value = field;
                    document.getElementById('dir1').value = field === 'hire_date' ? 'asc' : 'desc';
                    
                    // Clear other sort levels
                    for (let i = 2; i <= 4; i++) {
                        document.getElementById(`sort${i}`).value = '';
                    }
                    
                    applySort();
                }
                
                function exportData() {
                    alert('Export functionality will be implemented to download current view as Excel file');
                    // In production, this would POST current filters/sort to an export endpoint
                }
            </script>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        return f"""
        <html>
        <head><title>Error - Overtime Management</title></head>
        <body>
            <div style="max-width: 800px; margin: 50px auto; padding: 20px;">
                <h1>Error Loading Overtime Data</h1>
                <p>Error: {str(e)}</p>
                <p><a href="/dashboard">Back to Dashboard</a></p>
            </div>
        </body>
        </html>
        """, 500
        
        # Get overtime history for the last 13 weeks
        thirteen_weeks_ago = datetime.now().date() - timedelta(weeks=13)
        
        employees_data = []
        for emp in employees:
            # Get overtime hours from OvertimeHistory table
            overtime_total = db.session.query(func.sum(OvertimeHistory.overtime_hours)).filter(
                OvertimeHistory.employee_id == emp.id,
                OvertimeHistory.week_start_date >= thirteen_weeks_ago
            ).scalar() or 0.0
            
            # Get current week overtime
            current_week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())
            current_week_ot = db.session.query(func.sum(OvertimeHistory.overtime_hours)).filter(
                OvertimeHistory.employee_id == emp.id,
                OvertimeHistory.week_start_date == current_week_start
            ).scalar() or 0.0
            
            employees_data.append({
                'id': emp.id,
                'name': emp.name,
                'employee_id': emp.employee_id or f'EMP{emp.id}',
                'crew': emp.crew or 'Unassigned',
                'position': emp.position.name if emp.position else 'No Position',
                'current_week_overtime': round(current_week_ot, 1),
                'last_13_weeks_overtime': round(overtime_total, 1),
                'average_weekly_overtime': round(overtime_total / 13, 1) if overtime_total else 0
            })
        
        # Sort by total overtime descending
        employees_data.sort(key=lambda x: x['last_13_weeks_overtime'], reverse=True)
        
        # Simple HTML response
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Overtime Management</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body {{ background-color: #f5f7fa; }}
                .container {{ max-width: 1200px; margin: 2rem auto; }}
                .header {{ margin-bottom: 2rem; }}
                .alert-warning {{ margin-bottom: 2rem; }}
                table {{ background: white; }}
                .high-ot {{ background-color: #fee; }}
                .medium-ot {{ background-color: #ffd; }}
                .crew-badge {{
                    display: inline-block;
                    padding: 0.25rem 0.5rem;
                    border-radius: 0.25rem;
                    font-size: 0.875rem;
                    font-weight: 500;
                }}
                .crew-a {{ background-color: #e3f2fd; color: #1976d2; }}
                .crew-b {{ background-color: #f3e5f5; color: #7b1fa2; }}
                .crew-c {{ background-color: #e8f5e9; color: #388e3c; }}
                .crew-d {{ background-color: #fff3e0; color: #f57c00; }}
                .debug-info {{ background: #f0f0f0; padding: 10px; margin-bottom: 20px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Overtime Management</h1>
                    <p class="text-muted">13-Week Rolling Overtime Summary</p>
                    <a href="/dashboard" class="btn btn-secondary">Back to Dashboard</a>
                    <a href="/upload-employees" class="btn btn-primary">Upload New Data</a>
                </div>
                
                <div class="debug-info">
                    <strong>Debug Info:</strong><br>
                    Total employees in database: {total_employees}<br>
                    Active employees: {active_employees}<br>
                    Employees found by query: {len(employees)}<br>
                    OvertimeHistory records: {OvertimeHistory.query.count()}
                </div>
        """
        
        if not employees_data:
            html += """
                <div class="alert alert-warning">
                    <h4>No Employee Data Found</h4>
                    <p>Please <a href="/upload-employees">upload employee data</a> to view overtime information.</p>
                </div>
                
                <div class="debug-info">
                    <strong>Additional Debug:</strong><br>
            """
            
            # Show first few employees if any exist
            sample_employees = Employee.query.limit(5).all()
            if sample_employees:
                html += "Sample employees in database:<br>"
                for emp in sample_employees:
                    html += f"- {emp.name} (ID: {emp.id}, Active: {getattr(emp, 'is_active', 'N/A')}, Crew: {emp.crew})<br>"
            else:
                html += "No employees found in database at all!<br>"
                
            html += """
                </div>
            """
        else:
            # Statistics
            total_ot = sum(e['last_13_weeks_overtime'] for e in employees_data)
            high_ot_count = len([e for e in employees_data if e['last_13_weeks_overtime'] > 200])
            
            html += f"""
                <div class="row mb-4">
                    <div class="col-md-3">
                        <div class="card">
                            <div class="card-body text-center">
                                <h3>{len(employees_data)}</h3>
                                <p class="text-muted mb-0">Total Employees</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card">
                            <div class="card-body text-center">
                                <h3>{total_ot:.1f}</h3>
                                <p class="text-muted mb-0">Total OT Hours</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card">
                            <div class="card-body text-center">
                                <h3>{total_ot/len(employees_data) if employees_data else 0:.1f}</h3>
                                <p class="text-muted mb-0">Avg OT/Employee</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card">
                            <div class="card-body text-center">
                                <h3>{high_ot_count}</h3>
                                <p class="text-muted mb-0">High OT (&gt;200h)</p>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-body">
                        <table class="table table-hover">
                            <thead>
                                <tr>
                                    <th>Employee</th>
                                    <th>ID</th>
                                    <th>Crew</th>
                                    <th>Position</th>
                                    <th>Current Week OT</th>
                                    <th>13-Week Total</th>
                                    <th>Weekly Average</th>
                                </tr>
                            </thead>
                            <tbody>
            """
            
            for emp in employees_data:
                row_class = ''
                if emp['last_13_weeks_overtime'] > 200:
                    row_class = 'high-ot'
                elif emp['last_13_weeks_overtime'] > 150:
                    row_class = 'medium-ot'
                
                crew_badge = f'<span class="crew-badge crew-{emp["crew"].lower()}">{emp["crew"]}</span>' if emp['crew'] != 'Unassigned' else emp['crew']
                
                html += f"""
                    <tr class="{row_class}">
                        <td>{emp['name']}</td>
                        <td>{emp['employee_id']}</td>
                        <td>{crew_badge}</td>
                        <td>{emp['position']}</td>
                        <td>{emp['current_week_overtime']}h</td>
                        <td><strong>{emp['last_13_weeks_overtime']}h</strong></td>
                        <td>{emp['average_weekly_overtime']}h</td>
                    </tr>
                """
            
            html += """
                            </tbody>
                        </table>
                    </div>
                </div>
            """
        
        html += """
            </div>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        # If there's any error, show a simple error page
        return f"""
        <html>
        <head><title>Error - Overtime Management</title></head>
        <body>
            <div style="max-width: 800px; margin: 50px auto; padding: 20px;">
                <h1>Error Loading Overtime Data</h1>
                <p>There was an error loading the overtime management page.</p>
                <p>Error details: {str(e)}</p>
                <p><a href="/dashboard">Back to Dashboard</a></p>
                <p><a href="/upload-employees">Upload Employee Data</a></p>
            </div>
        </body>
        </html>
        """, 500

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

@main_bp.route('/fix-employees-active')
@login_required
def fix_employees_active():
    """This route is no longer needed - is_active field doesn't exist"""
    if not current_user.is_supervisor:
        flash('You must be a supervisor to access this page.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    return f"""
    <html>
    <head><title>Not Needed</title></head>
    <body style="font-family: Arial; margin: 50px;">
        <h1>Fix Not Needed</h1>
        <p>The is_active field doesn't exist on the Employee model.</p>
        <p>The overtime management page has been updated to show all employees.</p>
        <p><a href="/overtime-management">Go to Overtime Management</a></p>
        <p><a href="/dashboard">Back to Dashboard</a></p>
    </body>
    </html>
    """

@main_bp.route('/debug-employees')
@login_required
def debug_employees():
    """Debug route to check employee data"""
    employees = Employee.query.all()
    overtime_records = OvertimeHistory.query.all()
    
    html = """
    <html>
    <head><title>Employee Debug Info</title></head>
    <body style="font-family: Arial; margin: 20px;">
        <h1>Employee Database Debug</h1>
        <a href="/dashboard">Back to Dashboard</a>
        
        <h2>Employees (Total: {0})</h2>
        <table border="1" cellpadding="5">
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Email</th>
                <th>Crew</th>
                <th>Position</th>
                <th>is_active</th>
                <th>is_supervisor</th>
            </tr>
    """.format(len(employees))
    
    for emp in employees:
        html += f"""
            <tr>
                <td>{emp.id}</td>
                <td>{emp.name}</td>
                <td>{emp.email}</td>
                <td>{emp.crew or 'None'}</td>
                <td>{emp.position.name if emp.position else 'None'}</td>
                <td>{getattr(emp, 'is_active', 'N/A')}</td>
                <td>{emp.is_supervisor}</td>
            </tr>
        """
    
    html += f"""
        </table>
        
        <h2>Overtime History Records (Total: {len(overtime_records)})</h2>
        <table border="1" cellpadding="5">
            <tr>
                <th>ID</th>
                <th>Employee ID</th>
                <th>Week Start</th>
                <th>Overtime Hours</th>
            </tr>
    """
    
    for ot in overtime_records[:20]:  # Show first 20 records
        html += f"""
            <tr>
                <td>{ot.id}</td>
                <td>{ot.employee_id}</td>
                <td>{ot.week_start_date}</td>
                <td>{ot.overtime_hours}</td>
            </tr>
        """
    
    if len(overtime_records) > 20:
        html += f"<tr><td colspan='4'>... and {len(overtime_records) - 20} more records</td></tr>"
    
    html += """
        </table>
    </body>
    </html>
    """
    
    return html

# API endpoints for any AJAX calls
@main_bp.route('/api/overtime-data')
@login_required
def api_overtime_data():
    """API endpoint for overtime data"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        employees = Employee.query.all()
        thirteen_weeks_ago = datetime.now().date() - timedelta(weeks=13)
        
        employees_data = []
        for emp in employees:
            if emp.id == current_user.id:
                continue
                
            # Get overtime totals
            overtime_total = db.session.query(func.sum(OvertimeHistory.overtime_hours)).filter(
                OvertimeHistory.employee_id == emp.id,
                OvertimeHistory.week_start_date >= thirteen_weeks_ago
            ).scalar() or 0.0
            
            current_week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())
            current_week_ot = db.session.query(func.sum(OvertimeHistory.overtime_hours)).filter(
                OvertimeHistory.employee_id == emp.id,
                OvertimeHistory.week_start_date == current_week_start
            ).scalar() or 0.0
            
            employees_data.append({
                'id': emp.id,
                'name': emp.name,
                'employee_id': emp.employee_id or f'EMP{emp.id}',
                'crew': emp.crew or 'Unassigned',
                'position': emp.position.name if emp.position else 'No Position',
                'hire_date': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else None,
                'current_week_ot': round(current_week_ot, 1),
                'overtime_13week': round(overtime_total, 1),
                'weekly_average': round(overtime_total / 13, 1) if overtime_total else 0
            })
        
        return jsonify({
            'employees': employees_data,
            'total': len(employees_data)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@main_bp.route('/api/clear-all-employees', methods=['GET', 'POST'])
@login_required
def clear_all_employees():
    """Nuclear option to clear all employees except current user"""
    if not current_user.is_supervisor:
        flash('You must be a supervisor to access this page.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'GET':
        # Show confirmation page
        employee_count = Employee.query.filter(Employee.id != current_user.id).count()
        return f"""
        <html>
        <head><title>Clear All Employees</title></head>
        <body style="font-family: Arial; margin: 50px;">
            <h1>⚠️ Clear All Employees</h1>
            <p>This will permanently delete {employee_count} employees (everyone except you).</p>
            <p><strong>This action cannot be undone!</strong></p>
            <form method="POST">
                <button type="submit" class="btn btn-danger" style="background: red; color: white; padding: 10px 20px;">
                    Yes, Delete All {employee_count} Employees
                </button>
                <a href="/overtime-management" style="margin-left: 20px;">Cancel</a>
            </form>
        </body>
        </html>
        """
    
    try:
        # Delete all employees except current user
        from sqlalchemy import text
        
        # Delete related records first
        db.session.execute(text("DELETE FROM overtime_history WHERE employee_id != :uid"), {'uid': current_user.id})
        db.session.execute(text("DELETE FROM employee_skills WHERE employee_id != :uid"), {'uid': current_user.id})
        db.session.execute(text("DELETE FROM schedule WHERE employee_id != :uid"), {'uid': current_user.id})
        db.session.execute(text("DELETE FROM time_off_request WHERE employee_id != :uid"), {'uid': current_user.id})
        
        # Delete employees
        result = db.session.execute(text("DELETE FROM employee WHERE id != :uid"), {'uid': current_user.id})
        deleted_count = result.rowcount
        
        db.session.commit()
        
        flash(f'Successfully deleted {deleted_count} employees. You can now upload fresh data.', 'success')
        return redirect(url_for('employee_import.upload_employees'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting employees: {str(e)}', 'danger')
        return redirect(url_for('main.overtime_management'))

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
