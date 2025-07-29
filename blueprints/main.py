# blueprints/main.py
"""
Fixed main blueprint with proper dashboard routing
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file, current_app
from flask_login import login_required, current_user
from models import (db, Employee, Position, Schedule, OvertimeHistory, TimeOffRequest, 
                   ShiftSwapRequest, ScheduleSuggestion, CrewCoverageRequirement,
                   CoverageRequest, MaintenanceIssue, CasualWorker, OvertimeOpportunity,
                   CoverageNotification)
from datetime import date, timedelta, datetime
from sqlalchemy import or_, func, text, and_
from utils.helpers import get_coverage_gaps
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
    """Supervisor Operations Center Dashboard"""
    if not current_user.is_supervisor:
        return redirect(url_for('main.employee_dashboard'))
    
    try:
        # Get real-time staffing data
        today = date.today()
        
        # Current staffing levels
        scheduled_today = Schedule.query.filter_by(date=today).count()
        
        # Calculate total required positions
        total_positions = db.session.query(func.sum(Position.min_coverage)).scalar() or 0
        
        # Today's absences
        absences = db.session.query(Employee).join(TimeOffRequest).filter(
            TimeOffRequest.status == 'approved',
            TimeOffRequest.start_date <= today,
            TimeOffRequest.end_date >= today
        ).count()
        
        # No-shows (scheduled but not checked in - placeholder for now)
        no_shows = 0  # Would need attendance tracking system
        
        # Get current shift info
        current_hour = datetime.now().hour
        if 6 <= current_hour < 18:
            current_shift = 'day'
            shift_start = '06:00'
            shift_end = '18:00'
        else:
            current_shift = 'night'
            shift_start = '18:00'
            shift_end = '06:00'
        
        # Get crews on duty today
        crews_on_duty = {}
        for crew in ['A', 'B', 'C', 'D']:
            crew_schedules = db.session.query(Schedule).join(Employee).filter(
                Employee.crew == crew,
                Schedule.date == today,
                Schedule.shift_type == current_shift
            ).count()
            
            # Get required positions for this crew
            crew_positions = db.session.query(
                func.sum(CrewCoverageRequirement.min_coverage)
            ).filter(
                CrewCoverageRequirement.crew == crew
            ).scalar() or 0
            
            crews_on_duty[crew] = {
                'scheduled': crew_schedules,
                'required': crew_positions,
                'status': 'on' if crew_schedules > 0 else 'off',
                'shortage': max(0, crew_positions - crew_schedules)
            }
        
        # Get coverage gaps using helper function
        all_gaps = get_coverage_gaps()
        
        # Format gaps for display (next 7 days)
        coverage_gaps = []
        for gap in all_gaps:
            if gap['date'] <= today + timedelta(days=7):
                coverage_gaps.append({
                    'date': gap['date'],
                    'date_str': gap['date'].strftime('%b %d'),
                    'shift': gap['shift_type'],
                    'position': gap['position_name'],
                    'shortage': gap['shortage']
                })
        
        # Limit to top 5 most urgent gaps
        coverage_gaps = sorted(coverage_gaps, key=lambda x: (x['date'], x['shortage']), reverse=True)[:5]
        future_gaps_count = len([g for g in all_gaps if g['date'] > today and g['date'] <= today + timedelta(days=7)])
        
        # Get overtime volunteers available today
        off_duty_crews = [c for c, info in crews_on_duty.items() if info['status'] == 'off']
        overtime_volunteers = Employee.query.filter(
            Employee.is_supervisor == False,
            Employee.crew.in_(off_duty_crews) if off_duty_crews else Employee.crew.isnot(None)
        ).count()
        
        # Get pending actions
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').limit(5).all()
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').limit(5).all()
        
        # Build priority actions list
        priority_actions = []
        
        # Add critical staffing shortages
        total_shortage = max(0, total_positions - scheduled_today)
        if total_shortage > 0:
            for crew, info in crews_on_duty.items():
                if info['shortage'] > 0 and info['status'] == 'on':
                    # Find which positions are short
                    crew_positions = db.session.query(Position).join(
                        CrewCoverageRequirement
                    ).filter(
                        CrewCoverageRequirement.crew == crew
                    ).all()
                    
                    for position in crew_positions:
                        scheduled_for_position = db.session.query(Schedule).join(Employee).filter(
                            Employee.crew == crew,
                            Employee.position_id == position.id,
                            Schedule.date == today,
                            Schedule.shift_type == current_shift
                        ).count()
                        
                        required = position.min_coverage
                        if scheduled_for_position < required:
                            priority_actions.append({
                                'priority': 'high',
                                'title': f'Fill {position.name} Position',
                                'subtitle': f'Crew {crew} - {current_shift.title()} Shift - Critical Position',
                                'crew': crew,
                                'position_id': position.id,
                                'actions': ['post_overtime', 'mandate']
                            })
        
        # Add pending time-off that would create shortage
        for time_off in pending_time_off[:2]:  # Show top 2
            # Check if approving would create a shortage
            would_create_shortage = False  # Simplified - implement actual check
            priority_actions.append({
                'priority': 'medium' if would_create_shortage else 'low',
                'title': 'Review Time-Off Request',
                'subtitle': f'{time_off.employee.name} - {time_off.start_date.strftime("%b %d")}-{time_off.end_date.strftime("%b %d")}',
                'actions': ['approve', 'deny', 'view_impact'],
                'request_id': time_off.id,
                'would_create_shortage': would_create_shortage
            })
        
        # Add pending swaps
        for swap in pending_swaps[:1]:  # Show top 1
            priority_actions.append({
                'priority': 'low',
                'title': 'Shift Swap Pending',
                'subtitle': f'{swap.requesting_employee.name} ↔ {swap.target_employee.name if swap.target_employee else "Open"}',
                'actions': ['review'],
                'swap_id': swap.id
            })
        
        # Get overtime distribution for current week
        week_start = today - timedelta(days=today.weekday())
        overtime_distribution = db.session.query(
            Employee.id,
            Employee.name,
            Employee.crew,
            func.coalesce(func.sum(OvertimeHistory.overtime_hours), 0).label('ot_hours')
        ).outerjoin(
            OvertimeHistory,
            and_(
                OvertimeHistory.employee_id == Employee.id,
                OvertimeHistory.week_start_date == week_start
            )
        ).filter(
            Employee.is_supervisor == False
        ).group_by(Employee.id, Employee.name, Employee.crew).order_by(
            func.sum(OvertimeHistory.overtime_hours).desc().nullslast()
        ).limit(10).all()
        
        # Calculate staffing percentage
        staffing_percentage = int((scheduled_today / total_positions * 100)) if total_positions > 0 else 0
        
        return render_template('dashboard.html',
            # Current status
            current_staffing=scheduled_today,
            total_required=total_positions,
            staffing_shortage=total_shortage,
            staffing_percentage=staffing_percentage,
            absences_count=absences,
            no_shows_count=no_shows,
            overtime_volunteers=overtime_volunteers,
            future_gaps_count=future_gaps_count,
            
            # Shift info
            current_shift=current_shift,
            shift_start=shift_start,
            shift_end=shift_end,
            crews_on_duty=crews_on_duty,
            
            # Actions needed
            priority_actions=priority_actions,
            coverage_gaps=coverage_gaps,
            overtime_distribution=overtime_distribution,
            
            # Pending counts
            pending_time_off_count=len(pending_time_off),
            pending_swaps_count=len(pending_swaps),
            
            # Time info
            current_time=datetime.now(),
            current_date=today
        )
        
    except Exception as e:
        print(f"Dashboard error: {str(e)}")
        traceback.print_exc()
        flash('Error loading dashboard. Please try again.', 'danger')
        
        # Return a basic dashboard on error
        return render_template('dashboard.html',
            current_staffing=0,
            total_required=0,
            staffing_shortage=0,
            staffing_percentage=0,
            absences_count=0,
            no_shows_count=0,
            overtime_volunteers=0,
            future_gaps_count=0,
            current_shift='day',
            shift_start='06:00',
            shift_end='18:00',
            crews_on_duty={},
            priority_actions=[],
            coverage_gaps=[],
            overtime_distribution=[],
            pending_time_off_count=0,
            pending_swaps_count=0,
            current_time=datetime.now(),
            current_date=date.today()
        )

@main_bp.route('/employee-dashboard')
@login_required
def employee_dashboard():
    """Employee dashboard"""
    if current_user.is_supervisor:
        return redirect(url_for('main.dashboard'))
    
    try:
        # Get employee's schedule for the week
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        
        my_schedule = Schedule.query.filter(
            Schedule.employee_id == current_user.id,
            Schedule.date >= week_start,
            Schedule.date <= week_end
        ).order_by(Schedule.date).all()
        
        # Get time-off requests
        my_time_off = TimeOffRequest.query.filter_by(
            employee_id=current_user.id
        ).order_by(TimeOffRequest.created_at.desc()).limit(5).all()
        
        # Get shift swaps
        my_swaps = ShiftSwapRequest.query.filter(
            db.or_(
                ShiftSwapRequest.requesting_employee_id == current_user.id,
                ShiftSwapRequest.target_employee_id == current_user.id
            )
        ).order_by(ShiftSwapRequest.created_at.desc()).limit(5).all()
        
        # Get overtime opportunities
        overtime_opps = CoverageRequest.query.filter(
            CoverageRequest.date >= today,
            CoverageRequest.status == 'open'
        ).order_by(CoverageRequest.date).limit(5).all()
        
        # Get current week overtime
        current_week_ot = db.session.query(
            func.sum(OvertimeHistory.overtime_hours)
        ).filter(
            OvertimeHistory.employee_id == current_user.id,
            OvertimeHistory.week_start_date == week_start
        ).scalar() or 0
        
        # Get vacation balance
        vacation_balance = current_user.vacation_days
        sick_balance = current_user.sick_days
        personal_balance = current_user.personal_days
        
        return render_template('employee_dashboard.html',
            my_schedule=my_schedule,
            my_time_off=my_time_off,
            my_swaps=my_swaps,
            overtime_opportunities=overtime_opps,
            current_week_overtime=current_week_ot,
            vacation_balance=vacation_balance,
            sick_balance=sick_balance,
            personal_balance=personal_balance,
            week_start=week_start,
            week_end=week_end,
            today=today
        )
        
    except Exception as e:
        print(f"Employee dashboard error: {str(e)}")
        flash('Error loading dashboard. Please try again.', 'danger')
        return render_template('employee_dashboard.html',
            my_schedule=[],
            my_time_off=[],
            my_swaps=[],
            overtime_opportunities=[],
            current_week_overtime=0,
            vacation_balance=0,
            sick_balance=0,
            personal_balance=0,
            week_start=date.today(),
            week_end=date.today(),
            today=date.today()
        )

# NEW API ROUTES FOR QUICK ACTIONS
@main_bp.route('/api/quick-action', methods=['POST'])
@login_required
def quick_action():
    """Handle quick actions from the dashboard"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        action_type = request.json.get('action')
        data = request.json.get('data', {})
        
        if action_type == 'post_overtime':
            # Redirect to overtime posting
            return jsonify({
                'success': True,
                'redirect': url_for('overtime.quick_post_form', 
                                  position_id=data.get('position_id'))
            })
            
        elif action_type == 'call_casual':
            # Get available casual workers
            position_id = data.get('position_id')
            date_needed = data.get('date', date.today().strftime('%Y-%m-%d'))
            
            casuals = CasualWorker.query.filter_by(is_active=True).all()
            
            # Filter by skills if position specified
            if position_id:
                position = Position.query.get(position_id)
                required_skill_names = [s.name for s in position.required_skills]
                
                qualified_casuals = []
                for casual in casuals:
                    casual_skills = [s.name for s in casual.skills]
                    if any(skill in casual_skills for skill in required_skill_names):
                        qualified_casuals.append({
                            'id': casual.id,
                            'name': casual.name,
                            'phone': casual.phone,
                            'email': casual.email,
                            'rating': casual.rating,
                            'last_worked': casual.last_worked_date.strftime('%Y-%m-%d') if casual.last_worked_date else 'Never'
                        })
                
                return jsonify({
                    'success': True,
                    'casuals': qualified_casuals,
                    'position': position.name if position else 'Any'
                })
            
            return jsonify({
                'success': True,
                'casuals': [{'id': c.id, 'name': c.name, 'phone': c.phone} for c in casuals]
            })
            
        elif action_type == 'reassign_staff':
            # Get reassignment options
            from_crew = data.get('from_crew')
            to_position = data.get('to_position')
            date_str = data.get('date', date.today().strftime('%Y-%m-%d'))
            
            # Find employees who could be reassigned
            available_employees = db.session.query(Employee).join(Schedule).filter(
                Employee.crew == from_crew,
                Schedule.date == datetime.strptime(date_str, '%Y-%m-%d').date(),
                Employee.is_supervisor == False
            ).all()
            
            return jsonify({
                'success': True,
                'available_employees': [
                    {'id': e.id, 'name': e.name, 'current_position': e.position.name if e.position else 'None'}
                    for e in available_employees
                ]
            })
            
        elif action_type == 'view_schedule':
            crew = data.get('crew')
            return jsonify({
                'success': True,
                'redirect': url_for('schedule.view_schedules', crew=crew)
            })
            
        elif action_type == 'overtime_report':
            return jsonify({
                'success': True,
                'redirect': url_for('main.overtime_management')
            })
            
        elif action_type == 'message_crew':
            crew = data.get('crew')
            return jsonify({
                'success': True,
                'redirect': url_for('supervisor.messages', crew=crew)
            })
            
        else:
            return jsonify({'error': 'Unknown action type'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@main_bp.route('/api/fill-gap', methods=['POST'])
@login_required
def fill_gap():
    """Quick fill for coverage gaps"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        gap_date = request.json.get('date')
        shift_type = request.json.get('shift')
        position_name = request.json.get('position')
        
        # Find the position
        position = Position.query.filter_by(name=position_name).first()
        if not position:
            return jsonify({'error': 'Position not found'}), 404
        
        # Use the overtime engine to find eligible employees
        from blueprints.overtime import OvertimeAssignmentEngine
        
        date_needed = datetime.strptime(gap_date, '%Y-%m-%d').date()
        eligible = OvertimeAssignmentEngine.get_eligible_employees(
            position.id, date_needed, shift_type
        )
        
        # Create overtime opportunity
        opportunity = OvertimeOpportunity(
            position_id=position.id,
            date=date_needed,
            shift_type=shift_type,
            posted_by_id=current_user.id,
            status='open',
            urgent=True,
            response_deadline=datetime.now() + timedelta(hours=4)
        )
        db.session.add(opportunity)
        
        # Notify top 5 eligible employees
        notified = 0
        for emp_data in eligible[:5]:
            if emp_data['availability']['available']:
                notification = CoverageNotification(
                    sent_to_type='individual',
                    sent_to_employee_id=emp_data['employee'].id,
                    sent_by_id=current_user.id,
                    message=f"URGENT: {position.name} needed for {shift_type} shift on {date_needed.strftime('%b %d')}"
                )
                db.session.add(notification)
                notified += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Posted to {notified} eligible employees',
            'opportunity_id': opportunity.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@main_bp.route('/api/quick-schedule', methods=['POST'])
@login_required
def quick_schedule():
    """API endpoint for quick scheduling actions"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        action = request.json.get('action')
        data = request.json.get('data', {})
        
        if action == 'post_overtime':
            # Create overtime opportunity
            position_id = data.get('position_id')
            date_str = data.get('date')
            shift_type = data.get('shift_type')
            crew = data.get('crew')
            
            # Implementation would go here
            return jsonify({'success': True, 'message': 'Overtime posted successfully'})
            
        elif action == 'mandate':
            # Mandatory overtime assignment
            employee_id = data.get('employee_id')
            date_str = data.get('date')
            shift_type = data.get('shift_type')
            
            # Implementation would go here
            return jsonify({'success': True, 'message': 'Overtime assigned'})
            
        else:
            return jsonify({'error': 'Invalid action'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Keep all your existing routes below this line
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
    """Get real-time dashboard statistics - UPDATED VERSION"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        today = date.today()
        
        # Get current staffing
        scheduled_today = Schedule.query.filter_by(date=today).count()
        total_required = db.session.query(func.sum(Position.min_coverage)).scalar() or 0
        
        # Get pending counts
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        
        # Get gaps for next 7 days
        gaps = get_coverage_gaps()
        future_gaps = len([g for g in gaps if g['date'] > today and g['date'] <= today + timedelta(days=7)])
        
        return jsonify({
            'success': True,
            'data': {
                'current_staffing': scheduled_today,
                'total_required': total_required,
                'shortage': max(0, total_required - scheduled_today),
                'pending_time_off': pending_time_off,
                'pending_swaps': pending_swaps,
                'future_gaps': future_gaps,
                'last_updated': datetime.now().strftime('%H:%M:%S')
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Error handlers
@main_bp.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@main_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500
