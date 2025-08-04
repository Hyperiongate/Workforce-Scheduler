# utils/helpers.py - Complete implementation with coverage gap detection

from datetime import date, timedelta
from sqlalchemy import func
from flask import request
from sqlalchemy import or_

def get_coverage_gaps(start_date=None, end_date=None):
    """
    Identify coverage gaps in the schedule
    Returns a list of gaps with details
    """
    from models import db, Schedule, Position, Employee, TimeOffRequest
    from datetime import date, timedelta
    from sqlalchemy import func
    
    if not start_date:
        start_date = date.today()
    if not end_date:
        end_date = start_date + timedelta(days=14)  # Look 2 weeks ahead by default
    
    gaps = []
    
    # Check each day in the range
    current_date = start_date
    while current_date <= end_date:
        # Get all positions and their requirements
        positions = Position.query.all()
        
        for position in positions:
            # Skip positions that don't require coverage
            if hasattr(position, 'requires_coverage') and not position.requires_coverage:
                continue
                
            # Count scheduled employees for this position on this date
            scheduled_count = db.session.query(func.count(Schedule.id)).join(
                Employee, Schedule.employee_id == Employee.id
            ).filter(
                Schedule.date == current_date,
                Employee.position_id == position.id
            ).scalar() or 0
            
            # Count employees on approved time off
            time_off_count = db.session.query(func.count(TimeOffRequest.id)).join(
                Employee, TimeOffRequest.employee_id == Employee.id
            ).filter(
                TimeOffRequest.start_date <= current_date,
                TimeOffRequest.end_date >= current_date,
                TimeOffRequest.status == 'approved',
                Employee.position_id == position.id
            ).scalar() or 0
            
            # Get minimum coverage requirement
            min_required = position.min_coverage or 1
            
            # Calculate actual available
            actual_available = scheduled_count - time_off_count
            
            # Check if there's a gap
            if actual_available < min_required:
                gap = {
                    'date': current_date,
                    'position_id': position.id,
                    'position_name': position.name,
                    'scheduled': scheduled_count,
                    'time_off': time_off_count,
                    'available': actual_available,
                    'required': min_required,
                    'shortage': min_required - actual_available,
                    'shift_type': 'day',  # You can enhance this to check actual shift types
                    'critical': (min_required - actual_available) >= 2  # Critical if 2+ short
                }
                gaps.append(gap)
        
        current_date += timedelta(days=1)
    
    return gaps


def get_overtime_opportunities():
    """
    Get available overtime opportunities
    """
    from models import OvertimeOpportunity
    from datetime import date
    
    today = date.today()
    
    # Get open opportunities
    opportunities = OvertimeOpportunity.query.filter(
        OvertimeOpportunity.date >= today,
        OvertimeOpportunity.status == 'open'
    ).order_by(OvertimeOpportunity.date).all()
    
    return opportunities


def calculate_trade_compatibility(requesting_employee, target_employee, date):
    """
    Calculate compatibility score for shift trades
    """
    from models import Schedule, OvertimeHistory
    from datetime import timedelta
    
    score = 100  # Start with perfect score
    
    # Check if target employee is already scheduled
    existing_schedule = Schedule.query.filter_by(
        employee_id=target_employee.id,
        date=date
    ).first()
    
    if existing_schedule:
        score -= 50  # Major deduction if already scheduled
    
    # Check overtime in current week
    week_start = date - timedelta(days=date.weekday())
    target_ot = db.session.query(func.sum(OvertimeHistory.overtime_hours)).filter(
        OvertimeHistory.employee_id == target_employee.id,
        OvertimeHistory.week_start_date == week_start
    ).scalar() or 0
    
    # Deduct points for high overtime
    if target_ot > 40:
        score -= 20
    elif target_ot > 20:
        score -= 10
    
    # Check skill compatibility
    if requesting_employee.position_id == target_employee.position_id:
        score += 10  # Bonus for same position
    
    # Check crew compatibility (same crew is easier)
    if requesting_employee.crew == target_employee.crew:
        score += 5
    
    return max(0, score)  # Don't go below 0


def build_overtime_query_filters(request_args):
    """
    Build filter conditions for overtime queries based on request arguments
    """
    filters = []
    
    # Search filter
    search_term = request_args.get('search', '')
    if search_term:
        from models import Employee
        filters.append(
            or_(
                Employee.name.ilike(f'%{search_term}%'),
                Employee.employee_id.ilike(f'%{search_term}%')
            )
        )
    
    # Crew filter
    crew_filter = request_args.get('crew', '')
    if crew_filter and crew_filter != 'all':
        from models import Employee
        filters.append(Employee.crew == crew_filter)
    
    # Position filter
    position_filter = request_args.get('position', '')
    if position_filter and position_filter != 'all':
        from models import Employee
        filters.append(Employee.position_id == int(position_filter))
    
    return filters


def apply_overtime_range_filter(query, ot_range, total_hours_column):
    """
    Apply overtime range filter to a query
    """
    if not ot_range or ot_range == 'all':
        return query
        
    if ot_range == '0-50':
        return query.having(total_hours_column.between(0, 50))
    elif ot_range == '50-100':
        return query.having(total_hours_column.between(50, 100))
    elif ot_range == '100-150':
        return query.having(total_hours_column.between(100, 150))
    elif ot_range == '150+':
        return query.having(total_hours_column > 150)
    
    return query


def get_crew_distribution():
    """
    Get employee count by crew
    """
    from models import Employee, db
    
    distribution = db.session.query(
        Employee.crew,
        func.count(Employee.id).label('count')
    ).group_by(Employee.crew).all()
    
    # Convert to dict
    crew_counts = {}
    for crew, count in distribution:
        crew_name = crew if crew else 'Unassigned'
        crew_counts[crew_name] = count
    
    return crew_counts


def get_position_distribution():
    """
    Get employee count by position
    """
    from models import Employee, Position, db
    
    distribution = db.session.query(
        Position.name,
        func.count(Employee.id).label('count')
    ).join(
        Employee, Employee.position_id == Position.id
    ).group_by(Position.name).all()
    
    # Convert to dict
    position_counts = {}
    for position_name, count in distribution:
        position_counts[position_name] = count
    
    return position_counts


def calculate_weekly_overtime_average(employee_id, weeks=13):
    """
    Calculate average weekly overtime for an employee
    """
    from models import OvertimeHistory, db
    from datetime import datetime, timedelta
    
    start_date = datetime.now().date() - timedelta(weeks=weeks)
    
    total_ot = db.session.query(
        func.sum(OvertimeHistory.overtime_hours)
    ).filter(
        OvertimeHistory.employee_id == employee_id,
        OvertimeHistory.week_start_date >= start_date
    ).scalar() or 0
    
    return round(total_ot / weeks, 1)


def get_employees_by_overtime_range(min_hours=0, max_hours=None):
    """
    Get employees within a specific overtime range
    """
    from models import Employee, OvertimeHistory, db
    from datetime import datetime, timedelta
    
    thirteen_weeks_ago = datetime.now().date() - timedelta(weeks=13)
    
    query = db.session.query(
        Employee,
        func.sum(OvertimeHistory.overtime_hours).label('total_ot')
    ).join(
        OvertimeHistory, Employee.id == OvertimeHistory.employee_id
    ).filter(
        OvertimeHistory.week_start_date >= thirteen_weeks_ago
    ).group_by(Employee.id)
    
    if max_hours:
        query = query.having(
            func.sum(OvertimeHistory.overtime_hours).between(min_hours, max_hours)
        )
    else:
        query = query.having(
            func.sum(OvertimeHistory.overtime_hours) >= min_hours
        )
    
    return query.all()


# Add any other helper functions your application needs here
