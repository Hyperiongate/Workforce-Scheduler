from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, JSON

db = SQLAlchemy()

# Association tables
employee_skills = db.Table('employee_skills',
    db.Column('employee_id', db.Integer, db.ForeignKey('employee.id'), primary_key=True),
    db.Column('skill_id', db.Integer, db.ForeignKey('skill.id'), primary_key=True),
    db.Column('is_primary', db.Boolean, default=False),  # Track primary qualification
    db.Column('certification_date', db.Date),
    db.Column('expiry_date', db.Date)
)

position_skills = db.Table('position_skills',
    db.Column('position_id', db.Integer, db.ForeignKey('position.id'), primary_key=True),
    db.Column('skill_id', db.Integer, db.ForeignKey('skill.id'), primary_key=True)
)

class Employee(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(20), unique=True)  # Employee ID field
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(200))
    is_supervisor = db.Column(db.Boolean, default=False)
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'))
    department = db.Column(db.String(50))
    hire_date = db.Column(db.Date, default=date.today)
    phone = db.Column(db.String(20))
    crew = db.Column(db.String(1))  # A, B, C, or D for 24/7 operations
    shift_pattern = db.Column(db.String(20))  # day, night, rotating, etc.
    seniority_date = db.Column(db.Date)  # For determining order in various processes
    
    # NEW AUTHENTICATION FIELDS
    username = db.Column(db.String(50), unique=True, nullable=True, index=True)
    
    # Account status fields
    must_change_password = db.Column(db.Boolean, default=True)
    first_login = db.Column(db.Boolean, default=True)
    account_active = db.Column(db.Boolean, default=True)
    
    # Account tracking
    account_created_date = db.Column(db.DateTime, nullable=True)
    last_password_change = db.Column(db.DateTime, nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)
    login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    
    # Password reset
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    
    # NEW FIELDS FOR STAFFING MANAGEMENT
    default_shift = db.Column(db.String(20), default='day')
    max_consecutive_days = db.Column(db.Integer, default=14)
    is_on_call = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    
    # Time off balances
    vacation_days = db.Column(db.Float, default=10.0)
    sick_days = db.Column(db.Float, default=5.0)
    personal_days = db.Column(db.Float, default=3.0)
    
    # Relationships - FIXED VERSION
    position = db.relationship('Position', backref='employees')
    skills = db.relationship('Skill', secondary=employee_skills, backref='employees')
    schedules = db.relationship('Schedule', foreign_keys='[Schedule.employee_id]', backref='employee', lazy='dynamic')
    availability = db.relationship('Availability', backref='employee', lazy='dynamic')
    coverage_requests = db.relationship('CoverageRequest', 
                                      foreign_keys='[CoverageRequest.requester_id]',
                                      backref='requester', 
                                      lazy='dynamic')
    circadian_profile = db.relationship('CircadianProfile', backref='employee', uselist=False, 
                                      cascade='all, delete-orphan')
    sleep_logs = db.relationship('SleepLog', backref='employee', lazy='dynamic', 
                               cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_primary_skills(self):
        """Get list of primary skills/qualifications"""
        return db.session.query(Skill).join(employee_skills).filter(
            employee_skills.c.employee_id == self.id,
            employee_skills.c.is_primary == True
        ).all()
    
    def has_skill(self, skill_name):
        """Check if employee has a specific skill"""
        return any(skill.name == skill_name for skill in self.skills)
    
    def can_work_position(self, position):
        """Check if employee has all required skills for a position"""
        required_skills = set(skill.id for skill in position.required_skills)
        employee_skills = set(skill.id for skill in self.skills)
        return required_skills.issubset(employee_skills)
    
    # NEW AUTHENTICATION METHODS
    @property
    def full_name(self):
        """Get employee's full name"""
        return self.name if self.name else f"Employee {self.employee_id}"
    
    @property
    def first_name(self):
        """Extract first name from full name"""
        if self.name:
            parts = self.name.split()
            return parts[0] if parts else ''
        return ''
    
    @property
    def last_name(self):
        """Extract last name from full name"""
        if self.name:
            parts = self.name.split()
            return parts[-1] if len(parts) > 1 else ''
        return ''
    
    @property
    def role(self):
        """Get role for compatibility"""
        return 'Supervisor' if self.is_supervisor else 'Employee'
    
    @property
    def password(self):
        """Compatibility property for password"""
        return self.password_hash
        
    @password.setter
    def password(self, value):
        """Compatibility setter for password"""
        self.password_hash = value
    
    def is_locked(self):
        """Check if account is locked"""
        if self.locked_until and self.locked_until > datetime.utcnow():
            return True
        return False
        
    def increment_login_attempts(self):
        """Increment failed login attempts"""
        self.login_attempts += 1
        # Lock account after 5 failed attempts for 30 minutes
        if self.login_attempts >= 5:
            self.locked_until = datetime.utcnow() + timedelta(minutes=30)
            
    def reset_login_attempts(self):
        """Reset login attempts on successful login"""
        self.login_attempts = 0
        self.locked_until = None
        self.last_login = datetime.utcnow()
        
    def generate_reset_token(self):
        """Generate password reset token"""
        import secrets
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        return self.reset_token
        
    def validate_reset_token(self, token):
        """Validate reset token"""
        if not self.reset_token or self.reset_token != token:
            return False
        if self.reset_token_expires < datetime.utcnow():
            return False
        return True
        
    # ==================== OVERTIME PROPERTIES ====================
    @property
    def current_week_overtime(self):
        """Get current week's overtime hours"""
        from datetime import date, timedelta
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        
        ot_record = OvertimeHistory.query.filter_by(
            employee_id=self.id,
            week_start_date=week_start
        ).first()
        
        return ot_record.overtime_hours if ot_record else 0
    
    @property
    def last_13_weeks_overtime(self):
        """Get total overtime for last 13 weeks"""
        from datetime import date, timedelta
        end_date = date.today()
        start_date = end_date - timedelta(weeks=13)
        
        total = db.session.query(func.sum(OvertimeHistory.overtime_hours)).filter(
            OvertimeHistory.employee_id == self.id,
            OvertimeHistory.week_start_date >= start_date,
            OvertimeHistory.week_start_date <= end_date
        ).scalar()
        
        return total or 0
    
    @property
    def average_weekly_overtime(self):
        """Get average weekly overtime for last 13 weeks"""
        total = self.last_13_weeks_overtime
        return round(total / 13, 2) if total else 0
    
    @property
    def overtime_trend(self):
        """Get overtime trend (increasing, decreasing, stable)"""
        from datetime import date, timedelta
        
        # Get last 4 weeks
        recent_4_weeks = []
        for i in range(4):
            week_start = date.today() - timedelta(weeks=i+1)
            week_start = week_start - timedelta(days=week_start.weekday())
            
            ot_record = OvertimeHistory.query.filter_by(
                employee_id=self.id,
                week_start_date=week_start
            ).first()
            
            recent_4_weeks.append(ot_record.overtime_hours if ot_record else 0)
        
        # Check trend
        if all(recent_4_weeks[i] <= recent_4_weeks[i+1] for i in range(3)):
            return 'increasing'
        elif all(recent_4_weeks[i] >= recent_4_weeks[i+1] for i in range(3)):
            return 'decreasing'
        else:
            return 'stable'
    
    def get_overtime_hours(self, start_date, end_date):
        """Get total overtime hours in date range"""
        total = db.session.query(func.sum(OvertimeHistory.overtime_hours)).filter(
            OvertimeHistory.employee_id == self.id,
            OvertimeHistory.week_start_date >= start_date,
            OvertimeHistory.week_start_date <= end_date
        ).scalar()
        
        return total or 0
    
    def update_overtime_record(self, week_start_date, regular_hours=0, overtime_hours=0):
        """Update or create overtime record for a specific week"""
        ot_record = OvertimeHistory.query.filter_by(
            employee_id=self.id,
            week_start_date=week_start_date
        ).first()
        
        if ot_record:
            ot_record.regular_hours = regular_hours
            ot_record.overtime_hours = overtime_hours
            ot_record.total_hours = regular_hours + overtime_hours
            ot_record.updated_at = datetime.utcnow()
        else:
            ot_record = OvertimeHistory(
                employee_id=self.id,
                week_start_date=week_start_date,
                regular_hours=regular_hours,
                overtime_hours=overtime_hours,
                total_hours=regular_hours + overtime_hours
            )
            db.session.add(ot_record)
        
        db.session.commit()
        return ot_record

# Add this to your models.py file

class CrewCoverageRequirement(db.Model):
    """Crew-specific coverage requirements for positions"""
    __tablename__ = 'crew_coverage_requirements'
    
    id = db.Column(db.Integer, primary_key=True)
    crew = db.Column(db.String(1), nullable=False)  # A, B, C, or D
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'), nullable=False)
    min_coverage = db.Column(db.Integer, default=0)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    position = db.relationship('Position', backref='crew_requirements')
    
    # Unique constraint to prevent duplicate crew-position combinations
    __table_args__ = (
        db.UniqueConstraint('crew', 'position_id', name='_crew_position_uc'),
    )
    
    def __repr__(self):
        return f'<CrewCoverageRequirement Crew {self.crew} - {self.position.name}: {self.min_coverage}>'

class Position(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(50))
    min_coverage = db.Column(db.Integer, default=1)  # Minimum people needed
    
    # NEW FIELDS FOR STAFFING MANAGEMENT
    skills_required = db.Column(db.Text)  # Comma-separated list of required skills
    requires_coverage = db.Column(db.Boolean, default=True)
    critical_position = db.Column(db.Boolean, default=False)
    
    # Relationships
    required_skills = db.relationship('Skill', secondary=position_skills, backref='positions')

class Skill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    category = db.Column(db.String(50))  # technical, certification, etc.
    requires_certification = db.Column(db.Boolean, default=False)
    certification_valid_days = db.Column(db.Integer, default=365)  # How long cert is valid

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    shift_type = db.Column(db.String(20))  # day, evening, night, etc.
    start_time = db.Column(db.String(10))  # Changed to String
    end_time = db.Column(db.String(10))    # Changed to String
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'))
    hours = db.Column(db.Float)
    crew = db.Column(db.String(1))  # A, B, C, or D
    status = db.Column(db.String(20), default='scheduled')  # scheduled, worked, absent, covered
    
    # NEW FIELDS FOR STAFFING MANAGEMENT
    is_overtime = db.Column(db.Boolean, default=False)
    overtime_reason = db.Column(db.String(200))
    original_employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    
    # Relationships
    position = db.relationship('Position', backref='schedules')
    original_employee = db.relationship('Employee', foreign_keys=[original_employee_id])
    
    # Indexes for better query performance
    __table_args__ = (
        db.Index('idx_schedule_date_crew', 'date', 'crew'),
        db.Index('idx_schedule_employee_date', 'employee_id', 'date'),
    )

class Availability(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    day_of_week = db.Column(db.Integer)  # 0=Monday, 6=Sunday
    available = db.Column(db.Boolean, default=True)
    preferred_shift = db.Column(db.String(20))
    notes = db.Column(db.Text)

class TimeOffRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    request_type = db.Column(db.String(20))  # vacation, sick, personal
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')  # pending, approved, denied
    
    # UPDATED FIELDS
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Changed from submitted_date
    approved_by = db.Column(db.Integer, db.ForeignKey('employee.id'))  # Changed from reviewed_by_id
    approved_date = db.Column(db.DateTime)  # Changed from reviewed_date
    notes = db.Column(db.Text)  # Changed from reviewer_notes
    days_requested = db.Column(db.Float)
    
    # Relationships
    employee = db.relationship('Employee', foreign_keys=[employee_id], backref='time_off_requests')
    approver = db.relationship('Employee', foreign_keys=[approved_by], backref='approved_time_off_requests')

class VacationCalendar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    request_id = db.Column(db.Integer, db.ForeignKey('time_off_request.id'))
    type = db.Column(db.String(20))  # vacation, sick, personal, holiday
    status = db.Column(db.String(20), default='approved')  # For tracking
    
    # Relationships
    employee = db.relationship('Employee', backref='calendar_entries')
    request = db.relationship('TimeOffRequest', backref='calendar_entries')
    
    # Ensure no duplicate entries
    __table_args__ = (
        db.UniqueConstraint('employee_id', 'date', name='_employee_date_uc'),
    )

class CoverageRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'))
    requester_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    reason = db.Column(db.String(200))
    status = db.Column(db.String(20), default='open')  # open, filled, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    filled_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    filled_at = db.Column(db.DateTime)
    
    # Push notification fields
    pushed_to_crews = db.Column(db.String(10))  # "A,B,C" for multiple crews
    pushed_to_supervisors = db.Column(db.Text)  # JSON list of supervisor IDs
    push_message = db.Column(db.Text)
    position_required = db.Column(db.Integer, db.ForeignKey('position.id'))
    skills_required = db.Column(db.Text)  # JSON list of skill IDs
    
    # Relationships
    schedule = db.relationship('Schedule', backref='coverage_request')
    filled_by = db.relationship('Employee', foreign_keys=[filled_by_id])
    position = db.relationship('Position', backref='coverage_requests')

class CasualWorker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    skills = db.Column(db.Text)  # JSON list of skills
    availability = db.Column(db.Text)  # JSON availability preferences
    rating = db.Column(db.Float, default=5.0)
    total_hours_worked = db.Column(db.Float, default=0.0)
    registered_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    preferred_crews = db.Column(db.String(10))  # "A,B,C" for multiple crews
    
    # Relationships
    assignments = db.relationship('CasualAssignment', backref='worker', lazy='dynamic')

class CasualAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('casual_worker.id'), nullable=False)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'))
    date = db.Column(db.Date, nullable=False)
    shift_type = db.Column(db.String(20))
    hours = db.Column(db.Float)
    position = db.Column(db.String(100))
    crew = db.Column(db.String(1))
    status = db.Column(db.String(20), default='assigned')  # assigned, completed, cancelled
    rating = db.Column(db.Integer)  # 1-5 rating for this assignment
    notes = db.Column(db.Text)
    
    # Relationships
    schedule = db.relationship('Schedule', backref='casual_assignment')

class ShiftSwapRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    requested_with_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    requester_schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    requested_schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, denied
    reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    reviewed_at = db.Column(db.DateTime)
    reviewer_notes = db.Column(db.Text)
    
    # Relationships
    requester = db.relationship('Employee', foreign_keys=[requester_id], backref='swap_requests_made')
    requested_with = db.relationship('Employee', foreign_keys=[requested_with_id], backref='swap_requests_received')
    requester_schedule = db.relationship('Schedule', foreign_keys=[requester_schedule_id])
    requested_schedule = db.relationship('Schedule', foreign_keys=[requested_schedule_id])
    reviewer = db.relationship('Employee', foreign_keys=[reviewed_by_id])

class ScheduleSuggestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    suggestion_type = db.Column(db.String(50))  # shift_preference, availability_change, scheduling_process, fairness, general
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), default='medium')  # low, medium, high
    status = db.Column(db.String(20), default='new')  # new, under_review, implemented, declined
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    reviewer_notes = db.Column(db.Text)
    
    # Relationships
    employee = db.relationship('Employee', foreign_keys=[employee_id], backref='schedule_suggestions')
    reviewed_by = db.relationship('Employee', foreign_keys=[reviewed_by_id], backref='schedule_suggestions_reviewed')

# Shift Trade Models
class ShiftTrade(db.Model):
    """Represents a shift trade transaction between two employees"""
    __tablename__ = 'shift_trades'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Employee 1 (initiator)
    employee1_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    schedule1_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    
    # Employee 2 
    employee2_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    schedule2_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    
    # Status tracking
    status = db.Column(db.String(20), default='pending')  # pending, employee_approved, supervisor_approved, rejected, cancelled
    
    # Approvals
    employee1_approved = db.Column(db.Boolean, default=False)
    employee1_approved_at = db.Column(db.DateTime)
    employee2_approved = db.Column(db.Boolean, default=False)
    employee2_approved_at = db.Column(db.DateTime)
    
    supervisor_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    supervisor_approved_at = db.Column(db.DateTime)
    
    # Notes
    employee1_notes = db.Column(db.Text)
    employee2_notes = db.Column(db.Text)
    supervisor_notes = db.Column(db.Text)
    rejection_reason = db.Column(db.Text)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    # Supervisor visibility notes - NEW
    employee1_supervisor_notes = db.Column(db.Text)  # What supervisor should know about emp1's situation
    employee2_supervisor_notes = db.Column(db.Text)  # What supervisor should know about emp2's situation
    
    # Relationships
    employee1 = db.relationship('Employee', foreign_keys=[employee1_id], backref='trades_initiated')
    employee2 = db.relationship('Employee', foreign_keys=[employee2_id], backref='trades_received')
    schedule1 = db.relationship('Schedule', foreign_keys=[schedule1_id])
    schedule2 = db.relationship('Schedule', foreign_keys=[schedule2_id])
    supervisor = db.relationship('Employee', foreign_keys=[supervisor_id])
    
    @property
    def is_approved(self):
        """Check if trade is fully approved"""
        return (self.employee1_approved and 
                self.employee2_approved and 
                self.status == 'supervisor_approved')
    
    @property
    def is_pending_supervisor(self):
        """Check if waiting for supervisor approval"""
        return (self.employee1_approved and 
                self.employee2_approved and 
                self.status == 'employee_approved')
                
    @property
    def other_employee(self):
        """Get the other employee in the trade from current user perspective"""
        from flask_login import current_user
        if current_user.id == self.employee1_id:
            return self.employee2
        return self.employee1
        
    @property
    def my_schedule(self):
        """Get current user's schedule in the trade"""
        from flask_login import current_user
        if current_user.id == self.employee1_id:
            return self.schedule1
        return self.schedule2
        
    @property
    def other_schedule(self):
        """Get other employee's schedule in the trade"""
        from flask_login import current_user
        if current_user.id == self.employee1_id:
            return self.schedule2
        return self.schedule1
    
    @property
    def supervisor_notes(self):
        """Get supervisor notes relevant to current user"""
        from flask_login import current_user
        if current_user.id == self.employee1_id:
            return self.employee1_supervisor_notes
        return self.employee2_supervisor_notes

class TradeMatchPreference(db.Model):
    """Employee preferences for trade matching"""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), unique=True, nullable=False)
    
    # Matching preferences
    prefer_same_position = db.Column(db.Boolean, default=True)
    prefer_same_shift_type = db.Column(db.Boolean, default=False)
    max_commute_difference = db.Column(db.Integer)  # minutes
    
    # Blackout dates (JSON list of date ranges)
    blackout_dates = db.Column(db.Text)
    
    # Auto-approval settings
    auto_approve_same_position = db.Column(db.Boolean, default=False)
    auto_approve_same_crew = db.Column(db.Boolean, default=False)
    
    # Notification preferences
    notify_new_matches = db.Column(db.Boolean, default=True)
    notify_proposal_received = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    employee = db.relationship('Employee', backref=db.backref('trade_preferences', uselist=False))

# ==========================================
# NEW COMMUNICATION MODELS
# ==========================================

class SupervisorMessage(db.Model):
    """Messages between supervisors across different shifts"""
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), default='normal')  # low, normal, high, urgent
    category = db.Column(db.String(50))  # coverage, safety, general, handoff, etc.
    
    # Metadata
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime)
    archived = db.Column(db.Boolean, default=False)
    
    # Thread support for conversations
    parent_message_id = db.Column(db.Integer, db.ForeignKey('supervisor_message.id'))
    
    # Relationships
    sender = db.relationship('Employee', foreign_keys=[sender_id], backref='sent_supervisor_messages')
    recipient = db.relationship('Employee', foreign_keys=[recipient_id], backref='received_supervisor_messages')
    replies = db.relationship('SupervisorMessage', backref=db.backref('parent_message', remote_side=[id]))
    
    @property
    def is_read(self):
        return self.read_at is not None

class PositionMessage(db.Model):
    """Messages between employees in the same position across different shifts"""
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50))  # handoff, tips, questions, alerts, etc.
    
    # Visibility
    crew_specific = db.Column(db.Boolean, default=False)
    target_crew = db.Column(db.String(1))  # If crew_specific, which crew
    
    # Metadata
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)  # Optional expiration
    
    # Relationships
    sender = db.relationship('Employee', backref='position_messages_sent')
    position = db.relationship('Position', backref='messages')
    read_receipts = db.relationship('MessageReadReceipt', backref='position_message', 
                                   cascade='all, delete-orphan')
    
    def is_read_by(self, employee_id):
        """Check if message was read by specific employee"""
        return any(r.employee_id == employee_id for r in self.read_receipts)

class MessageReadReceipt(db.Model):
    """Track who has read position messages"""
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('position_message.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    read_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    employee = db.relationship('Employee', backref='message_read_receipts')
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('message_id', 'employee_id', name='_message_employee_uc'),
    )

# ==========================================
# EQUIPMENT & MAINTENANCE MODELS
# ==========================================

class Equipment(db.Model):
    """Track equipment that employees might need to report issues for"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    equipment_type = db.Column(db.String(50))
    location = db.Column(db.String(100))
    serial_number = db.Column(db.String(100), unique=True)
    department = db.Column(db.String(50))
    status = db.Column(db.String(20), default='operational')  # operational, maintenance, broken
    last_maintenance = db.Column(db.Date)
    next_maintenance = db.Column(db.Date)
    
    # Relationships
    issues = db.relationship('MaintenanceIssue', backref='equipment', lazy='dynamic')

class MaintenanceIssue(db.Model):
    """Track maintenance issues reported by employees"""
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipment.id'))
    
    # Issue details
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(100))
    severity = db.Column(db.String(20), default='medium')  # low, medium, high, critical
    category = db.Column(db.String(50))  # electrical, mechanical, safety, etc.
    
    # Status tracking
    status = db.Column(db.String(20), default='new')  # new, assigned, in_progress, resolved, closed
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    resolved_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    
    # Timestamps
    reported_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_at = db.Column(db.DateTime)
    resolved_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)
    
    # Resolution details
    resolution_notes = db.Column(db.Text)
    downtime_hours = db.Column(db.Float)
    
    # Relationships
    reporter = db.relationship('Employee', foreign_keys=[reporter_id], 
                             backref='reported_issues')
    assigned_to = db.relationship('Employee', foreign_keys=[assigned_to_id], 
                                backref='assigned_issues')
    resolved_by = db.relationship('Employee', foreign_keys=[resolved_by_id], 
                                backref='resolved_issues')
    comments = db.relationship('MaintenanceComment', backref='issue', 
                             cascade='all, delete-orphan')

class MaintenanceComment(db.Model):
    """Comments on maintenance issues"""
    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(db.Integer, db.ForeignKey('maintenance_issue.id'), nullable=False)
    commenter_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    commenter = db.relationship('Employee', backref='maintenance_comments')

# ==========================================
# SUGGESTION BOX MODEL
# ==========================================

class EmployeeSuggestion(db.Model):
    """Track employee suggestions for improvements"""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), default='medium')  # low, medium, high
    status = db.Column(db.String(20), default='new')  # new, reviewed, implemented, declined
    submitted_date = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_date = db.Column(db.DateTime)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    response = db.Column(db.Text)
    
    # Relationships
    employee = db.relationship('Employee', foreign_keys=[employee_id], 
                             backref='employee_suggestions')
    reviewed_by = db.relationship('Employee', foreign_keys=[reviewed_by_id], 
                                backref='employee_suggestions_reviewed')

# Sleep Management Models
class CircadianProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), unique=True, nullable=False)
    chronotype = db.Column(db.String(20))  # morning, intermediate, evening
    current_shift_type = db.Column(db.String(20))  # day, evening, night
    days_on_current_pattern = db.Column(db.Integer, default=0)
    circadian_adaptation_score = db.Column(db.Float, default=50.0)  # 0-100
    last_shift_change = db.Column(db.Date)
    preferred_sleep_time = db.Column(db.Time)
    preferred_wake_time = db.Column(db.Time)
    
    # Assessment data
    assessment_completed = db.Column(db.DateTime)
    morningness_score = db.Column(db.Integer)  # MEQ score
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SleepLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    bedtime = db.Column(db.DateTime)
    wake_time = db.Column(db.DateTime)
    sleep_duration = db.Column(db.Float)  # hours
    sleep_quality = db.Column(db.Integer)  # 1-10 scale
    
    # Environmental factors
    pre_sleep_light_exposure = db.Column(db.String(20))  # minimal, moderate, high
    caffeine_cutoff_time = db.Column(db.Time)
    exercise_time = db.Column(db.Time)
    
    # Nap information
    had_nap = db.Column(db.Boolean, default=False)
    nap_start = db.Column(db.Time)
    nap_duration = db.Column(db.Integer)  # minutes
    
    # Work context
    worked_date = db.Column(db.Date)
    shift_type = db.Column(db.String(20))
    
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('employee_id', 'date', name='_employee_sleep_date_uc'),
    )

class SleepRecommendation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    recommendation_type = db.Column(db.String(50))  # sleep_timing, light_exposure, etc.
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), default='medium')
    target_shift_type = db.Column(db.String(20))  # Which shift type this applies to
    
    # Timing
    valid_from = db.Column(db.Date)
    valid_until = db.Column(db.Date)
    dismissed_at = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    employee = db.relationship('Employee', backref='sleep_recommendations')

# ==================== NOTIFICATION MODELS ====================
class CoverageNotification(db.Model):
    """Track notifications sent for coverage needs"""
    __tablename__ = 'coverage_notification'
    
    id = db.Column(db.Integer, primary_key=True)
    coverage_request_id = db.Column(db.Integer, db.ForeignKey('coverage_request.id'), nullable=False)
    sent_to_employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    sent_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    viewed_at = db.Column(db.DateTime)
    response = db.Column(db.String(20))  # 'accepted', 'declined', 'no_response'
    response_at = db.Column(db.DateTime)
    
    # Relationships
    coverage_request = db.relationship('CoverageRequest', backref='notifications')
    sent_to_employee = db.relationship('Employee', foreign_keys=[sent_to_employee_id])
    sent_by = db.relationship('Employee', foreign_keys=[sent_by_id])

# ==================== POSITION COVERAGE REQUIREMENT ====================
class PositionCoverage(db.Model):
    """Define minimum coverage requirements for positions by shift type"""
    __tablename__ = 'position_coverage'
    
    id = db.Column(db.Integer, primary_key=True)
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'), nullable=False)
    shift_type = db.Column(db.String(20), nullable=False)  # day, night
    min_required = db.Column(db.Integer, default=1)
    
    # Relationships
    position = db.relationship('Position', backref='coverage_requirements')
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('position_id', 'shift_type', name='_position_shift_uc'),
    )

# ==========================================
# NEW STAFFING MANAGEMENT MODELS
# ==========================================

class OvertimeOpportunity(db.Model):
    """Track overtime opportunities posted to employees"""
    __tablename__ = 'overtime_opportunities'
    
    id = db.Column(db.Integer, primary_key=True)
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    shift_type = db.Column(db.String(20), nullable=False)
    posted_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    posted_at = db.Column(db.DateTime, default=datetime.now)
    response_deadline = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='open')
    urgency = db.Column(db.String(20), default='standard')
    notes = db.Column(db.Text)
    filled_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    filled_at = db.Column(db.DateTime)
    notified_employees = db.Column(JSON)
    
    position = db.relationship('Position', backref='overtime_opportunities')
    posted_by = db.relationship('Employee', foreign_keys=[posted_by_id], backref='posted_overtime')
    filled_by = db.relationship('Employee', foreign_keys=[filled_by_id], backref='overtime_taken')

class OvertimeResponse(db.Model):
    """Track employee responses to overtime opportunities"""
    __tablename__ = 'overtime_responses'
    
    id = db.Column(db.Integer, primary_key=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey('overtime_opportunities.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    response = db.Column(db.String(20), nullable=False)
    responded_at = db.Column(db.DateTime, default=datetime.now)
    reason = db.Column(db.String(200))
    
    opportunity = db.relationship('OvertimeOpportunity', backref='responses')
    employee = db.relationship('Employee', backref='overtime_responses')

class CoverageGap(db.Model):
    """Track detected coverage gaps for analysis"""
    __tablename__ = 'coverage_gaps'
    
    id = db.Column(db.Integer, primary_key=True)
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    shift_type = db.Column(db.String(20), nullable=False)
    required_count = db.Column(db.Integer, nullable=False)
    scheduled_count = db.Column(db.Integer, nullable=False)
    gap_count = db.Column(db.Integer, nullable=False)
    detected_at = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(20), default='open')
    resolved_at = db.Column(db.DateTime)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    resolution_method = db.Column(db.String(50))
    
    position = db.relationship('Position', backref='coverage_gaps')
    resolved_by = db.relationship('Employee', backref='resolved_gaps')

class EmployeeSkill(db.Model):
    """Track employee skills and certifications"""
    __tablename__ = 'employee_skills_new'  # Different name to avoid conflict
    
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    skill_name = db.Column(db.String(100), nullable=False)
    certification_number = db.Column(db.String(100))
    certified_date = db.Column(db.Date)
    expiry_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)
    
    employee = db.relationship('Employee', backref='employee_skills')
    
    __table_args__ = (
        db.UniqueConstraint('employee_id', 'skill_name', name='_employee_skill_new_uc'),
    )

class FatigueTracking(db.Model):
    """Track employee fatigue indicators for safety"""
    __tablename__ = 'fatigue_tracking'
    
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    consecutive_days = db.Column(db.Integer, default=0)
    hours_last_7_days = db.Column(db.Float, default=0)
    hours_last_14_days = db.Column(db.Float, default=0)
    night_shifts_last_7_days = db.Column(db.Integer, default=0)
    shift_changes_last_7_days = db.Column(db.Integer, default=0)
    fatigue_score = db.Column(db.Float, default=0)
    last_updated = db.Column(db.DateTime, default=datetime.now)
    
    employee = db.relationship('Employee', backref='fatigue_records')
    
    __table_args__ = (
        db.UniqueConstraint('employee_id', 'date', name='_employee_fatigue_date_uc'),
    )

class MandatoryOvertimeLog(db.Model):
    """Log all mandatory overtime assignments for compliance"""
    __tablename__ = 'mandatory_overtime_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    shift_type = db.Column(db.String(20), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.now)
    reason = db.Column(db.Text, nullable=False)
    employees_considered = db.Column(db.Integer)
    seniority_rank = db.Column(db.Integer)
    
    employee = db.relationship('Employee', foreign_keys=[employee_id], backref='mandatory_overtime_assigned')
    assigned_by = db.relationship('Employee', foreign_keys=[assigned_by_id], backref='mandatory_overtime_given')
    position = db.relationship('Position', backref='mandatory_assignments')

class ShiftPattern(db.Model):
    """Define shift patterns for crew rotations"""
    __tablename__ = 'shift_patterns'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    pattern_type = db.Column(db.String(50), nullable=False)
    cycle_days = db.Column(db.Integer, nullable=False)
    pattern_data = db.Column(JSON, nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

class CoverageNotificationResponse(db.Model):
    """Track responses to coverage notifications"""
    __tablename__ = 'coverage_notification_responses'
    
    id = db.Column(db.Integer, primary_key=True)
    notification_id = db.Column(db.Integer, db.ForeignKey('coverage_notification.id'), nullable=False)
    response = db.Column(db.String(20), nullable=False)
    responded_at = db.Column(db.DateTime, default=datetime.now)
    decline_reason = db.Column(db.String(200))
    
    notification = db.relationship('CoverageNotification', backref='notification_responses')

# ==========================================
# NEW SHIFT TRADE MARKETPLACE MODELS
# ==========================================

class ShiftTradePost(db.Model):
    """Posted shifts available for trade in the marketplace"""
    id = db.Column(db.Integer, primary_key=True)
    poster_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    
    # Trade preferences
    preferred_start_date = db.Column(db.Date)
    preferred_end_date = db.Column(db.Date)
    preferred_shift_types = db.Column(db.String(50))  # CSV: "Day,Evening"
    notes = db.Column(db.Text)
    
    # Status tracking
    status = db.Column(db.String(20), default='active')  # active, matched, cancelled, expired
    auto_approve = db.Column(db.Boolean, default=False)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    view_count = db.Column(db.Integer, default=0)
    
    # Relationships
    poster = db.relationship('Employee', foreign_keys=[poster_id], backref='trade_posts')
    schedule = db.relationship('Schedule', backref='trade_post')
    proposals = db.relationship('ShiftTradeProposal', backref='trade_post', lazy='dynamic',
                              cascade='all, delete-orphan')
    
    @property
    def shift_date(self):
        return self.schedule.date if self.schedule else None
    
    @property
    def is_expired(self):
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False

class ShiftTradeProposal(db.Model):
    """Proposals for shift trades"""
    id = db.Column(db.Integer, primary_key=True)
    trade_post_id = db.Column(db.Integer, db.ForeignKey('shift_trade_post.id'), nullable=False)
    proposer_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    proposed_schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    
    # Proposal details
    message = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')  # pending, accepted, rejected, withdrawn
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime)
    
    # Relationships
    proposer = db.relationship('Employee', backref='trade_proposals')
    proposed_schedule = db.relationship('Schedule')

# ==================== OVERTIME TRACKING ====================

class OvertimeHistory(db.Model):
    """Track weekly overtime hours for employees"""
    __tablename__ = 'overtime_history'
    
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    week_start_date = db.Column(db.Date, nullable=False)
    regular_hours = db.Column(db.Float, default=0)
    overtime_hours = db.Column(db.Float, default=0)
    total_hours = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    employee = db.relationship('Employee', backref='overtime_history')
    
    # Unique constraint to prevent duplicate entries
    __table_args__ = (
        db.UniqueConstraint('employee_id', 'week_start_date', name='_employee_week_uc'),
    )

class SkillRequirement(db.Model):
    """Define skill requirements for different shift types"""
    __tablename__ = 'skill_requirements'
    
    id = db.Column(db.Integer, primary_key=True)
    skill_id = db.Column(db.Integer, db.ForeignKey('skill.id'), nullable=False)
    shift_type = db.Column(db.String(50), nullable=False)  # day, evening, night
    minimum_required = db.Column(db.Integer, default=1)
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'))

# Add this to the end of your models.py file, after the SkillRequirement class

class FileUpload(db.Model):
    """Track uploaded files and their processing status"""
    __tablename__ = 'file_uploads'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(50))  # employee_import, schedule_import, etc.
    file_size = db.Column(db.Integer)  # Size in bytes
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    
    # Processing status
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    records_processed = db.Column(db.Integer, default=0)
    records_failed = db.Column(db.Integer, default=0)
    error_details = db.Column(db.Text)
    
    # Relationships
    uploaded_by = db.relationship('Employee', backref='file_uploads')
    
    def __repr__(self):
        return f'<FileUpload {self.filename} - {self.status}>'

# NEW UPLOAD HISTORY MODEL
class UploadHistory(db.Model):
    """Track file upload history with detailed information"""
    __tablename__ = 'upload_history'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500))  # Path to stored file
    upload_type = db.Column(db.String(50))  # employee, overtime, bulk_update
    
    # Upload details
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Processing status
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed, partial
    records_processed = db.Column(db.Integer, default=0)
    records_created = db.Column(db.Integer, default=0)
    records_updated = db.Column(db.Integer, default=0)
    records_skipped = db.Column(db.Integer, default=0)
    records_failed = db.Column(db.Integer, default=0)
    
    # Error tracking
    error_details = db.Column(db.Text)  # JSON string of errors
    warnings = db.Column(db.Text)  # JSON string of warnings
    
    # Completion tracking
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # Additional metadata
    notes = db.Column(db.Text)  # JSON string for additional data
    
    # Relationships
    uploaded_by = db.relationship('Employee', backref='upload_history')
    
    def __repr__(self):
        return f'<UploadHistory {self.filename} - {self.status}>'
    
    @property
    def duration(self):
        """Calculate processing duration"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    @property
    def success_rate(self):
        """Calculate success rate percentage"""
        if self.records_processed > 0:
            successful = self.records_created + self.records_updated
            return round((successful / self.records_processed) * 100, 2)
        return 0
# ==========================================
# ADD THESE TO THE END OF YOUR models.py FILE
# ==========================================

class CommunicationMessage(db.Model):
    """Main communications message model"""
    __tablename__ = 'communication_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(20), nullable=False)  # plantwide, hr, maintenance, hourly
    subject = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), default='normal')  # low, normal, high, urgent
    
    # Sender information
    sender_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Target audience
    target_audience = db.Column(db.String(20), default='all')  # all, department, crew, position, individual
    target_department = db.Column(db.String(50))
    target_crew = db.Column(db.String(1))
    target_position_id = db.Column(db.Integer, db.ForeignKey('position.id'))
    recipient_id = db.Column(db.Integer, db.ForeignKey('employee.id'))  # For individual messages
    
    # Message settings
    expires_at = db.Column(db.DateTime)
    is_pinned = db.Column(db.Boolean, default=False)
    is_archived = db.Column(db.Boolean, default=False)
    
    # Relationships
    sender = db.relationship('Employee', foreign_keys=[sender_id], backref='sent_communications')
    recipient = db.relationship('Employee', foreign_keys=[recipient_id], backref='received_communications')
    target_position = db.relationship('Position', backref='targeted_communications')
    attachments = db.relationship('MessageAttachment', backref='message', cascade='all, delete-orphan')
    read_receipts = db.relationship('MessageReadReceipt', backref='message', cascade='all, delete-orphan')
    
    # Indexes for better query performance
    __table_args__ = (
        db.Index('idx_comm_category_created', 'category', 'created_at'),
        db.Index('idx_comm_sender_created', 'sender_id', 'created_at'),
        db.Index('idx_comm_target', 'target_audience', 'target_department', 'target_crew'),
    )

class MessageReadReceipt(db.Model):
    """Track who has read each message"""
    __tablename__ = 'message_read_receipts'
    
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('communication_messages.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    read_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    employee = db.relationship('Employee', backref='message_read_receipts')
    
    # Ensure each employee can only read a message once
    __table_args__ = (
        db.UniqueConstraint('message_id', 'employee_id', name='_message_employee_uc'),
    )

class MessageAttachment(db.Model):
    """File attachments for messages"""
    __tablename__ = 'message_attachments'
    
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('communication_messages.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class MessageTemplate(db.Model):
    """Reusable message templates"""
    __tablename__ = 'message_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(20), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    created_by = db.relationship('Employee', backref='created_templates')

class MessageCategory(db.Model):
    """Define communication categories and permissions"""
    __tablename__ = 'message_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # plantwide, hr, maintenance, hourly
    display_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50))  # Bootstrap icon class
    color = db.Column(db.String(7))  # Hex color code
    
    # Who can send messages in this category
    require_supervisor = db.Column(db.Boolean, default=False)
    require_department = db.Column(db.String(50))  # Specific department required
    require_position = db.Column(db.String(50))  # Specific position required
    
    is_active = db.Column(db.Boolean, default=True)
