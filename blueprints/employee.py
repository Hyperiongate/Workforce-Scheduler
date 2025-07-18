from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Schedule, VacationCalendar, Employee, Position, Skill
from datetime import date, timedelta
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
    # Get employees with overtime data
    employees = Employee.query.filter_by(is_supervisor=False).order_by(Employee.name).all()
    
    # Calculate overtime for last 13 weeks
    overtime_data = []
    end_date = date.today()
    start_date = end_date - timedelta(weeks=13)
    
    for employee in employees:
        # Get weekly overtime hours
        weekly_data = []
        current = start_date
        total_ot = 0
        
        while current <= end_date:
            week_start = current - timedelta(days=current.weekday())
            week_end = week_start + timedelta(days=6)
            
            # Calculate overtime hours for this week
            ot_hours = db.session.query(func.sum(Schedule.hours)).filter(
                Schedule.employee_id == employee.id,
                Schedule.date >= week_start,
                Schedule.date <= week_end,
                Schedule.is_overtime == True
            ).scalar() or 0
            
            weekly_data.append({
                'week_start': week_start,
                'hours': ot_hours
            })
            total_ot += ot_hours
            
            current += timedelta(weeks=1)
        
        overtime_data.append({
            'employee': employee,
            'employee_id': employee.id,  # Include employee ID
            'weekly_data': weekly_data,
            'total_overtime': total_ot,
            'average_weekly': total_ot / 13 if total_ot > 0 else 0
        })
    
    return render_template('overtime_management.html',
                         overtime_data=overtime_data,
                         start_date=start_date,
                         end_date=end_date)
