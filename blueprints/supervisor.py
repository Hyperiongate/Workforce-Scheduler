# blueprints/supervisor.py
"""
Supervisor blueprint with all required routes and proper error handling
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from models import db, Employee, TimeOffRequest, ShiftSwapRequest, Schedule, Position, OvertimeHistory, PositionCoverage, VacationCalendar
from datetime import date, datetime, timedelta
from sqlalchemy import func, and_, or_, inspect
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

@supervisor_bp.route('/supervisor/dashboard')
@login_required
@supervisor_required
def dashboard():
    """Supervisor dashboard with complete data and proper error handling"""
    try:
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
            
            # User info
            'current_user': current_user,
            'today': date.today(),
            'now': datetime.now()
        }
        
        # CRITICAL: Clear any failed transactions first
        try:
            db.session.rollback()
            db.session.close()
            db.session.remove()
        except:
            pass
        
        # Get pending time off counts
        try:
            context['pending_time_off'] = TimeOffRequest.query.filter_by(status='pending').count()
        except Exception as e:
            current_app.logger.error(f"Error getting pending time off: {e}")
            db.session.rollback()
        
        # Get pending swaps - with schema check
        try:
            # Check if table exists and has required columns
            inspector = inspect(db.engine)
            
            if 'shift_swap_request' in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns('shift_swap_request')]
                
                if 'status' in columns:
                    context['pending_swaps'] = ShiftSwapRequest.query.filter_by(status='pending').count()
                else:
                    current_app.logger.warning("shift_swap_request table missing 'status' column")
                    context['pending_swaps'] = 0
            else:
                current_app.logger.warning("shift_swap_request table does not exist")
                context['pending_swaps'] = 0
                
        except Exception as e:
            current_app.logger.error(f"Error getting pending swaps: {e}")
            db.session.rollback()
            context['pending_swaps'] = 0
        
        # Get employee counts
        try:
            all_employees = Employee.query.filter_by(is_supervisor=False).all()
            context['total_employees'] = len(all_employees)
            
            # Count employees missing OT data
            for emp in all_employees:
                try:
                    ot_count = OvertimeHistory.query.filter_by(employee_id=emp.id).count()
                    if ot_count == 0:
                        context['employees_missing_ot'] += 1
                except:
                    # Skip if error
                    pass
                    
        except Exception as e:
            current_app.logger.error(f"Error counting employees: {e}")
            db.session.rollback()
        
        # Get high OT employees (>10 hours this week)
        try:
            week_start = date.today() - timedelta(days=date.today().weekday())
            high_ot = OvertimeHistory.query.filter(
                OvertimeHistory.week_start_date == week_start,
                OvertimeHistory.overtime_hours > 10
            ).all()
            
            context['high_ot_employees'] = [ot.employee for ot in high_ot if ot.employee]
        except Exception as e:
            current_app.logger.error(f"Error getting high OT employees: {e}")
            db.session.rollback()
        
        # Get recent time off requests
        try:
            context['recent_time_off'] = TimeOffRequest.query.order_by(
                TimeOffRequest.created_at.desc()
            ).limit(5).all()
        except Exception as e:
            current_app.logger.error(f"Error getting recent time off: {e}")
            db.session.rollback()
        
        # Calculate coverage gaps
        try:
            today = date.today()
            scheduled_today = Schedule.query.filter_by(date=today).count()
            
            # Check if Position table has min_coverage column
            inspector = inspect(db.engine)
            position_columns = [col['name'] for col in inspector.get_columns('position')]
            
            if 'min_coverage' in position_columns:
                required = db.session.query(func.sum(Position.min_coverage)).scalar() or 0
            else:
                # Use a default if column doesn't exist
                required = 20
                
            context['coverage_gaps'] = max(0, required - scheduled_today)
        except Exception as e:
            current_app.logger.error(f"Error calculating coverage gaps: {e}")
            db.session.rollback()
        
        # Try different template names in order of preference
        template_names = [
            'supervisor_dashboard.html',
            'dashboard_classic.html',
            'supervisor_dashboard_simple.html',
            'dashboard.html', 
            'supervisor/dashboard.html',
            'basic_dashboard.html'  # Emergency fallback
        ]
        
        for template_name in template_names:
            try:
                return render_template(template_name, **context)
            except Exception as e:
                current_app.logger.debug(f"Template {template_name} not found: {e}")
                continue
        
        # If no template found, create a minimal response
        flash('Dashboard template not found. Using emergency view.', 'warning')
        return f"""
        <html>
            <head><title>Supervisor Dashboard</title></head>
            <body>
                <h1>Supervisor Dashboard</h1>
                <p>Welcome, {current_user.name}!</p>
                <ul>
                    <li>Pending Time Off: {context['pending_time_off']}</li>
                    <li>Pending Swaps: {context['pending_swaps']}</li>
                    <li>Total Employees: {context['total_employees']}</li>
                    <li>Coverage Gaps: {context['coverage_gaps']}</li>
                </ul>
                <a href="/auth/logout">Logout</a>
            </body>
        </html>
        """
        
    except Exception as e:
        current_app.logger.error(f"Critical error in supervisor dashboard: {e}")
        current_app.logger.error(traceback.format_exc())
        
        # Ensure database session is clean
        try:
            db.session.rollback()
            db.session.close()
            db.session.remove()
        except:
            pass
        
        flash('An error occurred loading the dashboard. Please try again.', 'danger')
        return redirect(url_for('main.home') if hasattr(current_app, 'main') else '/')

@supervisor_bp.route('/supervisor/time-off-requests')
@login_required
@supervisor_required
def time_off_requests():
    """View and manage time off requests"""
    try:
        # Clear any failed transactions
        db.session.rollback()
        
        # Get filter parameters
        status_filter = request.args.get('status', 'all')
        crew_filter = request.args.get('crew', 'all')
        
        # Base query
        query = TimeOffRequest.query
        
        # Apply filters
        if status_filter != 'all':
            query = query.filter_by(status=status_filter)
        
        if crew_filter != 'all':
            query = query.join(Employee).filter(Employee.crew == crew_filter)
        
        # Get requests
        requests = query.order_by(TimeOffRequest.created_at.desc()).all()
        
        # Get statistics
        stats = {
            'pending_count': TimeOffRequest.query.filter_by(status='pending').count(),
            'approved_this_week': TimeOffRequest.query.filter(
                TimeOffRequest.status == 'approved',
                TimeOffRequest.created_at >= datetime.now() - timedelta(days=7)
            ).count(),
            'total_days_requested': 0
        }
        
        # Calculate total days with error handling
        try:
            result = db.session.query(
                func.sum(
                    func.julianday(TimeOffRequest.end_date) - 
                    func.julianday(TimeOffRequest.start_date) + 1
                )
            ).filter_by(status='pending').scalar()
            stats['total_days_requested'] = result or 0
        except:
            pass
        
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
        
        time_off.status = 'approved'
        time_off.approved_by_id = current_user.id
        time_off.approved_date = datetime.now()
        
        # Check if VacationCalendar has all required columns
        inspector = inspect(db.engine)
        if 'vacation_calendar' in inspector.get_table_names():
            vacation_columns = [col['name'] for col in inspector.get_columns('vacation_calendar')]
            
            # Create vacation entry with available columns
            vacation_data = {
                'employee_id': time_off.employee_id,
                'date': time_off.start_date,  # Single date entry
                'type': time_off.request_type
            }
            
            if 'status' in vacation_columns:
                vacation_data['status'] = 'approved'
            
            if 'request_id' in vacation_columns:
                vacation_data['request_id'] = time_off.id
                
            # Create an entry for each day
            current_date = time_off.start_date
            while current_date <= time_off.end_date:
                vacation_entry = VacationCalendar(**vacation_data)
                vacation_entry.date = current_date
                db.session.add(vacation_entry)
                current_date += timedelta(days=1)
        
        db.session.commit()
        
        flash(f'Time off request for {time_off.employee.name} has been approved.', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error approving time off: {e}")
        flash('Error approving request.', 'danger')
    
    return redirect(url_for('supervisor.time_off_requests'))

@supervisor_bp.route('/supervisor/deny-time-off/<int:request_id>', methods=['POST'])
@login_required
@supervisor_required
def deny_time_off(request_id):
    """Deny a time off request"""
    try:
        time_off = TimeOffRequest.query.get_or_404(request_id)
        
        if time_off.status != 'pending':
            flash('This request has already been processed.', 'warning')
            return redirect(url_for('supervisor.time_off_requests'))
        
        time_off.status = 'denied'
        time_off.approved_by_id = current_user.id
        time_off.approved_date = datetime.now()
        
        # Check if denial_reason column exists
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('time_off_request')]
        if 'denial_reason' in columns:
            time_off.denial_reason = request.form.get('denial_reason', 'No reason provided')
        
        db.session.commit()
        
        flash(f'Time off request for {time_off.employee.name} has been denied.', 'info')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error denying time off: {e}")
        flash('Error denying request.', 'danger')
    
    return redirect(url_for('supervisor.time_off_requests'))

@supervisor_bp.route('/supervisor/swap-requests')
@login_required
@supervisor_required
def swap_requests():
    """View and manage shift swap requests"""
    try:
        # Clear any failed transactions
        db.session.rollback()
        
        # Check if table exists and has required columns
        inspector = inspect(db.engine)
        
        swaps = []
        stats = {
            'pending_count': 0,
            'approved_this_week': 0
        }
        
        if 'shift_swap_request' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('shift_swap_request')]
            
            if 'status' in columns and 'created_at' in columns:
                swaps = ShiftSwapRequest.query.order_by(
                    ShiftSwapRequest.created_at.desc()
                ).all()
                
                stats['pending_count'] = ShiftSwapRequest.query.filter_by(status='pending').count()
                stats['approved_this_week'] = ShiftSwapRequest.query.filter(
                    ShiftSwapRequest.status == 'approved',
                    ShiftSwapRequest.created_at >= datetime.now() - timedelta(days=7)
                ).count()
        
        return render_template('swap_requests.html', swaps=swaps, stats=stats)
    
    except Exception as e:
        current_app.logger.error(f"Error in swap_requests: {e}")
        db.session.rollback()
        flash('Error loading swap requests.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/coverage-gaps')
@login_required
@supervisor_required
def coverage_gaps():
    """View coverage gaps"""
    try:
        # Clear any failed transactions
        db.session.rollback()
        
        # Get date range
        start_date = request.args.get('start_date', date.today())
        end_date = request.args.get('end_date', date.today() + timedelta(days=7))
        
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Get all positions and their requirements
        positions = Position.query.all()
        
        # Check if min_coverage column exists
        inspector = inspect(db.engine)
        position_columns = [col['name'] for col in inspector.get_columns('position')]
        has_min_coverage = 'min_coverage' in position_columns
        
        position_requirements = {}
        for p in positions:
            if has_min_coverage:
                position_requirements[p.id] = p.min_coverage or 0
            else:
                position_requirements[p.id] = 2  # Default requirement
        
        # Get schedules in date range
        schedules = Schedule.query.filter(
            Schedule.date >= start_date,
            Schedule.date <= end_date
        ).all()
        
        # Calculate gaps by date and position
        gaps = []
        current_date = start_date
        
        while current_date <= end_date:
            for position in positions:
                scheduled = len([s for s in schedules 
                               if s.date == current_date and s.position_id == position.id])
                required = position_requirements.get(position.id, 0)
                
                if scheduled < required:
                    gaps.append({
                        'date': current_date,
                        'position': position.name,
                        'scheduled': scheduled,
                        'required': required,
                        'gap': required - scheduled
                    })
            
            current_date += timedelta(days=1)
        
        return render_template('coverage_gaps.html',
                             gaps=gaps,
                             start_date=start_date,
                             end_date=end_date)
    
    except Exception as e:
        current_app.logger.error(f"Error in coverage_gaps: {e}")
        db.session.rollback()
        flash('Error loading coverage gaps.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/coverage-needs')
@login_required
@supervisor_required
def coverage_needs():
    """View and manage coverage needs"""
    try:
        # Clear any failed transactions
        db.session.rollback()
        
        # Get all positions
        positions = Position.query.order_by(Position.name).all()
        
        # Check if PositionCoverage table exists
        inspector = inspect(db.engine)
        has_position_coverage = 'position_coverage' in inspector.get_table_names()
        
        # Get coverage requirements by crew
        coverage_data = []
        for position in positions:
            crew_dict = {}
            
            if has_position_coverage:
                # Get current requirements
                crew_coverage = PositionCoverage.query.filter_by(position_id=position.id).all()
                crew_dict = {pc.crew: pc.required_count for pc in crew_coverage}
            
            # Check if position has min_coverage
            position_columns = [col['name'] for col in inspector.get_columns('position')]
            min_coverage = 0
            if 'min_coverage' in position_columns:
                min_coverage = position.min_coverage or 0
            
            coverage_data.append({
                'position': position,
                'department': getattr(position, 'department', 'Unknown'),
                'min_coverage': min_coverage,
                'crew_coverage': {
                    'A': crew_dict.get('A', 0),
                    'B': crew_dict.get('B', 0),
                    'C': crew_dict.get('C', 0),
                    'D': crew_dict.get('D', 0)
                }
            })
        
        # Get current staffing levels
        staffing = {}
        for crew in ['A', 'B', 'C', 'D']:
            crew_employees = Employee.query.filter_by(crew=crew, is_supervisor=False).all()
            staffing[crew] = {
                'total': len(crew_employees),
                'by_position': {}
            }
            
            for emp in crew_employees:
                if emp.position:
                    pos_name = emp.position.name
                    staffing[crew]['by_position'][pos_name] = staffing[crew]['by_position'].get(pos_name, 0) + 1
        
        return render_template('coverage_needs.html',
                             coverage_data=coverage_data,
                             staffing=staffing)
    
    except Exception as e:
        current_app.logger.error(f"Error in coverage_needs: {e}")
        db.session.rollback()
        flash('Error loading coverage needs.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/update-coverage', methods=['POST'])
@login_required
@supervisor_required
def update_coverage():
    """Update position coverage requirements"""
    try:
        position_id = request.form.get('position_id')
        position = Position.query.get_or_404(position_id)
        
        # Check if columns exist
        inspector = inspect(db.engine)
        position_columns = [col['name'] for col in inspector.get_columns('position')]
        has_position_coverage = 'position_coverage' in inspector.get_table_names()
        
        # Update minimum coverage if column exists
        if 'min_coverage' in position_columns:
            min_coverage = request.form.get('min_coverage', type=int)
            if min_coverage is not None:
                position.min_coverage = min_coverage
        
        # Update crew-specific coverage if table exists
        if has_position_coverage:
            for crew in ['A', 'B', 'C', 'D']:
                required = request.form.get(f'crew_{crew}', type=int)
                if required is not None:
                    # Find or create coverage record
                    coverage = PositionCoverage.query.filter_by(
                        position_id=position_id,
                        crew=crew
                    ).first()
                    
                    if coverage:
                        coverage.required_count = required
                    else:
                        coverage = PositionCoverage(
                            position_id=position_id,
                            crew=crew,
                            required_count=required
                        )
                        db.session.add(coverage)
        
        db.session.commit()
        flash(f'Coverage requirements updated for {position.name}', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating coverage: {e}")
        flash('Error updating coverage requirements.', 'danger')
    
    return redirect(url_for('supervisor.coverage_needs'))

@supervisor_bp.route('/supervisor/overtime-distribution')
@login_required
@supervisor_required
def overtime_distribution():
    """View overtime distribution"""
    try:
        # Clear any failed transactions
        db.session.rollback()
        
        # Get all employees with their OT data
        employees = Employee.query.filter_by(is_supervisor=False).all()
        
        # Calculate OT statistics
        ot_data = []
        for emp in employees:
            try:
                # Get last 13 weeks of OT
                thirteen_weeks_ago = date.today() - timedelta(weeks=13)
                ot_records = OvertimeHistory.query.filter(
                    OvertimeHistory.employee_id == emp.id,
                    OvertimeHistory.week_start_date >= thirteen_weeks_ago
                ).all()
                
                total_ot = sum(record.overtime_hours for record in ot_records)
                avg_ot = total_ot / 13 if ot_records else 0
                
                # Get current week OT
                current_week_start = date.today() - timedelta(days=date.today().weekday())
                current_ot = OvertimeHistory.query.filter_by(
                    employee_id=emp.id,
                    week_start_date=current_week_start
                ).first()
                
                ot_data.append({
                    'employee': emp,
                    'total_13_weeks': total_ot,
                    'average_weekly': round(avg_ot, 1),
                    'current_week': current_ot.overtime_hours if current_ot else 0,
                    'weeks_with_data': len(ot_records)
                })
            except:
                # If error, add employee with zero data
                ot_data.append({
                    'employee': emp,
                    'total_13_weeks': 0,
                    'average_weekly': 0,
                    'current_week': 0,
                    'weeks_with_data': 0
                })
        
        # Sort by total OT (ascending for fair distribution)
        ot_data.sort(key=lambda x: x['total_13_weeks'])
        
        return render_template('overtime_distribution.html', 
                             overtime_data=ot_data)
    
    except Exception as e:
        current_app.logger.error(f"Error in overtime_distribution: {e}")
        db.session.rollback()
        flash('Error loading overtime distribution.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/vacation-calendar')
@login_required
@supervisor_required
def vacation_calendar():
    """Display vacation calendar"""
    try:
        # Clear any failed transactions
        db.session.rollback()
        
        # Get month and year from request
        month = request.args.get('month', type=int, default=date.today().month)
        year = request.args.get('year', type=int, default=date.today().year)
        
        # Get all vacation entries for the month
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)
        
        # Check if VacationCalendar table exists
        inspector = inspect(db.engine)
        if 'vacation_calendar' not in inspector.get_table_names():
            flash('Vacation calendar not available.', 'warning')
            return redirect(url_for('supervisor.dashboard'))
        
        # Build query based on available columns
        columns = [col['name'] for col in inspector.get_columns('vacation_calendar')]
        
        query = VacationCalendar.query
        
        # Filter by date range
        if 'date' in columns:
            query = query.filter(
                VacationCalendar.date >= start_date,
                VacationCalendar.date <= end_date
            )
        elif 'start_date' in columns and 'end_date' in columns:
            query = query.filter(
                or_(
                    and_(VacationCalendar.start_date >= start_date, 
                         VacationCalendar.start_date <= end_date),
                    and_(VacationCalendar.end_date >= start_date, 
                         VacationCalendar.end_date <= end_date),
                    and_(VacationCalendar.start_date < start_date, 
                         VacationCalendar.end_date > end_date)
                )
            )
        
        # Filter by status if column exists
        if 'status' in columns:
            query = query.filter_by(status='approved')
        
        vacations = query.all()
        
        # Group by crew
        crew_vacations = {'A': [], 'B': [], 'C': [], 'D': []}
        for vacation in vacations:
            if vacation.employee and vacation.employee.crew in crew_vacations:
                crew_vacations[vacation.employee.crew].append(vacation)
        
        return render_template('vacation_calendar.html',
                             month=month,
                             year=year,
                             crew_vacations=crew_vacations,
                             start_date=start_date,
                             end_date=end_date)
    
    except Exception as e:
        current_app.logger.error(f"Error in vacation_calendar: {e}")
        db.session.rollback()
        flash('Error loading vacation calendar.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/api/vacation-calendar')
@login_required
@supervisor_required
def api_vacation_calendar():
    """API endpoint for vacation calendar data"""
    try:
        # Clear any failed transactions
        db.session.rollback()
        
        start_date = request.args.get('start')
        end_date = request.args.get('end')
        
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        else:
            start_date = date.today().replace(day=1)
            
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        # Check table structure
        inspector = inspect(db.engine)
        if 'vacation_calendar' not in inspector.get_table_names():
            return jsonify([])
        
        columns = [col['name'] for col in inspector.get_columns('vacation_calendar')]
        
        # Build query based on available columns
        query = VacationCalendar.query
        
        if 'date' in columns:
            query = query.filter(
                VacationCalendar.date >= start_date,
                VacationCalendar.date <= end_date
            )
        elif 'start_date' in columns and 'end_date' in columns:
            query = query.filter(
                or_(
                    and_(VacationCalendar.start_date >= start_date, 
                         VacationCalendar.start_date <= end_date),
                    and_(VacationCalendar.end_date >= start_date, 
                         VacationCalendar.end_date <= end_date),
                    and_(VacationCalendar.start_date < start_date, 
                         VacationCalendar.end_date > end_date)
                )
            )
        
        if 'status' in columns:
            query = query.filter_by(status='approved')
        
        vacations = query.all()
        
        # Format for FullCalendar
        events = []
        for vacation in vacations:
            if vacation.employee:
                color = {
                    'A': '#28a745',
                    'B': '#17a2b8', 
                    'C': '#ffc107',
                    'D': '#dc3545'
                }.get(vacation.employee.crew, '#6c757d')
                
                # Determine date range
                if hasattr(vacation, 'date'):
                    start = vacation.date
                    end = vacation.date + timedelta(days=1)
                elif hasattr(vacation, 'start_date') and hasattr(vacation, 'end_date'):
                    start = vacation.start_date
                    end = vacation.end_date + timedelta(days=1)
                else:
                    continue
                
                events.append({
                    'id': vacation.id,
                    'title': f"{vacation.employee.name} ({vacation.type})",
                    'start': start.isoformat(),
                    'end': end.isoformat(),
                    'color': color,
                    'crew': vacation.employee.crew,
                    'employee_id': vacation.employee_id,
                    'type': vacation.type
                })
        
        return jsonify(events)
        
    except Exception as e:
        current_app.logger.error(f"Error in api_vacation_calendar: {e}")
        db.session.rollback()
        return jsonify({'error': 'Failed to load calendar data'}), 500

@supervisor_bp.route('/supervisor/employee-management')
@login_required
@supervisor_required
def employee_management():
    """Employee management page"""
    try:
        # Clear any failed transactions
        db.session.rollback()
        
        employees = Employee.query.order_by(Employee.crew, Employee.name).all()
        positions = Position.query.order_by(Position.name).all()
        
        # Get crew statistics
        crew_stats = {}
        for crew in ['A', 'B', 'C', 'D']:
            crew_employees = [e for e in employees if e.crew == crew]
            crew_stats[crew] = {
                'total': len(crew_employees),
                'supervisors': len([e for e in crew_employees if e.is_supervisor])
            }
        
        return render_template('employee_management.html',
                             employees=employees,
                             positions=positions,
                             crew_stats=crew_stats)
    
    except Exception as e:
        current_app.logger.error(f"Error in employee_management: {e}")
        db.session.rollback()
        flash('Error loading employee management.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/crew-management') 
@login_required
@supervisor_required
def crew_management():
    """Crew management interface"""
    try:
        # Clear any failed transactions
        db.session.rollback()
        
        # Get all employees grouped by crew
        crews = {}
        for crew_name in ['A', 'B', 'C', 'D', 'Unassigned']:
            if crew_name == 'Unassigned':
                crew_employees = Employee.query.filter(
                    or_(Employee.crew == None, Employee.crew == '')
                ).order_by(Employee.name).all()
            else:
                crew_employees = Employee.query.filter_by(crew=crew_name).order_by(Employee.name).all()
            
            crews[crew_name] = crew_employees
        
        # Get positions for assignment
        positions = Position.query.order_by(Position.name).all()
        
        # Calculate crew statistics
        crew_stats = {}
        for crew_name in ['A', 'B', 'C', 'D']:
            crew_stats[crew_name] = {
                'total': len(crews.get(crew_name, [])),
                'positions': {},
                'supervisor_count': len([e for e in crews.get(crew_name, []) if e.is_supervisor])
            }
            
            # Count positions
            for emp in crews.get(crew_name, []):
                if emp.position:
                    pos_name = emp.position.name
                    crew_stats[crew_name]['positions'][pos_name] = \
                        crew_stats[crew_name]['positions'].get(pos_name, 0) + 1
        
        return render_template('crew_management.html',
                             crews=crews,
                             positions=positions,
                             crew_stats=crew_stats)
    
    except Exception as e:
        current_app.logger.error(f"Error in crew_management: {e}")
        db.session.rollback()
        flash('Error loading crew management.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/update-crew', methods=['POST'])
@login_required
@supervisor_required
def update_crew():
    """Update employee crew assignment"""
    try:
        employee_id = request.form.get('employee_id')
        new_crew = request.form.get('new_crew')
        
        employee = Employee.query.get_or_404(employee_id)
        old_crew = employee.crew
        
        employee.crew = new_crew if new_crew != 'Unassigned' else None
        db.session.commit()
        
        flash(f'{employee.name} moved from Crew {old_crew or "Unassigned"} to Crew {new_crew}', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating crew: {e}")
        flash('Error updating crew assignment.', 'danger')
    
    return redirect(url_for('supervisor.crew_management'))

# Template download routes
@supervisor_bp.route('/supervisor/download-employee-template')
@login_required
@supervisor_required
def download_employee_template():
    """Download employee upload template"""
    try:
        # Clear any failed transactions
        db.session.rollback()
        
        from utils.excel_templates_generator import generate_employee_template
        
        filepath = generate_employee_template()
        return send_file(filepath, as_attachment=True, 
                        download_name='employee_upload_template.xlsx')
                        
    except Exception as e:
        current_app.logger.error(f"Error generating template: {e}")
        flash('Error generating template.', 'danger')
        return redirect(url_for('supervisor.employee_management'))

@supervisor_bp.route('/supervisor/download-current-employees')
@login_required
@supervisor_required
def download_current_employees():
    """Export current employee list"""
    try:
        # Clear any failed transactions
        db.session.rollback()
        
        employees = Employee.query.filter_by(is_supervisor=False).all()
        
        # Create DataFrame
        data = []
        for emp in employees:
            data.append({
                'Employee ID': emp.employee_id,
                'First Name': emp.name.split()[0] if emp.name else '',
                'Last Name': emp.name.split()[-1] if emp.name and len(emp.name.split()) > 1 else '',
                'Email': emp.email,
                'Crew': emp.crew or '',
                'Position': emp.position.name if emp.position else '',
                'Department': getattr(emp.position, 'department', '') if emp.position else ''
            })
        
        df = pd.DataFrame(data)
        
        # Save to Excel
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
        os.makedirs(upload_folder, exist_ok=True)
        
        filepath = os.path.join(upload_folder, 
                               f'employees_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
        df.to_excel(filepath, index=False)
        
        return send_file(filepath, as_attachment=True)
        
    except Exception as e:
        current_app.logger.error(f"Error exporting employees: {e}")
        db.session.rollback()
        flash('Error exporting employee data.', 'danger')
        return redirect(url_for('supervisor.employee_management'))

# API endpoints
@supervisor_bp.route('/api/dashboard-stats')
@login_required
@supervisor_required
def api_dashboard_stats():
    """API endpoint for real-time dashboard statistics"""
    try:
        # Clear any failed transactions
        db.session.rollback()
        
        stats = {
            'pending_time_off': 0,
            'pending_swaps': 0,
            'coverage_gaps': 0,
            'total_employees': 0,
            'employees_on_leave': 0,
            'last_updated': datetime.now().strftime('%H:%M:%S')
        }
        
        # Get basic counts with error handling
        try:
            stats['pending_time_off'] = TimeOffRequest.query.filter_by(status='pending').count()
        except:
            pass
            
        try:
            # Check if shift_swap_request has status column
            inspector = inspect(db.engine)
            if 'shift_swap_request' in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns('shift_swap_request')]
                if 'status' in columns:
                    stats['pending_swaps'] = ShiftSwapRequest.query.filter_by(status='pending').count()
        except:
            pass
            
        try:
            stats['total_employees'] = Employee.query.filter_by(is_supervisor=False).count()
        except:
            pass
        
        # Calculate coverage gaps
        try:
            today = date.today()
            scheduled = Schedule.query.filter_by(date=today).count()
            
            # Check if Position has min_coverage
            inspector = inspect(db.engine)
            position_columns = [col['name'] for col in inspector.get_columns('position')]
            
            if 'min_coverage' in position_columns:
                required = db.session.query(func.sum(Position.min_coverage)).scalar() or 0
            else:
                required = 20  # Default
                
            stats['coverage_gaps'] = max(0, required - scheduled)
        except:
            pass
        
        # Count employees on leave today
        try:
            today = date.today()
            stats['employees_on_leave'] = TimeOffRequest.query.filter(
                TimeOffRequest.status == 'approved',
                TimeOffRequest.start_date <= today,
                TimeOffRequest.end_date >= today
            ).count()
        except:
            pass
        
        return jsonify(stats)
    
    except Exception as e:
        current_app.logger.error(f"Error in api_dashboard_stats: {e}")
        return jsonify({'error': 'Failed to load statistics'}), 500
