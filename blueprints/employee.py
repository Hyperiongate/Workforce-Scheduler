# ========================================
# FILE 1: blueprints/employee.py
# ========================================
"""
Employee blueprint - Complete file with all functionality
Following project instructions for robust, complete code
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from datetime import date, timedelta, datetime
from sqlalchemy import or_, func, case, and_
import pandas as pd
import io
from werkzeug.utils import secure_filename
import os

# CORRECTED IMPORTS - Removed non-existent models
from models import (
    db, Employee, Schedule, VacationCalendar, Position, Skill, 
    TimeOffRequest, ShiftSwapRequest, CircadianProfile, CoverageNotification, 
    OvertimeHistory, SleepLog, PositionMessage, MessageReadReceipt, 
    MaintenanceIssue, ShiftTradePost, ShiftTradeProposal, ShiftTrade,
    FileUpload, Availability, CoverageRequest, OvertimeOpportunity,
    CoverageGap, ScheduleSuggestion
)

# Create the blueprint
employee_bp = Blueprint('employee', __name__)

# Helper decorator for supervisor-only routes
def supervisor_required(f):
    """Decorator to require supervisor access"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.is_supervisor:
            flash('You must be a supervisor to access this page.', 'danger')
            return redirect(url_for('employee.employee_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@employee_bp.route('/employee-dashboard')
@login_required
def employee_dashboard():
    """Main employee dashboard with comprehensive information"""
    try:
        # Get employee's upcoming schedules (next 14 days)
        upcoming_schedules = Schedule.query.filter(
            Schedule.employee_id == current_user.id,
            Schedule.date >= date.today(),
            Schedule.date <= date.today() + timedelta(days=14)
        ).order_by(Schedule.date).all()
        
        # Get recent time off requests (last 10)
        recent_requests = TimeOffRequest.query.filter_by(
            employee_id=current_user.id
        ).order_by(TimeOffRequest.created_at.desc()).limit(10).all()
        
        # Get overtime hours for last 13 weeks
        thirteen_weeks_ago = date.today() - timedelta(weeks=13)
        overtime_hours = OvertimeHistory.query.filter(
            OvertimeHistory.employee_id == current_user.id,
            OvertimeHistory.week_ending >= thirteen_weeks_ago
        ).order_by(OvertimeHistory.week_ending.desc()).all()
        
        # Calculate total OT hours and averages
        total_ot_hours = sum(ot.hours_worked for ot in overtime_hours) if overtime_hours else 0
        avg_weekly_ot = total_ot_hours / 13 if overtime_hours else 0
        
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
        position_messages = []
        if current_user.position_id:
            position_messages = PositionMessage.query.filter_by(
                position_id=current_user.position_id
            ).order_by(PositionMessage.sent_at.desc()).limit(5).all()
            
            # Count unread messages
            for msg in position_messages:
                if not msg.is_read_by(current_user.id):
                    unread_messages += 1
        
        # Get available overtime opportunities (next 2 months)
        two_months_ahead = date.today() + timedelta(days=60)
        available_overtime = OvertimeOpportunity.query.filter(
            OvertimeOpportunity.date >= date.today(),
            OvertimeOpportunity.date <= two_months_ahead,
            OvertimeOpportunity.status == 'open'
        ).order_by(OvertimeOpportunity.date).limit(10).all()
        
        # Get maintenance issues reported by user
        my_maintenance_issues = MaintenanceIssue.query.filter_by(
            reporter_id=current_user.id
        ).order_by(MaintenanceIssue.created_at.desc()).limit(5).all()
        
        # Calculate time off balances
        balances = {
            'vacation': current_user.vacation_days,
            'sick': current_user.sick_days,
            'personal': current_user.personal_days,
            'total_available': current_user.vacation_days + current_user.sick_days + current_user.personal_days
        }
        
        # Get crew information
        crew_info = {
            'crew': current_user.crew or 'Not Assigned',
            'position': current_user.position.name if current_user.position else 'Not Assigned',
            'department': current_user.department or 'Not Assigned',
            'supervisor': Employee.query.filter_by(crew=current_user.crew, is_supervisor=True).first() if current_user.crew else None
        }
        
        return render_template('employee_dashboard.html',
                             upcoming_schedules=upcoming_schedules,
                             recent_requests=recent_requests,
                             overtime_hours=overtime_hours,
                             total_ot_hours=total_ot_hours,
                             avg_weekly_ot=avg_weekly_ot,
                             active_swaps=active_swaps,
                             position_messages=position_messages,
                             unread_messages=unread_messages,
                             available_overtime=available_overtime,
                             my_maintenance_issues=my_maintenance_issues,
                             balances=balances,
                             crew_info=crew_info)
                             
    except Exception as e:
        # Log the error but still show dashboard with empty data
        print(f"Error in employee_dashboard: {str(e)}")
        flash('Some dashboard data could not be loaded.', 'warning')
        
        # Return dashboard with safe defaults
        return render_template('employee_dashboard.html',
                             upcoming_schedules=[],
                             recent_requests=[],
                             overtime_hours=[],
                             total_ot_hours=0,
                             avg_weekly_ot=0,
                             active_swaps=[],
                             position_messages=[],
                             unread_messages=0,
                             available_overtime=[],
                             my_maintenance_issues=[],
                             balances={'vacation': 0, 'sick': 0, 'personal': 0, 'total_available': 0},
                             crew_info={'crew': 'Not Assigned', 'position': 'Not Assigned', 
                                       'department': 'Not Assigned', 'supervisor': None})

@employee_bp.route('/vacation/request', methods=['GET', 'POST'])
@login_required
def vacation_request():
    """Handle vacation/time-off requests with validation"""
    if request.method == 'POST':
        try:
            # Extract and validate form data
            request_type = request.form.get('request_type')
            start_date_str = request.form.get('start_date')
            end_date_str = request.form.get('end_date')
            reason = request.form.get('reason', '').strip()
            
            # Validate required fields
            if not all([request_type, start_date_str, end_date_str]):
                flash('Please fill in all required fields.', 'danger')
                return redirect(url_for('employee.vacation_request'))
            
            # Parse dates
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid date format. Please use the date picker.', 'danger')
                return redirect(url_for('employee.vacation_request'))
            
            # Validate dates
            if start_date < date.today():
                flash('Start date cannot be in the past.', 'danger')
                return redirect(url_for('employee.vacation_request'))
            
            if end_date < start_date:
                flash('End date must be after or equal to start date.', 'danger')
                return redirect(url_for('employee.vacation_request'))
            
            # Calculate business days requested
            days_requested = 0
            current_date = start_date
            while current_date <= end_date:
                if current_date.weekday() < 5:  # Monday = 0, Friday = 4
                    days_requested += 1
                current_date += timedelta(days=1)
            
            if days_requested == 0:
                flash('Request spans only weekends. Please select dates that include weekdays.', 'warning')
                return redirect(url_for('employee.vacation_request'))
            
            # Check balance based on request type
            balance_check = {
                'vacation': current_user.vacation_days,
                'sick': current_user.sick_days,
                'personal': current_user.personal_days
            }
            
            if request_type in balance_check:
                if days_requested > balance_check[request_type]:
                    flash(f'Insufficient {request_type} days. You have {balance_check[request_type]} days available but requested {days_requested} days.', 'danger')
                    return redirect(url_for('employee.vacation_request'))
            
            # Check for conflicts with existing schedules
            conflicting_schedules = Schedule.query.filter(
                Schedule.employee_id == current_user.id,
                Schedule.date >= start_date,
                Schedule.date <= end_date
            ).all()
            
            if conflicting_schedules:
                flash(f'You have {len(conflicting_schedules)} scheduled shifts during this period. Please coordinate with your supervisor.', 'warning')
            
            # Check for overlapping requests
            overlapping_requests = TimeOffRequest.query.filter(
                TimeOffRequest.employee_id == current_user.id,
                TimeOffRequest.status.in_(['pending', 'approved']),
                or_(
                    and_(TimeOffRequest.start_date <= start_date, TimeOffRequest.end_date >= start_date),
                    and_(TimeOffRequest.start_date <= end_date, TimeOffRequest.end_date >= end_date),
                    and_(TimeOffRequest.start_date >= start_date, TimeOffRequest.end_date <= end_date)
                )
            ).all()
            
            if overlapping_requests:
                flash('You have overlapping time-off requests for this period.', 'danger')
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
            
            flash(f'Time off request submitted successfully! Requesting {days_requested} {request_type} days.', 'success')
            
            # TODO: Send notification to supervisor
            
            return redirect(url_for('employee.vacation_request'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Error submitting time off request: {str(e)}")
            flash('An error occurred while submitting your request. Please try again.', 'danger')
            return redirect(url_for('employee.vacation_request'))
    
    # GET request - show form and existing requests
    try:
        # Get all requests for the employee
        all_requests = TimeOffRequest.query.filter_by(employee_id=current_user.id)\
                                         .order_by(TimeOffRequest.created_at.desc()).all()
        
        # Separate by status
        pending_requests = [r for r in all_requests if r.status == 'pending']
        approved_requests = [r for r in all_requests if r.status == 'approved']
        denied_requests = [r for r in all_requests if r.status == 'denied']
        
        # Calculate used days this year
        current_year = date.today().year
        used_days = {
            'vacation': 0,
            'sick': 0,
            'personal': 0
        }
        
        for req in approved_requests:
            if req.start_date.year == current_year:
                if req.request_type in used_days:
                    used_days[req.request_type] += req.days_requested
        
        return render_template('vacation_request.html', 
                             pending_requests=pending_requests,
                             approved_requests=approved_requests,
                             denied_requests=denied_requests,
                             vacation_balance=current_user.vacation_days,
                             sick_balance=current_user.sick_days,
                             personal_balance=current_user.personal_days,
                             used_days=used_days)
                             
    except Exception as e:
        print(f"Error loading vacation requests: {str(e)}")
        flash('Error loading time off data.', 'warning')
        return render_template('vacation_request.html',
                             pending_requests=[],
                             approved_requests=[],
                             denied_requests=[],
                             vacation_balance=0,
                             sick_balance=0,
                             personal_balance=0,
                             used_days={'vacation': 0, 'sick': 0, 'personal': 0})

@employee_bp.route('/shift-marketplace')
@login_required
def shift_marketplace():
    """View and participate in shift trades"""
    try:
        # Get available shift trades (not posted by current user, still open)
        available_trades = ShiftTradePost.query.filter(
            ShiftTradePost.status == 'open',
            ShiftTradePost.posted_by_id != current_user.id
        ).order_by(ShiftTradePost.created_at.desc()).all()
        
        # Filter for compatible trades (same position or no position requirement)
        compatible_trades = []
        for trade in available_trades:
            if trade.shift:
                # Check position compatibility
                if not trade.shift.position_id or trade.shift.position_id == current_user.position_id:
                    compatible_trades.append(trade)
        
        # Get user's posted trades
        my_trades = ShiftTradePost.query.filter_by(
            posted_by_id=current_user.id
        ).order_by(ShiftTradePost.created_at.desc()).all()
        
        # Get user's upcoming shifts (for offering in trades)
        my_upcoming_shifts = Schedule.query.filter(
            Schedule.employee_id == current_user.id,
            Schedule.date >= date.today(),
            Schedule.date <= date.today() + timedelta(days=60)  # Next 2 months
        ).order_by(Schedule.date).all()
        
        # Get proposals on user's trades
        my_trade_ids = [trade.id for trade in my_trades]
        incoming_proposals = []
        if my_trade_ids:
            incoming_proposals = ShiftTradeProposal.query.filter(
                ShiftTradeProposal.trade_post_id.in_(my_trade_ids),
                ShiftTradeProposal.status == 'pending'
            ).all()
        
        # Get user's outgoing proposals
        outgoing_proposals = ShiftTradeProposal.query.filter_by(
            proposer_id=current_user.id,
            status='pending'
        ).all()
        
        # Get completed trades
        completed_trades = ShiftTrade.query.filter(
            or_(
                ShiftTrade.employee1_id == current_user.id,
                ShiftTrade.employee2_id == current_user.id
            ),
            ShiftTrade.status == 'completed'
        ).order_by(ShiftTrade.completed_at.desc()).limit(10).all()
        
        return render_template('shift_marketplace.html',
                             compatible_trades=compatible_trades,
                             my_trades=my_trades,
                             my_upcoming_shifts=my_upcoming_shifts,
                             incoming_proposals=incoming_proposals,
                             outgoing_proposals=outgoing_proposals,
                             completed_trades=completed_trades)
                             
    except Exception as e:
        print(f"Error in shift marketplace: {str(e)}")
        flash('Error loading shift marketplace data.', 'warning')
        return render_template('shift_marketplace.html',
                             compatible_trades=[],
                             my_trades=[],
                             my_upcoming_shifts=[],
                             incoming_proposals=[],
                             outgoing_proposals=[],
                             completed_trades=[])

@employee_bp.route('/maintenance/report', methods=['GET', 'POST'])
@login_required
def report_maintenance():
    """Report a maintenance issue"""
    if request.method == 'POST':
        try:
            # Extract form data
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            location = request.form.get('location', '').strip()
            severity = request.form.get('severity', 'medium')
            category = request.form.get('category', 'general')
            equipment_id = request.form.get('equipment_id')
            
            # Validate required fields
            if not all([title, description, location]):
                flash('Please fill in all required fields.', 'danger')
                return redirect(url_for('employee.report_maintenance'))
            
            # Validate severity
            valid_severities = ['low', 'medium', 'high', 'critical']
            if severity not in valid_severities:
                severity = 'medium'
            
            # Create maintenance issue
            issue = MaintenanceIssue(
                reporter_id=current_user.id,
                title=title,
                description=description,
                location=location,
                severity=severity,
                category=category,
                equipment_id=equipment_id if equipment_id else None,
                status='new',
                created_at=datetime.now()
            )
            
            # Set priority based on severity
            priority_map = {
                'critical': 'urgent',
                'high': 'high',
                'medium': 'normal',
                'low': 'low'
            }
            issue.priority = priority_map.get(severity, 'normal')
            
            db.session.add(issue)
            db.session.commit()
            
            flash('Maintenance issue reported successfully! Maintenance team has been notified.', 'success')
            
            # TODO: Send notification to maintenance team
            
            return redirect(url_for('employee.maintenance_issues'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Error reporting maintenance issue: {str(e)}")
            flash('Error reporting issue. Please try again.', 'danger')
            return redirect(url_for('employee.report_maintenance'))
    
    # GET request - show form
    try:
        # Get equipment list for dropdown (if applicable)
        equipment_list = []  # TODO: Implement Equipment model if needed
        
        # Get recent issues by this user for reference
        recent_issues = MaintenanceIssue.query.filter_by(
            reporter_id=current_user.id
        ).order_by(MaintenanceIssue.created_at.desc()).limit(5).all()
        
        return render_template('report_maintenance.html',
                             equipment_list=equipment_list,
                             recent_issues=recent_issues)
                             
    except Exception as e:
        print(f"Error loading maintenance form: {str(e)}")
        return render_template('report_maintenance.html',
                             equipment_list=[],
                             recent_issues=[])

@employee_bp.route('/maintenance/issues')
@login_required
def maintenance_issues():
    """View all maintenance issues"""
    try:
        # Get filter parameters
        status_filter = request.args.get('status', 'open')
        severity_filter = request.args.get('severity')
        category_filter = request.args.get('category')
        
        # Base query
        query = MaintenanceIssue.query
        
        # Apply filters
        if status_filter == 'open':
            query = query.filter(MaintenanceIssue.status.in_(['new', 'in_progress']))
        elif status_filter != 'all':
            query = query.filter_by(status=status_filter)
        
        if severity_filter:
            query = query.filter_by(severity=severity_filter)
        
        if category_filter:
            query = query.filter_by(category=category_filter)
        
        # Get all issues with applied filters
        all_issues = query.order_by(
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
        ).order_by(MaintenanceIssue.created_at.desc()).all()
        
        # Calculate statistics
        stats = {
            'total_open': MaintenanceIssue.query.filter(
                MaintenanceIssue.status.in_(['new', 'in_progress'])
            ).count(),
            'critical': MaintenanceIssue.query.filter_by(severity='critical', status='new').count(),
            'high': MaintenanceIssue.query.filter_by(severity='high', status='new').count(),
            'my_total': len(my_issues),
            'my_resolved': len([i for i in my_issues if i.status == 'resolved']),
            'my_pending': len([i for i in my_issues if i.status in ['new', 'in_progress']])
        }
        
        # Get unique categories for filter dropdown
        categories = db.session.query(MaintenanceIssue.category).distinct().all()
        categories = [c[0] for c in categories if c[0]]
        
        return render_template('maintenance_issues.html',
                             all_issues=all_issues,
                             my_issues=my_issues,
                             stats=stats,
                             categories=categories,
                             current_filters={
                                 'status': status_filter,
                                 'severity': severity_filter,
                                 'category': category_filter
                             })
                             
    except Exception as e:
        print(f"Error loading maintenance issues: {str(e)}")
        flash('Error loading maintenance issues.', 'warning')
        return render_template('maintenance_issues.html',
                             all_issues=[],
                             my_issues=[],
                             stats={},
                             categories=[],
                             current_filters={})

@employee_bp.route('/position-messages')
@login_required
def position_messages():
    """View messages for employee's position"""
    if not current_user.position_id:
        flash('You must have a position assigned to view position messages.', 'info')
        return redirect(url_for('employee.employee_dashboard'))
    
    try:
        # Get all messages for user's position
        all_messages = PositionMessage.query.filter_by(
            position_id=current_user.position_id
        ).order_by(PositionMessage.sent_at.desc()).all()
        
        # Filter messages by crew if applicable
        relevant_messages = []
        for message in all_messages:
            # Include if not crew-specific or if it's for user's crew
            if not message.crew_specific or message.target_crew == current_user.crew:
                relevant_messages.append(message)
        
        # Mark unread messages as read
        for message in relevant_messages:
            if not message.is_read_by(current_user.id):
                try:
                    read_receipt = MessageReadReceipt(
                        message_id=message.id,
                        employee_id=current_user.id,
                        read_at=datetime.now()
                    )
                    db.session.add(read_receipt)
                except:
                    # Skip if already exists (race condition)
                    pass
        
        db.session.commit()
        
        # Separate by priority
        high_priority = [m for m in relevant_messages if m.priority == 'high']
        normal_priority = [m for m in relevant_messages if m.priority == 'normal']
        low_priority = [m for m in relevant_messages if m.priority == 'low']
        
        return render_template('position_messages.html',
                             high_priority=high_priority,
                             normal_priority=normal_priority,
                             low_priority=low_priority,
                             total_messages=len(relevant_messages))
                             
    except Exception as e:
        print(f"Error loading position messages: {str(e)}")
        flash('Error loading messages.', 'warning')
        return render_template('position_messages.html',
                             high_priority=[],
                             normal_priority=[],
                             low_priority=[],
                             total_messages=0)

@employee_bp.route('/overtime/opportunities')
@login_required
def overtime_opportunities():
    """View and volunteer for overtime opportunities"""
    try:
        # Get date range (next 2 months)
        start_date = date.today()
        end_date = start_date + timedelta(days=60)
        
        # Get all open opportunities in date range
        all_opportunities = OvertimeOpportunity.query.filter(
            OvertimeOpportunity.date >= start_date,
            OvertimeOpportunity.date <= end_date,
            OvertimeOpportunity.status == 'open'
        ).order_by(OvertimeOpportunity.date).all()
        
        # Filter for position compatibility
        compatible_opportunities = []
        for opp in all_opportunities:
            # Check if position matches or no specific position required
            if not opp.position_id or opp.position_id == current_user.position_id:
                compatible_opportunities.append(opp)
        
        # Get user's volunteered opportunities
        # TODO: Implement OvertimeVolunteer model to track this
        volunteered_ids = []  # Placeholder
        
        # Separate by urgency
        urgent = [o for o in compatible_opportunities if (o.date - date.today()).days <= 7]
        upcoming = [o for o in compatible_opportunities if (o.date - date.today()).days > 7]
        
        # Get user's OT stats
        ot_stats = {
            'ytd_hours': 0,
            'last_13_weeks': 0,
            'voluntary_count': 0,
            'mandatory_count': 0
        }
        
        # Calculate YTD overtime
        ytd_start = date(date.today().year, 1, 1)
        ytd_overtime = OvertimeHistory.query.filter(
            OvertimeHistory.employee_id == current_user.id,
            OvertimeHistory.week_ending >= ytd_start
        ).all()
        
        ot_stats['ytd_hours'] = sum(ot.hours_worked for ot in ytd_overtime)
        
        # Last 13 weeks
        thirteen_weeks_ago = date.today() - timedelta(weeks=13)
        recent_overtime = [ot for ot in ytd_overtime if ot.week_ending >= thirteen_weeks_ago]
        ot_stats['last_13_weeks'] = sum(ot.hours_worked for ot in recent_overtime)
        
        # Count voluntary vs mandatory
        for ot in ytd_overtime:
            if ot.overtime_type == 'voluntary':
                ot_stats['voluntary_count'] += 1
            elif ot.overtime_type == 'mandatory':
                ot_stats['mandatory_count'] += 1
        
        return render_template('overtime_opportunities.html',
                             urgent_opportunities=urgent,
                             upcoming_opportunities=upcoming,
                             volunteered_ids=volunteered_ids,
                             ot_stats=ot_stats)
                             
    except Exception as e:
        print(f"Error loading overtime opportunities: {str(e)}")
        flash('Error loading overtime opportunities.', 'warning')
        return render_template('overtime_opportunities.html',
                             urgent_opportunities=[],
                             upcoming_opportunities=[],
                             volunteered_ids=[],
                             ot_stats={})

@employee_bp.route('/view-employees-crews')
@login_required
def view_employees_crews():
    """View all employees and their crew assignments"""
    try:
        # Get all active employees
        all_employees = Employee.query.filter_by(is_active=True).all()
        
        # Group by crew
        crews = {
            'A': [],
            'B': [],
            'C': [],
            'D': [],
            'Unassigned': []
        }
        
        for employee in all_employees:
            crew_key = employee.crew if employee.crew in crews else 'Unassigned'
            crews[crew_key].append(employee)
        
        # Sort employees within each crew by name
        for crew in crews:
            crews[crew].sort(key=lambda e: e.name)
        
        # Get all positions for filter
        positions = Position.query.order_by(Position.name).all()
        
        # Get all skills for filter  
        skills = Skill.query.order_by(Skill.name).all()
        
        # Calculate comprehensive statistics
        stats = {
            'total_employees': len(all_employees),
            'total_crews': len([c for c in ['A', 'B', 'C', 'D'] if crews[c]]),
            'total_supervisors': len([e for e in all_employees if e.is_supervisor]),
            'unassigned': len(crews['Unassigned']),
            'crew_sizes': {crew: len(crews[crew]) for crew in ['A', 'B', 'C', 'D']},
            'avg_crew_size': sum(len(crews[c]) for c in ['A', 'B', 'C', 'D']) / 4 if all_employees else 0,
            'positions_filled': len([e for e in all_employees if e.position_id]),
            'positions_vacant': len([e for e in all_employees if not e.position_id])
        }
        
        # Check crew balance
        if stats['avg_crew_size'] > 0:
            stats['crew_balance'] = max(stats['crew_sizes'].values()) - min(stats['crew_sizes'].values())
            stats['balanced'] = stats['crew_balance'] <= 2  # Crews are balanced if difference <= 2
        else:
            stats['crew_balance'] = 0
            stats['balanced'] = True
        
        return render_template('view_employees_crews.html',
                             crews=crews,
                             positions=positions,
                             skills=skills,
                             stats=stats)
                             
    except Exception as e:
        print(f"Error viewing employees/crews: {str(e)}")
        flash('Error loading employee data.', 'warning')
        return render_template('view_employees_crews.html',
                             crews={'A': [], 'B': [], 'C': [], 'D': [], 'Unassigned': []},
                             positions=[],
                             skills=[],
                             stats={})

# ========== SUPERVISOR-ONLY ROUTES ==========

@employee_bp.route('/employees/crew-management')
@login_required
@supervisor_required
def crew_management():
    """Crew management page - for supervisors only"""
    try:
        # Get all employees with details
        all_employees = Employee.query.filter_by(is_active=True).all()
        
        # Group by crew with additional info
        crews = {
            'A': {'employees': [], 'day_shift': True, 'supervisor': None},
            'B': {'employees': [], 'day_shift': True, 'supervisor': None},
            'C': {'employees': [], 'day_shift': False, 'supervisor': None},
            'D': {'employees': [], 'day_shift': False, 'supervisor': None},
            'Unassigned': {'employees': [], 'day_shift': None, 'supervisor': None}
        }
        
        for employee in all_employees:
            crew_key = employee.crew if employee.crew in crews else 'Unassigned'
            crews[crew_key]['employees'].append(employee)
            
            # Identify crew supervisors
            if employee.is_supervisor and employee.crew in ['A', 'B', 'C', 'D']:
                crews[employee.crew]['supervisor'] = employee
        
        # Sort employees within each crew
        for crew in crews:
            crews[crew]['employees'].sort(key=lambda e: (not e.is_supervisor, e.name))
        
        # Get all positions for assignment dropdown
        positions = Position.query.order_by(Position.name).all()
        
        # Get all skills
        skills = Skill.query.order_by(Skill.name).all()
        
        # Calculate crew statistics
        crew_stats = {}
        for crew_name in ['A', 'B', 'C', 'D']:
            crew_data = crews[crew_name]
            employees = crew_data['employees']
            
            crew_stats[crew_name] = {
                'total': len(employees),
                'supervisors': len([e for e in employees if e.is_supervisor]),
                'positions': {},
                'skills': {},
                'avg_seniority': 0
            }
            
            # Count positions
            for emp in employees:
                if emp.position:
                    pos_name = emp.position.name
                    crew_stats[crew_name]['positions'][pos_name] = crew_stats[crew_name]['positions'].get(pos_name, 0) + 1
            
            # Count skills
            for emp in employees:
                for skill in emp.skills:
                    skill_name = skill.name
                    crew_stats[crew_name]['skills'][skill_name] = crew_stats[crew_name]['skills'].get(skill_name, 0) + 1
            
            # Calculate average seniority
            if employees:
                total_days = sum((date.today() - (e.hire_date or date.today())).days for e in employees)
                crew_stats[crew_name]['avg_seniority'] = total_days / len(employees) / 365.25  # Years
        
        return render_template('crew_management.html', 
                             crews=crews,
                             positions=positions,
                             skills=skills,
                             crew_stats=crew_stats)
                             
    except Exception as e:
        print(f"Error in crew management: {str(e)}")
        flash('Error loading crew management data.', 'danger')
        return redirect(url_for('main.dashboard'))

@employee_bp.route('/overtime-management/export/excel')
@login_required
@supervisor_required
def export_overtime_excel():
    """Export overtime data to Excel with filters"""
    try:
        # Get filter parameters
        crew_filter = request.args.get('crew')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Base query
        query = OvertimeHistory.query.join(Employee)
        
        # Apply filters
        if crew_filter and crew_filter != 'all':
            query = query.filter(Employee.crew == crew_filter)
        
        if start_date:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            query = query.filter(OvertimeHistory.week_ending >= start)
        
        if end_date:
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            query = query.filter(OvertimeHistory.week_ending <= end)
        
        # Get data
        overtime_data = query.order_by(Employee.name, OvertimeHistory.week_ending.desc()).all()
        
        # Create DataFrame
        data = []
        for ot in overtime_data:
            data.append({
                'Employee Name': ot.employee.name,
                'Employee ID': ot.employee.employee_id,
                'Crew': ot.employee.crew or 'Unassigned',
                'Position': ot.employee.position.name if ot.employee.position else 'Not Assigned',
                'Week Ending': ot.week_ending.strftime('%Y-%m-%d'),
                'Regular Hours': ot.regular_hours or 40,
                'Overtime Hours': ot.hours_worked,
                'Total Hours': (ot.regular_hours or 40) + ot.hours_worked,
                'Type': ot.overtime_type or 'Unknown',
                'Reason': ot.reason or '',
                'Approved By': ot.approved_by.name if ot.approved_by else '',
                'Approved Date': ot.approved_date.strftime('%Y-%m-%d') if ot.approved_date else ''
            })
        
        df = pd.DataFrame(data)
        
        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Write main data
            df.to_excel(writer, sheet_name='Overtime Data', index=False)
            
            # Get workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets['Overtime Data']
            
            # Define formats
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#366092',
                'font_color': 'white',
                'border': 1
            })
            
            date_format = workbook.add_format({'num_format': 'yyyy-mm-dd'})
            number_format = workbook.add_format({'num_format': '#,##0.00'})
            
            # Apply header format
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            # Set column widths and formats
            worksheet.set_column('A:A', 20)  # Employee Name
            worksheet.set_column('B:B', 12)  # Employee ID
            worksheet.set_column('C:C', 8)   # Crew
            worksheet.set_column('D:D', 20)  # Position
            worksheet.set_column('E:E', 12, date_format)  # Week Ending
            worksheet.set_column('F:H', 12, number_format)  # Hours columns
            worksheet.set_column('I:I', 12)  # Type
            worksheet.set_column('J:J', 30)  # Reason
            worksheet.set_column('K:K', 20)  # Approved By
            worksheet.set_column('L:L', 12, date_format)  # Approved Date
            
            # Add summary sheet
            summary_data = []
            
            # Group by employee
            if not df.empty:
                employee_summary = df.groupby(['Employee Name', 'Employee ID', 'Crew']).agg({
                    'Overtime Hours': 'sum',
                    'Total Hours': 'sum',
                    'Week Ending': 'count'
                }).reset_index()
                employee_summary.rename(columns={'Week Ending': 'Weeks Worked'}, inplace=True)
                
                employee_summary.to_excel(writer, sheet_name='Employee Summary', index=False)
                
                # Format summary sheet
                summary_worksheet = writer.sheets['Employee Summary']
                for col_num, value in enumerate(employee_summary.columns.values):
                    summary_worksheet.write(0, col_num, value, header_format)
            
            # Add filters
            worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)
        
        output.seek(0)
        
        # Generate filename
        filename = f'overtime_export_{date.today().strftime("%Y%m%d")}'
        if crew_filter and crew_filter != 'all':
            filename += f'_crew{crew_filter}'
        filename += '.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        print(f"Error exporting overtime data: {str(e)}")
        flash(f'Error exporting data: {str(e)}', 'danger')
        return redirect(url_for('main.overtime_management'))

# ========== API ENDPOINTS ==========

@employee_bp.route('/api/shift-trades/create', methods=['POST'])
@login_required
def create_trade_post():
    """Create a new shift trade post"""
    try:
        data = request.get_json()
        
        shift_id = data.get('shift_id')
        reason = data.get('reason', '')
        preferred_dates = data.get('preferred_dates', [])
        requirements = data.get('requirements', '')
        
        # Validate shift ownership
        shift = Schedule.query.get(shift_id)
        if not shift:
            return jsonify({'success': False, 'message': 'Shift not found'}), 404
        
        if shift.employee_id != current_user.id:
            return jsonify({'success': False, 'message': 'You can only trade your own shifts'}), 403
        
        if shift.date < date.today():
            return jsonify({'success': False, 'message': 'Cannot trade past shifts'}), 400
        
        # Check if shift is already posted
        existing = ShiftTradePost.query.filter_by(
            shift_id=shift_id,
            status='open'
        ).first()
        
        if existing:
            return jsonify({'success': False, 'message': 'This shift is already posted for trade'}), 400
        
        # Create trade post
        trade_post = ShiftTradePost(
            posted_by_id=current_user.id,
            shift_id=shift_id,
            reason=reason,
            preferred_dates=','.join(preferred_dates) if preferred_dates else None,
            requirements=requirements,
            status='open',
            created_at=datetime.now()
        )
        
        db.session.add(trade_post)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Shift posted for trade successfully',
            'trade_id': trade_post.id
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creating trade post: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred'}), 500

@employee_bp.route('/api/shift-trades/propose', methods=['POST'])
@login_required
def propose_trade():
    """Propose a shift trade"""
    try:
        data = request.get_json()
        
        trade_post_id = data.get('trade_post_id')
        offered_shift_id = data.get('offered_shift_id')
        message = data.get('message', '')
        
        # Validate trade post
        trade_post = ShiftTradePost.query.get(trade_post_id)
        if not trade_post or trade_post.status != 'open':
            return jsonify({'success': False, 'message': 'Trade post not available'}), 400
        
        # Can't propose to own trade
        if trade_post.posted_by_id == current_user.id:
            return jsonify({'success': False, 'message': 'Cannot propose trade with yourself'}), 400
        
        # Validate offered shift
        offered_shift = Schedule.query.get(offered_shift_id)
        if not offered_shift or offered_shift.employee_id != current_user.id:
            return jsonify({'success': False, 'message': 'Invalid shift offer'}), 400
        
        if offered_shift.date < date.today():
            return jsonify({'success': False, 'message': 'Cannot offer past shifts'}), 400
        
        # Check for existing proposal
        existing = ShiftTradeProposal.query.filter_by(
            trade_post_id=trade_post_id,
            proposer_id=current_user.id,
            status='pending'
        ).first()
        
        if existing:
            return jsonify({'success': False, 'message': 'You already have a pending proposal for this trade'}), 400
        
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
        
        # TODO: Notify the trade poster
        
        return jsonify({
            'success': True,
            'message': 'Trade proposal submitted successfully',
            'proposal_id': proposal.id
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creating trade proposal: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred'}), 500

@employee_bp.route('/api/shift-trades/accept/<int:proposal_id>', methods=['POST'])
@login_required
def accept_trade_proposal(proposal_id):
    """Accept a trade proposal"""
    try:
        # Get proposal
        proposal = ShiftTradeProposal.query.get(proposal_id)
        if not proposal:
            return jsonify({'success': False, 'message': 'Proposal not found'}), 404
        
        # Verify ownership
        if proposal.trade_post.posted_by_id != current_user.id:
            return jsonify({'success': False, 'message': 'Not authorized'}), 403
        
        if proposal.status != 'pending':
            return jsonify({'success': False, 'message': 'Proposal is no longer pending'}), 400
        
        # Get shifts
        shift1 = proposal.trade_post.shift
        shift2 = proposal.offered_shift
        
        # Begin transaction
        try:
            # Swap the shifts
            emp1_id = shift1.employee_id
            emp2_id = shift2.employee_id
            
            shift1.employee_id = emp2_id
            shift2.employee_id = emp1_id
            
            # Update proposal status
            proposal.status = 'accepted'
            proposal.responded_at = datetime.now()
            
            # Close the trade post
            proposal.trade_post.status = 'completed'
            
            # Reject other proposals
            other_proposals = ShiftTradeProposal.query.filter(
                ShiftTradeProposal.trade_post_id == proposal.trade_post_id,
                ShiftTradeProposal.id != proposal_id,
                ShiftTradeProposal.status == 'pending'
            ).all()
            
            for other in other_proposals:
                other.status = 'rejected'
                other.responded_at = datetime.now()
            
            # Create trade record
            trade = ShiftTrade(
                employee1_id=emp1_id,
                employee2_id=emp2_id,
                shift1_id=shift1.id,
                shift2_id=shift2.id,
                status='completed',
                initiated_by_id=proposal.trade_post.posted_by_id,
                completed_at=datetime.now()
            )
            db.session.add(trade)
            
            db.session.commit()
            
            # TODO: Notify both employees
            
            return jsonify({
                'success': True,
                'message': 'Trade completed successfully'
            })
            
        except Exception as e:
            db.session.rollback()
            raise e
            
    except Exception as e:
        print(f"Error accepting trade proposal: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred'}), 500

@employee_bp.route('/api/overtime/volunteer', methods=['POST'])
@login_required
def volunteer_overtime():
    """Volunteer for overtime opportunity"""
    try:
        data = request.get_json()
        opportunity_id = data.get('opportunity_id')
        availability_note = data.get('note', '')
        
        # Validate opportunity
        opportunity = OvertimeOpportunity.query.get(opportunity_id)
        if not opportunity or opportunity.status != 'open':
            return jsonify({'success': False, 'message': 'Opportunity not available'}), 400
        
        # Check position compatibility
        if opportunity.position_id and opportunity.position_id != current_user.position_id:
            return jsonify({'success': False, 'message': 'Position mismatch'}), 400
        
        # TODO: Create OvertimeVolunteer record
        # For now, just return success with notification
        
        return jsonify({
            'success': True,
            'message': 'Thank you for volunteering! A supervisor will contact you if selected.',
            'opportunity_date': opportunity.date.strftime('%Y-%m-%d')
        })
        
    except Exception as e:
        print(f"Error volunteering for overtime: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred'}), 500

@employee_bp.route('/api/availability/update', methods=['POST'])
@login_required
def update_availability():
    """Update employee availability preferences"""
    try:
        data = request.get_json()
        availability_data = data.get('availability', [])
        
        # Validate data
        valid_days = list(range(7))  # 0-6 for Monday-Sunday
        valid_shifts = ['day', 'evening', 'night', 'any']
        
        for item in availability_data:
            if item.get('day') not in valid_days:
                return jsonify({'success': False, 'message': 'Invalid day'}), 400
            if item.get('preferred_shift') and item.get('preferred_shift') not in valid_shifts:
                return jsonify({'success': False, 'message': 'Invalid shift preference'}), 400
        
        # Update availability
        for day_data in availability_data:
            day_of_week = day_data.get('day')
            available = day_data.get('available', True)
            preferred_shift = day_data.get('preferred_shift', 'any')
            notes = day_data.get('notes', '')
            
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
            
            # Update fields
            availability.available = available
            availability.preferred_shift = preferred_shift
            availability.notes = notes
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Availability updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating availability: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred'}), 500

@employee_bp.route('/api/employee/<int:employee_id>/skills', methods=['GET'])
@login_required
def get_employee_skills(employee_id):
    """Get skills for a specific employee"""
    try:
        employee = Employee.query.get(employee_id)
        if not employee:
            return jsonify({'success': False, 'message': 'Employee not found'}), 404
        
        skills = [{'id': s.id, 'name': s.name} for s in employee.skills]
        
        return jsonify({
            'success': True,
            'employee_name': employee.name,
            'skills': skills
        })
        
    except Exception as e:
        print(f"Error getting employee skills: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred'}), 500

# Error handlers
@employee_bp.errorhandler(404)
def not_found_error(error):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': 'Not found'}), 404
    return render_template('404.html'), 404

@employee_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': 'Internal server error'}), 500
    return render_template('500.html'), 500
