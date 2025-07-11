from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Employee(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))  # For simple login
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    hire_date = db.Column(db.Date, default=datetime.utcnow)
    is_supervisor = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    crew = db.Column(db.String(50))  # Day shift, Night shift, Weekend, etc.
    overtime_eligible = db.Column(db.Boolean, default=True)
    overtime_hours = db.Column(db.Float, default=0)  # Track overtime hours
    max_hours_per_week = db.Column(db.Integer, default=40)
    
    # Vacation tracking
    vacation_days_total = db.Column(db.Float, default=14)  # Total vacation days per year
    vacation_days_used = db.Column(db.Float, default=0)   # Vacation days used this year
    sick_days_total = db.Column(db.Float, default=7)      # Total sick days per year
    sick_days_used = db.Column(db.Float, default=0)       # Sick days used this year
    personal_days_total = db.Column(db.Float, default=3)  # Total personal days per year
    personal_days_used = db.Column(db.Float, default=0)   # Personal days used this year
    
    # Relationships
    skills = db.relationship('EmployeeSkill', backref='employee', lazy=True)
    schedules = db.relationship('Schedule', backref='employee', lazy=True)
    availability = db.relationship('Availability', backref='employee', lazy=True)
    
    def __repr__(self):
        return f'<Employee {self.name}>'
    
    def has_skill(self, skill_id):
        return any(es.skill_id == skill_id for es in self.skills)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    @property
    def vacation_days_remaining(self):
        return self.vacation_days_total - self.vacation_days_used
    
    @property
    def sick_days_remaining(self):
        return self.sick_days_total - self.sick_days_used
    
    @property
    def personal_days_remaining(self):
        return self.personal_days_total - self.personal_days_used
    
    def get_time_off_balance(self, leave_type):
        """Get remaining balance for a specific leave type"""
        if leave_type == 'vacation':
            return self.vacation_days_remaining
        elif leave_type == 'sick':
            return self.sick_days_remaining
        elif leave_type == 'personal':
            return self.personal_days_remaining
        return 0

class Position(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    
    # Relationships
    required_skills = db.relationship('PositionSkill', backref='position', lazy=True)
    schedules = db.relationship('Schedule', backref='position', lazy=True)
    
    def __repr__(self):
        return f'<Position {self.name}>'

class Skill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    
    def __repr__(self):
        return f'<Skill {self.name}>'

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'), nullable=False)
    status = db.Column(db.String(20), default='scheduled')  # scheduled, confirmed, absent, covered
    hours = db.Column(db.Float)  # Calculate from start/end time
    is_overtime = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<Schedule {self.date} - {self.position_id}>'
    
    def calculate_hours(self):
        # Calculate hours worked for this shift
        if self.start_time and self.end_time:
            start = datetime.combine(self.date, self.start_time)
            end = datetime.combine(self.date, self.end_time)
            # Handle overnight shifts
            if end < start:
                end += timedelta(days=1)
            delta = end - start
            self.hours = delta.total_seconds() / 3600
        else:
            self.hours = 0
        return self.hours

class EmployeeSkill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey('skill.id'), nullable=False)
    proficiency = db.Column(db.Integer, default=3)  # 1-5 scale
    
class PositionSkill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey('skill.id'), nullable=False)
    required = db.Column(db.Boolean, default=True)

class Availability(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    day_of_week = db.Column(db.Integer)  # 0=Monday, 6=Sunday
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    is_available = db.Column(db.Boolean, default=True)

class TimeOffRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    leave_type = db.Column(db.String(20), nullable=False)  # vacation, sick, personal, unpaid
    reason = db.Column(db.String(200))
    status = db.Column(db.String(20), default='pending')  # pending, approved, denied, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # New fields for vacation system
    days_requested = db.Column(db.Float, default=0)  # Number of days requested
    approved_by = db.Column(db.Integer, db.ForeignKey('employee.id'))
    approved_at = db.Column(db.DateTime)
    supervisor_notes = db.Column(db.Text)
    
    # Coverage tracking
    requires_coverage = db.Column(db.Boolean, default=True)
    coverage_arranged = db.Column(db.Boolean, default=False)
    coverage_notes = db.Column(db.Text)
    
    # Relationships
    employee = db.relationship('Employee', foreign_keys=[employee_id], backref='time_off_requests')
    approver = db.relationship('Employee', foreign_keys=[approved_by])
    
    def calculate_days(self):
        """Calculate number of days requested (excluding weekends)"""
        if not self.start_date or not self.end_date:
            return 0
        
        days = 0
        current_date = self.start_date
        while current_date <= self.end_date:
            # Skip weekends (5=Saturday, 6=Sunday)
            if current_date.weekday() < 5:
                days += 1
            current_date += timedelta(days=1)
        
        self.days_requested = days
        return days

class CoverageRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    filled_by = db.Column(db.Integer, db.ForeignKey('employee.id'))
    status = db.Column(db.String(20), default='open')  # open, filled, cancelled
    
    schedule = db.relationship('Schedule', backref='coverage_requests')

# NEW MODELS FOR CASUAL WORKERS
class CasualWorker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))  # For simple login
    phone = db.Column(db.String(20), nullable=False)
    skills = db.Column(db.Text)  # Comma-separated skills
    availability = db.Column(db.Text)  # JSON string of available days/times
    status = db.Column(db.String(20), default='available')  # available, working, unavailable
    rating = db.Column(db.Float, default=5.0)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_worked = db.Column(db.Date)
    
    # Track work history
    assignments = db.relationship('CasualAssignment', backref='worker', lazy=True)
    
    def __repr__(self):
        return f'<CasualWorker {self.name}>'

class CasualAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('casual_worker.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    position = db.Column(db.String(100))
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, completed, cancelled
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<CasualAssignment {self.date} - {self.position}>'

# NEW MODEL FOR SHIFT SWAPPING
class ShiftSwapRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    requester_schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    target_employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    target_schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    reason = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')  # pending, approved, denied, cancelled
    supervisor_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('employee.id'))
    
    # Relationships
    requester = db.relationship('Employee', foreign_keys=[requester_id], backref='swap_requests_made')
    target_employee = db.relationship('Employee', foreign_keys=[target_employee_id], backref='swap_requests_received')
    requester_schedule = db.relationship('Schedule', foreign_keys=[requester_schedule_id])
    target_schedule = db.relationship('Schedule', foreign_keys=[target_schedule_id])
    reviewer = db.relationship('Employee', foreign_keys=[reviewed_by])
    
    def __repr__(self):
        return f'<ShiftSwapRequest {self.requester_id} -> {self.target_employee_id}>'

# NEW MODEL FOR SUGGESTIONS
class ScheduleSuggestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    suggestion_type = db.Column(db.String(50))  # shift_preference, availability_change, general
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='new')  # new, under_review, implemented, declined
    priority = db.Column(db.String(20), default='medium')  # low, medium, high
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    reviewer_notes = db.Column(db.Text)
    
    # Relationship
    employee = db.relationship('Employee', backref='suggestions')
    
    def __repr__(self):
        return f'<ScheduleSuggestion {self.title}>'

# NEW MODEL FOR VACATION CALENDAR EVENTS
class VacationCalendar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    leave_type = db.Column(db.String(20), nullable=False)  # vacation, sick, personal, unpaid
    time_off_request_id = db.Column(db.Integer, db.ForeignKey('time_off_request.id'))
    
    # Relationships
    employee = db.relationship('Employee', backref='vacation_calendar')
    time_off_request = db.relationship('TimeOffRequest', backref='calendar_entries')
    
    def __repr__(self):
        return f'<VacationCalendar {self.employee_id} - {self.date}>'
