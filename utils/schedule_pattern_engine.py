# utils/schedule_pattern_engine.py
"""
Core schedule generation engine for all shift patterns
Implements Pitman, DuPont, Southern Swing, and other patterns
UPDATED WITH COMPLETE HOURS SUPPORT
"""

from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional
from models import db, Schedule, Employee, Position
import logging

logger = logging.getLogger(__name__)

class SchedulePatternEngine:
    """Generate schedules based on various shift patterns with proper hours tracking"""
    
    # Shift timing defaults with hours
    SHIFT_TIMES = {
        '12-hour': {
            'day': {'start': '06:00', 'end': '18:00', 'hours': 12.0},
            'night': {'start': '18:00', 'end': '06:00', 'hours': 12.0}
        },
        '8-hour': {
            'day': {'start': '07:00', 'end': '15:00', 'hours': 8.0},
            'evening': {'start': '15:00', 'end': '23:00', 'hours': 8.0},
            'night': {'start': '23:00', 'end': '07:00', 'hours': 8.0}
        },
        'custom': {
            # Can be overridden in config
            'day': {'start': '06:00', 'end': '18:00', 'hours': 12.0},
            'evening': {'start': '14:00', 'end': '22:00', 'hours': 8.0},
            'night': {'start': '22:00', 'end': '06:00', 'hours': 8.0}
        }
    }
    
    def __init__(self):
        self.crews = ['A', 'B', 'C', 'D']
        
    def generate_schedule(self, pattern: str, start_date: date, end_date: date, 
                         config: Dict) -> List[Schedule]:
        """
        Generate schedules based on pattern type
        
        Args:
            pattern: Pattern name (pitman, dupont, etc.)
            start_date: Start date for schedule
            end_date: End date for schedule
            config: Pattern-specific configuration including:
                - shift_length: '12-hour', '8-hour', or 'custom'
                - day_shift_start: Start time for day shifts
                - night_shift_start: Start time for night shifts
                - evening_shift_start: Start time for evening shifts
                - custom_hours: Dict with custom hours per shift type
                - created_by_id: ID of user creating the schedule
                
        Returns:
            List of Schedule objects (not yet committed to DB)
        """
        
        pattern_generators = {
            'pitman': self._generate_pitman,
            'dupont': self._generate_dupont,
            'southern_swing': self._generate_southern_swing,
            'fixed_fixed': self._generate_fixed_fixed,
            'five_and_two': self._generate_five_and_two,
            'four_on_four_off': self._generate_four_on_four_off,
            'panama': self._generate_panama,
            'continental': self._generate_continental
        }
        
        generator = pattern_generators.get(pattern)
        if not generator:
            raise ValueError(f"Unknown pattern: {pattern}")
        
        # Set up shift times based on configuration
        self._setup_shift_times(config)
        
        return generator(start_date, end_date, config)
    
    def _setup_shift_times(self, config: Dict):
        """Setup shift times based on configuration"""
        shift_length = config.get('shift_length', '12-hour')
        
        if shift_length in self.SHIFT_TIMES:
            self.current_shift_times = self.SHIFT_TIMES[shift_length].copy()
        else:
            # Default to 12-hour
            self.current_shift_times = self.SHIFT_TIMES['12-hour'].copy()
        
        # Override with custom times if provided
        custom_times = config.get('custom_shift_times', {})
        for shift_type, times in custom_times.items():
            if shift_type in self.current_shift_times:
                self.current_shift_times[shift_type].update(times)
        
        # Override with individual time settings
        if config.get('day_shift_start'):
            self.current_shift_times['day']['start'] = config['day_shift_start']
        if config.get('night_shift_start'):
            self.current_shift_times['night']['start'] = config['night_shift_start']
        if config.get('evening_shift_start') and 'evening' in self.current_shift_times:
            self.current_shift_times['evening']['start'] = config['evening_shift_start']
        
        # Override hours if specified
        custom_hours = config.get('custom_hours', {})
        for shift_type, hours in custom_hours.items():
            if shift_type in self.current_shift_times:
                self.current_shift_times[shift_type]['hours'] = float(hours)
    
    def _create_schedule(self, employee_id: int, date: date, shift_type: str, 
                        position_id: Optional[int] = None, 
                        created_by_id: Optional[int] = None,
                        is_overtime: bool = False) -> Schedule:
        """Create a single schedule entry with proper hours calculation"""
        
        shift_info = self.current_shift_times.get(shift_type, self.current_shift_times['day'])
        
        start_time_str = shift_info['start']
        hours = shift_info['hours']
        
        # Parse start time
        start_time = datetime.strptime(start_time_str, '%H:%M').time()
        
        # Calculate end time
        start_datetime = datetime.combine(date, start_time)
        end_datetime = start_datetime + timedelta(hours=hours)
        end_time = end_datetime.time()
        
        # Handle day overflow for night shifts
        if end_datetime.date() > date:
            # Night shift crosses midnight
            pass  # end_time is correct for next day
        
        return Schedule(
            employee_id=employee_id,
            date=date,
            shift_type=shift_type,
            start_time=start_time,
            end_time=end_time,
            hours=hours,
            position_id=position_id,
            created_by_id=created_by_id,
            is_overtime=is_overtime,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
    
    def _generate_pitman(self, start_date: date, end_date: date, config: Dict) -> List[Schedule]:
        """
        Generate Pitman (2-2-3) schedule
        Pattern: Work 2, off 2, work 3, off 2, work 2, off 3
        """
        schedules = []
        
        # Get configuration
        variation = config.get('variation', 'fixed')  # fixed, rapid, 2_week, 4_week
        created_by_id = config.get('created_by_id')
        
        # Pitman pattern (14-day cycle)
        # 1 = work, 0 = off
        base_pattern = [1,1,0,0,1,1,1,0,0,1,1,0,0,0]
        
        # Crew patterns - each crew starts at different point in cycle
        crew_patterns = {
            'A': base_pattern,
            'B': self._rotate_pattern(base_pattern, 7),  # Offset by 7 days
            'C': base_pattern,  # Same as A but nights
            'D': self._rotate_pattern(base_pattern, 7)   # Same as B but nights
        }
        
        current_date = start_date
        day_index = 0
        
        # Determine which crews work which shifts based on variation
        if variation == 'fixed':
            day_crews = ['A', 'B']
            night_crews = ['C', 'D']
        else:
            # For rotating variations, we'll need to track rotation periods
            day_crews = self.crews
            night_crews = self.crews
            
        while current_date <= end_date:
            cycle_day = day_index % 14
            
            # Get employees for each crew
            for crew in self.crews:
                if crew_patterns[crew][cycle_day] == 1:  # Working day
                    crew_employees = Employee.query.filter_by(
                        crew=crew, 
                        is_active=True
                    ).all()
                    
                    # Determine shift type
                    if variation == 'fixed':
                        shift_type = 'day' if crew in day_crews else 'night'
                    else:
                        # Handle rotating variations
                        shift_type, _ = self._get_rotating_shift(
                            crew, current_date, start_date, variation
                        )
                    
                    # Create schedules for all employees in this crew
                    for emp in crew_employees:
                        schedule = self._create_schedule(
                            employee_id=emp.id,
                            date=current_date,
                            shift_type=shift_type,
                            position_id=emp.position_id,
                            created_by_id=created_by_id
                        )
                        schedules.append(schedule)
            
            current_date += timedelta(days=1)
            day_index += 1
            
        return schedules
    
    def _generate_dupont(self, start_date: date, end_date: date, config: Dict) -> List[Schedule]:
        """
        Generate DuPont schedule
        28-day rotating cycle with 7 consecutive days off
        Pattern: 4N-3off-3D-1off-3N-3off-4D-7off
        """
        schedules = []
        created_by_id = config.get('created_by_id')
        
        # DuPont pattern (28-day cycle)
        # D = day, N = night, O = off
        pattern = [
            'N','N','N','N','O','O','O',  # 4 nights, 3 off
            'D','D','D','O',               # 3 days, 1 off
            'N','N','N','O','O','O',       # 3 nights, 3 off
            'D','D','D','D',               # 4 days
            'O','O','O','O','O','O','O'    # 7 off
        ]
        
        # Each crew starts at different week
        crew_start_offsets = {'A': 0, 'B': 7, 'C': 14, 'D': 21}
        
        current_date = start_date
        day_index = 0
        
        while current_date <= end_date:
            for crew in self.crews:
                # Calculate position in pattern for this crew
                crew_day_index = (day_index + crew_start_offsets[crew]) % 28
                shift = pattern[crew_day_index]
                
                if shift != 'O':  # Not an off day
                    crew_employees = Employee.query.filter_by(
                        crew=crew, 
                        is_active=True
                    ).all()
                    
                    shift_type = 'day' if shift == 'D' else 'night'
                    
                    for emp in crew_employees:
                        schedule = self._create_schedule(
                            employee_id=emp.id,
                            date=current_date,
                            shift_type=shift_type,
                            position_id=emp.position_id,
                            created_by_id=created_by_id
                        )
                        schedules.append(schedule)
            
            current_date += timedelta(days=1)
            day_index += 1
            
        return schedules
    
    def _generate_southern_swing(self, start_date: date, end_date: date, config: Dict) -> List[Schedule]:
        """
        Generate Southern Swing schedule
        8-hour shifts rotating through days, evenings, nights over 4 weeks
        """
        schedules = []
        created_by_id = config.get('created_by_id')
        
        # Southern Swing pattern (28-day cycle)
        # Each week has different shift pattern
        weekly_patterns = [
            # Week 1: Mon-Fri days, weekend off
            ['D','D','D','D','D','O','O'],
            # Week 2: Mon-Tue off, Wed-Sun evenings
            ['O','O','E','E','E','E','E'],
            # Week 3: Mon-Tue evenings, Wed off, Thu-Sun nights
            ['E','E','O','N','N','N','N'],
            # Week 4: Mon-Wed nights, Thu-Fri off, Sat-Sun days
            ['N','N','N','O','O','D','D']
        ]
        
        # Crew rotation - each crew starts at different week
        crew_week_offsets = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
        
        current_date = start_date
        
        while current_date <= end_date:
            # Determine week and day
            days_from_start = (current_date - start_date).days
            week_index = (days_from_start // 7) % 4
            day_of_week = current_date.weekday()  # 0 = Monday
            
            for crew in self.crews:
                # Calculate which week pattern this crew is on
                crew_week = (week_index + crew_week_offsets[crew]) % 4
                shift = weekly_patterns[crew_week][day_of_week]
                
                if shift != 'O':  # Not an off day
                    crew_employees = Employee.query.filter_by(
                        crew=crew, 
                        is_active=True
                    ).all()
                    
                    # Map shift type
                    shift_mapping = {
                        'D': 'day',
                        'E': 'evening',
                        'N': 'night'
                    }
                    
                    shift_type = shift_mapping[shift]
                    
                    for emp in crew_employees:
                        schedule = self._create_schedule(
                            employee_id=emp.id,
                            date=current_date,
                            shift_type=shift_type,
                            position_id=emp.position_id,
                            created_by_id=created_by_id
                        )
                        schedules.append(schedule)
            
            current_date += timedelta(days=1)
            
        return schedules
    
    def _generate_fixed_fixed(self, start_date: date, end_date: date, config: Dict) -> List[Schedule]:
        """
        Generate Fixed-Fixed schedule
        Mon-Thu crews work 4 days (48 hrs/week)
        Fri-Sun crews work 3 days (36 hrs/week)
        """
        schedules = []
        created_by_id = config.get('created_by_id')
        
        # Crew assignments for Fixed-Fixed
        weekday_crews = ['A', 'B']  # Mon-Thu
        weekend_crews = ['C', 'D']  # Fri-Sun
        
        current_date = start_date
        
        while current_date <= end_date:
            day_of_week = current_date.weekday()  # 0 = Monday
            
            # Determine which crews work today
            if day_of_week < 4:  # Monday-Thursday
                working_crews = weekday_crews
            else:  # Friday-Sunday
                working_crews = weekend_crews
            
            # Assign shifts
            for i, crew in enumerate(working_crews):
                crew_employees = Employee.query.filter_by(
                    crew=crew, 
                    is_active=True
                ).all()
                
                # Alternate day/night between crews
                shift_type = 'day' if i == 0 else 'night'
                
                for emp in crew_employees:
                    schedule = self._create_schedule(
                        employee_id=emp.id,
                        date=current_date,
                        shift_type=shift_type,
                        position_id=emp.position_id,
                        created_by_id=created_by_id
                    )
                    schedules.append(schedule)
            
            current_date += timedelta(days=1)
            
        return schedules
    
    def _generate_five_and_two(self, start_date: date, end_date: date, config: Dict) -> List[Schedule]:
        """
        Generate 5&2 schedule
        Work stretches of 5 and 2 days, off stretches of 5 and 2 days
        """
        schedules = []
        created_by_id = config.get('created_by_id')
        
        # 5&2 patterns (14-day cycles)
        # Different patterns for day and night crews
        day_patterns = {
            'A': [1,1,1,1,1,0,0,1,1,0,0,0,0,0],  # 5 on, 2 off, 2 on, 5 off
            'B': [0,0,0,0,0,1,1,0,0,1,1,1,1,1]   # Opposite of A
        }
        night_patterns = {
            'C': [1,1,0,0,0,0,0,1,1,1,1,1,0,0],  # 2 on, 5 off, 5 on, 2 off
            'D': [0,0,1,1,1,1,1,0,0,0,0,0,1,1]   # Opposite of C
        }
        
        current_date = start_date
        day_index = 0
        
        while current_date <= end_date:
            cycle_day = day_index % 14
            
            # Process each crew
            for crew in self.crews:
                pattern = day_patterns.get(crew, night_patterns.get(crew))
                
                if pattern and pattern[cycle_day] == 1:  # Working day
                    crew_employees = Employee.query.filter_by(
                        crew=crew, 
                        is_active=True
                    ).all()
                    
                    shift_type = 'day' if crew in ['A', 'B'] else 'night'
                    
                    for emp in crew_employees:
                        schedule = self._create_schedule(
                            employee_id=emp.id,
                            date=current_date,
                            shift_type=shift_type,
                            position_id=emp.position_id,
                            created_by_id=created_by_id
                        )
                        schedules.append(schedule)
            
            current_date += timedelta(days=1)
            day_index += 1
            
        return schedules
    
    def _generate_four_on_four_off(self, start_date: date, end_date: date, config: Dict) -> List[Schedule]:
        """
        Generate 4-on-4-off schedule
        Simple pattern: Work 4 days, off 4 days
        """
        schedules = []
        created_by_id = config.get('created_by_id')
        
        # 4-on-4-off pattern (8-day cycle)
        base_pattern = [1,1,1,1,0,0,0,0]
        
        # Each crew starts at different point
        crew_patterns = {
            'A': base_pattern,
            'B': self._rotate_pattern(base_pattern, 4),
            'C': base_pattern,  # Same as A but nights
            'D': self._rotate_pattern(base_pattern, 4)  # Same as B but nights
        }
        
        current_date = start_date
        day_index = 0
        
        while current_date <= end_date:
            cycle_day = day_index % 8
            
            for crew in self.crews:
                if crew_patterns[crew][cycle_day] == 1:
                    crew_employees = Employee.query.filter_by(
                        crew=crew, 
                        is_active=True
                    ).all()
                    
                    # A & B work days, C & D work nights
                    shift_type = 'day' if crew in ['A', 'B'] else 'night'
                    
                    for emp in crew_employees:
                        schedule = self._create_schedule(
                            employee_id=emp.id,
                            date=current_date,
                            shift_type=shift_type,
                            position_id=emp.position_id,
                            created_by_id=created_by_id
                        )
                        schedules.append(schedule)
            
            current_date += timedelta(days=1)
            day_index += 1
            
        return schedules
    
    def _generate_panama(self, start_date: date, end_date: date, config: Dict) -> List[Schedule]:
        """
        Generate Panama schedule (2-3-2 variation)
        Similar to Pitman but different rhythm
        """
        schedules = []
        created_by_id = config.get('created_by_id')
        
        # Panama pattern - variation of 2-2-3
        base_pattern = [1,1,0,0,0,1,1,1,0,0,1,1,0,0]  # 14-day cycle
        
        crew_patterns = {
            'A': base_pattern,
            'B': self._rotate_pattern(base_pattern, 7),
            'C': base_pattern,
            'D': self._rotate_pattern(base_pattern, 7)
        }
        
        current_date = start_date
        day_index = 0
        
        while current_date <= end_date:
            cycle_day = day_index % 14
            
            for crew in self.crews:
                if crew_patterns[crew][cycle_day] == 1:
                    crew_employees = Employee.query.filter_by(
                        crew=crew, 
                        is_active=True
                    ).all()
                    
                    shift_type = 'day' if crew in ['A', 'B'] else 'night'
                    
                    for emp in crew_employees:
                        schedule = self._create_schedule(
                            employee_id=emp.id,
                            date=current_date,
                            shift_type=shift_type,
                            position_id=emp.position_id,
                            created_by_id=created_by_id
                        )
                        schedules.append(schedule)
            
            current_date += timedelta(days=1)
            day_index += 1
            
        return schedules
    
    def _generate_continental(self, start_date: date, end_date: date, config: Dict) -> List[Schedule]:
        """
        Generate Continental schedule
        Pattern: 2D-2O-3D-2O-2D-3O-2N-2O-3N-2O-2N-3O
        """
        schedules = []
        created_by_id = config.get('created_by_id')
        
        # Continental pattern (42-day cycle)
        pattern = [
            'D','D','O','O','D','D','D','O','O','D','D','O','O','O',  # Days
            'N','N','O','O','N','N','N','O','O','N','N','O','O','O',  # Nights
            'O','O','O','O','O','O','O','O','O','O','O','O','O','O'   # Rest period
        ]
        
        # Crew offsets
        crew_offsets = {'A': 0, 'B': 10, 'C': 21, 'D': 31}
        
        current_date = start_date
        day_index = 0
        
        while current_date <= end_date:
            for crew in self.crews:
                crew_day = (day_index + crew_offsets[crew]) % 42
                shift = pattern[crew_day]
                
                if shift != 'O':
                    crew_employees = Employee.query.filter_by(
                        crew=crew, 
                        is_active=True
                    ).all()
                    
                    shift_type = 'day' if shift == 'D' else 'night'
                    
                    for emp in crew_employees:
                        schedule = self._create_schedule(
                            employee_id=emp.id,
                            date=current_date,
                            shift_type=shift_type,
                            position_id=emp.position_id,
                            created_by_id=created_by_id
                        )
                        schedules.append(schedule)
            
            current_date += timedelta(days=1)
            day_index += 1
            
        return schedules
    
    # Helper methods
    def _rotate_pattern(self, pattern: List[int], offset: int) -> List[int]:
        """Rotate a pattern by offset days"""
        return pattern[offset:] + pattern[:offset]
    
    def _get_rotating_shift(self, crew: str, current_date: date, start_date: date, 
                           variation: str) -> Tuple[str, str]:
        """
        Determine shift type for rotating variations
        Returns (shift_type, shift_start_time)
        """
        days_from_start = (current_date - start_date).days
        
        if variation == 'rapid':
            # Change every break period (roughly every 3-4 days)
            rotation_period = days_from_start // 4
        elif variation == '2_week':
            # Change every 2 weeks
            rotation_period = days_from_start // 14
        elif variation == '4_week':
            # Change every 4 weeks
            rotation_period = days_from_start // 28
        else:
            rotation_period = 0
        
        # Determine if on days or nights based on rotation
        crew_index = self.crews.index(crew)
        is_day_shift = ((crew_index + rotation_period) % 2) == 0
        
        shift_type = 'day' if is_day_shift else 'night'
        shift_start = self.current_shift_times[shift_type]['start']
        
        return shift_type, shift_start
    
    def calculate_weekly_hours(self, schedules: List[Schedule], employee_id: int, 
                              week_start: date) -> Dict[str, float]:
        """
        Calculate total hours for an employee in a given week
        
        Args:
            schedules: List of Schedule objects
            employee_id: Employee ID to calculate for
            week_start: Start date of the week (Monday)
            
        Returns:
            Dict with regular_hours, overtime_hours, total_hours
        """
        week_end = week_start + timedelta(days=6)
        
        # Filter schedules for this employee and week
        employee_week_schedules = [
            s for s in schedules 
            if s.employee_id == employee_id 
            and week_start <= s.date <= week_end
        ]
        
        total_hours = sum(s.hours for s in employee_week_schedules)
        regular_hours = min(total_hours, 40.0)
        overtime_hours = max(0.0, total_hours - 40.0)
        
        return {
            'regular_hours': regular_hours,
            'overtime_hours': overtime_hours,
            'total_hours': total_hours,
            'shifts_worked': len(employee_week_schedules)
        }
    
    def validate_schedule(self, schedules: List[Schedule]) -> Dict[str, any]:
        """
        Validate generated schedules for coverage and conflicts
        Returns validation results with any issues found
        """
        validation_results = {
            'is_valid': True,
            'coverage_gaps': [],
            'conflicts': [],
            'overtime_concerns': [],
            'statistics': {},
            'hours_analysis': {}
        }
        
        if not schedules:
            validation_results['is_valid'] = False
            validation_results['error'] = "No schedules generated"
            return validation_results
        
        # Group schedules by date and employee
        schedules_by_date = {}
        schedules_by_employee = {}
        
        for schedule in schedules:
            date_key = schedule.date
            emp_id = schedule.employee_id
            
            if date_key not in schedules_by_date:
                schedules_by_date[date_key] = []
            schedules_by_date[date_key].append(schedule)
            
            if emp_id not in schedules_by_employee:
                schedules_by_employee[emp_id] = []
            schedules_by_employee[emp_id].append(schedule)
        
        # Check for scheduling conflicts (employee scheduled multiple times per day)
        for date_key, date_schedules in schedules_by_date.items():
            employee_schedules_today = {}
            for schedule in date_schedules:
                emp_id = schedule.employee_id
                if emp_id in employee_schedules_today:
                    validation_results['conflicts'].append({
                        'date': date_key,
                        'employee_id': emp_id,
                        'issue': 'Multiple schedules on same day'
                    })
                    validation_results['is_valid'] = False
                else:
                    employee_schedules_today[emp_id] = schedule
        
        # Check coverage for each date
        for date_key, date_schedules in schedules_by_date.items():
            # Check minimum coverage requirements
            day_count = sum(1 for s in date_schedules if s.shift_type == 'day')
            night_count = sum(1 for s in date_schedules if s.shift_type == 'night')
            evening_count = sum(1 for s in date_schedules if s.shift_type == 'evening')
            
            # Configurable minimum coverage (adjust as needed)
            min_per_shift = 8  # Minimum staff per shift
            
            if day_count > 0 and day_count < min_per_shift:
                validation_results['coverage_gaps'].append({
                    'date': date_key,
                    'shift': 'day',
                    'scheduled': day_count,
                    'required': min_per_shift
                })
            
            if night_count > 0 and night_count < min_per_shift:
                validation_results['coverage_gaps'].append({
                    'date': date_key,
                    'shift': 'night',
                    'scheduled': night_count,
                    'required': min_per_shift
                })
        
        # Analyze hours and overtime
        start_date = min(s.date for s in schedules)
        end_date = max(s.date for s in schedules)
        
        # Get first Monday on or before start date
        days_to_monday = start_date.weekday()
        week_start = start_date - timedelta(days=days_to_monday)
        
        total_overtime_hours = 0
        employees_with_overtime = 0
        
        while week_start <= end_date:
            for emp_id in schedules_by_employee:
                weekly_hours = self.calculate_weekly_hours(schedules, emp_id, week_start)
                
                if weekly_hours['overtime_hours'] > 0:
                    total_overtime_hours += weekly_hours['overtime_hours']
                    
                    if weekly_hours['overtime_hours'] > 16:  # High overtime threshold
                        validation_results['overtime_concerns'].append({
                            'employee_id': emp_id,
                            'week_start': week_start,
                            'total_hours': weekly_hours['total_hours'],
                            'overtime_hours': weekly_hours['overtime_hours']
                        })
            
            week_start += timedelta(days=7)
        
        # Calculate statistics
        validation_results['statistics'] = {
            'total_schedules': len(schedules),
            'unique_employees': len(set(s.employee_id for s in schedules)),
            'date_range': f"{min(s.date for s in schedules)} to {max(s.date for s in schedules)}",
            'avg_shifts_per_day': len(schedules) / len(schedules_by_date) if schedules_by_date else 0,
            'total_coverage_gaps': len(validation_results['coverage_gaps']),
            'total_conflicts': len(validation_results['conflicts'])
        }
        
        # Hours analysis
        total_scheduled_hours = sum(s.hours for s in schedules)
        avg_hours_per_employee = total_scheduled_hours / len(schedules_by_employee) if schedules_by_employee else 0
        
        validation_results['hours_analysis'] = {
            'total_scheduled_hours': total_scheduled_hours,
            'total_overtime_hours': total_overtime_hours,
            'avg_hours_per_employee': avg_hours_per_employee,
            'employees_with_overtime': employees_with_overtime,
            'overtime_percentage': (total_overtime_hours / total_scheduled_hours * 100) if total_scheduled_hours > 0 else 0
        }
        
        return validation_results
    
    def generate_overtime_opportunities(self, schedules: List[Schedule], 
                                      target_date: date) -> List[Dict]:
        """
        Identify overtime opportunities based on coverage gaps
        
        Args:
            schedules: Current schedule list
            target_date: Date to analyze for overtime needs
            
        Returns:
            List of overtime opportunity dictionaries
        """
        opportunities = []
        
        # Get schedules for target date
        date_schedules = [s for s in schedules if s.date == target_date]
        
        # Analyze coverage by shift
        shift_coverage = {}
        for schedule in date_schedules:
            shift_type = schedule.shift_type
            if shift_type not in shift_coverage:
                shift_coverage[shift_type] = []
            shift_coverage[shift_type].append(schedule)
        
        # Determine if additional coverage is needed
        target_coverage = {'day': 12, 'night': 10, 'evening': 8}  # Configurable
        
        for shift_type, target_count in target_coverage.items():
            current_count = len(shift_coverage.get(shift_type, []))
            
            if current_count < target_count:
                gap = target_count - current_count
                
                # Create overtime opportunity
                shift_info = self.current_shift_times.get(shift_type, self.current_shift_times['day'])
                
                opportunities.append({
                    'date': target_date,
                    'shift_type': shift_type,
                    'positions_needed': gap,
                    'hours': shift_info['hours'],
                    'start_time': shift_info['start'],
                    'priority': 'high' if gap > 3 else 'medium',
                    'reason': f'Coverage gap: {current_count}/{target_count}'
                })
        
        return opportunities
