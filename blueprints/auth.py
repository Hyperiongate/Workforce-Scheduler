# blueprints/auth.py - Proper implementation without database initialization
"""
Authentication Blueprint
Handles login, logout, and password management
NO DATABASE INITIALIZATION HERE - that belongs in app.py
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from models import db, Employee
from datetime import datetime, timedelta
import logging
from sqlalchemy.exc import OperationalError
from functools import wraps

# Set up logging
logger = logging.getLogger(__name__)

# Create blueprint
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    # If already logged in, redirect appropriately
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('employee.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)
        
        if not email or not password:
            flash('Please enter both email and password.', 'warning')
            return render_template('login.html')
        
        try:
            # Find employee by email or username
            employee = Employee.query.filter(
                db.or_(Employee.email == email, Employee.username == email)
            ).first()
            
            if not employee:
                flash('Invalid email/username or password.', 'danger')
                logger.warning(f"Failed login attempt for: {email}")
                return render_template('login.html')
            
            # Check if account is active
            if hasattr(employee, 'account_active') and not employee.account_active:
                flash('Your account has been deactivated. Please contact your supervisor.', 'danger')
                return render_template('login.html')
            
            # Check if account is locked
            if hasattr(employee, 'locked_until') and employee.locked_until:
                if employee.locked_until > datetime.utcnow():
                    remaining = (employee.locked_until - datetime.utcnow()).seconds // 60
                    flash(f'Account is locked. Please try again in {remaining} minutes.', 'danger')
                    return render_template('login.html')
                else:
                    # Unlock the account
                    employee.locked_until = None
                    employee.login_attempts = 0
            
            # Verify password
            if not employee.password_hash:
                flash('Password not set. Please contact your supervisor.', 'danger')
                return render_template('login.html')
            
            if check_password_hash(employee.password_hash, password):
                # Reset login attempts
                if hasattr(employee, 'login_attempts'):
                    employee.login_attempts = 0
                
                # Update last login
                if hasattr(employee, 'last_login'):
                    employee.last_login = datetime.utcnow()
                
                # Check if first login
                first_login = False
                if hasattr(employee, 'first_login') and employee.first_login:
                    employee.first_login = False
                    first_login = True
                
                # Commit changes
                db.session.commit()
                
                # Log the user in
                login_user(employee, remember=remember)
                
                # Check if password change required
                if hasattr(employee, 'must_change_password') and employee.must_change_password:
                    flash('You must change your password before continuing.', 'info')
                    return redirect(url_for('auth.change_password'))
                
                # Welcome message
                if first_login:
                    flash(f'Welcome to the Workforce Scheduler, {employee.name}!', 'success')
                else:
                    flash(f'Welcome back, {employee.name}!', 'success')
                
                # Redirect to appropriate dashboard
                next_page = request.args.get('next')
                if next_page and next_page.startswith('/'):
                    return redirect(next_page)
                
                if employee.is_supervisor:
                    return redirect(url_for('supervisor.dashboard'))
                else:
                    return redirect(url_for('employee.dashboard'))
            else:
                # Failed login
                if hasattr(employee, 'login_attempts'):
                    employee.login_attempts = (employee.login_attempts or 0) + 1
                    
                    if employee.login_attempts >= 5:
                        employee.locked_until = datetime.utcnow() + timedelta(minutes=30)
                        db.session.commit()
                        flash('Too many failed attempts. Account locked for 30 minutes.', 'danger')
                    else:
                        remaining = 5 - employee.login_attempts
                        db.session.commit()
                        flash(f'Invalid password. {remaining} attempts remaining.', 'danger')
                else:
                    flash('Invalid email/username or password.', 'danger')
                
                logger.warning(f"Failed login attempt for user: {employee.email}")
                return render_template('login.html')
                
        except OperationalError as e:
            logger.error(f"Database error during login: {e}")
            flash('Database connection error. Please try again later.', 'danger')
            return render_template('login.html')
        except Exception as e:
            logger.error(f"Unexpected login error: {e}")
            db.session.rollback()
            flash('An error occurred. Please try again.', 'danger')
            return render_template('login.html')
    
    # GET request - show login form
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """Handle user logout"""
    try:
        user_name = current_user.name
        logout_user()
        flash(f'Goodbye, {user_name}! You have been logged out.', 'info')
    except Exception as e:
        logger.error(f"Logout error: {e}")
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
        
        # Validate all fields provided
        if not all([current_password, new_password, confirm_password]):
            flash('All fields are required.', 'warning')
            return render_template('change_password.html')
        
        # Verify current password
        if not check_password_hash(current_user.password_hash, current_password):
            flash('Current password is incorrect.', 'danger')
            return render_template('change_password.html')
        
        # Validate new password
        if len(new_password) < 8:
            flash('New password must be at least 8 characters long.', 'warning')
            return render_template('change_password.html')
        
        if new_password != confirm_password:
            flash('New passwords do not match.', 'warning')
            return render_template('change_password.html')
        
        if current_password == new_password:
            flash('New password must be different from current password.', 'warning')
            return render_template('change_password.html')
        
        try:
            # Update password
            current_user.password_hash = generate_password_hash(new_password)
            
            # Update password metadata if fields exist
            if hasattr(current_user, 'must_change_password'):
                current_user.must_change_password = False
            if hasattr(current_user, 'last_password_change'):
                current_user.last_password_change = datetime.utcnow()
            
            db.session.commit()
            
            flash('Password changed successfully!', 'success')
            
            # Redirect to appropriate dashboard
            if current_user.is_supervisor:
                return redirect(url_for('supervisor.dashboard'))
            else:
                return redirect(url_for('employee.dashboard'))
                
        except Exception as e:
            logger.error(f"Password change error: {e}")
            db.session.rollback()
            flash('An error occurred. Please try again.', 'danger')
            return render_template('change_password.html')
    
    # GET request - show change password form
    return render_template('change_password.html')

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Handle forgotten password requests"""
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Please enter your email address.', 'warning')
            return render_template('forgot_password.html')
        
        try:
            employee = Employee.query.filter_by(email=email).first()
            
            # Always show the same message to prevent email enumeration
            flash('If the email exists in our system, you will receive password reset instructions.', 'info')
            
            if employee:
                # In production, generate token and send email
                # For now, just log it
                logger.info(f"Password reset requested for: {email}")
                
                # TODO: Implement email sending
                # - Generate secure token
                # - Save token with expiration
                # - Send email with reset link
            
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            logger.error(f"Forgot password error: {e}")
            flash('An error occurred. Please try again later.', 'danger')
            return render_template('forgot_password.html')
    
    # GET request - show forgot password form
    return render_template('forgot_password.html')

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password using token"""
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    try:
        # Find user with valid token
        employee = Employee.query.filter_by(reset_token=token).first()
        
        if not employee:
            flash('Invalid or expired reset link.', 'danger')
            return redirect(url_for('auth.login'))
        
        # Check token expiration
        if hasattr(employee, 'reset_token_expires'):
            if not employee.reset_token_expires or employee.reset_token_expires < datetime.utcnow():
                flash('Reset link has expired. Please request a new one.', 'danger')
                return redirect(url_for('auth.forgot_password'))
        
        if request.method == 'POST':
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            # Validate passwords
            if not new_password or not confirm_password:
                flash('Both password fields are required.', 'warning')
                return render_template('reset_password.html', token=token)
            
            if len(new_password) < 8:
                flash('Password must be at least 8 characters long.', 'warning')
                return render_template('reset_password.html', token=token)
            
            if new_password != confirm_password:
                flash('Passwords do not match.', 'warning')
                return render_template('reset_password.html', token=token)
            
            # Reset password
            employee.password_hash = generate_password_hash(new_password)
            employee.reset_token = None
            employee.reset_token_expires = None
            
            # Update password metadata
            if hasattr(employee, 'must_change_password'):
                employee.must_change_password = False
            if hasattr(employee, 'last_password_change'):
                employee.last_password_change = datetime.utcnow()
            
            db.session.commit()
            
            flash('Password reset successfully! You can now login.', 'success')
            return redirect(url_for('auth.login'))
        
        # GET request - show reset form
        return render_template('reset_password.html', token=token)
        
    except Exception as e:
        logger.error(f"Reset password error: {e}")
        flash('An error occurred. Please try again later.', 'danger')
        return redirect(url_for('auth.login'))
