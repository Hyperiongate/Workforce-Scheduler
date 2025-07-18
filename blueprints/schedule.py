from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from models import db, Employee, Position, Schedule, VacationCalendar, CircadianProfile, Skill
from datetime import datetime, timedelta, date, time
from sqlalchemy import func
import pandas as pd
from io import BytesIO

schedule_bp = Blueprint('schedule', __name__, url_prefix='/schedule')

@schedule_bp.route('/view')
@login_required
def view_schedules():
    """View schedules with crew filtering"""
    # Get crew filter
    crew = request.args.get('crew', 'ALL')
    
    # Get date range
    start_date = request.args.get('start_date', date.today())
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    end_date = request.args.get('end_date', start_date + timedelta(days=13))
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Build query
    query = Schedule.query.filter(
        Schedule.date >= start_date,
        Schedule.date <= end_date
    )
    
    if crew != 'ALL':
        query = query.filter(Schedule.crew == crew)
    
    schedules = query.order_by(Schedule.date, Schedule.shift_type, Schedule.start_time).all()
    
    # Get all employees for the schedule grid
    employees_query = Employee.query.filter_by(is_supervisor=False)
    if crew != 'ALL':
        employees_query = employees_query.filter_by(crew=crew)
    employees = employees_query.order_by(Employee.crew, Employee.name).all()
    
    # Create date range
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)
    
    # Create schedule dictionary for easy lookup
    schedule_dict = {}
    for schedule in schedules:
        key = (schedule.employee_id, schedule.date.strftime('%Y-%m-%d'))
        schedule_dict[key] = schedule
    
    # Calculate previous and next dates for navigation
    prev_start = start_date - timedelta(days=14)
    prev_end = end_date - timedelta(days=14)
    next_start = start_date + timedelta(days=14)
    next_end = end_date + timedelta(days=14)
    
    return render_template('view_schedule.html',  # Using view_schedule.html
                         employees=employees,
                         dates=dates,
                         schedules=schedule_dict,
                         start_date=start_date,
                         end_date=end_date,
                         selected_crew=crew,
                         prev_start=prev_start.strftime('%Y-%m-%d'),
                         prev_end=prev_end.strftime('%Y-%m-%d'),
                         next_start=next_start.strftime('%Y-%m-%d'),
                         next_end=next_end.strftime('%Y-%m-%d'),
                         today=date.today())

@schedule_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_schedule():
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    if request.method == 'POST':
        schedule_type = request.form.get('schedule_type')
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
        
        if schedule_type == '4_crew_rotation':
            rotation_pattern = request.form.get('rotation_pattern')
            
            # Route to appropriate creation function based on pattern
            if rotation_pattern == 'pitman':
                flash('Pitman schedule creation would go here', 'info')
            elif rotation_pattern == 'southern_swing':
                flash('Southern Swing schedule creation would go here', 'info')
            # Add other patterns as needed
            
        else:
            # Standard schedule creation
            shift_pattern = request.form.get('shift_pattern')
            flash(f'Creating {shift_pattern} schedule from {start_date} to {end_date}', 'info')
        
        return redirect(url_for('schedule.view_schedules'))
    
    employees = Employee.query.filter_by(is_supervisor=False).all()
    positions = Position.query.all()
    
    # Group employees by crew for display
    employees_by_crew = {}
    for emp in employees:
        crew = emp.crew or 'Unassigned'
        if crew not in employees_by_crew:
            employees_by_crew[crew] = []
        employees_by_crew[crew].append(emp)
    
    # Calculate employees near overtime
    week_start = date.today() - timedelta(days=date.today().weekday())
    week_end = week_start + timedelta(days=6)
    
    employees_near_overtime = []
    for emp in employees:
        current_hours = db.session.query(func.sum(Schedule.hours)).filter(
            Schedule.employee_id == emp.id,
            Schedule.date >= week_start,
            Schedule.date <= week_end
        ).scalar() or 0
        
        if current_hours >= 35:  # Near overtime threshold
            emp.current_hours = current_hours
            employees_near_overtime.append(emp)
    
    return render_template('schedule_input.html',
                         employees=employees,
                         positions=positions,
                         employees_by_crew=employees_by_crew,
                         employees_near_overtime=employees_near_overtime)

@schedule_bp.route('/wizard/<pattern>')
@login_required
def schedule_wizard(pattern):
    """Pattern-specific schedule creation wizard"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    # Validate pattern
    valid_patterns = ['pitman', 'southern_swing', 'fixed_fixed', 'dupont', 
                      'five_and_two', 'four_on_four_off', 'three_on_three_off', 
                      'alternating_fixed']
    
    if pattern not in valid_patterns:
        flash('Invalid schedule pattern selected.', 'danger')
        return redirect(url_for('schedule.select'))
    
    # Get data for wizard
    employees = Employee.query.filter_by(is_supervisor=False).order_by(Employee.name).all()
    positions = Position.query.order_by(Position.name).all()
    
    # Group employees by current crew
    employees_by_crew = {}
    unassigned_employees = []
    
    for emp in employees:
        if emp.crew:
            if emp.crew not in employees_by_crew:
                employees_by_crew[emp.crew] = []
            employees_by_crew[emp.crew].append(emp)
        else:
            unassigned_employees.append(emp)
    
    # Get crew statistics
    crew_stats = {}
    for crew in ['A', 'B', 'C', 'D']:
        crew_stats[crew] = {
            'count': len(employees_by_crew.get(crew, [])),
            'positions': {}
        }
        # Count positions in each crew
        for emp in employees_by_crew.get(crew, []):
            if emp.position:
                pos_name = emp.position.name
                crew_stats[crew]['positions'][pos_name] = crew_stats[crew]['positions'].get(pos_name, 0) + 1
    
    return render_template('schedule_wizard.html',
                         pattern=pattern,
                         employees=employees,
                         positions=positions,
                         employees_by_crew=employees_by_crew,
                         unassigned_employees=unassigned_employees,
                         crew_stats=crew_stats)

@schedule_bp.route('/select')
@login_required
def schedule_select():
    """Schedule pattern selection page"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    return render_template('schedule_selection.html')
