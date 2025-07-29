from flask import current_app
from models import db
from sqlalchemy import or_, and_, func

# Add these functions to your utils/helpers.py file

def calculate_overtime_trend(employee_id, weeks=13):
    """
    Calculate overtime trend for an employee over specified weeks.
    Returns 'increasing', 'decreasing', or 'stable'
    """
    from models import OvertimeHistory
    from datetime import date, timedelta
    from sqlalchemy import func
    
    end_date = date.today()
    start_date = end_date - timedelta(weeks=weeks)
    mid_date = start_date + timedelta(weeks=weeks//2)
    
    try:
        # Get first half total
        first_half = db.session.query(
            func.sum(OvertimeHistory.overtime_hours)
        ).filter(
            OvertimeHistory.employee_id == employee_id,
            OvertimeHistory.week_start_date >= start_date,
            OvertimeHistory.week_start_date < mid_date
        ).scalar() or 0
        
        # Get second half total
        second_half = db.session.query(
            func.sum(OvertimeHistory.overtime_hours)
        ).filter(
            OvertimeHistory.employee_id == employee_id,
            OvertimeHistory.week_start_date >= mid_date,
            OvertimeHistory.week_start_date <= end_date
        ).scalar() or 0
        
        # Calculate trend
        if second_half > first_half * 1.2:  # 20% increase
            return 'increasing'
        elif second_half < first_half * 0.8:  # 20% decrease
            return 'decreasing'
        else:
            return 'stable'
    except:
        return 'stable'

def get_overtime_statistics(crew=None, position_id=None):
    """
    Get overtime statistics for dashboard
    """
    from models import Employee, OvertimeHistory
    from datetime import date, timedelta
    from sqlalchemy import func, and_
    
    end_date = date.today()
    start_date = end_date - timedelta(weeks=13)
    
    # Base query
    query = db.session.query(
        func.count(Employee.id).label('employee_count'),
        func.sum(OvertimeHistory.overtime_hours).label('total_hours'),
        func.avg(OvertimeHistory.overtime_hours).label('avg_hours')
    ).join(
        OvertimeHistory, Employee.id == OvertimeHistory.employee_id
    ).filter(
        Employee.is_active == True,
        OvertimeHistory.week_start_date >= start_date,
        OvertimeHistory.week_start_date <= end_date
    )
    
    # Apply filters
    if crew:
        query = query.filter(Employee.crew == crew)
    if position_id:
        query = query.filter(Employee.position_id == position_id)
    
    result = query.first()
    
    return {
        'employee_count': result.employee_count or 0,
        'total_hours': round(float(result.total_hours or 0)),
        'avg_hours': round(float(result.avg_hours or 0))
    }

def format_overtime_for_display(overtime_hours):
    """
    Format overtime hours for display with appropriate styling
    """
    overtime_hours = round(float(overtime_hours))
    
    if overtime_hours >= 60:
        return {
            'value': overtime_hours,
            'class': 'overtime-high',
            'label': f'{overtime_hours}h (HIGH)'
        }
    elif overtime_hours >= 40:
        return {
            'value': overtime_hours,
            'class': 'overtime-medium',
            'label': f'{overtime_hours}h'
        }
    else:
        return {
            'value': overtime_hours,
            'class': 'overtime-low',
            'label': f'{overtime_hours}h'
        }

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
    if crew_filter:
        from models import Employee
        filters.append(Employee.crew == crew_filter)
    
    # Position filter
    position_filter = request_args.get('position', '')
    if position_filter:
        from models import Employee
        filters.append(Employee.position_id == int(position_filter))
    
    return filters

def apply_overtime_range_filter(query, ot_range, total_hours_column):
    """
    Apply overtime range filter to a query
    """
    if ot_range == '0-50':
        return query.having(total_hours_column.between(0, 50))
    elif ot_range == '50-100':
        return query.having(total_hours_column.between(50, 100))
    elif ot_range == '100-150':
        return query.having(total_hours_column.between(100, 150))
    elif ot_range == '150+':
        return query.having(total_hours_column > 150)
    return query

def get_coverage_gaps(start_date=None, end_date=None):
    """
    Identify coverage gaps in the schedule
    Returns a list of gaps with details
    """
    from models import db, Schedule, Position, Employee, CrewCoverageRequirement
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
            # Count scheduled employees for this position on this date
            scheduled_count = db.session.query(func.count(Schedule.id)).join(
                Employee, Schedule.employee_id == Employee.id
            ).filter(
                Schedule.date == current_date,
                Employee.position_id == position.id
            ).scalar() or 0
            
            # Get minimum coverage requirement
            min_required = position.min_coverage or 1
            
            # Check if there's a gap
            if scheduled_count < min_required:
                gap = {
                    'date': current_date,
                    'position_id': position.id,
                    'position_name': position.name,
                    'scheduled': scheduled_count,
                    'required': min_required,
                    'shortage': min_required - scheduled_count,
                    'shift_type': 'day'  # You can enhance this to check actual shift types
                }
                gaps.append(gap)
        
        current_date += timedelta(days=1)
    
    return gaps
