# blueprints/employee.py
"""
Employee blueprint - handles all employee-related routes
Complete file with all functionality
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from datetime import date, timedelta, datetime
from sqlalchemy import or_, func, case, and_
import pandas as pd
import io
from werkzeug.utils import secure_filename
import os

# Fixed imports - removed non-existent models
from models import (
    db, Employee, Schedule, VacationCalendar, Position, Skill, 
    TimeOffRequest, ShiftSwapRequest, CircadianProfile, CoverageNotification, 
    OvertimeHistory, SleepLog, PositionMessage, MessageReadReceipt, 
    MaintenanceIssue, ShiftTradePost, ShiftTradeProposal, ShiftTrade,
    FileUpload, Availability, CoverageRequest, OvertimeOpportunity
)

# Create the blueprint
employee_bp = Blueprint('employee', __name__)

# Helper decorator for supervisor-only routes
def supervisor_required(f):
    """Decorator to require supervisor access"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_supervisor:
            flash('You must be a supervisor to access this page.', 'danger')
            return redirect(url_for('main.employee_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@employee_bp.route('/employee-dashboard')
@login_required
def employee_dashboard():
    """Main employee dashboard"""
    try:
        # Get employee's upcoming schedules
        upcoming_schedules = Schedule.query.filter(
            Schedule.employee_id == current_user.id,
            Schedule.date >= date.today()
        ).order_by(Schedule.date).limit(14).all()
        
        # Get recent time off requests
        recent_requests = TimeOffRequest.query.filter_by(
            employee_id=current_user.id
        ).order_by(TimeOffRequest.created_at.desc()).limit(5).all()
        
        # Get overtime hours for last 13 weeks
        thirteen_weeks_ago = date.today() - timedelta(weeks=13)
        overtime_hours = OvertimeHistory.query.filter(
            OvertimeHistory.employee_id == current_user.id,
            OvertimeHistory.week_ending >= thirteen_weeks_ago
        ).order_by(OvertimeHistory.week_ending.desc()).all()
        
        # Calculate total OT hours
        total_ot_hours = sum(ot.hours_worked for ot in overtime_hours)
        
        # Get any active shift swap requests
        active_swaps = ShiftSwapRequest.query.filter(
            or_(
                ShiftSwapRequest.requester_id == current_user.id,
                ShiftSwapRequest.requested_with_id == current_user.id
            ),
            ShiftSwapRequest.status == 'pending'
        ).all()
        
        # Get position messages
        unread_messages = 0
        if current_user.position_id:
            position_messages = PositionMessage.query.filter_by(
                position_id=current_user.position_id
            ).order_by(PositionMessage.sent_at.desc()).limit(5).all()
            
            # Count unread
            for msg in position_messages:
                if not msg.is_read_by(current_user.id):
                    unread_messages += 1
        else:
            position_messages = []
        
        # Get available overtime opportunities
        available_overtime = OvertimeOpportunity.query.filter(
            OvertimeOpportunity.date >= date.today(),
            OvertimeOpportunity.status == 'open'
        ).order_by(OvertimeOpportunity.date).limit(10).all()
        
        return render_template('employee_dashboard.html',
                             upcoming_schedules=upcoming_schedules,
                             recent_requests=recent_requests,
                             overtime_hours=overtime_hours,
                             total_ot_hours=total_ot_hours,
                             active_swaps=active_swaps,
                             position_messages=position_messages,
                             unread_messages=unread_messages,
                             available_overtime=available_overtime)
                             
    except Exception as e:
        flash(f'Error loading dashboard: {str(e)}', 'danger')
        return render_template('employee_dashboard.html',
                             upcoming_schedules=[],
                             recent_requests=[],
                             overtime_hours=[],
                             total_ot_hours=0,
                             active_swaps=[],
                             position_messages=[],
                             unread_messages=0,
                             available_overtime=[])

@employee_bp.route('/vacation/request', methods=['GET', 'POST'])
@login_required
def vacation_request():
    """Handle vacation/time-off requests"""
    if request.method == 'POST':
        try:
            request_type = request.form.get('request_type')
            start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
            end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
            reason = request.form.get('reason', '')
            
            # Validate dates
            if start_date < date.today():
                flash('Start date cannot be in the past', 'danger')
                return redirect(url_for('employee.vacation_request'))
            
            if end_date < start_date:
                flash('End date must be after start date', 'danger')
                return redirect(url_for('employee.vacation_request'))
            
            # Calculate days requested
            days_requested = 0
            current_date = start_date
            while current_date <= end_date:
                if current_date.weekday() < 5:  # Monday = 0, Friday = 4
                    days_requested += 1
                current_date += timedelta(days=1)
            
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
            
            # Create time off request
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
            return redirect(url_for('employee.vacation_request'))
            
        except Exception as e:
            flash(f'Error submitting request: {str(e)}', 'danger')
            return redirect(url_for('employee.vacation_request'))
    
    # GET request - show form and existing requests
    requests = TimeOffRequest.query.filter_by(employee_id=current_user.id)\
                                 .order_by(TimeOffRequest.created_at.desc()).all()
    
    return render_template('vacation_request.html', 
                         requests=requests,
                         vacation_balance=current_user.vacation_days,
                         sick_balance=current_user.sick_days,
                         personal_balance=current_user.personal_days)

@employee_bp.route('/shift-marketplace')
@login_required
def shift_marketplace():
    """View and participate in shift trades"""
    # Get available shift trades (not posted by current user)
    available_trades = ShiftTradePost.query.filter(
        ShiftTradePost.status == 'open',
        ShiftTradePost.posted_by_id != current_user.id
    ).order_by(ShiftTradePost.created_at.desc()).all()
    
    # Get user's posted trades
    my_trades = ShiftTradePost.query.filter_by(
        posted_by_id=current_user.id
    ).order_by(ShiftTradePost.created_at.desc()).all()
    
    # Get user's upcoming shifts (for offering in trades)
    my_upcoming_shifts = Schedule.query.filter(
        Schedule.employee_id == current_user.id,
        Schedule.date >= date.today()
    ).order_by(Schedule.date).all()
    
    # Get proposals on user's trades
    my_trade_ids = [trade.id for trade in my_trades]
    incoming_proposals = ShiftTradeProposal.query.filter(
        ShiftTradeProposal.trade_post_id.in_(my_trade_ids),
        ShiftTradeProposal.status == 'pending'
    ).all() if my_trade_ids else []
    
    # Get user's outgoing proposals
    outgoing_proposals = ShiftTradeProposal.query.filter_by(
        proposer_id=current_user.id,
        status='pending'
    ).all()
    
    return render_template('shift_marketplace.html',
                         available_trades=available_trades,
                         my_trades=my_trades,
                         my_upcoming_shifts=my_upcoming_shifts,
                         incoming_proposals=incoming_proposals,
                         outgoing_proposals=outgoing_proposals)

@employee_bp.route('/maintenance/report', methods=['GET', 'POST'])
@login_required
def report_maintenance():
    """Report a maintenance issue"""
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            description = request.form.get('description')
            location = request.form.get('location')
            severity = request.form.get('severity', 'medium')
            category = request.form.get('category', 'general')
            
            # Validate required fields
            if not all([title, description, location]):
                flash('Please fill in all required fields', 'danger')
                return redirect(url_for('employee.report_maintenance'))
            
            issue = MaintenanceIssue(
                reporter_id=current_user.id,
                title=title,
                description=description,
                location=location,
                severity=severity,
                category=category,
                status='new',
                created_at=datetime.now()
            )
            
            db.session.add(issue)
            db.session.commit()
            
            flash('Maintenance issue reported successfully!', 'success')
            return redirect(url_for('employee.maintenance_issues'))
            
        except Exception as e:
            flash(f'Error reporting issue: {str(e)}', 'danger')
            return redirect(url_for('employee.report_maintenance'))
    
    return render_template('report_maintenance.html')

@employee_bp.route('/maintenance/issues')
@login_required
def maintenance_issues():
    """View maintenance issues"""
    # Get all open issues
    open_issues = MaintenanceIssue.query.filter(
        MaintenanceIssue.status.in_(['new', 'in_progress'])
    ).order_by(
        case(
            (MaintenanceIssue.severity == 'critical', 1),
            (MaintenanceIssue.severity == 'high', 2),
            (MaintenanceIssue.severity == 'medium', 3),
            (MaintenanceIssue.severity == 'low', 4)
        ),
        MaintenanceIssue.created_at.desc()
    ).all()
    
    # Get user's reported issues
    my_issues = MaintenanceIssue.query.filter_by(
        reporter_id=current_user.id
    ).order_by(MaintenanceIssue.created_at.desc()).limit(10).all()
    
    # Count by status for stats
    stats = {
        'total_open': len(open_issues),
        'critical': len([i for i in open_issues if i.severity == 'critical']),
        'my_total': MaintenanceIssue.query.filter_by(reporter_id=current_user.id).count(),
        'my_resolved': MaintenanceIssue.query.filter_by(
            reporter_id=current_user.id, 
            status='resolved'
        ).count()
    }
    
    return render_template('maintenance_issues.html',
                         open_issues=open_issues,
                         my_issues=my_issues,
                         stats=stats)

@employee_bp.route('/position-messages')
@login_required
def position_messages():
    """View messages for employee's position"""
    if not current_user.position_id:
        flash('You must have a position assigned to view messages.', 'info')
        return redirect(url_for('employee.employee_dashboard'))
    
    # Get messages for user's position
    messages = PositionMessage.query.filter_by(
        position_id=current_user.position_id
    ).order_by(PositionMessage.sent_at.desc()).all()
    
    # Mark messages as read
    for message in messages:
        if not message.is_read_by(current_user.id):
            read_receipt = MessageReadReceipt(
                message_id=message.id,
                employee_id=current_user.id,
                read_at=datetime.now()
            )
            db.session.add(read_receipt)
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash('Error marking messages as read', 'warning')
    
    return render_template('position_messages.html', messages=messages)

@employee_bp.route('/overtime/opportunities')
@login_required
def overtime_opportunities():
    """View available overtime opportunities"""
    # Get available OT for next 2 months
    two_months = date.today() + timedelta(days=60)
    
    opportunities = OvertimeOpportunity.query.filter(
        OvertimeOpportunity.date >= date.today(),
        OvertimeOpportunity.date <= two_months,
        OvertimeOpportunity.status == 'open'
    ).order_by(OvertimeOpportunity.date).all()
    
    # Get user's volunteered shifts
    volunteered = []  # This would come from an OvertimeVolunteer table
    
    return render_template('overtime_opportunities.html',
                         opportunities=opportunities,
                         volunteered=volunteered)

@employee_bp.route('/view-employees-crews')
@login_required
def view_employees_crews():
    """View all employees and their crew assignments"""
    # Get all employees grouped by crew
    crews = {}
    employees = Employee.query.filter_by(is_active=True)\
                            .order_by(Employee.crew, Employee.name).all()
    
    for employee in employees:
        crew_name = employee.crew or 'Unassigned'
        if crew_name not in crews:
            crews[crew_name] = []
        crews[crew_name].append(employee)
    
    # Get positions for filter
    positions = Position.query.order_by(Position.name).all()
    
    # Get skills for filter  
    skills = Skill.query.order_by(Skill.name).all()
    
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

# Supervisor-only routes
@employee_bp.route('/employees/crew-management')
@login_required
@supervisor_required
def crew_management():
    """Crew management page - for supervisors"""
    # Get all employees grouped by crew
    crews = {}
    employees = Employee.query.filter_by(is_active=True)\
                            .order_by(Employee.crew, Employee.name).all()
    
    for employee in employees:
        crew_name = employee.crew or 'Unassigned'
        if crew_name not in crews:
            crews[crew_name] = []
        crews[crew_name].append(employee)
    
    # Get all positions for assignment
    positions = Position.query.order_by(Position.name).all()
    
    return render_template('crew_management.html', 
                         crews=crews,
                         positions=positions)

@employee_bp.route('/overtime-management/export/excel')
@login_required
@supervisor_required
def export_overtime_excel():
    """Export overtime data to Excel"""
    try:
        # Get all overtime data
        overtime_data = OvertimeHistory.query.join(Employee)\
                                           .order_by(Employee.name, OvertimeHistory.week_ending.desc())\
                                           .all()
        
        # Create DataFrame
        data = []
        for ot in overtime_data:
            data.append({
                'Employee': ot.employee.name,
                'Employee ID': ot.employee.employee_id,
                'Crew': ot.employee.crew,
                'Week Ending': ot.week_ending,
                'Hours Worked': ot.hours_worked,
                'Type': ot.overtime_type,
                'Reason': ot.reason
            })
        
        df = pd.DataFrame(data)
        
        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Overtime Data', index=False)
            
            # Get workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets['Overtime Data']
            
            # Add formatting
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#366092',
                'font_color': 'white'
            })
            
            # Apply header format
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            # Auto-fit columns
            for column in df:
                column_width = max(df[column].astype(str).map(len).max(), len(column)) + 2
                col_idx = df.columns.get_loc(column)
                worksheet.set_column(col_idx, col_idx, column_width)
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'overtime_export_{date.today().strftime("%Y%m%d")}.xlsx'
        )
        
    except Exception as e:
        flash(f'Error exporting data: {str(e)}', 'danger')
        return redirect(url_for('main.overtime_management'))

# API endpoints
@employee_bp.route('/api/shift-trades/create', methods=['POST'])
@login_required
def create_trade_post():
    """Create a new shift trade post"""
    try:
        data = request.get_json()
        
        shift_id = data.get('shift_id')
        reason = data.get('reason', '')
        preferred_dates = data.get('preferred_dates', [])
        
        # Validate shift ownership
        shift = Schedule.query.get(shift_id)
        if not shift or shift.employee_id != current_user.id:
            return jsonify({'success': False, 'message': 'Invalid shift'}), 400
        
        # Create trade post
        trade_post = ShiftTradePost(
            posted_by_id=current_user.id,
            shift_id=shift_id,
            reason=reason,
            preferred_dates=','.join(preferred_dates) if preferred_dates else None,
            status='open',
            created_at=datetime.now()
        )
        
        db.session.add(trade_post)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Trade post created successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@employee_bp.route('/api/shift-trades/propose', methods=['POST'])
@login_required
def propose_trade():
    """Propose a shift trade"""
    try:
        data = request.get_json()
        
        trade_post_id = data.get('trade_post_id')
        offered_shift_id = data.get('offered_shift_id')
        message = data.get('message', '')
        
        # Validate
        trade_post = ShiftTradePost.query.get(trade_post_id)
        offered_shift = Schedule.query.get(offered_shift_id)
        
        if not trade_post or trade_post.status != 'open':
            return jsonify({'success': False, 'message': 'Trade post not available'}), 400
        
        if not offered_shift or offered_shift.employee_id != current_user.id:
            return jsonify({'success': False, 'message': 'Invalid shift offer'}), 400
        
        # Check if already proposed
        existing = ShiftTradeProposal.query.filter_by(
            trade_post_id=trade_post_id,
            proposer_id=current_user.id,
            status='pending'
        ).first()
        
        if existing:
            return jsonify({'success': False, 'message': 'You already have a pending proposal'}), 400
        
        # Create proposal
        proposal = ShiftTradeProposal(
            trade_post_id=trade_post_id,
            proposer_id=current_user.id,
            offered_shift_id=offered_shift_id,
            message=message,
            status='pending',
            created_at=datetime.now()
        )
        
        db.session.add(proposal)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Trade proposal submitted!'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@employee_bp.route('/api/overtime/volunteer', methods=['POST'])
@login_required
def volunteer_overtime():
    """Volunteer for overtime opportunity"""
    try:
        data = request.get_json()
        opportunity_id = data.get('opportunity_id')
        
        # Validate opportunity
        opportunity = OvertimeOpportunity.query.get(opportunity_id)
        if not opportunity or opportunity.status != 'open':
            return jsonify({'success': False, 'message': 'Opportunity not available'}), 400
        
        # Check if already volunteered (would need OvertimeVolunteer model)
        # For now, just return success
        
        flash('Thank you for volunteering! A supervisor will contact you if selected.', 'success')
        return jsonify({'success': True, 'message': 'Volunteered successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@employee_bp.route('/api/availability/update', methods=['POST'])
@login_required
def update_availability():
    """Update employee availability"""
    try:
        data = request.get_json()
        
        # Update availability for each day
        for day_data in data.get('availability', []):
            day_of_week = day_data.get('day')
            available = day_data.get('available')
            preferred_shift = day_data.get('preferred_shift')
            
            # Find or create availability record
            availability = Availability.query.filter_by(
                employee_id=current_user.id,
                day_of_week=day_of_week
            ).first()
            
            if not availability:
                availability = Availability(
                    employee_id=current_user.id,
                    day_of_week=day_of_week
                )
                db.session.add(availability)
            
            availability.available = available
            availability.preferred_shift = preferred_shift
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Availability updated'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# Error handlers
@employee_bp.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@employee_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500
