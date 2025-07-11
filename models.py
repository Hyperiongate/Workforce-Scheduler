# models.py - Complete file with all features including sleep advisor

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta
import json

db = SQLAlchemy()

class Employee(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='employee')  # 'employee' or 'supervisor'
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'))
    department = db.Column(db.String(100))
    hire_date = db.Column(db.Date)
    phone = db.Column(db.String(20))
    crew = db.Column(db.String(1))  # A, B, C, or D for 4-crew rotation
    
    # Vacation tracking fields
    vacation_days_total = db.Column(db.Float, default=10.0)
    vacation_days_used = db.Column(db.Float, default=0.0)
    sick_days_total = db.Column(db.Float, default=5.0)
    sick_days_used = db.Column(db.Float, default=0.0)
    personal_days_total = db.Column(db.Float, default=3.0)
    personal_days_used = db.Column(db.Float, default=0.0)
    
    # Relationships
    schedules = db.relationship('Schedule', backref='employee', lazy='dynamic')
    skills = db.relationship('Skill', secondary='employee_skill', backref='employees')
    availability = db.relationship('Availability', backref='employee', lazy='dynamic')
    time_off_requests = db.relationship('TimeOffRequest', backref='employee', lazy='dynamic')
    
    def get_id(self):
        return str(self.id)

class Position(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100))
    
    # Relationships
    employees = db.relationship('Employee', backref='position', lazy='dynamic')
    required_skills = db.relationship('Skill', secondary='position_skill', backref='positions')

class Skill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(200))

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    shift_type = db.Column(db.String(20))  # 'day', 'evening', 'night'
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'))
    
    # Relationships
    position = db.relationship('Position', backref='schedules')

class EmployeeSkill(db.Model):
    __tablename__ = 'employee_skill'
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), primary_key=True)
    skill_id = db.Column(db.Integer, db.ForeignKey('skill.id'), primary_key=True)
    proficiency_level = db.Column(db.Integer, default=3)  # 1-5 scale
    certified_date = db.Column(db.Date)

class PositionSkill(db.Model):
    __tablename__ = 'position_skill'
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'), primary_key=True)
    skill_id = db.Column(db.Integer, db.ForeignKey('skill.id'), primary_key=True)
    required_level = db.Column(db.Integer, default=3)  # Minimum proficiency required

class Availability(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    day_of_week = db.Column(db.Integer)  # 0-6 (Monday-Sunday)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    availability_type = db.Column(db.String(20))  # 'available', 'preferred', 'unavailable'

class TimeOffRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(200))
    status = db.Column(db.String(20), default='pending')  # 'pending', 'approved', 'denied'
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    
    # Enhanced fields for vacation tracking
    leave_type = db.Column(db.String(20))  # 'vacation', 'sick', 'personal'
    days_requested = db.Column(db.Float)
    approved_by = db.Column(db.Integer, db.ForeignKey('employee.id'))
    approved_at = db.Column(db.DateTime)
    supervisor_notes = db.Column(db.Text)
    requires_coverage = db.Column(db.Boolean, default=True)
    coverage_arranged = db.Column(db.Boolean, default=False)
    coverage_notes = db.Column(db.Text)
    
    # Relationships
    approver = db.relationship('Employee', foreign_keys=[approved_by], backref='approved_requests')

class VacationCalendar(db.Model):
    """Calendar entries for approved time off"""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    leave_type = db.Column(db.String(20))  # 'vacation', 'sick', 'personal'
    time_off_request_id = db.Column(db.Integer, db.ForeignKey('time_off_request.id'))
    
    # Relationships
    employee = db.relationship('Employee', backref='vacation_calendar')
    time_off_request = db.relationship('TimeOffRequest', backref='calendar_entries')

class CoverageRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    requesting_employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    covering_employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    reason = db.Column(db.String(200))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    schedule = db.relationship('Schedule', backref='coverage_requests')
    requesting_employee = db.relationship('Employee', foreign_keys=[requesting_employee_id], backref='coverage_requested')
    covering_employee = db.relationship('Employee', foreign_keys=[covering_employee_id], backref='coverage_provided')

class CasualWorker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    skills = db.Column(db.String(500))  # Comma-separated skills
    availability = db.Column(db.String(200))  # JSON or simple text
    hourly_rate = db.Column(db.Float)
    rating = db.Column(db.Float, default=0.0)
    total_hours_worked = db.Column(db.Float, default=0.0)
    registration_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    assignments = db.relationship('CasualAssignment', backref='worker', lazy='dynamic')

class CasualAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    casual_worker_id = db.Column(db.Integer, db.ForeignKey('casual_worker.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    department = db.Column(db.String(100))
    supervisor_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    status = db.Column(db.String(20), default='scheduled')  # 'scheduled', 'completed', 'cancelled'
    hours_worked = db.Column(db.Float)
    performance_rating = db.Column(db.Integer)  # 1-5 scale
    notes = db.Column(db.Text)
    
    # Relationships
    supervisor = db.relationship('Employee', backref='supervised_casuals')

class ShiftSwapRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    requesting_employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    requested_schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    offering_schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    target_employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    reason = db.Column(db.String(200))
    status = db.Column(db.String(20), default='pending')  # 'pending', 'approved', 'denied'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('employee.id'))
    
    # Relationships
    requesting_employee = db.relationship('Employee', foreign_keys=[requesting_employee_id], backref='swap_requests_made')
    target_employee = db.relationship('Employee', foreign_keys=[target_employee_id], backref='swap_requests_received')
    requested_schedule = db.relationship('Schedule', foreign_keys=[requested_schedule_id], backref='swap_requests_for')
    offering_schedule = db.relationship('Schedule', foreign_keys=[offering_schedule_id], backref='swap_offers')
    reviewer = db.relationship('Employee', foreign_keys=[reviewed_by], backref='swap_requests_reviewed')

class ScheduleSuggestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    suggestion_type = db.Column(db.String(50))  # 'pattern', 'coverage', 'fairness', etc.
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), default='medium')  # 'low', 'medium', 'high'
    status = db.Column(db.String(20), default='pending')  # 'pending', 'reviewing', 'implemented', 'rejected'
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('employee.id'))
    response = db.Column(db.Text)
    
    # Relationships
    employee = db.relationship('Employee', foreign_keys=[employee_id], backref='suggestions_made')
    reviewer = db.relationship('Employee', foreign_keys=[reviewed_by], backref='suggestions_reviewed')

# Sleep and Circadian Rhythm Models

class CircadianProfile(db.Model):
    """Track employee circadian rhythm and sleep patterns"""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    
    # Chronotype assessment (morning lark vs night owl)
    chronotype = db.Column(db.String(20))  # 'morning', 'intermediate', 'evening'
    chronotype_score = db.Column(db.Float)  # -2 to +2 scale
    
    # Current shift pattern tracking
    current_shift_type = db.Column(db.String(20))  # 'day', 'evening', 'night'
    days_on_current_pattern = db.Column(db.Integer, default=0)
    last_shift_change = db.Column(db.DateTime)
    
    # Sleep debt tracking
    cumulative_sleep_debt = db.Column(db.Float, default=0.0)  # in hours
    last_sleep_debt_update = db.Column(db.DateTime)
    
    # Adaptation progress
    circadian_adaptation_score = db.Column(db.Float, default=0.0)  # 0-100%
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    employee = db.relationship('Employee', backref='circadian_profile')
    sleep_logs = db.relationship('SleepLog', backref='circadian_profile', lazy='dynamic')
    sleep_recommendations = db.relationship('SleepRecommendation', backref='circadian_profile', lazy='dynamic')


class SleepLog(db.Model):
    """Track actual sleep patterns"""
    id = db.Column(db.Integer, primary_key=True)
    circadian_profile_id = db.Column(db.Integer, db.ForeignKey('circadian_profile.id'), nullable=False)
    
    # Sleep timing
    sleep_date = db.Column(db.Date, nullable=False)
    bedtime = db.Column(db.DateTime)
    wake_time = db.Column(db.DateTime)
    
    # Sleep quality metrics
    sleep_duration = db.Column(db.Float)  # hours
    sleep_quality = db.Column(db.Integer)  # 1-10 scale
    sleep_efficiency = db.Column(db.Float)  # percentage
    
    # Factors
    pre_sleep_light_exposure = db.Column(db.String(20))  # 'high', 'moderate', 'low'
    caffeine_cutoff_time = db.Column(db.Time)
    took_nap = db.Column(db.Boolean, default=False)
    nap_duration = db.Column(db.Integer)  # minutes
    
    # Work context
    worked_before_sleep = db.Column(db.Boolean)
    shift_type_before_sleep = db.Column(db.String(20))
    hours_since_last_shift = db.Column(db.Float)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SleepRecommendation(db.Model):
    """Personalized sleep recommendations"""
    id = db.Column(db.Integer, primary_key=True)
    circadian_profile_id = db.Column(db.Integer, db.ForeignKey('circadian_profile.id'), nullable=False)
    
    # Recommendation details
    recommendation_date = db.Column(db.DateTime, default=datetime.utcnow)
    recommendation_type = db.Column(db.String(50))  # 'sleep_timing', 'light_exposure', 'nap', 'caffeine', 'meal_timing'
    priority = db.Column(db.String(20))  # 'critical', 'high', 'medium', 'low'
    
    # Content
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    action_items = db.Column(db.JSON)  # List of specific actions
    
    # Timing
    valid_from = db.Column(db.DateTime)
    valid_until = db.Column(db.DateTime)
    
    # Tracking
    was_viewed = db.Column(db.Boolean, default=False)
    viewed_at = db.Column(db.DateTime)
    was_helpful = db.Column(db.Boolean)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ShiftTransitionPlan(db.Model):
    """Help employees transition between different shift patterns"""
    id = db.Column(db.Integer, primary_key=True)
    circadian_profile_id = db.Column(db.Integer, db.ForeignKey('circadian_profile.id'), nullable=False)
    
    # Transition details
    from_shift_type = db.Column(db.String(20))
    to_shift_type = db.Column(db.String(20))
    transition_start_date = db.Column(db.Date)
    transition_duration_days = db.Column(db.Integer)
    
    # Plan details
    plan_data = db.Column(db.JSON)  # Daily sleep/wake recommendations
    is_active = db.Column(db.Boolean, default=True)
    completion_percentage = db.Column(db.Float, default=0.0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    # Relationship
    circadian_profile = db.relationship('CircadianProfile', backref='transition_plans')
