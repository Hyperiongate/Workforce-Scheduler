from datetime import datetime, timedelta, date
from sqlalchemy import func, and_, or_
from collections import defaultdict
import json

class CoverageGapDetectionEngine:
    """
    Detects and analyzes coverage gaps in real-time and for future shifts.
    Integrates with the supervisor dashboard for immediate visibility.
    """
    
    def __init__(self, db, models):
        self.db = db
        self.Employee = models['Employee']
        self.Schedule = models['Schedule']
        self.Position = models['Position']
        self.PositionCoverage = models['PositionCoverage']
        self.VacationCalendar = models['VacationCalendar']
        self.CoverageGap = models.get('CoverageGap')
        
    def detect_current_gaps(self, crews_on_duty=['A', 'B'], shift_type='day'):
        """
        Detect coverage gaps for the current shift.
        Returns detailed gap information by position.
        """
        today = date.today()
        gaps = []
        
        # Get all positions that need coverage
        positions = self.Position.query.filter(
            self.Position.requires_coverage == True
        ).all()
        
        for position in positions:
            # Get coverage requirements for this position
            coverage_req = self.PositionCoverage.query.filter_by(
                position_id=position.id,
                shift_type=shift_type
            ).first()
            
            if not coverage_req:
                continue
                
            required_count = coverage_req.min_required
            
            # Count scheduled employees for this position
            scheduled = self.db.session.query(func.count(self.Schedule.id)).join(
                self.Employee
            ).filter(
                self.Schedule.date == today,
                self.Schedule.shift_type == shift_type,
                self.Employee.position_id == position.id,
                self.Employee.crew.in_(crews_on_duty)
            ).scalar() or 0
            
            # Count absences (vacation, sick, etc.)
            absences = self.db.session.query(func.count(self.VacationCalendar.id)).join(
                self.Employee
            ).filter(
                self.VacationCalendar.date == today,
                self.Employee.position_id == position.id,
                self.Employee.crew.in_(crews_on_duty)
            ).scalar() or 0
            
            actual_coverage = scheduled - absences
            gap_count = required_count - actual_coverage
            
            if gap_count > 0:
                gaps.append({
                    'position_id': position.id,
                    'position_name': position.name,
                    'shift_type': shift_type,
                    'date': today,
                    'required': required_count,
                    'scheduled': scheduled,
                    'absences': absences,
                    'actual': actual_coverage,
                    'gap': gap_count,
                    'critical': gap_count >= 2,  # Critical if 2+ short
                    'skills_required': position.skills_required,
                    'urgency': 'immediate'
                })
        
        return gaps
    
    def detect_future_gaps(self, days_ahead=14):
        """
        Detect coverage gaps for future shifts.
        Analyzes approved time off and known scheduling gaps.
        """
        future_gaps = []
        start_date = date.today() + timedelta(days=1)
        end_date = date.today() + timedelta(days=days_ahead)
        
        # Iterate through each future date
        current_date = start_date
        while current_date <= end_date:
            for shift_type in ['day', 'night']:
                # Determine which crews work this shift
                crews_on_duty = self._get_crews_on_duty(current_date, shift_type)
                
                positions = self.Position.query.filter(
                    self.Position.requires_coverage == True
                ).all()
                
                for position in positions:
                    coverage_req = self.PositionCoverage.query.filter_by(
                        position_id=position.id,
                        shift_type=shift_type
                    ).first()
                    
                    if not coverage_req:
                        continue
                    
                    # Get total employees in position for on-duty crews
                    total_employees = self.Employee.query.filter(
                        self.Employee.position_id == position.id,
                        self.Employee.crew.in_(crews_on_duty),
                        self.Employee.is_active == True
                    ).count()
                    
                    # Count approved time off
                    time_off_count = self.db.session.query(
                        func.count(self.VacationCalendar.id)
                    ).join(
                        self.Employee
                    ).filter(
                        self.VacationCalendar.date == current_date,
                        self.VacationCalendar.status == 'approved',
                        self.Employee.position_id == position.id,
                        self.Employee.crew.in_(crews_on_duty)
                    ).scalar() or 0
                    
                    projected_coverage = total_employees - time_off_count
                    gap_count = coverage_req.min_required - projected_coverage
                    
                    if gap_count > 0:
                        days_until = (current_date - date.today()).days
                        urgency = self._calculate_urgency(days_until)
                        
                        future_gaps.append({
                            'position_id': position.id,
                            'position_name': position.name,
                            'shift_type': shift_type,
                            'date': current_date,
                            'crews_affected': crews_on_duty,
                            'required': coverage_req.min_required,
                            'available': total_employees,
                            'time_off': time_off_count,
                            'projected': projected_coverage,
                            'gap': gap_count,
                            'critical': gap_count >= 2,
                            'days_until': days_until,
                            'urgency': urgency,
                            'skills_required': position.skills_required
                        })
            
            current_date += timedelta(days=1)
        
        return future_gaps
    
    def _get_crews_on_duty(self, check_date, shift_type):
        """
        Determine which crews are on duty for a given date and shift.
        This should match your rotation pattern logic.
        """
        # This is a simplified example - replace with your actual rotation logic
        # For now, assuming a simple 2-on-2-off pattern
        days_from_start = (check_date - date(2024, 1, 1)).days
        cycle_day = days_from_start % 4
        
        if shift_type == 'day':
            if cycle_day in [0, 1]:
                return ['A', 'B']
            else:
                return ['C', 'D']
        else:  # night
            if cycle_day in [0, 1]:
                return ['C', 'D']
            else:
                return ['A', 'B']
    
    def _calculate_urgency(self, days_until):
        """Calculate urgency level based on time until gap occurs."""
        if days_until == 0:
            return 'immediate'
        elif days_until <= 1:
            return 'urgent'
        elif days_until <= 3:
            return 'high'
        elif days_until <= 7:
            return 'medium'
        else:
            return 'low'
    
    def get_gap_summary(self):
        """
        Get a summary of all coverage gaps for dashboard display.
        """
        current_gaps = self.detect_current_gaps()
        future_gaps = self.detect_future_gaps()
        
        # Group future gaps by urgency
        urgency_groups = defaultdict(list)
        for gap in future_gaps:
            urgency_groups[gap['urgency']].append(gap)
        
        summary = {
            'current_shift': {
                'total_gaps': sum(g['gap'] for g in current_gaps),
                'critical_positions': [g for g in current_gaps if g['critical']],
                'gaps_by_position': current_gaps
            },
            'next_24_hours': urgency_groups.get('urgent', []),
            'next_48_hours': urgency_groups.get('high', []),
            'next_7_days': urgency_groups.get('medium', []),
            'next_14_days': urgency_groups.get('low', []),
            'statistics': {
                'total_current_gaps': len(current_gaps),
                'total_future_gaps': len(future_gaps),
                'critical_gaps': len([g for g in current_gaps + future_gaps if g['critical']]),
                'positions_affected': len(set(g['position_id'] for g in current_gaps + future_gaps))
            }
        }
        
        return summary
    
    def check_time_off_impact(self, employee_id, start_date, end_date):
        """
        Check the coverage impact of a potential time off request.
        Used when supervisors review time off requests.
        """
        employee = self.Employee.query.get(employee_id)
        if not employee:
            return None
        
        impacts = []
        current_date = start_date
        
        while current_date <= end_date:
            for shift_type in ['day', 'night']:
                crews_on_duty = self._get_crews_on_duty(current_date, shift_type)
                
                if employee.crew in crews_on_duty:
                    # Check current coverage for employee's position
                    coverage_req = self.PositionCoverage.query.filter_by(
                        position_id=employee.position_id,
                        shift_type=shift_type
                    ).first()
                    
                    if coverage_req:
                        # Count available employees (excluding this request)
                        available = self.Employee.query.filter(
                            self.Employee.position_id == employee.position_id,
                            self.Employee.crew.in_(crews_on_duty),
                            self.Employee.is_active == True,
                            self.Employee.id != employee_id
                        ).count()
                        
                        # Count existing approved time off
                        existing_off = self.db.session.query(
                            func.count(self.VacationCalendar.id)
                        ).join(
                            self.Employee
                        ).filter(
                            self.VacationCalendar.date == current_date,
                            self.VacationCalendar.status == 'approved',
                            self.Employee.position_id == employee.position_id,
                            self.Employee.crew.in_(crews_on_duty),
                            self.Employee.id != employee_id
                        ).scalar() or 0
                        
                        projected_coverage = available - existing_off
                        would_create_gap = projected_coverage < coverage_req.min_required
                        
                        if would_create_gap or projected_coverage <= coverage_req.min_required:
                            impacts.append({
                                'date': current_date,
                                'shift_type': shift_type,
                                'position': employee.position.name,
                                'required': coverage_req.min_required,
                                'would_have': projected_coverage,
                                'creates_gap': would_create_gap,
                                'severity': 'high' if would_create_gap else 'medium'
                            })
            
            current_date += timedelta(days=1)
        
        return {
            'employee': employee.name,
            'position': employee.position.name,
            'crew': employee.crew,
            'impacts': impacts,
            'total_days_affected': len(impacts),
            'creates_gaps': any(i['creates_gap'] for i in impacts)
        }
    
    def get_recommended_actions(self, gaps):
        """
        Generate recommended actions for each gap based on urgency and severity.
        """
        actions = []
        
        for gap in gaps:
            urgency = gap.get('urgency', 'medium')
            
            if urgency == 'immediate':
                actions.append({
                    'gap': gap,
                    'action_type': 'immediate_fill',
                    'steps': [
                        'Check standby/on-call personnel',
                        'Reassign from non-critical positions',
                        'Call in off-duty volunteers',
                        'Consider mandatory assignment'
                    ],
                    'time_limit': 'Within 1 hour'
                })
            elif urgency == 'urgent':
                actions.append({
                    'gap': gap,
                    'action_type': 'urgent_posting',
                    'steps': [
                        'Post overtime opportunity immediately',
                        'Set 4-8 hour response window',
                        'Notify eligible employees via text/call',
                        'Prepare mandatory assignment list'
                    ],
                    'time_limit': 'Within 4 hours'
                })
            elif urgency == 'high':
                actions.append({
                    'gap': gap,
                    'action_type': 'standard_posting',
                    'steps': [
                        'Post overtime opportunity',
                        'Set 24-hour response window',
                        'Check casual worker availability',
                        'Consider shift swaps'
                    ],
                    'time_limit': 'Within 24 hours'
                })
            else:
                actions.append({
                    'gap': gap,
                    'action_type': 'planned_coverage',
                    'steps': [
                        'Post to shift marketplace',
                        'Allow 48-72 hour response time',
                        'Coordinate with other supervisors',
                        'Plan cross-training if needed'
                    ],
                    'time_limit': f'Within {gap.get("days_until", 7)} days'
                })
        
        return actions
