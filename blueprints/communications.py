# blueprints/communications.py
"""
Communications Blueprint - Complete implementation
Handles all company communications (Plantwide, HR, Maintenance, Hourly)
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db, Employee, Position, CommunicationMessage, CommunicationReadReceipt, CommunicationAttachment, MessageTemplate, MessageCategory
from datetime import datetime, timedelta
from sqlalchemy import or_, and_, func
import os
import logging

# Set up logging
logger = logging.getLogger(__name__)

# Create blueprint
communications_bp = Blueprint('communications', __name__, url_prefix='/communications')

# ============================================
# HELPER FUNCTIONS
# ============================================

def allowed_file(filename):
    """Check if file extension is allowed"""
    ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xlsx', 'xls', 'png', 'jpg', 'jpeg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_unread_counts():
    """Get unread message counts for current user"""
    if not current_user.is_authenticated:
        return {'total': 0, 'plantwide': 0, 'hr': 0, 'maintenance': 0, 'hourly': 0}
    
    try:
        # Get all messages targeted to current user
        messages = get_user_messages()
        
        # Count unread by category
        unread = {'plantwide': 0, 'hr': 0, 'maintenance': 0, 'hourly': 0}
        
        for msg in messages:
            if not is_message_read(msg.id, current_user.id):
                if msg.category in unread:
                    unread[msg.category] += 1
        
        unread['total'] = sum(unread.values())
        return unread
    except Exception as e:
        logger.error(f"Error getting unread counts: {e}")
        return {'total': 0, 'plantwide': 0, 'hr': 0, 'maintenance': 0, 'hourly': 0}

def get_user_messages(category=None):
    """Get all messages visible to current user"""
    query = CommunicationMessage.query.filter(
        CommunicationMessage.is_archived == False,
        or_(
            CommunicationMessage.expires_at == None,
            CommunicationMessage.expires_at > datetime.utcnow()
        )
    )
    
    if category:
        query = query.filter(CommunicationMessage.category == category)
    
    # Filter by target audience
    query = query.filter(
        or_(
            CommunicationMessage.target_audience == 'all',
            and_(
                CommunicationMessage.target_audience == 'department',
                CommunicationMessage.target_department == current_user.department
            ),
            and_(
                CommunicationMessage.target_audience == 'crew',
                CommunicationMessage.target_crew == current_user.crew
            ),
            and_(
                CommunicationMessage.target_audience == 'position',
                CommunicationMessage.target_position_id == current_user.position_id
            ),
            and_(
                CommunicationMessage.target_audience == 'individual',
                CommunicationMessage.recipient_id == current_user.id
            )
        )
    )
    
    return query.order_by(
        CommunicationMessage.is_pinned.desc(),
        CommunicationMessage.created_at.desc()
    ).all()

def is_message_read(message_id, employee_id):
    """Check if a message has been read by an employee"""
    return CommunicationReadReceipt.query.filter_by(
        message_id=message_id,
        employee_id=employee_id
    ).first() is not None

def mark_message_read(message_id, employee_id):
    """Mark a message as read by an employee"""
    if not is_message_read(message_id, employee_id):
        receipt = CommunicationReadReceipt(
            message_id=message_id,
            employee_id=employee_id
        )
        db.session.add(receipt)
        db.session.commit()

def can_send_in_category(category):
    """Check if current user can send messages in a category"""
    cat = MessageCategory.query.filter_by(name=category).first()
    if not cat:
        return False
    
    # Supervisors can send to any category
    if current_user.is_supervisor:
        return True
    
    # Check specific requirements
    if cat.require_supervisor:
        return False
    
    if cat.require_department and current_user.department != cat.require_department:
        return False
    
    if cat.require_position and current_user.position.name != cat.require_position:
        return False
    
    return True

# ============================================
# ROUTES
# ============================================

@communications_bp.route('/')
@login_required
def hub():
    """Main communications hub showing all categories"""
    categories = MessageCategory.query.filter_by(is_active=True).all()
    unread = get_unread_counts()
    
    # Get recent messages for each category
    recent_messages = {}
    for cat in categories:
        messages = get_user_messages(cat.name)[:3]
        recent_messages[cat.name] = messages
    
    return render_template('communications_hub.html',
                         categories=categories,
                         unread=unread,
                         recent_messages=recent_messages)

@communications_bp.route('/category/<category>')
@login_required
def category_view(category):
    """View all messages in a specific category"""
    # Validate category
    cat = MessageCategory.query.filter_by(name=category).first()
    if not cat:
        flash('Invalid category', 'error')
        return redirect(url_for('communications.hub'))
    
    # Get filters
    priority = request.args.get('priority')
    search = request.args.get('search')
    
    # Get messages
    messages = get_user_messages(category)
    
    # Apply filters
    if priority:
        messages = [m for m in messages if m.priority == priority]
    
    if search:
        search_lower = search.lower()
        messages = [m for m in messages if search_lower in m.subject.lower() or search_lower in m.content.lower()]
    
    # Mark messages as read for current page
    for msg in messages[:10]:  # Only mark first page as read
        mark_message_read(msg.id, current_user.id)
    
    return render_template('communications_category.html',
                         category=cat,
                         messages=messages,
                         can_send=can_send_in_category(category))

@communications_bp.route('/message/<int:message_id>')
@login_required
def view_message(message_id):
    """View a single message"""
    message = CommunicationMessage.query.get_or_404(message_id)
    
    # Check if user can view this message
    messages = get_user_messages()
    if message not in messages:
        flash('You do not have permission to view this message', 'error')
        return redirect(url_for('communications.hub'))
    
    # Mark as read
    mark_message_read(message_id, current_user.id)
    
    # Get read receipts if sender
    read_receipts = []
    if message.sender_id == current_user.id:
        read_receipts = CommunicationReadReceipt.query.filter_by(message_id=message_id).all()
    
    return render_template('communications_message.html',
                         message=message,
                         read_receipts=read_receipts)

@communications_bp.route('/compose', methods=['GET', 'POST'])
@login_required
def compose():
    """Compose a new message"""
    if request.method == 'POST':
        try:
            category = request.form.get('category')
            
            # Check permissions
            if not can_send_in_category(category):
                flash('You do not have permission to send messages in this category', 'error')
                return redirect(url_for('communications.compose'))
            
            # Create message
            message = CommunicationMessage(
                category=category,
                subject=request.form.get('subject'),
                content=request.form.get('content'),
                priority=request.form.get('priority', 'normal'),
                sender_id=current_user.id,
                target_audience=request.form.get('target_audience', 'all')
            )
            
            # Set target specifics
            if message.target_audience == 'department':
                message.target_department = request.form.get('target_department')
            elif message.target_audience == 'crew':
                message.target_crew = request.form.get('target_crew')
            elif message.target_audience == 'position':
                message.target_position_id = request.form.get('target_position_id')
            elif message.target_audience == 'individual':
                message.recipient_id = request.form.get('recipient_id')
            
            # Set expiration
            expires_in = request.form.get('expires_in')
            if expires_in and expires_in != 'never':
                days = int(expires_in)
                message.expires_at = datetime.utcnow() + timedelta(days=days)
            
            # Handle file attachments
            if 'attachments' in request.files:
                files = request.files.getlist('attachments')
                for file in files:
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        # Save file logic here
                        attachment = CommunicationAttachment(
                            filename=filename,
                            original_filename=file.filename,
                            file_size=len(file.read())
                        )
                        file.seek(0)  # Reset file pointer
                        message.attachments.append(attachment)
            
            db.session.add(message)
            db.session.commit()
            
            flash('Message sent successfully!', 'success')
            return redirect(url_for('communications.view_message', message_id=message.id))
            
        except Exception as e:
            logger.error(f"Error composing message: {e}")
            db.session.rollback()
            flash('Error sending message. Please try again.', 'error')
    
    # Get data for form
    categories = MessageCategory.query.filter_by(is_active=True).all()
    departments = db.session.query(Employee.department).distinct().all()
    positions = Position.query.all()
    templates = MessageTemplate.query.filter_by(created_by_id=current_user.id).all()
    
    # Filter categories user can send to
    sendable_categories = [cat for cat in categories if can_send_in_category(cat.name)]
    
    return render_template('communications_compose.html',
                         categories=sendable_categories,
                         departments=[d[0] for d in departments if d[0]],
                         positions=positions,
                         templates=templates)

@communications_bp.route('/analytics')
@login_required
def analytics():
    """View message analytics (supervisors only)"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'error')
        return redirect(url_for('communications.hub'))
    
    # Get date range
    days = int(request.args.get('days', 30))
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Messages by category
    category_stats = db.session.query(
        CommunicationMessage.category,
        func.count(CommunicationMessage.id).label('count')
    ).filter(
        CommunicationMessage.created_at >= start_date
    ).group_by(CommunicationMessage.category).all()
    
    # Messages by priority
    priority_stats = db.session.query(
        CommunicationMessage.priority,
        func.count(CommunicationMessage.id).label('count')
    ).filter(
        CommunicationMessage.created_at >= start_date
    ).group_by(CommunicationMessage.priority).all()
    
    # Top senders
    top_senders = db.session.query(
        Employee.name,
        func.count(CommunicationMessage.id).label('count')
    ).join(
        CommunicationMessage, CommunicationMessage.sender_id == Employee.id
    ).filter(
        CommunicationMessage.created_at >= start_date
    ).group_by(Employee.name).order_by(
        func.count(CommunicationMessage.id).desc()
    ).limit(10).all()
    
    # Read rates by category
    read_rates = {}
    for cat in MessageCategory.query.all():
        messages = CommunicationMessage.query.filter_by(
            category=cat.name
        ).filter(
            CommunicationMessage.created_at >= start_date
        ).all()
        
        if messages:
            total_recipients = 0
            total_reads = 0
            
            for msg in messages:
                # Estimate recipients based on target
                if msg.target_audience == 'all':
                    recipients = Employee.query.count()
                elif msg.target_audience == 'crew':
                    recipients = Employee.query.filter_by(crew=msg.target_crew).count()
                elif msg.target_audience == 'department':
                    recipients = Employee.query.filter_by(department=msg.target_department).count()
                else:
                    recipients = 1
                
                reads = CommunicationReadReceipt.query.filter_by(message_id=msg.id).count()
                total_recipients += recipients
                total_reads += reads
            
            read_rates[cat.name] = (total_reads / total_recipients * 100) if total_recipients > 0 else 0
    
    return render_template('communications_analytics.html',
                         category_stats=category_stats,
                         priority_stats=priority_stats,
                         top_senders=top_senders,
                         read_rates=read_rates,
                         days=days)

@communications_bp.route('/api/mark-read/<int:message_id>', methods=['POST'])
@login_required
def api_mark_read(message_id):
    """API endpoint to mark message as read"""
    try:
        mark_message_read(message_id, current_user.id)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error marking message read: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@communications_bp.route('/api/delete/<int:message_id>', methods=['POST'])
@login_required
def api_delete_message(message_id):
    """API endpoint to delete/archive a message"""
    message = CommunicationMessage.query.get_or_404(message_id)
    
    # Only sender or supervisor can delete
    if message.sender_id != current_user.id and not current_user.is_supervisor:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    
    try:
        message.is_archived = True
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting message: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@communications_bp.route('/templates/save', methods=['POST'])
@login_required
def save_template():
    """Save a message as template"""
    try:
        template = MessageTemplate(
            name=request.form.get('template_name'),
            category=request.form.get('category'),
            subject=request.form.get('subject'),
            content=request.form.get('content'),
            created_by_id=current_user.id
        )
        db.session.add(template)
        db.session.commit()
        
        return jsonify({'success': True, 'template_id': template.id})
    except Exception as e:
        logger.error(f"Error saving template: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
