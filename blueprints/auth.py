# blueprints/auth.py
"""
Complete Authentication Blueprint
Handles all authentication routes with correct redirects
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from models import db, Employee
from datetime import datetime
from werkzeug.security import check_password_hash

# Create the blueprint
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def index():
    """Landing page - redirect to login or appropriate dashboard"""
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('main.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    
    # For non-authenticated users, show a landing page or redirect to login
    # Option 1: Redirect directly to login
    return redirect(url_for('auth.login'))
    
    # Option 2: Show a landing page (uncomment below and comment above)
    # return render_template('index.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    # If already logged in, redirect to appropriate dashboard
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('main.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        # Find employee by email
        employee = Employee.query.filter_by(email=email).first()
        
        if employee and employee.check_password(password):
            # Check if account is locked (if the field exists)
            if hasattr(employee, 'is_locked') and employee.is_locked():
                flash('Your account is temporarily locked due to too many failed login attempts. Please try again later.', 'danger')
                return render_template('login.html')
            
            # Reset login attempts on successful login (if method exists)
            if hasattr(employee, 'reset_login_attempts'):
                employee.reset_login_attempts()
            
            # Update last login (if field exists)
            if hasattr(employee, 'last_login'):
                employee.last_login = datetime.utcnow()
            
            db.session.commit()
            
            # Log the user in
            login_user(employee, remember=remember)
            
            # Check if password change is required (if field exists)
            if hasattr(employee, 'must_change_password') and employee.must_change_password:
                flash('You must change your password before continuing.', 'warning')
                return redirect(url_for('auth.change_password'))
            
            # Check for first login (if field exists)
            if hasattr(employee, 'first_login') and employee.first_login:
                employee.first_login = False
                db.session.commit()
                flash(f'Welcome to the Workforce Scheduler, {employee.name}! This is your first login.', 'success')
            else:
                flash(f'Welcome back, {employee.name}!', 'success')
            
            # Get the next page from query params, or default to dashboard
            next_page = request.args.get('next')
            
            # Security check - only redirect to relative URLs
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            
            # Default redirects based on role
            if employee.is_supervisor:
                return redirect(url_for('main.dashboard'))
            else:
                return redirect(url_for('main.employee_dashboard'))
        else:
            # Handle failed login attempt (if method exists)
            if employee and hasattr(employee, 'record_failed_login'):
                employee.record_failed_login()
                db.session.commit()
            
            flash('Invalid email or password. Please try again.', 'danger')
            return render_template('login.html')
    
    # GET request - show login form
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """Handle user logout"""
    # Store the user name before logging out
    user_name = current_user.name if current_user.is_authenticated else 'User'
    
    # Log out the user
    logout_user()
    
    # Clear session
    session.clear()
    
    flash(f'You have been logged out successfully. Goodbye, {user_name}!', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change user password"""
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate current password
        if not current_user.check_password(current_password):
            flash('Current password is incorrect.', 'danger')
            return render_template('change_password.html')
        
        # Validate new password
        if new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
            return render_template('change_password.html')
        
        if len(new_password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return render_template('change_password.html')
        
        # Check password complexity (optional)
        if new_password == current_password:
            flash('New password must be different from current password.', 'danger')
            return render_template('change_password.html')
        
        # Update password
        current_user.set_password(new_password)
        
        # Clear must_change_password flag if it exists
        if hasattr(current_user, 'must_change_password'):
            current_user.must_change_password = False
        
        # Update password change date if field exists
        if hasattr(current_user, 'password_changed_at'):
            current_user.password_changed_at = datetime.utcnow()
        
        db.session.commit()
        
        flash('Password changed successfully!', 'success')
        
        # Redirect to appropriate dashboard
        if current_user.is_supervisor:
            return redirect(url_for('main.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    
    # GET request - show change password form
    return render_template('change_password.html')

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Handle password reset requests"""
    if request.method == 'POST':
        email = request.form.get('email')
        employee = Employee.query.filter_by(email=email).first()
        
        # Always show the same message to prevent email enumeration
        flash('If an account exists with that email, password reset instructions have been sent.', 'info')
        
        if employee:
            # In a real application, you would:
            # 1. Generate a secure reset token
            # 2. Store it with an expiration time
            # 3. Send an email with a reset link
            # For now, we'll just log it
            print(f"Password reset requested for: {employee.email}")
            
            # Example of what you might do:
            # reset_token = generate_reset_token()
            # employee.reset_token = reset_token
            # employee.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
            # db.session.commit()
            # send_reset_email(employee.email, reset_token)
        
        return redirect(url_for('auth.login'))
    
    # GET request - show forgot password form
    return render_template('forgot_password.html')

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password with token"""
    # Find employee with valid reset token
    employee = Employee.query.filter_by(reset_token=token).first()
    
    if not employee:
        flash('Invalid or expired reset link.', 'danger')
        return redirect(url_for('auth.login'))
    
    # Check if token is expired (if expiration field exists)
    if hasattr(employee, 'reset_token_expires'):
        if employee.reset_token_expires < datetime.utcnow():
            flash('Reset link has expired. Please request a new one.', 'danger')
            return redirect(url_for('auth.forgot_password'))
    
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate passwords
        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', token=token)
        
        if len(new_password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return render_template('reset_password.html', token=token)
        
        # Update password
        employee.set_password(new_password)
        
        # Clear reset token
        employee.reset_token = None
        if hasattr(employee, 'reset_token_expires'):
            employee.reset_token_expires = None
        
        # Clear must_change_password flag if it exists
        if hasattr(employee, 'must_change_password'):
            employee.must_change_password = False
        
        db.session.commit()
        
        flash('Password has been reset successfully. You can now log in with your new password.', 'success')
        return redirect(url_for('auth.login'))
    
    # GET request - show reset password form
    return render_template('reset_password.html', token=token)

@auth_bp.route('/profile')
@login_required
def profile():
    """View user profile"""
    return render_template('profile.html', employee=current_user)

@auth_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Edit user profile"""
    if request.method == 'POST':
        # Update allowed fields
        current_user.phone = request.form.get('phone', '')
        current_user.emergency_contact = request.form.get('emergency_contact', '')
        current_user.emergency_phone = request.form.get('emergency_phone', '')
        
        # Don't allow users to change their own supervisor status
        # or other sensitive fields
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('auth.profile'))
    
    return render_template('edit_profile.html', employee=current_user)

# Error handler for login required
@auth_bp.errorhandler(401)
def unauthorized(error):
    """Handle unauthorized access"""
    flash('Please log in to access this page.', 'warning')
    return redirect(url_for('auth.login', next=request.url))
