from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Employee, Schedule, TimeOffRequest, ShiftSwapRequest, ScheduleSuggestion
from datetime import datetime, timedelta, date, time
from sqlalchemy import func, or_

main_bp = Blueprint('main', __name__)

@main_bp.route('/dashboard')
@login_required
def dashboard():
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.')
        return redirect(url_for('main.employee_dashboard'))
    
    # Your existing dashboard code here (copy from the original)
    # This is a simplified version
    selected_crew = request.args.get('crew', '')
    
    employees_query = Employee.query
    if selected_crew:
        employees_query = employees_query.filter_by(crew=selected_crew)
    
    employees = employees_query.all()
    total_employees = len(employees)
    
    # Get other data for dashboard
    pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
    pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
    pending_suggestions = ScheduleSuggestion.query.filter_by(status='pending').count()
    pending_requests = pending_time_off + pending_swaps + pending_suggestions
    
    return render_template('dashboard.html',
                         employees=employees,
                         total_employees=total_employees,
                         selected_crew=selected_crew,
                         pending_requests=pending_requests)

@main_bp.route('/employee-dashboard')
@login_required
def employee_dashboard():
    """Employee dashboard with schedules, requests, and sleep health info"""
    employee = Employee.query.get(current_user.id)
    
    # Get upcoming schedules
    schedules = Schedule.query.filter(
        Schedule.employee_id == employee.id,
        Schedule.date >= date.today()
    ).order_by(Schedule.date, Schedule.start_time).limit(7).all()
    
    return render_template('employee_dashboard.html',
                         employee=employee,
                         schedules=schedules)
