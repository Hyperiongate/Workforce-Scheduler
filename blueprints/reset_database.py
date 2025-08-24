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
            'overtime_history',
            'file_upload',
            'shift_swap_request',
            'time_off_request',
            'schedule',
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
        
        # Create tables with correct schema
        logger.info("Creating new tables...")
        
        # Create position table
        db.session.execute(text("""
            CREATE TABLE position (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Create employee table with all needed columns
        db.session.execute(text("""
            CREATE TABLE employee (
                id SERIAL PRIMARY KEY,
                employee_id VARCHAR(50) UNIQUE,
                first_name VARCHAR(100),
                last_name VARCHAR(100),
                name VARCHAR(255),
                email VARCHAR(255),
                password_hash VARCHAR(255),
                crew VARCHAR(10),
                position_id INTEGER REFERENCES position(id),
                department VARCHAR(100),
                hire_date DATE,
                phone VARCHAR(20),
                is_active BOOLEAN DEFAULT TRUE,
                is_supervisor BOOLEAN DEFAULT FALSE,
                is_admin BOOLEAN DEFAULT FALSE,
                max_hours_per_week INTEGER DEFAULT 40,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Create file_upload table with all columns
        db.session.execute(text("""
            CREATE TABLE file_upload (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                upload_type VARCHAR(50),
                file_type VARCHAR(50),
                uploaded_by_id INTEGER REFERENCES employee(id),
                total_records INTEGER DEFAULT 0,
                successful_records INTEGER DEFAULT 0,
                failed_records INTEGER DEFAULT 0,
                records_processed INTEGER DEFAULT 0,
                records_failed INTEGER DEFAULT 0,
                error_details TEXT,
                status VARCHAR(50) DEFAULT 'pending',
                file_path VARCHAR(255),
                file_size INTEGER,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Create overtime_history table
        db.session.execute(text("""
            CREATE TABLE overtime_history (
                id SERIAL PRIMARY KEY,
                employee_id INTEGER REFERENCES employee(id),
                week_starting DATE NOT NULL,
                hours DECIMAL(5,2) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(employee_id, week_starting)
            )
        """))
        
        # Create other tables as needed
        db.session.execute(text("""
            CREATE TABLE time_off_request (
                id SERIAL PRIMARY KEY,
                employee_id INTEGER REFERENCES employee(id),
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                request_type VARCHAR(50),
                type VARCHAR(50),
                reason TEXT,
                status VARCHAR(50) DEFAULT 'pending',
                approved_by_id INTEGER REFERENCES employee(id),
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                approved_date TIMESTAMP
            )
        """))
        
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
        
        for pos in default_positions:
            db.session.execute(text("""
                INSERT INTO position (name) VALUES (:name)
            """), {"name": pos})
        
        db.session.commit()
        logger.info("Added default positions")
        
        # Re-create the supervisor account
        db.session.execute(text("""
            INSERT INTO employee (
                id, employee_id, email, password_hash, name, 
                is_supervisor, is_admin, is_active, crew
            ) VALUES (
                :id, 'SUP001', :email, :password_hash, :name,
                TRUE, TRUE, TRUE, 'A'
            )
        """), {
            "id": current_user_id,
            "email": current_user.email,
            "password_hash": current_user.password_hash,
            "name": current_user.name
        })
        
        db.session.commit()
        logger.info("Recreated supervisor account")
        
        flash('✅ Database reset successful! You can now upload employee data.', 'success')
        return redirect(url_for('reset_db.reset_database_page'))
        
    except Exception as e:
        logger.error(f"Database reset failed: {e}")
        db.session.rollback()
        flash(f'❌ Reset failed: {str(e)}', 'danger')
        return redirect(url_for('reset_db.reset_database_page'))
