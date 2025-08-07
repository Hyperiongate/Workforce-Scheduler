# blueprints/main.py - COMPLETE FILE
"""
Main blueprint with enhanced employee dashboard and fixed overtime management
Complete implementation following project requirements
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file, current_app
from flask_login import login_required, current_user
from models import (db, Employee, Position, Schedule, OvertimeHistory, TimeOffRequest, 
                   ShiftSwapRequest, ScheduleSuggestion, CrewCoverageRequirement,
                   CoverageRequest, MaintenanceIssue, CasualWorker, OvertimeOpportunity,
                   CoverageNotification, VacationCalendar)
from datetime import date, timedelta, datetime
from sqlalchemy import or_, func, text, and_, case
from utils.helpers import get_coverage_gaps
import traceback

# Create the blueprint
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
    """Supervisor Operations Center Dashboard"""
    if not current_user.is_supervisor:
        return redirect(url_for('main.employee_dashboard'))
    
    try:
        # Get real-time staffing data
        today = date.today()
        
        # Get pending counts - REQUIRED by template
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        total_employees = Employee.query.count()
        
        # Calculate coverage gaps for today - REQUIRED by template
        all_gaps = get_coverage_gaps()
        coverage_gaps = len([g for g in all_gaps if g['date'] == today])
        
        # NEW: Add missing variables that dashboard.html expects
        # Today's scheduled employees
        try:
            today_scheduled = Schedule.query.filter_by(date=today).count()
        except:
            today_scheduled = 0
        
        # Employees on leave today
        try:
            today_on_leave = VacationCalendar.query.filter(
                and_(
                    VacationCalendar.date == today,
                    VacationCalendar.status == 'approved'
                )
            ).count()
        except:
            today_on_leave = 0
        
        # Critical maintenance issues
        try:
            critical_maintenance = MaintenanceIssue.query.filter(
                and_(
                    MaintenanceIssue.priority == 'critical',
                    MaintenanceIssue.status.in_(['open', 'in_progress'])
                )
            ).count()
        except:
            critical_maintenance = 0
        
        # Format current date
        current_date = today.strftime('%A, %B %d, %Y')
        
        # Return with ALL variables the template expects
        return render_template('dashboard.html',
            # Original 4 variables
            pending_time_off=pending_time_off,
            pending_swaps=pending_swaps,
            total_employees=total_employees,
            coverage_gaps=coverage_gaps,
            # NEW: Additional required variables
            today_scheduled=today_scheduled,
            today_on_leave=today_on_leave,
            critical_maintenance=critical_maintenance,
            current_date=current_date
        )
        
    except Exception as e:
        print(f"Dashboard error: {str(e)}")
        traceback.print_exc()
        flash('Error loading dashboard. Please try again.', 'error')
        
        # If error, render with safe defaults
        return render_template('dashboard.html',
            pending_time_off=0,
            pending_swaps=0,
            total_employees=0,
            coverage_gaps=0,
            today_scheduled=0,
            today_on_leave=0,
            critical_maintenance=0,
            current_date=date.today().strftime('%A, %B %d, %Y')
        )

@main_bp.route('/employee-dashboard')
@login_required
def employee_dashboard():
    """Enhanced employee dashboard with comprehensive self-service features"""
    if current_user.is_supervisor:
        return redirect(url_for('main.dashboard'))
    
    try:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        
        # 1. MY INFORMATION SECTION
        employee_info = {
            'name': current_user.name,
            'employee_id': current_user.employee_id,
            'crew': current_user.crew or 'Not Assigned',
            'position': current_user.position.name if current_user.position else 'Not Assigned',
            'department': current_user.department or 'Not Assigned',
            'email': current_user.email,
            'hire_date': current_user.hire_date if hasattr(current_user, 'hire_date') else None,
            'supervisor': None
        }
        
        # Find their supervisor
        if current_user.crew:
            supervisor = Employee.query.filter_by(
                crew=current_user.crew, 
                is_supervisor=True
            ).first()
            if supervisor:
                employee_info['supervisor'] = supervisor.name
        
        # 2. SCHEDULE INFORMATION
        # Current week schedule
        current_week_schedule = Schedule.query.filter(
            Schedule.employee_id == current_user.id,
            Schedule.date >= week_start,
            Schedule.date <= week_end
        ).order_by(Schedule.date).all()
        
        # Next shift
        next_shift = Schedule.query.filter(
            Schedule.employee_id == current_user.id,
            Schedule.date >= today
        ).order_by(Schedule.date).first()
        
        # Calculate weekly hours
        weekly_hours = sum(8 for s in current_week_schedule)  # Assuming 8-hour shifts
        
        # 3. OVERTIME SECTION
        # Get 13-week overtime history
        thirteen_weeks_ago = today - timedelta(weeks=13)
        overtime_history = OvertimeHistory.query.filter(
            OvertimeHistory.employee_id == current_user.id,
            OvertimeHistory.week_ending >= thirteen_weeks_ago
        ).order_by(OvertimeHistory.week_ending.desc()).all()
        
        # Calculate overtime statistics
        total_ot_hours = sum(ot.hours_worked for ot in overtime_history) if overtime_history else 0
        avg_weekly_ot = round(total_ot_hours / 13, 1) if overtime_history else 0
        
        # Get available overtime opportunities (next 2 months)
        two_months_ahead = today + timedelta(days=60)
        available_overtime = []
        
        try:
            # Check if OvertimeOpportunity model exists
            available_overtime = OvertimeOpportunity.query.filter(
                OvertimeOpportunity.date >= today,
                OvertimeOpportunity.date <= two_months_ahead,
                OvertimeOpportunity.crew == current_user.crew,
                OvertimeOpportunity.status == 'open'
            ).order_by(OvertimeOpportunity.date).limit(10).all()
        except:
            # Model might not exist yet - use CoverageRequest as proxy
            try:
                available_overtime = CoverageRequest.query.filter(
                    CoverageRequest.date >= today,
                    CoverageRequest.date <= two_months_ahead,
                    CoverageRequest.status == 'open'
                ).order_by(CoverageRequest.date).limit(10).all()
            except:
                available_overtime = []
        
        # 4. TIME OFF BALANCES
        time_off_balances = {
            'vacation': current_user.vacation_days,
            'sick': current_user.sick_days,
            'personal': current_user.personal_days,
            'total': current_user.vacation_days + current_user.sick_days + current_user.personal_days
        }
        
        # Recent time off requests
        recent_time_off = TimeOffRequest.query.filter_by(
            employee_id=current_user.id
        ).order_by(TimeOffRequest.created_at.desc()).limit(5).all()
        
        # 5. SHIFT SWAP MARKETPLACE
        # My active swap requests
        my_swap_requests = ShiftSwapRequest.query.filter(
            or_(
                ShiftSwapRequest.requesting_employee_id == current_user.id,
                ShiftSwapRequest.target_employee_id == current_user.id
            ),
            ShiftSwapRequest.status == 'pending'
        ).order_by(ShiftSwapRequest.created_at.desc()).all()
        
        # Count pending swaps
        pending_swaps = len(my_swap_requests)
        
        # Available swaps from others (same crew)
        available_swaps = ShiftSwapRequest.query.join(
            Employee, ShiftSwapRequest.requesting_employee_id == Employee.id
        ).filter(
            Employee.crew == current_user.crew,
            ShiftSwapRequest.status == 'open',
            ShiftSwapRequest.requesting_employee_id != current_user.id
        ).order_by(ShiftSwapRequest.shift_date).limit(5).all()
        
        # 6. MESSAGES/NOTIFICATIONS
        unread_messages = 0
        recent_announcements = []
        
        try:
            # Check for position messages
            from models import PositionMessage, MessageReadReceipt
            
            position_messages = PositionMessage.query.filter(
                PositionMessage.position_id == current_user.position_id,
                PositionMessage.created_at >= today - timedelta(days=7)
            ).order_by(PositionMessage.created_at.desc()).limit(3).all()
            
            # Count unread
            for msg in position_messages:
                receipt = MessageReadReceipt.query.filter_by(
                    message_id=msg.id,
                    employee_id=current_user.id
                ).first()
                if not receipt:
                    unread_messages += 1
                    
            recent_announcements = position_messages
        except:
            # Models might not exist
            pass
        
        # 7. QUICK STATS
        stats = {
            'shifts_this_month': Schedule.query.filter(
                Schedule.employee_id == current_user.id,
                Schedule.date >= date(today.year, today.month, 1),
                Schedule.date <= today
            ).count(),
            'ot_this_month': sum(
                ot.hours_worked for ot in overtime_history 
                if ot.week_ending.month == today.month
            ) if overtime_history else 0,
            'days_until_next_off': None
        }
        
        # Calculate days until next day off
        next_off_day = None
        check_date = today + timedelta(days=1)
        for i in range(14):  # Check next 2 weeks
            scheduled = Schedule.query.filter_by(
                employee_id=current_user.id,
                date=check_date
            ).first()
            if not scheduled:
                next_off_day = check_date
                stats['days_until_next_off'] = (check_date - today).days
                break
            check_date += timedelta(days=1)
        
        # Return enhanced dashboard
        return render_template('employee_dashboard_enhanced.html',
            # Employee Information
            employee_info=employee_info,
            # Schedule Data
            current_week_schedule=current_week_schedule,
            next_shift=next_shift,
            weekly_hours=weekly_hours,
            week_start=week_start,
            week_end=week_end,
            # Overtime Data
            overtime_history=overtime_history,
            total_ot_hours=total_ot_hours,
            avg_weekly_ot=avg_weekly_ot,
            available_overtime=available_overtime,
            # Time Off Data
            time_off_balances=time_off_balances,
            recent_time_off=recent_time_off,
            # Swap Data
            my_swap_requests=my_swap_requests,
            pending_swaps=pending_swaps,
            available_swaps=available_swaps,
            # Messages
            unread_messages=unread_messages,
            recent_announcements=recent_announcements,
            # Stats
            stats=stats,
            # Dates
            today=today,
            current_date=today.strftime('%A, %B %d, %Y')
        )
        
    except Exception as e:
        print(f"Employee dashboard error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        flash('Some dashboard features could not be loaded.', 'warning')
        
        # Return basic dashboard on error with safe defaults
        return render_template('employee_dashboard_enhanced.html',
            employee_info={'name': current_user.name, 'crew': 'Error loading', 'employee_id': '', 
                          'position': 'Not Assigned', 'department': 'Not Assigned', 
                          'email': current_user.email, 'hire_date': None, 'supervisor': None},
            current_week_schedule=[],
            next_shift=None,
            weekly_hours=0,
            week_start=week_start,
            week_end=week_end,
            overtime_history=[],
            total_ot_hours=0,
            avg_weekly_ot=0,
            available_overtime=[],
            time_off_balances={'vacation': 0, 'sick': 0, 'personal': 0, 'total': 0},
            recent_time_off=[],
            my_swap_requests=[],
            pending_swaps=0,
            available_swaps=[],
            unread_messages=0,
            recent_announcements=[],
            stats={'shifts_this_month': 0, 'ot_this_month': 0, 'days_until_next_off': None},
            today=today,
            current_date=today.strftime('%A, %B %d, %Y')
        )

@main_bp.route('/supervisor/overtime-management')
@login_required
def overtime_management():
    """Enhanced overtime management page with multi-level sorting - FIXED VERSION"""
    # Check if user is supervisor
    if not current_user.is_supervisor:
        flash('You must be a supervisor to access this page.', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    try:
        # Get parameters from URL
        page = request.args.get('page', 1, type=int)
        per_page = 25
        
        # Search and filter parameters
        search_term = request.args.get('search', '')
        crew_filter = request.args.get('crew', '')
        position_filter = request.args.get('position', '')
        ot_range_filter = request.args.get('ot_range', '')
        
        # Multi-level sort parameters
        sort_levels = []
        for i in range(1, 5):
            sort_field = request.args.get(f'sort{i}')
            sort_dir = request.args.get(f'dir{i}', 'asc')
            if sort_field:
                sort_levels.append((sort_field, sort_dir))
        
        # Calculate date range for 13-week period
        today = date.today()
        end_date = today
        start_date = today - timedelta(weeks=13)
        
        # Base query - get all employees (no is_active filter)
        query = db.session.query(
            Employee,
            func.coalesce(func.sum(OvertimeHistory.overtime_hours), 0).label('total_ot')
        ).outerjoin(
            OvertimeHistory,
            and_(
                Employee.id == OvertimeHistory.employee_id,
                OvertimeHistory.week_start_date >= start_date,
                OvertimeHistory.week_start_date <= end_date
            )
        ).group_by(Employee.id)
        
        # Apply filters
        if search_term:
            query = query.filter(
                or_(
                    Employee.name.ilike(f'%{search_term}%'),
                    Employee.employee_id.ilike(f'%{search_term}%')
                )
            )
        
        if crew_filter:
            query = query.filter(Employee.crew == crew_filter)
        
        if position_filter:
            query = query.filter(Employee.position_id == position_filter)
        
        # Apply OT range filter
        if ot_range_filter:
            if ot_range_filter == '0-50':
                query = query.having(func.coalesce(func.sum(OvertimeHistory.hours_worked), 0) <= 50)
            elif ot_range_filter == '50-100':
                query = query.having(
                    and_(
                        func.coalesce(func.sum(OvertimeHistory.hours_worked), 0) > 50,
                        func.coalesce(func.sum(OvertimeHistory.hours_worked), 0) <= 100
                    )
                )
            elif ot_range_filter == '100-150':
                query = query.having(
                    and_(
                        func.coalesce(func.sum(OvertimeHistory.hours_worked), 0) > 100,
                        func.coalesce(func.sum(OvertimeHistory.hours_worked), 0) <= 150
                    )
                )
            elif ot_range_filter == '150+':
                query = query.having(func.coalesce(func.sum(OvertimeHistory.hours_worked), 0) > 150)
        
        # Apply multi-level sorting
        if sort_levels:
            for sort_field, sort_dir in sort_levels:
                if sort_field == 'crew':
                    order_func = Employee.crew.asc() if sort_dir == 'asc' else Employee.crew.desc()
                elif sort_field == 'jobtitle':
                    # Join with Position table if needed
                    if not any(isinstance(j.left, type(Position.__table__)) for j in query._legacy_facade[0]._join_entities):
                        query = query.outerjoin(Position, Employee.position_id == Position.id)
                    order_func = Position.name.asc() if sort_dir == 'asc' else Position.name.desc()
                elif sort_field == 'seniority':
                    order_func = Employee.hire_date.asc() if sort_dir == 'asc' else Employee.hire_date.desc()
                elif sort_field == 'overtime':
                    order_func = func.coalesce(func.sum(OvertimeHistory.overtime_hours), 0)
                    order_func = order_func.asc() if sort_dir == 'asc' else order_func.desc()
                else:
                    continue
                
                query = query.order_by(order_func)
        else:
            # Default sort by overtime hours descending
            query = query.order_by(func.coalesce(func.sum(OvertimeHistory.overtime_hours), 0).desc())
        
        # Execute paginated query
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Process results for template
        employees = []
        total_overtime_hours = 0
        employees_with_overtime = 0
        high_overtime_employees = []
        
        for emp, total_ot in paginated.items:
            # Get weekly breakdown for this employee
            weekly_ot = OvertimeHistory.query.filter_by(
                employee_id=emp.id
            ).filter(
                OvertimeHistory.week_start_date >= start_date,
                OvertimeHistory.week_start_date <= end_date
            ).order_by(OvertimeHistory.week_start_date.desc()).all()
            
            # Calculate current week overtime
            current_week_start = today - timedelta(days=today.weekday())
            current_week_ot = sum(
                ot.overtime_hours for ot in weekly_ot 
                if ot.week_start_date >= current_week_start
            )
            
            # Calculate average weekly overtime
            avg_weekly_ot = round(total_ot / 13, 1) if total_ot > 0 else 0
            
            # Determine trend (simplified)
            if len(weekly_ot) >= 4:
                recent_avg = sum(ot.overtime_hours for ot in weekly_ot[:4]) / 4
                older_avg = sum(ot.overtime_hours for ot in weekly_ot[-4:]) / 4
                if recent_avg > older_avg * 1.1:
                    trend = 'increasing'
                elif recent_avg < older_avg * 0.9:
                    trend = 'decreasing'
                else:
                    trend = 'stable'
            else:
                trend = 'stable'
            
            # Calculate years employed
            if emp.hire_date:
                years_employed = (today - emp.hire_date).days // 365
            else:
                years_employed = 0
            
            # Add employee data
            employee_data = {
                'id': emp.id,
                'name': emp.name,
                'employee_id': emp.employee_id,
                'crew': emp.crew,
                'position': emp.position,
                'position_id': emp.position_id,
                'hire_date': emp.hire_date,
                'years_employed': years_employed,
                'last_13_weeks_overtime': int(total_ot),
                'current_week_overtime': int(current_week_ot),
                'average_weekly_overtime': avg_weekly_ot,
                'overtime_trend': trend,
                'weekly_breakdown': weekly_ot
            }
            
            employees.append(employee_data)
            
            # Update statistics
            total_overtime_hours += total_ot
            if total_ot > 0:
                employees_with_overtime += 1
            if avg_weekly_ot >= 15:  # High OT threshold
                high_overtime_employees.append(employee_data)
        
        # Calculate overall statistics
        all_employees_count = Employee.query.count()
        avg_overtime = round(total_overtime_hours / all_employees_count, 1) if all_employees_count > 0 else 0
        
        # Get all positions for filter dropdown
        positions = Position.query.order_by(Position.name).all()
        
        # Get pending counts for base.html navigation
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        
        # Prepare template context
        return render_template('overtime_management.html',
            # Employee data
            employees=employees,
            # Pagination
            page=page,
            total_pages=paginated.pages,
            total_employees=paginated.total,
            # Filters
            search_term=search_term,
            crew_filter=crew_filter,
            position_filter=position_filter,
            ot_range_filter=ot_range_filter,
            positions=positions,
            # Statistics
            total_overtime_hours=int(total_overtime_hours),
            employees_with_overtime=employees_with_overtime,
            avg_overtime=avg_overtime,
            high_overtime_count=len(high_overtime_employees),
            high_overtime_employees=high_overtime_employees,
            # Date range
            start_date=start_date,
            end_date=end_date,
            # Sort parameters (for maintaining state)
            sort_levels=sort_levels,
            # Variables for base.html
            pending_time_off=pending_time_off,
            pending_swaps=pending_swaps
        )
        
    except Exception as e:
        print(f"Overtime management error: {str(e)}")
        traceback.print_exc()
        flash('Error loading overtime data. Please try again.', 'error')
        
        # Return empty template on error
        return render_template('overtime_management.html',
            employees=[],
            page=1,
            total_pages=0,
            total_employees=0,
            search_term='',
            crew_filter='',
            position_filter='',
            ot_range_filter='',
            positions=[],
            total_overtime_hours=0,
            employees_with_overtime=0,
            avg_overtime=0,
            high_overtime_count=0,
            high_overtime_employees=[],
            start_date=date.today() - timedelta(weeks=13),
            end_date=date.today(),
            sort_levels=[],
            pending_time_off=0,
            pending_swaps=0
        )

# Keep existing utility routes below

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

# API Routes
@main_bp.route('/api/dashboard-stats')
@login_required
def api_dashboard_stats():
    """API endpoint for real-time dashboard statistics"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        today = date.today()
        
        stats = {
            'pending_time_off': TimeOffRequest.query.filter_by(status='pending').count(),
            'pending_swaps': ShiftSwapRequest.query.filter_by(status='pending').count(),
            'total_employees': Employee.query.count(),
            'coverage_gaps': len([g for g in get_coverage_gaps() if g['date'] == today]),
            'today_scheduled': Schedule.query.filter_by(date=today).count(),
            'critical_maintenance': MaintenanceIssue.query.filter_by(priority='critical', status='open').count()
        }
        
        return jsonify(stats)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@main_bp.route('/api/quick-schedule', methods=['POST'])
@login_required
def api_quick_schedule():
    """Quick schedule creation from dashboard"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Implementation for quick schedule creation
    return jsonify({'message': 'Feature coming soon'}), 501

@main_bp.route('/api/quick-alert', methods=['POST'])
@login_required
def api_quick_alert():
    """Send quick alerts from dashboard"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Implementation for quick alerts
    return jsonify({'message': 'Feature coming soon'}), 501
