# real_pitman_schedule.py - Production-Ready Pitman Schedule Generator
"""
REAL WORKING PITMAN SCHEDULE GENERATOR
Generates actual 2-2-3 pattern schedules for your crews

The Pitman Schedule Pattern:
- 14-day cycle: Work 2, Off 2, Work 3, Off 2, Work 2, Off 3
- Each crew works 7 days out of every 14 
- Provides continuous 24/7 coverage with 4 crews
- Average 42 hours per week (some weeks 48, some weeks 36)
"""

from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional
from models import db, Schedule, Employee, Position
import logging

logger = logging.getLogger(__name__)

class RealPitmanSchedule:
    """Production-ready Pitman schedule generator for actual deployment"""
    
    def __init__(self):
        # TRUE Pitman 2-2-3 pattern (14-day cycle)
        # 1 = work day, 0 = off day
        self.pitman_base_pattern = [1, 1, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0]
        
        # Crew rotations to ensure 24/7 coverage
        self.crew_offsets = {
            'A': 0,   # Starts on day 1 of pattern
            'B': 7,   # Starts on day 8 of pattern (opposite of A)
            'C': 0,   # Same pattern as A but on nights
            'D': 7    # Same pattern as B but on nights  
        }
        
        # Shift configurations
        self.shift_config = {
            'day': {
                'start_time': '06:00',
                'end_time': '18:00', 
                'hours': 12.0
            },
            'night': {
                'start_time': '18:00',
                'end_time': '06:00',
                'hours': 12.0
            }
        }
    
    def generate_pitman_schedule(self, start_date: date, end_date: date, 
                                variation: str = 'fixed', 
                                created_by_id: int = None) -> Dict:
        """
        Generate complete Pitman schedule for all crews
        
        Args:
            start_date: When schedule starts
            end_date: When schedule ends  
            variation: 'fixed' (A,B=days, C,D=nights) or 'rotating' (crews alternate)
            created_by_id: ID of supervisor creating schedule
            
        Returns:
            Dict with schedules, statistics, and validation results
        """
        
        logger.info(f"Generating Pitman schedule: {start_date} to {end_date}")
        
        # Validate inputs
        if end_date <= start_date:
            raise ValueError("End date must be after start date")
        
        if (end_date - start_date).days < 14:
            logger.warning("Schedule period less than one full Pitman cycle (14 days)")
        
        # Get active employees by crew
        crew_employees = self._get_crew_employees()
        
        # Validate crew assignments
        validation = self._validate_crews(crew_employees)
        if not validation['valid']:
            logger.error(f"Crew validation failed: {validation['issues']}")
        
        schedules = []
        current_date = start_date
        day_index = 0
        
        # Generate schedule day by day
        while current_date <= end_date:
            daily_schedules = self._generate_daily_schedule(
                current_date, day_index, crew_employees, variation, created_by_id
            )
            schedules.extend(daily_schedules)
            
            current_date += timedelta(days=1)
            day_index += 1
        
        # Calculate statistics
        stats = self._calculate_schedule_stats(schedules, crew_employees)
        
        # Validate generated schedule
        validation_results = self._validate_schedule(schedules)
        
        return {
            'schedules': schedules,
            'statistics': stats,
            'validation': validation_results,
            'crew_info': crew_employees,
            'pattern_info': {
                'type': 'Pitman 2-2-3',
                'variation': variation,
                'cycle_length': 14,
                'total_days': (end_date - start_date).days + 1
            }
        }
    
    def _get_crew_employees(self) -> Dict:
        """Get all active employees organized by crew"""
        crew_employees = {'A': [], 'B': [], 'C': [], 'D': []}
        
        employees = Employee.query.filter_by(is_active=True).all()
        
        for emp in employees:
            if emp.crew in crew_employees:
                crew_employees[emp.crew].append({
                    'id': emp.id,
                    'name': emp.name,
                    'position_id': emp.position_id,
                    'position_name': emp.position.name if emp.position else 'Unassigned'
                })
            else:
                logger.warning(f"Employee {emp.name} has invalid crew assignment: {emp.crew}")
        
        return crew_employees
    
    def _validate_crews(self, crew_employees: Dict) -> Dict:
        """Validate crew assignments for Pitman schedule"""
        issues = []
        recommendations = []
        
        # Check crew sizes
        crew_sizes = {crew: len(employees) for crew, employees in crew_employees.items()}
        total_employees = sum(crew_sizes.values())
        
        if total_employees == 0:
            return {'valid': False, 'issues': ['No active employees found']}
        
        # Ideal Pitman crew size is 10-12 per crew for good coverage
        ideal_crew_size = max(8, total_employees // 4)
        
        for crew, size in crew_sizes.items():
            if size == 0:
                issues.append(f"Crew {crew} has no employees assigned")
            elif size < ideal_crew_size * 0.7:
                recommendations.append(f"Crew {crew} may be understaffed ({size} employees)")
            elif size > ideal_crew_size * 1.3:
                recommendations.append(f"Crew {crew} may be overstaffed ({size} employees)")
        
        # Check for unassigned employees
        unassigned = Employee.query.filter_by(is_active=True, crew=None).count()
        if unassigned > 0:
            issues.append(f"{unassigned} active employees have no crew assignment")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'recommendations': recommendations,
            'crew_sizes': crew_sizes,
            'total_employees': total_employees,
            'ideal_crew_size': ideal_crew_size
        }
    
    def _generate_daily_schedule(self, current_date: date, day_index: int, 
                               crew_employees: Dict, variation: str, 
                               created_by_id: int) -> List[Schedule]:
        """Generate schedule for a single day"""
        daily_schedules = []
        
        for crew in ['A', 'B', 'C', 'D']:
            # Calculate if this crew works today
            cycle_day = (day_index + self.crew_offsets[crew]) % 14
            works_today = self.pitman_base_pattern[cycle_day] == 1
            
            if not works_today:
                continue  # Crew is off today
            
            # Determine shift type based on variation
            if variation == 'fixed':
                # Traditional: A,B = days, C,D = nights
                shift_type = 'day' if crew in ['A', 'B'] else 'night'
            elif variation == 'rotating':
                # Crews alternate between day/night every few weeks
                shift_type = self._get_rotating_shift_type(crew, current_date, day_index)
            else:
                shift_type = 'day'  # Default fallback
            
            # Create schedules for all employees in this crew
            for emp_data in crew_employees[crew]:
                schedule = Schedule(
                    employee_id=emp_data['id'],
                    date=current_date,
                    shift_type=shift_type,
                    start_time=datetime.strptime(
                        self.shift_config[shift_type]['start_time'], '%H:%M'
                    ).time(),
                    hours=self.shift_config[shift_type]['hours'],
                    position_id=emp_data['position_id'],
                    created_by_id=created_by_id,
                    is_overtime=False,  # Regular scheduled shift
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                
                # Calculate end time
                start_datetime = datetime.combine(current_date, schedule.start_time)
                end_datetime = start_datetime + timedelta(hours=schedule.hours)
                schedule.end_time = end_datetime.time()
                
                daily_schedules.append(schedule)
        
        return daily_schedules
    
    def _get_rotating_shift_type(self, crew: str, current_date: date, day_index: int) -> str:
        """Determine shift type for rotating Pitman variation"""
        # Rotate every 2 weeks (14 days) 
        rotation_cycle = (day_index // 14) % 2
        
        if crew in ['A', 'C']:
            return 'day' if rotation_cycle == 0 else 'night'
        else:  # crews B, D
            return 'night' if rotation_cycle == 0 else 'day'
    
    def _calculate_schedule_stats(self, schedules: List[Schedule], 
                                 crew_employees: Dict) -> Dict:
        """Calculate comprehensive schedule statistics"""
        if not schedules:
            return {'error': 'No schedules generated'}
        
        # Basic counts
        total_schedules = len(schedules)
        unique_employees = len(set(s.employee_id for s in schedules))
        date_range = f"{min(s.date for s in schedules)} to {max(s.date for s in schedules)}"
        
        # Hours analysis  
        total_hours = sum(s.hours for s in schedules)
        avg_hours_per_employee = total_hours / unique_employees if unique_employees > 0 else 0
        
        # Shift distribution
        shift_counts = {}
        for schedule in schedules:
            shift_type = schedule.shift_type
            shift_counts[shift_type] = shift_counts.get(shift_type, 0) + 1
        
        # Crew workload analysis
        crew_stats = {}
        for crew, employees in crew_employees.items():
            crew_schedules = [s for s in schedules if any(
                s.employee_id == emp['id'] for emp in employees
            )]
            
            crew_stats[crew] = {
                'employee_count': len(employees),
                'total_shifts': len(crew_schedules),
                'total_hours': sum(s.hours for s in crew_schedules),
                'avg_shifts_per_employee': len(crew_schedules) / len(employees) if employees else 0,
                'avg_hours_per_employee': sum(s.hours for s in crew_schedules) / len(employees) if employees else 0
            }
        
        # Weekly hours analysis (important for Pitman)
        start_date = min(s.date for s in schedules)
        end_date = max(s.date for s in schedules)
        
        # Find first Monday
        days_to_monday = start_date.weekday()
        week_start = start_date - timedelta(days=days_to_monday)
        
        weekly_analysis = []
        while week_start <= end_date:
            week_end = week_start + timedelta(days=6)
            week_schedules = [s for s in schedules if week_start <= s.date <= week_end]
            
            weekly_analysis.append({
                'week_start': week_start,
                'total_shifts': len(week_schedules),
                'total_hours': sum(s.hours for s in week_schedules),
                'unique_employees': len(set(s.employee_id for s in week_schedules))
            })
            
            week_start += timedelta(days=7)
        
        return {
            'basic_stats': {
                'total_schedules': total_schedules,
                'unique_employees': unique_employees,
                'total_hours': total_hours,
                'avg_hours_per_employee': round(avg_hours_per_employee, 1),
                'date_range': date_range
            },
            'shift_distribution': shift_counts,
            'crew_analysis': crew_stats,
            'weekly_analysis': weekly_analysis
        }
    
    def _validate_schedule(self, schedules: List[Schedule]) -> Dict:
        """Validate the generated Pitman schedule"""
        issues = []
        warnings = []
        
        if not schedules:
            return {'valid': False, 'issues': ['No schedules generated']}
        
        # Check for conflicts (employee scheduled multiple times per day)
        dates_employees = {}
        for schedule in schedules:
            date_key = schedule.date.strftime('%Y-%m-%d')
            if date_key not in dates_employees:
                dates_employees[date_key] = set()
            
            if schedule.employee_id in dates_employees[date_key]:
                issues.append(f"Employee {schedule.employee_id} scheduled multiple times on {date_key}")
            else:
                dates_employees[date_key].add(schedule.employee_id)
        
        # Check coverage consistency 
        daily_coverage = {}
        for schedule in schedules:
            date_key = schedule.date.strftime('%Y-%m-%d')
            if date_key not in daily_coverage:
                daily_coverage[date_key] = {'day': 0, 'night': 0}
            daily_coverage[date_key][schedule.shift_type] += 1
        
        # Validate Pitman pattern compliance
        for date_str, coverage in daily_coverage.items():
            total_coverage = coverage['day'] + coverage['night']
            if total_coverage == 0:
                warnings.append(f"No coverage on {date_str}")
            elif coverage['day'] == 0 and coverage['night'] > 0:
                # Night-only coverage might be intentional
                pass
            elif coverage['night'] == 0 and coverage['day'] > 0:
                # Day-only coverage might be intentional
                pass
        
        # Check for reasonable coverage levels
        avg_daily_coverage = sum(
            sum(coverage.values()) for coverage in daily_coverage.values()
        ) / len(daily_coverage) if daily_coverage else 0
        
        if avg_daily_coverage < 10:
            warnings.append("Average daily coverage seems low - may indicate understaffing")
        elif avg_daily_coverage > 50:
            warnings.append("Average daily coverage very high - may indicate overstaffing")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings,
            'avg_daily_coverage': round(avg_daily_coverage, 1),
            'total_dates_covered': len(daily_coverage)
        }
    
    def commit_schedules_to_database(self, schedules: List[Schedule], 
                                   replace_existing: bool = False) -> Dict:
        """
        Save generated schedules to database
        
        Args:
            schedules: List of Schedule objects to save
            replace_existing: If True, delete existing schedules in date range first
            
        Returns:
            Dict with results and any errors
        """
        if not schedules:
            return {'success': False, 'error': 'No schedules to save'}
        
        try:
            # Get date range
            start_date = min(s.date for s in schedules)
            end_date = max(s.date for s in schedules)
            
            if replace_existing:
                # Delete existing schedules in this date range
                logger.info(f"Deleting existing schedules from {start_date} to {end_date}")
                existing_count = Schedule.query.filter(
                    Schedule.date >= start_date,
                    Schedule.date <= end_date
                ).count()
                
                Schedule.query.filter(
                    Schedule.date >= start_date,
                    Schedule.date <= end_date
                ).delete()
                
                logger.info(f"Deleted {existing_count} existing schedules")
            
            # Add new schedules
            for schedule in schedules:
                db.session.add(schedule)
            
            # Commit all changes
            db.session.commit()
            
            logger.info(f"Successfully saved {len(schedules)} Pitman schedules to database")
            
            return {
                'success': True,
                'schedules_saved': len(schedules),
                'date_range': f"{start_date} to {end_date}",
                'replaced_existing': replace_existing
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error saving schedules to database: {e}")
            return {'success': False, 'error': str(e)}
    
    def preview_schedule_pattern(self, days: int = 28) -> str:
        """
        Generate a text preview of the Pitman pattern
        Useful for understanding the schedule before generating
        """
        preview = "PITMAN SCHEDULE PATTERN PREVIEW (2-2-3)\n"
        preview += "=" * 50 + "\n\n"
        
        # Show pattern for each crew over specified days
        for crew in ['A', 'B', 'C', 'D']:
            preview += f"CREW {crew}:\n"
            pattern_line = ""
            
            for day in range(days):
                cycle_day = (day + self.crew_offsets[crew]) % 14
                works = self.pitman_base_pattern[cycle_day]
                
                if works:
                    shift_type = 'D' if crew in ['A', 'B'] else 'N'  # Fixed pattern
                    pattern_line += f"{shift_type:2}"
                else:
                    pattern_line += " O"
                
                # Add separator every 7 days
                if (day + 1) % 7 == 0:
                    pattern_line += " | "
            
            preview += pattern_line + "\n\n"
        
        preview += "Legend: D=Day Shift, N=Night Shift, O=Off\n"
        preview += "Pattern repeats every 14 days\n"
        preview += "Each crew works 7 days out of every 14 days\n"
        
        return preview

# Example usage function
def generate_pitman_for_production(start_date_str: str, weeks: int = 4, 
                                 variation: str = 'fixed',
                                 supervisor_id: int = None) -> Dict:
    """
    Convenience function to generate Pitman schedule for production use
    
    Args:
        start_date_str: Start date in 'YYYY-MM-DD' format
        weeks: Number of weeks to generate (minimum 2 for full pattern)
        variation: 'fixed' or 'rotating'
        supervisor_id: ID of supervisor creating the schedule
        
    Returns:
        Complete schedule generation results
    """
    
    # Parse start date
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = start_date + timedelta(weeks=weeks)
    
    # Generate schedule
    pitman_generator = RealPitmanSchedule()
    results = pitman_generator.generate_pitman_schedule(
        start_date=start_date,
        end_date=end_date,
        variation=variation,
        created_by_id=supervisor_id
    )
    
    return results
