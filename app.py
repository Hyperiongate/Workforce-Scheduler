# app.py
"""
Main application file for Workforce Scheduler
Compatible with Flask 2.3+ (no before_first_request)
Fixed version with proper transaction handling for database fixes
"""

from flask import Flask, render_template, redirect, url_for, flash, jsonify, request
from flask_login import LoginManager, login_required, current_user
from flask_migrate import Migrate
import os
import logging
from datetime import datetime, date, timedelta
from sqlalchemy import text, inspect
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import OperationalError, ProgrammingError

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
            'keepalives_interval': 10,
            'keepalives_count': 5,
        }
    }
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workforce.db'
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {}

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File upload configuration
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = '/tmp/upload_files' if os.environ.get('RENDER') else 'upload_files'

# Create upload folder
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Import your models FIRST
from models import db, Employee

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    try:
        return Employee.query.get(int(user_id))
    except:
        return None

# Track if initialization has run
_initialized = False

# AUTOMATIC DATABASE FIX FUNCTION
def fix_database_schema():
    """Automatically fix missing columns in database"""
    logger.info("🔧 Starting database schema check...")
    
    try:
        # Test if is_admin column exists
        db.session.execute(text("SELECT is_admin FROM employee LIMIT 1"))
        logger.info("✅ is_admin column already exists")
    except (OperationalError, ProgrammingError) as e:
        if 'is_admin' in str(e):
            logger.info("🔧 Missing is_admin column detected, fixing...")
            try:
                # Add the missing column
                db.session.execute(text("ALTER TABLE employee ADD COLUMN is_admin BOOLEAN DEFAULT FALSE"))
                db.session.commit()
                logger.info("✅ Added is_admin column")
                
                # Set admin privileges
                db.session.execute(text("""
                    UPDATE employee 
                    SET is_admin = TRUE 
                    WHERE email = 'admin@workforce.com' 
                    OR email LIKE '%admin%'
                    OR is_supervisor = TRUE
                """))
                db.session.commit()
                logger.info("✅ Updated admin privileges")
                
            except Exception as fix_error:
                logger.error(f"❌ Could not fix database: {fix_error}")
                db.session.rollback()
        else:
            logger.error(f"❌ Database error: {e}")
        db.session.rollback()
    
    # Check for other potentially missing columns
    columns_to_check = [
        ("employee", "is_admin", "BOOLEAN DEFAULT FALSE"),
        ("employee", "max_hours_per_week", "INTEGER DEFAULT 48"),
        ("employee", "is_active", "BOOLEAN DEFAULT TRUE"),
        ("employee", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ("employee", "updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    ]
    
    for table, column, col_type in columns_to_check:
        try:
            db.session.execute(text(f"SELECT {column} FROM {table} LIMIT 1"))
        except (OperationalError, ProgrammingError):
            logger.info(f"🔧 Adding missing column: {table}.{column}")
            try:
                db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                db.session.commit()
                logger.info(f"✅ Added {column} column to {table}")
            except Exception as e:
                if 'already exists' not in str(e):
                    logger.error(f"❌ Could not add {column}: {e}")
                db.session.rollback()

# Create initial admin user if doesn't exist
def create_admin_user():
    """Create default admin user if it doesn't exist"""
    try:
        admin = Employee.query.filter_by(email='admin@workforce.com').first()
        if not admin:
            logger.info("Creating default admin user...")
            admin = Employee(
                email='admin@workforce.com',
                name='Admin User',
                employee_id='ADMIN001',
                is_supervisor=True,
                is_admin=True,
                is_active=True,
                department='Administration'
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            logger.info("✅ Created default admin user (admin@workforce.com / admin123)")
        else:
            # Ensure existing admin has is_admin flag
            if not admin.is_admin:
                admin.is_admin = True
                db.session.commit()
                logger.info("✅ Updated admin user with is_admin flag")
    except Exception as e:
        logger.error(f"Could not create/update admin user: {e}")
        db.session.rollback()

# Initialize database on first request
def initialize_database():
    """Initialize database - runs once on first request"""
    global _initialized
    if _initialized:
        return
    
    _initialized = True
    logger.info("=== Initializing Database ===")
    
    with app.app_context():
        try:
            # Create all tables
            db.create_all()
            logger.info("✅ Database tables verified/created")
            
            # Fix schema
            fix_database_schema()
            
            # Create admin user
            create_admin_user()
            
            logger.info("=== Database initialization complete ===")
        except Exception as e:
            logger.error(f"❌ Database initialization error: {e}")

# Import and register blueprints
try:
    from blueprints.auth import auth_bp
    app.register_blueprint(auth_bp)
    logger.info("✅ Auth blueprint loaded")
except ImportError as e:
    logger.error(f"❌ Could not import auth blueprint: {e}")

try:
    from blueprints.main import main_bp
    app.register_blueprint(main_bp)
    logger.info("✅ Main blueprint loaded")
except ImportError as e:
    logger.error(f"❌ Could not import main blueprint: {e}")

try:
    from blueprints.supervisor import supervisor_bp
    app.register_blueprint(supervisor_bp)
    logger.info("✅ Supervisor blueprint loaded")
except ImportError as e:
    logger.error(f"❌ Could not import supervisor blueprint: {e}")

try:
    from blueprints.employee import employee_bp
    app.register_blueprint(employee_bp)
    logger.info("✅ Employee blueprint loaded")
except ImportError as e:
    logger.error(f"❌ Could not import employee blueprint: {e}")

try:
    from blueprints.employee_import import employee_import_bp
    app.register_blueprint(employee_import_bp)
    logger.info("✅ Employee import blueprint loaded")
except ImportError as e:
    logger.error(f"❌ Could not import employee_import blueprint: {e}")

# Middleware to run initialization
@app.before_request
def before_request():
    """Run initialization before first request"""
    initialize_database()

# Root route
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_supervisor:
            return redirect(url_for('supervisor.dashboard'))
        else:
            return redirect(url_for('main.employee_dashboard'))
    return redirect(url_for('auth.login'))

# Health check route
@app.route('/health')
def health():
    try:
        # Test database connection
        db.session.execute(text('SELECT 1'))
        
        # Check if admin exists
        admin_exists = Employee.query.filter_by(email='admin@workforce.com').first() is not None
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'admin_exists': admin_exists,
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

# Database fix endpoint - manual trigger
@app.route('/fix-database')
def fix_database():
    """Manual endpoint to fix database issues"""
    if not request.args.get('confirm') == 'yes':
        return "Add ?confirm=yes to run database fixes", 400
    
    try:
        with app.app_context():
            fix_database_schema()
            create_admin_user()
        return jsonify({
            'status': 'success',
            'message': 'Database fixes applied',
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

# Complete fix route with proper transaction handling
@app.route('/complete-fix')
def complete_fix():
    """Complete database fix with proper transaction handling"""
    results = {
        'columns_added': [],
        'columns_exists': [],
        'errors': [],
        'admin_status': None,
        'tables_checked': []
    }
    
    # First, rollback any bad transactions
    try:
        db.session.rollback()
        db.session.close()
        db.engine.dispose()
        results['transaction_cleanup'] = 'Success - cleared bad transactions'
    except Exception as e:
        results['transaction_cleanup'] = f'Warning: {str(e)}'
    
    # Create new connection
    try:
        db.session.execute(text('SELECT 1'))
        db.session.commit()
        results['database_connection'] = 'Connected'
    except Exception as e:
        results['database_connection'] = f'Failed: {str(e)}'
        return jsonify(results), 500
    
    # Fix is_admin column with individual transactions
    try:
        # Check if column exists
        result = db.session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'employee' 
            AND column_name = 'is_admin'
        """))
        
        if result.rowcount == 0:
            # Column doesn't exist, add it
            db.session.execute(text("ALTER TABLE employee ADD COLUMN is_admin BOOLEAN DEFAULT FALSE"))
            db.session.commit()
            results['columns_added'].append('is_admin')
        else:
            results['columns_exists'].append('is_admin')
            db.session.commit()
    except Exception as e:
        results['errors'].append(f'is_admin check/add: {str(e)}')
        db.session.rollback()
    
    # Check other columns one by one
    columns_to_check = [
        ('max_hours_per_week', 'INTEGER DEFAULT 48'),
        ('is_active', 'BOOLEAN DEFAULT TRUE'),
        ('created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'),
        ('updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    ]
    
    for column_name, column_type in columns_to_check:
        try:
            # Check if column exists
            result = db.session.execute(text(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'employee' 
                AND column_name = '{column_name}'
            """))
            
            if result.rowcount == 0:
                # Add column
                db.session.execute(text(f"ALTER TABLE employee ADD COLUMN {column_name} {column_type}"))
                db.session.commit()
                results['columns_added'].append(column_name)
            else:
                results['columns_exists'].append(column_name)
                db.session.commit()
        except Exception as e:
            results['errors'].append(f'{column_name}: {str(e)}')
            db.session.rollback()
    
    # Update admin privileges
    try:
        db.session.execute(text("""
            UPDATE employee 
            SET is_admin = TRUE 
            WHERE (email = 'admin@workforce.com' OR is_supervisor = TRUE)
            AND is_admin IS NOT NULL
        """))
        db.session.commit()
        results['admin_privileges_updated'] = 'Success'
    except Exception as e:
        results['errors'].append(f'Update privileges: {str(e)}')
        db.session.rollback()
    
    # Check/create admin user with raw SQL
    try:
        # Check if admin exists
        result = db.session.execute(text("""
            SELECT email, name, is_admin, is_supervisor 
            FROM employee 
            WHERE email = 'admin@workforce.com'
        """))
        admin_row = result.fetchone()
        
        if admin_row:
            results['admin_status'] = 'exists'
            # Update to ensure admin privileges
            db.session.execute(text("""
                UPDATE employee 
                SET is_admin = TRUE, 
                    is_supervisor = TRUE,
                    is_active = TRUE
                WHERE email = 'admin@workforce.com'
            """))
            db.session.commit()
            results['admin_status'] = 'updated'
        else:
            # Create admin with raw SQL
            db.session.execute(text("""
                INSERT INTO employee (
                    email, name, employee_id, 
                    is_supervisor, is_admin, is_active, 
                    department, password_hash, crew
                ) VALUES (
                    'admin@workforce.com',
                    'Admin User',
                    'ADMIN001',
                    TRUE, TRUE, TRUE,
                    'Administration',
                    :password_hash,
                    'A'
                )
            """), {
                'password_hash': '$2b$12$YP6JXgK3P7N3rHqr0J5FYuPQjW2aFYXoVzV6M8RjN6cGyCZLKGNEi'
            })
            db.session.commit()
            results['admin_status'] = 'created'
    except Exception as e:
        results['errors'].append(f'Admin user: {str(e)}')
        db.session.rollback()
    
    # Get table list
    try:
        inspector = inspect(db.engine)
        results['tables_checked'] = inspector.get_table_names()
    except Exception as e:
        results['errors'].append(f'Table inspection: {str(e)}')
    
    # Final verification
    try:
        # Verify is_admin column exists
        result = db.session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'employee' 
            AND column_name = 'is_admin'
        """))
        results['is_admin_verified'] = result.rowcount > 0
        
        # Verify admin user
        result = db.session.execute(text("""
            SELECT email, is_admin 
            FROM employee 
            WHERE email = 'admin@workforce.com'
        """))
        admin = result.fetchone()
        results['admin_verified'] = admin is not None
    except Exception as e:
        results['verification_error'] = str(e)
    
    # Prepare response
    success = len(results['errors']) == 0 and results.get('is_admin_verified', False)
    status_code = 200 if success else 500
    
    # Build HTML response
    html_response = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Database Fix Results</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .success {{ color: green; }}
            .error {{ color: red; }}
            .info {{ color: blue; }}
            h1 {{ color: #333; }}
            h2 {{ color: #666; margin-top: 30px; }}
            ul {{ margin: 10px 0; }}
            .summary {{ 
                background: #f0f0f0; 
                padding: 20px; 
                border-radius: 5px; 
                margin: 20px 0;
            }}
            .critical {{ 
                background: #ffe0e0; 
                padding: 15px; 
                border-radius: 5px; 
                margin: 20px 0;
                border: 2px solid #ff0000;
            }}
        </style>
    </head>
    <body>
        <h1>Database Fix Results - Transaction Safe Version</h1>
        
        <div class="summary">
            <h2>Summary</h2>
            <p>Transaction Cleanup: <span class="success">{results.get('transaction_cleanup', 'Not performed')}</span></p>
            <p>Database Connection: <span class="{'success' if results['database_connection'] == 'Connected' else 'error'}">{results['database_connection']}</span></p>
            <p>Columns Added: <span class="success">{len(results['columns_added'])}</span></p>
            <p>Columns Already Exist: <span class="info">{len(results['columns_exists'])}</span></p>
            <p>Errors: <span class="error">{len(results['errors'])}</span></p>
            <p>Admin Status: <span class="{'success' if results['admin_status'] else 'error'}">{results['admin_status'] or 'failed'}</span></p>
            <p>is_admin Column Verified: <span class="{'success' if results.get('is_admin_verified') else 'error'}">{results.get('is_admin_verified', False)}</span></p>
        </div>
        
        <h2>Columns Added</h2>
        <ul>
        {''.join(f'<li class="success">✓ {col}</li>' for col in results['columns_added']) or '<li>None</li>'}
        </ul>
        
        <h2>Columns Already Exist</h2>
        <ul>
        {''.join(f'<li class="info">• {col}</li>' for col in results['columns_exists']) or '<li>None</li>'}
        </ul>
        
        {'<h2>Errors</h2><ul>' + ''.join(f'<li class="error">✗ {err}</li>' for err in results['errors']) + '</ul>' if results['errors'] else ''}
        
        {'<div class="critical"><h2>⚠️ CRITICAL ISSUE</h2><p>The is_admin column is still not being added. You need to use a PostgreSQL client to add it manually.</p></div>' if not results.get('is_admin_verified') else ''}
        
        <div class="summary">
            <h2>Next Steps</h2>
            {'<p class="success">✅ Database should be fixed! <a href="/login">Try logging in now</a> with:<br>Email: admin@workforce.com<br>Password: admin123</p>' if success else '<p class="error">The automatic fix is still failing. You need to manually add the column using a PostgreSQL client.</p>'}
        </div>
        
        <p style="margin-top: 40px;">
            <a href="/">← Back to Home</a> | 
            <a href="/health">Check Health</a> | 
            <a href="/login">Go to Login</a> |
            <a href="/complete-fix">Try Again</a>
        </p>
    </body>
    </html>
    """
    
    return html_response, status_code

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    logger.warning(f"404 error: {request.url}")
    if current_user.is_authenticated:
        flash('Page not found', 'warning')
        return redirect(url_for('index'))
    return redirect(url_for('auth.login'))

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {error}")
    db.session.rollback()
    flash('An internal error occurred', 'danger')
    return redirect(url_for('index'))

# Context processor for templates
@app.context_processor
def inject_now():
    return {'now': datetime.utcnow}

# Run initialization at startup when running directly
if __name__ == '__main__':
    with app.app_context():
        initialize_database()
    
    # Run the app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    # When running under gunicorn, initialize on import
    with app.app_context():
        initialize_database()
