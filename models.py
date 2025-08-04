# ADD THESE TO YOUR EXISTING models.py FILE

# 1. Add these fields to your Employee class (inside the class, after existing fields):

    # Authentication fields (ADD THESE IF MISSING)
    username = db.Column(db.String(50), unique=True, nullable=True, index=True)
    
    # Account status fields (ADD THESE)
    must_change_password = db.Column(db.Boolean, default=True)
    first_login = db.Column(db.Boolean, default=True)
    account_active = db.Column(db.Boolean, default=True)
    
    # Account tracking (ADD THESE)
    account_created_date = db.Column(db.DateTime, nullable=True)
    last_password_change = db.Column(db.DateTime, nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)
    login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    
    # Password reset (ADD THESE)
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)

# 2. Add these methods to your Employee class (inside the class, after existing methods):
    
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

# 3. Add this complete class at the END of your models.py file (NO INDENTATION):

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
