# blueprints/auth.py
"""
Authentication Blueprint
Handles login, logout, and password management
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from models import db, Employee
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Create blueprint
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)
        
        if not email or not password:
            flash('Please enter both email and password.', 'warning')
            return render_template('login.html')
        
        try:
            # Find employee by email (no username field in model)
            employee = Employee.query.filter_by(email=email).first()
            
            if not employee:
                flash('Invalid email or password.', 'danger')
                return render_template('login.html')
            
            if not employee.password_hash:
                flash('Account not properly configured. Please contact your supervisor.', 'danger')
                return render_template('login.html')
            
            if employee.check_password(password):
                # Successful login
                login_user(employee, remember=remember)
                
                # Update last login if field exists
                try:
                    employee.last_login = datetime.utcnow()
                    db.session.commit()
                except:
                    pass  # Field might not exist
                
                flash(f'Welcome back, {employee.name}!', 'success')
                
                # Redirect to next page or appropriate dashboard
                next_page = request.args.get('next')
                if next_page and next_page.startswith('/'):
                    return redirect(next_page)
                
                if employee.is_supervisor:
                    return redirect(url_for('supervisor.dashboard'))
                else:
                    return redirect(url_for('main.employee_dashboard'))
            else:
                flash('Invalid email or password.', 'danger')
                return render_template('login.html')
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            db.session.rollback()
            flash('An error occurred during login. Please try again.', 'danger')
            return render_template('login.html')
    
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """Handle user logout"""
    try:
        user_name = current_user.name
        logout_user()
        flash(f'Goodbye, {user_name}! You have been logged out.', 'info')
    except:
        logout_user()
        flash('You have been logged out.', 'info')
    
    return redirect(url_for('auth.login'))

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Allow users to change their password"""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not all([current_password, new_password, confirm_password]):
            flash('All fields are required.', 'warning')
            return render_template('change_password.html')
        
        if not current_user.check_password(current_password):
            flash('Current password is incorrect.', 'danger')
            return render_template('change_password.html')
        
        if len(new_password) < 8:
            flash('New password must be at least 8 characters long.', 'warning')
            return render_template('change_password.html')
        
        if new_password != confirm_password:
            flash('New passwords do not match.', 'warning')
            return render_template('change_password.html')
        
        try:
            current_user.set_password(new_password)
            db.session.commit()
            flash('Password changed successfully!', 'success')
            
            if current_user.is_supervisor:
                return redirect(url_for('supervisor.dashboard'))
            else:
                return redirect(url_for('main.employee_dashboard'))
                
        except Exception as e:
            logger.error(f"Password change error: {e}")
            db.session.rollback()
            flash('An error occurred while changing your password. Please try again.', 'danger')
            return render_template('change_password.html')
    
    return render_template('change_password.html')

@auth_bp.route('/')
def index():
    """Root route - redirect to login or dashboard"""
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    return redirect(url_for('auth.login'))
