# blueprints/main.py
from flask import Blueprint, render_template, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, Employee, TimeOffRequest, ShiftSwapRequest, CoverageGap, MaintenanceIssue
from datetime import datetime, date, timedelta
from functools import wraps

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

@main_bp.route('/')
def index():
    """Landing page - redirect based on authentication"""
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('main.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    return render_template('index.html')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - redirect based on role"""
    if current_user.is_supervisor:
        return redirect(url_for('supervisor.dashboard'))
    else:
        return redirect(url
