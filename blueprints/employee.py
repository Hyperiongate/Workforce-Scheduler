# blueprints/employee.py

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from models import db, Schedule, VacationCalendar, Employee, Position, Skill, TimeOffRequest, ShiftSwapRequest, CircadianProfile, CoverageNotification, OvertimeHistory, SleepLog, PositionMessage, MessageReadReceipt, MaintenanceIssue, MaintenanceUpdate, ShiftTradePost, ShiftTradeProposal, ShiftTrade
from datetime import date, timedelta, datetime
from sqlalchemy import or_, func, case, and_

# Create the blueprint
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

# REMOVED THE DUPLICATE /overtime-management ROUTE - IT'S NOW IN main.py

@employee_bp.route('/overtime-management/export/excel')
@login_required
def export_overtime_excel():
    """Export overtime data to Excel with current filters and sorting"""
    if not current_user.is_supervisor:
        flash('You must be a supervisor to export data.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    try:
        import pandas as pd
        from io import BytesIO
        from datetime import datetime, timedelta
        
        # Get filter parameters from query string
        crew_filter = request.args.get('crew', 'all')
        position_filter = request.args.get('position', 'all')
        ot_range = request.args.get('ot_range', 'all')
        
        # Get all employees
        query = Employee.query
        
        # Apply crew filter
        if crew_filter != 'all':
            query = query.filter_by(crew=crew_filter)
            
        # Apply position filter  
        if position_filter != 'all':
            query = query.filter_by(position_id=int(position_filter))
            
        employees = query.all()
        
        # Get overtime data for the last 13 weeks
        thirteen_weeks_ago = datetime.now().date() - timedelta(weeks=13)
        
        # Create data for export
        export_data = []
        
        for emp in employees:
            # Skip current user
            if emp.id == current_user.id:
                continue
                
            # Get overtime total
            overtime_total = db.session.query(func.sum(OvertimeHistory.overtime_hours)).filter(
                OvertimeHistory.employee_id == emp.id,
                OvertimeHistory.week_start_date >= thirteen_weeks_ago
            ).scalar() or 0.0
            
            # Apply OT range filter
            if ot_range == '0-50' and overtime_total > 50:
                continue
            elif ot_range == '50-100' and (overtime_total <= 50 or overtime_total > 100):
                continue
            elif ot_range == '100-150' and (overtime_total <= 100 or overtime_total > 150):
                continue
            elif ot_range == '150+' and overtime_total <= 150:
                continue
            
            # Get weekly breakdown
            weekly_data = {
                'Employee Name': emp.name,
                'Employee ID': emp.employee_id or f'EMP{emp.id}',
                'Crew': emp.crew or 'Unassigned',
                'Position': emp.position.name if emp.position else 'No Position',
                'Date of Hire': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '',
                '13-Week Total': round(overtime_total, 1),
                'Weekly Average': round(overtime_total / 13, 1) if overtime_total else 0
            }
            
            # Add week-by-week breakdown
            for week_num in range(13):
                week_start = thirteen_weeks_ago + timedelta(weeks=week_num)
                week_ot = db.session.query(OvertimeHistory.overtime_hours).filter(
                    OvertimeHistory.employee_id == emp.id,
                    OvertimeHistory.week_start_date == week_start
                ).scalar() or 0
                
                week_label = f'Week {week_num + 1} ({week_start.strftime("%m/%d")})'
                weekly_data[week_label] = round(week_ot, 1)
            
            export_data.append(weekly_data)
        
        # Create DataFrame
        df = pd.DataFrame(export_data)
        
        # Sort by 13-week total descending
        if export_data:
            df = df.sort_values('13-Week Total', ascending=False)
        
        # Create Excel file in memory
        output = BytesIO()
        
        # Write to Excel with formatting
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Overtime Report', index=False)
            
            # Get workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets['Overtime Report']
            
            # Add formats
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'fg_color': '#D7E4BD',
                'border': 1
            })
            
            # Apply header format
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            # Adjust column widths
            worksheet.set_column('A:A', 20)  # Employee Name
            worksheet.set_column('B:B', 12)  # Employee ID
            worksheet.set_column('C:D', 10)  # Crew, Position
            worksheet.set_column('E:E', 12)  # Date of Hire
            worksheet.set_column('F:G', 12)  # Totals
            worksheet.set_column('H:T', 10)  # Weekly columns
            
            # Add conditional formatting for high overtime
            worksheet.conditional_format(1, 5, len(df), 5, {
                'type': 'cell',
                'criteria': '>',
                'value': 150,
                'format': workbook.add_format({'bg_color': '#FFC7CE'})
            })
        
        output.seek(0)
        
        # Generate filename with timestamp
        filename = f'overtime_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        flash(f'Error generating Excel export: {str(e)}', 'danger')
        return redirect(url_for('main.overtime_management'))

@employee_bp.route('/position/messages')
@login_required
def position_messages():
    """View messages for your position"""
    if not current_user.position_id:
        flash('You must have a position assigned to view position messages.', 'warning')
        return redirect(url_for('main.employee_dashboard'))
    
    # Get messages for user's position
    messages = PositionMessage.query.filter_by(
        position_id=current_user.position_id
    ).order_by(PositionMessage.sent_at.desc()).all()
    
    # Mark messages as read
    for message in messages:
        read_receipt = MessageReadReceipt.query.filter_by(
            message_id=message.id,
            employee_id=current_user.id
        ).first()
        
        if not read_receipt:
            read_receipt = MessageReadReceipt(
                message_id=message.id,
                employee_id=current_user.id,
                read_at=datetime.now()
            )
            db.session.add(read_receipt)
    
    db.session.commit()
    
    return render_template('position_messages.html', messages=messages)

@employee_bp.route('/maintenance/report', methods=['GET', 'POST'])
@login_required
def report_maintenance():
    """Report a maintenance issue"""
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        location = request.form.get('location')
        category = request.form.get('category', 'equipment')
        priority = request.form.get('priority', 'medium')
        
        issue = MaintenanceIssue(
            reporter_id=current_user.id,
            title=title,
            description=description,
            location=location,
            category=category,
            priority=priority,
            status='new',
            created_at=datetime.now()
        )
        
        db.session.add(issue)
        db.session.commit()
        
        flash('Maintenance issue reported successfully!', 'success')
        return redirect(url_for('employee.maintenance_issues'))
    
    return render_template('report_maintenance.html')

@employee_bp.route('/maintenance/issues')
@login_required
def maintenance_issues():
    """View maintenance issues"""
    # Get issues reported by current user
    my_issues = MaintenanceIssue.query.filter_by(
        reporter_id=current_user.id
    ).order_by(MaintenanceIssue.created_at.desc()).all()
    
    # If user is maintenance, show all issues
    all_issues = []
    if current_user.department == 'Maintenance' or current_user.is_supervisor:
        all_issues = MaintenanceIssue.query.order_by(
            MaintenanceIssue.created_at.desc()
        ).all()
    
    return render_template('maintenance_issues.html',
                         my_issues=my_issues,
                         all_issues=all_issues)

@employee_bp.route('/maintenance/issue/<int:issue_id>')
@login_required
def view_maintenance_issue(issue_id):
    """View a specific maintenance issue"""
    issue = MaintenanceIssue.query.get_or_404(issue_id)
    
    # Check if user can view this issue
    can_view = (
        issue.reporter_id == current_user.id or
        current_user.department == 'Maintenance' or
        current_user.is_supervisor
    )
    
    if not can_view:
        flash('You do not have permission to view this issue.', 'danger')
        return redirect(url_for('employee.maintenance_issues'))
    
    return render_template('view_maintenance_issue.html', issue=issue)

@employee_bp.route('/maintenance/issue/<int:issue_id>/update', methods=['POST'])
@login_required
def update_maintenance_issue(issue_id):
    """Update a maintenance issue"""
    issue = MaintenanceIssue.query.get_or_404(issue_id)
    
    # Check if user can update (maintenance or supervisor)
    if current_user.department != 'Maintenance' and not current_user.is_supervisor:
        flash('You do not have permission to update this issue.', 'danger')
        return redirect(url_for('employee.maintenance_issues'))
    
    # Get update data
    update_text = request.form.get('update_text')
    new_status = request.form.get('status')
    new_priority = request.form.get('priority')
    
    # Create update record
    update = MaintenanceUpdate(
        issue_id=issue.id,
        updater_id=current_user.id,
        update_text=update_text,
        old_status=issue.status,
        new_status=new_status,
        created_at=datetime.now()
    )
    
    # Update issue
    issue.status = new_status
    if new_priority:
        issue.priority = new_priority
    issue.updated_at = datetime.now()
    
    db.session.add(update)
    db.session.commit()
    
    flash('Issue updated successfully!', 'success')
    return redirect(url_for('employee.view_maintenance_issue', issue_id=issue_id))

@employee_bp.route('/vacation/request', methods=['GET', 'POST'])
@login_required
def vacation_request():
    """Request time off"""
    if request.method == 'POST':
        request_type = request.form.get('request_type', 'vacation')
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        reason = request.form.get('reason', '')
        
        # Calculate days requested
        days_requested = (end_date - start_date).days + 1
        
        # Check balance
        if request_type == 'vacation' and days_requested > current_user.vacation_days:
            flash(f'Insufficient vacation days. You have {current_user.vacation_days} days available.', 'danger')
            return redirect(url_for('employee.vacation_request'))
        elif request_type == 'sick' and days_requested > current_user.sick_days:
            flash(f'Insufficient sick days. You have {current_user.sick_days} days available.', 'danger')
            return redirect(url_for('employee.vacation_request'))
        elif request_type == 'personal' and days_requested > current_user.personal_days:
            flash(f'Insufficient personal days. You have {current_user.personal_days} days available.', 'danger')
            return redirect(url_for('employee.vacation_request'))
        
        # Create request
        time_off = TimeOffRequest(
            employee_id=current_user.id,
            request_type=request_type,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            days_requested=days_requested,
            status='pending',
            created_at=datetime.now()
        )
        
        db.session.add(time_off)
        db.session.commit()
        
        flash('Time off request submitted successfully!', 'success')
        return redirect(url_for('main.employee_dashboard'))
    
    # Get current balances
    balances = {
        'vacation': current_user.vacation_days,
        'sick': current_user.sick_days,
        'personal': current_user.personal_days
    }
    
    # Get pending and recent requests
    requests = TimeOffRequest.query.filter_by(
        employee_id=current_user.id
    ).order_by(TimeOffRequest.created_at.desc()).limit(10).all()
    
    return render_template('vacation_request.html',
                         balances=balances,
                         requests=requests)

@employee_bp.route('/shift-marketplace')
@login_required
def shift_marketplace():
    """Shift trading marketplace"""
    # Get available shifts for trade
    available_trades = ShiftTradePost.query.filter_by(
        status='open'
    ).filter(
        ShiftTradePost.shift_date >= date.today()
    ).order_by(ShiftTradePost.shift_date).all()
    
    # Get my posted trades
    my_trades = ShiftTradePost.query.filter_by(
        poster_id=current_user.id
    ).order_by(ShiftTradePost.created_at.desc()).all()
    
    # Get trades I've requested
    my_requests = ShiftTradeProposal.query.filter_by(
        proposer_id=current_user.id
    ).order_by(ShiftTradeProposal.created_at.desc()).all()
    
    # Get completed trades
    completed_trades = ShiftTrade.query.filter(
        or_(
            ShiftTrade.employee1_id == current_user.id,
            ShiftTrade.employee2_id == current_user.id
        )
    ).order_by(ShiftTrade.trade_date.desc()).limit(10).all()
    
    return render_template('shift_marketplace.html',
                         available_trades=available_trades,
                         my_trades=my_trades,
                         my_requests=my_requests,
                         completed_trades=completed_trades)

@employee_bp.route('/shift-marketplace/post', methods=['POST'])
@login_required
def post_shift_trade():
    """Post a shift for trade"""
    shift_date = datetime.strptime(request.form.get('shift_date'), '%Y-%m-%d').date()
    shift_type = request.form.get('shift_type', 'day')
    reason = request.form.get('reason', '')
    requirements = request.form.get('requirements', '')
    
    # Verify user is scheduled for this shift
    schedule = Schedule.query.filter_by(
        employee_id=current_user.id,
        date=shift_date,
        shift_type=shift_type
    ).first()
    
    if not schedule:
        flash('You are not scheduled for this shift.', 'danger')
        return redirect(url_for('employee.shift_marketplace'))
    
    # Create trade post
    trade_post = ShiftTradePost(
        poster_id=current_user.id,
        schedule_id=schedule.id,
        shift_date=shift_date,
        shift_type=shift_type,
        position_id=current_user.position_id,
        reason=reason,
        requirements=requirements,
        status='open',
        created_at=datetime.now()
    )
    
    db.session.add(trade_post)
    db.session.commit()
    
    flash('Shift posted for trade successfully!', 'success')
    return redirect(url_for('employee.shift_marketplace'))

@employee_bp.route('/shift-marketplace/propose/<int:post_id>', methods=['POST'])
@login_required
def propose_shift_trade(post_id):
    """Propose a trade for a posted shift"""
    post = ShiftTradePost.query.get_or_404(post_id)
    
    # Can't trade with yourself
    if post.poster_id == current_user.id:
        flash('You cannot trade with yourself.', 'danger')
        return redirect(url_for('employee.shift_marketplace'))
    
    # Check if already proposed
    existing = ShiftTradeProposal.query.filter_by(
        post_id=post_id,
        proposer_id=current_user.id
    ).first()
    
    if existing:
        flash('You have already proposed a trade for this shift.', 'warning')
        return redirect(url_for('employee.shift_marketplace'))
    
    # Create proposal
    proposal = ShiftTradeProposal(
        post_id=post_id,
        proposer_id=current_user.id,
        proposed_schedule_id=None,  # Could be enhanced to specify which shift to trade
        message=request.form.get('message', ''),
        status='pending',
        created_at=datetime.now()
    )
    
    db.session.add(proposal)
    db.session.commit()
    
    flash('Trade proposal submitted!', 'success')
    return redirect(url_for('employee.shift_marketplace'))

@employee_bp.route('/shift-marketplace/accept/<int:proposal_id>', methods=['POST'])
@login_required
def accept_trade_proposal(proposal_id):
    """Accept a trade proposal"""
    proposal = ShiftTradeProposal.query.get_or_404(proposal_id)
    post = proposal.post
    
    # Verify this is your post
    if post.poster_id != current_user.id:
        flash('You can only accept proposals for your own posts.', 'danger')
        return redirect(url_for('employee.shift_marketplace'))
    
    # Create the trade
    trade = ShiftTrade(
        employee1_id=post.poster_id,
        employee2_id=proposal.proposer_id,
        schedule1_id=post.schedule_id,
        schedule2_id=proposal.proposed_schedule_id,
        trade_date=datetime.now(),
        status='pending',  # Needs supervisor approval
        reason=f"Trade initiated via marketplace: {post.reason}"
    )
    
    # Update proposal and post status
    proposal.status = 'accepted'
    proposal.responded_at = datetime.now()
    post.status = 'accepted'
    
    # Reject other proposals
    other_proposals = ShiftTradeProposal.query.filter_by(
        post_id=post.id,
        status='pending'
    ).filter(ShiftTradeProposal.id != proposal_id).all()
    
    for other in other_proposals:
        other.status = 'rejected'
        other.responded_at = datetime.now()
    
    db.session.add(trade)
    db.session.commit()
    
    flash('Trade accepted! Pending supervisor approval.', 'success')
    return redirect(url_for('employee.shift_marketplace'))

@employee_bp.route('/sleep/dashboard')
@login_required
def sleep_dashboard():
    """Sleep health dashboard"""
    # Get or create circadian profile
    profile = CircadianProfile.query.filter_by(employee_id=current_user.id).first()
    if not profile:
        profile = CircadianProfile(
            employee_id=current_user.id,
            chronotype='intermediate',
            current_shift_type='day',
            circadian_adaptation_score=50.0
        )
        db.session.add(profile)
        db.session.commit()
    
    # Get recent sleep logs
    sleep_logs = SleepLog.query.filter_by(
        employee_id=current_user.id
    ).order_by(SleepLog.sleep_date.desc()).limit(30).all()
    
    # Calculate averages
    if sleep_logs:
        avg_duration = sum(log.sleep_duration for log in sleep_logs) / len(sleep_logs)
        avg_quality = sum(log.sleep_quality for log in sleep_logs) / len(sleep_logs)
    else:
        avg_duration = 0
        avg_quality = 0
    
    # Get recommendations
    recommendations = []
    
    # Check for shift changes
    recent_schedules = Schedule.query.filter_by(
        employee_id=current_user.id
    ).filter(
        Schedule.date >= date.today() - timedelta(days=14)
    ).order_by(Schedule.date).all()
    
    shift_types = [s.shift_type for s in recent_schedules]
    if len(set(shift_types)) > 1:
        recommendations.append({
            'type': 'warning',
            'title': 'Multiple Shift Types Detected',
            'message': 'You have worked different shift types recently. This can disrupt your sleep pattern.'
        })
    
    # Check average sleep duration
    if avg_duration < 7 and avg_duration > 0:
        recommendations.append({
            'type': 'warning',
            'title': 'Low Sleep Duration',
            'message': f'Your average sleep is {avg_duration:.1f} hours. Aim for 7-9 hours per night.'
        })
    
    return render_template('sleep_dashboard.html',
                         profile=profile,
                         sleep_logs=sleep_logs,
                         avg_duration=avg_duration,
                         avg_quality=avg_quality,
                         recommendations=recommendations)

@employee_bp.route('/sleep/log', methods=['GET', 'POST'])
@login_required
def log_sleep():
    """Log sleep data"""
    if request.method == 'POST':
        sleep_date = datetime.strptime(request.form.get('sleep_date'), '%Y-%m-%d').date()
        bedtime = request.form.get('bedtime')
        wake_time = request.form.get('wake_time')
        sleep_quality = int(request.form.get('sleep_quality', 5))
        notes = request.form.get('notes', '')
        
        # Calculate duration (simplified - doesn't handle midnight crossing perfectly)
        try:
            bed = datetime.strptime(bedtime, '%H:%M')
            wake = datetime.strptime(wake_time, '%H:%M')
            
            # If wake time is before bed time, assume next day
            if wake < bed:
                wake += timedelta(days=1)
            
            duration = (wake - bed).total_seconds() / 3600
        except:
            duration = 8  # Default if calculation fails
        
        # Check if log exists
        existing = SleepLog.query.filter_by(
            employee_id=current_user.id,
            sleep_date=sleep_date
        ).first()
        
        if existing:
            # Update existing
            existing.bedtime = bedtime
            existing.wake_time = wake_time
            existing.sleep_duration = duration
            existing.sleep_quality = sleep_quality
            existing.notes = notes
        else:
            # Create new
            sleep_log = SleepLog(
                employee_id=current_user.id,
                sleep_date=sleep_date,
                bedtime=bedtime,
                wake_time=wake_time,
                sleep_duration=duration,
                sleep_quality=sleep_quality,
                notes=notes
            )
            db.session.add(sleep_log)
        
        db.session.commit()
        flash('Sleep data logged successfully!', 'success')
        return redirect(url_for('employee.sleep_dashboard'))
    
    # Get today's date for default
    today = date.today()
    
    # Check if already logged today
    existing = SleepLog.query.filter_by(
        employee_id=current_user.id,
        sleep_date=today
    ).first()
    
    return render_template('log_sleep.html',
                         today=today,
                         existing=existing)

@employee_bp.route('/sleep/profile', methods=['GET', 'POST'])
@login_required
def sleep_profile():
    """Update sleep profile"""
    profile = CircadianProfile.query.filter_by(employee_id=current_user.id).first()
    
    if request.method == 'POST':
        profile.chronotype = request.form.get('chronotype', 'intermediate')
        profile.preferred_sleep_time = request.form.get('preferred_sleep_time')
        profile.preferred_wake_time = request.form.get('preferred_wake_time')
        profile.sleep_debt_threshold = float(request.form.get('sleep_debt_threshold', 10))
        
        db.session.commit()
        flash('Sleep profile updated!', 'success')
        return redirect(url_for('employee.sleep_dashboard'))
    
    return render_template('sleep_profile_form.html', profile=profile)
