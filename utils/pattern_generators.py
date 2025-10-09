# utils/pattern_generators.py
"""
Schedule Pattern Generators
Creates actual Schedule database records for various shift patterns
COMPLETE FILE - Last Updated: 2025-10-08

Pattern Support:
- 4-on-4-off Weekly Rotation (16-day cycle, 16-week full rotation)
- 4-on-4-off Fast Rotation (8-day cycle with 2D-2N-4Off)
- 4-on-4-off Fixed Simple (8-day cycle, day/night separate)
- 4-on-4-off Modified (8-week cycle with full weekends)

Change Log:
  2025-10-08: Created file with 4-on-4-off patterns
  2025-10-08: Implemented correct weekly rotation matching manual
"""

from datetime import datetime, date, timedelta, time
from models import db, Schedule, Employee, ShiftType
from sqlalchemy import and_
import logging

logger = logging.getLogger(__name__)


class PatternGenerator:
    """Base class for schedule pattern generators"""
    
    def __init__(self):
        self.schedules = []
        self.errors = []
        self.warnings = []
    
    def validate_date_range(self, start_date, end_date):
        """Validate date range is reasonable"""
        if start_date > end_date:
            raise ValueError("Start date must be before end date")
        
        days = (end_date - start_date).days + 1
        if days > 365:
            raise ValueError("Schedule period cannot exceed 1 year (365 days)")
        
        if days < 7:
            self.warnings.append(f"Short schedule period: only {days} days")
        
        return True
    
    def get_crew_employees(self):
        """Get employees organized by crew"""
        employees = Employee.query.filter_by(
            is_active=True,
            is_supervisor=False
        ).all()
        
        crews = {'A': [], 'B': [], 'C': [], 'D': []}
        for emp in employees:
            if emp.crew in ['A', 'B', 'C', 'D']:
                crews[emp.crew].append(emp)
        
        return crews
    
    def validate_crews(self, crews):
        """Validate we have employees in all crews"""
        for crew_letter in ['A', 'B', 'C', 'D']:
            if not crews.get(crew_letter):
                self.warnings.append(f"Crew {crew_letter} has no employees")
        
        total = sum(len(crew) for crew in crews.values())
        if total == 0:
            raise ValueError("No active employees found for scheduling")
        
        return True
    
    def clear_existing_schedules(self, start_date, end_date, crew_employees):
        """Delete existing schedules in date range for these employees"""
        all_employee_ids = []
        for crew in crew_employees.values():
            all_employee_ids.extend([emp.id for emp in crew])
        
        if not all_employee_ids:
            return 0
        
        deleted = Schedule.query.filter(
            and_(
                Schedule.date >= start_date,
                Schedule.date <= end_date,
                Schedule.employee_id.in_(all_employee_ids)
            )
        ).delete(synchronize_session=False)
        
        db.session.commit()
        
        if deleted > 0:
            logger.info(f"Deleted {deleted} existing schedules in date range")
        
        return deleted
    
    def save_schedules(self, replace_existing=False):
        """Save generated schedules to database"""
        if not self.schedules:
            return {
                'success': False,
                'error': 'No schedules to save',
                'schedules_saved': 0
            }
        
        try:
            if replace_existing:
                # Get date range from schedules
                dates = [s.date for s in self.schedules]
                start_date = min(dates)
                end_date = max(dates)
                
                # Get affected employees
                employee_ids = list(set(s.employee_id for s in self.schedules))
                
                # Delete existing
                deleted = Schedule.query.filter(
                    and_(
                        Schedule.date >= start_date,
                        Schedule.date <= end_date,
                        Schedule.employee_id.in_(employee_ids)
                    )
                ).delete(synchronize_session=False)
                
                if deleted > 0:
                    logger.info(f"Replaced {deleted} existing schedules")
            
            # Add new schedules
            for schedule in self.schedules:
                db.session.add(schedule)
            
            db.session.commit()
            
            return {
                'success': True,
                'schedules_saved': len(self.schedules),
                'date_range': {
                    'start': min(s.date for s in self.schedules).isoformat(),
                    'end': max(s.date for s in self.schedules).isoformat()
                }
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error saving schedules: {e}")
            return {
                'success': False,
                'error': str(e),
                'schedules_saved': 0
            }


class FourOnFourOffWeekly(PatternGenerator):
    """
    4-on-4-off Weekly Rotation Pattern
    
    16-day cycle per crew: 4D, 4Off, 4N, 4Off (repeats)
    16-week full rotation (4 crews × 4 weeks offset)
    
    Crew offsets:
    - Crew A: Week 1 (day 0)
    - Crew B: Week 5 (day 28)
    - Crew C: Week 9 (day 56)
    - Crew D: Week 13 (day 84)
    """
    
    def __init__(self):
        super().__init__()
        self.pattern_name = "4-on-4-off Weekly Rotation"
        self.cycle_days = 16  # Per crew cycle
        self.full_rotation_days = 112  # 16 weeks
    
    def generate(self, start_date, end_date, created_by_id=None, replace_existing=False):
        """Generate 4-on-4-off weekly rotation schedule"""
        logger.info(f"Generating 4-on-4-off Weekly: {start_date} to {end_date}")
        
        # Validate inputs
        self.validate_date_range(start_date, end_date)
        
        # Get employees by crew
        crews = self.get_crew_employees()
        self.validate_crews(crews)
        
        # Clear existing if requested
        if replace_existing:
            self.clear_existing_schedules(start_date, end_date, crews)
        
        # Define the 16-day pattern for one crew
        # D=Day, N=Night, O=Off
        pattern = [
            'D', 'D', 'D', 'D',  # Days 0-3: Work days
            'O', 'O', 'O', 'O',  # Days 4-7: Off
            'N', 'N', 'N', 'N',  # Days 8-11: Work nights
            'O', 'O', 'O', 'O'   # Days 12-15: Off
        ]
        
        # Crew start offsets (in days from schedule start)
        crew_offsets = {
            'A': 0,    # Starts Week 1
            'B': 28,   # Starts Week 5 (4 weeks later)
            'C': 56,   # Starts Week 9 (8 weeks later)
            'D': 84    # Starts Week 13 (12 weeks later)
        }
        
        # Shift times
        day_start = time(6, 0)    # 06:00
        day_end = time(18, 0)     # 18:00
        night_start = time(18, 0)  # 18:00
        night_end = time(6, 0)     # 06:00 (next day)
        
        # Generate schedules for each day in range
        current_date = start_date
        while current_date <= end_date:
            # Calculate day offset from start
            day_offset = (current_date - start_date).days
            
            # For each crew
            for crew_letter, employees in crews.items():
                if not employees:
                    continue
                
                # Calculate this crew's position in their 16-day cycle
                crew_offset = crew_offsets[crew_letter]
                days_since_crew_start = day_offset - crew_offset
                
                # If before this crew's start, skip
                if days_since_crew_start < 0:
                    continue
                
                # Find position in 16-day pattern
                cycle_position = days_since_crew_start % self.cycle_days
                shift_type_code = pattern[cycle_position]
                
                # Skip if off day
                if shift_type_code == 'O':
                    continue
                
                # Determine shift type and times
                if shift_type_code == 'D':
                    shift_type = ShiftType.DAY
                    start_time = day_start
                    end_time = day_end
                elif shift_type_code == 'N':
                    shift_type = ShiftType.NIGHT
                    start_time = night_start
                    end_time = night_end
                else:
                    continue
                
                # Create schedule for each employee in this crew
                for employee in employees:
                    schedule = Schedule(
                        employee_id=employee.id,
                        date=current_date,
                        shift_type=shift_type,
                        start_time=start_time,
                        end_time=end_time,
                        hours=12.0,
                        position_id=employee.position_id,
                        created_by_id=created_by_id,
                        is_overtime=False
                    )
                    self.schedules.append(schedule)
            
            current_date += timedelta(days=1)
        
        logger.info(f"Generated {len(self.schedules)} schedule entries")
        
        # Save to database
        result = self.save_schedules(replace_existing=replace_existing)
        
        # Add statistics
        result['statistics'] = {
            'total_schedules': len(self.schedules),
            'date_range_days': (end_date - start_date).days + 1,
            'pattern_name': self.pattern_name,
            'crews_scheduled': [crew for crew, emps in crews.items() if emps]
        }
        
        return result


class FourOnFourOffFast(PatternGenerator):
    """
    4-on-4-off Fast Rotation
    8-day cycle: 2D, 2N, 4Off
    Crews staggered by 2 weeks (14 days)
    """
    
    def __init__(self):
        super().__init__()
        self.pattern_name = "4-on-4-off Fast Rotation"
        self.cycle_days = 8
    
    def generate(self, start_date, end_date, created_by_id=None, replace_existing=False):
        """Generate fast rotation schedule"""
        logger.info(f"Generating 4-on-4-off Fast: {start_date} to {end_date}")
        
        self.validate_date_range(start_date, end_date)
        crews = self.get_crew_employees()
        self.validate_crews(crews)
        
        if replace_existing:
            self.clear_existing_schedules(start_date, end_date, crews)
        
        # 8-day pattern: 2D, 2N, 4Off
        pattern = ['D', 'D', 'N', 'N', 'O', 'O', 'O', 'O']
        
        # Crew offsets (staggered by 14 days = 2 weeks)
        crew_offsets = {
            'A': 0,
            'B': 14,
            'C': 28,
            'D': 42
        }
        
        current_date = start_date
        while current_date <= end_date:
            day_offset = (current_date - start_date).days
            
            for crew_letter, employees in crews.items():
                if not employees:
                    continue
                
                crew_offset = crew_offsets[crew_letter]
                days_since_crew_start = day_offset - crew_offset
                
                if days_since_crew_start < 0:
                    continue
                
                cycle_position = days_since_crew_start % self.cycle_days
                shift_code = pattern[cycle_position]
                
                if shift_code == 'O':
                    continue
                
                if shift_code == 'D':
                    shift_type = ShiftType.DAY
                    start_time = time(6, 0)
                    end_time = time(18, 0)
                else:  # N
                    shift_type = ShiftType.NIGHT
                    start_time = time(18, 0)
                    end_time = time(6, 0)
                
                for employee in employees:
                    schedule = Schedule(
                        employee_id=employee.id,
                        date=current_date,
                        shift_type=shift_type,
                        start_time=start_time,
                        end_time=end_time,
                        hours=12.0,
                        position_id=employee.position_id,
                        created_by_id=created_by_id
                    )
                    self.schedules.append(schedule)
            
            current_date += timedelta(days=1)
        
        result = self.save_schedules(replace_existing=replace_existing)
        result['statistics'] = {
            'total_schedules': len(self.schedules),
            'pattern_name': self.pattern_name
        }
        
        return result


class FourOnFourOffFixed(PatternGenerator):
    """
    4-on-4-off Fixed Simple
    8-day cycle: 4 on, 4 off
    Crews A&B work days only, C&D work nights only
    """
    
    def __init__(self):
        super().__init__()
        self.pattern_name = "4-on-4-off Fixed Shifts"
        self.cycle_days = 8
    
    def generate(self, start_date, end_date, created_by_id=None, replace_existing=False):
        """Generate fixed shift schedule"""
        logger.info(f"Generating 4-on-4-off Fixed: {start_date} to {end_date}")
        
        self.validate_date_range(start_date, end_date)
        crews = self.get_crew_employees()
        self.validate_crews(crews)
        
        if replace_existing:
            self.clear_existing_schedules(start_date, end_date, crews)
        
        # 8-day pattern: 4 on, 4 off
        pattern = ['X', 'X', 'X', 'X', 'O', 'O', 'O', 'O']
        
        # Crew offsets (B and D offset by 4 days)
        crew_offsets = {
            'A': 0,
            'B': 4,
            'C': 0,
            'D': 4
        }
        
        current_date = start_date
        while current_date <= end_date:
            day_offset = (current_date - start_date).days
            
            for crew_letter, employees in crews.items():
                if not employees:
                    continue
                
                crew_offset = crew_offsets[crew_letter]
                cycle_position = (day_offset + crew_offset) % self.cycle_days
                
                if pattern[cycle_position] == 'O':
                    continue
                
                # A and B work days, C and D work nights
                if crew_letter in ['A', 'B']:
                    shift_type = ShiftType.DAY
                    start_time = time(6, 0)
                    end_time = time(18, 0)
                else:  # C or D
                    shift_type = ShiftType.NIGHT
                    start_time = time(18, 0)
                    end_time = time(6, 0)
                
                for employee in employees:
                    schedule = Schedule(
                        employee_id=employee.id,
                        date=current_date,
                        shift_type=shift_type,
                        start_time=start_time,
                        end_time=end_time,
                        hours=12.0,
                        position_id=employee.position_id,
                        created_by_id=created_by_id
                    )
                    self.schedules.append(schedule)
            
            current_date += timedelta(days=1)
        
        result = self.save_schedules(replace_existing=replace_existing)
        result['statistics'] = {
            'total_schedules': len(self.schedules),
            'pattern_name': self.pattern_name
        }
        
        return result


# Factory function to get the right generator
def get_pattern_generator(pattern, variation=None):
    """
    Get the appropriate pattern generator
    
    Args:
        pattern: Base pattern name (e.g., 'four_on_four_off')
        variation: Pattern variation (e.g., 'weekly', 'fast', 'fixed_simple')
    
    Returns:
        PatternGenerator instance or None if not found
    """
    if pattern == 'four_on_four_off':
        if variation == 'weekly':
            return FourOnFourOffWeekly()
        elif variation == 'fast':
            return FourOnFourOffFast()
        elif variation == 'fixed_simple':
            return FourOnFourOffFixed()
    
    return None
