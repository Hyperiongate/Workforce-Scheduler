from datetime import datetime, timedelta, date
from sqlalchemy import func, and_, or_, case
from collections import defaultdict
import json

class OvertimeAssignmentEngine:
    """
    Manages fair and efficient overtime distribution following priority protocols.
    Implements voluntary and mandatory assignment logic with fatigue management.
    """
    
    def __init__(self, db, models):
        self.db = db
        self.Employee = models['Employee']
        self.Schedule = models['Schedule']
        self.Position = models['Position']
        self.OvertimeHistory = models['OvertimeHistory']
        self.OvertimeOpportunity = models.get('OvertimeOpportunity')
        self.EmployeeSkill = models.get('EmployeeSkill')
        
    def get_eligible_employees(self, position_id, date_needed, shift_type='day', 
                              crews_to_consider=None, urgency='standard'):
        """
        Get list of eligible employees for overtime, sorted by priority.
        Implements the proximity-based approach from the framework.
        """
        position = self.Position.query.get(position_id)
        if not position:
            return []
        
        # Determine which crews are working on the date
        working_crews = self._get_working_crews(date_needed, shift_type)
        off_duty_crews = self._get_off_duty_crews(date_needed, shift_type)
        
        # Get all employees with required skills
        eligible_employees = []
        
        # Query base employee pool
        base_query = self.Employee.query.filter(
            self.Employee.is_active == True,
            self.Employee.is_supervisor == False
        )
        
        # Filter by position or skills
        if position.skills_required:
            # Need to check skills
            skilled_employees = base_query.join(
                self.EmployeeSkill
            ).filter(
                self.EmployeeSkill.skill_name.in_(position.skills_required.split(','))
            ).distinct().all()
        else:
            # Position-based only
            skilled_employees = base_query.filter(
                self.Employee.position_id == position_id
            ).all()
        
        # Evaluate each employee
        for employee in skilled_employees:
            eligibility = self._evaluate_employee_eligibility(
                employee, date_needed, shift_type, working_crews, off_duty_crews
            )
            
            if eligibility['eligible'] or eligibility['eligible_with_warning']:
                eligible_employees.append({
                    'employee': employee,
                    'priority_score': eligibility['priority_score'],
                    'overtime_hours_13w': eligibility['overtime_hours_13w'],
                    'last_overtime_date': eligibility['last_overtime_date'],
                    'consecutive_days': eligibility['consecutive_days'],
                    'fatigue_score': eligibility['fatigue_score'],
                    'availability': eligibility,
                    'crew': employee.crew,
                    'is_off_duty': employee.crew in off_duty_crews
                })
        
        # Sort by priority
        eligible_employees.sort(key=lambda x: (
            x['priority_score'],  # Lower is better
            x['overtime_hours_13w'],  # Less OT is better
            x['fatigue_score']  # Lower fatigue is better
        ))
        
        return eligible_employees
    
    def _evaluate_employee_eligibility(self, employee, date_needed, shift_type,
                                     working_crews, off_duty_crews):
        """
        Evaluate individual employee eligibility and calculate priority score.
        """
        result = {
            'eligible': True,
            'eligible_with_warning': False,
            'reasons': [],
            'warnings': [],
            'priority_score': 0,
            'overtime_hours_13w': 0,
            'last_overtime_date': None,
            'consecutive_days': 0,
            'fatigue_score': 0
        }
        
        # Check 13-week overtime history
        thirteen_weeks_ago = date_needed - timedelta(weeks=13)
        overtime_sum = self.db.session.query(
            func.sum(self.OvertimeHistory.overtime_hours)
        ).filter(
            self.OvertimeHistory.employee_id == employee.id,
            self.OvertimeHistory.week_start_date >= thirteen_weeks_ago
        ).scalar() or 0
        
        result['overtime_hours_13w'] = float(overtime_sum)
        
        # Check consecutive days worked
        consecutive = self._calculate_consecutive_days(employee.id, date_needed)
        result['consecutive_days'] = consecutive
        
        # Maximum consecutive days rules
        max_consecutive = 14  # Company policy
        if shift_type == 'night':
            max_consecutive = 7  # More restrictive for nights
        
        if consecutive >= max_consecutive:
            result['eligible'] = False
            result['reasons'].append(f'Would exceed {max_consecutive} consecutive days')
        elif consecutive >= max_consecutive - 2:
            result['eligible_with_warning'] = True
            result['warnings'].append(f'Approaching {max_consecutive} day limit')
        
        # Fatigue scoring (higher = more fatigued)
        result['fatigue_score'] = self._calculate_fatigue_score(
            employee.id, date_needed, shift_type, consecutive
        )
        
        if result['fatigue_score'] > 8:
            result['eligible_with_warning'] = True
            result['warnings'].append('High fatigue risk')
        
        # Priority scoring based on crew assignment
        if employee.crew in off_duty_crews:
            # Check if they're resting before next shift
            next_scheduled = self._get_next_scheduled_shift(employee.id, date_needed)
            if next_scheduled and (next_scheduled - date_needed).days <= 2:
                result['priority_score'] = 1  # Highest priority - natural fit
            else:
                result['priority_score'] = 2  # Good option - off duty
        else:
            result['priority_score'] = 3  # Would create double - lowest priority
            result['eligible_with_warning'] = True
            result['warnings'].append('Would create double shift')
        
        # Check for recent overtime
        recent_ot = self.db.session.query(self.Schedule).filter(
            self.Schedule.employee_id == employee.id,
            self.Schedule.is_overtime == True,
            self.Schedule.date >= date_needed - timedelta(days=7),
            self.Schedule.date < date_needed
        ).count()
        
        if recent_ot > 2:
            result['priority_score'] += 1  # Lower priority if lots of recent OT
        
        # Add night shift adjustment
        if shift_type == 'night':
            # Prefer employees already on night schedule
            recent_nights = self._count_recent_night_shifts(employee.id, date_needed)
            if recent_nights < 2:
                result['priority_score'] += 2  # Discourage day workers from night OT
                result['warnings'].append('Not on night schedule')
        
        result['available'] = result['eligible'] or result['eligible_with_warning']
        
        return result
    
    def _calculate_consecutive_days(self, employee_id, check_date):
        """Calculate consecutive days that would be worked including the OT day."""
        consecutive = 0
        current_date = check_date
        
        # Check backwards
        while True:
            current_date -= timedelta(days=1)
            scheduled = self.Schedule.query.filter(
                self.Schedule.employee_id == employee_id,
                self.Schedule.date == current_date
            ).first()
            
            if scheduled:
                consecutive += 1
            else:
                break
        
        # Add the OT day itself
        consecutive += 1
        
        # Check forwards from OT date
        current_date = check_date
        while True:
            current_date += timedelta(days=1)
            scheduled = self.Schedule.query.filter(
                self.Schedule.employee_id == employee_id,
                self.Schedule.date == current_date
            ).first()
            
            if scheduled:
                consecutive += 1
            else:
                break
        
        return consecutive
    
    def _calculate_fatigue_score(self, employee_id, date_needed, shift_type, consecutive_days):
        """
        Calculate fatigue risk score (0-10 scale).
        Considers consecutive days, shift changes, and recent overtime.
        """
        score = 0
        
        # Base score from consecutive days
        score += min(consecutive_days * 0.7, 5)
        
        # Check for shift changes in past week
        week_ago = date_needed - timedelta(days=7)
        shifts = self.Schedule.query.filter(
            self.Schedule.employee_id == employee_id,
            self.Schedule.date >= week_ago,
            self.Schedule.date < date_needed
        ).all()
        
        shift_types = set(s.shift_type for s in shifts)
        if len(shift_types) > 1:
            score += 2  # Penalty for rotating shifts
        
        # Night shift fatigue multiplier
        if shift_type == 'night':
            score *= 1.3
        
        # Recent overtime penalty
        recent_ot_hours = sum(s.hours for s in shifts if s.is_overtime)
        score += min(recent_ot_hours / 24, 3)  # Up to 3 points for recent OT
        
        return min(score, 10)  # Cap at 10
    
    def _get_working_crews(self, check_date, shift_type):
        """Get crews scheduled to work on given date/shift."""
        # This should match your rotation pattern
        # Simplified example - replace with actual logic
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
    
    def _get_off_duty_crews(self, check_date, shift_type):
        """Get crews not working on given date/shift."""
        all_crews = ['A', 'B', 'C', 'D']
        working = self._get_working_crews(check_date, shift_type)
        return [c for c in all_crews if c not in working]
    
    def _get_next_scheduled_shift(self, employee_id, after_date):
        """Find next scheduled shift for employee after given date."""
        next_shift = self.Schedule.query.filter(
            self.Schedule.employee_id == employee_id,
            self.Schedule.date > after_date
        ).order_by(self.Schedule.date).first()
        
        return next_shift.date if next_shift else None
    
    def _count_recent_night_shifts(self, employee_id, before_date):
        """Count night shifts in past week."""
        week_ago = before_date - timedelta(days=7)
        return self.Schedule.query.filter(
            self.Schedule.employee_id == employee_id,
            self.Schedule.date >= week_ago,
            self.Schedule.date < before_date,
            self.Schedule.shift_type == 'night'
        ).count()
    
    def create_overtime_opportunity(self, position_id, date_needed, shift_type,
                                  posted_by_id, urgency='standard', notes=None):
        """
        Create and post an overtime opportunity.
        Returns the opportunity and list of notified employees.
        """
        # Set response deadline based on urgency
        if urgency == 'immediate':
            deadline = datetime.now() + timedelta(hours=2)
        elif urgency == 'urgent':
            deadline = datetime.now() + timedelta(hours=8)
        else:
            deadline = datetime.now() + timedelta(hours=48)
        
        # Create opportunity record
        opportunity = self.OvertimeOpportunity(
            position_id=position_id,
            date=date_needed,
            shift_type=shift_type,
            posted_by_id=posted_by_id,
            posted_at=datetime.now(),
            response_deadline=deadline,
            status='open',
            urgency=urgency,
            notes=notes
        )
        
        self.db.session.add(opportunity)
        self.db.session.flush()
        
        # Get eligible employees
        eligible = self.get_eligible_employees(
            position_id, date_needed, shift_type, urgency=urgency
        )
        
        # Determine how many to notify based on urgency
        if urgency == 'immediate':
            notify_count = min(len(eligible), 20)  # Notify more for urgent
        else:
            notify_count = min(len(eligible), 10)  # Standard notification
        
        notified_employees = []
        for emp_data in eligible[:notify_count]:
            notified_employees.append({
                'employee_id': emp_data['employee'].id,
                'name': emp_data['employee'].name,
                'priority_score': emp_data['priority_score'],
                'warnings': emp_data['availability'].get('warnings', [])
            })
        
        opportunity.notified_employees = json.dumps(notified_employees)
        self.db.session.commit()
        
        return opportunity, notified_employees
    
    def assign_mandatory_overtime(self, position_id, date_needed, shift_type, assigned_by_id):
        """
        Assign mandatory overtime using reverse seniority.
        Returns the assigned employee and schedule entry.
        """
        # Get eligible employees
        eligible = self.get_eligible_employees(position_id, date_needed, shift_type)
        
        # Filter to only truly available (no warnings)
        available = [e for e in eligible if e['availability']['eligible'] 
                    and not e['availability']['eligible_with_warning']]
        
        if not available:
            # If no one without warnings, use those with warnings
            available = [e for e in eligible if e['availability']['available']]
        
        if not available:
            raise ValueError("No available employees for mandatory assignment")
        
        # Sort by reverse seniority (hire date)
        available.sort(key=lambda x: x['employee'].hire_date or date.today(), reverse=True)
        
        # Assign to newest available employee
        selected = available[0]['employee']
        
        # Create schedule entry
        schedule = self.Schedule(
            employee_id=selected.id,
            date=date_needed,
            shift_type=shift_type,
            start_time='06:00' if shift_type == 'day' else '18:00',
            end_time='18:00' if shift_type == 'day' else '06:00',
            hours=12.0,
            is_overtime=True,
            overtime_reason='Mandatory assignment - reverse seniority'
        )
        
        self.db.session.add(schedule)
        
        # Update overtime history
        self._update_overtime_history(selected.id, date_needed, 12.0)
        
        # Log the assignment
        assignment_log = {
            'assigned_to': selected.id,
            'assigned_by': assigned_by_id,
            'position_id': position_id,
            'date': date_needed.isoformat(),
            'shift_type': shift_type,
            'reason': 'Mandatory - no volunteers',
            'timestamp': datetime.now().isoformat()
        }
        
        self.db.session.commit()
        
        return selected, schedule, assignment_log
    
    def _update_overtime_history(self, employee_id, work_date, hours):
        """Update the 13-week overtime history tracking."""
        # Find the week this date belongs to (assuming week starts Monday)
        days_since_monday = work_date.weekday()
        week_start = work_date - timedelta(days=days_since_monday)
        
        # Find or create history record
        history = self.OvertimeHistory.query.filter_by(
            employee_id=employee_id,
            week_start_date=week_start
        ).first()
        
        if history:
            history.overtime_hours += hours
        else:
            history = self.OvertimeHistory(
                employee_id=employee_id,
                week_start_date=week_start,
                overtime_hours=hours
            )
            self.db.session.add(history)
    
    def get_overtime_distribution_report(self, start_date=None, end_date=None):
        """
        Generate overtime distribution analysis for fairness monitoring.
        """
        if not start_date:
            start_date = date.today() - timedelta(weeks=13)
        if not end_date:
            end_date = date.today()
        
        # Get all employees with overtime in period
        overtime_data = self.db.session.query(
            self.Employee.id,
            self.Employee.name,
            self.Employee.crew,
            self.Employee.position_id,
            func.sum(self.OvertimeHistory.overtime_hours).label('total_hours'),
            func.count(self.OvertimeHistory.id).label('weeks_with_ot')
        ).join(
            self.OvertimeHistory
        ).filter(
            self.OvertimeHistory.week_start_date >= start_date,
            self.OvertimeHistory.week_start_date <= end_date
        ).group_by(
            self.Employee.id,
            self.Employee.name,
            self.Employee.crew,
            self.Employee.position_id
        ).all()
        
        # Calculate statistics
        total_ot_hours = sum(d.total_hours for d in overtime_data)
        avg_ot_hours = total_ot_hours / len(overtime_data) if overtime_data else 0
        
        # Identify imbalances
        distribution = []
        for emp in overtime_data:
            variance = emp.total_hours - avg_ot_hours
            distribution.append({
                'employee_id': emp.id,
                'name': emp.name,
                'crew': emp.crew,
                'total_hours': emp.total_hours,
                'weeks_with_ot': emp.weeks_with_ot,
                'variance_from_avg': variance,
                'percentage_of_total': (emp.total_hours / total_ot_hours * 100) if total_ot_hours > 0 else 0
            })
        
        # Sort by total hours descending
        distribution.sort(key=lambda x: x['total_hours'], reverse=True)
        
        return {
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'summary': {
                'total_overtime_hours': total_ot_hours,
                'average_hours_per_employee': avg_ot_hours,
                'employees_with_overtime': len(overtime_data)
            },
            'distribution': distribution,
            'alerts': self._identify_distribution_issues(distribution)
        }
    
    def _identify_distribution_issues(self, distribution):
        """Identify potential fairness issues in overtime distribution."""
        alerts = []
        
        if not distribution:
            return alerts
        
        # Check for employees with excessive overtime
        max_hours = max(d['total_hours'] for d in distribution)
        avg_hours = sum(d['total_hours'] for d in distribution) / len(distribution)
        
        for emp in distribution:
            if emp['total_hours'] > avg_hours * 2:
                alerts.append({
                    'type': 'excessive_overtime',
                    'employee': emp['name'],
                    'hours': emp['total_hours'],
                    'message': f"{emp['name']} has {emp['total_hours']:.1f} hours OT (2x average)"
                })
        
        # Check for crew imbalances
        crew_totals = defaultdict(float)
        crew_counts = defaultdict(int)
        
        for emp in distribution:
            crew_totals[emp['crew']] += emp['total_hours']
            crew_counts[emp['crew']] += 1
        
        for crew, total in crew_totals.items():
            crew_avg = total / crew_counts[crew]
            if abs(crew_avg - avg_hours) > avg_hours * 0.3:
                alerts.append({
                    'type': 'crew_imbalance',
                    'crew': crew,
                    'average': crew_avg,
                    'message': f"Crew {crew} averaging {crew_avg:.1f} hours vs overall {avg_hours:.1f}"
                })
        
        return alerts
