# utils/decorators.py
"""
Custom decorators for access control and other functionality
"""

from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user

def supervisor_required(f):
    """
    Decorator to require supervisor access for a route
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        
        if not current_user.is_supervisor:
            flash('Supervisor access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    
    return decorated_function

def admin_required(f):
    """
    Decorator to require admin access for a route
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        
        if not current_user.is_admin:
            flash('Admin access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        
        return f(*args, **kwargs)
    
    return decorated_function

def position_required(position_name):
    """
    Decorator to require a specific position for access
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login'))
            
            if not current_user.position or current_user.position.name != position_name:
                flash(f'This page requires {position_name} position.', 'danger')
                return redirect(url_for('main.dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
