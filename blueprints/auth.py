# blueprints/auth.py - COMPLETE FIXED FILE
"""
Authentication blueprint with corrected routing
Fixes all route naming issues and adds robust error handling
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from models import db, Employee
from datetime import datetime
from werkzeug.security import check_password_hash, generate_password_hash

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def index():
    """Landing page - redirect to login or dashboard"""
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            # FIXED: Use supervisor.dashboard instead of main.dashboard
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    return redirect(url_for('auth.login'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login with proper error handling"""
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)
        
        if not email or not password:
            flash('Please enter both email and password.', 'danger')
            return render_template('login.html')
        
        # Find employee by email
        employee = Employee.query.filter_by(email=email).first()
        
        if employee and employee.check_password(password):
            # Update last login
            employee.last_login = datetime.utcnow()
            db.session.commit()
            
            # Log the user in
            login_user(employee, remember=remember)
            
            # Check if password change is required
            if hasattr(employee, 'needs_password_change') and employee.needs_password_change:
                flash('You must change your password before continuing.', 'warning')
                return redirect(url_for('auth.change_password'))
            
            flash(f'Welcome back, {employee.name}!', 'success')
            
            # Redirect to appropriate dashboard
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            elif employee.is_supervisor:
                return redirect(url_for('supervisor.dashboard'))
            else:
                return redirect(url_for('main.employee_dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
    
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """Handle user logout"""
    logout_user()
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change password page with fixed routing"""
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate current password
        if not current_user.check_password(current_password):
            flash('Current password is incorrect.', 'danger')
            return render_template('change_password.html')
        
        # Validate new password
        if len(new_password) < 6:
            flash('New password must be at least 6 characters long.', 'danger')
            return render_template('change_password.html')
            
        if new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
            return render_template('change_password.html')
        
        if current_password == new_password:
            flash('New password must be different from current password.', 'danger')
            return render_template('change_password.html')
        
        # Update password
        current_user.set_password(new_password)
        if hasattr(current_user, 'needs_password_change'):
            current_user.needs_password_change = False
        db.session.commit()
        
        flash('Your password has been changed successfully!', 'success')
        
        # Redirect to appropriate dashboard
        if current_user.is_supervisor:
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    
    return render_template('change_password.html')
