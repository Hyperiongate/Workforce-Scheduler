from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, Schedule, VacationCalendar, Employee, Position, Skill, TimeOffRequest, ShiftSwapRequest, CircadianProfile, CoverageNotification, OvertimeHistory
from datetime import date, timedelta, datetime
from sqlalchemy import or_, func

employee_bp = Blueprint('employee', __name__)

@employee_bp.route('/view-employees-crews')
@login_required
def view_employees_crews():
    """View all employees and their crew assignments"""
    # Get all employees grouped by crew
    crews = {}
    employees = Employee.query.order_by(Employee.crew, Employee.name).all()
    
    for employee in employees:
        crew_name = employee.crew or 'Unassigned'
        if crew_name not in crews:
            crews[crew_name] = []
        crews[crew_name].append(employee)
    
    # Get positions
    positions = Position.query.all()
    
    # Get skills
    skills = Skill.query.all()
    
    # Calculate statistics
    stats = {
        'total_employees': len(employees),
        'total_crews': len([c for c in crews if c != 'Unassigned']),
        'total_supervisors': len([e for e in employees if e.is_supervisor]),
        'unassigned': len(crews.get('Unassigned', []))
    }
    
    return render_template('view_employees_crews.html',
                         crews=crews,
                         positions=positions,
                         skills=skills,
                         stats=stats)

@employee_bp.route('/overtime-management')
@login_required
def overtime_management():
    """View and manage overtime tracking"""
    # Check if user is supervisor
    if not current_user.is_supervisor:
        flash('You must be a supervisor to access this page.', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        # Get all active employees
        employees = Employee.query.filter_by(is_active=True).order_by(Employee.crew, Employee.name).all()
        
        # Initialize overtime data for each employee
        for emp in employees:
            # Add default overtime attributes for template
            emp.overtime_hours = 0
            emp.last_overtime_date = None
        
        # Calculate basic statistics
        total_overtime_hours = 0
        employees_with_overtime = 0
        high_overtime_count = 0
        
        # Try to get overtime data if OvertimeHistory table exists
        try:
            # Get overtime data for the last 13 weeks
            end_date = date.today()
            start_date = end_date - timedelta(weeks=13)
            
            # Get overtime records
            overtime_records = db.session.query(
                OvertimeHistory.employee_id,
                func.sum(OvertimeHistory.overtime_hours).label('total_hours')
            ).filter(
                OvertimeHistory.week_start_date >= start_date
            ).group_by(OvertimeHistory.employee_id).all()
            
            # Create a dictionary for quick lookup
            overtime_dict = {record.employee_id: record.total_hours for record in overtime_records}
            
            # Update employee overtime data
            for emp in employees:
                if emp.id in overtime_dict:
                    emp.overtime_hours = overtime_dict[emp.id]
                    total_overtime_hours += emp.overtime_hours
                    employees_with_overtime += 1
                    if emp.overtime_hours > 10:
                        high_overtime_count += 1
                    
                    # Get last overtime date
                    last_ot = OvertimeHistory.query.filter_by(
                        employee_id=emp.id
                    ).order_by(OvertimeHistory.week_start_date.desc()).first()
                    if last_ot:
                        emp.last_overtime_date = last_ot.week_start_date.strftime('%m/%d/%Y')
        except Exception as e:
            # If OvertimeHistory doesn't exist or has issues, use default values
            print(f"Could not load overtime history: {str(e)}")
        
        # Calculate averages
        avg_overtime = round(total_overtime_hours / len(employees), 1) if employees else 0
        max_overtime = max([emp.overtime_hours for emp in employees]) if employees else 10
        
        # Calculate crew overtime data for chart
        crew_overtime_data = [0, 0, 0, 0]  # For crews A, B, C, D
        crew_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
        
        for emp in employees:
            if emp.crew in crew_map:
                crew_overtime_data[crew_map[emp.crew]] += emp.overtime_hours
        
        # Round crew data
        crew_overtime_data = [round(hours, 1) for hours in crew_overtime_data]
        
        # Prepare overtime history (empty for now)
        overtime_history = []
        
        return render_template('overtime_management.html',
                             employees=employees,
                             all_employees=employees,
                             total_overtime_hours=round(total_overtime_hours, 1),
                             employees_with_overtime=employees_with_overtime,
                             avg_overtime=avg_overtime,
                             high_overtime_count=high_overtime_count,
                             max_overtime=max_overtime,
                             crew_overtime_data=crew_overtime_data,
                             overtime_history=overtime_history)
                             
    except Exception as e:
        # Log error and show user-friendly message
        print(f"Error in overtime_management: {str(e)}")
        flash('Error loading overtime data. Please try again later.', 'danger')
        return redirect(url_for('dashboard'))

@employee_bp.route('/vacation/request', methods=['GET', 'POST'])
@login_required
def vacation_request():
    """Request time off"""
    if request.method == 'POST':
        request_type = request.form.get('request_type')
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        reason = request.form.get('reason', '')
        
        # Calculate days (excluding weekends)
        days_requested = 0
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:  # Monday = 0, Friday = 4
                days_requested += 1
            current += timedelta(days=1)
        
        # Check balance
        if request_type == 'vacation' and days_requested > current_user.vacation_days:
            flash('Insufficient vacation days available.', 'danger')
            return redirect(url_for('employee.vacation_request'))
        elif request_type == 'sick' and days_requested > current_user.sick_days:
            flash('Insufficient sick days available.', 'danger')
            return redirect(url_for('employee.vacation_request'))
        elif request_type == 'personal' and days_requested > current_user.personal_days:
            flash('Insufficient personal days available.', 'danger')
            return redirect(url_for('employee.vacation_request'))
        
        # Create request
        time_off = TimeOffRequest(
            employee_id=current_user.id,
            request_type=request_type,
            start_date=start_date,
            end_date=end_date,
            days_requested=days_requested,
            reason=reason,
            status='pending'
        )
        
        db.session.add(time_off)
        db.session.commit()
        
        flash('Time off request submitted successfully!', 'success')
        return redirect(url_for('main.employee_dashboard'))
    
    return render_template('vacation_request.html',
                         vacation_days=current_user.vacation_days,
                         sick_days=current_user.sick_days,
                         personal_days=current_user.personal_days)

@employee_bp.route('/swap-request', methods=['POST'])
@login_required
def create_swap_request():
    """Create a shift swap request"""
    schedule_id = request.form.get('schedule_id')
    reason = request.form.get('reason', '')
    
    schedule = Schedule.query.get_or_404(schedule_id)
    
    if schedule.employee_id != current_user.id:
        flash('You can only request swaps for your own shifts.', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    # Create swap request
    swap_request = ShiftSwapRequest(
        requester_id=current_user.id,
        original_schedule_id=schedule_id,
        reason=reason,
        status='pending'
    )
    
    db.session.add(swap_request)
    db.session.commit()
    
    flash('Shift swap request submitted! Both supervisors will need to approve.', 'success')
    return redirect(url_for('main.employee_dashboard'))

@employee_bp.route('/sleep-dashboard')
@login_required
def sleep_dashboard():
    """Main sleep health dashboard"""
    # Get or create circadian profile
    profile = CircadianProfile.query.filter_by(employee_id=current_user.id).first()
    if not profile:
        return redirect(url_for('employee.sleep_profile'))
    
    # Get recent sleep logs
    from models import SleepLog, SleepRecommendation
    recent_logs = SleepLog.query.filter_by(
        employee_id=current_user.id
    ).order_by(SleepLog.date.desc()).limit(7).all()
    
    # Get active recommendations
    recommendations = SleepRecommendation.query.filter_by(
        employee_id=current_user.id,
        is_active=True
    ).order_by(SleepRecommendation.priority).all()
    
    # Get upcoming shift changes
    upcoming_schedules = Schedule.query.filter(
        Schedule.employee_id == current_user.id,
        Schedule.date >= date.today(),
        Schedule.date <= date.today() + timedelta(days=14)
    ).order_by(Schedule.date).all()
    
    return render_template('sleep_dashboard.html',
                         profile=profile,
                         recent_logs=recent_logs,
                         recommendations=recommendations,
                         upcoming_schedules=upcoming_schedules)

@employee_bp.route('/sleep-profile', methods=['GET', 'POST'])
@login_required
def sleep_profile():
    """Complete chronotype assessment"""
    if request.method == 'POST':
        # Create or update circadian profile
        profile = CircadianProfile.query.filter_by(employee_id=current_user.id).first()
        if not profile:
            profile = CircadianProfile(employee_id=current_user.id)
        
        profile.chronotype = request.form.get('chronotype')
        profile.preferred_sleep_time = datetime.strptime(request.form.get('preferred_sleep_time'), '%H:%M').time()
        profile.preferred_wake_time = datetime.strptime(request.form.get('preferred_wake_time'), '%H:%M').time()
        
        db.session.add(profile)
        db.session.commit()
        
        flash('Sleep profile updated successfully!', 'success')
        return redirect(url_for('employee.sleep_dashboard'))
    
    profile = CircadianProfile.query.filter_by(employee_id=current_user.id).first()
    return render_template('sleep_profile_form.html', profile=profile)

@employee_bp.route('/position/messages')
@login_required
def position_messages():
    """View messages for employee's position"""
    if not current_user.position_id:
        flash('You must be assigned to a position to view position messages.', 'warning')
        return redirect(url_for('main.employee_dashboard'))
    
    from models import PositionMessage
    
    # Get messages for user's position
    messages_query = PositionMessage.query.filter_by(
        position_id=current_user.position_id
    ).filter(
        or_(
            PositionMessage.expires_at.is_(None),
            PositionMessage.expires_at > datetime.now()
        )
    )
    
    # Filter by shift if specified
    shift_filter = request.args.get('shift', 'all')
    if shift_filter != 'all':
        messages_query = messages_query.filter(
            or_(
                PositionMessage.target_shifts == 'all',
                PositionMessage.target_shifts.contains(shift_filter)
            )
        )
    
    # Get pinned messages first, then others by date
    pinned_messages = messages_query.filter_by(pinned=True).all()
    recent_messages = messages_query.filter_by(pinned=False).order_by(
        PositionMessage.sent_at.desc()
    ).limit(50).all()
    
    # Mark messages as read
    for message in pinned_messages + recent_messages:
        if not message.is_read_by(current_user.id):
            message.mark_read_by(current_user.id)
    
    db.session.commit()
    
    # Get colleagues in same position but different shifts
    colleagues = Employee.query.filter(
        Employee.position_id == current_user.position_id,
        Employee.id != current_user.id,
        Employee.crew != current_user.crew
    ).all()
    
    return render_template('position_messages.html',
                         pinned_messages=pinned_messages,
                         recent_messages=recent_messages,
                         colleagues=colleagues,
                         current_position=current_user.position,
                         shift_filter=shift_filter)

@employee_bp.route('/shift-marketplace')
@login_required
def shift_marketplace():
    """Main shift trade marketplace view"""
    from models import ShiftTradePost, ShiftTrade, ShiftTradeProposal
    
    # Get filters from query params
    filters = {
        'start_date': request.args.get('start_date', date.today().strftime('%Y-%m-%d')),
        'end_date': request.args.get('end_date', (date.today() + timedelta(days=30)).strftime('%Y-%m-%d')),
        'shift_type': request.args.get('shift_type', ''),
        'position': request.args.get('position', ''),
        'compatibility': request.args.get('compatibility', '')
    }
    
    # Get available trades (exclude user's own posts)
    available_trades_query = ShiftTradePost.query.filter(
        ShiftTradePost.status == 'active',
        ShiftTradePost.poster_id != current_user.id
    ).join(Schedule)
    
    # Apply filters
    if filters['start_date']:
        available_trades_query = available_trades_query.filter(
            Schedule.date >= datetime.strptime(filters['start_date'], '%Y-%m-%d').date()
        )
    if filters['end_date']:
        available_trades_query = available_trades_query.filter(
            Schedule.date <= datetime.strptime(filters['end_date'], '%Y-%m-%d').date()
        )
    if filters['shift_type']:
        available_trades_query = available_trades_query.filter(
            Schedule.shift_type == filters['shift_type']
        )
    if filters['position']:
        available_trades_query = available_trades_query.filter(
            Schedule.position_id == int(filters['position'])
        )
    
    available_trades = available_trades_query.order_by(Schedule.date).all()
    
    # Calculate compatibility for each trade
    from utils.helpers import calculate_trade_compatibility
    for trade in available_trades:
        trade.compatibility = calculate_trade_compatibility(current_user, trade)
    
    # Filter by compatibility if specified
    if filters['compatibility']:
        available_trades = [t for t in available_trades if t.compatibility == filters['compatibility']]
    
    # Get user's posted shifts
    my_posts = ShiftTradePost.query.filter_by(
        poster_id=current_user.id,
        status='active'
    ).all()
    
    # Get user's active trades
    my_trades = ShiftTrade.query.filter(
        or_(
            ShiftTrade.employee1_id == current_user.id,
            ShiftTrade.employee2_id == current_user.id
        ),
        ShiftTrade.status.in_(['pending', 'approved'])
    ).all()
    
    # Get trade history
    from utils.helpers import get_trade_history
    trade_history = get_trade_history(current_user.id)
    
    # Get upcoming shifts for posting
    my_upcoming_shifts = Schedule.query.filter(
        Schedule.employee_id == current_user.id,
        Schedule.date >= date.today(),
        Schedule.date <= date.today() + timedelta(days=60)
    ).order_by(Schedule.date).all()
    
    # Get positions for filter
    positions = Position.query.all()
    
    # Calculate statistics
    stats = {
        'available_trades': len(available_trades),
        'my_posted_shifts': len(my_posts),
        'my_active_trades': len(my_trades),
        'pending_trades': len([t for t in my_trades if t.status == 'pending']),
        'completed_trades': ShiftTrade.query.filter(
            or_(
                ShiftTrade.employee1_id == current_user.id,
                ShiftTrade.employee2_id == current_user.id
            ),
            ShiftTrade.status == 'completed'
        ).count()
    }
    
    return render_template('shift_marketplace.html',
                         available_trades=available_trades,
                         my_posts=my_posts,
                         my_trades=my_trades,
                         trade_history=trade_history,
                         my_upcoming_shifts=my_upcoming_shifts,
                         positions=positions,
                         filters=filters,
                         stats=stats)

@employee_bp.route('/maintenance/report', methods=['GET', 'POST'])
@login_required
def report_maintenance():
    """Report a maintenance issue"""
    if request.method == 'POST':
        try:
            from models import MaintenanceIssue, MaintenanceUpdate, MaintenanceManager
            
            title = request.form.get('title')
            description = request.form.get('description')
            location = request.form.get('location')
            category = request.form.get('category', 'general')
            priority = request.form.get('priority', 'normal')
            safety_issue = request.form.get('safety_issue') == 'on'
            
            # Create issue
            issue = MaintenanceIssue(
                reporter_id=current_user.id,
                title=title,
                description=description,
                location=location,
                category=category,
                priority=priority,
                safety_issue=safety_issue,
                status='open',
                reported_at=datetime.now()
            )
            
            # Try to auto-assign to primary maintenance manager if exists
            try:
                primary_manager = MaintenanceManager.query.filter_by(is_primary=True).first()
                if primary_manager:
                    issue.assigned_to_id = primary_manager.employee_id
            except:
                pass
            
            db.session.add(issue)
            db.session.flush()
            
            # Create initial update
            try:
                update = MaintenanceUpdate(
                    issue_id=issue.id,
                    author_id=current_user.id,
                    update_type='comment',
                    message=f"Issue reported: {description}",
                    created_at=datetime.now()
                )
                db.session.add(update)
            except:
                pass
            
            db.session.commit()
            
            flash('Maintenance issue reported successfully!', 'success')
            return redirect(url_for('employee.maintenance_issues'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error reporting issue: {str(e)}', 'danger')
            return redirect(url_for('employee.report_maintenance'))
    
    return render_template('report_maintenance.html')

@employee_bp.route('/maintenance/issues')
@login_required
def maintenance_issues():
    """View maintenance issues"""
    from models import MaintenanceIssue, MaintenanceManager
    
    # Check if user is a maintenance manager
    is_manager = False
    try:
        manager_check = MaintenanceManager.query.filter_by(employee_id=current_user.id).first()
        is_manager = manager_check is not None
    except:
        is_manager = False
    
    # Base query
    if is_manager:
        # Managers see all issues
        issues_query = MaintenanceIssue.query
    else:
        # Regular employees see only their reported issues
        issues_query = MaintenanceIssue.query.filter_by(reporter_id=current_user.id)
    
    # Apply filters
    status_filter = request.args.get('status', 'active')
    if status_filter == 'active':
        issues_query = issues_query.filter(
            MaintenanceIssue.status.in_(['open', 'acknowledged', 'in_progress'])
        )
    elif status_filter != 'all':
        issues_query = issues_query.filter_by(status=status_filter)
    
    # Sort by priority and date
    from sqlalchemy import case
    issues = issues_query.order_by(
        case(
            (MaintenanceIssue.priority == 'critical', 1),
            (MaintenanceIssue.priority == 'high', 2),
            (MaintenanceIssue.priority == 'normal', 3),
            (MaintenanceIssue.priority == 'low', 4)
        ),
        MaintenanceIssue.reported_at.desc()
    ).all()
    
    # Get statistics for managers
    stats = {
        'open': 0,
        'in_progress': 0,
        'resolved': 0,
        'critical': 0
    }
    
    if is_manager:
        try:
            stats['open'] = MaintenanceIssue.query.filter_by(status='open').count()
            stats['in_progress'] = MaintenanceIssue.query.filter_by(status='in_progress').count()
            stats['resolved'] = MaintenanceIssue.query.filter_by(status='resolved').count()
            stats['critical'] = MaintenanceIssue.query.filter_by(priority='critical', status='open').count()
        except:
            pass
    
    return render_template('maintenance_issues.html',
                         issues=issues,
                         is_manager=is_manager,
                         stats=stats,
                         status_filter=status_filter)
