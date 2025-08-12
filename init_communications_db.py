# Add these models to your existing models.py file

# ==========================================
# COMMUNICATIONS SYSTEM MODELS
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
    
    def __repr__(self):
        return f'<CommunicationMessage {self.id}: {self.subject}>'

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
    
    def __repr__(self):
        return f'<MessageReadReceipt Message:{self.message_id} Employee:{self.employee_id}>'

class MessageAttachment(db.Model):
    """File attachments for messages"""
    __tablename__ = 'message_attachments'
    
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('communication_messages.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<MessageAttachment {self.id}: {self.original_filename}>'

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
    
    def __repr__(self):
        return f'<MessageTemplate {self.id}: {self.name}>'

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
    
    def __repr__(self):
        return f'<MessageCategory {self.name}>'
