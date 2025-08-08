# utils/helpers.py - COMPLETE FILE
"""
Helper functions for the workforce scheduler
Includes coverage gap calculations and other utilities
"""

from models import db, Schedule, Position, Employee, TimeOffRequest
from datetime import date, timedelta
from sqlalchemy import func, and_
import logging

logger = logging.getLogger(__name__)

def get_coverage_gaps():
    """
    Calculate coverage gaps for the next 14 days
    Returns a list of dates with staffing shortages
    """
    try:
        gaps = []
        today = date.today()
        
        # Check next 14 days
        for i in range(14):
            check_date = today + timedelta(days=i)
            
            # Get scheduled employees for this date
            scheduled_count = Schedule.query.filter_by(date=check_date).count()
            
            # Get employees on approved time off
            on_leave_count = TimeOffRequest.query.filter(
                TimeOffRequest.status == 'approved',
                TimeOffRequest.start_date <= check_date,
                TimeOffRequest.end_date >= check_date
            ).count()
            
            # Get required coverage (sum of all position minimums)
            required_coverage = db.session.query(
                func.sum(Position.min_coverage)
            ).scalar() or 0
            
            # Calculate actual available
            actual_available = scheduled_count - on_leave_count
            
            if actual_available < required_coverage:
                gaps.append({
                    'date': check_date,
                    'scheduled': scheduled_count,
                    'on_leave': on_leave_count,
                    'available': actual_available,
                    'required': required_coverage,
                    'gap': required_coverage - actual_available
                })
        
        return gaps
        
    except Exception as e:
        logger.error(f"Error calculating coverage gaps: {e}")
        return []

def get_crew_coverage(crew, check_date):
    """
    Get coverage information for a specific crew on a specific date
    """
    try:
        # Get scheduled employees from this crew
        scheduled = Schedule.query.join(Employee).filter(
            Employee.crew == crew,
            Schedule.date == check_date
        ).count()
        
        # Get employees from this crew on leave
        on_leave = TimeOffRequest.query.join(Employee).filter(
            Employee.crew == crew,
            TimeOffRequest.status == 'approved',
            TimeOffRequest.start_date <= check_date,
            TimeOffRequest.end_date >= check_date
        ).count()
        
        # Get total employees in crew
        total_in_crew = Employee.query.filter_by(
            crew=crew,
            is_supervisor=False
        ).count()
        
        return {
            'crew': crew,
            'date': check_date,
            'total': total_in_crew,
            'scheduled': scheduled,
            'on_leave': on_leave,
            'available': scheduled - on_leave
        }
        
    except Exception as e:
        logger.error(f"Error getting crew coverage: {e}")
        return None

def calculate_overtime_average(employee_id, weeks=13):
    """
    Calculate average overtime hours for an employee over specified weeks
    """
    try:
        from models import OvertimeHistory
        
        # Get date range
        end_date = date.today()
        start_date = end_date - timedelta(weeks=weeks)
        
        # Calculate average
        result = db.session.query(
            func.avg(OvertimeHistory.overtime_hours)
        ).filter(
            OvertimeHistory.employee_id == employee_id,
            OvertimeHistory.week_start_date >= start_date
        ).scalar()
        
        return round(result or 0, 2)
        
    except Exception as e:
        logger.error(f"Error calculating overtime average: {e}")
        return 0

def get_position_coverage_status(position_id, check_date):
    """
    Check if a position has adequate coverage on a specific date
    """
    try:
        position = Position.query.get(position_id)
        if not position:
            return None
        
        # Count scheduled employees for this position
        scheduled = Schedule.query.join(Employee).filter(
            Employee.position_id == position_id,
            Schedule.date == check_date
        ).count()
        
        # Count employees on leave
        on_leave = TimeOffRequest.query.join(Employee).filter(
            Employee.position_id == position_id,
            TimeOffRequest.status == 'approved',
            TimeOffRequest.start_date <= check_date,
            TimeOffRequest.end_date >= check_date
        ).count()
        
        available = scheduled - on_leave
        
        return {
            'position': position.name,
            'required': position.min_coverage,
            'scheduled': scheduled,
            'on_leave': on_leave,
            'available': available,
            'shortage': max(0, position.min_coverage - available),
            'adequate': available >= position.min_coverage
        }
        
    except Exception as e:
        logger.error(f"Error checking position coverage: {e}")
        return None

def format_date_range(start_date, end_date):
    """
    Format a date range for display
    """
    if start_date == end_date:
        return start_date.strftime('%B %d, %Y')
    elif start_date.month == end_date.month:
        return f"{start_date.strftime('%B %d')} - {end_date.day}, {end_date.year}"
    else:
        return f"{start_date.strftime('%B %d')} - {end_date.strftime('%B %d, %Y')}"

def get_employee_availability(employee_id, check_date):
    """
    Check if an employee is available on a specific date
    """
    try:
        # Check if scheduled
        scheduled = Schedule.query.filter_by(
            employee_id=employee_id,
            date=check_date
        ).first()
        
        if not scheduled:
            return {'available': False, 'reason': 'Not scheduled'}
        
        # Check if on leave
        on_leave = TimeOffRequest.query.filter(
            TimeOffRequest.employee_id == employee_id,
            TimeOffRequest.status == 'approved',
            TimeOffRequest.start_date <= check_date,
            TimeOffRequest.end_date >= check_date
        ).first()
        
        if on_leave:
            return {'available': False, 'reason': f'On {on_leave.request_type}'}
        
        return {'available': True, 'reason': None}
        
    except Exception as e:
        logger.error(f"Error checking employee availability: {e}")
        return {'available': False, 'reason': 'Error checking availability'}
