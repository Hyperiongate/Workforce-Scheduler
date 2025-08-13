# blueprints/communications.py
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from models import (db, CommunicationCategory, CommunicationMessage, 
                   CommunicationReadReceipt, CommunicationAttachment, Employee)
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import os
from functools import wraps

communications_bp = Blueprint('communications', __name__)

# Decorator for supervisor access
def supervisor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_supervisor:
            flash('Access denied. Supervisor privileges required.', 'danger')
            return redirect(url_for('main.employee_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# MAIN COMMUNICATIONS VIEWS
# ==========================================

@communications_bp.route('/communications')
@login_required
def index():
    """Main communications dashboard"""
    try:
        # Get all active categories
        categories = CommunicationCategory.query.filter_by(is_active=True).all()
        
        # Get recent messages for each category
        recent_messages = {}
        unread_counts = {}
        
        for category in categories:
            # Get messages targeted to this user
            messages_query = CommunicationMessage.query.filter_by(
                category_id=category.id,
                is_archived=False
            ).filter(
                db.or_(
                    CommunicationMessage.target_all == True,
                    CommunicationMessage.target_crews.contains(current_user.crew),
                    CommunicationMessage.target_departments.contains(current_user.department),
                    CommunicationMessage.target_positions.contains(str(current_user.position_id))
                )
            ).order_by(
                CommunicationMessage.is_pinned.desc(),
                CommunicationMessage.created_at.desc()
            )
            
            # Get recent messages
            recent_messages[category.id] = messages_query.limit(5).all()
            
            # Count unread messages
            unread_count = 0
            for message in messages_query.all():
                if not message.is_read_by(current_user.id):
                    unread_count += 1
            unread_counts[category.id] = unread_count
        
        # Get messages requiring acknowledgment
        pending_acknowledgments = CommunicationMessage.query.filter(
            CommunicationMessage.requires_acknowledgment == True,
            CommunicationMessage.is_archived == False
        ).filter(
            db.or_(
                CommunicationMessage.target_all == True,
                CommunicationMessage.target_crews.contains(current_user.crew),
                CommunicationMessage.target_departments.contains(current_user.department),
                CommunicationMessage.target_positions.contains(str(current_user.position_id))
            )
        ).all()
        
        # Filter out already acknowledged
        pending_acknowledgments = [
            msg for msg in pending_acknowledgments 
            if not msg.is_acknowledged_by(current_user.id)
        ]
        
        return render_template('communications/index.html',
                             categories=categories,
                             recent_messages=recent_messages,
                             unread_counts=unread_counts,
                             pending_acknowledgments=pending_acknowledgments)
                             
    except Exception as e:
        flash(f'Error loading communications: {str(e)}', 'danger')
        return redirect(url_for('main.employee_dashboard'))

@communications_bp.route('/communications/category/<int:category_id>')
@login_required
def category_view(category_id):
    """View all messages in a category"""
    try:
        category = CommunicationCategory.query.get_or_404(category_id)
        
        # Get messages for this category
        messages_query = CommunicationMessage.query.filter_by(
            category_id=category_id,
            is_archived=False
        ).filter(
            db.or_(
                CommunicationMessage.target_all == True,
                CommunicationMessage.target_crews.contains(current_user.crew),
                CommunicationMessage.target_departments.contains(current_user.department),
                CommunicationMessage.target_positions.contains(str(current_user.position_id))
            )
        ).order_by(
            CommunicationMessage.is_pinned.desc(),
            CommunicationMessage.created_at.desc()
        )
        
        # Pagination
        page = request.args.get('page', 1, type=int)
        messages = messages_query.paginate(page=page, per_page=20, error_out=False)
        
        return render_template('communications/category.html',
                             category=category,
                             messages=messages)
                             
    except Exception as e:
        flash(f'Error loading category: {str(e)}', 'danger')
        return redirect(url_for('communications.index'))

@communications_bp.route('/communications/message/<int:message_id>')
@login_required
def view_message(message_id):
    """View a single message"""
    try:
        message = CommunicationMessage.query.get_or_404(message_id)
        
        # Check if user has access
        if not _user_can_view_message(current_user, message):
            flash('You do not have access to this message.', 'danger')
            return redirect(url_for('communications.index'))
        
        # Mark as read
        receipt = CommunicationReadReceipt.query.filter_by(
            message_id=message_id,
            employee_id=current_user.id
        ).first()
        
        if not receipt:
            receipt = CommunicationReadReceipt(
                message_id=message_id,
                employee_id=current_user.id,
                read_at=datetime.utcnow()
            )
            db.session.add(receipt)
            db.session.commit()
        
        # Get read/acknowledgment stats if supervisor
        read_stats = None
        if current_user.is_supervisor:
            total_employees = _count_target_employees(message)
            read_count = len(message.read_receipts)
            ack_count = sum(1 for r in message.read_receipts if r.acknowledged)
            
            read_stats = {
                'total': total_employees,
                'read': read_count,
                'acknowledged': ack_count,
                'read_percentage': (read_count / total_employees * 100) if total_employees > 0 else 0,
                'ack_percentage': (ack_count / total_employees * 100) if total_employees > 0 else 0
            }
        
        return render_template('communications/message.html',
                             message=message,
                             receipt=receipt,
                             read_stats=read_stats)
                             
    except Exception as e:
        flash(f'Error loading message: {str(e)}', 'danger')
        return redirect(url_for('communications.index'))

# ==========================================
# MESSAGE CREATION & MANAGEMENT
# ==========================================

@communications_bp.route('/communications/create', methods=['GET', 'POST'])
@login_required
@supervisor_required
def create_message():
    """Create a new communication message"""
    if request.method == 'POST':
        try:
            # Get form data
            category_id = request.form.get('category_id', type=int)
            title = request.form.get('title')
            content = request.form.get('content')
            priority = request.form.get('priority', 'normal')
            
            # Visibility options
            is_pinned = request.form.get('is_pinned') == 'on'
            requires_acknowledgment = request.form.get('requires_acknowledgment') == 'on'
            
            # Target audience
            target_all = request.form.get('target_all') == 'on'
            target_crews = request.form.getlist('target_crews') if not target_all else None
            target_departments = request.form.getlist('target_departments') if not target_all else None
            target_positions = request.form.getlist('target_positions') if not target_all else None
            
            # Expiration
            expires_in = request.form.get('expires_in', type=int)
            expires_at = None
            if expires_in:
                expires_at = datetime.utcnow() + timedelta(days=expires_in)
            
            # Create message
            message = CommunicationMessage(
                category_id=category_id,
                author_id=current_user.id,
                title=title,
                content=content,
                priority=priority,
                is_pinned=is_pinned,
                requires_acknowledgment=requires_acknowledgment,
                target_all=target_all,
                target_crews=target_crews,
                target_departments=target_departments,
                target_positions=target_positions,
                expires_at=expires_at
            )
            
            db.session.add(message)
            db.session.commit()
            
            # Handle file attachments
            if 'attachments' in request.files:
                for file in request.files.getlist('attachments'):
                    if file and file.filename:
                        filename = secure_filename(file.filename)
                        # Save file logic here
                        attachment = CommunicationAttachment(
                            message_id=message.id,
                            filename=filename,
                            file_size=0,  # Calculate actual size
                            mime_type=file.content_type
                        )
                        db.session.add(attachment)
                
                db.session.commit()
            
            flash('Message created successfully!', 'success')
            return redirect(url_for('communications.view_message', message_id=message.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating message: {str(e)}', 'danger')
    
    # GET request - show form
    categories = CommunicationCategory.query.filter_by(is_active=True).all()
    departments = db.session.query(Employee.department).distinct().all()
    departments = [d[0] for d in departments if d[0]]
    
    from models import Position
    positions = Position.query.all()
    
    return render_template('communications/create.html',
                         categories=categories,
                         departments=departments,
                         positions=positions)

@communications_bp.route('/communications/message/<int:message_id>/acknowledge', methods=['POST'])
@login_required
def acknowledge_message(message_id):
    """Acknowledge a message"""
    try:
        message = CommunicationMessage.query.get_or_404(message_id)
        
        # Check access
        if not _user_can_view_message(current_user, message):
            return jsonify({'error': 'Access denied'}), 403
        
        # Update or create receipt
        receipt = CommunicationReadReceipt.query.filter_by(
            message_id=message_id,
            employee_id=current_user.id
        ).first()
        
        if not receipt:
            receipt = CommunicationReadReceipt(
                message_id=message_id,
                employee_id=current_user.id,
                read_at=datetime.utcnow()
            )
            db.session.add(receipt)
        
        receipt.acknowledged = True
        receipt.acknowledged_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==========================================
# ADMIN FUNCTIONS
# ==========================================

@communications_bp.route('/communications/admin')
@login_required
@supervisor_required
def admin():
    """Communications admin panel"""
    categories = CommunicationCategory.query.all()
    
    # Get statistics
    stats = {
        'total_messages': CommunicationMessage.query.count(),
        'active_messages': CommunicationMessage.query.filter_by(is_archived=False).count(),
        'pinned_messages': CommunicationMessage.query.filter_by(is_pinned=True, is_archived=False).count(),
        'pending_acks': db.session.query(CommunicationMessage).join(
            CommunicationReadReceipt
        ).filter(
            CommunicationMessage.requires_acknowledgment == True,
            CommunicationReadReceipt.acknowledged == False
        ).count()
    }
    
    return render_template('communications/admin.html',
                         categories=categories,
                         stats=stats)

@communications_bp.route('/communications/category/create', methods=['POST'])
@login_required
@supervisor_required
def create_category():
    """Create a new category"""
    try:
        name = request.form.get('name')
        description = request.form.get('description')
        icon = request.form.get('icon', 'bi-chat-dots')
        color = request.form.get('color', 'primary')
        
        category = CommunicationCategory(
            name=name,
            description=description,
            icon=icon,
            color=color
        )
        
        db.session.add(category)
        db.session.commit()
        
        flash('Category created successfully!', 'success')
        return redirect(url_for('communications.admin'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating category: {str(e)}', 'danger')
        return redirect(url_for('communications.admin'))

# ==========================================
# UTILITY FUNCTIONS
# ==========================================

def _user_can_view_message(user, message):
    """Check if a user can view a message based on targeting"""
    if message.target_all:
        return True
    
    if message.target_crews and user.crew in message.target_crews:
        return True
    
    if message.target_departments and user.department in message.target_departments:
        return True
    
    if message.target_positions and str(user.position_id) in message.target_positions:
        return True
    
    # Supervisors can view all messages
    if user.is_supervisor:
        return True
    
    return False

def _count_target_employees(message):
    """Count how many employees are targeted by a message"""
    query = Employee.query.filter_by(is_active=True)
    
    if not message.target_all:
        filters = []
        
        if message.target_crews:
            filters.append(Employee.crew.in_(message.target_crews))
        
        if message.target_departments:
            filters.append(Employee.department.in_(message.target_departments))
        
        if message.target_positions:
            position_ids = [int(p) for p in message.target_positions]
            filters.append(Employee.position_id.in_(position_ids))
        
        if filters:
            query = query.filter(db.or_(*filters))
    
    return query.count()

# ==========================================
# API ENDPOINTS
# ==========================================

@communications_bp.route('/api/communications/stats')
@login_required
def api_stats():
    """Get communication statistics"""
    try:
        # Count unread messages
        unread_count = 0
        pending_acks = 0
        
        # Get all messages targeted to user
        messages = CommunicationMessage.query.filter_by(is_archived=False).all()
        
        for message in messages:
            if _user_can_view_message(current_user, message):
                if not message.is_read_by(current_user.id):
                    unread_count += 1
                
                if message.requires_acknowledgment and not message.is_acknowledged_by(current_user.id):
                    pending_acks += 1
        
        return jsonify({
            'unread_count': unread_count,
            'pending_acknowledgments': pending_acks
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@communications_bp.route('/api/communications/mark-read', methods=['POST'])
@login_required
def api_mark_read():
    """Mark messages as read"""
    try:
        message_ids = request.json.get('message_ids', [])
        
        for message_id in message_ids:
            message = CommunicationMessage.query.get(message_id)
            if message and _user_can_view_message(current_user, message):
                receipt = CommunicationReadReceipt.query.filter_by(
                    message_id=message_id,
                    employee_id=current_user.id
                ).first()
                
                if not receipt:
                    receipt = CommunicationReadReceipt(
                        message_id=message_id,
                        employee_id=current_user.id,
                        read_at=datetime.utcnow()
                    )
                    db.session.add(receipt)
        
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
