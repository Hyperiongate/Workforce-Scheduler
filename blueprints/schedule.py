from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, Employee, Position, Skill, Schedule, TimeOffRequest, VacationCalendar, CoverageRequest
from datetime import datetime, timedelta, date
from sqlalchemy import func

supervisor_bp = Blueprint('supervisor', __name__, url_prefix='/supervisor')

def check_supervisor():
    """Check if current user is a supervisor"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return False
    return True

@supervisor_bp.route('/coverage-needs')
@login_required
def coverage_needs():
    """View and adjust coverage needs"""
    if not check_supervisor():
        return redirect(url_for('main.employee_dashboard'))
    
    # Get date range
    start_date = request.args.get('start_date', date.today())
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    end_date = start_date + timedelta(days=30)
    
    # Get all positions and their requirements
    positions = Position.query.all()
    
    # Get all skills
    skills = Skill.query.all()
    
    # Calculate coverage for each position
    coverage_data = []
    current = start_date
    while current <= end_date:
        for position in positions:
            # Count scheduled employees for this position and date
            scheduled = Schedule.query.filter_by(
                position_id=position.id,
                date=current
            ).count()
            
            coverage_data.append({
                'date': current,
                'position': position,
                'scheduled': scheduled,
                'required': position.min_coverage or 2,
                'gap': (position.min_coverage or 2) - scheduled
            })
        current += timedelta(days=1)
    
    return render_template('adjust_coverage.html',
                         positions=positions,
                         skills=skills,
                         coverage_data=coverage_data,
                         start_date=start_date,
                         end_date=end_date)

@supervisor_bp.route('/time-off-requests')
@login_required
def time_off_requests():
    """Review and manage time off requests"""
    if not check_supervisor():
        return redirect(url_for('main.employee_dashboard'))
    
    # Get pending requests
    pending_requests = TimeOffRequest.query.filter_by(status='pending').order_by(TimeOffRequest.submitted_date.desc()).all()
    
    # Get recently processed requests
    recent_requests = TimeOffRequest.query.filter(
        TimeOffRequest.status.in_(['approved', 'denied'])
    ).order_by(TimeOffRequest.submitted_date.desc()).limit(20).all()
    
    return render_template('time_off_requests.html',
                         pending_requests=pending_requests,
                         recent_requests=recent_requests)
