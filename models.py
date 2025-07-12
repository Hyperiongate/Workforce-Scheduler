from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

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
    
    # Time off balances
    vacation_days = db.Column(db.Float, default=10.0)
    sick_days = db.Column(db.Float, default=5.0)
    personal_days = db.Column(db.Float, default=3.0)
    
    # Relationships
    position = db.relationship('Position', backref='employees')
    skills = db.relationship('Skill', secondary=employee_skills, backref='employees')
    schedules = db.relationship('Schedule', backref='employee', lazy='dynamic')
    availability = db.relationship('Availability', backref='employee', lazy='dynamic')
    time_off_requests = db.relationship('TimeOffRequest', backref='employee', lazy='dynamic')
    coverage_requests = db.relationship('CoverageRequest', backref='requester', lazy='dynamic', 
                                      foreign_keys='CoverageRequest.requester_id')
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

class Position(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(50))
    min_coverage = db.Column(db.Integer, default=1)  # Minimum people needed
    
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
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'))
    hours = db.Column(db.Float)
    is_overtime = db.Column(db.Boolean, default=False)
    crew = db.Column(db.String(1))  # A, B, C, or D
    status = db.Column(db.String(20), default='scheduled')  # scheduled, worked, absent, covered
    
    # Relationships
    position = db.relationship('Position', backref='schedules')
    
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
    submitted_date = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_date = db.Column(db.DateTime)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    reviewer_notes = db.Column(db.Text)
    days_requested = db.Column(db.Float)
    
    # Relationships
    reviewed_by = db.relationship('Employee', foreign_keys=[reviewed_by_id])

class VacationCalendar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    request_id = db.Column(db.Integer, db.ForeignKey('time_off_request.id'))
    type = db.Column(db.String(20))  # vacation, sick, personal, holiday
    
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
    original_schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    target_employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    target_schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'))
    reason = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')  # pending, approved, denied
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Dual supervisor approval
    requester_supervisor_approved = db.Column(db.Boolean)
    requester_supervisor_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    requester_supervisor_date = db.Column(db.DateTime)
    
    target_supervisor_approved = db.Column(db.Boolean)
    target_supervisor_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    target_supervisor_date = db.Column(db.DateTime)
    
    # Relationships
    requester = db.relationship('Employee', foreign_keys=[requester_id], 
                               backref='swap_requests_made')
    target_employee = db.relationship('Employee', foreign_keys=[target_employee_id], 
                                    backref='swap_requests_received')
    original_schedule = db.relationship('Schedule', foreign_keys=[original_schedule_id])
    target_schedule = db.relationship('Schedule', foreign_keys=[target_schedule_id])
    requester_supervisor = db.relationship('Employee', foreign_keys=[requester_supervisor_id])
    target_supervisor = db.relationship('Employee', foreign_keys=[target_supervisor_id])

class ScheduleSuggestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    suggestion_type = db.Column(db.String(50))  # shift_preference, availability_change, etc.
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), default='medium')  # low, medium, high
    status = db.Column(db.String(20), default='new')  # new, reviewed, implemented, declined
    submitted_date = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_date = db.Column(db.DateTime)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    response = db.Column(db.Text)
    
    # Relationships
    employee = db.relationship('Employee', foreign_keys=[employee_id], 
                             backref='suggestions_made')
    reviewed_by = db.relationship('Employee', foreign_keys=[reviewed_by_id])

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
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    priority = db.Column(db.String(20))  # critical, high, medium, low
    action_items = db.Column(db.Text)  # JSON list
    
    # Timing
    valid_from = db.Column(db.DateTime, default=datetime.utcnow)
    valid_until = db.Column(db.DateTime)
    
    # Tracking
    is_active = db.Column(db.Boolean, default=True)
    acknowledged = db.Column(db.Boolean, default=False)
    acknowledged_date = db.Column(db.DateTime)
    
    # Relationships
    employee = db.relationship('Employee', backref='sleep_recommendations')

class ShiftTransitionPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    from_shift_type = db.Column(db.String(20))
    to_shift_type = db.Column(db.String(20))
    transition_start_date = db.Column(db.Date)
    transition_end_date = db.Column(db.Date)
    
    # Daily adjustment plan (JSON)
    daily_adjustments = db.Column(db.Text)
    
    # Progress tracking
    current_day = db.Column(db.Integer, default=0)
    completion_percentage = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    # Relationships
    employee = db.relationship('Employee', backref='transition_plans')

# Coverage & Overtime Models
class CoverageNotification(db.Model):
    """Notifications sent to employees about coverage opportunities"""
    id = db.Column(db.Integer, primary_key=True)
    coverage_request_id = db.Column(db.Integer, db.ForeignKey('coverage_request.id'))
    sent_to_type = db.Column(db.String(20))  # crew, supervisor, individual
    sent_to_crew = db.Column(db.String(1))  # A, B, C, or D
    sent_to_employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    sent_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    
    message = db.Column(db.Text)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime)
    responded_at = db.Column(db.DateTime)
    response = db.Column(db.String(20))  # accepted, declined, no_response
    
    # Relationships
    coverage_request = db.relationship('CoverageRequest', backref='notifications')
    sent_to_employee = db.relationship('Employee', foreign_keys=[sent_to_employee_id])
    sent_by = db.relationship('Employee', foreign_keys=[sent_by_id])

class OvertimeOpportunity(db.Model):
    """Track overtime opportunities that need to be filled"""
    id = db.Column(db.Integer, primary_key=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'))
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'))
    date = db.Column(db.Date, nullable=False)
    shift_type = db.Column(db.String(20))
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    hours = db.Column(db.Float)
    positions_needed = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default='open')  # open, partially_filled, filled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    schedule = db.relationship('Schedule', backref='overtime_opportunity')
    position = db.relationship('Position', backref='overtime_opportunities')

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
    def shift_type(self):
        return self.schedule.shift_type if self.schedule else None
    
    @property
    def start_time(self):
        return self.schedule.start_time if self.schedule else None
    
    @property
    def end_time(self):
        return self.schedule.end_time if self.schedule else None
    
    @property
    def position(self):
        return self.schedule.position if self.schedule else None
    
    @property
    def required_skills(self):
        return self.position.required_skills if self.position else []

class ShiftTradeProposal(db.Model):
    """Proposals for shift trades"""
    id = db.Column(db.Integer, primary_key=True)
    trade_post_id = db.Column(db.Integer, db.ForeignKey('shift_trade_post.id'), nullable=False)
    proposer_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    offered_schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    
    # Communication
    message = db.Column(db.Text)
    
    # Status
    status = db.Column(db.String(20), default='pending')  # pending, accepted, rejected, withdrawn
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime)
    
    # Relationships
    proposer = db.relationship('Employee', foreign_keys=[proposer_id], backref='trade_proposals')
    offered_schedule = db.relationship('Schedule', backref='trade_proposals')

class ShiftTrade(db.Model):
    """Completed or in-progress shift trades"""
    id = db.Column(db.Integer, primary_key=True)
    
    # Trade participants
    employee1_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    employee2_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    
    # Schedules being traded
    schedule1_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    schedule2_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    
    # Origin tracking
    trade_post_id = db.Column(db.Integer, db.ForeignKey('shift_trade_post.id'))
    trade_proposal_id = db.Column(db.Integer, db.ForeignKey('shift_trade_proposal.id'))
    
    # Status and approval
    status = db.Column(db.String(20), default='pending')  # pending, approved, completed, cancelled
    requires_approval = db.Column(db.Boolean, default=True)
    
    # Supervisor approvals (similar to ShiftSwapRequest)
    employee1_supervisor_approved = db.Column(db.Boolean)
    employee1_supervisor_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    employee1_supervisor_date = db.Column(db.DateTime)
    employee1_supervisor_notes = db.Column(db.Text)
    
    employee2_supervisor_approved = db.Column(db.Boolean)
    employee2_supervisor_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    employee2_supervisor_date = db.Column(db.DateTime)
    employee2_supervisor_notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    # Relationships
    employee1 = db.relationship('Employee', foreign_keys=[employee1_id], 
                               backref='trades_as_employee1')
    employee2 = db.relationship('Employee', foreign_keys=[employee2_id], 
                               backref='trades_as_employee2')
    schedule1 = db.relationship('Schedule', foreign_keys=[schedule1_id])
    schedule2 = db.relationship('Schedule', foreign_keys=[schedule2_id])
    trade_post = db.relationship('ShiftTradePost', backref='completed_trades')
    trade_proposal = db.relationship('ShiftTradeProposal', backref='completed_trade')
    employee1_supervisor = db.relationship('Employee', foreign_keys=[employee1_supervisor_id])
    employee2_supervisor = db.relationship('Employee', foreign_keys=[employee2_supervisor_id])
    
    @property
    def other_employee(self):
        """Get the other employee in the trade from perspective of current user"""
        from flask_login import current_user
        if current_user.id == self.employee1_id:
            return self.employee2
        return self.employee1
    
    @property
    def offered_shift(self):
        """Get the shift being offered by current user"""
        from flask_login import current_user
        if current_user.id == self.employee1_id:
            return self.schedule1
        return self.schedule2
    
    @property
    def requested_shift(self):
        """Get the shift being requested by current user"""
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
