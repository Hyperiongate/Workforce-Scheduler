# blueprints/auth.py - DIAGNOSTIC VERSION
"""
Authentication blueprint that shows what routes actually exist
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from models import db, Employee
from datetime import datetime
from werkzeug.security import check_password_hash, generate_password_hash

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def index():
    """Landing page - show available routes"""
    if current_user.is_authenticated:
        # Instead of redirecting to potentially non-existent routes,
        # show what routes are actually available
        routes = []
        for rule in current_app.url_map.iter_rules():
            if rule.endpoint != 'static':
                routes.append({
                    'endpoint': rule.endpoint,
                    'url': str(rule),
                    'methods': ', '.join(rule.methods - {'HEAD', 'OPTIONS'})
                })
        
        # Sort routes by URL
        routes.sort(key=lambda x: x['url'])
        
        # Create a simple HTML page showing available routes
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Workforce Scheduler - Home</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body>
            <div class="container mt-5">
                <h1>Welcome, {current_user.name}!</h1>
                <p class="lead">You are logged in as a {"Supervisor" if current_user.is_supervisor else "Employee"}</p>
                <hr>
                
                <h3>Available Routes in Your Application:</h3>
                <table class="table table-striped">
                    <thead>
                        <tr>
                            <th>URL</th>
                            <th>Endpoint</th>
                            <th>Methods</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        for route in routes:
            html += f"""
                        <tr>
                            <td><a href="{route['url']}">{route['url']}</a></td>
                            <td>{route['endpoint']}</td>
                            <td>{route['methods']}</td>
                        </tr>
            """
        
        html += """
                    </tbody>
                </table>
                
                <hr>
                <h3>Quick Links (Hardcoded - Should Work):</h3>
                <ul>
                    <li><a href="/logout">Logout</a></li>
                    <li><a href="/vacation-calendar">Vacation Calendar (if exists)</a></li>
                    <li><a href="/view-crews">View Crews (if exists)</a></li>
                    <li><a href="/upload-employees">Upload Employees (if exists)</a></li>
                </ul>
                
                <div class="alert alert-info mt-3">
                    <strong>Note:</strong> This diagnostic page shows all registered routes in your Flask application. 
                    Click on any URL to test if it works. If you get a 404, that route isn't properly registered.
                    If you get a 500, the route exists but has an error.
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    return redirect(url_for('auth.login'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    if current_user.is_authenticated:
        return redirect(url_for('auth.index'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)
        
        if not email or not password:
            flash('Please enter both email and password.', 'danger')
            return render_template('login.html')
        
        # Find employee by email
        try:
            employee = Employee.query.filter_by(email=email).first()
            
            if employee and employee.check_password(password):
                # Update last login
                employee.last_login = datetime.utcnow()
                db.session.commit()
                
                # Log the user in
                login_user(employee, remember=remember)
                
                flash(f'Welcome back, {employee.name}!', 'success')
                
                # Always redirect to index which shows available routes
                return redirect(url_for('auth.index'))
            else:
                flash('Invalid email or password.', 'danger')
        except Exception as e:
            flash(f'Login error: {str(e)}', 'danger')
            db.session.rollback()
    
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
    """Change password page"""
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
        
        try:
            # Update password
            current_user.set_password(new_password)
            if hasattr(current_user, 'needs_password_change'):
                current_user.needs_password_change = False
            db.session.commit()
            
            flash('Your password has been changed successfully!', 'success')
            return redirect(url_for('auth.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error changing password: {str(e)}', 'danger')
    
    return render_template('change_password.html')
