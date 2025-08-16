# blueprints/main.py
"""
Main blueprint - Fixed to prevent redirect loops
"""

from flask import Blueprint, render_template, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, Employee, TimeOffRequest, ShiftSwapRequest, CoverageGap, MaintenanceIssue
from datetime import datetime, date, timedelta
from functools import wraps
import logging

logger = logging.getLogger(__name__)

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

# Remove the competing root route - let auth.py handle it
# @main_bp.route('/')
# def index():
#     """Landing page - redirect based on authentication"""
#     # This is now handled by auth.py

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - redirect based on role with error handling"""
    try:
        if current_user.is_supervisor:
            # Don't redirect if we're already having issues
            # Instead, try to render a simple dashboard
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    except Exception as e:
        logger.error(f"Error in dashboard redirect: {e}")
        # Fallback to a simple dashboard
        return render_template('basic_dashboard.html', 
                             user_name=current_user.name,
                             pending_time_off=0,
                             pending_swaps=0,
                             total_employees=0)

@main_bp.route('/employee-dashboard')
@login_required
def employee_dashboard():
    """Employee dashboard view with error handling"""
    try:
        # Get pending requests with error handling
        pending_time_off = 0
        pending_swaps = 0
        
        try:
            pending_time_off = TimeOffRequest.query.filter_by(
                employee_id=current_user.id,
                status='pending'
            ).count()
        except Exception as e:
            logger.error(f"Error getting time off requests: {e}")
            db.session.rollback()
        
        try:
            pending_swaps = ShiftSwapRequest.query.filter_by(
                requester_id=current_user.id,
                status='pending'
            ).count()
        except Exception as e:
            logger.error(f"Error getting swap requests: {e}")
            db.session.rollback()
        
        return render_template('employee_dashboard.html',
                             pending_time_off=pending_time_off,
                             pending_swaps=pending_swaps)
    except Exception as e:
        logger.error(f"Error in employee dashboard: {e}")
        flash('Error loading dashboard. Please try again.', 'danger')
        return redirect(url_for('auth.login'))

@main_bp.route('/overtime-management')
@login_required
@supervisor_required
def overtime_management():
    """Overtime management page"""
    try:
        return render_template('overtime_management.html')
    except Exception as e:
        logger.error(f"Error in overtime management: {e}")
        flash('Error loading overtime management page.', 'danger')
        return redirect(url_for('main.dashboard'))

@main_bp.route('/view-crews')
@login_required
def view_crews():
    """View all crews and their members"""
    try:
        crews = {}
        for crew in ['A', 'B', 'C', 'D']:
            try:
                crews[crew] = Employee.query.filter_by(crew=crew, is_active=True).all()
            except:
                crews[crew] = []
                db.session.rollback()
        
        return render_template('view_crews.html', crews=crews)
    except Exception as e:
        logger.error(f"Error in view crews: {e}")
        flash('Error loading crew information.', 'danger')
        return redirect(url_for('main.dashboard'))

# ==========================================
# DIAGNOSTIC ROUTES
# ==========================================

@main_bp.route('/diagnostic')
@login_required
@supervisor_required
def diagnostic():
    """System diagnostic page"""
    diagnostics = {
        'database': 'Unknown',
        'employees': 0,
        'supervisors': 0,
        'pending_time_off': 0,
        'pending_swaps': 0,
        'coverage_gaps': 0,
        'open_maintenance': 0
    }
    
    # Test database connection
    try:
        db.session.execute('SELECT 1')
        diagnostics['database'] = 'Connected'
    except:
        diagnostics['database'] = 'Error'
        db.session.rollback()
    
    # Get counts with error handling
    try:
        diagnostics['employees'] = Employee.query.filter_by(is_active=True).count()
    except:
        db.session.rollback()
        
    try:
        diagnostics['supervisors'] = Employee.query.filter_by(is_supervisor=True).count()
    except:
        db.session.rollback()
        
    try:
        diagnostics['pending_time_off'] = TimeOffRequest.query.filter_by(status='pending').count()
    except:
        db.session.rollback()
        
    try:
        diagnostics['pending_swaps'] = ShiftSwapRequest.query.filter_by(status='pending').count()
    except:
        db.session.rollback()
    
    return render_template('diagnostic.html', diagnostics=diagnostics)

@main_bp.route('/debug-routes')
@login_required
@supervisor_required
def debug_routes():
    """Show all registered routes"""
    try:
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
    except Exception as e:
        logger.error(f"Error in debug routes: {e}")
        return f"<pre>Error getting routes: {str(e)}</pre>", 500

# ==========================================
# API ENDPOINTS
# ==========================================

@main_bp.route('/api/dashboard-stats')
@login_required
def dashboard_stats():
    """Get dashboard statistics"""
    stats = {}
    
    try:
        if current_user.is_supervisor:
            stats = {
                'total_employees': Employee.query.filter_by(is_active=True).count(),
                'pending_requests': 0,
                'coverage_gaps': 0,
                'critical_maintenance': 0
            }
            
            try:
                stats['pending_requests'] = TimeOffRequest.query.filter_by(status='pending').count()
            except:
                pass
                
        else:
            stats = {
                'pending_time_off': 0,
                'pending_swaps': 0
            }
            
            try:
                stats['pending_time_off'] = TimeOffRequest.query.filter_by(
                    employee_id=current_user.id,
                    status='pending'
                ).count()
            except:
                pass
                
            try:
                stats['pending_swaps'] = ShiftSwapRequest.query.filter_by(
                    requester_id=current_user.id,
                    status='pending'
                ).count()
            except:
                pass
                
    except Exception as e:
        logger.error(f"Error getting dashboard stats: {e}")
        
    return jsonify(stats)

# ==========================================
# ERROR HANDLERS
# ==========================================

@main_bp.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@main_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500
