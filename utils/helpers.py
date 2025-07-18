from models import db, Schedule, Employee, VacationCalendar
from datetime import date, timedelta
from sqlalchemy import func

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
