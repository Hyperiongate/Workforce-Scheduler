# reset_database.py
"""
Simple database reset page with a button
Add this file to your blueprints folder
"""

from flask import Blueprint, render_template_string, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db
from sqlalchemy import text
from functools import wraps
import logging

logger = logging.getLogger(__name__)

reset_db_bp = Blueprint('reset_db', __name__)

def supervisor_required(f):
    """Decorator to require supervisor access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.is_supervisor:
            flash('Access denied. Supervisors only.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Simple HTML template with a reset button
RESET_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Reset Database</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            background-color: #f8f9fa;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }
        .reset-container {
            background: white;
            padding: 3rem;
            border-radius: 10px;
            box-shadow: 0 0 20px rgba(0,0,0,0.1);
            text-align: center;
            max-width: 500px;
        }
        .warning-box {
            background-color: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 5px;
            padding: 1rem;
            margin: 1.5rem 0;
        }
        .btn-reset {
            background-color: #dc3545;
            color: white;
            padding: 12px 30px;
            font-size: 1.1rem;
            margin-top: 1rem;
        }
        .btn-reset:hover {
            background-color: #bb2d3b;
            color: white;
        }
    </style>
</head>
<body>
    <div class="reset-container">
        <h1>🔄 Reset Database</h1>
        
        <div class="warning-box">
            <h4>⚠️ Warning!</h4>
            <p>This will:</p>
            <ul class="text-start">
                <li>Delete ALL employee data (except your supervisor account)</li>
                <li>Fix all database structure issues</li>
                <li>Allow uploads to work properly</li>
            </ul>
            <p class="mb-0"><strong>This cannot be undone!</strong></p>
        </div>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ 'success' if category == 'success' else 'danger' }} alert-dismissible fade show" role="alert">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <form method="POST" action="{{ url_for('reset_db.reset_database') }}">
            <button type="submit" class="btn btn-reset" onclick="return confirm('Are you SURE you want to reset the database? This will delete all employee data!')">
                Reset Database Now
            </button>
        </form>
        
        <a href="{{ url_for('supervisor.dashboard') }}" class="btn btn-secondary mt-3">
            Cancel and Go Back
        </a>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

@reset_db_bp.route('/reset-database')
@login_required
@supervisor_required
def reset_database_page():
    """Show the reset database page"""
    return render_template_string(RESET_PAGE_HTML)

@reset_db_bp.route('/reset-database', methods=['POST'])
@login_required
@supervisor_required
def reset_database():
    """Actually reset the database"""
    try:
        # Keep the current user's ID to preserve their account
        current_user_id = current_user.id
        
        logger.info("Starting database reset...")
        
        # Drop and recreate tables
        logger.info("Dropping old tables...")
        
        # Drop tables in correct order (handle foreign key constraints)
        tables_to_drop = [
            'upload_history',
            'vacation_calendar',
            'crew_coverage_requirement',
            'file_upload',
            'coverage_request',
            'casual_worker',
            'sleep_log',
            'circadian_profile',
            'maintenance_comment',
            'maintenance_issue',
            'maintenance_update',
            'equipment',
            'communication_attachment',
            'communication_read_receipt',
            'communication_message',
            'communication_category',
            'position_message_read_receipt',
            'position_message',
            'supervisor_message',
            'message_read_receipt',
            'coverage_gap',
            'overtime_history',
            'shift_trade_post',
            'shift_swap_request',
            'availability',
            'time_off_request',
            'schedule',
            'employee_skill',
            'skill_requirement',
            'skill',
            'employee',
            'position'
        ]
        
        for table in tables_to_drop:
            try:
                db.session.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                db.session.commit()
                logger.info(f"Dropped table: {table}")
            except Exception as e:
                logger.warning(f"Could not drop {table}: {e}")
                db.session.rollback()
        
        # Recreate all tables
        logger.info("Creating new tables...")
        db.create_all()
        db.session.commit()
        logger.info("Created all tables")
        
        # Add default positions
        default_positions = [
            'Operator',
            'Senior Operator', 
            'Lead Operator',
            'Maintenance Technician',
            'Electrician',
            'Mechanic',
            'Control Room Operator',
            'Shift Supervisor',
            'Process Engineer',
            'Safety Coordinator'
        ]
        
        from models import Position
        for pos_name in default_positions:
            position = Position(name=pos_name)
            db.session.add(position)
        
        db.session.commit()
        logger.info("Added default positions")
        
        # Re-create the supervisor account
        from models import Employee
        
        # First check if there's already an admin user (from fix-db-now)
        admin_user = Employee.query.filter_by(email='admin@workforce.com').first()
        
        if not admin_user:
            # Re-create the current supervisor user
            supervisor = Employee(
                id=current_user_id,
                employee_id=current_user.employee_id or 'SUP001',
                email=current_user.email,
                password_hash=current_user.password_hash,
                name=current_user.name,
                is_supervisor=True,
                is_admin=True,
                is_active=True,
                crew='A',
                department='Management'
            )
            db.session.add(supervisor)
            db.session.commit()
            logger.info("Recreated supervisor account")
        else:
            logger.info("Admin account already exists")
        
        flash('✅ Database reset successful! You can now upload employee data.', 'success')
        return redirect(url_for('reset_db.reset_database_page'))
        
    except Exception as e:
        logger.error(f"Database reset failed: {e}")
        db.session.rollback()
        flash(f'❌ Reset failed: {str(e)}', 'danger')
        return redirect(url_for('reset_db.reset_database_page'))
