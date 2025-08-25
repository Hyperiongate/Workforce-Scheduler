# utils/predictive_staffing.py
"""
Predictive Staffing Utility
Analyzes future dates for potential understaffing based on:
- Known time off requests
- Historical absence patterns
- Crew requirements
"""

from datetime import datetime, timedelta, date
from sqlalchemy import and_, or_, func
from models import db, Employee, TimeOffRequest, VacationCalendar, Schedule, Position, CrewCoverageRequirement
import logging

logger = logging.getLogger(__name__)

class PredictiveStaffing:
    """Handles predictive staffing calculations"""
    
    def __init__(self):
        self.min_crew_size = {
            'A': 15,
            'B': 15,
            'C': 12,
            'D': 15
        }
        
    def check_coverage_range(self, start_date, end_date):
        """
        Check coverage for a date range
        Returns list of dates with predicted understaffing
        """
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            
        understaffed_dates = []
        current_date = start_date
        
        while current_date <= end_date:
            crew_status = self.check_date_coverage(current_date)
            
            for crew, data in crew_status.items():
                if data['shortage'] > 0:
                    understaffed_dates.append({
                        'date': current_date.isoformat(),
                        'crew': crew,
                        'available': data['available'],
                        'required': data['required'],
                        'shortage': data['shortage'],
                        'on_leave': data['on_leave']
                    })
            
            current_date += timedelta(days=1)
            
        return understaffed_dates
    
    def check_date_coverage(self, check_date):
        """
        Check coverage for a specific date
        Returns dict with crew coverage status
        """
        crew_status = {}
        
        for crew in ['A', 'B', 'C', 'D']:
            # Get total employees in crew
            total_employees = Employee.query.filter_by(
                crew=crew,
                is_supervisor=False,
                is_active=True
            ).count()
            
            # Get employees on approved time off
            on_time_off = self.get_employees_on_leave(crew, check_date)
            
            # Calculate available employees
            available = total_employees - len(on_time_off)
            
            # Get minimum required for this crew
            required = self.get_crew_requirements(crew, check_date)
            
            # Calculate shortage
            shortage = max(0, required - available)
            
            crew_status[crew] = {
                'total': total_employees,
                'available': available,
                'required': required,
                'shortage': shortage,
                'on_leave': on_time_off
            }
            
        return crew_status
    
    def get_employees_on_leave(self, crew, check_date):
        """Get list of employee IDs on leave for a specific crew and date"""
        on_leave = []
        
        # Check approved time off requests
        time_off_requests = TimeOffRequest.query.join(Employee).filter(
            Employee.crew == crew,
            TimeOffRequest.status == 'approved',
            TimeOffRequest.start_date <= check_date,
            TimeOffRequest.end_date >= check_date
        ).all()
        
        for request in time_off_requests:
            on_leave.append({
                'employee_id': request.employee_id,
                'name': request.employee.name,
                'type': request.type.value if hasattr(request.type, 'value') else 'time_off'
            })
        
        # Also check vacation calendar
        vacation_entries = VacationCalendar.query.join(Employee).filter(
            Employee.crew == crew,
            VacationCalendar.date == check_date
        ).all()
        
        for entry in vacation_entries:
            # Avoid duplicates
            if not any(e['employee_id'] == entry.employee_id for e in on_leave):
                on_leave.append({
                    'employee_id': entry.employee_id,
                    'name': entry.employee.name,
                    'type': entry.type or 'vacation'
                })
        
        return on_leave
    
    def get_crew_requirements(self, crew, check_date):
        """
        Get minimum crew requirements for a specific date
        Takes into account day of week, holidays, etc.
        """
        # Base requirement
        base_requirement = self.min_crew_size.get(crew, 15)
        
        # Adjust for day of week (weekends might need less)
        if check_date.weekday() >= 5:  # Saturday or Sunday
            base_requirement = int(base_requirement * 0.8)
        
        # Check for specific coverage requirements in database
        try:
            # Get all position requirements for this crew
            position_requirements = db.session.query(
                func.sum(CrewCoverageRequirement.minimum_count)
            ).filter_by(
                crew=crew
            ).scalar()
            
            if position_requirements and position_requirements > 0:
                # Use database requirements if they exist
                return int(position_requirements)
        except Exception as e:
            logger.warning(f"Could not get coverage requirements from database: {e}")
        
        return base_requirement
    
    def get_coverage_predictions(self, days_ahead=30):
        """
        Get coverage predictions for the next N days
        Returns summary of potential issues
        """
        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead)
        
        understaffed_dates = self.check_coverage_range(start_date, end_date)
        
        # Group by severity
        critical_dates = [d for d in understaffed_dates if d['shortage'] >= 3]
        warning_dates = [d for d in understaffed_dates if 1 <= d['shortage'] < 3]
        
        return {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'total_issues': len(understaffed_dates),
            'critical_count': len(critical_dates),
            'warning_count': len(warning_dates),
            'critical_dates': critical_dates[:5],  # Top 5 critical
            'warning_dates': warning_dates[:5],   # Top 5 warnings
            'by_crew': self._group_by_crew(understaffed_dates)
        }
    
    def _group_by_crew(self, understaffed_dates):
        """Group understaffing data by crew"""
        by_crew = {'A': [], 'B': [], 'C': [], 'D': []}
        
        for item in understaffed_dates:
            crew = item['crew']
            if crew in by_crew:
                by_crew[crew].append(item)
        
        # Summary for each crew
        crew_summary = {}
        for crew, dates in by_crew.items():
            crew_summary[crew] = {
                'total_days_short': len(dates),
                'total_shortage': sum(d['shortage'] for d in dates),
                'worst_day': max(dates, key=lambda x: x['shortage']) if dates else None
            }
            
        return crew_summary
    
    def suggest_solutions(self, date, crew):
        """
        Suggest solutions for understaffing on a specific date/crew
        """
        suggestions = []
        
        # Check other crews for excess capacity
        crew_status = self.check_date_coverage(date)
        
        for other_crew, status in crew_status.items():
            if other_crew != crew and status['available'] > status['required']:
                excess = status['available'] - status['required']
                if excess > 0:
                    suggestions.append({
                        'type': 'borrow',
                        'action': f"Borrow {min(excess, crew_status[crew]['shortage'])} employees from Crew {other_crew}",
                        'source_crew': other_crew,
                        'available': excess
                    })
        
        # Check for employees with low overtime who could work extra
        low_ot_employees = Employee.query.filter_by(
            crew=crew,
            is_active=True,
            is_supervisor=False
        ).all()
        
        # Filter those not already scheduled or on leave
        available_for_ot = []
        for emp in low_ot_employees:
            # Check if already working or on leave
            on_leave = TimeOffRequest.query.filter(
                TimeOffRequest.employee_id == emp.id,
                TimeOffRequest.status == 'approved',
                TimeOffRequest.start_date <= date,
                TimeOffRequest.end_date >= date
            ).first()
            
            if not on_leave:
                available_for_ot.append(emp)
        
        if available_for_ot:
            suggestions.append({
                'type': 'overtime',
                'action': f"Offer overtime to {len(available_for_ot)} available employees",
                'employee_count': len(available_for_ot)
            })
        
        # Suggest cancelling non-critical leave
        on_leave = self.get_employees_on_leave(crew, date)
        non_critical_leave = [e for e in on_leave if e['type'] not in ['sick', 'emergency']]
        
        if non_critical_leave:
            suggestions.append({
                'type': 'reschedule',
                'action': f"Consider rescheduling {len(non_critical_leave)} non-critical time off requests",
                'affected_count': len(non_critical_leave)
            })
        
        return suggestions


# API endpoint handler functions
def get_predictive_staffing_data(start_date, end_date):
    """
    API handler for predictive staffing requests
    """
    try:
        predictor = PredictiveStaffing()
        understaffed_dates = predictor.check_coverage_range(start_date, end_date)
        
        return {
            'success': True,
            'understaffed_dates': understaffed_dates,
            'total_issues': len(understaffed_dates)
        }
    except Exception as e:
        logger.error(f"Error in predictive staffing: {e}")
        return {
            'success': False,
            'error': str(e),
            'understaffed_dates': []
        }
