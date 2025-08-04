# blueprints/auth.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from models import Employee, db
from datetime import datetime, timedelta
import re

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Enhanced login with first login detection"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Please enter both username and password', 'error')
            return render_template('login.html')
            
        # Find employee by username
        employee = Employee.query.filter_by(username=username).first()
        
        if not employee:
            flash('Invalid username or password', 'error')
            return render_template('login.html')
            
        # Check if account is locked
        if employee.is_locked():
            flash('Account is locked due to too many failed attempts. Please try again later.', 'error')
            return render_template('login.html')
            
        # Check password
        if not employee.check_password(password):
            employee.increment_login_attempts()
            db.session.commit()
            flash('Invalid username or password', 'error')
            return render_template('login.html')
            
        # Successful login
        employee.reset_login_attempts()
        db.session.commit()
        
        # Log the user in
        login_user(employee)
        
        # Check if first login or must change password
        if employee.first_login or employee.must_change_password:
            flash('You must change your password before continuing.', 'info')
            return redirect(url_for('auth.change_password'))
            
        # Regular login - redirect to appropriate dashboard
        if employee.is_supervisor:
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('employee.dashboard'))
            
    return render_template('login.html')


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Force password change for first login"""
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate current password
        if not current_user.check_password(current_password):
            flash('Current password is incorrect', 'error')
            return render_template('change_password.html', first_login=current_user.first_login)
            
        # Validate new password
        error = validate_password(new_password)
        if error:
            flash(error, 'error')
            return render_template('change_password.html', first_login=current_user.first_login)
            
        # Check password match
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return render_template('change_password.html', first_login=current_user.first_login)
            
        # Check not same as current
        if current_user.check_password(new_password):
            flash('New password must be different from current password', 'error')
            return render_template('change_password.html', first_login=current_user.first_login)
            
        # Update password
        current_user.set_password(new_password)
        current_user.must_change_password = False
        current_user.first_login = False
        current_user.last_password_change = datetime.utcnow()
        db.session.commit()
        
        flash('Password changed successfully!', 'success')
        
        # Redirect to appropriate dashboard
        if current_user.is_supervisor:
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('employee.dashboard'))
            
    return render_template('change_password.html', first_login=current_user.first_login)


@auth_bp.route('/password-reset-request', methods=['GET', 'POST'])
def password_reset_request():
    """Request password reset"""
    if request.method == 'POST':
        username = request.form.get('username')
        
        employee = Employee.query.filter_by(username=username).first()
        if employee and employee.email:
            # Generate reset token
            token = employee.generate_reset_token()
            db.session.commit()
            
            # TODO: Send email with reset link
            # For now, just flash the link (remove in production!)
            reset_url = url_for('auth.password_reset', token=token, _external=True)
            flash(f'Password reset link would be sent to {employee.email}', 'info')
            # In development, show the link
            flash(f'Development only - Reset link: {reset_url}', 'warning')
            
        else:
            # Don't reveal if username exists
            flash('If an account exists with that username, reset instructions will be sent.', 'info')
            
        return redirect(url_for('auth.login'))
        
    return render_template('password_reset_request.html')


@auth_bp.route('/password-reset/<token>', methods=['GET', 'POST'])
def password_reset(token):
    """Reset password with token"""
    # Find employee with this token
    employee = Employee.query.filter_by(reset_token=token).first()
    
    if not employee or not employee.validate_reset_token(token):
        flash('Invalid or expired reset link', 'error')
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate new password
        error = validate_password(new_password)
        if error:
            flash(error, 'error')
            return render_template('password_reset.html', token=token)
            
        # Check password match
        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('password_reset.html', token=token)
            
        # Update password
        employee.set_password(new_password)
        employee.reset_token = None
        employee.reset_token_expires = None
        employee.must_change_password = False
        employee.last_password_change = datetime.utcnow()
        db.session.commit()
        
        flash('Password reset successfully! Please log in with your new password.', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('password_reset.html', token=token)


def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return "Password must be at least 8 characters long"
        
    if not re.search(r'[A-Z]', password):
        return "Password must contain at least one uppercase letter"
        
    if not re.search(r'[a-z]', password):
        return "Password must contain at least one lowercase letter"
        
    if not re.search(r'\d', password):
        return "Password must contain at least one number"
        
    # Optional: require special character
    # if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
    #     return "Password must contain at least one special character"
        
    return None  # Password is valid


# Add this to handle unauthorized access
@auth_bp.route('/unauthorized')
def unauthorized():
    """Handle unauthorized access attempts"""
    flash('You must be logged in to access that page.', 'warning')
    return redirect(url_for('auth.login'))


# Update logout to clear session properly
@auth_bp.route('/logout')
@login_required
def logout():
    """Enhanced logout"""
    logout_user()
    session.clear()  # Clear all session data
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


# Add middleware to check password change requirement
@auth_bp.before_app_request
def check_password_change():
    """Check if user needs to change password"""
    if current_user.is_authenticated:
        # Skip check for static files and auth routes
        if request.endpoint and (
            request.endpoint.startswith('static') or 
            request.endpoint.startswith('auth.')
        ):
            return
            
        # Force password change if needed
        if current_user.must_change_password:
            if request.endpoint != 'auth.change_password':
                flash('You must change your password before continuing.', 'warning')
                return redirect(url_for('auth.change_password'))
