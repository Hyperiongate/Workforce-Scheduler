# blueprints/communications.py
"""
Communications Blueprint - Comprehensive messaging system
Handles Plantwide, HR, Maintenance, and Hourly Employee communications
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, current_app
from flask_login import login_required, current_user
from models import db, Employee, Position, MessageCategory, CommunicationMessage, MessageReadReceipt, MessageAttachment, MessageTemplate
from datetime import datetime, date, timedelta
from sqlalchemy import func, or_, and_, desc
from werkzeug.utils import secure_filename
import os
import logging

# Set up logging
logger = logging.getLogger(__name__)

# Create blueprint
communications_bp = Blueprint('communications', __name__)

# ============================================
# HELPER FUNCTIONS
# ============================================

def get_user_communication_permissions():
    """Get the current user's communication permissions"""
    permissions = {
        'can_send_plantwide': False,
        'can_send_hr': False,
        'can_send_maintenance': False,
        'can_send_hourly': False,
        'can_view_all': current_user.is_supervisor
    }
    
    if current_user.is_supervisor:
        permissions['can_send_plantwide'] = True
        permissions['can_send_hr'] = True
        permissions['can_send_maintenance'] = True
        permissions['can_send_hourly'] = True
    else:
        # Check department-specific permissions
        if hasattr(current_user, 'department') and current_user.department == 'HR':
            permissions['can_send_hr'] = True
        elif hasattr(current_user, 'department') and current_user.department == 'Maintenance':
            permissions['can_send_maintenance'] = True
        
        # Check if user is a lead or has special permissions
        if hasattr(current_user, 'is_lead') and current_user.is_lead:
            permissions['can_send_hourly'] = True
    
    return permissions

def get_unread_counts():
    """Get unread message counts by category"""
    counts = {
        'plantwide': 0,
        'hr': 0,
        'maintenance': 0,
        'hourly': 0,
        'total': 0
    }
    
    try:
        # Get all messages the user should be able to see
        all_messages = CommunicationMessage.query.filter(
            CommunicationMessage.is_archived == False
        ).all()
        
        # Get messages the user has read
        read_message_ids = db.session.query(MessageReadReceipt.message_id).filter_by(
            employee_id=current_user.id
        ).subquery()
        
        for message in all_messages:
            if can_view_message(message) and message.id not in read_message_ids:
                if message.category in counts:
                    counts[message.category] += 1
                    counts['total'] += 1
    except Exception as e:
        logger.error(f"Error getting unread counts: {str(e)}")
    
    return counts

def mark_message_as_read(message_id):
    """Mark a message as read by the current user"""
    try:
        existing_receipt = MessageReadReceipt.query.filter_by(
            message_id=message_id,
            employee_id=current_user.id
        ).first()
        
        if not existing_receipt:
            receipt = MessageReadReceipt(
                message_id=message_id,
                employee_id=current_user.id,
                read_at=datetime.utcnow()
            )
            db.session.add(receipt)
            db.session.commit()
    except Exception as e:
        logger.error(f"Error marking message as read: {str(e)}")

def can_view_message(message):
    """Check if current user can view a message"""
    if current_user.is_supervisor:
        return True
    
    if message.target_audience == 'all':
        return True
    elif message.target_audience == 'department':
        return current_user.department == message.target_department
    elif message.target_audience == 'crew':
        return current_user.crew == message.target_crew
    elif message.target_audience == 'position':
        return current_user.position_id == message.target_position_id
    elif message.target_audience == 'individual':
        return current_user.id == message.recipient_id
    
    return False

# ============================================
# MAIN ROUTES
# ============================================

@communications_bp.route('/communications')
@login_required
def communications_hub():
    """Main communications hub showing all categories"""
    permissions = get_user_communication_permissions()
    unread_counts = get_unread_counts()
    
    # Get recent messages from each category
    recent_messages = {}
    
    for category in ['plantwide', 'hr', 'maintenance', 'hourly']:
        messages = CommunicationMessage.query.filter_by(
            category=category,
            is_archived=False
        ).order_by(desc(CommunicationMessage.created_at)).limit(5).all()
        
        # Filter messages user can view
        recent_messages[category] = [msg for msg in messages if can_view_message(msg)]
    
    return render_template('communications_hub.html',
                         permissions=permissions,
                         unread_counts=unread_counts,
                         recent_messages=recent_messages)

@communications_bp.route('/communications/<category>')
@login_required
def category_messages(category):
    """View messages for a specific category"""
    valid_categories = ['plantwide', 'hr', 'maintenance', 'hourly']
    
    if category not in valid_categories:
        flash('Invalid category', 'danger')
        return redirect(url_for('communications.communications_hub'))
    
    permissions = get_user_communication_permissions()
    
    # Check if user can view this category
    if category == 'hr' and current_user.department != 'HR' and not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('communications.communications_hub'))
    
    # Get messages for this category
    query = CommunicationMessage.query.filter_by(category=category, is_archived=False)
    
    # Apply filters
    search = request.args.get('search')
    if search:
        query = query.filter(or_(
            CommunicationMessage.subject.contains(search),
            CommunicationMessage.content.contains(search)
        ))
    
    priority = request.args.get('priority')
    if priority:
        query = query.filter_by(priority=priority)
    
    date_from = request.args.get('date_from')
    if date_from:
        query = query.filter(CommunicationMessage.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))
    
    date_to = request.args.get('date_to')
    if date_to:
        query = query.filter(CommunicationMessage.created_at <= datetime.strptime(date_to, '%Y-%m-%d'))
    
    # Order by date and get messages
    messages = query.order_by(desc(CommunicationMessage.created_at)).all()
    
    # Filter to only messages user can view
    messages = [msg for msg in messages if can_view_message(msg)]
    
    # Get read message IDs for this user
    read_message_ids = [r.message_id for r in MessageReadReceipt.query.filter_by(employee_id=current_user.id).all()]
    
    # Mark visible messages as read
    for message in messages:
        if message.id not in read_message_ids:
            mark_message_as_read(message.id)
    
    return render_template('communications_category.html',
                         category=category,
                         messages=messages,
                         permissions=permissions,
                         read_message_ids=read_message_ids)

@communications_bp.route('/communications/compose', methods=['GET', 'POST'])
@login_required
def compose_message():
    """Compose a new communication message"""
    permissions = get_user_communication_permissions()
    
    # Check if user can send any messages
    can_send_any = (permissions['can_send_plantwide'] or permissions['can_send_hr'] or 
                    permissions['can_send_maintenance'] or permissions['can_send_hourly'])
    
    if not can_send_any:
        flash('You do not have permission to send messages', 'danger')
        return redirect(url_for('communications.communications_hub'))
    
    if request.method == 'POST':
        category = request.form.get('category')
        
        # Verify permission for this category
        permission_key = f'can_send_{category}'
        if not permissions.get(permission_key, False):
            flash(f'You cannot send {category} messages', 'danger')
            return redirect(request.url)
        
        try:
            # Create the message
            message = CommunicationMessage(
                category=category,
                subject=request.form.get('subject'),
                content=request.form.get('content'),
                priority=request.form.get('priority', 'normal'),
                sender_id=current_user.id,
                target_audience=request.form.get('target_audience', 'all'),
                expires_at=datetime.strptime(request.form.get('expires_at'), '%Y-%m-%d') if request.form.get('expires_at') else None
            )
            
            # Set target specifics based on audience
            if message.target_audience == 'department':
                message.target_department = request.form.get('target_department')
            elif message.target_audience == 'crew':
                message.target_crew = request.form.get('target_crew')
            elif message.target_audience == 'position':
                message.target_position_id = request.form.get('target_position_id')
            elif message.target_audience == 'individual':
                message.recipient_id = request.form.get('recipient_id')
            
            db.session.add(message)
            db.session.flush()  # Get message ID before handling attachments
            
            # Handle attachments
            if 'attachments' in request.files:
                files = request.files.getlist('attachments')
                for file in files:
                    if file and file.filename:
                        filename = secure_filename(file.filename)
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        filename = f"{timestamp}_{filename}"
                        
                        upload_folder = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'upload_files'), 'communications')
                        os.makedirs(upload_folder, exist_ok=True)
                        filepath = os.path.join(upload_folder, filename)
                        
                        file.save(filepath)
                        
                        attachment = MessageAttachment(
                            message_id=message.id,
                            filename=filename,
                            original_filename=file.filename,
                            file_size=os.path.getsize(filepath)
                        )
                        db.session.add(attachment)
            
            db.session.commit()
            
            flash(f'{category.title()} message sent successfully', 'success')
            return redirect(url_for('communications.category_messages', category=category))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error sending message: {str(e)}")
            flash('Error sending message. Please try again.', 'danger')
            return redirect(request.url)
    
    # GET request - show compose form
    departments = db.session.query(Employee.department).distinct().filter(Employee.department != None).all()
    departments = [d[0] for d in departments]
    
    positions = Position.query.order_by(Position.name).all()
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    
    # Get pre-selected category from query parameter
    default_category = request.args.get('category', '')
    
    return render_template('communications_compose.html',
                         permissions=permissions,
                         departments=departments,
                         positions=positions,
                         employees=employees,
                         default_category=default_category)

@communications_bp.route('/communications/message/<int:message_id>')
@login_required
def view_message(message_id):
    """View a single message"""
    message = CommunicationMessage.query.get_or_404(message_id)
    
    if not can_view_message(message):
        flash('You do not have permission to view this message', 'danger')
        return redirect(url_for('communications.communications_hub'))
    
    # Mark as read
    mark_message_as_read(message_id)
    
    # Get read receipts if supervisor
    read_receipts = []
    if current_user.is_supervisor:
        read_receipts = MessageReadReceipt.query.filter_by(message_id=message_id).all()
    
    return render_template('communications_message.html',
                         message=message,
                         read_receipts=read_receipts,
                         Employee=Employee)  # Pass Employee model for template

@communications_bp.route('/communications/message/<int:message_id>/delete', methods=['POST'])
@login_required
def delete_message(message_id):
    """Delete a message (sender or supervisor only)"""
    message = CommunicationMessage.query.get_or_404(message_id)
    
    if message.sender_id != current_user.id and not current_user.is_supervisor:
        flash('You do not have permission to delete this message', 'danger')
        return redirect(url_for('communications.view_message', message_id=message_id))
    
    try:
        category = message.category
        
        # Delete attachments from filesystem
        for attachment in message.attachments:
            filepath = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'upload_files'), 
                                  'communications', attachment.filename)
            if os.path.exists(filepath):
                os.remove(filepath)
        
        db.session.delete(message)
        db.session.commit()
        
        flash('Message deleted successfully', 'success')
        return redirect(url_for('communications.category_messages', category=category))
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting message: {str(e)}")
        flash('Error deleting message', 'danger')
        return redirect(url_for('communications.view_message', message_id=message_id))

@communications_bp.route('/communications/attachment/<int:attachment_id>')
@login_required
def download_attachment(attachment_id):
    """Download a message attachment"""
    attachment = MessageAttachment.query.get_or_404(attachment_id)
    
    if not can_view_message(attachment.message):
        flash('Access denied', 'danger')
        return redirect(url_for('communications.communications_hub'))
    
    filepath = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'upload_files'), 
                           'communications', attachment.filename)
    
    if not os.path.exists(filepath):
        flash('Attachment file not found', 'danger')
        return redirect(url_for('communications.view_message', message_id=attachment.message_id))
    
    return send_file(filepath, as_attachment=True, download_name=attachment.original_filename)

# ============================================
# API ENDPOINTS
# ============================================

@communications_bp.route('/api/communications/unread-counts')
@login_required
def api_unread_counts():
    """Get unread message counts"""
    counts = get_unread_counts()
    return jsonify(counts)

@communications_bp.route('/api/communications/mark-read/<int:message_id>', methods=['POST'])
@login_required
def api_mark_read(message_id):
    """Mark a message as read"""
    message = CommunicationMessage.query.get_or_404(message_id)
    
    if not can_view_message(message):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    mark_message_as_read(message_id)
    return jsonify({'success': True})

@communications_bp.route('/api/communications/search')
@login_required
def api_search_messages():
    """Search messages across all categories"""
    query = request.args.get('q', '')
    
    if len(query) < 3:
        return jsonify({'results': []})
    
    messages = CommunicationMessage.query.filter(
        CommunicationMessage.is_archived == False,
        or_(
            CommunicationMessage.subject.contains(query),
            CommunicationMessage.content.contains(query)
        )
    ).order_by(desc(CommunicationMessage.created_at)).limit(20).all()
    
    # Filter to only messages user can view
    results = []
    for msg in messages:
        if can_view_message(msg):
            results.append({
                'id': msg.id,
                'category': msg.category,
                'subject': msg.subject,
                'preview': msg.content[:100] + '...' if len(msg.content) > 100 else msg.content,
                'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M'),
                'sender': msg.sender.name
            })
    
    return jsonify({'results': results})

# ============================================
# TEMPLATE ROUTES
# ============================================

@communications_bp.route('/communications/templates')
@login_required
def message_templates():
    """View and manage message templates"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('communications.communications_hub'))
    
    templates = MessageTemplate.query.order_by(MessageTemplate.category, MessageTemplate.name).all()
    
    return render_template('communications_templates.html', templates=templates)

@communications_bp.route('/communications/templates/create', methods=['GET', 'POST'])
@login_required
def create_template():
    """Create a new message template"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('communications.communications_hub'))
    
    if request.method == 'POST':
        try:
            template = MessageTemplate(
                name=request.form.get('name'),
                category=request.form.get('category'),
                subject=request.form.get('subject'),
                content=request.form.get('content'),
                created_by_id=current_user.id
            )
            
            db.session.add(template)
            db.session.commit()
            
            flash('Template created successfully', 'success')
            return redirect(url_for('communications.message_templates'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating template: {str(e)}")
            flash('Error creating template', 'danger')
            return redirect(request.url)
    
    return render_template('communications_template_form.html')

@communications_bp.route('/communications/templates/<int:template_id>/delete', methods=['POST'])
@login_required
def delete_template(template_id):
    """Delete a message template"""
    if not current_user.is_supervisor:
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    try:
        template = MessageTemplate.query.get_or_404(template_id)
        db.session.delete(template)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting template: {str(e)}")
        return jsonify({'success': False, 'error': 'Error deleting template'}), 500

# ============================================
# ANALYTICS ROUTES
# ============================================

@communications_bp.route('/communications/analytics')
@login_required
def communications_analytics():
    """View communications analytics"""
    if not current_user.is_supervisor:
        flash('Access denied', 'danger')
        return redirect(url_for('communications.communications_hub'))
    
    # Get message statistics
    total_messages = CommunicationMessage.query.filter_by(is_archived=False).count()
    
    messages_by_category = db.session.query(
        CommunicationMessage.category,
        func.count(CommunicationMessage.id)
    ).filter_by(is_archived=False).group_by(CommunicationMessage.category).all()
    
    messages_by_priority = db.session.query(
        CommunicationMessage.priority,
        func.count(CommunicationMessage.id)
    ).filter_by(is_archived=False).group_by(CommunicationMessage.priority).all()
    
    # Get read rates
    read_rates = {}
    for category in ['plantwide', 'hr', 'maintenance', 'hourly']:
        messages = CommunicationMessage.query.filter_by(category=category, is_archived=False).all()
        if messages:
            total_recipients = 0
            total_reads = 0
            
            for msg in messages:
                # Calculate potential recipients based on target audience
                if msg.target_audience == 'all':
                    recipients = Employee.query.filter_by(is_active=True).count()
                elif msg.target_audience == 'department':
                    recipients = Employee.query.filter_by(department=msg.target_department, is_active=True).count()
                elif msg.target_audience == 'crew':
                    recipients = Employee.query.filter_by(crew=msg.target_crew, is_active=True).count()
                elif msg.target_audience == 'position':
                    recipients = Employee.query.filter_by(position_id=msg.target_position_id, is_active=True).count()
                else:
                    recipients = 1
                
                reads = MessageReadReceipt.query.filter_by(message_id=msg.id).count()
                
                total_recipients += recipients
                total_reads += reads
            
            read_rates[category] = (total_reads / total_recipients * 100) if total_recipients > 0 else 0
    
    # Get top senders
    top_senders = db.session.query(
        Employee.name,
        func.count(CommunicationMessage.id).label('message_count')
    ).join(
        CommunicationMessage, CommunicationMessage.sender_id == Employee.id
    ).filter(
        CommunicationMessage.is_archived == False
    ).group_by(Employee.name).order_by(desc('message_count')).limit(10).all()
    
    # Get recent activity (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_activity = db.session.query(
        func.date(CommunicationMessage.created_at).label('date'),
        func.count(CommunicationMessage.id).label('count')
    ).filter(
        CommunicationMessage.created_at >= thirty_days_ago,
        CommunicationMessage.is_archived == False
    ).group_by(func.date(CommunicationMessage.created_at)).all()
    
    return render_template('communications_analytics.html',
                         total_messages=total_messages,
                         messages_by_category=dict(messages_by_category),
                         messages_by_priority=dict(messages_by_priority),
                         read_rates=read_rates,
                         top_senders=top_senders,
                         recent_activity=recent_activity)
