# blueprints/main.py
from flask import Blueprint, render_template, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, Employee, TimeOffRequest, ShiftSwapRequest, CoverageGap, MaintenanceIssue
from datetime import datetime, date, timedelta
from functools import wraps

main_bp = Blueprint('main', __name__)

def supervisor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.is_supervisor:
            flash('You need supervisor privileges to access this page.', 'warning')
            return redirect(url_for('main.employee_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@main_bp.route('/')
def index():
    """Landing page - redirect based on authentication"""
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('main.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    return render_template('index.html')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - redirect based on role"""
    if current_user.is_supervisor:
        return redirect(url_for('supervisor.dashboard'))
    else:
        return redirect(url_for('main.employee_dashboard'))

@main_bp.route('/employee-dashboard')
@login_required
def employee_dashboard():
    """Employee dashboard view"""
    # Get employee's current schedule
    today = date.today()
    
    # Get pending requests
    pending_time_off = TimeOffRequest.query.filter_by(
        employee_id=current_user.id,
        status='pending'
    ).count()
    
    pending_swaps = ShiftSwapRequest.query.filter_by(
        requester_id=current_user.id,
        status='pending'
    ).count()
    
    return render_template('employee_dashboard.html',
                         pending_time_off=pending_time_off,
                         pending_swaps=pending_swaps)

@main_bp.route('/overtime-management')
@login_required
@supervisor_required
def overtime_management():
    """Overtime management page"""
    return render_template('overtime_management.html')

@main_bp.route('/view-crews')
@login_required
def view_crews():
    """View all crews and their members"""
    crews = {}
    for crew in ['A', 'B', 'C', 'D']:
        crews[crew] = Employee.query.filter_by(crew=crew, is_active=True).all()
    
    return render_template('view_crews.html', crews=crews)

# ==========================================
# ADMIN FIX ROUTES
# ==========================================

@main_bp.route('/fix-admin')
def fix_admin():
    """Create admin user if it doesn't exist"""
    try:
        # Check if any admin exists
        admin = Employee.query.filter_by(email='admin@workforce.com').first()
        
        if admin:
            # Update existing admin
            admin.is_supervisor = True
            admin.is_admin = True
            admin.set_password('admin123')
            db.session.commit()
            return jsonify({
                'status': 'updated',
                'message': 'Admin user updated successfully',
                'email': 'admin@workforce.com',
                'password': 'admin123'
            })
        else:
            # Create new admin
            admin = Employee(
                email='admin@workforce.com',
                name='System Administrator',
                employee_id='ADMIN001',
                is_supervisor=True,
                is_admin=True,
                department='Management',
                crew='A',
                is_active=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            
            return jsonify({
                'status': 'created',
                'message': 'Admin user created successfully',
                'email': 'admin@workforce.com',
                'password': 'admin123'
            })
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'Error creating admin: {str(e)}'
        }), 500

@main_bp.route('/init-communications')
@login_required
@supervisor_required
def init_communications():
    """Initialize communications system"""
    try:
        from models import CommunicationCategory, CommunicationMessage
        
        # Check if already initialized
        existing = CommunicationCategory.query.first()
        if existing:
            return jsonify({
                'status': 'exists',
                'message': 'Communications system already initialized'
            })
        
        # Create categories
        categories = [
            {
                'name': 'Plant-wide Announcements',
                'description': 'Important announcements affecting all employees',
                'icon': 'bi-megaphone',
                'color': 'danger'
            },
            {
                'name': 'HR Updates',
                'description': 'Human resources updates, policies, and benefits information',
                'icon': 'bi-people',
                'color': 'primary'
            },
            {
                'name': 'Maintenance Notices',
                'description': 'Equipment maintenance schedules and facility updates',
                'icon': 'bi-tools',
                'color': 'warning'
            },
            {
                'name': 'Hourly Employee Announcements',
                'description': 'Information specific to hourly workforce',
                'icon': 'bi-clock',
                'color': 'info'
            }
        ]
        
        created_categories = {}
        for cat_data in categories:
            category = CommunicationCategory(**cat_data)
            db.session.add(category)
            db.session.flush()
            created_categories[cat_data['name']] = category
        
        # Create welcome message
        welcome_msg = CommunicationMessage(
            category_id=created_categories['Plant-wide Announcements'].id,
            author_id=current_user.id,
            title='Welcome to the New Communications System',
            content="""
            <p>We are excited to launch our new communications system!</p>
            <p>This system will help us share important information more effectively:</p>
            <ul>
                <li>Plant-wide announcements</li>
                <li>HR updates and policy changes</li>
                <li>Maintenance schedules</li>
                <li>Crew-specific information</li>
            </ul>
            <p>Please check this system regularly for important updates.</p>
            """,
            priority='high',
            is_pinned=True,
            target_all=True
        )
        db.session.add(welcome_msg)
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Communications system initialized successfully',
            'categories_created': len(categories)
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'Error initializing communications: {str(e)}'
        }), 500

@main_bp.route('/check-models')
@login_required
@supervisor_required
def check_models():
    """Check database models status"""
    try:
        from models import (Employee, CommunicationCategory, CommunicationMessage,
                          CommunicationReadReceipt, CommunicationAttachment,
                          PositionMessage, PositionMessageReadReceipt)
        
        model_status = {
            'Employee': Employee.query.count(),
            'CommunicationCategory': CommunicationCategory.query.count(),
            'CommunicationMessage': CommunicationMessage.query.count(),
            'CommunicationReadReceipt': CommunicationReadReceipt.query.count(),
            'CommunicationAttachment': CommunicationAttachment.query.count(),
            'PositionMessage': PositionMessage.query.count(),
            'PositionMessageReadReceipt': PositionMessageReadReceipt.query.count()
        }
        
        return jsonify({
            'status': 'success',
            'models': model_status
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error checking models: {str(e)}'
        }), 500

# ==========================================
# DIAGNOSTIC ROUTES
# ==========================================

@main_bp.route('/diagnostic')
@login_required
@supervisor_required
def diagnostic():
    """System diagnostic page"""
    diagnostics = {
        'total_employees': Employee.query.count(),
        'active_employees': Employee.query.filter_by(is_active=True).count(),
        'supervisors': Employee.query.filter_by(is_supervisor=True).count(),
        'pending_time_off': TimeOffRequest.query.filter_by(status='pending').count(),
        'pending_swaps': ShiftSwapRequest.query.filter_by(status='pending').count(),
        'coverage_gaps': CoverageGap.query.filter_by(is_filled=False).count(),
        'open_maintenance': MaintenanceIssue.query.filter_by(status='new').count()
    }
    
    return render_template('diagnostic.html', diagnostics=diagnostics)

@main_bp.route('/debug-routes')
@login_required
@supervisor_required
def debug_routes():
    """Show all registered routes"""
    from flask import current_app
    
    routes = []
    for rule in current_app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'path': str(rule)
        })
    
    routes.sort(key=lambda x: x['path'])
    
    return render_template('debug_routes.html', routes=routes)

# ==========================================
# API ENDPOINTS
# ==========================================

@main_bp.route('/api/dashboard-stats')
@login_required
def dashboard_stats():
    """Get dashboard statistics"""
    if current_user.is_supervisor:
        stats = {
            'total_employees': Employee.query.filter_by(is_active=True).count(),
            'pending_requests': TimeOffRequest.query.filter_by(status='pending').count(),
            'coverage_gaps': CoverageGap.query.filter_by(is_filled=False).count(),
            'critical_maintenance': MaintenanceIssue.query.filter_by(severity='critical', status='new').count()
        }
    else:
        stats = {
            'pending_time_off': TimeOffRequest.query.filter_by(
                employee_id=current_user.id,
                status='pending'
            ).count(),
            'pending_swaps': ShiftSwapRequest.query.filter_by(
                requester_id=current_user.id,
                status='pending'
            ).count()
        }
    
    return jsonify(stats)
