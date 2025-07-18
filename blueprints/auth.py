from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from models import Employee
from datetime import date

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def index():
    return render_template('index.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        employee = Employee.query.filter_by(email=email).first()
        
        if employee and employee.check_password(password):
            login_user(employee)
            flash(f'Welcome back, {employee.name}!', 'success')
            
            # Redirect based on role
            if employee.is_supervisor:
                return redirect(url_for('main.dashboard'))
            else:
                return redirect(url_for('main.employee_dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.index'))
