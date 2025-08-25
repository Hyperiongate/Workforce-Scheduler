#!/usr/bin/env python3
"""
Main application file for Workforce Scheduler
COMPLETE FILE with all diagnostic routes and supervisor dashboard debug
"""

from flask import Flask, render_template, redirect, url_for, flash, jsonify, request
from flask_login import LoginManager, login_required, current_user, login_user
from flask_migrate import Migrate
import os
import logging
from datetime import datetime, date, timedelta
from sqlalchemy import text, inspect
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import OperationalError, ProgrammingError
from werkzeug.security import generate_password_hash, check_password_hash

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Database configuration
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'poolclass': NullPool,
        'connect_args': {
            'sslmode': 'require',
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 5,
            'keepalives_count': 5
        }
    }
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workforce.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Upload configuration
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'upload_files')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'xls', 'xlsx'}

# Ensure upload folder exists
try:
    if os.path.exists(app.config['UPLOAD_FOLDER']):
        if not os.path.isdir(app.config['UPLOAD_FOLDER']):
            os.remove(app.config['UPLOAD_FOLDER'])
            os.makedirs(app.config['UPLOAD_FOLDER'])
    else:
        os.makedirs(app.config['UPLOAD_FOLDER'])
except Exception as e:
    logger.warning(f"Could not create upload folder: {e}")
    import tempfile
    app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

# Initialize extensions
from models import db
db.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'

# Import models after db initialization
from models import Employee, TimeOffRequest, ShiftSwapRequest

@login_manager.user_loader
def load_user(user_id):
    return Employee.query.get(int(user_id))

# TEST SUPERVISOR DASHBOARD ROUTE
@app.route('/test-supervisor-dashboard')
def test_supervisor_dashboard():
    """Test what's causing the 500 error"""
    results = []
    
    # Test 1: Can we import the blueprint?
    try:
        from blueprints.supervisor import supervisor_bp
        results.append("✅ Supervisor blueprint imports successfully")
    except Exception as e:
        results.append(f"❌ Blueprint import error: {str(e)}")
        import traceback
        results.append(f"<pre>{traceback.format_exc()}</pre>")
        
    # Test 2: Check if user is logged in and is supervisor
    try:
        from flask_login import current_user
        if current_user.is_authenticated:
            results.append(f"✅ User logged in: {current_user.email}, Supervisor: {getattr(current_user, 'is_supervisor', 'Unknown')}")
        else:
            results.append("❌ No user logged in - <a href='/login'>Login here</a>")
    except Exception as e:
        results.append(f"❌ Auth check error: {str(e)}")
        
    # Test 3: Check database models
    try:
        from models import Employee, TimeOffRequest, ShiftSwapRequest
        emp_count = Employee.query.count()
        results.append(f"✅ Database works: {emp_count} employees found")
    except Exception as e:
        results.append(f"❌ Database error: {str(e)}")
        
    # Test 4: Check if templates exist
    import os
    templates = ['supervisor_dashboard_enhanced.html', 'supervisor_dashboard.html']
    template_results = []
    for t in templates:
        path = os.path.join('templates', t)
        if os.path.exists(path):
            template_results.append(f"✅ {t} exists")
        else:
            template_results.append(f"❌ {t} missing")
    results.extend(template_results)
    
    # Test 5: Check specific imports that might fail
    try:
        from models import SupervisorMessage, VacationCalendar, Schedule, Position, OvertimeHistory
        results.append("✅ All model imports successful")
    except ImportError as e:
        results.append(f"❌ Model import error: {str(e)}")
        
    # Test 6: Check pandas import
    try:
        import pandas as pd
        results.append("✅ Pandas installed")
    except ImportError:
        results.append("❌ Pandas not installed - run: pip install pandas")
    
    return f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial; padding: 40px; background: #f5f5f5; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }}
            .success {{ color: green; }}
            .error {{ color: red; }}
            h1 {{ color: #333; }}
            p {{ margin: 10px 0; padding: 10px; background: #f9f9f9; border-radius: 5px; }}
            pre {{ background: #f0f0f0; padding: 10px; border-radius: 5px; overflow-x: auto; }}
            .btn {{ display: inline-block; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Supervisor Dashboard Debug Results</h1>
            {"".join(f"<p>{result}</p>" for result in results)}
            <hr>
            <a href="/supervisor/dashboard" class="btn">Try Dashboard</a>
            <a href="/force-login" class="btn" style="background: #28a745;">Force Login as Admin</a>
        </div>
    </body>
    </html>
    """

# DATABASE FIX ROUTE
@app.route('/fix-db-now')
def fix_db_now():
    """Complete database fix - final version after dry run"""
    fixes_applied = []
    errors = []
    
    try:
        # Step 1: Clear any aborted transaction
        db.session.rollback()
        db.session.close()
        logger.info("Cleared any existing transaction issues")
        
        # Step 2: Add ALL missing columns based on Employee model
        with db.engine.begin() as conn:
            # Get current columns
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'employee'
            """))
            existing_columns = {row[0] for row in result}
            logger.info(f"Existing columns: {existing_columns}")
            
            # Define all columns from the Employee model
            required_columns = [
                # Core fields
                ('email', 'VARCHAR(120)', 'UNIQUE NOT NULL'),
                ('password_hash', 'VARCHAR(255)', ''),
                ('name', 'VARCHAR(100)', 'NOT NULL'),
                ('employee_id', 'VARCHAR(50)', 'UNIQUE'),
                ('phone', 'VARCHAR(20)', ''),
                
                # Work info
                ('position_id', 'INTEGER', ''),
                ('department', 'VARCHAR(50)', ''),
                ('crew', 'VARCHAR(1)', ''),
                ('is_supervisor', 'BOOLEAN', 'DEFAULT FALSE'),
                ('is_admin', 'BOOLEAN', 'DEFAULT FALSE'),
                ('hire_date', 'DATE', ''),
                
                # Availability
                ('is_active', 'BOOLEAN', 'DEFAULT TRUE'),
                ('max_hours_per_week', 'INTEGER', 'DEFAULT 48'),
                
                # Timestamps
                ('created_at', 'TIMESTAMP', 'DEFAULT CURRENT_TIMESTAMP'),
                ('updated_at', 'TIMESTAMP', 'DEFAULT CURRENT_TIMESTAMP')
            ]
            
            # Add each missing column
            for col_name, col_type, constraints in required_columns:
                if col_name not in existing_columns:
                    try:
                        if constraints:
                            sql = f"ALTER TABLE employee ADD COLUMN {col_name} {col_type} {constraints}"
                        else:
                            sql = f"ALTER TABLE employee ADD COLUMN {col_name} {col_type}"
                        
                        conn.execute(text(sql))
                        fixes_applied.append(f"Added {col_name}")
                        logger.info(f"Added column {col_name}")
                    except Exception as e:
                        error_msg = str(e).lower()
                        if "already exists" not in error_msg and "duplicate column" not in error_msg:
                            errors.append(f"{col_name}: {str(e)}")
                            logger.error(f"Error adding {col_name}: {e}")
        
        # Step 3: Create or update admin user
        with db.engine.begin() as conn:
            try:
                # Generate password hash
                password_hash = generate_password_hash('admin123')
                
                # Check if admin exists
                result = conn.execute(text("""
                    SELECT id, email, name, is_admin, is_supervisor 
                    FROM employee 
                    WHERE email = 'admin@workforce.com'
                """))
                admin_row = result.fetchone()
                
                if admin_row:
                    # Update existing admin
                    conn.execute(text("""
                        UPDATE employee 
                        SET password_hash = :password_hash,
                            name = :name,
                            employee_id = :employee_id,
                            is_supervisor = :is_supervisor,
                            is_admin = :is_admin,
                            is_active = :is_active,
                            department = :department,
                            crew = :crew
                        WHERE email = :email
                    """), {
                        'password_hash': password_hash,
                        'name': 'Admin User',
                        'employee_id': 'ADMIN001',
                        'is_supervisor': True,
                        'is_admin': True,
                        'is_active': True,
                        'department': 'Administration',
                        'crew': 'A',
                        'email': 'admin@workforce.com'
                    })
                    fixes_applied.append("Updated admin user")
                    logger.info("Updated existing admin user")
                else:
                    # Create new admin - only required fields are email and name
                    conn.execute(text("""
                        INSERT INTO employee (
                            email, 
                            password_hash, 
                            name,
                            employee_id,
                            is_supervisor, 
                            is_admin, 
                            is_active,
                            department,
                            crew
                        ) VALUES (
                            :email,
                            :password_hash,
                            :name,
                            :employee_id,
                            :is_supervisor,
                            :is_admin,
                            :is_active,
                            :department,
                            :crew
                        )
                    """), {
                        'email': 'admin@workforce.com',
                        'password_hash': password_hash,
                        'name': 'Admin User',
                        'employee_id': 'ADMIN001',
                        'is_supervisor': True,
                        'is_admin': True,
                        'is_active': True,
                        'department': 'Administration',
                        'crew': 'A'
                    })
                    fixes_applied.append("Created admin user")
                    logger.info("Created new admin user")
                    
            except Exception as e:
                errors.append(f"Admin user: {str(e)}")
                logger.error(f"Error with admin user: {e}")
        
        # Build response
        success = len(errors) == 0
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Database Fix - {'Success' if success else 'Partial Success'}</title>
            <style>
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    margin: 0;
                    padding: 0;
                    background: #f5f7fa;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                }}
                .container {{
                    background: white;
                    padding: 40px;
                    border-radius: 12px;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.08);
                    max-width: 600px;
                    width: 90%;
                }}
                h1 {{ 
                    color: {'#28a745' if success else '#ffc107'};
                    margin: 0 0 24px 0;
                    font-size: 28px;
                }}
                .status-icon {{
                    font-size: 48px;
                    margin-bottom: 16px;
                }}
                .info-box {{
                    background: #e7f3ff;
                    border-left: 4px solid #2196F3;
                    padding: 20px;
                    margin: 24px 0;
                    border-radius: 4px;
                }}
                .info-box h3 {{
                    margin: 0 0 12px 0;
                    color: #1976D2;
                }}
                .success-list {{
                    background: #d4edda;
                    border: 1px solid #c3e6cb;
                    color: #155724;
                    padding: 16px;
                    border-radius: 4px;
                    margin: 16px 0;
                }}
                .error-list {{
                    background: #f8d7da;
                    border: 1px solid #f5c6cb;
                    color: #721c24;
                    padding: 16px;
                    border-radius: 4px;
                    margin: 16px 0;
                }}
                ul {{
                    margin: 8px 0;
                    padding-left: 24px;
                }}
                li {{
                    margin: 4px 0;
                }}
                .btn {{
                    display: inline-block;
                    padding: 12px 32px;
                    background: #007bff;
                    color: white;
                    text-decoration: none;
                    border-radius: 6px;
                    margin-top: 24px;
                    font-weight: 500;
                    transition: all 0.3s;
                }}
                .btn:hover {{
                    background: #0056b3;
                    transform: translateY(-1px);
                    box-shadow: 0 4px 12px rgba(0,123,255,0.3);
                }}
                .note {{
                    color: #6c757d;
                    font-size: 14px;
                    margin-top: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="status-icon">{'✅' if success else '⚠️'}</div>
                <h1>Database Fix {'Complete' if success else 'Completed with Warnings'}</h1>
                
                {f'''
                <div class="success-list">
                    <strong>Successfully Applied Fixes:</strong>
                    <ul>
                        {"".join(f"<li>{fix}</li>" for fix in fixes_applied) if fixes_applied else "<li>No fixes needed - database already up to date</li>"}
                    </ul>
                </div>
                ''' if fixes_applied else ''}
                
                {f'''
                <div class="error-list">
                    <strong>Errors Encountered:</strong>
                    <ul>
                        {"".join(f"<li>{error}</li>" for error in errors)}
                    </ul>
                </div>
                ''' if errors else ''}
                
                <div class="info-box">
                    <h3>Admin Login Credentials:</h3>
                    <p><strong>Email:</strong> admin@workforce.com<br>
                    <strong>Password:</strong> admin123</p>
                    <p class="note">Please change this password after your first login!</p>
                </div>
                
                <a href="/login" class="btn">Go to Login Page →</a>
            </div>
        </body>
        </html>
        """
            
    except Exception as e:
        # Critical error
        db.session.rollback()
        logger.error(f"Critical error in fix_db_now: {e}")
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Database Fix - Error</title>
            <style>
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    margin: 0;
                    padding: 0;
                    background: #f5f7fa;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                }}
                .container {{
                    background: white;
                    padding: 40px;
                    border-radius: 12px;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.08);
                    max-width: 600px;
                    width: 90%;
                }}
                h1 {{ 
                    color: #dc3545;
                    margin: 0 0 24px 0;
                }}
                pre {{
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 6px;
                    overflow-x: auto;
                    border: 1px solid #dee2e6;
                    font-size: 14px;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                }}
                .btn {{
                    display: inline-block;
                    padding: 12px 32px;
                    background: #6c757d;
                    color: white;
                    text-decoration: none;
                    border-radius: 6px;
                    margin-top: 24px;
                    font-weight: 500;
                }}
                .btn:hover {{
                    background: #5a6268;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>❌ Critical Error</h1>
                <p>A critical error occurred while attempting to fix the database:</p>
                <pre>{str(e)}</pre>
                <p>Please check the server logs for more details.</p>
                <a href="/fix-db-now" class="btn">Try Again</a>
            </div>
        </body>
        </html>
        """

# DIAGNOSTIC ROUTE
@app.route('/check-admin')
def check_admin():
    """Diagnostic route to check admin user status"""
    try:
        with db.engine.connect() as conn:
            # Check if admin exists
            result = conn.execute(text("""
                SELECT id, email, name, password_hash, 
                       is_admin, is_supervisor, is_active,
                       LENGTH(password_hash) as hash_length
                FROM employee 
                WHERE email = 'admin@workforce.com'
            """))
            admin = result.fetchone()
            
            if not admin:
                return """
                <html>
                <body style="font-family: Arial; padding: 40px;">
                    <h1 style="color: red;">❌ Admin User Not Found</h1>
                    <p>The admin@workforce.com user does not exist in the database.</p>
                    <p><a href="/fix-db-now" style="padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 5px;">Run Database Fix</a></p>
                </body>
                </html>
                """
            
            # Test password
            test_result = "Unknown"
            if admin[3]:  # password_hash
                try:
                    # Test if the hash is valid
                    is_valid = check_password_hash(admin[3], 'admin123')
                    test_result = "✅ Password hash is valid" if is_valid else "❌ Password hash does NOT match 'admin123'"
                except Exception as e:
                    test_result = f"❌ Error testing password: {str(e)}"
            else:
                test_result = "❌ No password hash found"
            
            return f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial; padding: 40px; background: #f5f5f5; }}
                    .container {{ background: white; padding: 30px; border-radius: 10px; max-width: 800px; margin: 0 auto; }}
                    table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                    th {{ background: #007bff; color: white; padding: 10px; text-align: left; }}
                    td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
                    .good {{ color: green; font-weight: bold; }}
                    .bad {{ color: red; font-weight: bold; }}
                    .btn {{ display: inline-block; padding: 10px 20px; background: #28a745; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Admin User Diagnostic</h1>
                    <table>
                        <tr><th>Field</th><th>Value</th><th>Status</th></tr>
                        <tr><td>ID</td><td>{admin[0]}</td><td class="good">✓</td></tr>
                        <tr><td>Email</td><td>{admin[1]}</td><td class="good">✓</td></tr>
                        <tr><td>Name</td><td>{admin[2] or 'NULL'}</td><td class="{'good' if admin[2] else 'bad'}">{'✓' if admin[2] else '✗'}</td></tr>
                        <tr><td>Has Password Hash</td><td>{'Yes' if admin[3] else 'No'}</td><td class="{'good' if admin[3] else 'bad'}">{'✓' if admin[3] else '✗'}</td></tr>
                        <tr><td>Hash Length</td><td>{admin[7] or 0} chars</td><td class="{'good' if admin[7] and admin[7] > 50 else 'bad'}">{'✓' if admin[7] and admin[7] > 50 else '✗'}</td></tr>
                        <tr><td>Is Admin</td><td>{admin[4]}</td><td class="{'good' if admin[4] else 'bad'}">{'✓' if admin[4] else '✗'}</td></tr>
                        <tr><td>Is Supervisor</td><td>{admin[5]}</td><td class="{'good' if admin[5] else 'bad'}">{'✓' if admin[5] else '✗'}</td></tr>
                        <tr><td>Is Active</td><td>{admin[6]}</td><td class="{'good' if admin[6] else 'bad'}">{'✓' if admin[6] else '✗'}</td></tr>
                    </table>
                    
                    <h3>Password Test:</h3>
                    <p>{test_result}</p>
                    
                    <h3>Next Steps:</h3>
                    <ol>
                        <li>If password test failed, run <a href="/fix-db-now">/fix-db-now</a> again</li>
                        <li>If all checks pass, try <a href="/login">logging in</a></li>
                        <li>Make sure you're using email: <code>admin@workforce.com</code> and password: <code>admin123</code></li>
                    </ol>
                    
                    <a href="/login" class="btn">Try Login</a>
                </div>
            </body>
            </html>
            """
            
    except Exception as e:
        return f"""
        <html>
        <body style="font-family: Arial; padding: 40px;">
            <h1 style="color: red;">❌ Diagnostic Error</h1>
            <pre style="background: #f8f9fa; padding: 20px; border-radius: 5px;">{str(e)}</pre>
            <p><a href="/fix-db-now">Try Running Fix Again</a></p>
        </body>
        </html>
        """

# PASSWORD RESET ROUTE
@app.route('/reset-admin-password')
def reset_admin_password():
    """Emergency route to reset admin password"""
    try:
        # Generate new password hash
        new_password_hash = generate_password_hash('admin123')
        
        with db.engine.begin() as conn:
            # Update admin password
            result = conn.execute(text("""
                UPDATE employee 
                SET password_hash = :password_hash,
                    is_admin = true,
                    is_supervisor = true,
                    is_active = true
                WHERE email = 'admin@workforce.com'
                RETURNING id, email
            """), {'password_hash': new_password_hash})
            
            updated = result.fetchone()
            
            if updated:
                return f"""
                <html>
                <head>
                    <style>
                        body {{ font-family: Arial; padding: 40px; background: #f5f5f5; }}
                        .container {{ background: white; padding: 30px; border-radius: 10px; max-width: 600px; margin: 0 auto; }}
                        .success {{ background: #d4edda; border: 1px solid #c3e6cb; color: #155724; padding: 20px; border-radius: 5px; }}
                        .credentials {{ background: #e7f3ff; border-left: 4px solid #2196F3; padding: 20px; margin: 20px 0; }}
                        .btn {{ display: inline-block; padding: 12px 30px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>✅ Password Reset Successful!</h1>
                        
                        <div class="success">
                            <p>Admin password has been reset successfully.</p>
                            <p>User ID: {updated[0]}, Email: {updated[1]}</p>
                        </div>
                        
                        <div class="credentials">
                            <h3>Login Credentials:</h3>
                            <p><strong>Email:</strong> admin@workforce.com<br>
                            <strong>Password:</strong> admin123</p>
                        </div>
                        
                        <a href="/login" class="btn">Go to Login</a>
                    </div>
                </body>
                </html>
                """
            else:
                # Admin doesn't exist, create it
                conn.execute(text("""
                    INSERT INTO employee (email, password_hash, name, is_admin, is_supervisor, is_active)
                    VALUES ('admin@workforce.com', :password_hash, 'Admin User', true, true, true)
                """), {'password_hash': new_password_hash})
                
                return """
                <html>
                <body style="font-family: Arial; padding: 40px;">
                    <h1 style="color: green;">✅ Admin User Created!</h1>
                    <p>Admin user was missing and has been created.</p>
                    <div style="background: #f0f0f0; padding: 20px; margin: 20px 0; border-radius: 5px;">
                        <strong>Email:</strong> admin@workforce.com<br>
                        <strong>Password:</strong> admin123
                    </div>
                    <a href="/login" style="display: inline-block; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 5px;">Go to Login</a>
                </body>
                </html>
                """
                
    except Exception as e:
        db.session.rollback()
        return f"""
        <html>
        <body style="font-family: Arial; padding: 40px;">
            <h1 style="color: red;">❌ Reset Error</h1>
            <pre style="background: #f8f9fa; padding: 20px; border-radius: 5px;">{str(e)}</pre>
        </body>
        </html>
        """

# TEST PASSWORD ROUTE
@app.route('/test-password')
def test_password():
    """Test if password checking is working"""
    try:
        # Test 1: Basic password hashing
        test_password = 'admin123'
        test_hash = generate_password_hash(test_password)
        test_result = check_password_hash(test_hash, test_password)
        
        # Test 2: Check admin user
        admin = Employee.query.filter_by(email='admin@workforce.com').first()
        
        results = []
        results.append(f"Test 1 - Basic hash test: {'✅ PASS' if test_result else '❌ FAIL'}")
        
        if admin:
            results.append(f"Test 2 - Admin found: ✅ ID={admin.id}, Email={admin.email}")
            results.append(f"Test 3 - Admin has password_hash: {'✅ YES' if admin.password_hash else '❌ NO'}")
            
            if admin.password_hash:
                try:
                    # Test the actual check_password method
                    check_result = admin.check_password('admin123')
                    results.append(f"Test 4 - admin.check_password('admin123'): {'✅ PASS' if check_result else '❌ FAIL'}")
                    
                    # Also test direct check
                    direct_check = check_password_hash(admin.password_hash, 'admin123')
                    results.append(f"Test 5 - Direct check_password_hash: {'✅ PASS' if direct_check else '❌ FAIL'}")
                    
                    # Show hash details
                    results.append(f"Test 6 - Hash starts with: {admin.password_hash[:20]}...")
                    results.append(f"Test 7 - Hash length: {len(admin.password_hash)} chars")
                    
                except Exception as e:
                    results.append(f"Test 4 - Error in check_password: ❌ {str(e)}")
        else:
            results.append("Test 2 - Admin not found: ❌ Run /fix-db-now first")
        
        # Test 3: Force create a new hash for admin123
        new_hash = generate_password_hash('admin123')
        new_check = check_password_hash(new_hash, 'admin123')
        results.append(f"Test 8 - Fresh hash test: {'✅ PASS' if new_check else '❌ FAIL'}")
        
        # Build response
        return f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial; padding: 40px; background: #f5f5f5; }}
                .container {{ background: white; padding: 30px; border-radius: 10px; max-width: 800px; margin: 0 auto; }}
                .pass {{ color: green; }}
                .fail {{ color: red; }}
                pre {{ background: #f8f9fa; padding: 15px; border-radius: 5px; }}
                .btn {{ display: inline-block; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; margin: 10px 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Password System Test Results</h1>
                <pre>{'<br>'.join(results)}</pre>
                
                <h3>Next Steps:</h3>
                <p>If Test 4 or 5 fail, the password hash in the database doesn't match 'admin123'</p>
                
                <div>
                    <a href="/reset-admin-password" class="btn">Reset Password</a>
                    <a href="/force-login" class="btn">Force Login</a>
                    <a href="/login" class="btn">Try Normal Login</a>
                </div>
            </div>
        </body>
        </html>
        """
        
    except Exception as e:
        import traceback
        return f"""
        <html>
        <body style="font-family: Arial; padding: 40px;">
            <h1 style="color: red;">❌ Test Error</h1>
            <pre style="background: #f8f9fa; padding: 20px; border-radius: 5px;">{str(e)}\n\n{traceback.format_exc()}</pre>
        </body>
        </html>
        """

# FORCE LOGIN ROUTE
@app.route('/force-login')
def force_login():
    """Force login as admin - bypasses broken password check"""
    try:
        # Find admin user
        admin = Employee.query.filter_by(email='admin@workforce.com').first()
        
        if not admin:
            return """
            <html>
            <body style="font-family: Arial; padding: 40px;">
                <h1 style="color: red;">❌ Admin User Not Found</h1>
                <p>Run <a href="/fix-db-now">/fix-db-now</a> first to create admin user.</p>
            </body>
            </html>
            """
        
        # Force login without password check
        login_user(admin, remember=True)
        
        # Redirect based on role
        if admin.is_supervisor:
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
            
    except Exception as e:
        return f"""
        <html>
        <body style="font-family: Arial; padding: 40px;">
            <h1 style="color: red;">❌ Force Login Error</h1>
            <pre style="background: #f8f9fa; padding: 20px; border-radius: 5px;">{str(e)}</pre>
        </body>
        </html>
        """

# Import blueprints
from blueprints.auth import auth_bp
from blueprints.main import main_bp
from blueprints.employee import employee_bp
from blueprints.supervisor import supervisor_bp
from blueprints.schedule import schedule_bp
from blueprints.employee_import import employee_import_bp
from blueprints.reset_database import reset_db_bp

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(employee_bp)
app.register_blueprint(supervisor_bp)
app.register_blueprint(schedule_bp)
app.register_blueprint(employee_import_bp)
app.register_blueprint(reset_db_bp)

# Add 404 handler
@app.errorhandler(404)
def not_found_error(error):
    logger.warning(f"404 error: {request.url}")
    if request.endpoint and 'api' in request.endpoint:
        return jsonify({'error': 'Not found'}), 404
    return render_template('404.html'), 404

# Add 500 handler
@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {error}")
    db.session.rollback()
    if request.endpoint and 'api' in request.endpoint:
        return jsonify({'error': 'Internal server error'}), 500
    return render_template('500.html'), 500

# Health check endpoint
@app.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        with db.engine.connect() as conn:
            result = conn.execute(text('SELECT 1'))
            result.fetchone()
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 503

# Context processors
@app.context_processor
def inject_user_permissions():
    """Inject user permissions into all templates"""
    return dict(
        is_supervisor=lambda: current_user.is_authenticated and current_user.is_supervisor
    )

@app.context_processor
def inject_pending_counts():
    """Inject pending counts into all templates for navbar"""
    pending_time_off = 0
    pending_swaps = 0
    
    if current_user.is_authenticated and current_user.is_supervisor:
        try:
            pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        except Exception as e:
            logger.warning(f"Could not get pending time off count: {e}")
            
        try:
            pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        except Exception as e:
            logger.warning(f"Could not get pending swaps count: {e}")
    
    return dict(
        pending_time_off=pending_time_off,
        pending_swaps=pending_swaps
    )

# Utility functions
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# ==========================================
# AUTO-FIX DATABASE ON STARTUP
# ==========================================

print("Starting database schema check...")
with app.app_context():
    try:
        # First ensure all tables exist
        db.create_all()
        print("✓ Database tables verified/created")
        
        # Then run the column fixes if available
        try:
            from fix_db_columns import fix_database_schema
            print("Checking for missing columns...")
            fixes = fix_database_schema()
            if fixes > 0:
                print(f"✅ Applied {fixes} database fixes successfully!")
            else:
                print("✅ Database schema is up to date")
        except ImportError:
            print("⚠️  fix_db_columns.py not found - skipping database fixes")
        except Exception as e:
            print(f"⚠️  Could not run database fixes: {e}")
            
    except Exception as e:
        print(f"⚠️  Could not run database fixes: {e}")
        print("The app will continue but some features may not work correctly")

# ==========================================
# END OF DATABASE FIX SECTION
# ==========================================

# Run the application
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
