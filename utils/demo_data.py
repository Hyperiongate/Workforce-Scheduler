# utils/demo_data.py
"""
Demo data service for supervisor dashboard
Provides realistic sample data for testing and development
Later replaced with real data sources
"""

from datetime import date, datetime, timedelta
import random
from typing import Dict, List, Any

class DemoDataService:
    """Centralized demo data provider for supervisor dashboard"""
    
    def __init__(self):
        # Initialize with some base data
        self.crews = ['A', 'B', 'C', 'D']
        self.positions = [
            'Operator', 'Senior Operator', 'Lead Operator',
            'Maintenance Technician', 'Electrician', 'Mechanic',
            'Control Room Operator', 'Shift Supervisor', 'Process Engineer'
        ]
        
        self.employee_names = [
            'John Smith', 'Mary Johnson', 'David Williams', 'Sarah Brown',
            'Mike Davis', 'Lisa Wilson', 'Tom Anderson', 'Jennifer Taylor',
            'Chris Martin', 'Ashley Garcia', 'Kevin Rodriguez', 'Amanda Lewis',
            'Brian Walker', 'Nicole Hall', 'Daniel Allen', 'Michelle Young'
        ]
        
        self.supervisors = [
            {'id': 1, 'name': 'Bob Johnson', 'crew': 'A'},
            {'id': 2, 'name': 'Sarah Williams', 'crew': 'B'},
            {'id': 3, 'name': 'Mike Davis', 'crew': 'C'},
            {'id': 4, 'name': 'Lisa Chen', 'crew': 'D'}
        ]

    def get_communication_counts(self) -> Dict[str, int]:
        """Get realistic communication counts"""
        return {
            'supervisor_to_supervisor': random.randint(0, 5),
            'employee_to_supervisor': random.randint(2, 12),
            'plantwide_recent': random.randint(0, 3)
        }

    def get_supervisor_messages(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get sample supervisor-to-supervisor messages"""
        message_subjects = [
            'Crew A Schedule Change',
            'Overtime Distribution',
            'Equipment Maintenance Window',
            'Safety Meeting Notes',
            'Weekend Coverage Request',
            'Training Schedule Update',
            'Holiday Staffing Plan'
        ]
        
        messages = []
        for i in range(min(limit, random.randint(3, 8))):
            messages.append({
                'id': 100 + i,
                'from': random.choice([s['name'] for s in self.supervisors]),
                'subject': random.choice(message_subjects),
                'date': (datetime.now() - timedelta(days=random.randint(0, 7))).strftime('%Y-%m-%d'),
                'unread': random.choice([True, False, False]),  # 1/3 chance unread
                'priority': random.choice(['normal', 'normal', 'high'])
            })
        
        return sorted(messages, key=lambda x: x['date'], reverse=True)

    def get_employee_messages(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get sample employee-to-supervisor messages"""
        message_subjects = [
            'Schedule Question',
            'Overtime Availability',
            'Equipment Issue Report',
            'Time Off Request Clarification',
            'Shift Trade Request',
            'Training Completion',
            'Safety Concern'
        ]
        
        messages = []
        for i in range(min(limit, random.randint(4, 12))):
            messages.append({
                'id': 200 + i,
                'from': random.choice(self.employee_names),
                'subject': random.choice(message_subjects),
                'date': (datetime.now() - timedelta(days=random.randint(0, 5))).strftime('%Y-%m-%d'),
                'unread': random.choice([True, True, False])  # 2/3 chance unread
            })
        
        return sorted(messages, key=lambda x: x['date'], reverse=True)

    def get_predictive_staffing_data(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Generate realistic staffing shortage predictions"""
        understaffed_dates = []
        
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        current = start
        while current <= end:
            # Randomly generate some understaffing scenarios
            # Higher chance on weekends and holidays
            is_weekend = current.weekday() >= 5
            shortage_chance = 0.3 if is_weekend else 0.15
            
            if random.random() < shortage_chance:
                crew = random.choice(self.crews)
                shortage = random.randint(1, 4)
                required = random.randint(12, 16)
                available = required - shortage
                
                understaffed_dates.append({
                    'date': current.strftime('%Y-%m-%d'),
                    'crew': crew,
                    'shortage': shortage,
                    'available': available,
                    'required': required,
                    'reason': 'Vacation conflicts' if not is_weekend else 'Weekend coverage gaps'
                })
            
            current += timedelta(days=1)
        
        return {
            'success': True,
            'understaffed_dates': understaffed_dates,
            'total_issues': len(understaffed_dates)
        }

    def get_crew_status_data(self) -> Dict[str, Any]:
        """Get current crew status information"""
        crew_data = {}
        
        for crew in self.crews:
            total_employees = random.randint(18, 25)
            
            # Position distribution for this crew
            positions = {}
            remaining = total_employees
            for position in self.positions:
                if remaining <= 0:
                    positions[position] = 0
                elif position == self.positions[-1]:  # Last position gets remainder
                    positions[position] = remaining
                else:
                    count = random.randint(0, min(4, remaining))
                    positions[position] = count
                    remaining -= count
            
            # Current shift status
            scheduled = random.randint(total_employees - 3, total_employees)
            on_leave = total_employees - scheduled
            
            crew_data[crew] = {
                'total': total_employees,
                'scheduled': scheduled,
                'on_leave': on_leave,
                'positions': positions,
                'coverage_level': 'Good' if scheduled >= (total_employees * 0.85) else 'Limited'
            }
        
        return crew_data

    def get_today_schedule_data(self) -> Dict[str, Any]:
        """Get today's schedule breakdown"""
        today = date.today()
        schedule_data = {}
        
        for crew in self.crews:
            total_crew = random.randint(18, 25)
            on_leave_count = random.randint(0, 3)
            scheduled_count = total_crew - on_leave_count
            
            # Generate some employee names for display
            scheduled_employees = random.sample(self.employee_names, 
                                              min(scheduled_count, len(self.employee_names)))
            on_leave_employees = random.sample(
                [name for name in self.employee_names if name not in scheduled_employees],
                on_leave_count
            )
            
            schedule_data[crew] = {
                'total': total_crew,
                'scheduled_count': scheduled_count,
                'on_leave_count': on_leave_count,
                'scheduled_employees': scheduled_employees[:5],  # Show first 5
                'on_leave_employees': on_leave_employees,
                'overtime_scheduled': random.randint(0, 2)
            }
        
        return {
            'date': today,
            'crews': schedule_data,
            'total_scheduled': sum(data['scheduled_count'] for data in schedule_data.values()),
            'total_on_leave': sum(data['on_leave_count'] for data in schedule_data.values())
        }

    def get_coverage_gaps_data(self) -> List[Dict[str, Any]]:
        """Get coverage gap information"""
        gaps = []
        
        # Generate some realistic coverage gaps
        gap_scenarios = [
            {
                'position': 'Control Room Operator',
                'crew': 'B',
                'shift': 'Night',
                'date': date.today() + timedelta(days=2),
                'severity': 'Critical',
                'reason': 'Certification expired'
            },
            {
                'position': 'Maintenance Technician',
                'crew': 'A',
                'shift': 'Day',
                'date': date.today() + timedelta(days=5),
                'severity': 'High',
                'reason': 'Vacation conflict'
            },
            {
                'position': 'Senior Operator',
                'crew': 'C',
                'shift': 'Evening',
                'date': date.today() + timedelta(days=1),
                'severity': 'Medium',
                'reason': 'Training assignment'
            }
        ]
        
        # Randomly include some gaps
        for scenario in gap_scenarios:
            if random.random() < 0.6:  # 60% chance of each gap
                gaps.append(scenario)
        
        return gaps

    def get_overtime_distribution_data(self) -> List[Dict[str, Any]]:
        """Get overtime distribution for employees"""
        overtime_data = []
        
        for i, name in enumerate(self.employee_names[:12]):  # Show 12 employees
            # Generate realistic overtime patterns
            base_hours = random.uniform(35, 65)
            weeks_13_total = base_hours + random.uniform(-15, 25)
            
            overtime_data.append({
                'employee_id': f'EMP{1000 + i:03d}',
                'name': name,
                'crew': random.choice(self.crews),
                'position': random.choice(self.positions),
                'total_overtime_13_weeks': round(weeks_13_total, 1),
                'average_weekly': round(weeks_13_total / 13, 1),
                'last_week': round(random.uniform(0, 12), 1),
                'trend': random.choice(['increasing', 'decreasing', 'stable'])
            })
        
        # Sort by total overtime descending
        overtime_data.sort(key=lambda x: x['total_overtime_13_weeks'], reverse=True)
        
        return overtime_data

    def get_maintenance_issues_data(self) -> List[Dict[str, Any]]:
        """Get current maintenance issues"""
        issues = [
            {
                'id': 1001,
                'equipment': 'Pump Station #3',
                'priority': 'High',
                'status': 'In Progress',
                'reported_by': 'Mike Davis',
                'reported_date': '2025-08-23',
                'description': 'Unusual vibration detected'
            },
            {
                'id': 1002,
                'equipment': 'Control Panel B-4',
                'priority': 'Critical',
                'status': 'Pending',
                'reported_by': 'Sarah Williams',
                'reported_date': '2025-08-25',
                'description': 'Display showing error codes'
            },
            {
                'id': 1003,
                'equipment': 'Safety Valve #7',
                'priority': 'Medium',
                'status': 'Scheduled',
                'reported_by': 'Tom Anderson',
                'reported_date': '2025-08-22',
                'description': 'Scheduled maintenance due'
            }
        ]
        
        # Randomly include some issues
        return [issue for issue in issues if random.random() < 0.7]

    def get_dashboard_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics for dashboard cards"""
        return {
            'total_employees': random.randint(95, 105),
            'today_scheduled': random.randint(85, 95),
            'today_on_leave': random.randint(2, 8),
            'coverage_gaps': len(self.get_coverage_gaps_data()),
            'critical_maintenance': len([
                issue for issue in self.get_maintenance_issues_data() 
                if issue['priority'] == 'Critical'
            ]),
            'pending_time_off': random.randint(0, 6),
            'pending_swaps': random.randint(0, 4),
            'high_overtime_employees': len([
                emp for emp in self.get_overtime_distribution_data()
                if emp['total_overtime_13_weeks'] > 60
            ])
        }

    def send_demo_message(self, message_type: str, **kwargs) -> Dict[str, Any]:
        """Simulate sending a message"""
        success_rate = 0.9  # 90% success rate for demo
        
        if random.random() < success_rate:
            message_id = random.randint(3000, 9999)
            recipients = kwargs.get('recipients', 1)
            
            return {
                'success': True,
                'message_id': message_id,
                'recipients': recipients,
                'sent_at': datetime.now().isoformat()
            }
        else:
            return {
                'success': False,
                'error': 'Demo network timeout - please try again'
            }

# Global demo service instance
demo_service = DemoDataService()
