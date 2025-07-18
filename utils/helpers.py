from models import db, Schedule, Employee, VacationCalendar, Position, ShiftTrade, OvertimeOpportunity
from datetime import date, timedelta
from sqlalchemy import func, or_

def get_coverage_gaps(crew='ALL', days_ahead=7):
    """Get coverage gaps for the specified crew and time period"""
    gaps = []
    start_date = date.today()
    end_date = start_date + timedelta(days=days_ahead)
    
    current = start_date
    while current <= end_date:
        # Check each shift type
        for shift_type in ['day', 'evening', 'night']:
            scheduled_query = Schedule.query.filter(
                Schedule.date == current,
                Schedule.shift_type == shift_type
            )
            
            if crew != 'ALL':
                scheduled_query = scheduled_query.filter(Schedule.crew == crew)
            
            scheduled_count = scheduled_query.count()
            
            # Define minimum coverage requirements
            min_coverage = {
                'day': 4,
                'evening': 3,
                'night': 2
            }
            
            if scheduled_count < min_coverage.get(shift_type, 2):
                gaps.append({
                    'date': current,
                    'shift_type': shift_type,
                    'scheduled': scheduled_count,
                    'required': min_coverage.get(shift_type, 2),
                    'gap': min_coverage.get(shift_type, 2) - scheduled_count,
                    'crew': crew
                })
    
        current += timedelta(days=1)
    
    return gaps

def get_overtime_opportunities():
    """Get upcoming overtime opportunities"""
    opportunities = []
    gaps = get_coverage_gaps('ALL', 14)
    
    for gap in gaps:
        if gap['gap'] > 0:
            opportunities.append({
                'id': f"{gap['date']}_{gap['shift_type']}",
                'date': gap['date'],
                'shift_type': gap['shift_type'],
                'positions_needed': gap['gap'],
                'start_time': datetime.strptime('07:00', '%H:%M').time() if gap['shift_type'] == 'day' else datetime.strptime('19:00', '%H:%M').time(),
                'end_time': datetime.strptime('19:00', '%H:%M').time() if gap['shift_type'] == 'day' else datetime.strptime('07:00', '%H:%M').time(),
                'hours': 12
            })
    
    return opportunities[:10]  # Return first 10

def get_overtime_eligible_employees():
    """Get employees eligible for overtime"""
    # Get employees with less than 60 hours this week
    week_start = date.today() - timedelta(days=date.today().weekday())
    week_end = week_start + timedelta(days=6)
    
    employees = Employee.query.filter_by(is_supervisor=False).all()
    eligible = []
    
    for emp in employees:
        week_hours = db.session.query(func.sum(Schedule.hours)).filter(
            Schedule.employee_id == emp.id,
            Schedule.date >= week_start,
            Schedule.date <= week_end
        ).scalar() or 0
        
        if week_hours < 60:  # Eligible if under 60 hours
            eligible.append({
                'employee': emp,
                'current_hours': week_hours,
                'available_hours': 60 - week_hours
            })
    
    return eligible

def calculate_trade_compatibility(user, trade_post):
    """Calculate compatibility score for a trade"""
    schedule = trade_post.schedule
    
    # Check position match
    if user.position_id == schedule.position_id:
        return 'high'
    
    # Check skill match
    if schedule.position:
        required_skills = [s.id for s in schedule.position.required_skills]
        user_skills = [s.id for s in user.skills]
        if all(skill in user_skills for skill in required_skills):
            return 'medium'
    
    return 'low'

def get_trade_history(employee_id, limit=10):
    """Get trade history for an employee"""
    trades = ShiftTrade.query.filter(
        or_(
            ShiftTrade.employee1_id == employee_id,
            ShiftTrade.employee2_id == employee_id
        ),
        ShiftTrade.status == 'completed'
    ).order_by(ShiftTrade.completed_at.desc()).limit(limit).all()
    
    return trades

def calculate_time_ago(timestamp):
    """Calculate how long ago a timestamp was"""
    if not timestamp:
        return "Unknown time"
    
    from datetime import datetime
    now = datetime.now()
    
    if hasattr(timestamp, 'date'):
        time_diff = now - timestamp
    else:
        time_diff = now.date() - timestamp
        return f"{time_diff.days} days ago" if time_diff.days > 0 else "Today"
    
    seconds = time_diff.total_seconds()
    
    if seconds < 60:
        return "Just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"
