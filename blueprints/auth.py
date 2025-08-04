from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from models import db, Employee
from datetime import datetime
from werkzeug.security import check_password_hash

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def index():
    """Landing page - redirect to login or dashboard"""
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('main.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    return render_template('index.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
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
            # Check if account is locked
            if hasattr(employee, 'is_locked') and employee.is_locked():
                flash('Your account is temporarily locked due to too many failed login attempts. Please try again later.', 'danger')
                return render_template('login.html')
            
            # Reset login attempts on successful login
            if hasattr(employee, 'reset_login_attempts'):
                employee.reset_login_attempts()
            
            # Update last login
            if hasattr(employee, 'last_login'):
                employee.last_login = datetime.utcnow()
            
            db.session.commit()
            
            # Log the user in
            login_user(employee, remember=remember)
            
            # Check if password change is required
            if hasattr(employee, 'must_change_password') and employee.must_change_password:
                flash('You must change your password before continuing.', 'warning')
                return redirect(url_for('auth.change_password'))
            
            # Check for first login
            if hasattr(employee, 'first_login') and employee.first_login:
                employee.first_login = False
                db.session.commit()
                flash(f'Welcome to the Workforce Scheduler, {employee.name}! This is your first login.', 'success')
            else:
                flash(f'Welcome back, {employee.name}!', 'success')
            
            # Redirect to appropriate dashboard
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            elif employee.is_supervisor:
                return redirect(url_for('main.dashboard'))
            else:
                return redirect(url_for('main.employee_dashboard'))
        else:
            # Invalid credentials
            if employee:
                # Increment failed login attempts
                if hasattr(employee, 'increment_login_attempts'):
                    employee.increment_login_attempts()
                    db.session.commit()
                    
                    if employee.login_attempts >= 5:
                        flash('Too many failed login attempts. Your account has been temporarily locked.', 'danger')
                    else:
                        remaining_attempts = 5 - employee.login_attempts
                        flash(f'Invalid email or password. {remaining_attempts} attempts remaining.', 'danger')
                else:
                    flash('Invalid email or password.', 'danger')
            else:
                flash('Invalid email or password.', 'danger')
    
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """Handle user logout"""
    logout_user()
    # Clear any session data
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Force password change for new users or password resets"""
    if request.metho
