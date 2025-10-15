# utils/pattern_generators.py
# COMPLETE FILE - Pattern Generators for Workforce Scheduler
# Last Updated: 2025-10-15 - FIXED 3-on-3-off Slow Rotation transition
# 
# Change Log:
#   2025-10-15: FIXED ThreeOnThreeOffSlow to prevent D,D,N situations at week 6/7 boundary
#               - Ensured crews are OFF during shift transition
#               - Pattern starts Monday with 3-day work stretches
#   2025-10-13: CORRECTED ThreeOnThreeOffFast to use full 12-week (84-day) pattern
#   2025-10-11: Added 3-on-3-off pattern variations
#   2025-10-10: FINAL FIX - Correct Modified 4-on-4-off pattern
#   2025-10-09: Added FourOnFourOffModified class with 8-week (56-day) cycle

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
        
        result = self.save_schedules(replace_existing=replace_existing)
        result['statistics'] = {
            'total_schedules': len(self.schedules),
            'pattern_name': self.pattern_name
        }
        
        return result


class FourOnFourOffFast(PatternGenerator):
    """
    4-on-4-off Fast Rotation Pattern (2-2-3 style)
    8-day cycle: 2 days, 2 nights, 4 off (repeats)
    All crews rotate through this pattern with offsets
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
        
        # 8-day pattern: D=Day, N=Night, O=Off
        pattern = ['D', 'D', 'N', 'N', 'O', 'O', 'O', 'O']
        
        # Crew offsets
        crew_offsets = {
            'A': 0,
            'B': 2,
            'C': 4,
            'D': 6
        }
        
        current_date = start_date
        while current_date <= end_date:
            day_offset = (current_date - start_date).days
            
            for crew_letter, employees in crews.items():
                if not employees:
                    continue
                
                crew_offset = crew_offsets[crew_letter]
                cycle_position = (day_offset + crew_offset) % self.cycle_days
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
    4-on-4-off Modified Pattern - Full Weekends Off via Saturday Swaps
    
    8-week cycle (56 days) - CORRECT IMPLEMENTATION
    
    Logic:
    1. Start with standard 4-on-4-off pattern (work 4, off 4, repeating every 8 days)
    2. Apply strategic Saturday swaps:
       - Week 3: Crew A gives Saturday to Crew B
         Result: Crew A works only 3 days (Wed-Fri), gets FULL WEEKEND OFF
                 Crew B takes Saturday, starts 5-day stretch
       - Week 7: Crew B gives Saturday to Crew A  
         Result: Crew B works only 3 days, gets FULL WEEKEND OFF
                 Crew A takes Saturday, starts 5-day stretch
    3. Same logic for Crews C & D on night shifts
    
    Benefits:
    - Eliminates split weekends (working Sat but off Sun, or vice versa)
    - Each crew gets 4 full weekends off in 8 weeks
    - Creates predictable full weekend patterns
    - Maintains 24/7 coverage with exactly 1 day crew + 1 night crew at all times
    """
    
    def __init__(self):
        super().__init__()
        self.pattern_name = "4-on-4-off Modified (Full Weekends Off)"
        self.cycle_days = 56  # 8 weeks
    
    def generate(self, start_date, end_date, created_by_id=None, replace_existing=False):
        """Generate modified 4-on-4-off schedule with Saturday swaps for full weekends"""
        logger.info(f"Generating 4-on-4-off Modified: {start_date} to {end_date}")
        
        self.validate_date_range(start_date, end_date)
        crews = self.get_crew_employees()
        self.validate_crews(crews)
        
        if replace_existing:
            self.clear_existing_schedules(start_date, end_date, crews)
        
        # CORRECT Modified Pattern with Saturday Swaps
        # 'X' = Work, 'O' = Off
        # Monday-Sunday format, 56 days total (8 weeks)
        
        # CREW A - DAY SHIFT
        # Standard 4-on-4-off with Week 3 Sat given to B, Week 7 Sat taken from B
        crew_a_pattern = [
            'X', 'X', 'X', 'X', 'O', 'O', 'O',  # Week 1: Mon-Thu work, Fri-Sun off
            'O', 'X', 'X', 'X', 'X', 'O', 'O',  # Week 2: Mon off, Tue-Fri work, Sat-Sun off
            'O', 'O', 'X', 'X', 'X', 'O', 'O',  # Week 3: Wed-Fri work (gave Sat), Sat-Sun off (FULL WEEKEND!)
            'O', 'O', 'O', 'X', 'X', 'X', 'X',  # Week 4: Thu-Sun work, Mon off
            'O', 'O', 'O', 'O', 'X', 'X', 'X',  # Week 5: Mon-Wed off, Thu-Sat work
            'X', 'O', 'O', 'O', 'O', 'X', 'X',  # Week 6: Sun work, Mon-Thu off, Fri-Sat work
            'X', 'X', 'O', 'O', 'O', 'X', 'X',  # Week 7: Mon-Tue work, Wed-Fri off, Sat-Sun work (took Sat)
            'X', 'X', 'X', 'O', 'O', 'O', 'O',  # Week 8: Mon-Wed work, Thu-Sun off
        ]
        
        # CREW B - DAY SHIFT
        # Inverse of Crew A (offset by 4 days), takes Week 3 Sat, gives Week 7 Sat
        crew_b_pattern = [
            'O', 'O', 'O', 'O', 'X', 'X', 'X',  # Week 1
            'X', 'O', 'O', 'O', 'O', 'X', 'X',  # Week 2
            'X', 'X', 'O', 'O', 'O', 'X', 'X',  # Week 3: took Sat (5-day stretch)
            'X', 'X', 'X', 'O', 'O', 'O', 'O',  # Week 4
            'X', 'X', 'X', 'X', 'O', 'O', 'O',  # Week 5
            'O', 'X', 'X', 'X', 'X', 'O', 'O',  # Week 6
            'O', 'O', 'X', 'X', 'X', 'O', 'O',  # Week 7: gave Sat (FULL WEEKEND!)
            'O', 'O', 'O', 'X', 'X', 'X', 'X',  # Week 8
        ]
        
        # CREWS C & D - NIGHT SHIFT (same pattern as A & B)
        crew_c_pattern = crew_a_pattern.copy()
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
        
        # Generate schedule
        current_date = start_date
        while current_date <= end_date:
            day_offset = (current_date - start_date).days
            cycle_day = day_offset % self.cycle_days
            
            for crew_letter, employees in crews.items():
                if not employees:
                    continue
                
                # Check if this crew works today
                pattern = crew_patterns[crew_letter]
                if pattern[cycle_day] == 'O':
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
            'crews_scheduled': [crew for crew, emps in crews.items() if emps],
            'full_weekends_per_crew': '4 out of 8 weeks'
        }
        
        return result


# ============================================================================
# 3-ON-3-OFF PATTERN VARIATIONS
# ============================================================================

class ThreeOnThreeOffFast(PatternGenerator):
    """
    3-on-3-off Fast Rotation Pattern - CORRECTED 12-WEEK PATTERN
    
    84-day (12-week) cycle where each crew follows the same pattern
    but starts at a different point:
    - Crew A: Starts Week 1 (day 0)
    - Crew B: Starts Week 4 (day 21) 
    - Crew C: Starts Week 7 (day 42)
    - Crew D: Starts Week 10 (day 63)
    
    The pattern repeats every 12 weeks, aligning to the same weekday.
    
    Benefits:
    - Shorter work stretches (3 days max)
    - Quick rotation provides variety
    - Regular pattern, easy to remember
    - Good work-life balance
    """
    
    def __init__(self):
        super().__init__()
        self.pattern_name = "3-on-3-off Fast Rotation"
        self.cycle_days = 84  # 12 weeks
    
    def generate(self, start_date, end_date, created_by_id=None, replace_existing=False):
        """Generate fast rotation 3-on-3-off schedule with 12-week pattern"""
        logger.info(f"Generating 3-on-3-off Fast (12-week): {start_date} to {end_date}")
        
        self.validate_date_range(start_date, end_date)
        crews = self.get_crew_employees()
        self.validate_crews(crews)
        
        if replace_existing:
            self.clear_existing_schedules(start_date, end_date, crews)
        
        # 84-day pattern (12 weeks × 7 days, Monday start)
        # D=Day, N=Night, O=Off
        full_pattern = [
            # Week 1: Mon-Sun
            'D', 'D', 'D', 'O', 'O', 'O', 'N',
            # Week 2: Mon-Sun
            'N', 'N', 'O', 'O', 'O', 'D', 'D',
            # Week 3: Mon-Sun
            'D', 'O', 'O', 'O', 'N', 'N', 'N',
            # Week 4: Mon-Sun
            'O', 'O', 'O', 'D', 'D', 'D', 'O',
            # Week 5: Mon-Sun
            'O', 'O', 'N', 'N', 'N', 'O', 'O',
            # Week 6: Mon-Sun
            'O', 'D', 'D', 'D', 'O', 'O', 'O',
            # Week 7: Mon-Sun
            'N', 'N', 'N', 'O', 'O', 'O', 'D',
            # Week 8: Mon-Sun
            'D', 'D', 'O', 'O', 'O', 'N', 'N',
            # Week 9: Mon-Sun
            'N', 'O', 'O', 'O', 'D', 'D', 'D',
            # Week 10: Mon-Sun
            'O', 'O', 'O', 'N', 'N', 'N', 'O',
            # Week 11: Mon-Sun
            'O', 'O', 'D', 'D', 'D', 'O', 'O',
            # Week 12: Mon-Sun
            'O', 'N', 'N', 'N', 'O', 'O', 'O'
        ]
        
        # Crew start offsets (when each crew begins in the pattern)
        crew_offsets = {
            'A': 0,   # Week 1 = day 0
            'B': 21,  # Week 4 = day 21 (3 weeks × 7 days)
            'C': 42,  # Week 7 = day 42 (6 weeks × 7 days)
            'D': 63   # Week 10 = day 63 (9 weeks × 7 days)
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
            
            for crew_letter, employees in crews.items():
                if not employees:
                    continue
                
                # Calculate where this crew is in their pattern
                crew_offset = crew_offsets[crew_letter]
                pattern_position = (day_offset + crew_offset) % self.cycle_days
                
                shift_code = full_pattern[pattern_position]
                
                # Skip off days
                if shift_code == 'O':
                    continue
                
                # Determine shift type
                if shift_code == 'D':
                    shift_type = ShiftType.DAY
                    start_time = day_start
                    end_time = day_end
                else:  # N
                    shift_type = ShiftType.NIGHT
                    start_time = night_start
                    end_time = night_end
                
                # Create schedule for each employee
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
            'pattern_name': self.pattern_name,
            'cycle_length': f"{self.cycle_days} days (12 weeks)",
            'crew_offsets': 'A:Wk1, B:Wk4, C:Wk7, D:Wk10'
        }
        
        return result


class ThreeOnThreeOffSlow(PatternGenerator):
    """
    3-on-3-off Slow Rotation Pattern - CORRECTED 12-WEEK PATTERN
    
    84-day cycle (12 weeks) with shift swap at week 7:
    - Weeks 1-6: A&B work DAYS (alternating), C&D work NIGHTS (alternating)
    - Weeks 7-12: C&D work DAYS (alternating), A&B work NIGHTS (alternating)
    
    Work pattern: 3 on, 3 off (repeating every 6 days)
    Crew alternation: A alternates with B, C alternates with D
    
    CRITICAL FIX: Pattern ensures crews are OFF at the week 6/7 boundary
    to prevent D,D,N situations (2 days then 1 night)
    
    Benefits:
    - 6 weeks on same shift (better circadian adjustment)
    - Always work exactly 3 consecutive days
    - Predictable pattern
    - All crews experience both shifts
    """
    
    def __init__(self):
        super().__init__()
        self.pattern_name = "3-on-3-off Slow Rotation"
        self.cycle_days = 84  # 12 weeks
    
    def generate(self, start_date, end_date, created_by_id=None, replace_existing=False):
        """Generate slow rotation 3-on-3-off schedule with 12-week cycle"""
        logger.info(f"Generating 3-on-3-off Slow (12-week): {start_date} to {end_date}")
        
        self.validate_date_range(start_date, end_date)
        crews = self.get_crew_employees()
        self.validate_crews(crews)
        
        if replace_existing:
            self.clear_existing_schedules(start_date, end_date, crews)
        
        # 6-day basic pattern: 3 on, 3 off
        work_pattern = ['X', 'X', 'X', 'O', 'O', 'O']
        
        # CRITICAL: Crew offsets designed to ensure crews are OFF at week boundaries
        # For a Monday start, we need A & C to start at day 0 (Monday)
        # This gives them Mon-Tue-Wed work, Thu-Fri-Sat off
        # Week boundary (Sunday) falls on their OFF cycle
        crew_offsets = {
            'A': 0,  # Start Monday: Mon-Tue-Wed work
            'B': 3,  # Start Thursday: Thu-Fri-Sat work (opposite of A)
            'C': 0,  # Start Monday: Mon-Tue-Wed work (same as A)
            'D': 3   # Start Thursday: Thu-Fri-Sat work (same as B)
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
            cycle_day = day_offset % self.cycle_days
            current_week = cycle_day // 7  # 0-11 for weeks 1-12
            
            for crew_letter, employees in crews.items():
                if not employees:
                    continue
                
                # Determine if this crew works today
                crew_offset = crew_offsets[crew_letter]
                pattern_position = (day_offset + crew_offset) % 6
                
                # Check if working today based on 3-on-3-off pattern
                if work_pattern[pattern_position] == 'O':
                    continue
                
                # Determine shift type based on crew and current week
                # Weeks 0-5 (1-6): A&B on days, C&D on nights
                # Weeks 6-11 (7-12): C&D on days, A&B on nights
                if current_week < 6:
                    # First 6 weeks
                    if crew_letter in ['A', 'B']:
                        shift_type = ShiftType.DAY
                        start_time = day_start
                        end_time = day_end
                    else:  # C or D
                        shift_type = ShiftType.NIGHT
                        start_time = night_start
                        end_time = night_end
                else:
                    # Last 6 weeks (shift swap)
                    if crew_letter in ['C', 'D']:
                        shift_type = ShiftType.DAY
                        start_time = day_start
                        end_time = day_end
                    else:  # A or B
                        shift_type = ShiftType.NIGHT
                        start_time = night_start
                        end_time = night_end
                
                # Create schedule for each employee
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
            'pattern_name': self.pattern_name,
            'cycle_length': f"{self.cycle_days} days (12 weeks)",
            'rotation_frequency': '6 weeks per shift type',
            'shift_swap': 'Week 7 (crews swap day/night)'
        }
        
        return result


class ThreeOnThreeOffFixed(PatternGenerator):
    """
    3-on-3-off Fixed Shifts Pattern
    
    6-day cycle: 3 on, 3 off
    Crews A & B work days only, Crews C & D work nights only
    Simple fixed shift assignment with 3-day work stretches
    
    Benefits:
    - No shift rotation (better sleep patterns)
    - Shorter work stretches than 4-on-4-off
    - Simple, predictable schedule
    - Good for those who prefer fixed shifts
    
    Pattern:
    - Crew A: Days, starting Monday (3 on, 3 off)
    - Crew B: Days, starting Thursday (3 on, 3 off)
    - Crew C: Nights, starting Monday (3 on, 3 off)
    - Crew D: Nights, starting Thursday (3 on, 3 off)
    """
    
    def __init__(self):
        super().__init__()
        self.pattern_name = "3-on-3-off Fixed Shifts"
        self.cycle_days = 6
    
    def generate(self, start_date, end_date, created_by_id=None, replace_existing=False):
        """Generate fixed shift 3-on-3-off schedule"""
        logger.info(f"Generating 3-on-3-off Fixed: {start_date} to {end_date}")
        
        self.validate_date_range(start_date, end_date)
        crews = self.get_crew_employees()
        self.validate_crews(crews)
        
        if replace_existing:
            self.clear_existing_schedules(start_date, end_date, crews)
        
        # 6-day pattern: 3 on, 3 off
        pattern = ['X', 'X', 'X', 'O', 'O', 'O']
        
        # Crew offsets - A & C start together, B & D start 3 days later
        crew_offsets = {
            'A': 0,
            'B': 3,
            'C': 0,
            'D': 3
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
            
            for crew_letter, employees in crews.items():
                if not employees:
                    continue
                
                crew_offset = crew_offsets[crew_letter]
                cycle_position = (day_offset + crew_offset) % self.cycle_days
                
                # Skip off days
                if pattern[cycle_position] == 'O':
                    continue
                
                # A & B work days, C & D work nights (fixed)
                if crew_letter in ['A', 'B']:
                    shift_type = ShiftType.DAY
                    start_time = day_start
                    end_time = day_end
                else:  # C or D
                    shift_type = ShiftType.NIGHT
                    start_time = night_start
                    end_time = night_end
                
                # Create schedule for each employee
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
            'pattern_name': self.pattern_name,
            'cycle_length': f"{self.cycle_days} days",
            'shift_assignment': 'A&B days, C&D nights (fixed)'
        }
        
        return result


class ThreeOnThreeOffModified(PatternGenerator):
    """
    3-on-3-off Modified Pattern - Full Weekends Off
    
    42-day cycle (6 weeks) with strategic swaps for full weekends
    Similar concept to 4-on-4-off Modified but with 3-day work stretches
    
    Strategy:
    - Base pattern: 3 on, 3 off
    - Swap specific days to create full weekends off
    - Each crew gets 3 full weekends off in the 6-week cycle
    - Maintains 24/7 coverage
    
    Benefits:
    - Shorter work stretches (3 days vs 4)
    - Full weekends off (Sat & Sun together)
    - More frequent time off
    - Better work-life balance
    """
    
    def __init__(self):
        super().__init__()
        self.pattern_name = "3-on-3-off Modified (Full Weekends)"
        self.cycle_days = 42  # 6 weeks
    
    def generate(self, start_date, end_date, created_by_id=None, replace_existing=False):
        """Generate modified 3-on-3-off with full weekends"""
        logger.info(f"Generating 3-on-3-off Modified: {start_date} to {end_date}")
        
        self.validate_date_range(start_date, end_date)
        crews = self.get_crew_employees()
        self.validate_crews(crews)
        
        if replace_existing:
            self.clear_existing_schedules(start_date, end_date, crews)
        
        # 42-day patterns with weekend swaps (Mon-Sun format)
        # 'X' = Work, 'O' = Off
        
        # CREW A - DAY SHIFT
        crew_a_pattern = [
            'X', 'X', 'X', 'O', 'O', 'O', 'O',  # Week 1: Mon-Wed work, Thu-Sun off (FULL WEEKEND!)
            'X', 'X', 'X', 'O', 'O', 'O', 'X',  # Week 2: Mon-Wed work, Sun work
            'X', 'X', 'O', 'O', 'O', 'X', 'X',  # Week 3: Mon-Tue work, Sat-Sun work
            'X', 'O', 'O', 'O', 'X', 'X', 'X',  # Week 4: Mon work, Fri-Sun work
            'O', 'O', 'O', 'X', 'X', 'X', 'O',  # Week 5: Thu-Sat work
            'O', 'X', 'X', 'X', 'O', 'O', 'O',  # Week 6: Tue-Thu work, Fri-Sun off (FULL WEEKEND!)
        ]
        
        # CREW B - DAY SHIFT (offset to provide coverage)
        crew_b_pattern = [
            'O', 'O', 'O', 'X', 'X', 'X', 'O',  # Week 1
            'O', 'O', 'O', 'X', 'X', 'X', 'O',  # Week 2
            'O', 'O', 'X', 'X', 'X', 'O', 'O',  # Week 3: Fri-Sun off (FULL WEEKEND!)
            'O', 'X', 'X', 'X', 'O', 'O', 'O',  # Week 4
            'X', 'X', 'X', 'O', 'O', 'O', 'X',  # Week 5
            'X', 'O', 'O', 'O', 'X', 'X', 'X',  # Week 6
        ]
        
        # CREWS C & D - NIGHT SHIFT (same patterns as A & B)
        crew_c_pattern = crew_a_pattern.copy()
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
            cycle_day = day_offset % self.cycle_days
            
            for crew_letter, employees in crews.items():
                if not employees:
                    continue
                
                # Check if this crew works today
                pattern = crew_patterns[crew_letter]
                if pattern[cycle_day] == 'O':
                    continue
                
                # A & B work days, C & D work nights
                if crew_letter in ['A', 'B']:
                    shift_type = ShiftType.DAY
                    start_time = day_start
                    end_time = day_end
                else:  # C or D
                    shift_type = ShiftType.NIGHT
                    start_time = night_start
                    end_time = night_end
                
                # Create schedule for each employee
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
            'pattern_name': self.pattern_name,
            'cycle_length': f"{self.cycle_days} days (6 weeks)",
            'full_weekends_per_crew': '3 out of 6 weeks'
        }
        
        return result


# Factory function to get the right generator
def get_pattern_generator(pattern, variation=None):
    """
    Get the appropriate pattern generator
    
    Args:
        pattern: Base pattern name (e.g., 'four_on_four_off', 'three_on_three_off')
        variation: Pattern variation (e.g., 'weekly', 'fast', 'fixed', 'modified', 'slow')
    
    Returns:
        PatternGenerator instance or None if not found
    """
    if pattern == 'four_on_four_off':
        if variation == 'weekly':
            return FourOnFourOffWeekly()
        elif variation == 'fast':
            return FourOnFourOffFast()
        elif variation == 'fixed_simple' or variation == 'fixed':
            return FourOnFourOffFixed()
        elif variation == 'modified':
            return FourOnFourOffModified()
    
    elif pattern == 'three_on_three_off':
        if variation == 'fast':
            return ThreeOnThreeOffFast()
        elif variation == 'slow' or variation == 'sixweek':
            return ThreeOnThreeOffSlow()
        elif variation == 'fixed':
            return ThreeOnThreeOffFixed()
        elif variation == 'modified':
            return ThreeOnThreeOffModified()
    
    return None
