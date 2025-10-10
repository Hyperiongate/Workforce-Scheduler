# utils/pattern_generators.py
# COMPLETE FILE - Pattern Generators for Workforce Scheduler
# Last Updated: 2025-10-10 - FIXED Modified 4-on-4-off pattern for proper 24/7 coverage
# 
# Change Log:
#   2025-10-10: CRITICAL FIX - Corrected Modified 4-on-4-off crew patterns
#               - Analyzed user's screenshot showing coverage gaps and overlaps
#               - Redesigned crew patterns to ensure 24/7 coverage
#               - Crews A&B cover days with proper offset
#               - Crews C&D cover nights with proper offset
#               - Verified no gaps, no overlaps in 8-week cycle
#   2025-10-09: Added FourOnFourOffModified class with 8-week (56-day) cycle
#   2025-10-09: Updated get_pattern_generator to include 'modified' variation

from models import db, Employee, Schedule, ShiftType
from datetime import datetime, date, timedelta, time
from sqlalchemy import and_
import logging

logger = logging.getLogger(__name__)


class PatternGenerator:
    """Base class for all schedule pattern generators"""
    
    def __init__(self):
        self.schedules = []
        self.pattern_name = "Base Pattern"
        self.cycle_days = 14
    
    def validate_date_range(self, start_date, end_date):
        """Validate date range is reasonable"""
        if start_date > end_date:
            raise ValueError("Start date must be before end date")
        
        if (end_date - start_date).days > 365:
            raise ValueError("Date range cannot exceed 365 days")
    
    def get_crew_employees(self):
        """Get active employees organized by crew"""
        employees = Employee.query.filter_by(is_active=True, is_supervisor=False).all()
        
        crews = {'A': [], 'B': [], 'C': [], 'D': []}
        for emp in employees:
            if emp.crew in crews:
                crews[emp.crew].append(emp)
        
        return crews
    
    def validate_crews(self, crews):
        """Ensure we have employees in crews"""
        if not any(crews.values()):
            raise ValueError("No active employees found in any crew")
    
    def clear_existing_schedules(self, start_date, end_date, crews):
        """Remove existing schedules in date range for these crews"""
        employee_ids = []
        for crew_employees in crews.values():
            employee_ids.extend([emp.id for emp in crew_employees])
        
        if employee_ids:
            Schedule.query.filter(
                and_(
                    Schedule.employee_id.in_(employee_ids),
                    Schedule.date >= start_date,
                    Schedule.date <= end_date
                )
            ).delete(synchronize_session=False)
            db.session.commit()
            logger.info(f"Cleared existing schedules from {start_date} to {end_date}")
    
    def save_schedules(self, replace_existing=False):
        """Save all generated schedules to database"""
        try:
            db.session.add_all(self.schedules)
            db.session.commit()
            
            logger.info(f"Successfully saved {len(self.schedules)} schedules")
            
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
        
        # Generate schedules
        current_date = start_date
        while current_date <= end_date:
            day_offset = (current_date - start_date).days
            
            for crew_letter, employees in crews.items():
                if not employees:
                    continue
                
                crew_offset = crew_offsets[crew_letter]
                days_since_crew_start = day_offset - crew_offset
                
                # Skip if this crew hasn't started yet
                if days_since_crew_start < 0:
                    continue
                
                # Determine position in 16-day cycle
                cycle_position = days_since_crew_start % self.cycle_days
                shift_code = pattern[cycle_position]
                
                # Skip off days
                if shift_code == 'O':
                    continue
                
                # Determine shift type and times
                if shift_code == 'D':
                    shift_type = ShiftType.DAY
                    start_time = day_start
                    end_time = day_end
                else:  # N
                    shift_type = ShiftType.NIGHT
                    start_time = night_start
                    end_time = night_end
                
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
                        created_by_id=created_by_id
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


class FourOnFourOffModified(PatternGenerator):
    """
    4-on-4-off Modified Pattern - Full Weekends Off
    
    8-week cycle (56 days) with proper 24/7 coverage
    
    CRITICAL FIX 2025-10-10:
    - Crews A & B work DAY shifts with 28-day offset (4 weeks)
    - Crews C & D work NIGHT shifts with 28-day offset (4 weeks)
    - This ensures ONE day crew and ONE night crew working at all times
    - Pattern designed to maximize full weekends off
    - No coverage gaps, no overlaps
    
    Pattern starts on MONDAY (ISO week format)
    """
    
    def __init__(self):
        super().__init__()
        self.pattern_name = "4-on-4-off Modified (Full Weekends Off)"
        self.cycle_days = 56  # 8 weeks
    
    def generate(self, start_date, end_date, created_by_id=None, replace_existing=False):
        """Generate modified 4-on-4-off schedule with full weekends"""
        logger.info(f"Generating 4-on-4-off Modified: {start_date} to {end_date}")
        
        self.validate_date_range(start_date, end_date)
        crews = self.get_crew_employees()
        self.validate_crews(crews)
        
        if replace_existing:
            self.clear_existing_schedules(start_date, end_date, crews)
        
        # CORRECTED 8-week patterns (Monday-Sunday format, 56 days total)
        # 'X' = Work, 'O' = Off
        # These patterns are designed to:
        # 1. Ensure 24/7 coverage (one day crew + one night crew at all times)
        # 2. Maximize full weekends off
        # 3. Eliminate split weekends where possible
        
        # CREW A - DAY SHIFT ONLY
        crew_a_pattern = [
            # Week 1: Mon-Thu work, Fri-Sun off
            'X', 'X', 'X', 'X', 'O', 'O', 'O',
            # Week 2: Mon off, Tue-Fri work, Sat-Sun off
            'O', 'X', 'X', 'X', 'X', 'O', 'O',
            # Week 3: Mon-Tue off, Wed-Sat work, Sun off
            'O', 'O', 'X', 'X', 'X', 'X', 'O',
            # Week 4: Mon-Wed off, Thu-Sun work
            'O', 'O', 'O', 'X', 'X', 'X', 'X',
            # Week 5: Mon-Thu work, Fri-Sun off
            'X', 'X', 'X', 'X', 'O', 'O', 'O',
            # Week 6: Mon off, Tue-Fri work, Sat-Sun off
            'O', 'X', 'X', 'X', 'X', 'O', 'O',
            # Week 7: Mon-Tue off, Wed-Sat work, Sun off
            'O', 'O', 'X', 'X', 'X', 'X', 'O',
            # Week 8: Mon-Wed off, Thu-Sun work
            'O', 'O', 'O', 'X', 'X', 'X', 'X'
        ]
        
        # CREW B - DAY SHIFT ONLY (28-day offset from Crew A)
        # When Crew A is off, Crew B works (and vice versa)
        crew_b_pattern = [
            # Week 1: Mon-Thu off, Fri-Sun work
            'O', 'O', 'O', 'O', 'X', 'X', 'X',
            # Week 2: Mon work, Tue-Fri off, Sat-Sun work
            'X', 'O', 'O', 'O', 'O', 'X', 'X',
            # Week 3: Mon-Tue work, Wed-Sat off, Sun work
            'X', 'X', 'O', 'O', 'O', 'O', 'X',
            # Week 4: Mon-Wed work, Thu-Sun off
            'X', 'X', 'X', 'O', 'O', 'O', 'O',
            # Week 5: Mon-Thu off, Fri-Sun work
            'O', 'O', 'O', 'O', 'X', 'X', 'X',
            # Week 6: Mon work, Tue-Fri off, Sat-Sun work
            'X', 'O', 'O', 'O', 'O', 'X', 'X',
            # Week 7: Mon-Tue work, Wed-Sat off, Sun work
            'X', 'X', 'O', 'O', 'O', 'O', 'X',
            # Week 8: Mon-Wed work, Thu-Sun off
            'X', 'X', 'X', 'O', 'O', 'O', 'O'
        ]
        
        # CREW C - NIGHT SHIFT ONLY (same pattern as Crew A but nights)
        crew_c_pattern = crew_a_pattern.copy()
        
        # CREW D - NIGHT SHIFT ONLY (same pattern as Crew B but nights)
        crew_d_pattern = crew_b_pattern.copy()
        
        crew_patterns = {
            'A': crew_a_pattern,
            'B': crew_b_pattern,
            'C': crew_c_pattern,
            'D': crew_d_pattern
        }
        
        # Shift times
        day_start = time(6, 0)
        day_end = time(18, 0)
        night_start = time(18, 0)
        night_end = time(6, 0)
        
        # Generate schedules
        current_date = start_date
        
        while current_date <= end_date:
            day_offset = (current_date - start_date).days
            
            # Calculate position in 56-day cycle
            cycle_day = day_offset % 56
            
            for crew_letter, employees in crews.items():
                if not employees:
                    continue
                
                # Get shift code for this crew on this cycle day
                shift_code = crew_patterns[crew_letter][cycle_day]
                
                # Skip off days
                if shift_code == 'O':
                    continue
                
                # Determine shift type based on crew
                # A & B work DAYS, C & D work NIGHTS
                if crew_letter in ['A', 'B']:
                    shift_type = ShiftType.DAY
                    start_time = day_start
                    end_time = day_end
                else:  # C or D
                    shift_type = ShiftType.NIGHT
                    start_time = night_start
                    end_time = night_end
                
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
                        created_by_id=created_by_id
                    )
                    self.schedules.append(schedule)
            
            current_date += timedelta(days=1)
        
        logger.info(f"Generated {len(self.schedules)} schedule entries for Modified 4-on-4-off")
        
        # Save to database
        result = self.save_schedules(replace_existing=replace_existing)
        
        # Add statistics
        result['statistics'] = {
            'total_schedules': len(self.schedules),
            'date_range_days': (end_date - start_date).days + 1,
            'pattern_name': self.pattern_name,
            'cycle_length': f"{self.cycle_days} days (8 weeks)",
            'crews_scheduled': [crew for crew, emps in crews.items() if emps]
        }
        
        return result


# Factory function to get the right generator
def get_pattern_generator(pattern, variation=None):
    """
    Get the appropriate pattern generator
    
    Args:
        pattern: Base pattern name (e.g., 'four_on_four_off')
        variation: Pattern variation (e.g., 'weekly', 'fast', 'fixed_simple', 'modified')
    
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
        elif variation == 'modified':
            return FourOnFourOffModified()
    
    return None
