# models.py - Complete Database Models
"""
Complete database models for Workforce Scheduler
Fixed to match actual database schema
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from sqlalchemy import event
from sqlalchemy.sql import func
import enum

db = SQLAlchemy()

# Enums
class ShiftType(enum.Enum):
    DAY = "day"
    EVENING = "evening"
    NIGHT = "night"

class TimeOffType(enum.Enum):
    VACATION = "vacation"
    SICK = "sick"
    PERSONAL = "personal"
    OTHER = "other"

class TimeOffStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    CANCELLED = "cancelled"

# ==========================================
# EMPLOYEE & AUTH MODELS
# ==========================================

class Employee(UserMixin, db.Model):
    """Core employee model with authentication"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255))
    
    # Personal Info
    name = db.Column(db.String(100), nullable=False)
    employee_id = db.Column(db.String(50), unique=True)
    phone = db.Column(db.String(20))
    
    # Work Info
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'))
    department = db.Column(db.String(50))
    crew = db.Column(db.String(1))  # A, B, C, or D
    is_supervisor = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)  # CRITICAL: This fixes the login issue
    hire_date = db.Column(db.Date)
    
    # Availability
    is_active = db.Column(db.Boolean, default=True)
    max_hours_per_week = db.Column(db.Integer, default=48)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships defined via backref in other models
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    @property
    def current_overtime_hours(self):
        """Get overtime hours for current period"""
        if hasattr(self, 'overtime_histories'):
            current = self.overtime_histories.filter_by(is_current=True).first()
            return current.total_hours if current else 0
        return 0
    
    @property
    def average_overtime_hours(self):
        """Get 13-week average overtime"""
        if hasattr(self, 'overtime_histories'):
            histories = self.overtime_histories.limit(13).all()
            if histories:
                return sum(h.total_hours for h in histories) / len(histories)
        return 0

class Position(db.Model):
    """Job positions/roles - FIXED to match actual database schema"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    department = db.Column(db.String(50))
    min_coverage = db.Column(db.Integer, default=1)
    
    # These columns exist in your database but weren't in the model
    skills_required = db.Column(db.Text)
    requires_coverage = db.Column(db.Boolean, default=True)
    critical_position = db.Column(db.Boolean, default=False)
    default_skills = db.Column(db.Text)
    
    # Relationships
    employees = db.relationship('Employee', backref='position', lazy='dynamic')
    
    def __repr__(self):
        return f'<Position {self.name}>'
    
    def get_required_skills(self):
        """Get list of required skills"""
        if self.skills_required:
            return [s.strip() for s in self.skills_required.split(',')]
        return []
    
    def get_default_skills(self):
        """Get list of default skills"""
        if self.default_skills:
            return [s.strip() for s in self.default_skills.split(',')]
        return []
    
class Skill(db.Model):
    """Employee skills and certifications"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    category = db.Column(db.String(50))
    requires_renewal = db.Column(db.Boolean, default=False)
    renewal_period_days = db.Column(db.Integer)
    
class EmployeeSkill(db.Model):
    """Many-to-many relationship for employee skills"""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey('skill.id'), nullable=False)
    certified_date = db.Column(db.Date)
    expiry_date = db.Column(db.Date)
    
    # Relationships
    employee = db.relationship('Employee', backref='employee_skills')
    skill = db.relationship('Skill', backref='certified_employees')

# ==========================================
# SCHEDULE & TIME-OFF MODELS
# ==========================================

class Schedule(db.Model):
    """Daily schedule entries"""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    shift_type = db.Column(db.Enum(ShiftType), nullable=False)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    
    # Status
    is_overtime = db.Column(db.Boolean, default=False)
    is_training = db.Column(db.Boolean, default=False)
    
    # Relationships
    employee = db.relationship('Employee', backref='schedules')
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('employee_id', 'date', name='_employee_date_uc'),
    )

class TimeOffRequest(db.Model):
    """Employee time-off requests"""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    
    # Request details
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    type = db.Column(db.Enum(TimeOffType), nullable=False)
    request_type = db.Column(db.String(50), default='vacation')  # Added for compatibility
    reason = db.Column(db.Text)
    
    # Status
    status = db.Column(db.Enum(TimeOffStatus), default=TimeOffStatus.PENDING)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    
    # Timestamps
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Added for compatibility
    processed_at = db.Column(db.DateTime)
    approved_date = db.Column(db.DateTime)  # Added for compatibility
    
    # Relationships
    employee = db.relationship('Employee', foreign_keys=[employee_id], backref='time_off_requests')
    approved_by = db.relationship('Employee', foreign_keys=[approved_by_id])

class VacationCalendar(db.Model):
    """Track approved vacation days"""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    request_id = db.Column(db.Integer, db.ForeignKey('time_off_request.id'))  # Added for linking
    type = db.Column(db.String(20), default='vacation')
    status = db.Column(db.String(20), default='approved')
    
    # Relationships
    employee = db.relationship('Employee', backref='vacation_days')
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('employee_id', 'date', name='_employee_vacation_date_uc'),
    )

# ==========================================
# SHIFT SWAP & TRADE MODELS
# ==========================================

class ShiftSwapRequest(db.Model):
    """Shift swap requests between employees"""
    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    target_employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    
    # Shift details
    requester_date = db.Column(db.Date, nullable=False)
    requester_shift = db.Column(db.String(20), nullable=False)  # Changed from Enum to String
    target_date = db.Column(db.Date)
    target_shift = db.Column(db.String(20))  # Changed from Enum to String
    
    # Status
    status = db.Column(db.String(20), default='pending')
    reason = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    
    # Relationships
    requester = db.relationship('Employee', foreign_keys=[requester_id], backref='swap_requests_made')
    target_employee = db.relationship('Employee', foreign_keys=[target_employee_id], backref='swap_requests_received')

class ShiftTradePost(db.Model):
    """Marketplace for shift trades"""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    
    # Shift being offered
    shift_date = db.Column(db.Date, nullable=False)
    shift_type = db.Column(db.Enum(ShiftType), nullable=False)
    
    # Trade preferences
    preferred_dates = db.Column(db.JSON)  # List of acceptable dates
    notes = db.Column(db.Text)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    traded_with_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    
    # Timestamps
    posted_at = db.Column(db.DateTime, default=datetime.utcnow)
    traded_at = db.Column(db.DateTime)
    
    # Relationships
    employee = db.relationship('Employee', foreign_keys=[employee_id], backref='trade_posts')
    traded_with = db.relationship('Employee', foreign_keys=[traded_with_id])

# ==========================================
# OVERTIME & COVERAGE MODELS
# ==========================================

class OvertimeHistory(db.Model):
    """13-week rolling overtime history"""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    week_ending = db.Column(db.Date, nullable=False)
    week_start_date = db.Column(db.Date)  # Added for compatibility
    regular_hours = db.Column(db.Float, default=0)  # Added
    overtime_hours = db.Column(db.Float, default=0)  # Added  
    total_hours = db.Column(db.Float, default=0)  # Added
    hours = db.Column(db.Float, default=0)  # Kept for backward compatibility
    is_current = db.Column(db.Boolean, default=False)
    
    # Relationships
    employee = db.relationship('Employee', backref=db.backref('overtime_histories', lazy='dynamic'))
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('employee_id', 'week_ending', name='_employee_week_uc'),
    )

class CoverageGap(db.Model):
    """Identified coverage gaps"""
    id = db.Column(db.Integer, primary_key=True)
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    shift_type = db.Column(db.Enum(ShiftType), nullable=False)
    required_count = db.Column(db.Integer, default=1)
    scheduled_count = db.Column(db.Integer, default=0)
    
    # Status
    is_filled = db.Column(db.Boolean, default=False)
    filled_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    
    # Relationships
    position = db.relationship('Position', backref='coverage_gaps')
    filled_by = db.relationship('Employee')

# ==========================================
# MESSAGING & COMMUNICATION MODELS
# ==========================================

class SupervisorMessage(db.Model):
    """Messages from supervisors to employees"""
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    
    # Message content
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), default='normal')
    
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
    
    # Target specific shifts or crews
    target_shifts = db.Column(db.JSON)  # ['day', 'evening', 'night'] or None for all
    
    # Visibility
    crew_specific = db.Column(db.Boolean, default=False)
    target_crew = db.Column(db.String(1))  # If crew_specific, which crew
    
    # Metadata
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)  # Optional expiration
    
    # Relationships
    sender = db.relationship('Employee', backref='position_messages_sent')
    position = db.relationship('Position', backref='messages')
    read_receipts = db.relationship('PositionMessageReadReceipt', backref='position_message', 
                                   cascade='all, delete-orphan')
    
    def is_read_by(self, employee_id):
        """Check if message was read by specific employee"""
        return any(r.employee_id == employee_id for r in self.read_receipts)

class PositionMessageReadReceipt(db.Model):
    """Track who has read position messages"""
    __tablename__ = 'position_message_read_receipt'
    
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('position_message.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    read_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    employee = db.relationship('Employee', backref='position_message_read_receipts')
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('message_id', 'employee_id', name='_position_message_employee_uc'),
    )

# ==========================================
# NEW COMMUNICATIONS SYSTEM MODELS
# ==========================================

class CommunicationCategory(db.Model):
    """Categories for the new communications system"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50))  # Bootstrap icon name
    color = db.Column(db.String(20))  # Bootstrap color class
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    messages = db.relationship('CommunicationMessage', backref='category', lazy='dynamic')

class CommunicationMessage(db.Model):
    """Messages in the new communications system"""
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('communication_category.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    
    # Content
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), default='normal')  # low, normal, high, urgent
    
    # Visibility
    is_pinned = db.Column(db.Boolean, default=False)
    is_archived = db.Column(db.Boolean, default=False)
    requires_acknowledgment = db.Column(db.Boolean, default=False)
    
    # Target audience
    target_all = db.Column(db.Boolean, default=True)
    target_crews = db.Column(db.JSON)  # ['A', 'B', 'C', 'D'] or None for all
    target_departments = db.Column(db.JSON)  # List of departments or None
    target_positions = db.Column(db.JSON)  # List of position IDs or None
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = db.Column(db.DateTime)  # Optional expiration
    
    # Relationships
    author = db.relationship('Employee', backref='communication_messages')
    read_receipts = db.relationship('CommunicationReadReceipt', backref='message', cascade='all, delete-orphan')
    attachments = db.relationship('CommunicationAttachment', backref='message', cascade='all, delete-orphan')
    
    def is_read_by(self, employee_id):
        """Check if message was read by specific employee"""
        return any(r.employee_id == employee_id for r in self.read_receipts)
    
    def is_acknowledged_by(self, employee_id):
        """Check if message was acknowledged by specific employee"""
        return any(r.employee_id == employee_id and r.acknowledged for r in self.read_receipts)

class CommunicationReadReceipt(db.Model):
    """Track reads and acknowledgments for communication messages"""
    __tablename__ = 'communication_read_receipt'
    
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('communication_message.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    read_at = db.Column(db.DateTime, default=datetime.utcnow)
    acknowledged = db.Column(db.Boolean, default=False)
    acknowledged_at = db.Column(db.DateTime)
    
    # Relationships
    employee = db.relationship('Employee', backref='communication_read_receipts')
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('message_id', 'employee_id', name='_communication_message_employee_uc'),
    )

class CommunicationAttachment(db.Model):
    """File attachments for communication messages"""
    __tablename__ = 'communication_attachment'
    
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('communication_message.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500))
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(100))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

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
# HEALTH & SAFETY MODELS
# ==========================================

class CircadianProfile(db.Model):
    """Track employee circadian rhythm preferences"""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), unique=True, nullable=False)
    chronotype = db.Column(db.String(20))  # morning, evening, flexible
    preferred_shift = db.Column(db.Enum(ShiftType))
    shift_adaptability = db.Column(db.Integer)  # 1-10 scale
    
    # Sleep patterns
    typical_bedtime = db.Column(db.Time)
    typical_waketime = db.Column(db.Time)
    minimum_hours_between_shifts = db.Column(db.Integer, default=8)
    
    # Relationships
    employee = db.relationship('Employee', backref=db.backref('circadian_profile', uselist=False))

class SleepLog(db.Model):
    """Employee self-reported sleep tracking"""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    
    # Sleep data
    hours_slept = db.Column(db.Float)
    quality = db.Column(db.Integer)  # 1-5 scale
    pre_shift_fatigue = db.Column(db.Integer)  # 1-10 scale
    post_shift_fatigue = db.Column(db.Integer)  # 1-10 scale
    
    # Relationships
    employee = db.relationship('Employee', backref='sleep_logs')

# ==========================================
# CASUAL WORKERS & MISC MODELS
# ==========================================

class CasualWorker(db.Model):
    """Pool of casual/on-call workers"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True)
    phone = db.Column(db.String(20))
    
    # Availability
    available_shifts = db.Column(db.JSON)  # {'monday': ['day', 'evening'], ...}
    max_shifts_per_week = db.Column(db.Integer, default=3)
    
    # Skills
    qualified_positions = db.Column(db.JSON)  # List of position IDs
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    last_worked = db.Column(db.Date)
    rating = db.Column(db.Float)  # Average rating from supervisors
    
    # Timestamps
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

class CoverageRequest(db.Model):
    """Requests for coverage (sick calls, emergencies)"""
    id = db.Column(db.Integer, primary_key=True)
    shift_date = db.Column(db.Date, nullable=False)
    shift_type = db.Column(db.Enum(ShiftType), nullable=False)
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'), nullable=False)
    reason = db.Column(db.Text)
    
    # Status
    status = db.Column(db.String(20), default='open')  # open, filled, cancelled
    filled_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    is_emergency = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    filled_at = db.Column(db.DateTime)
    
    # Relationships
    position = db.relationship('Position')
    filled_by = db.relationship('Employee')

class FileUpload(db.Model):
    """Track file uploads (employee imports, etc.)"""
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    upload_type = db.Column(db.String(50))  # employee_import, overtime_import, etc.
    file_type = db.Column(db.String(50))  # Added for compatibility
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    
    # Results
    total_records = db.Column(db.Integer, default=0)
    successful_records = db.Column(db.Integer, default=0)
    failed_records = db.Column(db.Integer, default=0)
    records_processed = db.Column(db.Integer, default=0)  # Added
    records_failed = db.Column(db.Integer, default=0)  # Added
    error_details = db.Column(db.JSON)
    status = db.Column(db.String(20), default='pending')  # Added
    
    # File info
    file_path = db.Column(db.String(500))  # Added
    file_size = db.Column(db.Integer)  # Added
    
    # Timestamps
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    uploaded_by = db.relationship('Employee')

# Additional models for other features...
class CrewCoverageRequirement(db.Model):
    """Define minimum coverage requirements per crew/shift/position"""
    id = db.Column(db.Integer, primary_key=True)
    crew = db.Column(db.String(1), nullable=False)
    shift_type = db.Column(db.Enum(ShiftType), nullable=False)
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'), nullable=False)
    minimum_count = db.Column(db.Integer, default=1)
    preferred_count = db.Column(db.Integer, default=1)
    
    # Relationships
    position = db.relationship('Position')
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('crew', 'shift_type', 'position_id', name='_crew_shift_position_uc'),
    )

class Availability(db.Model):
    """Employee availability preferences"""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    day_of_week = db.Column(db.Integer)  # 0=Monday, 6=Sunday
    shift_type = db.Column(db.Enum(ShiftType))
    is_available = db.Column(db.Boolean, default=True)
    preference_level = db.Column(db.Integer, default=3)  # 1=strongly avoid, 5=strongly prefer
    
    # Relationships
    employee = db.relationship('Employee', backref='availability_preferences')

# Additional placeholder models to prevent import errors
class ShiftPattern(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))

class OvertimeOpportunity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date)
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'))
    hours = db.Column(db.Float)
    status = db.Column(db.String(20), default='open')

class OvertimeResponse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    opportunity_id = db.Column(db.Integer)

class PositionCoverage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    position_id = db.Column(db.Integer)

class FatigueTracking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer)

class MandatoryOvertimeLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer)

class CoverageNotification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer)

class CoverageNotificationResponse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    notification_id = db.Column(db.Integer)

class ShiftTradeProposal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer)

class ShiftTrade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    proposal_id = db.Column(db.Integer)

class UploadHistory(db.Model):
    """Track history of Excel uploads"""
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    upload_type = db.Column(db.String(50), nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    
    # Processing details
    total_rows = db.Column(db.Integer, default=0)
    processed_rows = db.Column(db.Integer, default=0)
    error_rows = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='pending')
    
    # Additional info
    file_path = db.Column(db.String(500))
    error_log = db.Column(db.JSON)
    upload_metadata = db.Column(db.JSON)
    
    # Timestamps
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    # Relationships
    uploaded_by = db.relationship('Employee', backref='upload_history')
    
    @property
    def success_rate(self):
        if self.total_rows == 0:
            return 0
        return (self.processed_rows / self.total_rows) * 100

class SkillRequirement(db.Model):
    """Skills required for positions"""
    id = db.Column(db.Integer, primary_key=True)
    position_id = db.Column(db.Integer, db.ForeignKey('position.id'), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey('skill.id'), nullable=False)
    is_mandatory = db.Column(db.Boolean, default=True)
    
    # Relationships
    position = db.relationship('Position', backref='skill_requirements')
    skill = db.relationship('Skill', backref='position_requirements')

class MaintenanceUpdate(db.Model):
    """Updates/progress on maintenance issues"""
    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(db.Integer, db.ForeignKey('maintenance_issue.id'), nullable=False)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    update_text = db.Column(db.Text, nullable=False)
    status_change = db.Column(db.String(50))  # If status was changed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    issue = db.relationship('MaintenanceIssue', backref='updates')
    updated_by = db.relationship('Employee', backref='maintenance_updates')

# Add this placeholder model if referenced anywhere
class ScheduleSuggestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    date = db.Column(db.Date)
    suggestion_type = db.Column(db.String(50))

# Add read receipt model if not present
class MessageReadReceipt(db.Model):
    """Generic message read receipts"""
    id = db.Column(db.Integer, primary_key=True)
    message_type = db.Column(db.String(50))
    message_id = db.Column(db.Integer)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    read_at = db.Column(db.DateTime, default=datetime.utcnow)
