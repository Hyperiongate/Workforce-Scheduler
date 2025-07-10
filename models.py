from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin

db = SQLAlchemy()

class Employee(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    hire_date = db.Column(db.Date, default=datetime.utcnow)
    is_supervisor = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    crew = db.Column(db.String(50))  # Day shift, Night shift, Weekend, etc.
    
    # Relationships
    skills = db.relationship('EmployeeSkill', backref='employee', lazy=True)
    schedules = db.relationship('Schedule', backref='employee', lazy=True)
    availability = db.relationship('Availability', backref='employee', lazy=True)
    
    def __repr__(self):
        return f'<Employee {self.name}>'

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
    
    def __repr__(self):
        return f'<Schedule {self.date} - {self.position_id}>'

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
    reason = db.Column(db.String(200))
    status = db.Column(db.String(20), default='pending')  # pending, approved, denied
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    employee = db.relationship('Employee', backref='time_off_requests')

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
